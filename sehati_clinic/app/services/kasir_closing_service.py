"""
KasirClosingService — Buka Kasir / Tutup Kasir / Rekonsiliasi (Kasir-1).

Alur (DEC-074 era, keputusan dr. Hansen 2026-06-27):
1. buka_kasir(id_staf_kasir, modal_awal): buat sesi `kasir_closing` status OPEN,
   set shift_mulai = anchor agregasi + modal_awal (kas laci). Cegah double-open.
2. get_closing_preview(id_staf_kasir): hitung EXPECTED per metode sejak shift_mulai,
   EXCLUDE transaksi VOID (status_transaksi='BAYAR' saja — perbaiki gap rekap lama).
   TUNAI: expected_laci = modal_awal + penjualan_tunai.
3. tutup_kasir(...): terima counted fisik per metode, hitung selisih = counted-expected,
   simpan closing record (detail per metode = JSON), status -> CLOSED.

Metode kanonik: TUNAI / QRIS / DEBIT / KREDIT / TRANSFER.
Anchor expected = kasir_closing.shift_mulai (independen dari login),
basis waktu = datetime.now() (WIB, konsisten dengan rekap_shift / waktu_mulai_shift; A4/DEC-052).

Audit: BUKA_KASIR, TUTUP_KASIR. Tidak ada PDF disimpan (slip Z-report transien).
"""

from datetime import datetime, time as _time
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import KasirClosing, TransaksiKasir, TransaksiPembayaran
from app.repositories.staf_repo import StafRepository
from app.services.audit_service import AuditService


# Urutan kanonik untuk tampilan + agregasi
METODE_KANONIK = ["TUNAI", "QRIS", "DEBIT", "KREDIT", "TRANSFER"]


class KasirClosingService:
    def __init__(self, db: Session):
        self.db = db
        self.staf_repo = StafRepository(db)
        self.audit = AuditService(db)

    # =========================================================================
    # HELPERS
    # =========================================================================
    # -------------------------------------------------------------------------
    # T28 (keputusan dr. Hansen 2026-10-05, DESAIN_T28_TUTUP_KASIR_PER_TANGGAL.md):
    # klinik punya SATU laci dan SATU shift per hari. Sesi kasir kini milik LACI,
    # bukan orang, dan expected-nya = SEMUA uang di TANGGAL sesi.
    #
    # Dulu expected = pembayaran oleh `id_staf_kasir` pemilik sesi, sejak `shift_mulai`.
    # Dua celah, keduanya membuat uang yang ADA di laci tidak ada di hitungan:
    #   - jam : bayar sebelum "Buka Kasir" ditekan / sesudah tutup (Temuan 28);
    #   - orang: bayar yang diproses staf lain (FO, Owner, Admin) yang tak membuka
    #            sesi sendiri — di DB dev 25 dari 28 transaksi diproses bukan oleh kasir.
    # `id_staf_kasir` di baris sesi kini berarti "yang MEMBUKA laci", bukan pemilik uang.
    # -------------------------------------------------------------------------
    def get_open_session(self, id_staf_kasir: Optional[int] = None) -> Optional[KasirClosing]:
        """Sesi laci yang masih OPEN (paling baru), siapa pun yang membukanya.

        `id_staf_kasir` diabaikan sejak T28 — dipertahankan agar pemanggil lama tidak
        patah. Satu laci = satu sesi terbuka.
        """
        stmt = (
            select(KasirClosing)
            .where(KasirClosing.status == "OPEN")
            .order_by(KasirClosing.id_closing.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def _rentang_tanggal(sesi: KasirClosing) -> tuple:
        """[awal, akhir] hari kalender sesi — tanggal = DATE(shift_mulai)."""
        tgl = sesi.shift_mulai.date()
        return datetime.combine(tgl, _time.min), datetime.combine(tgl, _time.max)

    def _penjualan_per_metode(self, sesi: KasirClosing) -> dict:
        """Uang SISTEM per metode di TANGGAL sesi, siapa pun pemrosesnya. EXCLUDE VOID.

        Refund dikurangkan menurut tgl_refund lewat `_refund_bukuan` — definisi yang
        sama dengan laporan omzet sejak T32, jadi tutup kasir dan laporan tidak bisa
        berbeda pendapat tentang refund yang sama. (Task #54-F: tanpa pengurangan ini,
        tutup kasir selisih sebesar refund dan petugas yang disalahkan.)
        Return dict {METODE: Decimal}.
        """
        from app.services import _refund_bukuan as _rb
        awal, akhir = self._rentang_tanggal(sesi)
        stmt = (
            select(TransaksiPembayaran.metode_bayar, func.sum(TransaksiPembayaran.nominal))
            .join(TransaksiKasir, TransaksiPembayaran.id_transaksi == TransaksiKasir.id_transaksi)
            .where(TransaksiKasir.waktu_bayar >= awal)
            .where(TransaksiKasir.waktu_bayar <= akhir)
            .where(TransaksiKasir.status_transaksi == "BAYAR")
            .group_by(TransaksiPembayaran.metode_bayar)
        )
        result = {m: Decimal("0") for m in METODE_KANONIK}
        for metode, total in self.db.execute(stmt).all():
            key = (metode or "").upper()
            result[key] = result.get(key, Decimal("0")) + Decimal(str(total or 0))
        for key, nilai in _rb.refund_per_metode(self.db, awal, akhir).items():
            result[key] = result.get(key, Decimal("0")) - nilai
        return result

    def _rincian_per_petugas(self, sesi: KasirClosing) -> list:
        """Siapa memproses berapa di tanggal sesi — laci satu, tapi selisih tetap bisa
        ditelusuri ke orang. Refund diatribusikan ke PELAKU refund."""
        from app.db.models import MasterStaf
        from app.services import _refund_bukuan as _rb
        awal, akhir = self._rentang_tanggal(sesi)
        jual = dict(self.db.execute(
            select(TransaksiKasir.id_staf_kasir, func.sum(TransaksiPembayaran.nominal))
            .join(TransaksiPembayaran, TransaksiPembayaran.id_transaksi == TransaksiKasir.id_transaksi)
            .where(TransaksiKasir.waktu_bayar >= awal)
            .where(TransaksiKasir.waktu_bayar <= akhir)
            .where(TransaksiKasir.status_transaksi == "BAYAR")
            .group_by(TransaksiKasir.id_staf_kasir)
        ).all())
        refund = _rb.refund_per_staf(self.db, awal, akhir)
        out = []
        for id_staf in sorted(set(jual) | set(refund)):
            staf = self.db.get(MasterStaf, id_staf)
            j = Decimal(str(jual.get(id_staf) or 0))
            r = refund.get(id_staf, Decimal("0"))
            out.append({
                "id_staf": id_staf,
                "nama": staf.nama_staf if staf else f"staf #{id_staf}",
                "penjualan": j, "refund": r, "bersih": j - r,
            })
        return out

    def _pembayaran_di_luar_jendela(self, sesi: KasirClosing, *, sesudah_tutup: bool) -> list:
        """Pembayaran di tanggal sesi yang jatuh di LUAR jam laci terbuka.

        sesudah_tutup=False → sebelum `shift_mulai` (masuk sebelum "Buka Kasir" ditekan).
          TETAP dihitung di expected — ini hanya penjelasan.
        sesudah_tutup=True  → sesudah `shift_tutup` (sesi CLOSED). TIDAK mengubah angka
          tutup kasir yang sudah ditandatangani (prinsip sama dengan T32) — ditampilkan
          supaya uangnya tidak hilang dari pandangan.
        """
        from app.db.models import MasterStaf
        awal, akhir = self._rentang_tanggal(sesi)
        stmt = (
            select(TransaksiKasir.id_transaksi, TransaksiKasir.waktu_bayar,
                   MasterStaf.nama_staf, func.sum(TransaksiPembayaran.nominal))
            .join(TransaksiPembayaran, TransaksiPembayaran.id_transaksi == TransaksiKasir.id_transaksi)
            .join(MasterStaf, MasterStaf.id_staf == TransaksiKasir.id_staf_kasir)
            .where(TransaksiKasir.status_transaksi == "BAYAR")
            .group_by(TransaksiKasir.id_transaksi, TransaksiKasir.waktu_bayar, MasterStaf.nama_staf)
            .order_by(TransaksiKasir.waktu_bayar)
        )
        if sesudah_tutup:
            if sesi.shift_tutup is None:
                return []
            stmt = stmt.where(TransaksiKasir.waktu_bayar > sesi.shift_tutup,
                              TransaksiKasir.waktu_bayar <= akhir)
        else:
            stmt = stmt.where(TransaksiKasir.waktu_bayar >= awal,
                              TransaksiKasir.waktu_bayar < sesi.shift_mulai)
        return [
            {"id_transaksi": i, "waktu": w, "petugas": n, "nominal": Decimal(str(t or 0))}
            for i, w, n, t in self.db.execute(stmt).all()
        ]

    def _build_rows(self, penjualan: dict, modal: Decimal) -> tuple:
        """Bangun daftar expected per metode + total_expected.

        TUNAI: expected = modal_awal + penjualan_tunai (expected_laci).
        Non-tunai: expected = penjualan sistem.
        Return (rows, total_expected).
        """
        rows = []
        total_expected = Decimal("0")
        for metode in METODE_KANONIK:
            jual = penjualan.get(metode, Decimal("0"))
            is_tunai = metode == "TUNAI"
            exp = (modal + jual) if is_tunai else jual
            total_expected += exp
            rows.append({
                "metode_bayar": metode,
                "penjualan_sistem": jual,
                "modal_awal": modal if is_tunai else Decimal("0"),
                "expected": exp,
            })
        return rows, total_expected

    # =========================================================================
    # BUKA KASIR
    # =========================================================================
    def buka_kasir(
        self,
        id_staf_kasir: int,
        modal_awal,
        actor_id_staf: Optional[int] = None,
        request: Optional[Request] = None,
    ) -> KasirClosing:
        """Buka sesi LACI dengan modal awal.

        T28: satu laci, satu sesi per tanggal (keputusan dr. Hansen 2026-10-05).
        - Masih ada sesi OPEN (siapa pun yang membuka) → tolak. Kalau sesi itu dari
          tanggal lampau, pesannya menyebut tanggalnya: tutup dulu, hitungannya tetap
          tanggal sesi itu.
        - Hari ini sudah pernah ada sesi (walau sudah CLOSED) → tolak.
        Tidak memblokir pembayaran: `proses_bayar` memang tidak menuntut sesi terbuka.
        """
        existing = self.get_open_session()
        if existing is not None:
            tgl_sesi = existing.shift_mulai.strftime("%d/%m/%Y")
            raise HTTPException(
                400,
                f"Laci masih terbuka: sesi #{existing.id_closing} tanggal {tgl_sesi}. "
                f"Tutup kasir sesi itu dulu sebelum membuka sesi baru.",
            )
        modal = Decimal(str(modal_awal or 0))
        if modal < 0:
            raise HTTPException(400, "Modal awal tidak boleh negatif.")

        now = datetime.now()
        sudah = self.db.execute(
            select(KasirClosing.id_closing)
            .where(KasirClosing.shift_mulai >= datetime.combine(now.date(), _time.min))
            .where(KasirClosing.shift_mulai <= datetime.combine(now.date(), _time.max))
            .limit(1)
        ).scalar_one_or_none()
        if sudah is not None:
            raise HTTPException(
                400,
                f"Kasir hari ini sudah pernah dibuka dan ditutup (sesi #{sudah}). "
                "Satu laci, satu sesi per hari — uang yang masuk sesudah tutup tetap "
                "tercatat dan ditampilkan sebagai peringatan pada sesi itu.",
            )
        actor = actor_id_staf or id_staf_kasir
        sesi = KasirClosing(
            id_staf_kasir=id_staf_kasir,
            shift_mulai=now,
            status="OPEN",
            modal_awal=modal,
            id_staf_buka=actor,
        )
        self.db.add(sesi)
        self.db.flush()
        self.audit.log(
            aksi="BUKA_KASIR",
            id_staf=actor,
            tabel_target="kasir_closing",
            id_target=sesi.id_closing,
            data_baru={"modal_awal": float(modal), "shift_mulai": now.isoformat()},
            keterangan=f"Buka kasir kasir_id={id_staf_kasir}, modal Rp {modal}",
            request=request,
        )
        self.db.commit()
        self.db.refresh(sesi)
        return sesi

    # =========================================================================
    # PREVIEW TUTUP KASIR
    # =========================================================================
    def get_closing_preview(self, id_staf_kasir: Optional[int] = None) -> dict:
        """Tampilkan expected per metode untuk sesi OPEN kasir ini."""
        sesi = self.get_open_session(id_staf_kasir)
        if sesi is None:
            raise HTTPException(
                400, "Belum ada sesi kasir OPEN. Lakukan 'Buka Kasir' dulu."
            )
        modal = Decimal(str(sesi.modal_awal or 0))
        penjualan = self._penjualan_per_metode(sesi)
        rows, total_expected = self._build_rows(penjualan, modal)
        return {
            "id_closing": sesi.id_closing,
            "id_staf_kasir": sesi.id_staf_kasir,
            "shift_mulai": sesi.shift_mulai,
            "tanggal_sesi": sesi.shift_mulai.date(),
            "modal_awal": modal,
            "metode": rows,
            "total_expected": total_expected,
            "per_petugas": self._rincian_per_petugas(sesi),
            "sebelum_buka": self._pembayaran_di_luar_jendela(sesi, sesudah_tutup=False),
        }

    def _pending_antrian_hari_ini(self, tanggal=None) -> dict:
        """Hitung pasien yang MASIH aktif/antri hari ini (belum settle), per status.

        Aktif = semua `status_antrian` KECUALI terminal (COMPLETED, BATAL).
        Dipakai guard `tutup_kasir` (hard block, keputusan 2026-07-10): status antri
        yang tertinggal tak auto-transisi, jadi harus diselesaikan / diubah FO dulu.
        """
        from datetime import date as _date
        from sqlalchemy import func as _f, select as _sel
        from app.db.models import Kunjungan

        _TERMINAL = ("COMPLETED", "BATAL")
        # T28: tanggal SESI, bukan hari ini — menutup sesi kemarin yang terlupa tidak
        # boleh terhalang antrian hari ini yang memang masih berjalan.
        rows = self.db.execute(
            _sel(Kunjungan.status_antrian, _f.count())
            .where(
                _f.date(Kunjungan.tgl_kunjungan) == (tanggal or _date.today()),
                Kunjungan.status_antrian.notin_(_TERMINAL),
            )
            .group_by(Kunjungan.status_antrian)
        ).all()
        return {s: int(n) for s, n in rows if s is not None}

    # =========================================================================
    # TUTUP KASIR
    # =========================================================================
    def tutup_kasir(
        self,
        id_staf_kasir: int,
        counted_per_metode: dict,
        catatan: Optional[str] = None,
        actor_id_staf: Optional[int] = None,
        request: Optional[Request] = None,
    ) -> KasirClosing:
        """Tutup sesi: hitung selisih per metode + total, simpan closing record.

        counted_per_metode = {"TUNAI": 500000, "QRIS": 0, ...} (boleh sebagian).
        Catatan WAJIB kalau total_selisih != 0.
        """
        sesi = self.get_open_session(id_staf_kasir)
        if sesi is None:
            raise HTTPException(400, "Belum ada sesi kasir OPEN untuk ditutup.")

        # HARD BLOCK (2026-07-10): tolak tutup kasir kalau masih ada pasien antri hari ini.
        # Status antri yang tertinggal tak auto-transisi → wajib diselesaikan (bayar/serah)
        # atau FO ubah status pasien yang tersangkut dulu.
        pending = self._pending_antrian_hari_ini(sesi.shift_mulai.date())
        if pending:
            ringkas = ", ".join(f"{s}={n}" for s, n in sorted(pending.items()))
            raise HTTPException(
                400,
                f"Masih ada pasien belum selesai hari ini ({ringkas}). "
                "Selesaikan (bayar / serah obat) dulu, atau minta FO mengubah status "
                "pasien yang tersangkut, sebelum menutup kasir.",
            )

        modal = Decimal(str(sesi.modal_awal or 0))
        penjualan = self._penjualan_per_metode(sesi)

        detail = []
        total_expected = Decimal("0")
        total_counted = Decimal("0")
        for metode in METODE_KANONIK:
            jual = penjualan.get(metode, Decimal("0"))
            is_tunai = metode == "TUNAI"
            exp = (modal + jual) if is_tunai else jual
            counted = Decimal(str(counted_per_metode.get(metode, 0) or 0))
            if counted < 0:
                raise HTTPException(400, f"Counted {metode} tidak boleh negatif.")
            selisih = counted - exp
            total_expected += exp
            total_counted += counted
            detail.append({
                "metode_bayar": metode,
                "penjualan_sistem": float(jual),
                "modal_awal": float(modal) if is_tunai else 0.0,
                "expected": float(exp),
                "counted": float(counted),
                "selisih": float(selisih),
                # Setoran tunai = porsi penjualan yg disetor (counted - modal). Hanya TUNAI.
                "setoran_tunai": float(counted - modal) if is_tunai else None,
            })

        total_selisih = total_counted - total_expected
        catatan_clean = (catatan or "").strip()
        if total_selisih != 0 and not catatan_clean:
            raise HTTPException(
                400,
                f"Selisih total Rp {total_selisih} (tidak nol) — catatan wajib diisi.",
            )

        now = datetime.now()
        sesi.shift_tutup = now
        sesi.status = "CLOSED"
        sesi.total_expected = total_expected
        sesi.total_counted = total_counted
        sesi.total_selisih = total_selisih
        sesi.detail_metode = detail
        sesi.catatan = catatan_clean or None
        sesi.id_staf_tutup = actor_id_staf or id_staf_kasir
        self.db.flush()

        self.audit.log(
            aksi="TUTUP_KASIR",
            id_staf=actor_id_staf or id_staf_kasir,
            tabel_target="kasir_closing",
            id_target=sesi.id_closing,
            data_baru={
                "total_expected": float(total_expected),
                "total_counted": float(total_counted),
                "total_selisih": float(total_selisih),
                "detail_metode": detail,
                # T28: jejak siapa memproses berapa + uang yang masuk sebelum laci
                # dibuka (sudah termasuk di expected). Snapshot saat tutup.
                "tanggal_sesi": sesi.shift_mulai.date().isoformat(),
                "per_petugas": [
                    {"id_staf": p["id_staf"], "nama": p["nama"],
                     "penjualan": float(p["penjualan"]), "refund": float(p["refund"])}
                    for p in self._rincian_per_petugas(sesi)
                ],
                "sebelum_buka": [
                    {"id_transaksi": x["id_transaksi"], "waktu": x["waktu"].isoformat(),
                     "nominal": float(x["nominal"])}
                    for x in self._pembayaran_di_luar_jendela(sesi, sesudah_tutup=False)
                ],
            },
            keterangan=f"Tutup kasir #{sesi.id_closing}, selisih total Rp {total_selisih}",
            request=request,
        )
        self.db.commit()
        self.db.refresh(sesi)
        return sesi

    # =========================================================================
    # LAPORAN OWNER (dipakai Langkah 4)
    # =========================================================================
    def list_closings(
        self,
        tgl=None,
        id_staf_kasir: Optional[int] = None,
    ) -> list:
        """Daftar closing CLOSED, opsional filter tanggal (shift_tutup) + kasir."""
        stmt = select(KasirClosing).where(KasirClosing.status == "CLOSED")
        if id_staf_kasir is not None:
            stmt = stmt.where(KasirClosing.id_staf_kasir == id_staf_kasir)
        if tgl is not None:
            start = datetime.combine(tgl, _time.min)
            end = datetime.combine(tgl, _time.max)
            stmt = stmt.where(KasirClosing.shift_tutup >= start)
            stmt = stmt.where(KasirClosing.shift_tutup <= end)
        stmt = stmt.order_by(KasirClosing.shift_tutup.desc())
        return list(self.db.execute(stmt).scalars().all())


__all__ = ["KasirClosingService", "METODE_KANONIK"]
