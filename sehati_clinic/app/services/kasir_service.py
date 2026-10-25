"""
KasirService — auto-hitung tagihan, eksekusi bayar, void item, rekap shift.

Flow:
1. get_tagihan: read-only auto-hitung berdasarkan kunjungan_tindakan SELESAI
   + kunjungan_resep PENDING. Apply diskon dari MembershipService. Bulletproof
   check: kalau sudah ada transaksi, return LUNAS.
2. proses_bayar: atomic — INSERT transaksi_kasir + detail_produk + pembayaran,
   mark resep DIBAYAR, transition status kunjungan.
3. void_item: validate PIN dokter/admin, set status_item BATAL.
4. rekap_shift_kasir: aggregate transaksi kasir sejak waktu_mulai_shift.
5. lihat_antrian: list antri bayar + riwayat bayar hari ini (akses cetak nota).

Audit hooks: log per aksi mutating.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.db.models import (
    StafRoleEnum,
    StatusAksiAuditEnum,
    StatusTindakanEnum,
    StatusTransaksiEnum,
    TransaksiDetailProduk,
    MasterTreatment,
    TransaksiDetailRacikan,
    TransaksiDetailTindakan,
    TransaksiKasir,
    TransaksiPembayaran,
    VoidApprovalMethodEnum,
    VoidReasonEnum,
)
from app.repositories.kasir_repo import KasirRepository
from app.repositories.kunjungan_repo import KunjunganRepository
from app.repositories.staf_repo import StafRepository
from app.schemas.kasir import (
    AntrianKasirItem,
    AntrianKasirResponse,
    MembershipPendingItem,
    BayarRequest,
    RekapPerMetode,
    RekapShiftItem,
    RekapShiftResponse,
    RincianProduk,
    RincianRacikan,
    RincianRacikanBahan,
    RincianTindakan,
    RingkasanBiaya,
    RiwayatBayarItem,
    TagihanResponse,
    VoidItemRequest,
)
from app.services._baca_segar import mulai_baca_segar
from app.services.audit_service import AuditService
from app.services.membership_service import MembershipService
from app.services.komisi_service import KomisiService


# Role yang boleh otorisasi void
_ROLES_BOLEH_OTORISASI_VOID = {
    StafRoleEnum.DOKTER.value,
    StafRoleEnum.ADMIN.value,
    StafRoleEnum.SUPERADMIN.value,
    StafRoleEnum.OWNER.value,
}

# Role yang boleh menyetujui refund atas transaksi HARI LAMPAU (T32, keputusan
# dr. Hansen 2026-10-05: "PIN admin"). SENGAJA himpunan sendiri, BUKAN
# _ROLES_BOLEH_OTORISASI_VOID: himpunan void memuat Dokter, dan menyetujui uang
# keluar bukan wewenang dokter. Satu himpunan, dua arti = jebakan CLAUDE.md §4.1.
_ROLES_PENYETUJU_REFUND = {
    StafRoleEnum.ADMIN.value,
    StafRoleEnum.SUPERADMIN.value,
    StafRoleEnum.OWNER.value,
}


def daftar_pengembalian(db: Session, id_transaksi_list) -> dict:
    """{id_transaksi: [refund...]} — semua uang/nilai yang SUDAH dikembalikan atas transaksi.

    Kenapa ada (dr. Hansen 2026-10-05, saat mencoba void #270): sejak T32 total transaksi
    asal TIDAK dikurangi refund, jadi layar transaksi yang hanya membaca `total_tagihan`
    menampilkan "Rp 650.000 · BAYAR" walau Rp 150.000 sudah kembali ke pasien. Satu sumber
    untuk Cari Transaksi, halaman tagihan, dan pesan void — jangan menulis query refund
    sendiri di layar (CLAUDE.md §4.1).
    Baris memuat nomor & id retur bila refund berasal dari retur dari pasien.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import aliased
    from app.db.models import MasterStaf, ReturPasien, TransaksiRefund
    ids = [i for i in (id_transaksi_list or []) if i]
    if not ids:
        return {}
    pemroses, penyetuju = aliased(MasterStaf), aliased(MasterStaf)
    rows = db.execute(
        select(TransaksiRefund, ReturPasien.id_retur, ReturPasien.nomor_retur,
               ReturPasien.jenis, pemroses.nama_staf, penyetuju.nama_staf)
        .outerjoin(ReturPasien, ReturPasien.id_refund == TransaksiRefund.id_refund)
        .outerjoin(pemroses, pemroses.id_staf == TransaksiRefund.id_staf_refund)
        .outerjoin(penyetuju, penyetuju.id_staf == TransaksiRefund.id_staf_otorisasi)
        .where(TransaksiRefund.id_transaksi.in_(ids))
        .order_by(TransaksiRefund.id_refund)
    ).all()
    out: dict = {}
    for ref, id_retur, nomor, jenis, nama_p, nama_s in rows:
        out.setdefault(ref.id_transaksi, []).append({
            "id_refund": ref.id_refund, "tgl": ref.tgl_refund,
            "nilai": Decimal(str(ref.nilai_refund or 0)),
            "metode": (ref.metode_refund or "TUNAI").upper(),
            "id_retur": id_retur, "nomor_retur": nomor,
            "jenis": (jenis.value if hasattr(jenis, "value") else jenis) if jenis else None,
            "pemroses": nama_p or "-", "penyetuju": nama_s, "alasan": ref.alasan or "",
        })
    return out


def pengembalian_kunjungan(db: Session, id_kunjungan: int) -> list:
    """Semua pengembalian atas SEMUA transaksi kunjungan ini (asal + TUKAR), datar,
    urut waktu — untuk kotak "Pengembalian & retur" di halaman tagihan. Satu kunjungan
    bisa punya transaksi TUKAR sejak retur dari pasien, jadi tidak cukup satu transaksi."""
    from sqlalchemy import select
    ids = db.execute(select(TransaksiKasir.id_transaksi)
                     .where(TransaksiKasir.id_kunjungan == id_kunjungan)).scalars().all()
    per = daftar_pengembalian(db, ids)
    flat = [dict(r, id_transaksi=t) for t, rows in per.items() for r in rows]
    return sorted(flat, key=lambda r: (r["tgl"] is None, r["tgl"] or 0, r["id_refund"]))


def transaksi_kunjungan(db: Session, id_kunjungan: int) -> list:
    """SEMUA transaksi kunjungan ini, urut waktu bayar, dengan nilai bersihnya — untuk
    halaman tagihan yang sudah lunas (dr. Hansen 2026-10-05).

    Kenapa perlu: `get_tagihan` memakai transaksi TERAKHIR (benar untuk cutoff tagihan
    susulan), dan sejak retur TUKAR menempel di kunjungan asal, header halaman jadi
    menunjuk transaksi TUKAR (#1324 Rp 30.000) sementara daftar obatnya memuat obat
    transaksi asal juga. Daftar ini menampilkan setiap transaksi dengan notanya sendiri.

    `bersih` = total − pengembalian atas transaksi ITU; VOID → 0 (tidak dihitung).
    Uang TUKAR saling meniadakan: transaksi TUKAR dibayar metode TUKAR dan transaksi
    asalnya punya pengembalian TUKAR senilai sama, jadi jumlah `bersih` = uang yang
    benar-benar dibayar pasien untuk kunjungan ini."""
    from sqlalchemy import select
    rows = db.execute(select(TransaksiKasir)
                      .where(TransaksiKasir.id_kunjungan == id_kunjungan)
                      .order_by(TransaksiKasir.waktu_bayar, TransaksiKasir.id_transaksi)
                      ).scalars().all()
    per = daftar_pengembalian(db, [t.id_transaksi for t in rows])
    hasil = []
    for t in rows:
        total = Decimal(str(t.total_tagihan or 0))
        kembali = sum((r["nilai"] for r in per.get(t.id_transaksi, [])), Decimal("0"))
        void = t.status_transaksi == "VOID"
        hasil.append({
            "id_transaksi": t.id_transaksi,
            "jenis": t.jenis_transaksi or "KLINIS",
            "status": t.status_transaksi,
            "waktu_bayar": t.waktu_bayar,
            "total": total,
            "kembali": kembali,
            "bersih": Decimal("0") if void else total - kembali,
        })
    return hasil


def daftar_penyetuju_refund(db: Session, kecuali_id_staf: Optional[int]) -> list:
    """Staf yang BISA dipilih sebagai penyetuju PIN refund/retur: aktif, ber-PIN, berperan
    `_ROLES_PENYETUJU_REFUND`, dan BUKAN orang yang sedang memproses (empat mata).
    Satu sumber untuk layar Obat Tertunda dan layar Retur dari pasien — server tetap
    memverifikasi ulang (`_otorisasi_refund_lampau`); daftar ini hanya untuk tampilan."""
    from sqlalchemy import select
    from app.db.models import MasterStaf
    return [
        s for s in db.execute(
            select(MasterStaf).where(MasterStaf.is_active.is_(True))
            .where(MasterStaf.pin.is_not(None)).where(MasterStaf.pin != "")
            .order_by(MasterStaf.nama_staf)
        ).scalars().all()
        if (s.role.value if hasattr(s.role, "value") else str(s.role)) in _ROLES_PENYETUJU_REFUND
        and s.id_staf != kecuali_id_staf
    ]


class KasirService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = KasirRepository(db)
        self.kunjungan_repo = KunjunganRepository(db)
        self.staf_repo = StafRepository(db)
        self.membership = MembershipService(db)
        self.audit = AuditService(db)

    # =========================================================================
    # ANTRIAN
    # =========================================================================
    def lihat_antrian(self) -> AntrianKasirResponse:
        from datetime import date
        today = date.today()
        rows = self.repo.list_antrian_bayar(today=today)
        items = []
        for kunjungan, pasien, n_tindakan, n_resep, belum_selesai in rows:
            tipe = (
                pasien.tipe_membership.value
                if hasattr(pasien.tipe_membership, "value")
                else str(pasien.tipe_membership) if pasien.tipe_membership else None
            )
            items.append(AntrianKasirItem(
                id_kunjungan=kunjungan.id_kunjungan,
                nomor_antrean=kunjungan.nomor_antrean,
                tgl_kunjungan=kunjungan.tgl_kunjungan,
                status_antrian=kunjungan.status_antrian,
                id_pasien=pasien.id_pasien,
                no_rm=pasien.no_rm,
                nama_pasien=pasien.nama,
                tipe_membership=tipe,
                jumlah_tindakan=n_tindakan,
                jumlah_resep=n_resep,
                tindakan_belum_selesai=belum_selesai,
                jenis_kunjungan=getattr(kunjungan, "jenis_kunjungan", "KLINIS"),
                peresep_luar_nama=getattr(kunjungan, "peresep_luar_nama", None),
            ))

        # ====== Riwayat transaksi yang sudah lunas hari ini ======
        riwayat_rows = self.repo.list_riwayat_bayar_hari_ini(today=today)
        riwayat: list[RiwayatBayarItem] = []
        for trx, kunjungan, pasien in riwayat_rows:
            # Lookup nama kasir (jika ada)
            nama_kasir = None
            if trx.id_staf_kasir:
                staf = self.staf_repo.get_by_id(trx.id_staf_kasir)
                if staf:
                    nama_kasir = staf.nama_staf
            riwayat.append(RiwayatBayarItem(
                id_transaksi=trx.id_transaksi,
                id_kunjungan=trx.id_kunjungan,
                jenis_transaksi=getattr(trx, "jenis_transaksi", "KLINIS"),
                waktu_bayar=trx.waktu_bayar,
                id_pasien=pasien.id_pasien,
                no_rm=pasien.no_rm,
                nama_pasien=pasien.nama,
                total_bayar=Decimal(str(trx.total_tagihan or 0)),
                nama_kasir=nama_kasir,
            ))

        # ====== Membership PENDING (menunggu bayar) — transaksi terpisah ======
        mship_rows = self.repo.list_membership_pending()
        membership_pending: list[MembershipPendingItem] = []
        for hist, pasien, tier in mship_rows:
            tipe_now = (
                pasien.tipe_membership.value
                if hasattr(pasien.tipe_membership, "value")
                else str(pasien.tipe_membership) if pasien.tipe_membership else None
            )
            membership_pending.append(MembershipPendingItem(
                id_history=hist.id_history,
                id_pasien=pasien.id_pasien,
                no_rm=pasien.no_rm,
                nama_pasien=pasien.nama,
                tipe_membership_sekarang=tipe_now,
                nama_tier=tier.nama_tier,
                harga_aktivasi=Decimal(str(tier.harga_aktivasi or 0)),
            ))

        return AntrianKasirResponse(
            tanggal=today,
            total=len(items),
            data=items,
            riwayat=riwayat,
            riwayat_total=len(riwayat),
            membership_pending=membership_pending,
            membership_pending_total=len(membership_pending),
        )

    # =========================================================================
    # TAGIHAN — auto-hitung (read-only)
    # =========================================================================
    def get_tagihan(self, id_kunjungan: int, user_role=None) -> TagihanResponse:
        """
        Auto-hitung tagihan. Mendukung FLOW-D Part B (DEC-050):
        - Kalau ada existing transaksi DAN ada items baru (tindakan SELESAI atau
          resep PENDING dengan timestamp > waktu_bayar terakhir) → mode billing
          untuk items baru saja (tagihan tambahan).
        - Kalau ada existing transaksi TANPA items baru → view-only sudah_lunas
          dengan rincian populated dari semua SELESAI tindakan + resep non-BATAL.
        - Kalau tidak ada existing → normal billing untuk semua items.
        """
        kp = self.repo.get_kunjungan_with_pasien(id_kunjungan)
        if kp is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Kunjungan {id_kunjungan} tidak ditemukan.",
            )
        kunjungan, pasien = kp
        tipe = (
            pasien.tipe_membership.value
            if hasattr(pasien.tipe_membership, "value")
            else str(pasien.tipe_membership) if pasien.tipe_membership else None
        )

        from app.db.models import PasienRencanaTreatment as _PRT
        from app.db.models import KunjunganResep as _KR
        from app.db.models import MasterProduk as _MP
        from sqlalchemy import select as _sel, func as _func

        # Existing transaksi (return LATEST per DEC-050)
        existing = self.repo.get_transaksi_for_kunjungan(id_kunjungan)
        cutoff = existing.waktu_bayar if (existing is not None) else None

        def _compute_charge(tindakan, treatment):
            """Series-aware pricing (DEC-049)."""
            pakai_kuota = tindakan.id_kuota_member is not None
            charge = Decimal("0") if pakai_kuota else Decimal(str(treatment.harga))
            if tindakan.id_rencana is not None and not pakai_kuota:
                rencana = self.db.get(_PRT, tindakan.id_rencana)
                if rencana is not None:
                    if rencana.urutan_sesi == 1:
                        # Audit T4-11: anggota SERIES INI saja (app/services/_series.py). Dulu
                        # semua rencana treatment yang sama dari kunjungan ini — dua series
                        # di satu kunjungan → sesi 1 ditagih N1+N2 sesi.
                        from app.services._series import jumlah_sesi as _jumlah_sesi
                        total_sesi = _jumlah_sesi(self.db, rencana)
                        per_sesi = (
                            Decimal(str(treatment.harga_paket))
                            if treatment.harga_paket is not None
                            else Decimal(str(treatment.harga))
                        )
                        charge = per_sesi * Decimal(str(total_sesi))
                    else:
                        charge = Decimal("0")
            return charge, pakai_kuota

        # ===== Query ALL items =====
        # Bayar dulu T2-1: bukan BATAL, status apa pun (PENDING/PROSES = dibayar di muka).
        all_tindakan = self.repo.get_tindakan_untuk_tagihan(id_kunjungan)
        all_resep_pending = self.repo.get_resep_pending_for_billing(id_kunjungan)
        all_racikan_pending = self.repo.get_racikan_pending_for_billing(id_kunjungan)

        def _to_rincian_racikan(h, bahan_rows) -> RincianRacikan:
            """KunjunganRacikan + bahannya → baris tagihan. Harga TIDAK dihitung ulang."""
            return RincianRacikan(
                id_kunjungan_racikan=h.id_kunjungan_racikan,
                nama=h.nama_snapshot,
                jenis_racik=h.jenis_racik,
                jumlah_unit=int(h.jumlah_unit or 0),
                aturan_pakai=h.aturan_pakai,
                subtotal_bahan=Decimal(str(h.subtotal_bahan or 0)),
                biaya_racik=Decimal(str(h.biaya_racik or 0)),
                total=Decimal(str(h.total or 0)),
                status_item=h.status_item,
                bahan=[
                    RincianRacikanBahan(
                        id_produk=b.id_produk,
                        nama=b.nama_snapshot,
                        dipakai=float(b.dipakai or 0),
                        satuan_dipakai=b.satuan_dipakai,
                    )
                    for b in bahan_rows
                ],
            )

        # ===== Detect "new" items (FLOW-D Part B) =====
        # Tindakan "baru" = `tindakan_bisa_ditagih()` (bukan BATAL, BELUM punya transaksi
        # pembayar) — ekspresi yang SAMA dengan (K) di `_status_kunjungan`; jangan menyaring
        # ulang di sini. Bayar dulu T1-2: tindakan ditandai saat dibayar, sama seperti
        # resep/racikan (Audit T4-1) — jadi tak perlu lagi membandingkan jam. Dulu
        # `waktu_selesai > waktu_bayar`: tindakan yang selesai di detik yang SAMA dengan bayar
        # (atau sebelum bayar tapi tidak ikut ditagih) hilang dari tagihan susulan tanpa
        # jejak. T2-1: dulu hanya SELESAI; kini PENDING/PROSES ikut (dibayar di muka) —
        # `_compute_charge` (kuota/series) berlaku sama untuk semuanya. `all_tindakan` tetap
        # memuat semua yang bukan BATAL untuk mode lihat-saja di bawah.
        new_tindakan = self.repo.get_tindakan_untuk_tagihan(id_kunjungan, hanya_bisa_ditagih=True)
        if cutoff is not None:
            # Audit T4-1 (2026-10-15): resep & racikan PENDING = BELUM ditagih, apa pun
            # waktunya — bayar kini hanya menandai baris yang ditagih, jadi PENDING tidak
            # pernah berarti "sudah dibayar". Dulu disaring `waktu_input > cutoff`: resep yang
            # masuk SELAMA bayar (waktu_input < waktu_bayar) tak pernah muncul lagi — dulu
            # tak terasa karena ia diam-diam ikut DIBAYAR.
            new_resep = list(all_resep_pending)
            new_racikan = list(all_racikan_pending)
        else:
            new_resep = all_resep_pending
            new_racikan = all_racikan_pending

        has_new_items = (
            (len(new_tindakan) > 0) or (len(new_resep) > 0) or (len(new_racikan) > 0)
        )

        # ===== VIEW-ONLY MODE (sudah lunas, no new items) =====
        if existing is not None and not has_new_items:
            rincian_tindakan_view: list[RincianTindakan] = []
            # Tanpa item baru, setiap tindakan bukan-BATAL di `all_tindakan` pasti sudah
            # ber-`id_transaksi` (yang belum adalah item "baru" → mode tagih di bawah). Jadi
            # ini = tindakan yang sudah dibayar, APA PUN statusnya (prabayar tampil PENDING).
            for tindakan, treatment in all_tindakan:
                charge, pakai_kuota = _compute_charge(tindakan, treatment)
                rincian_tindakan_view.append(RincianTindakan(
                    id_kunjungan_tindakan=tindakan.id_kunjungan_tindakan,
                    id_treatment=tindakan.id_treatment,
                    nama_treatment=treatment.nama_treatment,
                    harga=charge,
                    pakai_kuota_member=pakai_kuota,
                    status_tindakan=getattr(tindakan.status_tindakan, "value",
                                            tindakan.status_tindakan),
                ))
            # Phase 4 (#364): Kalau transaksi VOID, cascade FLOW-V6 sudah ubah
            # resep DIBAYAR → BATAL. Untuk tampil di Detail Tagihan, include BATAL juga.
            # Existing variable di sini adalah transaksi (sudah ada).
            _existing_voided = (
                getattr(existing, "status_transaksi", "BAYAR") == "VOID"
            )
            if _existing_voided:
                # Tampilkan SEMUA items (DIBAYAR + BATAL) untuk konteks void
                resep_view = self.db.execute(
                    _sel(_KR, _MP)
                    .join(_MP, _KR.id_produk == _MP.id_produk)
                    .where(_KR.id_kunjungan == id_kunjungan)
                    .order_by(_KR.id_resep.asc())
                ).all()
            else:
                # Mode normal sudah_lunas: hide BATAL
                resep_view = self.db.execute(
                    _sel(_KR, _MP)
                    .join(_MP, _KR.id_produk == _MP.id_produk)
                    .where(_KR.id_kunjungan == id_kunjungan)
                    .where(_KR.status_item != "BATAL")
                    .order_by(_KR.id_resep.asc())
                ).all()
            rincian_produk_view: list[RincianProduk] = []
            for resep, produk in resep_view:
                harga_satuan = Decimal(str(produk.harga_jual or 0))
                qty = Decimal(str(resep.qty or 0))
                sub = harga_satuan * qty
                rincian_produk_view.append(RincianProduk(
                    id_resep=resep.id_resep,
                    id_produk=resep.id_produk,
                    nama_produk=produk.nama_produk,
                    qty=float(resep.qty),
                    harga_satuan=harga_satuan,
                    subtotal=sub,
                    status_item=(
                        resep.status_item.value
                        if hasattr(resep.status_item, "value")
                        else str(resep.status_item) if resep.status_item else None
                    ),
                ))
            # Racikan untuk tampilan (bukan untuk ditagih ulang): sama polanya dengan
            # resep — sembunyikan BATAL kecuali transaksinya memang sudah di-void.
            from app.db.models.racikan import (
                KunjunganRacikan as _KRC,
                KunjunganRacikanBahan as _KRCB,
            )
            _racik_q = (
                _sel(_KRC)
                .where(_KRC.id_kunjungan == id_kunjungan)
                .order_by(_KRC.id_kunjungan_racikan.asc())
            )
            if not _existing_voided:
                _racik_q = _racik_q.where(_KRC.status_item != "BATAL")
            rincian_racikan_view: list[RincianRacikan] = []
            for _h in self.db.execute(_racik_q).scalars().all():
                _bahan = self.db.execute(
                    _sel(_KRCB)
                    .where(_KRCB.id_kunjungan_racikan == _h.id_kunjungan_racikan)
                    .order_by(_KRCB.id_kunjungan_racikan_bahan.asc())
                ).scalars().all()
                rincian_racikan_view.append(_to_rincian_racikan(_h, _bahan))

            # Phase 4 (#364): cek apakah transaksi existing sudah di-void.
            is_voided = (
                getattr(existing, "status_transaksi", "BAYAR") == "VOID"
            )
            voided_by_nama = None
            if is_voided and getattr(existing, "void_by_id_staf", None):
                voider = self.staf_repo.get_by_id(existing.void_by_id_staf)
                voided_by_nama = voider.nama_staf if voider else None

            # Phase 7 (#364): Force past-day void eligibility computation
            can_force = False
            days_past_calc = 0
            max_days_calc = 0
            if not is_voided and user_role is not None and existing.waktu_bayar is not None:
                max_days_calc = self._MAX_PAST_DAYS_BY_ROLE.get(user_role, 0)
                # Use explicit role membership; Kasir max=0 but harus tetap eligible day 0
                if user_role in self._MAX_PAST_DAYS_BY_ROLE:
                    now_check = self._now_utc7()
                    days_past_calc = self._days_past(existing.waktu_bayar, now_check)
                    # Kasir limit=0 (only day 0). Admin/Owner limit lebih besar.
                    if 0 <= days_past_calc <= max_days_calc:
                        can_force = True
            return TagihanResponse(
                id_kunjungan=id_kunjungan,
                nama_pasien=pasien.nama,
                no_rm=pasien.no_rm,
                tipe_membership=tipe,
                sudah_lunas=True,
                waktu_bayar=existing.waktu_bayar,
                id_transaksi_existing=existing.id_transaksi,
                is_voided=is_voided,
                void_at=getattr(existing, "void_at", None),
                void_reason_code=getattr(existing, "void_reason_code", None),
                void_reason_note=getattr(existing, "void_reason_note", None),
                voided_by_nama=voided_by_nama,
                late_void=getattr(existing, "late_void", False) or False,
                can_force_void_past_day=can_force,
                days_past=days_past_calc,
                max_force_days=max_days_calc,
                message=(
                    "TAGIHAN SUDAH DI-VOID — transaksi sudah dibatalkan."
                    if is_voided
                    else "TAGIHAN SUDAH LUNAS — kunjungan ini sudah ada transaksi."
                ),
                rincian_tindakan=rincian_tindakan_view,
                rincian_produk=rincian_produk_view,
                rincian_racikan=rincian_racikan_view,
                ringkasan_biaya=RingkasanBiaya(
                    subtotal_tindakan=Decimal("0"),
                    subtotal_produk=Decimal("0"),
                    subtotal_racikan=Decimal("0"),
                    subtotal=Decimal("0"),
                    persen_diskon_treatment=Decimal("0"),
                    persen_diskon_produk=Decimal("0"),
                    nominal_diskon_treatment=Decimal("0"),
                    nominal_diskon_produk=Decimal("0"),
                    nominal_diskon_total=Decimal("0"),
                    total_tagihan=Decimal(str(existing.total_tagihan or 0)),
                ),
            )

        # ===== BILLING MODE (no existing, OR has new items = tagihan tambahan) =====
        rincian_tindakan: list[RincianTindakan] = []
        subtotal_tindakan = Decimal("0")
        for tindakan, treatment in new_tindakan:
            charge, pakai_kuota = _compute_charge(tindakan, treatment)
            subtotal_tindakan += charge
            rincian_tindakan.append(RincianTindakan(
                id_kunjungan_tindakan=tindakan.id_kunjungan_tindakan,
                id_treatment=tindakan.id_treatment,
                nama_treatment=treatment.nama_treatment,
                harga=charge,
                pakai_kuota_member=pakai_kuota,
                status_tindakan=getattr(tindakan.status_tindakan, "value",
                                        tindakan.status_tindakan),
            ))

        rincian_produk: list[RincianProduk] = []
        subtotal_produk = Decimal("0")
        for resep, produk in new_resep:
            harga_satuan = Decimal(str(produk.harga_jual or 0))
            qty = Decimal(str(resep.qty or 0))
            sub = harga_satuan * qty
            subtotal_produk += sub
            rincian_produk.append(RincianProduk(
                id_resep=resep.id_resep,
                id_produk=resep.id_produk,
                nama_produk=produk.nama_produk,
                qty=float(resep.qty),
                harga_satuan=harga_satuan,
                subtotal=sub,
                status_item=(
                    resep.status_item.value
                    if hasattr(resep.status_item, "value")
                    else str(resep.status_item) if resep.status_item else None
                ),
            ))

        rincian_racikan: list[RincianRacikan] = []
        subtotal_racikan = Decimal("0")
        for _h, _bahan in new_racikan:
            _row = _to_rincian_racikan(_h, _bahan)
            subtotal_racikan += _row.total
            rincian_racikan.append(_row)

        diskon = self.membership.get_diskon_for_pasien(pasien.id_pasien)
        nominal_diskon_t = (subtotal_tindakan * diskon.persen_treatment / Decimal("100")).quantize(Decimal("0.01"))
        nominal_diskon_p = (subtotal_produk * diskon.persen_produk / Decimal("100")).quantize(Decimal("0.01"))
        # Racikan memakai PERSEN produk, dikenakan ke SELURUH total racikan —
        # bahan DAN ongkos racik (keputusan dr. Hansen 2026-09-21).
        # Dijumlah PER BARIS (bukan dari agregat) supaya angka di ringkasan selalu
        # sama persis dengan jumlah diskon_item yang disimpan di transaksi_detail_racikan.
        nominal_diskon_r = sum(
            (_r.total * diskon.persen_produk / Decimal("100")).quantize(Decimal("0.01"))
            for _r in rincian_racikan
        ) or Decimal("0")
        nominal_diskon_total = nominal_diskon_t + nominal_diskon_p + nominal_diskon_r

        # M2: aktivasi membership TIDAK lagi ikut tagihan klinis. Membership kini
        # transaksi berdiri sendiri (jenis=MEMBERSHIP, id_kunjungan=NULL) dibayar
        # via /kasir/membership/{id_history}/bayar. Field di RingkasanBiaya
        # dipertahankan (kompat) tapi selalu 0/None di tagihan klinis.
        subtotal_aktivasi = Decimal("0")
        nama_tier_pending = None
        id_mship_pending = None
        id_hist_pending = None

        subtotal = subtotal_tindakan + subtotal_produk + subtotal_racikan
        total = subtotal - nominal_diskon_total

        # Tagihan tambahan: id_transaksi_existing dipopulate utk UI tahu ini reopen
        msg = ""
        if existing is not None:
            msg = (
                f"Tagihan tambahan untuk kunjungan ini "
                f"(sebelumnya sudah ada transaksi #{existing.id_transaksi})."
            )

        return TagihanResponse(
            id_kunjungan=id_kunjungan,
            nama_pasien=pasien.nama,
            no_rm=pasien.no_rm,
            tipe_membership=tipe,
            sudah_lunas=False,
            id_transaksi_existing=existing.id_transaksi if existing else None,
            message=msg,
            rincian_tindakan=rincian_tindakan,
            rincian_produk=rincian_produk,
            rincian_racikan=rincian_racikan,
            ringkasan_biaya=RingkasanBiaya(
                subtotal_tindakan=subtotal_tindakan,
                subtotal_produk=subtotal_produk,
                subtotal_racikan=subtotal_racikan,
                subtotal_aktivasi_membership=subtotal_aktivasi,
                nama_tier_aktivasi=nama_tier_pending,
                id_membership_aktivasi_pending=id_mship_pending,
                id_history_pending=id_hist_pending,
                subtotal=subtotal,
                persen_diskon_treatment=diskon.persen_treatment,
                persen_diskon_produk=diskon.persen_produk,
                nominal_diskon_treatment=nominal_diskon_t,
                nominal_diskon_produk=nominal_diskon_p,
                nominal_diskon_racikan=nominal_diskon_r,
                nominal_diskon_total=nominal_diskon_total,
                total_tagihan=total,
            ),
        )

    # =========================================================================
    # BAYAR — atomic
    # =========================================================================
    def _create_kuota_from_benefit(
        self, id_pasien, id_history, id_membership, expired_at,
        action_type=None,  # ACTIVATION | RENEWAL | UPGRADE | None (treat as ACTIVATION)
    ):
        """#362D + #362B-C - Auto-create / extend pasien_membership_kuota.

        TOTAL_PAKET: eager create 1 row per benefit. RENEWAL = extend existing
        kuota_total + expired_at (carry-over). UPGRADE = create new row.
        BULANAN: skip (lazy create saat treatment dispense - Phase 2).

        Kalau tidak ada benefit configured, skip silently.
        """
        if not id_pasien or not id_history or not id_membership:
            return
        from datetime import date as _date
        from app.db.models import (
            MasterMembershipBenefitTreatment as _MMBT,
            PasienMembershipKuota as _PMK,
            PasienMembershipHistory as _PMH3,
        )
        from sqlalchemy import select as _sel2

        benefits = self.db.execute(
            _sel2(_MMBT)
            .where(_MMBT.id_membership == id_membership)
            .where(_MMBT.is_active.is_(True))
        ).scalars().all()
        if not benefits:
            return

        is_renewal = (action_type or "").upper() == "RENEWAL"

        for b in benefits:
            periode_val = b.periode_kuota.value if hasattr(b.periode_kuota, "value") else str(b.periode_kuota)

            # BULANAN: lazy create — skip di sini. Akan auto-create saat treatment dispense.
            if periode_val == "BULANAN":
                continue

            # TOTAL_PAKET: cek existing kuota di history sebelumnya kalau RENEWAL
            if is_renewal:
                # Cari kuota row aktif untuk same treatment dari history pasien sebelumnya
                existing_kuota = self.db.execute(
                    _sel2(_PMK)
                    .join(_PMH3, _PMH3.id_history == _PMK.id_membership_history)
                    .where(_PMK.id_pasien == id_pasien)
                    .where(_PMK.id_treatment == b.id_treatment)
                    .where(_PMK.periode_kuota == b.periode_kuota)
                    .where(_PMK.is_active.is_(True))
                    .where(_PMH3.id_membership == id_membership)
                    .order_by(_PMK.id_kuota.desc())
                    .limit(1)
                ).scalar_one_or_none()

                if existing_kuota is not None:
                    # CARRY-OVER: tambah kuota_total + extend expired_at
                    existing_kuota.kuota_total += int(b.kuota_total or 0)
                    existing_kuota.expired_at = expired_at
                    # Update id_membership_history ke yang terbaru
                    existing_kuota.id_membership_history = id_history
                    continue

            # ACTIVATION / UPGRADE / RENEWAL tanpa existing: create new row
            kuota = _PMK(
                id_pasien=id_pasien,
                id_membership_history=id_history,
                id_treatment=b.id_treatment,
                periode_kuota=b.periode_kuota,
                bulan_periode=None,  # TOTAL_PAKET = NULL
                kuota_total=int(b.kuota_total or 0),
                kuota_terpakai=0,
                is_active=True,
                expired_at=expired_at,
            )
            self.db.add(kuota)
        self.db.flush()

    # Satu pesan untuk "tagihan berubah sejak dihitung/ditampilkan": sidik basi (T1-6) dan
    # tindakan yang tak lagi bisa ditagih saat ditautkan (T2-1 fix round 1).
    _PESAN_TAGIHAN_BERUBAH = ("Tagihan berubah sejak halaman dibuka — ada item baru dari "
                              "dokter/perawat. Halaman dimuat ulang; periksa lalu bayar lagi.")

    @staticmethod
    def sidik_tagihan(tagihan: TagihanResponse) -> str:
        """Sidik himpunan item yang DITAGIH di `tagihan` (Bayar dulu T1-6).

        Contoh: "T:12,T:15|R:40|C:7" — T tindakan, R resep (produk), C racikan; id urut naik
        per jenis; jenis yang kosong dilewati. Halaman tagihan membawanya di form, dan
        `proses_bayar` membandingkannya dengan himpunan SEGAR: kalau dokter/perawat menambah
        item sesudah halaman dibuka, Bayar ditahan. Tanpa ini kasir menagih himpunan yang
        tidak sama dengan yang ia lihat, dan total yang ditagih lebih besar dari yang ia
        sebutkan ke pasien. Perhatian: hanya id item yang masuk, BUKAN harga/diskon —
        perubahan harga bukan "item baru" dan sudah ditangani pagar nominal. Harus
        deterministik (urut), karena dibandingkan sebagai string.
        """
        bagian = []
        for awalan, ids in (
            ("T", [t.id_kunjungan_tindakan for t in tagihan.rincian_tindakan]),
            ("R", [p.id_resep for p in tagihan.rincian_produk]),
            ("C", [r.id_kunjungan_racikan for r in tagihan.rincian_racikan]),
        ):
            if ids:
                bagian.append(",".join(f"{awalan}:{i}" for i in sorted(ids)))
        return "|".join(bagian)

    def proses_bayar(
        self,
        payload: BayarRequest,
        id_staf_kasir: int,
        request: Optional[Request] = None,
    ) -> dict:
        # P0-2 (AUDIT_SEHATI_2026-07-10): kunci baris kunjungan → serialisasi submit
        # pembayaran konkuren utk kunjungan sama. Submit kedua baru lanjut setelah yang
        # pertama commit.
        #
        # Audit T4-1 (2026-10-15): kunci SAJA tidak cukup. MySQL REPEATABLE-READ: SELECT
        # biasa membaca POTRET yang dibuat pada pembacaan PERTAMA transaksi — di route itu
        # `get_user_from_cookie`, jauh sebelum kunci ini. Submit kedua (Kasir + Admin, kunci
        # idempotensi beda) menunggu kunci, lalu `get_tagihan` di bawah tetap melihat "belum
        # ada transaksi" → tagihan KEDUA penuh + komisi ganda, dan status jadi COMPLETED
        # (obat lunas hilang dari antrian apotek). Terbukti dengan dua koneksi di DB dev.
        # Maka transaksi baca ditutup DULU: potret baru dibuat oleh SELECT biasa pertama
        # SESUDAH kunci didapat (FOR UPDATE bukan pembacaan konsisten, tidak membuat potret).
        # ⚠ Jangan sisipkan SELECT biasa di antara commit ini dan kunci di bawahnya.
        # `expire_all`: sesi memakai expire_on_commit=False — objek yang sudah dimuat (mis.
        # route memanggil get_tagihan lebih dulu) harus dibaca ulang dari potret baru.
        mulai_baca_segar(self.db)   # lihat app/services/_baca_segar.py
        _kj_kunci = self.kunjungan_repo.get_by_id_for_update(payload.id_kunjungan)

        # Audit T2-3: kunjungan BATAL dulu tetap bisa dibayar (halaman tagihan yang
        # terbuka sebelum FO membatalkan) dan "hidup lagi" jadi ANTRI_OBAT/COMPLETED.
        # Diperiksa SESUDAH kunci, jadi pembatalan yang menang lebih dulu terlihat.
        if _kj_kunci is not None and _kj_kunci.status_antrian == "BATAL":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(f"Kunjungan {payload.id_kunjungan} sudah DIBATALKAN — tidak bisa "
                        f"dibayar. Kalau pasien tetap dilayani, daftarkan antrian baru."),
            )

        # 1. Re-fetch tagihan (server source of truth)
        tagihan = self.get_tagihan(payload.id_kunjungan)
        if tagihan.sudah_lunas:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Kunjungan {payload.id_kunjungan} sudah dibayar "
                    f"(transaksi #{tagihan.id_transaksi_existing})."
                ),
            )

        # Bayar dulu T1-6: halaman tagihan basi. Dibandingkan pada data SEGAR (sesudah
        # mulai_baca_segar + kunci, T4-1) dan SEBELUM tulisan apa pun. sidik None = klien API.
        if payload.sidik is not None and payload.sidik != self.sidik_tagihan(tagihan):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=self._PESAN_TAGIHAN_BERUBAH,
            )

        # Bayar dulu T2-2: tindakan yang belum dikerjakan ikut ditagih (dibayar di muka). Server
        # menolak tanpa konfirmasi -- centang di halaman saja bisa dilewati klien lain. Diletakkan
        # sesudah sidik (data segar, terkunci) dan sebelum tulisan apa pun.
        if (any(t.status_tindakan != "SELESAI" for t in tagihan.rincian_tindakan)
                and not payload.konfirmasi_prabayar):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=("Ada tindakan yang belum dikerjakan di tagihan ini. Centang konfirmasi "
                        "'dibayar di muka' untuk melanjutkan."),
            )

        total_tagihan = tagihan.ringkasan_biaya.total_tagihan
        total_bayar = sum((p.nominal for p in payload.pembayaran), Decimal("0"))

        # DEC-049: Conditional bypass nominal Rp 0
        # - Kalau total_tagihan == 0 → kunjungan ini full series sesi 2..N (lunas
        #   di sesi 1), atau full pakai kuota member. Boleh tanpa pembayaran.
        # - Kalau total_tagihan > 0 → wajib ada pembayaran ≥ total.
        if total_tagihan > 0 and total_bayar < total_tagihan:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Nominal pembayaran kurang dari total tagihan. "
                    f"Tagihan: {total_tagihan}, dibayar: {total_bayar}."
                ),
            )
        if total_tagihan == 0 and total_bayar > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Total tagihan Rp 0 (series lunas) — tidak boleh masukkan "
                    f"nominal pembayaran. Kosongkan form lalu klik Selesaikan."
                ),
            )
        kembalian = max(Decimal("0"), total_bayar - total_tagihan)

        kunjungan = self.kunjungan_repo.get_by_id(payload.id_kunjungan)

        try:
            # 2. INSERT transaksi_kasir (KLINIS — tanpa membership; M2 memisah membership)
            trx = TransaksiKasir(
                id_kunjungan=payload.id_kunjungan,
                id_pasien=(kunjungan.id_pasien if kunjungan else None),
                id_staf_kasir=id_staf_kasir,
                jenis_transaksi="KLINIS",
                rincian_tagihan=(
                    f"Tindakan: {tagihan.ringkasan_biaya.subtotal_tindakan}, "
                    f"Produk: {tagihan.ringkasan_biaya.subtotal_produk}, "
                    f"Racikan: {tagihan.ringkasan_biaya.subtotal_racikan}, "
                    f"Diskon: {tagihan.ringkasan_biaya.nominal_diskon_total}"
                ),
                subtotal=tagihan.ringkasan_biaya.subtotal,
                nominal_diskon=tagihan.ringkasan_biaya.nominal_diskon_total,
                keterangan_promo=payload.keterangan_promo or None,
                total_tagihan=total_tagihan,
                idempotency_key=payload.idempotency_key or None,  # P0-2 backstop
            )
            self.repo.create_transaksi(trx)
            id_trx_baru = trx.id_transaksi

            # Persen diskon produk (member) — dipakai untuk produk DAN racikan.
            _persen_racik = Decimal(str(tagihan.ringkasan_biaya.persen_diskon_produk or 0))

            # 3. INSERT detail produk (snapshot dari rincian_produk yang non-BATAL)
            # Task #54-F: `diskon_item` akhirnya DIISI. Kolomnya sudah ada sejak
            # M-FIN-1 tapi selalu 0, sehingga nilai BERSIH per baris produk tidak
            # pernah tersimpan. Akibatnya dua hal: Finance tak punya data margin per
            # lini, dan refund per item tidak tahu berapa yang benar-benar dibayar
            # pasien — kalau dikembalikan `subtotal` mentah, pasien member menerima
            # lebih banyak dari yang ia bayar. Racikan sudah benar sejak Fase 3.
            for produk_item in tagihan.rincian_produk:
                _diskon_p = (
                    Decimal(str(produk_item.subtotal)) * _persen_racik / Decimal("100")
                ).quantize(Decimal("0.01"))
                self.repo.add_detail_produk(TransaksiDetailProduk(
                    id_transaksi=id_trx_baru,
                    id_produk=produk_item.id_produk,
                    qty=produk_item.qty,
                    harga_satuan=produk_item.harga_satuan,
                    subtotal=produk_item.subtotal,
                    diskon_item=_diskon_p,
                ))

            # 3b. INSERT detail racikan (tabel SENDIRI — transaksi_detail_produk
            # tidak muat karena id_produk-nya NOT NULL sedangkan racikan banyak bahan).
            for racik_item in tagihan.rincian_racikan:
                _diskon_row = (
                    Decimal(str(racik_item.total)) * _persen_racik / Decimal("100")
                ).quantize(Decimal("0.01"))
                self.db.add(TransaksiDetailRacikan(
                    id_transaksi=id_trx_baru,
                    id_kunjungan_racikan=racik_item.id_kunjungan_racikan,
                    nama_snapshot=racik_item.nama,
                    jenis_racik=racik_item.jenis_racik,
                    jumlah_unit=racik_item.jumlah_unit,
                    subtotal_bahan=racik_item.subtotal_bahan,
                    biaya_racik=racik_item.biaya_racik,
                    diskon_item=_diskon_row,
                    subtotal=Decimal(str(racik_item.total)) - _diskon_row,
                ))
            if tagihan.rincian_racikan:
                self.db.flush()

            # 3c. INSERT detail TINDAKAN (F3 — backlog "Snapshot line-item Finance")
            #
            # KENAPA BARU SEKARANG: tabel `transaksi_detail_tindakan` sudah ada sejak
            # M-FIN-2 tapi TIDAK PERNAH SEKALI PUN DITULIS. Produk (3) dan racikan (3b)
            # punya baris rinciannya; tindakan tidak. Akibatnya modul Finance tidak
            # punya dasar margin/COGS untuk lini yang justru paling besar di klinik ini,
            # dan datanya TIDAK BISA DIAMBIL KEMBALI — transaksi yang sudah lewat tidak
            # meninggalkan jejak apa pun untuk direkonstruksi.
            #
            # ⚠ PEMBULATAN — ini bagian yang mudah salah.
            # `nominal_diskon_treatment` di header dihitung dari AGREGAT
            # (subtotal_tindakan x persen), sedangkan diskon per baris harus dibulatkan
            # sendiri-sendiri. Jumlah pembulatan per baris bisa meleset beberapa sen dari
            # angka header — dan Finance yang merekonsiliasi baris terhadap header akan
            # melihat selisih yang tidak bisa dijelaskan.
            #
            # Racikan menyelesaikannya dengan mengubah header jadi jumlah per-baris.
            # Di sini TIDAK: mengubah header berarti mengubah angka yang DIBAYAR PASIEN.
            # Sebagai gantinya selisih pembulatan dititipkan ke baris TERAKHIR, sehingga
            # SUM(diskon_item) == nominal_diskon_treatment PERSIS, tanpa menyentuh
            # total tagihan sama sekali.
            #
            # Baris berkuota member (harga 0) TETAP DITULIS: tindakannya benar-benar
            # dikerjakan dan BHP-nya benar-benar terpakai. Justru baris itulah yang
            # paling penting untuk margin — biaya tanpa pendapatan.
            if tagihan.rincian_tindakan:
                _persen_t = Decimal(str(
                    tagihan.ringkasan_biaya.persen_diskon_treatment or 0))
                _target_t = Decimal(str(
                    tagihan.ringkasan_biaya.nominal_diskon_treatment or 0))

                # BHP per tindakan dari master (snapshot saat bayar, bukan referensi).
                _bhp: dict[int, Decimal] = {}
                _id_tr = {r.id_treatment for r in tagihan.rincian_tindakan}
                if _id_tr:
                    for _mt in self.db.query(MasterTreatment).filter(
                            MasterTreatment.id_treatment.in_(_id_tr)).all():
                        _bhp[int(_mt.id_treatment)] = Decimal(
                            str(_mt.bhp_per_pakai_nominal or 0))

                _diskon_baris = [
                    (Decimal(str(t.harga)) * _persen_t / Decimal("100")
                     ).quantize(Decimal("0.01"))
                    for t in tagihan.rincian_tindakan
                ]
                _selisih = _target_t - sum(_diskon_baris)
                if _diskon_baris:
                    _diskon_baris[-1] += _selisih   # titipkan sisa pembulatan

                for _t, _dis in zip(tagihan.rincian_tindakan, _diskon_baris):
                    _harga = Decimal(str(_t.harga))
                    self.db.add(TransaksiDetailTindakan(
                        id_transaksi=id_trx_baru,
                        id_kunjungan_tindakan=_t.id_kunjungan_tindakan,
                        id_treatment=_t.id_treatment,
                        qty=1,                      # tindakan selalu 1x per baris
                        harga_satuan=_harga,
                        diskon_item=_dis,
                        subtotal=_harga - _dis,
                        bhp_satuan=_bhp.get(_t.id_treatment, Decimal("0")),
                    ))
                self.db.flush()

            # 4. INSERT pembayaran (split payment)
            for bayar in payload.pembayaran:
                self.repo.add_pembayaran(TransaksiPembayaran(
                    id_transaksi=id_trx_baru,
                    metode_bayar=bayar.metode_bayar,
                    nominal=bayar.nominal,
                ))

            # 5. Mark resep + racikan DIBAYAR
            # Audit T4-1: hanya baris yang DITAGIH di transaksi ini. Dulu "semua PENDING saat
            # UPDATE": resep/racikan yang disimpan dokter/perawat SELAMA pembayaran (SOAP &
            # upsell tidak mengunci kunjungan) ikut lunas tanpa ditagih. Baris yang tertinggal
            # tetap PENDING dan muncul di tagihan susulan (lihat get_tagihan).
            n_resep_updated = self.repo.mark_resep_dibayar(
                payload.id_kunjungan, id_trx_baru,
                ids=[r.id_resep for r in tagihan.rincian_produk])
            n_racikan_updated = self.repo.mark_racikan_dibayar(
                payload.id_kunjungan, id_trx_baru,
                ids=[r.id_kunjungan_racikan for r in tagihan.rincian_racikan])
            # Bayar dulu T1-2: tindakan yang ditagih ikut ditandai (hanya yang di tagihan ini;
            # susulan yang selesai selama pembayaran tetap NULL dan muncul di tagihan berikutnya).
            _ids_tindakan = [t.id_kunjungan_tindakan for t in tagihan.rincian_tindakan]
            n_tindakan_ditaut = self.repo.mark_tindakan_dibayar(
                payload.id_kunjungan, id_trx_baru, ids=_ids_tindakan)
            # Bayar dulu T2-1 (fix round 1, Ruling P3a): pagar cadangan. Tindakan yang
            # ditagih tapi tak tertaut = berubah sejak tagihan dihitung (mis. dibatalkan
            # perawat; Batalkan kini mengunci kunjungan dulu, jadi ini seharusnya tak
            # terjadi). Tanpa pagar ini pasien membayar tindakan BATAL yang kuotanya sudah
            # dikembalikan. Rollback: transaksi & pembayaran di atas belum di-commit.
            if n_tindakan_ditaut != len(_ids_tindakan):
                self.db.rollback()
                raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                    detail=self._PESAN_TAGIHAN_BERUBAH)

            # 6. Status kunjungan dari isinya (bayar dulu T1-4, menutup Audit T4-4).
            # Dulu: obat ditandai di transaksi ini → ANTRI_OBAT, selain itu COMPLETED —
            # TANPA melihat tindakan PENDING/PROSES, sehingga bayar-dulu saat tindakan
            # belum dikerjakan menutup kunjungan dan tindakannya hilang dari layar perawat.
            # Riwayat yang kini tercakup fungsi bersama, JANGAN ditulis ulang di sini:
            #  - racikan ikut dihitung (kunjungan racikan-saja dulu loncat ke COMPLETED dan
            #    stok bahannya tak pernah keluar) → (O) membaca resep DAN racikan DIBAYAR;
            #  - Audit T2-1: obat LAMA lunas belum diserahkan pada tagihan susulan → (O);
            #  - jalur Obat Tertunda (tgl_janji_kirim terisi) SENGAJA COMPLETED → (O)
            #    mengecualikannya.
            status_lama = kunjungan.status_antrian if kunjungan else None
            status_baru = status_lama
            if kunjungan:
                self.db.flush()
                from app.services._status_kunjungan import hitung_ulang_status
                status_baru = hitung_ulang_status(self.db, payload.id_kunjungan)

            # 7. AUDIT
            self.audit.log_create(
                id_staf=id_staf_kasir,
                tabel="transaksi_kasir",
                id_target=id_trx_baru,
                data_baru={
                    "id_kunjungan": payload.id_kunjungan,
                    "total_tagihan": float(total_tagihan),
                    "subtotal": float(tagihan.ringkasan_biaya.subtotal),
                    "nominal_diskon": float(tagihan.ringkasan_biaya.nominal_diskon_total),
                    "jumlah_metode_bayar": len(payload.pembayaran),
                    "kembalian": float(kembalian),
                },
                request=request,
            )
            if status_baru != status_lama:
                self.audit.log(
                    aksi="STATUS_UPDATE",
                    id_staf=id_staf_kasir,
                    tabel_target="kunjungan",
                    id_target=payload.id_kunjungan,
                    data_lama={"status_antrian": status_lama},
                    data_baru={"status_antrian": status_baru},
                    keterangan=(f"Auto-transition setelah pembayaran. Resep di-DIBAYAR: "
                                f"{n_resep_updated}, racikan: {n_racikan_updated}"),
                    request=request,
                )

            # K-L2 (DEC-087): catat komisi (snapshot) — ikut transaksi atomik.
            # Bayar dulu T2-3: bagian tindakan hanya yang ditautkan `mark_tindakan_dibayar` di
            # atas DAN sudah SELESAI; tindakan yang dibayar di muka berkomisi saat
            # `end_tindakan`. Jadi langkah ini HARUS tetap sesudah penautan.
            #
            # RESEP_LUAR dilewati SECARA EKSPLISIT. Peresepnya dokter di luar klinik, jadi
            # tidak ada dasar komisi. Sekarang hasilnya kebetulan sudah nol karena
            # `komisi_service` membutuhkan dokter internal — tapi kebetulan itu rapuh:
            # task #52 baru saja menambahkan fallback ke penulis SOAP pertama, dan satu
            # fallback baru lagi bisa membuat komisi mengalir ke dokter yang tidak
            # meresepkan apa pun. Aturannya dinyatakan, bukan disimpulkan.
            _jenis_kunj = getattr(kunjungan, "jenis_kunjungan", "KLINIS") if kunjungan else "KLINIS"
            if _jenis_kunj == "RESEP_LUAR":
                self.audit.log(
                    aksi="KOMISI_DILEWATI",
                    id_staf=id_staf_kasir,
                    tabel_target="transaksi_kasir",
                    id_target=id_trx_baru,
                    keterangan=(
                        "Komisi tidak dicatat: resep dari dokter LUAR klinik "
                        f"({getattr(kunjungan, 'peresep_luar_nama', None) or '-'})."
                    ),
                    request=request,
                )
            else:
                KomisiService(self.db).catat_komisi_transaksi(
                    id_transaksi=id_trx_baru,
                    id_kunjungan=payload.id_kunjungan,
                    id_pasien=kunjungan.id_pasien if kunjungan else None,
                    id_dokter_assigned=kunjungan.id_staf_dokter_assigned if kunjungan else None,
                    rincian_produk=tagihan.rincian_produk,
                    rincian_racikan=tagihan.rincian_racikan,
                    request=request,
                )

            self.db.commit()
            return {
                "status": "success",
                "message": "Pembayaran berhasil. Silakan cetak struk.",
                "data": {
                    "id_transaksi": id_trx_baru,
                    "total_tagihan": float(total_tagihan),
                    "total_bayar": float(total_bayar),
                    "kembalian": float(kembalian),
                    "resep_di_dibayar": n_resep_updated,
                    "status_kunjungan_baru": status_baru,
                },
            }
        except HTTPException:
            raise
        except IntegrityError:
            # P0-2: idempotency_key duplikat → submit pembayaran yang SAMA diproses
            # dua kali (double-click/retry/race). Batalkan submit kedua dgn aman
            # (tanpa transaksi/komisi ganda) dan beri pesan ramah, bukan 500.
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Pembayaran ini sudah diproses (submit ganda terdeteksi). "
                    "Muat ulang halaman untuk melihat status terbaru."
                ),
            )
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gagal proses pembayaran: {str(e)}",
            )

    # =========================================================================
    # R8 — "SISAKAN UNTUK NANTI" (DITUNDA). Tanpa PIN: tindakannya tidak merusak.
    # =========================================================================
    def _sisa_item_ditagih(self, id_kunjungan: int, *,
                           kecuali_resep: Optional[int] = None,
                           kecuali_racikan: Optional[int] = None) -> int:
        """Berapa item yang MASIH akan ditagih kalau satu item lagi ditunda.

        Dipakai untuk pagar "tidak boleh menunda SEMUANYA": kunjungan tanpa satu pun item
        berbayar akan melahirkan transaksi Rp 0 yang mengotori laporan. Kalau pasien batal
        membeli seluruhnya, jalurnya void kunjungan — bukan menunda satu per satu.
        Tindakan ikut dihitung: pasien yang sudah dirawat tetap punya tagihan.
        """
        from app.db.models import KunjunganResep as _KR
        from app.db.models.racikan import KunjunganRacikan as _KRC
        from sqlalchemy import select as _sel, func as _f

        q_resep = (_sel(_f.count(_KR.id_resep))
                   .where(_KR.id_kunjungan == id_kunjungan,
                          _KR.status_item == "PENDING"))
        if kecuali_resep is not None:
            q_resep = q_resep.where(_KR.id_resep != kecuali_resep)
        n = int(self.db.execute(q_resep).scalar() or 0)

        q_rac = (_sel(_f.count(_KRC.id_kunjungan_racikan))
                 .where(_KRC.id_kunjungan == id_kunjungan,
                        _KRC.status_item == "PENDING"))
        if kecuali_racikan is not None:
            q_rac = q_rac.where(_KRC.id_kunjungan_racikan != kecuali_racikan)
        n += int(self.db.execute(q_rac).scalar() or 0)

        # T2-1: tindakan yang BISA DITAGIH (satu definisi: bukan BATAL, belum punya
        # transaksi) — termasuk yang belum dikerjakan. Dulu semua SELESAI, termasuk yang
        # sudah lunas: tindakan lunas bukan isi tagihan INI, jadi menunda item terakhir di
        # tagihan susulan lolos dan melahirkan transaksi Rp 0.
        n += len(self.repo.get_tindakan_untuk_tagihan(id_kunjungan, hanya_bisa_ditagih=True))
        return n

    _PESAN_SEMUA_DITUNDA = (
        "Tidak bisa menunda item terakhir — tagihan akan jadi kosong. "
        "Kalau pasien batal membeli seluruhnya, batalkan kunjungannya (void), "
        "jangan menunda satu per satu."
    )

    def tunda_item_resep(self, id_resep: int, id_staf_kasir: int,
                         qty_tunda: Optional[float] = None,
                         request: Optional[Request] = None) -> dict:
        """"Sisakan untuk nanti" — seluruh baris ATAU sebagian jumlahnya.

        `qty_tunda=None` atau >= qty → SELURUH baris jadi DITUNDA.
        `0 < qty_tunda < qty`        → baris DIPECAH: baris asli turun jumlahnya dan tetap
                                       PENDING (ditagih hari ini), lahir baris BARU berisi
                                       sisanya dengan status DITUNDA.

        Kasus nyata yang memaksa pemecahan ini (dr. Hansen, 2026-09-27): "Cefixime 200mg
        no. XV, ditebus 10 dulu". Menebus sebagian JUMLAH jauh lebih sering daripada
        menebus sebagian DAFTAR.

        ⚠ JEBAKAN YANG SENGAJA DIHINDARI: baris pecahan TIDAK memakai `id_resep_asal`.
        Kolom itu punya arti lain — "baris ini SALINAN yang dibuat saat penebusan" — dan
        dipakai sebagai penanda anti-tebus-ganda. Kalau dipakai juga untuk pemecahan:
          (a) `list_resep_belum_ditebus` menyaring `id_resep_asal IS NULL`, jadi pecahan
              DITUNDA tidak akan pernah muncul untuk ditebus; dan
          (b) baris asal akan dianggap "sudah ditebus" padahal belum.
        Inilah pola "satu kolom dua arti" yang sudah berkali-kali menggigit proyek ini.
        Pecahan adalah SAUDARA, bukan salinan: `id_resep_asal` tetap NULL, dan jejak
        pemecahannya hidup di audit_log.
        """
        # Enum ini TIDAK diimpor di tingkat modul — berkas ini mengimpornya lokal di tiap
        # metode yang butuh. Ikuti polanya, jangan andalkan ingatan.
        from app.db.models import KunjunganResep as _KR, StatusItemResepEnum

        resep = self.repo.get_resep_by_id(id_resep)
        if resep is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                f"Resep {id_resep} tidak ditemukan.")
        _st = (resep.status_item.value if hasattr(resep.status_item, "value")
               else str(resep.status_item or ""))
        if _st != "PENDING":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Resep #{id_resep} berstatus '{_st}' — hanya item PENDING yang bisa "
                f"ditunda. Item yang sudah dibayar tidak bisa ditarik kembali di sini.",
            )

        _qty_total = float(resep.qty or 0)
        _pecah = qty_tunda is not None and 0 < float(qty_tunda) < _qty_total
        if qty_tunda is not None and float(qty_tunda) <= 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Jumlah yang disisakan harus lebih dari 0.")

        # Pagar "jangan kosongkan tagihan" HANYA berlaku untuk penundaan seluruh baris.
        # Pemecahan selalu menyisakan bagian yang ditagih, jadi tidak mungkin mengosongkan.
        if not _pecah and self._sisa_item_ditagih(
                resep.id_kunjungan, kecuali_resep=id_resep) < 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, self._PESAN_SEMUA_DITUNDA)

        try:
            if _pecah:
                _sisa = round(_qty_total - float(qty_tunda), 3)
                _dibayar = round(float(qty_tunda), 3)
                # Baris asli: yang DIBAYAR hari ini. Perhatikan qty_tunda adalah jumlah
                # yang DISISAKAN, jadi baris asli menerima selisihnya.
                resep.qty = _sisa
                pecahan = _KR(
                    id_kunjungan=resep.id_kunjungan,
                    id_produk=resep.id_produk,
                    qty=_dibayar,
                    aturan_pakai=resep.aturan_pakai,
                    status_item=StatusItemResepEnum.DITUNDA,
                    # Kolom NOT NULL. Peresep aslinya yang dipertahankan — pecahan ini
                    # tetap obat yang DIA resepkan, kasir cuma memecah penebusannya.
                    id_staf_input=(getattr(resep, "id_staf_input", None) or id_staf_kasir),
                )
                self.db.add(pecahan)
                self.db.flush()
                self.audit.log(
                    id_staf=id_staf_kasir, aksi="TUNDA_ITEM",
                    tabel_target="kunjungan_resep", id_target=id_resep,
                    data_lama={"qty": _qty_total, "status_item": "PENDING"},
                    data_baru={"qty": _sisa, "status_item": "PENDING",
                               "pecahan_ditunda": {"id_resep": pecahan.id_resep,
                                                   "qty": _dibayar}},
                    keterangan=(f"Resep #{id_resep} DIPECAH oleh kasir_id={id_staf_kasir}: "
                                f"{_sisa} ditagih hari ini, {_dibayar} disisakan sebagai "
                                f"resep #{pecahan.id_resep} (DITUNDA)."),
                    request=request,
                )
                self.db.commit()
                return {"status": "success", "id_resep": id_resep,
                        "qty_ditagih": _sisa, "qty_ditunda": _dibayar,
                        "id_resep_ditunda": pecahan.id_resep}

            resep.status_item = StatusItemResepEnum.DITUNDA
            self.audit.log(
                id_staf=id_staf_kasir, aksi="TUNDA_ITEM", tabel_target="kunjungan_resep",
                id_target=id_resep,
                data_lama={"status_item": "PENDING"},
                data_baru={"status_item": "DITUNDA"},
                keterangan=(f"Item resep #{id_resep} ({_qty_total}) disisakan SELURUHNYA "
                            f"untuk nanti oleh kasir_id={id_staf_kasir}."),
                request=request,
            )
            self.db.commit()
            return {"status": "success", "id_resep": id_resep,
                    "status_item_baru": "DITUNDA", "qty_ditunda": _qty_total}
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            self.db.rollback()
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                                f"Gagal menunda item: {e!s}")

    def tunda_racikan(self, id_kunjungan_racikan: int, id_staf_kasir: int,
                      unit_tunda: Optional[int] = None,
                      request: Optional[Request] = None) -> dict:
        """"Sisakan untuk nanti" untuk racikan — seluruhnya ATAU sebagian jumlah unit.

        `unit_tunda` kosong / >= jumlah_unit → seluruh racikan jadi DITUNDA.
        `0 < unit_tunda < jumlah_unit`       → dipecah jadi dua batch (lihat
                                               `RacikanService.pecah_racikan`).
        Pemecahan menambah ongkos racik satu kali lagi — itu disengaja dan disetujui
        dr. Hansen: dua batch = dua pekerjaan meracik.
        """
        from app.db.models.racikan import KunjunganRacikan as _KRC
        from app.services.racikan_service import RacikanService

        rc = self.db.get(_KRC, id_kunjungan_racikan)
        if rc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                f"Racikan {id_kunjungan_racikan} tidak ditemukan.")
        if rc.status_item != "PENDING":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Racikan #{id_kunjungan_racikan} berstatus '{rc.status_item}' — hanya "
                f"PENDING yang bisa ditunda.",
            )

        _total_unit = int(rc.jumlah_unit or 0)
        _pecah = unit_tunda is not None and 0 < int(unit_tunda) < _total_unit
        if _pecah:
            # Pemecahan selalu menyisakan bagian yang ditagih → pagar tidak berlaku.
            try:
                hasil = RacikanService(self.db).pecah_racikan(
                    id_kunjungan_racikan, int(unit_tunda))
                self.audit.log(
                    id_staf=id_staf_kasir, aksi="TUNDA_ITEM",
                    tabel_target="kunjungan_racikan", id_target=id_kunjungan_racikan,
                    data_lama={"jumlah_unit": _total_unit, "status_item": "PENDING"},
                    data_baru={"jumlah_unit": hasil["unit_ditagih"],
                               "pecahan_ditunda": {
                                   "id": hasil["id_pecahan"],
                                   "unit": hasil["unit_ditunda"]}},
                    keterangan=(
                        f"Racikan #{id_kunjungan_racikan} ({rc.nama_snapshot!r}) DIPECAH "
                        f"oleh kasir_id={id_staf_kasir}: {hasil['unit_ditagih']} unit "
                        f"ditagih, {hasil['unit_ditunda']} unit disisakan sebagai racikan "
                        f"#{hasil['id_pecahan']}. Ongkos racik dikenakan DUA kali "
                        f"(tambahan Rp {hasil['biaya_racik_ekstra']}) karena ini dua "
                        f"pekerjaan meracik."),
                    request=request,
                )
                self.db.commit()
                return {"status": "success", **hasil}
            except HTTPException:
                self.db.rollback()
                raise
            except Exception as e:  # noqa: BLE001
                self.db.rollback()
                raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    f"Gagal memecah racikan: {e!s}")

        if unit_tunda is not None and int(unit_tunda) <= 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Jumlah yang disisakan harus lebih dari 0.")
        if self._sisa_item_ditagih(rc.id_kunjungan,
                                   kecuali_racikan=id_kunjungan_racikan) < 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, self._PESAN_SEMUA_DITUNDA)

        try:
            rc.status_item = "DITUNDA"
            self.audit.log(
                id_staf=id_staf_kasir, aksi="TUNDA_ITEM", tabel_target="kunjungan_racikan",
                id_target=id_kunjungan_racikan,
                data_lama={"status_item": "PENDING"},
                data_baru={"status_item": "DITUNDA"},
                keterangan=(f"Racikan #{id_kunjungan_racikan} ({rc.nama_snapshot!r}) "
                            f"disisakan untuk nanti oleh kasir_id={id_staf_kasir}. "
                            f"Harga akan DIHITUNG ULANG saat ditebus."),
                request=request,
            )
            self.db.commit()
            return {"status": "success", "id_kunjungan_racikan": id_kunjungan_racikan,
                    "status_item_baru": "DITUNDA"}
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            self.db.rollback()
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                                f"Gagal menunda racikan: {e!s}")

    # =========================================================================
    # VOID ITEM — PIN dokter/admin
    # =========================================================================
    def void_item_resep(
        self,
        payload: VoidItemRequest,
        id_staf_kasir: int,
        request: Optional[Request] = None,
    ) -> dict:
        resep = self.repo.get_resep_by_id(payload.id_resep)
        if resep is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Resep {payload.id_resep} tidak ditemukan.",
            )
        status_resep = (
            resep.status_item.value
            if hasattr(resep.status_item, "value")
            else str(resep.status_item) if resep.status_item else None
        )
        if status_resep != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Resep #{payload.id_resep} status saat ini '{status_resep}' — "
                    f"hanya status 'PENDING' yang bisa di-void."
                ),
            )

        # DEC-063 SYNC-V1 (10 Juni 2026): Phase 1 kasir self-acc, no PIN.
        # Validate reason_code against VoidReasonEnum.
        try:
            reason_enum = VoidReasonEnum(payload.reason_code)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Reason code '{payload.reason_code}' tidak valid",
            )

        try:
            now = datetime.now()  # A4: WIB (return display)
            # Kasir void by themselves
            self.repo.void_resep(resep, id_staf_void=id_staf_kasir)

            self.audit.log_void(
                id_staf=id_staf_kasir,
                tabel="kunjungan_resep",
                id_target=payload.id_resep,
                keterangan=(
                    f"Void resep #{payload.id_resep} oleh kasir_id={id_staf_kasir} (self-acc). "
                    f"Reason: {reason_enum.value}. Note: {payload.alasan!r}"
                ),
                request=request,
            )
            self.db.commit()
            return {
                "status": "success",
                "message": f"Item resep #{payload.id_resep} berhasil di-void.",
                "data": {
                    "id_resep": payload.id_resep,
                    "status_item_baru": "BATAL",
                    "voided_by": id_staf_kasir,
                    "reason_code": reason_enum.value,
                    "waktu_void": now.isoformat(),
                },
            }
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gagal void item: {str(e)}",
            )

    # =========================================================================
    # REFUND PER ITEM (task #54-F) — obat tertunda yang tidak pernah datang
    # =========================================================================
    def refund_item_tertunda(
        self,
        *,
        id_resep: Optional[int] = None,
        id_kunjungan_racikan: Optional[int] = None,
        alasan: str,
        metode_refund: str = "TUNAI",
        actor_id_staf: int,
        id_staf_otorisasi: Optional[int] = None,
        pin_otorisasi: Optional[str] = None,
        request: Optional[Request] = None,
    ) -> dict:
        """Batalkan SATU item obat yang sudah dibayar tapi tidak pernah diserahkan,
        dan kembalikan uangnya.

        T32 (keputusan dr. Hansen 2026-10-05, DESAIN_T32_REFUND_HARI_LAMPAU.md):
        - Transaksi HARI LAMPAU butuh persetujuan PIN Admin/Superadmin/Owner, dan
          penyetuju TIDAK BOLEH orang yang sama dengan pemroses refund. Uangnya tetap
          dikembalikan; yang dipagari administrasinya. Hari yang sama: kasir sendiri.
        - Refund dibukukan di HARI REFUND: header transaksi asal TIDAK lagi dikurangi.
          Laporan omzet mengurangi `transaksi_refund` menurut `tgl_refund`
          (`app.services._refund_bukuan`).

        Kenapa bukan void transaksi: void membatalkan SELURUH transaksi, termasuk item
        yang sudah benar-benar diserahkan ke pasien — riwayatnya rusak dan komisi
        dokter untuk item itu hilang padahal pekerjaannya nyata.

        Pagar yang berlaku:
        - item harus **DIBAYAR**. `DISERAHKAN` ditolak (obat sudah di tangan pasien —
          itu urusan retur, bukan refund), `PENDING` ditolak (belum dibayar, pakai
          `void_item_resep`), `BATAL` ditolak (sudah dibatalkan).
        - transaksi asal harus `BAYAR`. Transaksi VOID tidak bisa direfund.
        - stok TIDAK disentuh: status DIBAYAR (bukan DISERAHKAN) sudah menjamin
          stoknya belum pernah dipotong.

        Nilai yang dikembalikan = nilai BERSIH yang benar-benar dibayar pasien
        (subtotal item dikurangi porsi diskonnya), bukan harga penuh.
        """
        import logging
        from sqlalchemy import select
        from app.db.models import TransaksiRefund, StatusItemResepEnum
        from app.db.models.racikan import KunjunganRacikan

        _log = logging.getLogger(__name__)

        if (id_resep is None) == (id_kunjungan_racikan is None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pilih tepat satu: item resep ATAU racikan.",
            )
        if not (alasan or "").strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Alasan pembatalan WAJIB diisi — ini uang keluar.",
            )
        # Audit T4-8: metode refund dari daftar yang dihitung tutup kasir — dulu teks bebas
        # (mis. `TUKAR`) mengurangi omzet tanpa mengurangi laci mana pun.
        from app.core.metode_bayar import metode_sah
        try:
            metode_refund = metode_sah(metode_refund or "TUNAI")
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        # ---- 1. Ambil item + pastikan statusnya DIBAYAR --------------------
        # Audit T3-2: item dibaca BERKUNCI & segar — refund yang berjalan bersama serah
        # dulu bisa mengembalikan uang atas obat yang baru saja diserahkan; dua refund
        # bersamaan sama-sama lolos anti-dobel (cek-lalu-insert tanpa indeks unik).
        from sqlalchemy import select as _sel_k
        from app.db.models import KunjunganResep   # dulu tak diimpor di sini (repo yang membaca)
        # Audit T4-5 (2026-10-15): kunci KUNJUNGAN dulu — urutan yang sama dengan bayar,
        # serah, dan void (void: transaksi → kunjungan → item). Dulu hanya item yang dikunci:
        # void yang berjalan bersamaan sudah memegang kunjungan, menunggu item, lalu tak
        # melihat refund ini (lihat `_kunci_untuk_void`). Transaksi baca ditutup dulu supaya
        # pembacaan sesudah kunci melihat data terbaru (pola T4-1).
        _id_kj = self.db.execute(
            _sel_k(KunjunganResep.id_kunjungan).where(KunjunganResep.id_resep == id_resep)
            if id_resep is not None else
            _sel_k(KunjunganRacikan.id_kunjungan)
            .where(KunjunganRacikan.id_kunjungan_racikan == id_kunjungan_racikan)
        ).scalar_one_or_none()
        mulai_baca_segar(self.db)   # lihat app/services/_baca_segar.py
        if _id_kj is not None:
            self.kunjungan_repo.get_by_id_for_update(_id_kj)
        if id_resep is not None:
            item = self.db.execute(
                _sel_k(KunjunganResep).where(KunjunganResep.id_resep == id_resep)
                .with_for_update().execution_options(populate_existing=True)
            ).scalar_one_or_none()
            if item is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND,
                                    f"Resep {id_resep} tidak ditemukan.")
            _st = item.status_item.value if hasattr(item.status_item, "value") else str(item.status_item or "")
            _label = f"resep #{id_resep}"
            _sumber_komisi, _id_ref_komisi = "PRODUK", id_resep
        else:
            item = self.db.execute(
                _sel_k(KunjunganRacikan)
                .where(KunjunganRacikan.id_kunjungan_racikan == id_kunjungan_racikan)
                .with_for_update().execution_options(populate_existing=True)
            ).scalar_one_or_none()
            if item is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND,
                                    f"Racikan {id_kunjungan_racikan} tidak ditemukan.")
            _st = str(item.status_item or "")
            _label = f"racikan #{id_kunjungan_racikan} ({item.nama_snapshot})"
            _sumber_komisi, _id_ref_komisi = "RACIKAN", id_kunjungan_racikan

        if _st == "DISERAHKAN":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    # Refund di sini hanya untuk obat yang BELUM diserahkan. Obat yang
                    # sudah diserahkan → retur dari pasien (DESAIN_RETUR_DARI_PASIEN.md).
                    f"{_label} sudah DISERAHKAN ke pasien — tidak bisa direfund dari "
                    "sini (refund hanya untuk obat yang belum diserahkan). Pakai Kasir → "
                    "Cari Transaksi → ↩ Retur."
                ),
            )
        if _st != "DIBAYAR":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"{_label} berstatus '{_st}' — hanya item DIBAYAR yang bisa "
                    "direfund."
                ),
            )

        # ---- 2. Temukan transaksi + nilai BERSIH item ----------------------
        # Rumusnya dipakai bersama dengan retur dari pasien (retur_pasien_service) —
        # SATU rumus uang, bukan dua salinan (CLAUDE.md §4.1).
        trx, nilai = self.trx_dan_nilai_bersih(
            item=item, id_resep=id_resep, id_kunjungan_racikan=id_kunjungan_racikan,
            label=_label,
        )

        if nilai <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Nilai refund {_label} nol — tidak ada yang dikembalikan.",
            )

        # ---- 3. Anti-dobel: item ini belum pernah direfund -----------------
        _sudah = self.db.execute(
            select(TransaksiRefund.id_refund).where(
                TransaksiRefund.id_resep == id_resep
                if id_resep is not None
                else TransaksiRefund.id_kunjungan_racikan == id_kunjungan_racikan
            ).limit(1).with_for_update()   # Audit T3-2: lihat refund yang baru saja di-commit
        ).first()
        if _sudah:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{_label} sudah pernah direfund.",
            )

        # ---- 3b. T32: transaksi hari lampau butuh PIN penyetuju -------------
        # "Hari lampau" memakai helper yang SAMA dengan jalur void, supaya refund
        # dan void tidak punya dua definisi berbeda tentang "hari ini".
        hari_lampau = (
            trx.waktu_bayar is not None
            and not self._is_same_calendar_day_utc7(trx.waktu_bayar, self._now_utc7())
        )
        id_penyetuju = None
        if hari_lampau:
            id_penyetuju = self._otorisasi_refund_lampau(
                trx=trx, label=_label, actor_id_staf=actor_id_staf,
                id_staf_otorisasi=id_staf_otorisasi, pin_otorisasi=pin_otorisasi,
                request=request,
            )

        try:
            now = self._now_utc7().replace(tzinfo=None)

            # ---- 4. Catat refund (tabel yang SUDAH dibaca ekspor Finance G9) ----
            self.db.add(TransaksiRefund(
                id_transaksi=trx.id_transaksi,
                tgl_refund=now,
                nilai_refund=nilai,
                metode_refund=metode_refund,
                alasan=f"Pembatalan obat tertunda — {_label}. {alasan.strip()}",
                id_staf_refund=actor_id_staf,
                id_staf_otorisasi=id_penyetuju,
                jenis_refund="ITEM",
                id_resep=id_resep,
                id_kunjungan_racikan=id_kunjungan_racikan,
            ))

            # ---- 5. Item jadi BATAL (stok TIDAK disentuh) ----------------------
            if id_resep is not None:
                item.status_item = StatusItemResepEnum.BATAL
                item.id_staf_void = actor_id_staf
                item.waktu_void = now
            else:
                item.status_item = "BATAL"

            # ---- 6. Header transaksi asal TIDAK disentuh (T32) -------------------
            # Dulu: `trx.total_tagihan -= nilai`, supaya 12 titik agregasi uang benar
            # tanpa query disentuh. Akibatnya omzet HARI ASAL berubah — hari yang
            # mungkin sudah tutup kasir dan sudah terkirim ke Finance. Keputusan dr.
            # Hansen 2026-10-05: refund dibukukan di HARI REFUND. Pengurangannya kini
            # terjadi saat laporan dibaca (`app.services._refund_bukuan`).
            # ⚠ JANGAN kembalikan mutasi ini: migrasi 20261005_0100 sudah memulihkan
            # header lama, jadi mutasi + pengurangan di laporan = refund DUA KALI.
            _total_lama = Decimal(str(trx.total_tagihan or 0))

            # ---- 7. Komisi baris item itu saja -------------------------------
            n_komisi = KomisiService(self.db).void_komisi_item(
                id_transaksi=trx.id_transaksi, sumber=_sumber_komisi,
                id_ref=_id_ref_komisi, actor_id_staf=actor_id_staf, request=request,
            )

            self.audit.log(
                aksi="REFUND_ITEM",
                id_staf=actor_id_staf,
                tabel_target="transaksi_kasir",
                id_target=trx.id_transaksi,
                data_lama={"total_tagihan": float(_total_lama)},
                data_baru={
                    "total_tagihan": float(_total_lama),  # tidak berubah sejak T32
                    "nilai_refund": float(nilai),
                    "metode_refund": metode_refund,
                    "id_resep": id_resep,
                    "id_kunjungan_racikan": id_kunjungan_racikan,
                    "komisi_divoid": n_komisi,
                    "hari_lampau": hari_lampau,
                    "id_staf_otorisasi": id_penyetuju,
                },
                keterangan=(
                    f"Refund item: {_label} sebesar {nilai}, dibukukan hari ini. Stok "
                    f"TIDAK dikembalikan (obat belum pernah diserahkan)."
                    + (f" Disetujui staf #{id_penyetuju} (transaksi hari lampau)."
                       if id_penyetuju else "")
                    + f" Alasan: {alasan.strip()!r}"
                ),
                request=request,
            )
            self.db.commit()
            return {
                "status": "success",
                "message": (
                    f"{_label} dibatalkan. Refund Rp {nilai:,.0f} ({metode_refund}), "
                    f"dibukukan hari ini."
                ).replace(",", "."),
                "data": {
                    "id_transaksi": trx.id_transaksi,
                    "nilai_refund": float(nilai),
                    "komisi_divoid": n_komisi,
                    "id_staf_otorisasi": id_penyetuju,
                },
            }
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            _log.exception("GAGAL refund item tertunda (%s)", _label)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gagal refund item: {e!s}",
            )

    def trx_dan_nilai_bersih(
        self,
        *,
        item,
        id_resep: Optional[int],
        id_kunjungan_racikan: Optional[int],
        label: str,
        qty=None,
    ) -> tuple:
        """(transaksi asal BAYAR, nilai BERSIH yang dibayar pasien untuk item ini).

        Bersih = subtotal baris dikurangi porsi diskonnya (`diskon_item`), dari snapshot
        transaksi — bukan harga master hari ini. `qty` (default qty item) memberi nilai
        proporsional per unit: dipakai retur SEBAGIAN dari pasien.
        Dipakai `refund_item_tertunda` DAN retur dari pasien — jangan disalin; dua rumus
        uang untuk hal yang sama pasti berbeda suatu hari (CLAUDE.md §4.1).
        Racikan selalu utuh (all-or-nothing) — `qty` diabaikan.
        """
        from sqlalchemy import select
        _label = label
        if id_resep is not None:
            # Resep tidak menyimpan id_transaksi; cari lewat detail produk transaksi
            # BAYAR pada kunjungan yang sama. Kalau satu produk muncul di dua baris
            # resep, nilainya dibagi rata per unit — itu satu-satunya pembagian yang
            # bisa dipertanggungjawabkan tanpa id_resep di tabel detail.
            # Transaksi yang MEMUAT produk ini, dibayar sesudah resepnya ditulis, yang
            # PALING AWAL. Dulu: "transaksi BAYAR terbaru di kunjungan" — benar selama satu
            # kunjungan hanya punya satu transaksi. Sejak retur TUKAR (2026-10-05) produk
            # pengganti ditagih di transaksi BARU di kunjungan yang sama, sehingga "terbaru"
            # untuk obat ASAL menunjuk transaksi tukar — salah transaksi, salah nilai.
            # Syarat waktu_input membuat produk pengganti menunjuk transaksi tukarnya
            # sendiri (resepnya ditulis tepat sebelum transaksi itu).
            _q = (
                select(TransaksiKasir)
                .join(TransaksiDetailProduk,
                      TransaksiDetailProduk.id_transaksi == TransaksiKasir.id_transaksi)
                .where(TransaksiKasir.id_kunjungan == item.id_kunjungan,
                       TransaksiKasir.status_transaksi == "BAYAR",
                       TransaksiDetailProduk.id_produk == item.id_produk)
            )
            trx = None
            # Audit T2-2: sejak migrasi 20261013_0100 resep MENYIMPAN transaksi pembayarnya
            # — itu yang dipakai. Pencarian lewat waktu di bawah tinggal jalur CADANGAN untuk
            # baris lama tanpa penanda.
            _tid = getattr(item, "id_transaksi", None)
            if _tid is not None:
                trx = self.db.execute(
                    _q.where(TransaksiKasir.id_transaksi == _tid)).scalars().first()
            if trx is None and getattr(item, "waktu_input", None) is not None:
                # Kedua kolom diisi JAM SERVER MySQL (server_default), jadi sebanding.
                trx = self.db.execute(
                    _q.where(TransaksiKasir.waktu_bayar >= item.waktu_input)
                    .order_by(TransaksiKasir.id_transaksi.asc()).limit(1)
                ).scalars().first()
            if trx is None:
                # Jatuh kembali tanpa syarat waktu (data lama/impor, jam yang pernah
                # bergeser): transaksi PALING AWAL yang memuat produk ini.
                trx = self.db.execute(
                    _q.order_by(TransaksiKasir.id_transaksi.asc()).limit(1)
                ).scalars().first()
            if trx is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Tidak ada transaksi BAYAR untuk {_label}.",
                )
            detail = self.db.execute(
                select(TransaksiDetailProduk).where(
                    TransaksiDetailProduk.id_transaksi == trx.id_transaksi,
                    TransaksiDetailProduk.id_produk == item.id_produk,
                ).limit(1)
            ).scalars().first()
            if detail is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{_label} tidak ditemukan di rincian transaksi "
                           f"#{trx.id_transaksi}.",
                )
            _qty_detail = Decimal(str(detail.qty or 0))
            _qty_item = Decimal(str(item.qty if qty is None else qty))
            _net_detail = (Decimal(str(detail.subtotal or 0))
                           - Decimal(str(detail.diskon_item or 0)))
            if _qty_detail > 0 and _qty_item > 0 and _qty_item != _qty_detail:
                nilai = (_net_detail * _qty_item / _qty_detail).quantize(Decimal("0.01"))
            else:
                nilai = _net_detail.quantize(Decimal("0.01"))
        else:
            _dr = self.db.execute(
                select(TransaksiDetailRacikan).where(
                    TransaksiDetailRacikan.id_kunjungan_racikan == id_kunjungan_racikan
                ).limit(1)
            ).scalars().first()
            if _dr is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{_label} belum pernah ditagih — tidak ada yang direfund.",
                )
            trx = self.db.get(TransaksiKasir, _dr.id_transaksi)
            if trx is None or trx.status_transaksi != "BAYAR":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Transaksi asal {_label} bukan BAYAR — tidak bisa direfund.",
                )
            nilai = Decimal(str(_dr.subtotal or 0)).quantize(Decimal("0.01"))

        return trx, nilai

    def _otorisasi_refund_lampau(
        self,
        *,
        trx: TransaksiKasir,
        label: str,
        actor_id_staf: int,
        id_staf_otorisasi: Optional[int],
        pin_otorisasi: Optional[str],
        request: Optional[Request],
        alasan_perlu: Optional[str] = None,
        aksi_tolak: str = "REFUND_DITOLAK_PIN",
    ) -> int:
        """Pagar T32: refund atas transaksi hari lampau. Return id penyetuju, atau raise.

        Dipakai juga retur dari pasien (hari lampau ATAU retur sebagian): `alasan_perlu`
        mengganti kalimat "kenapa butuh PIN", `aksi_tolak` nama aksi audit penolakan.

        Meniru otorisasi PIN dokter di `upsell_service` (pola yang sudah berjalan),
        dengan satu tambahan: penyetuju ≠ pemroses (empat mata, keputusan dr. Hansen
        2026-10-05). Penolakan PIN/peran dicatat di audit dan di-COMMIT sebelum raise —
        percobaan yang ditolak justru yang paling perlu terlihat. Pesan untuk PIN salah
        dan staf tak berwenang SENGAJA sama (tidak memberi petunjuk mana yang salah).
        """
        tgl_trx = trx.waktu_bayar.strftime("%d/%m/%Y")
        if not id_staf_otorisasi or not (pin_otorisasi or "").strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    (alasan_perlu or f"Transaksi {label} dibayar {tgl_trx} (hari lampau). Refund")
                    + " butuh persetujuan PIN Admin/Superadmin/Owner."
                ),
            )
        if id_staf_otorisasi == actor_id_staf:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Penyetuju tidak boleh orang yang sama dengan yang memproses refund.",
            )

        penyetuju = self.staf_repo.get_by_id(id_staf_otorisasi)
        _role = (
            penyetuju.role.value if penyetuju is not None and hasattr(penyetuju.role, "value")
            else (str(penyetuju.role) if penyetuju is not None else None)
        )
        pin_valid = False
        if (penyetuju is not None and penyetuju.is_active and penyetuju.pin
                and _role in _ROLES_PENYETUJU_REFUND):
            try:
                pin_valid = verify_password(pin_otorisasi, penyetuju.pin)
            except Exception:
                pin_valid = False

        if not pin_valid:
            self.audit.log(
                aksi=aksi_tolak,
                id_staf=actor_id_staf,
                tabel_target="transaksi_kasir",
                id_target=trx.id_transaksi,
                keterangan=(
                    f"Refund {label} atas transaksi {tgl_trx} ditolak: PIN salah atau "
                    f"staf tidak berwenang. id_staf_otorisasi_diuji={id_staf_otorisasi}"
                ),
                status_aksi=StatusAksiAuditEnum.FAILED,
                request=request,
            )
            self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="PIN penyetuju salah atau staf tidak berwenang menyetujui refund.",
            )
        return penyetuju.id_staf

    # =========================================================================
    # REKAP SHIFT
    # =========================================================================
    def rekap_shift(self, id_staf_kasir: int) -> RekapShiftResponse:
        staf = self.staf_repo.get_by_id(id_staf_kasir)
        if staf is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Staf kasir {id_staf_kasir} tidak ditemukan.",
            )

        sejak = staf.waktu_mulai_shift or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)  # A4: WIB anchor

        rows = self.repo.list_transaksi_shift(id_staf_kasir, sejak)
        per_metode_rows = self.repo.aggregate_pembayaran_shift(id_staf_kasir, sejak)

        daftar = [
            RekapShiftItem(
                id_transaksi=trx.id_transaksi,
                waktu_bayar=trx.waktu_bayar,
                nama_pasien=pasien.nama,
                total_tagihan=Decimal(str(trx.total_tagihan)),
            )
            for trx, pasien in rows
        ]
        per_metode = [
            RekapPerMetode(metode_bayar=m, jumlah_transaksi=n, total_nominal=total)
            for m, n, total in per_metode_rows
        ]
        # T32: refund oleh kasir ini sejak shift mulai dikurangkan di sini (sama dengan
        # tutup kasir) — bukan lagi lewat header transaksi asal yang dimutasi.
        from app.services import _refund_bukuan as _rb
        total_refund = _rb.refund_per_staf(self.db, sejak, datetime.now()).get(
            id_staf_kasir, Decimal("0"))
        total_omzet = sum((t.total_tagihan for t in daftar), Decimal("0")) - total_refund

        return RekapShiftResponse(
            id_staf_kasir=id_staf_kasir,
            nama_kasir=staf.nama_staf,
            waktu_mulai_shift=staf.waktu_mulai_shift,
            waktu_rekap=datetime.now(),
            total_transaksi=len(daftar),
            total_omzet=total_omzet,
            total_refund=total_refund,
            per_metode=per_metode,
            daftar_transaksi=daftar,
        )



    # =========================================================================
    # VOID PEMBAYARAN (DEC-063, #364) — Phase 1
    # =========================================================================

    # Minimum karakter note per reason code
    _VOID_REASON_MIN_CHARS = {
        VoidReasonEnum.SALAH_INPUT: 5,
        VoidReasonEnum.CUSTOMER_CANCEL: 5,
        VoidReasonEnum.REFUND_PASCA_TINDAKAN: 10,
        VoidReasonEnum.ITEM_RUSAK: 5,
        VoidReasonEnum.DUPLICATE_TRANSAKSI: 5,
        VoidReasonEnum.OTHER: 20,
    }

    # Max past-day untuk force void:
    # Kasir=0 (only same-day), Admin=3, Superadmin/Owner=7
    _MAX_PAST_DAYS_BY_ROLE = {
        StafRoleEnum.KASIR: 0,
        StafRoleEnum.ADMIN: 3,
        StafRoleEnum.SUPERADMIN: 7,
        StafRoleEnum.OWNER: 7,
    }

    # Bayar dulu T2-4: tindakan yang BELUM SELESAI dikerjakan dan belum dibatalkan. Void
    # transaksi yang menagihnya (dibayar di muka) MELEPASnya ke "belum ditagih" — tindakannya
    # tetap hidup, jadi kuota & series yang dipegangnya TIDAK dikembalikan/dibatalkan void.
    # Tindakan SELESAI di lingkup void ditolak pagar `_pagari_void_tindakan_selesai`.
    _TINDAKAN_HIDUP = (StatusTindakanEnum.PENDING, StatusTindakanEnum.PROSES)

    @staticmethod
    def _now_utc7():
        """Current datetime di UTC+7 (WIB)."""
        return datetime.now(timezone(timedelta(hours=7)))

    @staticmethod
    def _is_same_calendar_day_utc7(trx_dt, now_dt):
        """True kalau trx dan now masih di calendar day yang sama UTC+7."""
        wib = timezone(timedelta(hours=7))
        if trx_dt.tzinfo is None:
            trx_dt = trx_dt.replace(tzinfo=wib)
        else:
            trx_dt = trx_dt.astimezone(wib)
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=wib)
        else:
            now_dt = now_dt.astimezone(wib)
        return trx_dt.date() == now_dt.date()

    @staticmethod
    def _days_past(trx_dt, now_dt):
        """Jumlah hari kalender yang sudah lewat sejak transaksi."""
        wib = timezone(timedelta(hours=7))
        if trx_dt.tzinfo is None:
            trx_dt = trx_dt.replace(tzinfo=wib)
        else:
            trx_dt = trx_dt.astimezone(wib)
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=wib)
        else:
            now_dt = now_dt.astimezone(wib)
        return (now_dt.date() - trx_dt.date()).days

    def _validate_reason_note(self, reason_code, reason_note):
        """Raise 400 kalau note kurang dari min char untuk reason."""
        min_chars = self._VOID_REASON_MIN_CHARS.get(reason_code, 5)
        note_clean = (reason_note or "").strip()
        if len(note_clean) < min_chars:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Note void untuk reason '{reason_code.value}' "
                    f"minimal {min_chars} karakter. Saat ini: {len(note_clean)}."
                ),
            )

    def _lingkup_void(self, trx) -> dict:
        """Item yang DIBAYAR oleh transaksi INI — dasar SEMUA cascade & pagar void.

        Audit T2-2 (2026-10-13): dulu setiap cascade memilih per `id_kunjungan`. Pada split
        billing (T1 + tagihan susulan T2 di satu kunjungan) void T2 membatalkan obat T1,
        mengembalikan kuota tindakan T1, membatalkan series yang dibeli di T1 — dan
        sebaliknya tindakan SELESAI di T1 menghalangi void T2 yang hanya berisi obat.

        - TUNGGAL (tak ada transaksi BAYAR lain di kunjungan): resep & racikan = seluruh
          kunjungan, persis perilaku lama — aman untuk data lama tanpa penanda.
        - JAMAK: resep lewat `kunjungan_resep.id_transaksi` (migrasi 20261013_0100), racikan
          lewat `kunjungan_racikan.id_transaksi`. Bila ada obat lunas yang TIDAK tercatat
          transaksinya (data lama), 409 — sistem menolak alih-alih menebak.
        - TINDAKAN (Ruling 13, review akhir bayar dulu tahap 1) — TUNGGAL maupun JAMAK:
          `kunjungan_tindakan.id_transaksi == trx`; baris lama yang penandanya NULL memakai
          snapshot `transaksi_detail_tindakan` transaksi ini. Dulu TUNGGAL = semua tindakan
          kunjungan: benar selama tindakan selalu selesai sebelum bayar. Sejak bayar dulu,
          satu-satunya transaksi bisa menagih konsul/obat saja sementara tindakan masih
          PENDING — void-nya lalu mengembalikan kuota tindakan yang tak pernah ditagihnya
          (dan Batalkan tindakan mengembalikannya LAGI), membatalkan series yang sesi 1-nya
          belum dibayar, dan tindakan SUSULAN yang SELESAI tapi belum ditagih menghalangi
          void dengan pagar "tindakan sudah selesai". `series_pembuat` mengikuti lingkup ini.
          Migrasi 20261021_0100 menolak naik bila ada tindakan SELESAI di kunjungan lunas yang
          tak terpasangkan, jadi `id_transaksi` NULL di sini berarti BELUM DITAGIH.
        Return {"tunggal", "resep", "racikan", "tindakan", "series_pembuat"} (set id).
        """
        from sqlalchemy import and_, func, or_, select
        from app.db.models import (KunjunganResep, KunjunganTindakan, PasienRencanaTreatment,
                                   TransaksiDetailTindakan)
        from app.db.models.racikan import KunjunganRacikan as _KRC

        k = trx.id_kunjungan
        tindakan = set(self.db.execute(
            select(KunjunganTindakan.id_kunjungan_tindakan)
            .where(KunjunganTindakan.id_kunjungan == k)
            .where(or_(
                KunjunganTindakan.id_transaksi == trx.id_transaksi,
                and_(KunjunganTindakan.id_transaksi.is_(None),
                     KunjunganTindakan.id_kunjungan_tindakan.in_(
                         select(TransaksiDetailTindakan.id_kunjungan_tindakan)
                         .where(TransaksiDetailTindakan.id_transaksi == trx.id_transaksi)
                         .where(TransaksiDetailTindakan.id_kunjungan_tindakan.is_not(None))))))
        ).scalars())
        # Series lahir dari kunjungan ini; harga paketnya ditagih bersama tindakan SESI 1.
        # Rencana series hanya ikut dibatalkan bila transaksi INI yang menagih sesi 1.
        series_pembuat = False
        if tindakan:
            series_pembuat = bool(self.db.execute(
                select(func.count(KunjunganTindakan.id_kunjungan_tindakan))
                .join(PasienRencanaTreatment,
                      PasienRencanaTreatment.id_rencana == KunjunganTindakan.id_rencana)
                .where(KunjunganTindakan.id_kunjungan_tindakan.in_(tindakan))
                .where(PasienRencanaTreatment.urutan_sesi == 1)
                .where(PasienRencanaTreatment.id_kunjungan_pembuat == k)).scalar())

        lain = self.db.execute(
            select(func.count(TransaksiKasir.id_transaksi))
            .where(TransaksiKasir.id_kunjungan == k)
            .where(TransaksiKasir.status_transaksi == "BAYAR")
            .where(TransaksiKasir.id_transaksi != trx.id_transaksi)
        ).scalar() or 0
        if not lain:
            return {
                "tunggal": True,
                "resep": set(self.db.execute(select(KunjunganResep.id_resep)
                             .where(KunjunganResep.id_kunjungan == k)).scalars()),
                "racikan": set(self.db.execute(select(_KRC.id_kunjungan_racikan)
                               .where(_KRC.id_kunjungan == k)).scalars()),
                "tindakan": tindakan,
                "series_pembuat": series_pembuat,
            }

        _lunas = ("DIBAYAR", "DISERAHKAN")
        tanpa_resep = self.db.execute(
            select(func.count(KunjunganResep.id_resep))
            .where(KunjunganResep.id_kunjungan == k)
            .where(KunjunganResep.status_item.in_(_lunas))
            .where(KunjunganResep.id_transaksi.is_(None))).scalar() or 0
        tanpa_racik = self.db.execute(
            select(func.count(_KRC.id_kunjungan_racikan))
            .where(_KRC.id_kunjungan == k)
            .where(_KRC.status_item.in_(_lunas))
            .where(_KRC.id_transaksi.is_(None))).scalar() or 0
        # Tindakan TIDAK lagi ikut pagar ambigu ini (Ruling 13): dulu "kunjungan punya
        # tindakan tapi tak ada snapshot" = data pra-F3 yang tak bisa dipilah. Kini tindakan
        # pra-F3 yang lunas sudah ber-`id_transaksi` (backfill 20261021_0100, yang menolak
        # naik bila ada yang tak terpasangkan), dan pagar lama justru menolak void kunjungan
        # bayar-dulu yang tindakannya belum ditagih sama sekali (konsul T1 + obat T2,
        # tindakan PENDING → tak ada snapshot → 409).
        if tanpa_resep or tanpa_racik:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(f"Transaksi #{trx.id_transaksi} adalah salah satu dari beberapa "
                        f"transaksi di kunjungan ini, dan ada item lama yang tidak tercatat "
                        f"dibayar oleh transaksi mana — sistem tidak bisa memastikan item mana "
                        f"yang ikut di-void. Void TIDAK dijalankan; hubungi Admin."),
            )

        return {
            "tunggal": False,
            "resep": set(self.db.execute(select(KunjunganResep.id_resep)
                         .where(KunjunganResep.id_kunjungan == k)
                         .where(KunjunganResep.id_transaksi == trx.id_transaksi)).scalars()),
            "racikan": set(self.db.execute(select(_KRC.id_kunjungan_racikan)
                           .where(_KRC.id_kunjungan == k)
                           .where(_KRC.id_transaksi == trx.id_transaksi)).scalars()),
            "tindakan": tindakan,
            "series_pembuat": series_pembuat,
        }

    def _cancel_series_sesi_pending(self, trx, actor_id_staf, request):
        """Auto-cancel sesi PENDING/SCHEDULED dari pasien_rencana_treatment
        yang lahir dari kunjungan ini (Skenario B.1 DEC-063) — HANYA bila transaksi
        ini yang menagih sesi 1 (Audit T2-2, `_lingkup_void`).
        Return count."""
        from app.db.models import PasienRencanaTreatment, StatusRencanaTreatmentEnum
        from sqlalchemy import select
        _lk = self._lingkup_void(trx)
        if not _lk["series_pembuat"]:
            return 0
        _aktif = (StatusRencanaTreatmentEnum.PENDING, StatusRencanaTreatmentEnum.SCHEDULED)
        id_kunjungan = trx.id_kunjungan
        # Audit T4-11: hanya series yang SESI 1-nya ditagih transaksi ini — dulu semua
        # rencana kunjungan, termasuk sisa sesi series lain yang sudah lunas di transaksi
        # lain (reopen). Anggota series: app/services/_series.py.
        # Ruling 13 (bayar dulu): berlaku juga untuk TUNGGAL. Dulu "satu transaksi → semua
        # series yang lahir di sini dibayar olehnya"; sejak bayar dulu satu-satunya transaksi
        # bisa menagih konsul saja sementara sesi 1 masih PENDING — void-nya membatalkan
        # series yang harga paketnya baru akan ditagih bersama sesi 1 nanti.
        # Bayar dulu T2-4: sesi 1 yang tindakannya MASIH HIDUP (PENDING/PROSES, dibayar di
        # muka) TIDAK membatalkan seriesnya — void melepas tindakan itu kembali ke "belum
        # ditagih" (`_lepas_tindakan_hidup`) dan harga paketnya akan ditagih lagi bersamanya.
        # Membatalkan series di sini meninggalkan sesi 1 hidup tanpa seriesnya. Kalau pasien
        # lalu menolak sesi 1, Batalkan tindakan yang membatalkan series (`_batal_tindakan`).
        from app.db.models import KunjunganTindakan as _KT
        from app.services._series import anggota as _anggota
        sesi1_list = self.db.execute(
            select(PasienRencanaTreatment)
            .join(_KT, _KT.id_rencana == PasienRencanaTreatment.id_rencana)
            .where(_KT.id_kunjungan_tindakan.in_(_lk["tindakan"] or {-1}))
            .where(_KT.status_tindakan.notin_(self._TINDAKAN_HIDUP))
            .where(PasienRencanaTreatment.urutan_sesi == 1)
            .where(PasienRencanaTreatment.id_kunjungan_pembuat == id_kunjungan)
        ).scalars().all()
        rencana_list = [r for s1 in sesi1_list for r in _anggota(self.db, s1)
                        if r.status in _aktif]
        for rencana in rencana_list:
            old_status = rencana.status
            rencana.status = StatusRencanaTreatmentEnum.CANCELLED
            self.audit.log(
                aksi="VOID_SERIES_AUTO_CANCEL",
                id_staf=actor_id_staf,
                tabel_target="pasien_rencana_treatment",
                id_target=rencana.id_rencana,
                data_lama={"status": old_status.value if hasattr(old_status, "value") else str(old_status)},
                data_baru={"status": "CANCELLED", "trigger": "void_transaksi"},
                request=request,
            )
        return len(rencana_list)

    def _produk_stok_sudah_dipotong(self, transaksi) -> bool:
        """LEGACY — tebakan lama: COMPLETED berarti stok sudah dipotong.

        P0-1 (AUDIT_SEHATI_2026-07-10): dulu stok produk hanya dipotong saat serah obat,
        yang selalu mentransisi `ANTRI_OBAT -> COMPLETED`. Jadi COMPLETED = sudah diserah.

        ⚠ Sejak task #54 (serah PER ITEM, 2026-09-22) tebakan ini **tidak lagi benar**:
        kunjungan bisa COMPLETED sementara sebagian item belum diserahkan sama sekali.
        Memakainya akan mengembalikan stok yang tidak pernah keluar. Fungsi ini sekarang
        HANYA dipakai untuk data LAMA — kunjungan yang diserahkan sebelum status
        DISERAHKAN ada, sehingga itemnya masih tercatat DIBAYAR. Lihat `_mode_per_item`.
        """
        if not transaksi.id_kunjungan:
            return False
        from app.db.models import Kunjungan
        kunjungan = self.db.get(Kunjungan, transaksi.id_kunjungan)
        return kunjungan is not None and kunjungan.status_antrian == "COMPLETED"

    def _mode_per_item(self, id_kunjungan) -> bool:
        """True kalau kunjungan ini bisa dinilai PER ITEM (bukan lewat tebakan COMPLETED).

        Benar dalam dua keadaan, dan keduanya aman:
        - ada item berstatus DISERAHKAN → jelas sudah pakai skema baru;
        - belum ada jejak lot sama sekali → belum pernah ada penyerahan, jadi tidak ada
          apa pun yang perlu dikembalikan (jawaban per item = 0 untuk semuanya).

        Kalau keduanya tidak terpenuhi (ada jejak lot tapi tidak ada satu pun item
        DISERAHKAN) berarti kunjungan LAMA — diserahkan sebelum skema ini ada — dan
        penilaiannya jatuh ke `_produk_stok_sudah_dipotong`.
        """
        from sqlalchemy import select
        from app.db.models import KunjunganResep, KunjunganLotTerpakai, StatusItemResepEnum
        from app.db.models.racikan import KunjunganRacikan

        if not id_kunjungan:
            return False
        ada_diserahkan = self.db.execute(
            select(KunjunganResep.id_resep).where(
                KunjunganResep.id_kunjungan == id_kunjungan,
                KunjunganResep.status_item == StatusItemResepEnum.DISERAHKAN,
            ).limit(1)
        ).first() or self.db.execute(
            select(KunjunganRacikan.id_kunjungan_racikan).where(
                KunjunganRacikan.id_kunjungan == id_kunjungan,
                KunjunganRacikan.status_item == "DISERAHKAN",
            ).limit(1)
        ).first()
        if ada_diserahkan:
            return True
        ada_jejak = self.db.execute(
            select(KunjunganLotTerpakai.id_terpakai).where(
                KunjunganLotTerpakai.id_kunjungan == id_kunjungan
            ).limit(1)
        ).first()
        return not ada_jejak

    def _qty_produk_diserahkan(self, id_kunjungan, id_produk, id_resep_scope=None) -> float:
        """Total qty produk ini yang BENAR-BENAR sudah diserahkan di kunjungan tsb.

        Dijumlahkan, bukan diambil satu, karena satu produk bisa muncul di lebih dari
        satu baris resep — dan hanya sebagian yang sudah diserahkan.

        `id_resep_scope` (Audit T3-1): batasi ke resep milik SATU transaksi
        (`_lingkup_void(trx)["resep"]`). Tanpa itu, void transaksi susulan menghitung obat
        yang diserahkan lewat transaksi LAIN sebagai jatah pengembalian → stok hantu.
        """
        from sqlalchemy import select, func as _func
        from app.db.models import KunjunganResep, StatusItemResepEnum

        q = select(_func.coalesce(_func.sum(KunjunganResep.qty), 0)).where(
            KunjunganResep.id_kunjungan == id_kunjungan,
            KunjunganResep.id_produk == id_produk,
            KunjunganResep.status_item == StatusItemResepEnum.DISERAHKAN,
        )
        if id_resep_scope is not None:
            q = q.where(KunjunganResep.id_resep.in_(id_resep_scope))
        return float(self.db.execute(q).scalar() or 0)

    def _reverse_stok_per_item(self, transaksi, items_reverse, actor_id_staf, request, lot_map=None):
        """Reverse stok produk untuk items_reverse yang dichecklist user.

        P-L6b: kembalikan qty ke LOT yang dipilih operator (batch fisik yg diretur, baca label) →
        audit jelas untuk QC/telusur produk cacat. Kalau batch tak dipilih → buat lot 'VOID-RETURN' baru.

        P0-1 GUARD: hanya me-reverse kalau obat memang sudah diserah (stok sudah dipotong).
        Kalau belum, stok tak pernah berkurang → reverse = no-op (cegah overstate senyap).
        """
        from datetime import date as _date
        from app.db.models import MasterProduk, StokLot, KunjunganLotTerpakai
        from sqlalchemy import select

        if not items_reverse:
            return 0
        # Task #54: penilaian "stok sudah dipotong" pindah dari status KUNJUNGAN ke status
        # ITEM. Tebakan lama hanya dipakai untuk kunjungan lama (lihat _mode_per_item).
        per_item = self._mode_per_item(transaksi.id_kunjungan)
        if not per_item and not self._produk_stok_sudah_dipotong(transaksi):
            return 0
        lot_map = lot_map or {}
        # Audit T3-1 (2026-10-13): jatah & jejak lot PER TRANSAKSI. Saat T2-2 semua cascade
        # void dipindah ke `_lingkup_void`, tapi pembantu stok ini TERLEWAT (kesalahan sendiri,
        # tertangkap audit tahap 3) — void susulan T2 "mengembalikan" stok obat T1 yang sudah
        # diserahkan: stok hantu, dan jejak lot T1 ikut ditandai reversed.
        _lk = self._lingkup_void(transaksi) if transaksi.id_kunjungan else None

        # Token ber-namespace supaya produk & racikan tidak saling tertukar:
        #   "PRD:<id_produk>"            → baris produk di transaksi ini
        #   "RCK:<id_kunjungan_racikan>" → racikan; yang dikembalikan adalah tiap BAHAN-nya
        #   "<angka>"                    → legacy = id_detail transaksi_detail_produk
        # Sebelumnya template mengirim id_resep sementara service memfilter id_detail —
        # keduanya tidak pernah cocok, jadi reverse stok diam-diam tidak terjadi.
        from app.db.models.racikan import (
            KunjunganRacikanBahan as _KRCB,
            TransaksiDetailRacikan as _TDR,
        )

        jobs = []  # (produk, qty, lot_key, penanda_selesai, id_kunjungan_racikan|None)
        legacy_ids, produk_ids, racik_ids = [], [], []
        for tok in items_reverse:
            s = str(tok).strip()
            if s.upper().startswith("PRD:"):
                try:
                    produk_ids.append(int(s[4:]))
                except ValueError:
                    pass
            elif s.upper().startswith("RCK:"):
                try:
                    racik_ids.append(int(s[4:]))
                except ValueError:
                    pass
            else:
                try:
                    legacy_ids.append(int(s))
                except ValueError:
                    pass

        _cond = []
        if legacy_ids:
            _cond.append(TransaksiDetailProduk.id_detail.in_(legacy_ids))
        if produk_ids:
            _cond.append(TransaksiDetailProduk.id_produk.in_(produk_ids))
        if _cond:
            from sqlalchemy import or_ as _or
            for detail in self.db.execute(
                select(TransaksiDetailProduk).where(
                    TransaksiDetailProduk.id_transaksi == transaksi.id_transaksi,
                    _or(*_cond),
                )
            ).scalars().all():
                _p = self.db.get(MasterProduk, detail.id_produk)
                if _p is None:
                    continue
                jobs.append((_p, float(detail.qty), detail.id_detail, detail, None))

        for _dr in (self.db.execute(
            select(_TDR).where(
                _TDR.id_transaksi == transaksi.id_transaksi,
                _TDR.id_kunjungan_racikan.in_(racik_ids),
            )
        ).scalars().all() if racik_ids else []):
            for _b in self.db.execute(
                select(_KRCB).where(
                    _KRCB.id_kunjungan_racikan == _dr.id_kunjungan_racikan)
            ).scalars().all():
                if not _b.id_produk:
                    continue
                _pb = self.db.get(MasterProduk, _b.id_produk)
                if _pb is None or float(_b.dipakai or 0) <= 0:
                    continue
                jobs.append((_pb, float(_b.dipakai), f"RCK:{_dr.id_kunjungan_racikan}", _dr,
                             _dr.id_kunjungan_racikan))

        # Berapa qty tiap produk yang SUDAH terpakai oleh job sebelumnya — supaya dua
        # baris transaksi dengan produk sama tidak sama-sama mengklaim jatah yang sama.
        _terpakai: dict[int, float] = {}

        reversed_count = 0
        for produk, qty, lot_key, _marker, _id_racik in jobs:
            detail = _marker  # penanda void_reverse_stok (produk maupun racikan)

            # --- Batas per item (task #54) ---
            # Hanya item yang benar-benar DISERAHKAN yang boleh dikembalikan. Item yang
            # masih DIBAYAR (tertunda, belum diambil pasien) stoknya tidak pernah keluar.
            if per_item:
                if _id_racik is None:
                    _jatah = self._qty_produk_diserahkan(
                        transaksi.id_kunjungan, produk.id_produk,
                        id_resep_scope=(None if (_lk is None or _lk["tunggal"]) else _lk["resep"]))
                    _sisa_jatah = _jatah - _terpakai.get(produk.id_produk, 0.0)
                    qty = min(qty, max(_sisa_jatah, 0.0))
                else:
                    from app.db.models.racikan import KunjunganRacikan as _KR
                    _rh = self.db.get(_KR, _id_racik)
                    if _rh is None or _rh.status_item != "DISERAHKAN":
                        qty = 0.0
                if qty <= 1e-6:
                    continue
                if _id_racik is None:
                    _terpakai[produk.id_produk] = _terpakai.get(produk.id_produk, 0.0) + qty
            old_stok = float(produk.stok_terkini or 0)
            new_stok = old_stok + qty
            produk.stok_terkini = new_stok
            detail.void_reverse_stok = True
            # Audit T3-6: buku mutasi — barang kembali ke rak karena VOID
            from app.repositories.inventory_repo import InventoryRepository as _InvR
            from app.db.models._enums import JenisMutasiEnum as _JM
            _InvR(self.db).catat_mutasi_produk(
                id_staf=actor_id_staf, id_produk=produk.id_produk, jenis=_JM.PENYESUAIAN,
                qty_perubahan=qty, stok_akhir=new_stok,
                referensi=f"VOID-TRX-{transaksi.id_transaksi}",
                keterangan="Kembali dari void transaksi")

            # --- Kembalikan ke lot ---
            # H2/P0-1 (AUDIT_SEHATI_2026-07-10): prioritaskan jejak lot ASLI
            # (kunjungan_lot_terpakai, diisi saat serah) → ED asli terjaga & FEFO benar.
            # Fallback: lot pilihan operator (lot_map), lalu 'VOID-RETURN' (legacy/tanpa jejak).
            lot_batch = None
            lot_ed = None
            restored = []
            remaining = qty
            qty_tanpa_jejak = 0.0
            if transaksi.id_kunjungan:
                # Task #54: jejak disaring per ASAL. Tanpa ini, produk yang dijual biasa
                # DAN dipakai sebagai bahan racikan di kunjungan yang sama akan berbagi
                # jejak — void salah satunya memakan jejak milik yang lain, lalu yang
                # lain jatuh ke lot 'VOID-RETURN' tanpa ED. Baris lama (kedua kolom NULL)
                # tetap dapat dibaca keduanya supaya data lama tidak berubah perilakunya.
                from sqlalchemy import and_ as _and, or_ as _or2
                if _id_racik is None:
                    _scope = KunjunganLotTerpakai.id_kunjungan_racikan.is_(None)
                    if _lk is not None and not _lk["tunggal"]:
                        # Audit T3-1: hanya jejak resep transaksi INI (beberapa transaksi di
                        # kunjungan → `_lingkup_void` sudah menolak data lama tanpa penanda).
                        _scope = KunjunganLotTerpakai.id_resep.in_(_lk["resep"])
                else:
                    _scope = _or2(
                        KunjunganLotTerpakai.id_kunjungan_racikan == _id_racik,
                        _and(
                            KunjunganLotTerpakai.id_kunjungan_racikan.is_(None),
                            KunjunganLotTerpakai.id_resep.is_(None),
                        ),
                    )
                jejak_rows = list(self.db.execute(
                    select(KunjunganLotTerpakai).where(
                        KunjunganLotTerpakai.id_kunjungan == transaksi.id_kunjungan,
                        KunjunganLotTerpakai.id_produk == produk.id_produk,
                        KunjunganLotTerpakai.reversed_at.is_(None),
                        _scope,
                    ).order_by(KunjunganLotTerpakai.id_terpakai.desc())  # LIFO
                ).scalars().all())
                for jr in jejak_rows:
                    if remaining <= 1e-6:
                        break
                    take = min(float(jr.qty or 0), remaining)
                    if take <= 0:
                        continue
                    lot_asli = self.db.get(StokLot, jr.id_lot)
                    if lot_asli is None:
                        continue
                    lot_asli.qty_sisa = float(lot_asli.qty_sisa or 0) + take
                    if lot_asli.status == "HABIS":
                        lot_asli.status = "AKTIF"
                    jr.reversed_at = self._now_utc7().replace(tzinfo=None)
                    remaining -= take
                    restored.append(f"lot#{lot_asli.id_lot}(batch {lot_asli.batch_no or '-'}) +{take:g}")

            if restored and remaining <= 1e-6:
                # Sepenuhnya dipulihkan ke lot asli.
                lot_batch = "ASLI"
                lot_desc = "; ".join(restored)
            elif per_item:
                # TEMUAN 30 — JANGAN membuatkan lot untuk qty yang tidak punya jejak.
                #
                # Di skema per-item, `serahkan_obat` SELALU menulis jejak
                # `kunjungan_lot_terpakai` untuk setiap lot yang benar-benar dipotong
                # (`apotek_service._rekam_lot_terpakai`). Jadi qty tanpa jejak di sini
                # bukan berarti "jejaknya belum ada", melainkan "lotnya TIDAK PERNAH
                # keluar": penyerahan tetap berhasil walau stok kurang, karena stok
                # minus memang sengaja diizinkan (`apotek_repo.py:193`).
                #
                # Membuatkan lot 'VOID-RETURN' untuk qty itu memasukkan barang yang tak
                # pernah ada ke rak, dan FEFO akan membagikannya ke pasien berikutnya.
                # `DISERAHKAN` tidak boleh dipakai sebagai bukti bahwa lot sudah keluar
                # — jejak lot yang jadi buktinya.
                #
                # `stok_terkini` tetap dikembalikan PENUH (di atas), karena serah juga
                # memotongnya penuh. Dengan begitu cache dan SUM(qty_sisa) sama-sama
                # kembali ke keadaan sebelum serah — persis, termasuk pada serah yang
                # hanya sebagian terpenuhi lot.
                qty_tanpa_jejak = remaining if restored else qty
                lot_batch = "TANPA-JEJAK"
                lot_desc = (
                    (("; ".join(restored) + "; ") if restored else "")
                    + f"{qty_tanpa_jejak:g} TANPA jejak lot \u2014 tidak dibuatkan lot "
                    "retur (lot aslinya tidak pernah keluar saat serah)"
                )
            else:
                # Sisa (atau seluruhnya bila tak ada jejak) → jalur lama: lot pilihan / VOID-RETURN.
                sisa_qty = remaining if restored else qty
                id_lot_sel = lot_map.get(lot_key)
                lot = self.db.get(StokLot, id_lot_sel) if id_lot_sel else None
                _prefix = ("; ".join(restored) + "; ") if restored else ""
                if lot is not None and lot.tipe_item == "PRODUK" and lot.id_produk == produk.id_produk:
                    lot.qty_sisa = float(lot.qty_sisa or 0) + sisa_qty
                    if lot.status == "HABIS":
                        lot.status = "AKTIF"
                    lot_batch, lot_ed = lot.batch_no, (lot.tgl_ed.isoformat() if lot.tgl_ed else None)
                    lot_desc = _prefix + f"lot #{lot.id_lot} batch {lot.batch_no or '-'}"
                else:
                    new_lot = StokLot(
                        tipe_item="PRODUK", id_produk=produk.id_produk, lokasi="RETAIL",
                        batch_no="VOID-RETURN", tgl_ed=None, qty_masuk=sisa_qty, qty_sisa=sisa_qty,
                        status="AKTIF", tgl_masuk=_date.today(),
                    )
                    self.db.add(new_lot)
                    self.db.flush()
                    lot_batch = "VOID-RETURN"
                    lot_desc = _prefix + f"lot retur baru #{new_lot.id_lot}"

            self.audit.log(
                aksi="VOID_REVERSE_STOK",
                id_staf=actor_id_staf,
                tabel_target="master_produk",
                id_target=produk.id_produk,
                data_lama={"stok_terkini": old_stok},
                data_baru={
                    "stok_terkini": new_stok,
                    "qty_dikembalikan": qty,
                    "trigger": f"void_transaksi #{transaksi.id_transaksi}",
                    "lot_tujuan": lot_desc,
                    "batch_no": lot_batch,
                    "tgl_ed": lot_ed,
                    # Temuan 30: terbaca sebagai angka supaya bisa dicari lewat SQL,
                    # bukan hanya terbaca manusia di `lot_tujuan`.
                    "qty_tanpa_jejak": qty_tanpa_jejak,
                },
                request=request,
            )
            reversed_count += 1
        self.db.flush()
        return reversed_count

    def _cascade_void_kunjungan(self, trx, actor_id_staf, request):
        """DEC-063 Phase 1 (10 Juni 2026): cascade efek void transaksi ke kunjungan.

        Logika: void transaksi = pasien batal membeli item transaksi INI. Maka:
        - resep/racikan DIBAYAR milik transaksi ini (`_lingkup_void`) -> BATAL (apoteker
          tidak perlu serahkan);
        - status kunjungan DIHITUNG ULANG dari isinya (`hitung_ulang_status`, bayar dulu
          T1-4) — bukan lagi dipaksa COMPLETED. Hasilnya bisa MUNDUR: susulan yang belum
          ditagih → ANTRI_BAYAR, tindakan yang belum dikerjakan → ANTRI_TREATMENT, obat
          transaksi lain yang belum diserahkan → ANTRI_OBAT.

        ⚠ Nama lama dipertahankan karena tersimpan di data: kunci kembalian
        `kunjungan_advanced` dan aksi audit `VOID_KUNJUNGAN_FORWARD` kini berarti "status
        kunjungan BERUBAH karena void" (arah mana pun), bukan "dimajukan". Laporan/audit yang
        membaca aksi itu jangan menyimpulkan arah dari namanya — baca data_lama/data_baru.

        Return dict {cancelled_resep, cancelled_racikan, kunjungan_advanced: bool}.
        """
        from app.db.models import KunjunganResep, Kunjungan, StatusItemResepEnum
        from sqlalchemy import select

        id_kunjungan = trx.id_kunjungan
        lingkup = self._lingkup_void(trx)   # Audit T2-2: hanya item transaksi INI

        # Cascade 1: resep DIBAYAR -> BATAL
        stmt = select(KunjunganResep).where(
            KunjunganResep.id_kunjungan == id_kunjungan,
            KunjunganResep.status_item == StatusItemResepEnum.DIBAYAR,
            KunjunganResep.id_resep.in_(lingkup["resep"]),
        )
        resep_list = list(self.db.execute(stmt).scalars().all())
        cancelled_resep = 0
        for resep in resep_list:
            old_status = resep.status_item
            old_str = old_status.value if hasattr(old_status, "value") else str(old_status)
            resep.status_item = StatusItemResepEnum.BATAL
            resep.id_staf_void = actor_id_staf
            resep.waktu_void = datetime.now()  # A4: WIB (match void_at)
            self.audit.log(
                aksi="VOID_RESEP_CASCADE",
                id_staf=actor_id_staf,
                tabel_target="kunjungan_resep",
                id_target=resep.id_resep,
                data_lama={"status_item": old_str},
                data_baru={
                    "status_item": "BATAL",
                    "trigger": f"void_transaksi_kunjungan_{id_kunjungan}",
                },
                request=request,
            )
            cancelled_resep += 1

        # Cascade 1b: racikan DIBAYAR -> BATAL (sejajar resep; apoteker tidak perlu meracik)
        from app.db.models.racikan import KunjunganRacikan as _KRC
        cancelled_racikan = 0
        for _rc in self.db.execute(
            select(_KRC).where(
                _KRC.id_kunjungan == id_kunjungan,
                _KRC.status_item == "DIBAYAR",
                _KRC.id_kunjungan_racikan.in_(lingkup["racikan"]),
            )
        ).scalars().all():
            _old = _rc.status_item
            _rc.status_item = "BATAL"
            self.audit.log(
                aksi="VOID_RACIKAN_CASCADE",
                id_staf=actor_id_staf,
                tabel_target="kunjungan_racikan",
                id_target=_rc.id_kunjungan_racikan,
                data_lama={"status_item": _old},
                data_baru={
                    "status_item": "BATAL",
                    "trigger": f"void_transaksi_kunjungan_{id_kunjungan}",
                },
                request=request,
            )
            cancelled_racikan += 1

        # Cascade 2: status kunjungan dari isinya (bayar dulu T1-4).
        # Dulu: ANTRI_OBAT/ANTRI_BAYAR → COMPLETED kecuali masih ada obat transaksi LAIN
        # yang lunas belum diserahkan (Audit T2-2). Itu kini (O) di fungsi bersama.
        # Void satu-satunya transaksi hari ini tetap berakhir COMPLETED: transaksi VOID
        # dihitung "sudah ditangani kasir" oleh (K), jadi kunjungan tidak balik ke kasir.
        # Yang berubah: susulan yang belum ditagih (resep PENDING, tindakan SELESAI tanpa
        # id_transaksi) kini menahan kunjungan di ANTRI_BAYAR, bukan ikut ditutup.
        kunjungan = self.db.get(Kunjungan, id_kunjungan)
        kunjungan_advanced = False
        self.db.flush()
        if kunjungan:
            from app.services._status_kunjungan import hitung_ulang_status
            old_status = kunjungan.status_antrian
            new_status = hitung_ulang_status(self.db, id_kunjungan)
            if new_status != old_status:
                self.audit.log(
                    aksi="VOID_KUNJUNGAN_FORWARD",
                    id_staf=actor_id_staf,
                    tabel_target="kunjungan",
                    id_target=id_kunjungan,
                    data_lama={"status_antrian": old_status},
                    data_baru={"status_antrian": new_status, "trigger": "void_transaksi"},
                    request=request,
                )
                kunjungan_advanced = True

        return {
            "cancelled_resep": cancelled_resep,
            "cancelled_racikan": cancelled_racikan,
            "kunjungan_advanced": kunjungan_advanced,
        }

    def _revert_kuota_per_tindakan(self, trx, actor_id_staf, request):
        """Phase 3 (DEC-067 outstanding): saat void transaksi, kembalikan kuota
        member untuk setiap KunjunganTindakan yang pakai benefit (id_kuota_member
        NOT NULL). Call decrement_kuota_terpakai yang sudah tulis audit KUOTA_REVERT
        + floor at 0 secara internal.

        Graceful: kegagalan revert per tindakan TIDAK membatalkan void (best-effort).
        Return jumlah kuota yang berhasil di-revert.

        Bayar dulu T2-4: tindakan yang MASIH HIDUP (PENDING/PROSES — dibayar di muka) TIDAK
        dikembalikan kuotanya. Kuota dipakai saat tindakan DIBUAT (SOAP/upsell), bukan saat
        dibayar; void hanya melepas tindakan itu kembali ke "belum ditagih", tindakannya
        tetap ada dan tetap memegang slotnya. Kalau dikembalikan di sini, Batalkan tindakan
        nanti mengembalikannya LAGI (`_batal_tindakan.kembalikan_kuota` hanya melewati yang
        BATAL) → pasien mendapat slot gratis. BATAL juga dilewati: yang BATAL sudah
        dikembalikan saat dibatalkan (aturan yang sama dengan `_batal_tindakan`).
        """
        from app.db.models import KunjunganTindakan
        from app.db.models._enums import StatusTindakanEnum
        from sqlalchemy import select

        id_kunjungan = trx.id_kunjungan
        stmt = select(KunjunganTindakan).where(
            KunjunganTindakan.id_kunjungan == id_kunjungan,
            KunjunganTindakan.id_kuota_member.isnot(None),
            # Audit T2-2: hanya tindakan yang ditagih transaksi INI
            KunjunganTindakan.id_kunjungan_tindakan.in_(self._lingkup_void(trx)["tindakan"]),
            KunjunganTindakan.status_tindakan.notin_(
                self._TINDAKAN_HIDUP + (StatusTindakanEnum.BATAL,)),
        )
        tindakan_list = list(self.db.execute(stmt).scalars().all())
        reverted = 0
        for tindakan in tindakan_list:
            try:
                ok = self.membership.decrement_kuota_terpakai(
                    tindakan.id_kuota_member,
                    actor_id_staf=actor_id_staf,
                    id_kunjungan=id_kunjungan,
                    id_tindakan=tindakan.id_kunjungan_tindakan,
                    request=request,
                )
                if ok:
                    reverted += 1
            except Exception:
                # Best-effort: void tetap lanjut meski 1 revert gagal.
                pass
        return reverted

    def _lepas_tindakan_hidup(self, trx, actor_id_staf, request) -> int:
        """Bayar dulu T2-4: tindakan yang DITAGIH transaksi ini tapi BELUM dikerjakan
        (PENDING/PROSES, dibayar di muka) → `id_transaksi = NULL`, kembali "belum ditagih".

        Void = pasien batal membeli item transaksi INI; tindakannya sendiri belum batal.
        Tanpa langkah ini `id_transaksi` tetap menempel ke transaksi VOID dan tindakannya
        BUNTU: tak bisa ditagih lagi (`tindakan_bisa_ditagih` = tanpa id_transaksi), tak bisa
        dibatalkan (`batalkan_tindakan` menolak yang ber-id_transaksi), dan menahan kunjungan
        di ruang tindakan / tutup kasir. Sesudah dilepas: tagihan memuatnya lagi, dan bila
        pasien menolaknya, Batalkan mengembalikan kuota/series TEPAT sekali (void tidak
        mengembalikannya — `_revert_kuota_per_tindakan`, `_cancel_series_sesi_pending`).

        Hanya baris yang penandanya = transaksi ini (Ruling 13). Baris lama yang hanya
        tertaut lewat snapshot sudah ber-id_transaksi NULL. Kunci: dipanggil sesudah
        `_kunci_untuk_void` (trx → kunjungan), lalu baris tindakan FOR UPDATE — urutan
        Ruling P4; status dibaca TERBARU (perawat bisa baru saja menekan Mulai).
        Return jumlah tindakan yang dilepas. FLUSH, pemanggil commit.
        """
        from sqlalchemy import select
        from app.db.models import KunjunganTindakan

        ids = self._lingkup_void(trx)["tindakan"]
        if not ids:
            return 0
        rows = self.db.execute(
            select(KunjunganTindakan)
            .where(KunjunganTindakan.id_kunjungan_tindakan.in_(ids))
            .where(KunjunganTindakan.id_transaksi == trx.id_transaksi)
            .where(KunjunganTindakan.status_tindakan.in_(self._TINDAKAN_HIDUP))
            .with_for_update().execution_options(populate_existing=True)
        ).scalars().all()
        for kt in rows:
            kt.id_transaksi = None
            self.audit.log(
                aksi="VOID_TINDAKAN_DILEPAS",
                id_staf=actor_id_staf,
                tabel_target="kunjungan_tindakan",
                id_target=kt.id_kunjungan_tindakan,
                data_lama={"id_transaksi": trx.id_transaksi,
                           "status_tindakan": getattr(kt.status_tindakan, "value",
                                                      kt.status_tindakan)},
                data_baru={"id_transaksi": None, "trigger": "void_transaksi",
                           "kuota_dikembalikan": False},
                request=request,
            )
        self.db.flush()
        return len(rows)

    def _cascade_void_bersama(self, trx, actor_id_staf, request) -> dict:
        """SATU urutan cascade untuk KEDUA jalur void (`void_transaksi` &
        `force_past_day_void`) — CLAUDE.md §4.1: jalur void ada dua, dan `force_past_day_void`
        pernah kehilangan tiga langkah rollback karena salinan. Langkah baru masuk DI SINI.

        Urutan: series & kuota (keduanya melewati tindakan hidup) → lepas tindakan hidup →
        resep/racikan + status kunjungan. Status dihitung TERAKHIR supaya tindakan yang baru
        dilepas terbaca "belum ditagih" oleh `hitung_ulang_status`.
        """
        if not trx.id_kunjungan:
            return {"cancelled_series": 0, "kuota_reverted": 0, "tindakan_dilepas": 0,
                    "cascade_info": {"cancelled_resep": 0, "kunjungan_advanced": False}}
        # Audit T2-2: semua cascade PER TRANSAKSI (_lingkup_void), bukan per kunjungan.
        cancelled_series = self._cancel_series_sesi_pending(trx, actor_id_staf, request)
        kuota_reverted = self._revert_kuota_per_tindakan(trx, actor_id_staf, request)
        tindakan_dilepas = self._lepas_tindakan_hidup(trx, actor_id_staf, request)
        cascade_info = self._cascade_void_kunjungan(trx, actor_id_staf, request)
        return {"cancelled_series": cancelled_series, "kuota_reverted": kuota_reverted,
                "tindakan_dilepas": tindakan_dilepas, "cascade_info": cascade_info}

    def _catat_uang_keluar_void(self, trx, *, actor_id_staf, id_penyetuju, waktu, alasan) -> int:
        """Baris `transaksi_refund` berjenis VOID untuk void HARI LAMPAU — audit K4-1.

        Satu baris per metode bayar asal, totalnya = `total_tagihan` (yang benar-benar
        diterima klinik). Kembalian (bayar lebih) tidak ikut keluar: metode non-TUNAI
        dialokasikan lebih dulu, TUNAI menampung sisanya — kelebihan bayar hanya mungkin di
        tunai. Dibaca semua laporan uang & tutup kasir lewat `_refund_bukuan`, di TANGGAL VOID.
        """
        from sqlalchemy import select
        from app.db.models import TransaksiPembayaran, TransaksiRefund
        sisa = Decimal(str(trx.total_tagihan or 0))
        bayar = self.db.execute(
            select(TransaksiPembayaran)
            .where(TransaksiPembayaran.id_transaksi == trx.id_transaksi)
            .order_by(TransaksiPembayaran.id_pembayaran)
        ).scalars().all()
        bayar = sorted(bayar, key=lambda p: (str(p.metode_bayar or "").upper() == "TUNAI"))
        n = 0
        for p in bayar:
            if sisa <= 0:
                break
            nilai = min(Decimal(str(p.nominal or 0)), sisa)
            if nilai <= 0:
                continue
            self.db.add(TransaksiRefund(
                id_transaksi=trx.id_transaksi, tgl_refund=waktu, nilai_refund=nilai,
                metode_refund=str(p.metode_bayar or "TUNAI").upper(),
                alasan=f"Void hari lampau — {alasan}"[:1000],
                id_staf_refund=actor_id_staf, id_staf_otorisasi=id_penyetuju,
                jenis_refund="VOID",
            ))
            sisa -= nilai
            n += 1
        self.db.flush()
        return n

    def _kunci_untuk_void(self, id_transaksi):
        """Kunci transaksi LALU kunjungannya, dengan pembacaan segar — Audit T3-2.

        Dulu void membaca transaksi & status obat tanpa kunci: dua void bersamaan sama-sama
        lolos (komisi & kuota dikembalikan dua kali); void yang berjalan bersama serah obat
        bisa mem-void transaksi yang obatnya baru saja DISERAHKAN — persis yang dicegah
        pagar 2026-10-04. Serah, refund, dan bayar mengunci kunjungan yang sama.

        Audit T4-5 (2026-10-15): transaksi baca ditutup DULU (pola T4-1). Pagar-pagar void
        sesudah kunci — terutama `_pagari_void_sudah_refund` — adalah SELECT biasa yang di
        REPEATABLE-READ membaca potret awal permintaan. Refund obat tertunda yang commit
        sambil void menunggu kunci tak terlihat → void diterima, uang yang sama keluar dua
        kali, dan refund atas transaksi VOID hilang dari hitungan laci (`_refund_bukuan`
        hanya menghitung refund atas transaksi BAYAR). Terbukti dengan dua koneksi.
        ⚠ Jangan sisipkan SELECT biasa di antara commit ini dan kunci transaksi.
        """
        from sqlalchemy import select
        mulai_baca_segar(self.db)   # lihat app/services/_baca_segar.py
        trx = self.db.execute(
            select(TransaksiKasir).where(TransaksiKasir.id_transaksi == id_transaksi)
            .with_for_update().execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if trx is not None and trx.id_kunjungan:
            self.kunjungan_repo.get_by_id_for_update(trx.id_kunjungan)
        return trx

    def _tindakan_selesai_di_transaksi(self, trx) -> list:
        """Tindakan berstatus SELESAI pada kunjungan transaksi ini.

        Dipakai memagari void. Kebijakan dr. Hansen 2026-09-22 untuk komplain PASCA
        TINDAKAN: tidak ada penarikan komisi dokter/perawat, tidak ada pengembalian
        BHP, tidak ada pengembalian kuota, tidak ada pengembalian uang — komplain
        didokumentasikan lewat nomor transaksi dan ditangani Finance sebagai jurnal
        penanganan komplain.

        Masalahnya, `void_transaksi` melakukan PERSIS KEBALIKANNYA: menarik semua
        komisi jadi VOID, mengembalikan kuota membership, membatalkan resep, dan
        mengeluarkan transaksi dari omzet. Jadi void tidak boleh dipakai untuk
        tindakan yang pekerjaannya sudah benar-benar dilakukan.
        """
        from sqlalchemy import select
        from app.db.models import KunjunganTindakan, MasterTreatment, MasterStaf
        from app.db.models._enums import StatusTindakanEnum

        if not trx.id_kunjungan:
            return []
        rows = self.db.execute(
            select(KunjunganTindakan).where(
                KunjunganTindakan.id_kunjungan == trx.id_kunjungan,
                KunjunganTindakan.status_tindakan == StatusTindakanEnum.SELESAI,
                # Audit T2-2: hanya tindakan transaksi INI (dulu tindakan T1 menghalangi
                # void T2 yang hanya berisi obat)
                KunjunganTindakan.id_kunjungan_tindakan.in_(self._lingkup_void(trx)["tindakan"]),
            ).with_for_update()   # Audit T3-2: status TERBARU, bukan potret awal permintaan
        ).scalars().all()
        out = []
        for kt in rows:
            t = self.db.get(MasterTreatment, kt.id_treatment)
            dok = self.db.get(MasterStaf, kt.id_dokter_pelaksana) if kt.id_dokter_pelaksana else None
            per = self.db.get(MasterStaf, kt.id_perawat_pelaksana) if kt.id_perawat_pelaksana else None
            out.append({
                "id": kt.id_kunjungan_tindakan,
                "nama": t.nama_treatment if t else f"treatment #{kt.id_treatment}",
                "dokter": dok.nama_staf if dok else None,
                "perawat": per.nama_staf if per else None,
                "pakai_kuota": kt.id_kuota_member is not None,
            })
        return out

    def _item_diserahkan_di_transaksi(self, trx) -> list:
        """Resep & racikan berstatus DISERAHKAN pada kunjungan transaksi ini.

        Sejajar dengan `_tindakan_selesai_di_transaksi`, untuk alasan yang sama
        persis: barang yang sudah berpindah ke tangan pasien adalah pekerjaan yang
        sudah selesai. Stok sudah dipotong, racikan sudah diracik, dan — berbeda
        dari tindakan — barangnya tidak bisa diambil kembali.
        """
        from sqlalchemy import select
        from app.db.models import KunjunganResep, MasterProduk, StatusItemResepEnum
        from app.db.models.racikan import KunjunganRacikan as _KRC

        if not trx.id_kunjungan:
            return []

        lingkup = self._lingkup_void(trx)   # Audit T2-2: hanya item transaksi INI
        out = []
        for r in self.db.execute(
            select(KunjunganResep).where(
                KunjunganResep.id_kunjungan == trx.id_kunjungan,
                KunjunganResep.status_item == StatusItemResepEnum.DISERAHKAN,
                KunjunganResep.id_resep.in_(lingkup["resep"]),
            ).with_for_update()   # Audit T3-2
        ).scalars().all():
            prod = self.db.get(MasterProduk, r.id_produk)
            out.append({
                "jenis": "Resep",
                "nama": (prod.nama_produk if prod else f"produk #{r.id_produk}"),
            })

        # Racikan: VARCHAR, bukan enum (CLAUDE.md §4.4) — bandingkan string.
        for rc in self.db.execute(
            select(_KRC).where(
                _KRC.id_kunjungan == trx.id_kunjungan,
                _KRC.status_item == "DISERAHKAN",
                _KRC.id_kunjungan_racikan.in_(lingkup["racikan"]),
            ).with_for_update()   # Audit T3-2
        ).scalars().all():
            out.append({"jenis": "Racikan", "nama": rc.nama_snapshot or "racikan"})

        return out

    def _pagari_void_item_diserahkan(self, trx) -> None:
        """Tolak void bila ada resep/racikan yang SUDAH DISERAHKAN ke pasien.

        [Keputusan dr. Hansen 2026-10-04 — Opsi A audit alur uang]

        KENAPA PAGAR INI ADA. Sebelum ini, void DITERIMA walau obat/racikan sudah
        di tangan pasien, dan akibatnya tidak terlihat di mana pun:

          - `_cascade_void_kunjungan` hanya mengubah DIBAYAR -> BATAL. Yang sudah
            DISERAHKAN tidak cocok, jadi statusnya TETAP DISERAHKAN.
          - Laporan omzet mengecualikan transaksi VOID.
          - Laporan racikan / top-produk / apoteker-dispensed menghitung dari
            `status_item='DISERAHKAN'` TANPA melihat status transaksi.

        Hasilnya dua laporan berbeda pendapat tentang uang yang sama, tanpa error
        dan tanpa peringatan. Terbukti 2026-10-04 dengan racikan Rp 225.000 yang
        tetap muncul sebagai omzet apotek padahal transaksinya VOID.
        Rinciannya: `Project_Memory/AUDIT_ALUR_UANG_2026-10-04.md`.

        Aturannya sama dengan pagar tindakan SELESAI (CLAUDE.md §7): void hanya
        untuk yang BELUM selesai dikerjakan. Alasan void TIDAK dibedakan di sini —
        alasan mudah dipilih keliru, dan celah sekecil apa pun mengembalikan
        selisih laporan yang baru saja ditutup.

        ⚠ Ini MEMPERKETAT perilaku kasir: void yang dulu diterima sekarang ditolak.
        Itu disengaja. Yang dulu "berhasil" meninggalkan laporan yang salah.
        """
        diserahkan = self._item_diserahkan_di_transaksi(trx)
        if not diserahkan:
            return
        nama = ", ".join(f"{d['jenis']} {d['nama']}" for d in diserahkan[:3])
        if len(diserahkan) > 3:
            nama += f", +{len(diserahkan) - 3} lainnya"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                # 2026-10-05: sempat menyuruh "pakai jalur retur/refund" saat jalur itu
                # BELUM ADA. Sekarang menunjuk menu retur dari pasien yang sudah dibangun
                # (DESAIN_RETUR_DARI_PASIEN.md).
                f"Transaksi ini tidak bisa di-void: {len(diserahkan)} item SUDAH "
                f"DISERAHKAN ke pasien ({nama}). Void hanya untuk yang belum selesai. "
                "Kalau pasien mengembalikan obatnya, pakai Kasir → Cari Transaksi → "
                "↩ Retur (kembalikan uang atau tukar produk, maks. 7 hari sejak diserahkan)."
            ),
        )

    def _pagari_void_membership_pengganti(self, trx) -> None:
        """Tolak void transaksi yang aktivasinya MENGGANTIKAN membership lain (perpanjangan /
        upgrade yang sudah diaktifkan CS). Audit T4-3, keputusan dr. Hansen 2026-10-15
        (pilihan b): revert hanya membatalkan history baru, membership LAMA yang sudah
        dibayar tidak dipulihkan dan sisa kuotanya ikut mati — pasien jadi REGULAR.
        Aktivasi pertama (tidak menggantikan apa pun) tetap boleh di-void.
        Dipanggil di KEDUA jalur void.
        """
        lama = self.membership.membership_yang_digantikan(trx.id_transaksi)
        if not lama:
            return
        daftar = ", ".join(f"#{h.id_history}" for h in lama[:4])
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Transaksi #{trx.id_transaksi} adalah perpanjangan/upgrade membership yang "
                f"SUDAH diaktifkan dan menggantikan membership lama pasien ({daftar}). Void "
                f"akan menghapus membership lama yang sudah dibayar beserta sisa kuotanya, "
                f"jadi ditolak. Belum ada fitur pembatalan aktivasi — kalau memang harus "
                f"dibatalkan, catat nomor transaksi & history ini dan hubungi Superadmin "
                f"untuk koreksi manual."
            ),
        )

    def _pagari_void_sudah_refund(self, trx) -> None:
        """Tolak void bila transaksi SUDAH punya refund (T32, keputusan dr. Hansen 2026-10-05).

        Sejak T32 refund tidak lagi mengurangi `total_tagihan`; laporan mengurangi
        `transaksi_refund` pada tanggal refund. Void mengecualikan transaksi PENUH dari
        omzet — kalau refund-nya tetap dikurangi, uang yang sama terhitung keluar DUA
        KALI. Dan uangnya memang sudah dikembalikan sebagian ke pasien: transaksinya
        bukan lagi "belum selesai", jadi aturan void (CLAUDE.md §7) tidak berlaku.
        Dipanggil di KEDUA jalur void (`void_transaksi` & `force_past_day_void`).
        """
        rows = daftar_pengembalian(self.db, [trx.id_transaksi]).get(trx.id_transaksi, [])
        if not rows:
            return
        total = sum((r["nilai"] for r in rows), Decimal("0"))
        # Sebut NOMOR-nya (dr. Hansen 2026-10-05): petugas yang ditolak perlu tahu retur/
        # refund mana yang menghalangi, supaya bisa menelusurinya di halaman tagihan.
        # Format ribuan per ANGKA — `.replace(",", ".")` atas seluruh pesan ikut mengubah
        # koma pemisah daftar jadi titik.
        def rp(x):
            return f"Rp {x:,.0f}".replace(",", ".")
        rincian = ", ".join(
            f"{r['nomor_retur'] or 'refund #' + str(r['id_refund'])} "
            f"{rp(r['nilai'])} {r['metode']}" for r in rows[:4]
        ) + (f", +{len(rows) - 4} lainnya" if len(rows) > 4 else "")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Transaksi ini tidak bisa di-void: sudah ada {len(rows)} pengembalian "
                f"(total {rp(total)}) — {rincian}. Uangnya sudah dikembalikan/ditukar; "
                "void akan menghitungnya keluar dua kali. Lihat kotak 'Pengembalian & "
                "retur' di halaman tagihan."
            ),
        )

    def _pagari_void_tindakan_selesai(self, trx, reason_enum) -> None:
        """Tolak void bila ada tindakan yang SUDAH SELESAI dikerjakan — APA PUN alasannya.

        Aturan dr. Hansen (2026-09-22): **void hanya untuk tindakan yang BELUM selesai**
        (mis. salah input sebelum dikerjakan). Begitu penindak menekan Selesai,
        pekerjaannya nyata: bahan sudah terpakai, komisi dokter & perawat sudah layak,
        kuota member sudah terpakai. Void akan menarik semua itu kembali — dan itu
        bukan koreksi, melainkan merugikan orang yang sudah bekerja.

        Alasan void TIDAK dibedakan di sini. Pengecualian untuk "salah input" pernah
        dipertimbangkan dan DITOLAK dr. Hansen: alasan mudah dipilih keliru, dan celah
        sekecil apa pun membuat komisi bisa tertarik diam-diam.

        Komplain pasca tindakan ditangani di luar jalur ini — nomor transaksi dipakai
        sebagai dokumentasi, lalu masuk jurnal penanganan komplain di Finance.
        """
        selesai = self._tindakan_selesai_di_transaksi(trx)
        if not selesai:
            return
        nama = ", ".join(s["nama"] for s in selesai[:3])
        if len(selesai) > 3:
            nama += f", +{len(selesai) - 3} lainnya"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Transaksi ini tidak bisa di-void: {len(selesai)} tindakan SUDAH "
                f"SELESAI dikerjakan ({nama}). Void hanya untuk tindakan yang belum "
                "dikerjakan. Bahan sudah terpakai, komisi dokter & perawat sudah layak, "
                "dan kuota member sudah terpakai — semuanya tidak ditarik kembali. "
                "Untuk komplain, gunakan nomor transaksi ini sebagai dokumentasi dan "
                "tangani lewat jurnal penanganan komplain di Finance."
            ),
        )

    def peringatan_void(self, id_transaksi: int) -> dict:
        """Apa yang akan TERTARIK kalau transaksi ini di-void — untuk ditampilkan
        di layar konfirmasi SEBELUM petugas menekan void.

        Tanpa ini, menarik komisi dokter yang sudah bekerja terjadi tanpa ada yang
        melihatnya — pola kegagalan yang sama dengan centang reverse stok.
        """
        trx = self.db.get(TransaksiKasir, id_transaksi)
        if trx is None:
            return {"ada_tindakan_selesai": False, "tindakan": []}
        selesai = self._tindakan_selesai_di_transaksi(trx)
        return {
            "ada_tindakan_selesai": bool(selesai),
            "tindakan": selesai,
            "pakai_kuota": any(s["pakai_kuota"] for s in selesai),
        }

    def void_transaksi(
        self,
        id_transaksi,
        reason_code,
        reason_note,
        items_reverse_stok,
        actor_id_staf,
        request=None,
        lot_map=None,
    ):
        """Kasir void transaksi same-day. Phase 1 self-acc + audit log."""
        try:
            reason_enum = VoidReasonEnum(reason_code)
        except ValueError:
            raise HTTPException(400, f"Reason code '{reason_code}' tidak valid")
        self._validate_reason_note(reason_enum, reason_note)

        trx = self._kunci_untuk_void(id_transaksi)   # Audit T3-2
        if trx is None:
            raise HTTPException(404, f"Transaksi #{id_transaksi} tidak ditemukan")
        if trx.status_transaksi == StatusTransaksiEnum.VOID.value:
            raise HTTPException(400, "Sudah ter-void sebelumnya")
        if trx.status_transaksi != StatusTransaksiEnum.BAYAR.value:
            raise HTTPException(400, f"Hanya status BAYAR. Status: {trx.status_transaksi}")
        self._pagari_void_tindakan_selesai(trx, reason_enum)
        self._pagari_void_item_diserahkan(trx)
        self._pagari_void_sudah_refund(trx)
        self._pagari_void_membership_pengganti(trx)

        now = self._now_utc7()
        trx_dt = trx.waktu_bayar
        if trx_dt is None:
            raise HTTPException(400, "Transaksi tidak punya waktu_bayar")
        if not self._is_same_calendar_day_utc7(trx_dt, now):
            raise HTTPException(
                400,
                f"Transaksi sudah lewat tengah malam (waktu bayar: {trx_dt}). "
                f"Hubungi Admin/Owner untuk Force Past-Day Void."
            )

        try:
            now_naive = now.replace(tzinfo=None)
            data_lama = {
                "status_transaksi": trx.status_transaksi,
                "total_tagihan": float(trx.total_tagihan),
                "waktu_bayar": trx_dt.isoformat() if trx_dt else None,
            }
            trx.status_transaksi = StatusTransaksiEnum.VOID.value
            trx.void_at = now_naive
            trx.void_by_id_staf = actor_id_staf
            trx.void_reason_code = reason_enum.value
            trx.void_reason_note = reason_note.strip()
            trx.void_approved_by_id_staf = actor_id_staf
            trx.void_approved_at = now_naive
            trx.void_approval_method = VoidApprovalMethodEnum.SELF.value
            trx.late_void = False

            reversed_count = self._reverse_stok_per_item(trx, items_reverse_stok, actor_id_staf, request, lot_map=lot_map)
            # Bayar dulu T2-4: satu helper untuk KEDUA jalur void (series, kuota, lepas
            # tindakan prabayar, resep/racikan, status kunjungan).
            _cv = self._cascade_void_bersama(trx, actor_id_staf, request)
            cancelled_series, kuota_reverted = _cv["cancelled_series"], _cv["kuota_reverted"]
            tindakan_dilepas = _cv["tindakan_dilepas"]

            # #362E - Revert membership history kalau transaksi mengandung aktivasi.
            # ACTIVE (flow lama) -> PENDING; PAID (M2, transaksi MEMBERSHIP) -> PENDING.
            reverted_mship_history = self.membership.revert_active_to_pending(
                id_transaksi=trx.id_transaksi,
                actor_id_staf=actor_id_staf,
                request=request,
            )
            if reverted_mship_history is None:
                reverted_mship_history = self.membership.revert_paid_to_pending(
                    id_transaksi=trx.id_transaksi,
                    actor_id_staf=actor_id_staf,
                    request=request,
                )

            self.audit.log(
                aksi="VOID_TRANSAKSI",
                id_staf=actor_id_staf,
                tabel_target="transaksi_kasir",
                id_target=trx.id_transaksi,
                data_lama=data_lama,
                data_baru={
                    "status_transaksi": "VOID",
                    "void_reason_code": reason_enum.value,
                    "void_reason_note": reason_note.strip(),
                    "void_approval_method": "SELF",
                    "items_reverse_count": reversed_count,
                    "series_cancelled_count": cancelled_series,
                    "kuota_reverted_count": kuota_reverted,
                    "tindakan_dilepas_count": tindakan_dilepas,
                    "late_void": False,
                },
                request=request,
            )
            # K-L2: void baris komisi terkait transaksi ini.
            KomisiService(self.db).void_komisi_transaksi(
                id_transaksi=trx.id_transaksi, actor_id_staf=actor_id_staf, request=request,
            )
            self.db.commit()
            self.db.refresh(trx)
            return {
                "status": "success",
                "id_transaksi": trx.id_transaksi,
                "void_at": now_naive.isoformat(),
                "reason_code": reason_enum.value,
                "items_reverse_stok_count": reversed_count,
                "series_cancelled_count": cancelled_series,
                "kuota_reverted_count": kuota_reverted,
                "tindakan_dilepas_count": tindakan_dilepas,
                "message": f"Transaksi #{id_transaksi} berhasil di-void.",
            }
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal void: {e!s}")

    def force_past_day_void(
        self,
        id_transaksi,
        reason_code,
        reason_note,
        items_reverse_stok,
        actor_id_staf,
        actor_role,
        request=None,
        id_staf_otorisasi=None,
        pin_otorisasi=None,
    ):
        """Admin/Superadmin/Owner force past-day void.
        Limit: Admin=3 hari, Superadmin/Owner=7 hari.

        Void HARI LAMPAU (days_past > 0) = UANG KELUAR di tanggal void (keputusan dr. Hansen
        2026-10-15/16, audit K4-1): wajib PIN penyetuju ≠ pemroses (pagar T32 dipakai ulang),
        lalu `_catat_uang_keluar_void` menulis baris `transaksi_refund` berjenis VOID.
        Omzet hari asal TIDAK berubah (`_refund_bukuan.terhitung_omzet`). Override di hari
        yang sama (days_past == 0) tetap seperti void biasa: tanpa PIN, tanpa uang keluar.
        """
        if actor_role not in self._MAX_PAST_DAYS_BY_ROLE:
            raise HTTPException(403, "Role tidak punya wewenang force past-day void")
        max_days = self._MAX_PAST_DAYS_BY_ROLE[actor_role]

        try:
            reason_enum = VoidReasonEnum(reason_code)
        except ValueError:
            raise HTTPException(400, f"Reason code '{reason_code}' tidak valid")
        self._validate_reason_note(reason_enum, reason_note)

        trx = self._kunci_untuk_void(id_transaksi)   # Audit T3-2
        if trx is None:
            raise HTTPException(404, f"Transaksi #{id_transaksi} tidak ditemukan")
        if trx.status_transaksi == StatusTransaksiEnum.VOID.value:
            raise HTTPException(400, "Sudah ter-void")
        if trx.status_transaksi != StatusTransaksiEnum.BAYAR.value:
            raise HTTPException(400, f"Hanya status BAYAR")
        # Pagar yang sama berlaku di jalur past-day — justru di sinilah
        # REFUND_PASCA_TINDAKAN paling mungkin dipakai (batasnya 10 hari).
        self._pagari_void_tindakan_selesai(trx, reason_enum)
        self._pagari_void_item_diserahkan(trx)
        self._pagari_void_sudah_refund(trx)
        self._pagari_void_membership_pengganti(trx)

        now = self._now_utc7()
        trx_dt = trx.waktu_bayar
        if trx_dt is None:
            raise HTTPException(400, "Transaksi tidak punya waktu_bayar")
        days_past = self._days_past(trx_dt, now)
        if days_past < 0:
            raise HTTPException(400, "waktu_bayar di masa depan — data corrupt")
        if days_past > max_days:
            raise HTTPException(
                400,
                f"Force past-day void max {max_days} hari untuk role ini. "
                f"Transaksi sudah {days_past} hari lalu."
            )
        id_penyetuju = None
        if days_past > 0:
            id_penyetuju = self._otorisasi_refund_lampau(
                trx=trx, label=f"#{trx.id_transaksi}", actor_id_staf=actor_id_staf,
                id_staf_otorisasi=id_staf_otorisasi, pin_otorisasi=pin_otorisasi,
                request=request, aksi_tolak="VOID_LAMPAU_DITOLAK_PIN",
                alasan_perlu=(f"Transaksi #{trx.id_transaksi} dibayar "
                              f"{trx_dt:%d/%m/%Y} (hari lampau). Void hari lampau = uang "
                              f"keluar hari ini, jadi"),
            )

        try:
            now_naive = now.replace(tzinfo=None)
            data_lama = {
                "status_transaksi": trx.status_transaksi,
                "total_tagihan": float(trx.total_tagihan),
                "waktu_bayar": trx_dt.isoformat() if trx_dt else None,
                "days_past": days_past,
            }
            trx.status_transaksi = StatusTransaksiEnum.VOID.value
            trx.void_at = now_naive
            trx.void_by_id_staf = actor_id_staf
            trx.void_reason_code = reason_enum.value
            trx.void_reason_note = reason_note.strip()
            trx.void_approved_by_id_staf = id_penyetuju or actor_id_staf
            trx.void_approved_at = now_naive
            trx.void_approval_method = (VoidApprovalMethodEnum.PIN.value if id_penyetuju
                                        else VoidApprovalMethodEnum.SELF.value)
            # late_void flag: TRUE hanya kalau force void dilakukan past-day (days_past > 0).
            # Day 0 via Admin/Owner override tetap late_void=False (masih dalam calendar day).
            # ⚠ Sejak K4-1 flag ini MENENTUKAN UANG: transaksi late_void tetap dihitung di omzet
            # hari asal (`terhitung_omzet`) — jangan diubah tanpa baris uang keluarnya.
            trx.late_void = days_past > 0
            n_uang_keluar = 0
            if trx.late_void:
                n_uang_keluar = self._catat_uang_keluar_void(
                    trx, actor_id_staf=actor_id_staf, id_penyetuju=id_penyetuju,
                    waktu=now_naive, alasan=f"{reason_enum.value}: {reason_note.strip()}")

            reversed_count = self._reverse_stok_per_item(trx, items_reverse_stok, actor_id_staf, request)
            # Bayar dulu T2-4: helper yang SAMA dengan void_transaksi (CLAUDE.md §4.1).
            _cv = self._cascade_void_bersama(trx, actor_id_staf, request)
            cancelled_series, kuota_reverted = _cv["cancelled_series"], _cv["kuota_reverted"]
            tindakan_dilepas = _cv["tindakan_dilepas"]

            # #362E - Revert membership history kalau transaksi mengandung aktivasi.
            # ACTIVE (flow lama) -> PENDING; PAID (M2, transaksi MEMBERSHIP) -> PENDING.
            #
            # ⚠ DITAMBAHKAN 2026-10-04 — dulu HILANG di jalur ini saja.
            # `force_past_day_void` ternyata salinan `void_transaksi` yang kehilangan
            # TIGA langkah pengembalian, dan ini dua di antaranya. Akibat terburuknya
            # bukan di transaksinya, melainkan MENEMPEL KE PASIEN: membership yang sudah
            # ACTIVE tetap ACTIVE, `pasien.tipe_membership` tetap VVIP, dan diskonnya
            # terus berlaku di SETIAP kunjungan berikutnya — atas pembayaran yang
            # sudah di-VOID. Terbukti dengan menjalankannya; lihat
            # `Project_Memory/AUDIT_ALUR_UANG_2026-10-04.md` Temuan 5.
            #
            # Urutannya sama dengan void_transaksi: ACTIVE dulu, baru PAID — hanya satu
            # yang akan cocok untuk satu transaksi.
            reverted_mship_history = self.membership.revert_active_to_pending(
                id_transaksi=trx.id_transaksi,
                actor_id_staf=actor_id_staf,
                request=request,
            )
            if reverted_mship_history is None:
                reverted_mship_history = self.membership.revert_paid_to_pending(
                    id_transaksi=trx.id_transaksi,
                    actor_id_staf=actor_id_staf,
                    request=request,
                )

            self.audit.log(
                aksi="VOID_TRANSAKSI_FORCE_PAST_DAY",
                id_staf=actor_id_staf,
                tabel_target="transaksi_kasir",
                id_target=trx.id_transaksi,
                data_lama=data_lama,
                data_baru={
                    "status_transaksi": "VOID",
                    "void_reason_code": reason_enum.value,
                    "void_reason_note": reason_note.strip(),
                    "items_reverse_count": reversed_count,
                    "series_cancelled_count": cancelled_series,
                    "kuota_reverted_count": kuota_reverted,
                    "tindakan_dilepas_count": tindakan_dilepas,
                    "late_void": trx.late_void,       # dulu selalu True, juga untuk hari 0
                    "days_past": days_past,
                    "id_penyetuju": id_penyetuju,
                    "baris_uang_keluar": n_uang_keluar,
                    "actor_role": actor_role.value if hasattr(actor_role, "value") else str(actor_role),
                    # Ditambahkan bersama perbaikan 3 langkah yang hilang: tanpa angka
                    # ini, jejak audit tidak bisa membuktikan rollback benar terjadi.
                    "membership_history_reverted": reverted_mship_history,
                },
                request=request,
            )
            # K-L2: void baris komisi terkait transaksi ini.
            #
            # ⚠ DITAMBAHKAN 2026-10-04 — langkah ketiga yang hilang di jalur ini.
            # Tanpa ini staf tetap menerima komisi atas transaksi yang sudah
            # dibatalkan dan sudah dikeluarkan dari omzet.
            #
            # CATATAN TERBUKA (backlog F2): kalau periode payroll untuk hari itu SUDAH
            # DITUTUP dan komisinya sudah dibayar, penarikan ini terjadi SURUT. Itu
            # persoalan nyata — tapi berlaku untuk KEDUA jalur void, bukan alasan
            # membiarkan jalur ini pincang. Penanganannya menunggu konsep "periode
            # payroll ditutup" yang belum ada (F2).
            KomisiService(self.db).void_komisi_transaksi(
                id_transaksi=trx.id_transaksi, actor_id_staf=actor_id_staf, request=request,
            )
            self.db.commit()
            self.db.refresh(trx)
            return {
                "status": "success",
                "id_transaksi": trx.id_transaksi,
                "void_at": now_naive.isoformat(),
                "days_past": days_past,
                "late_void": trx.late_void,
                "reason_code": reason_enum.value,
                "items_reverse_stok_count": reversed_count,
                "series_cancelled_count": cancelled_series,
                "kuota_reverted_count": kuota_reverted,
                "tindakan_dilepas_count": tindakan_dilepas,
                "message": f"Transaksi #{id_transaksi} force past-day void ({days_past}d).",
            }
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal force past-day void: {e!s}")

__all__ = ["KasirService"]
