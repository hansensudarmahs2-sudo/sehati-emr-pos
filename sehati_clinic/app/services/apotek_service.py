"""
ApotekService — antrian, detail, serahkan obat, write-off, suggested order.

Per keputusan dr. Hansen Q1 Week 5:
- Stok produk POS dipotong dari `master_produk.stok_terkini` saja
- Tidak ada inventory_history tracking untuk produk POS (Phase 2+ kalau perlu)
- Stok diizinkan minus (filosofi: operasional jangan diblok)
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.models import StafRoleEnum, StatusItemResepEnum
from app.repositories.apotek_repo import ApotekRepository
from app.repositories.kunjungan_repo import KunjunganRepository
from app.schemas.apotek import (
    AntrianApotekItem,
    AntrianApotekResponse,
    DetailResepResponse,
    RacikanBahanDetailItem,
    RacikanDetailItem,
    ResepDetailItem,
    SerahkanObatRequest,
    StokPotongItem,
    SuggestedOrderItem,
    SuggestedOrderResponse,
    WriteOffProdukRequest,
)
from app.services.audit_service import AuditService


# Jenis mutasi valid untuk write-off
_VALID_JENIS_WRITEOFF = {"EXPIRED", "RUSAK", "PENYESUAIAN"}


class ApotekService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ApotekRepository(db)
        self.kunjungan_repo = KunjunganRepository(db)
        self.audit = AuditService(db)

    # =========================================================================
    # ANTRIAN
    # =========================================================================
    def lihat_antrian(self) -> AntrianApotekResponse:
        today = date.today()
        rows = self.repo.list_antrian_obat(today=today)
        items = [
            AntrianApotekItem(
                id_kunjungan=k.id_kunjungan,
                nomor_antrean=k.nomor_antrean,
                tgl_kunjungan=k.tgl_kunjungan,
                status_antrian=k.status_antrian,
                id_pasien=p.id_pasien,
                no_rm=p.no_rm,
                nama_pasien=p.nama,
                jumlah_item_obat=n_item,
            )
            for k, p, n_item in rows
        ]
        return AntrianApotekResponse(tanggal=today, total=len(items), data=items)

    # =========================================================================
    # DETAIL RESEP
    # =========================================================================
    def get_detail_resep(self, id_kunjungan: int) -> DetailResepResponse:
        kp = self.repo.get_kunjungan_with_pasien(id_kunjungan)
        if kp is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Kunjungan {id_kunjungan} tidak ditemukan.",
            )
        kunjungan, pasien = kp

        rows = self.repo.get_resep_for_apotek(id_kunjungan)
        items: list[ResepDetailItem] = []
        semua_cukup = True
        for resep, produk in rows:
            stok_terkini = float(produk.stok_terkini or 0)
            qty = float(resep.qty or 0)
            stok_cukup = qty <= stok_terkini
            if not stok_cukup:
                semua_cukup = False
            items.append(ResepDetailItem(
                id_resep=resep.id_resep,
                id_produk=resep.id_produk,
                kode_produk=produk.kode_produk,
                nama_produk=produk.nama_produk,
                qty=qty,
                satuan=produk.satuan,
                aturan_pakai=resep.aturan_pakai,
                status_item=(
                    resep.status_item.value
                    if hasattr(resep.status_item, "value")
                    else (str(resep.status_item) if resep.status_item else None)
                ),
                stok_terkini=stok_terkini,
                stok_cukup=stok_cukup,
            ))

        # Racikan: stok yang dicek adalah stok tiap BAHAN, bukan "produk racikan".
        racikan_items: list[RacikanDetailItem] = []
        for head, bahan_rows in self.repo.get_racikan_for_apotek(id_kunjungan):
            bahan_out: list[RacikanBahanDetailItem] = []
            for b in bahan_rows:
                _stok = None
                _cukup = True
                if b.id_produk:
                    from app.db.models import MasterProduk as _MPro
                    _p = self.db.get(_MPro, b.id_produk)
                    if _p is not None:
                        _stok = float(_p.stok_terkini or 0)
                        _cukup = float(b.dipakai or 0) <= _stok
                        if not _cukup:
                            semua_cukup = False
                bahan_out.append(RacikanBahanDetailItem(
                    id_produk=b.id_produk,
                    nama=b.nama_snapshot,
                    dipakai=float(b.dipakai or 0),
                    satuan_dipakai=b.satuan_dipakai,
                    stok_terkini=_stok,
                    stok_cukup=_cukup,
                ))
            racikan_items.append(RacikanDetailItem(
                id_kunjungan_racikan=head.id_kunjungan_racikan,
                nama=head.nama_snapshot,
                jenis_racik=head.jenis_racik,
                jumlah_unit=int(head.jumlah_unit or 0),
                aturan_pakai=head.aturan_pakai,
                status_item=head.status_item,
                bahan=bahan_out,
            ))

        return DetailResepResponse(
            id_kunjungan=id_kunjungan,
            id_pasien=pasien.id_pasien,
            no_rm=pasien.no_rm,
            nama_pasien=pasien.nama,
            daftar_obat=items,
            daftar_racikan=racikan_items,
            total_item=len(items) + len(racikan_items),
            semua_stok_cukup=semua_cukup,
        )

    @staticmethod
    def _now_serah() -> datetime:
        """Waktu serah dalam WIB, naive (kolom TIMESTAMP menyimpan tanpa tz).

        Sama seperti `KasirService._now_utc7` — jam dinding klinik, bukan UTC, supaya
        laporan harian apoteker tidak bergeser tanggal di atas jam 17:00.
        """
        return datetime.now(timezone(timedelta(hours=7))).replace(tzinfo=None)

    def _simpan_lot_terpakai(
        self, id_kunjungan, id_produk, consumed: list,
        id_resep: Optional[int] = None,
        id_kunjungan_racikan: Optional[int] = None,
    ) -> int:
        """H2/P0-1 (AUDIT_SEHATI_2026-07-10): rekam lot FEFO yang dipotong saat serah,
        supaya void bisa mengembalikan qty ke lot ASLI (ED terjaga) — bukan VOID-RETURN.

        Task #54: sekarang jejak juga mencatat ASAL potongan (`id_resep` ATAU
        `id_kunjungan_racikan`). Tanpa itu, satu produk yang dipakai sebagai obat biasa
        SEKALIGUS sebagai bahan racikan di kunjungan yang sama akan berbagi jejak —
        void salah satunya bisa memakan jejak milik yang lain.

        `consumed` = list dari consume_fefo (item {'id_lot', 'qty', ...}). FLUSH (caller commit).
        """
        from app.db.models import KunjunganLotTerpakai

        n = 0
        for c in consumed or []:
            id_lot = c.get("id_lot")
            qty = float(c.get("qty") or 0)
            if not id_lot or qty <= 0:
                continue
            self.db.add(KunjunganLotTerpakai(
                id_kunjungan=id_kunjungan, id_produk=id_produk, id_lot=id_lot, qty=qty,
                id_resep=id_resep, id_kunjungan_racikan=id_kunjungan_racikan,
            ))
            n += 1
        if n:
            self.db.flush()
        return n

    # =========================================================================
    # SERAHKAN OBAT — atomic potong stok + COMPLETED
    # =========================================================================
    def list_obat_tertunda(self) -> list[dict]:
        """Daftar kunjungan COMPLETED yang obatnya masih tertunda (tgl_janji_kirim terisi)."""
        from datetime import date as _date
        from sqlalchemy import select as _sel
        from app.db.models import Kunjungan as _K, Pasien as _P, KunjunganResep as _KR, MasterProduk as _MP
        today = _date.today()
        rows = self.db.execute(
            _sel(_K, _P).join(_P, _P.id_pasien == _K.id_pasien)
            .where(_K.status_antrian == "COMPLETED", _K.tgl_janji_kirim.is_not(None))
            .order_by(_K.tgl_janji_kirim.asc())
        ).all()
        out = []
        for kj, pasien in rows:
            resep = self.db.execute(
                _sel(_KR, _MP).join(_MP, _MP.id_produk == _KR.id_produk)
                .where(_KR.id_kunjungan == kj.id_kunjungan, _KR.status_item == "DIBAYAR")
            ).all()
            obat = [f"{mp.nama_produk} x{float(kr.qty or 0):g}" for kr, mp in resep]
            # Task #54-F: daftar TERSTRUKTUR per item, supaya tiap baris bisa
            # dibatalkan sendiri (refund) tanpa membatalkan seluruh transaksi.
            items = [
                {
                    "jenis": "RESEP",
                    "id": kr.id_resep,
                    "label": f"{mp.nama_produk} x{float(kr.qty or 0):g}",
                }
                for kr, mp in resep
            ]
            # Racikan ikut ditampilkan — kunjungan yang isinya racikan saja tetap perlu
            # terlihat di daftar Obat Tertunda.
            for _h, _bh in self.repo.get_racikan_dibayar_for_serah(kj.id_kunjungan):
                obat.append(f"⚗️ {_h.nama_snapshot} x{int(_h.jumlah_unit or 0)} unit")
                items.append({
                    "jenis": "RACIKAN",
                    "id": _h.id_kunjungan_racikan,
                    "label": f"⚗️ {_h.nama_snapshot} x{int(_h.jumlah_unit or 0)} unit",
                })
            out.append({
                "id_kunjungan": kj.id_kunjungan,
                "id_pasien": kj.id_pasien,
                "no_rm": pasien.no_rm,
                "nama_pasien": pasien.nama,
                "nomor_telepon": pasien.nomor_telepon or "",
                "tgl_janji_kirim": kj.tgl_janji_kirim,
                "catatan_kirim": kj.catatan_kirim or "",
                "obat": obat,
                "items": items,
                "overdue": kj.tgl_janji_kirim is not None and kj.tgl_janji_kirim <= today,
            })
        return out

    # =========================================================================
    # PENEBUSAN RESEP LAMA (tebus lanjut / tebus sebagian)
    # =========================================================================
    MAX_UMUR_RESEP_HARI = 30  # lewat ini: DIPERINGATKAN, tetap boleh (keputusan #8)

    def list_resep_belum_ditebus(self, id_pasien: int) -> list[dict]:
        """Resep PENDING milik pasien dari kunjungan LAMA yang belum pernah ditebus.

        "Belum ditebus" ditentukan dari **tidak adanya salinan** yang menunjuk ke baris
        ini (`kunjungan_resep.id_resep_asal`). Sengaja tidak ada kolom "sudah_ditebus"
        di baris asal: dua penanda untuk satu fakta bisa berselisih, dan yang berselisih
        diam-diam adalah yang paling mahal (lihat pelajaran task #54).

        Resep berumur lebih dari `MAX_UMUR_RESEP_HARI` tetap dikembalikan, tapi ditandai
        `kedaluwarsa=True` supaya layar bisa memperingatkan. Keadaan pasien bisa berubah
        dalam sebulan; memblokirnya akan memaksa konsultasi ulang untuk obat rutin.
        """
        from datetime import date as _date
        from sqlalchemy import select as _sel
        from sqlalchemy.orm import aliased as _aliased
        from app.db.models import (
            Kunjungan as _K, KunjunganResep as _KR, MasterProduk as _MP,
            StatusItemResepEnum as _ST,
        )

        # Sudah ditebus = ADA baris LAIN yang `id_resep_asal`-nya menunjuk baris ini.
        _salinan = _aliased(_KR)
        sudah_ditebus = (
            _sel(_salinan.id_resep)
            .where(_salinan.id_resep_asal == _KR.id_resep)
            .exists()
        )

        rows = self.db.execute(
            _sel(_KR, _MP, _K)
            .join(_MP, _MP.id_produk == _KR.id_produk)
            .join(_K, _K.id_kunjungan == _KR.id_kunjungan)
            .where(
                _K.id_pasien == id_pasien,
                # R8: DUA status berarti "belum dibayar" —
                #   PENDING = pasien pulang tanpa membayar sama sekali
                #   DITUNDA = pasien beli separuh di meja kasir, sisanya disisakan
                # Keduanya sah untuk ditebus belakangan.
                _KR.status_item.in_([_ST.PENDING, _ST.DITUNDA]),
                _KR.id_resep_asal.is_(None),   # jangan tawarkan salinan sebagai sumber
                ~sudah_ditebus,
            )
            .order_by(_K.tgl_kunjungan.desc(), _KR.id_resep.asc())
        ).all()

        hari_ini = _date.today()
        out = []
        for kr, mp, kj in rows:
            tgl = kj.tgl_kunjungan.date() if kj.tgl_kunjungan else None
            umur = (hari_ini - tgl).days if tgl else None
            out.append({
                "id_resep": kr.id_resep,
                "id_kunjungan": kj.id_kunjungan,
                "tgl_kunjungan": tgl,
                "umur_hari": umur,
                "kedaluwarsa": umur is not None and umur > self.MAX_UMUR_RESEP_HARI,
                "id_produk": mp.id_produk,
                "nama_produk": mp.nama_produk,
                "kode_produk": mp.kode_produk,
                "qty": float(kr.qty or 0),
                "aturan_pakai": kr.aturan_pakai or "",
                "stok_terkini": float(mp.stok_terkini or 0),
            })
        return out

    def list_racikan_belum_ditebus(self, id_pasien: int) -> list[dict]:
        """Racikan pasien yang belum ditebus — padanan `list_resep_belum_ditebus` (R8).

        Pola anti-tebus-ganda SAMA PERSIS: "sudah ditebus" = ADA baris lain yang
        `id_kunjungan_racikan_asal`-nya menunjuk baris ini. Tidak ada kolom penanda
        terpisah.

        ⚠ HARGA YANG DIKEMBALIKAN DI SINI hanya untuk ANCAR-ANCAR di layar. Harga yang
        ditagih DIHITUNG ULANG saat penebusan (keputusan dr. Hansen 2026-09-27), karena
        baris ini belum pernah ditagih dan harga bahan bisa sudah berubah.
        """
        from datetime import date as _date
        from sqlalchemy import select as _sel
        from sqlalchemy.orm import aliased as _aliased
        from app.db.models import Kunjungan as _K
        from app.db.models.racikan import (
            KunjunganRacikan as _KRC, KunjunganRacikanBahan as _KRCB,
        )

        _salinan = _aliased(_KRC)
        sudah_ditebus = (
            _sel(_salinan.id_kunjungan_racikan)
            .where(_salinan.id_kunjungan_racikan_asal == _KRC.id_kunjungan_racikan)
            .exists()
        )

        rows = self.db.execute(
            _sel(_KRC, _K)
            .join(_K, _K.id_kunjungan == _KRC.id_kunjungan)
            .where(
                _K.id_pasien == id_pasien,
                _KRC.status_item.in_(["PENDING", "DITUNDA"]),
                _KRC.id_kunjungan_racikan_asal.is_(None),
                ~sudah_ditebus,
            )
            .order_by(_K.tgl_kunjungan.desc(), _KRC.id_kunjungan_racikan.asc())
        ).all()

        hari_ini = _date.today()
        out = []
        for rc, kj in rows:
            bahan = self.db.execute(
                _sel(_KRCB)
                .where(_KRCB.id_kunjungan_racikan == rc.id_kunjungan_racikan)
                .order_by(_KRCB.id_kunjungan_racikan_bahan.asc())
            ).scalars().all()
            tgl = kj.tgl_kunjungan.date() if kj.tgl_kunjungan else None
            umur = (hari_ini - tgl).days if tgl else None
            out.append({
                "id_kunjungan_racikan": rc.id_kunjungan_racikan,
                "id_kunjungan": kj.id_kunjungan,
                "tgl_kunjungan": tgl,
                "umur_hari": umur,
                "kedaluwarsa": umur is not None and umur > self.MAX_UMUR_RESEP_HARI,
                "nama": rc.nama_snapshot,
                "jenis_racik": rc.jenis_racik,
                "jumlah_unit": int(rc.jumlah_unit or 0),
                "aturan_pakai": rc.aturan_pakai or "",
                "total_dulu": float(rc.total or 0),   # ancar-ancar saja, lihat docstring
                "bahan": [
                    {"id_produk": b.id_produk, "nama": b.nama_snapshot,
                     "dosis": float(b.dosis_per_unit or 0), "satuan": b.satuan_dosis}
                    for b in bahan
                ],
            })
        return out

    def tunda_serah_obat(
        self,
        id_kunjungan: int,
        tgl_janji_kirim,
        catatan: Optional[str],
        id_staf: int,
        request: Optional[Request] = None,
    ) -> dict:
        """OBAT TERTUNDA (P1-1): tandai obat dibayar tapi diserah/dikirim belakangan.

        Kunjungan → COMPLETED (kasir bisa Tutup Kasir), resep tetap DIBAYAR, stok BELUM
        dipotong. tgl_janji_kirim WAJIB. Serah sebenarnya dilakukan nanti via serahkan_obat.
        """
        kunjungan = self.kunjungan_repo.get_by_id(id_kunjungan)
        if kunjungan is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Kunjungan {id_kunjungan} tidak ditemukan.")
        # Task #54: setelah serah SEBAGIAN kunjungan sudah COMPLETED, tapi sisa itemnya
        # masih perlu bisa dijadwalkan ulang. Yang menentukan bukan status kunjungan,
        # melainkan apakah masih ada item DIBAYAR yang belum diserahkan.
        if kunjungan.status_antrian not in ("ANTRI_OBAT", "COMPLETED"):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Kunjungan '{kunjungan.status_antrian}' tidak bisa ditunda.",
            )
        if tgl_janji_kirim is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tanggal janji kirim/ambil WAJIB diisi.")
        resep_list = self.repo.get_resep_dibayar_for_serah(id_kunjungan)
        racikan_list = self.repo.get_racikan_dibayar_for_serah(id_kunjungan)
        if not resep_list and not racikan_list:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Tidak ada resep atau racikan DIBAYAR untuk ditunda.",
            )

        _status_lama = kunjungan.status_antrian
        kunjungan.tgl_janji_kirim = tgl_janji_kirim
        kunjungan.catatan_kirim = (catatan or None)
        if kunjungan.status_antrian == "ANTRI_OBAT":
            self.kunjungan_repo.update_status(kunjungan, "COMPLETED")
        self.audit.log(
            aksi="OBAT_TUNDA",
            id_staf=id_staf,
            tabel_target="kunjungan",
            id_target=id_kunjungan,
            data_lama={"status_antrian": _status_lama},
            data_baru={"status_antrian": "COMPLETED", "tgl_janji_kirim": str(tgl_janji_kirim)},
            keterangan=(
                f"Obat ditunda (kirim/ambil {tgl_janji_kirim}). "
                f"{len(resep_list)} resep + {len(racikan_list)} racikan. Stok belum dipotong."
            ),
            request=request,
        )
        self.db.commit()
        return {
            "status": "success",
            "message": f"Obat ditandai TERTUNDA — dijadwalkan {tgl_janji_kirim}. Kasir bisa menutup.",
            "data": {"id_kunjungan": id_kunjungan, "tgl_janji_kirim": str(tgl_janji_kirim)},
        }

    def serahkan_obat(
        self,
        payload: SerahkanObatRequest,
        id_staf_apoteker: int,
        request: Optional[Request] = None,
    ) -> dict:
        # 1. Validasi kunjungan
        kunjungan = self.kunjungan_repo.get_by_id(payload.id_kunjungan)
        if kunjungan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Kunjungan {payload.id_kunjungan} tidak ditemukan.",
            )
        _is_tertunda = (
            kunjungan.status_antrian == "COMPLETED"
            and kunjungan.tgl_janji_kirim is not None
        )
        if kunjungan.status_antrian != "ANTRI_OBAT" and not _is_tertunda:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Kunjungan status saat ini '{kunjungan.status_antrian}' — "
                    f"hanya 'ANTRI_OBAT' atau kunjungan dengan obat TERTUNDA yang bisa diserahkan."
                ),
            )

        # 2. Ambil daftar resep + racikan DIBAYAR (yang siap diserahkan)
        #    Task #54 — bisa SEBAGIAN. payload.id_resep / id_kunjungan_racikan None
        #    berarti "semua" (alur lama & API v1); kalau diisi, hanya itu yang diserahkan.
        _parsial = payload.id_resep is not None or payload.id_kunjungan_racikan is not None
        resep_list = self.repo.get_resep_dibayar_for_serah(
            payload.id_kunjungan, only_ids=payload.id_resep)
        racikan_list = self.repo.get_racikan_dibayar_for_serah(
            payload.id_kunjungan, only_ids=payload.id_kunjungan_racikan)
        if not resep_list and not racikan_list:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Tidak ada item yang dipilih untuk diserahkan."
                    if _parsial else
                    "Tidak ada resep atau racikan DIBAYAR di kunjungan ini untuk diserahkan."
                ),
            )

        # 2b. Hitung SISA — item DIBAYAR yang tidak ikut diserahkan kali ini.
        _semua_resep = self.repo.get_resep_dibayar_for_serah(payload.id_kunjungan)
        _semua_racik = self.repo.get_racikan_dibayar_for_serah(payload.id_kunjungan)
        _id_resep_serah = {r.id_resep for r in resep_list}
        _id_racik_serah = {h.id_kunjungan_racikan for h, _ in racikan_list}
        n_sisa = (
            len([r for r in _semua_resep if r.id_resep not in _id_resep_serah])
            + len([h for h, _ in _semua_racik if h.id_kunjungan_racikan not in _id_racik_serah])
        )
        # Sisa tanpa tanggal = obat yang tidak akan pernah muncul sebagai terlambat.
        # Lebih baik ditolak sekarang daripada hilang dari perhatian.
        if n_sisa > 0 and payload.tgl_janji_kirim_sisa is None and kunjungan.tgl_janji_kirim is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"{n_sisa} item belum diserahkan — tanggal janji kirim/ambil untuk "
                    "sisanya WAJIB diisi."
                ),
            )

        try:
            # 3. Loop potong stok produk (FOR UPDATE lock per produk)
            items_dipotong: list[StokPotongItem] = []
            batch_terpakai = []  # P-L5: jejak batch/ED yang keluar (FEFO)
            shortfall_warnings: list[str] = []  # sub-fix C: surface divergensi (tak blok)
            from app.services.inventory_lot_service import InventoryLotService
            _lot_svc = InventoryLotService(self.db)
            for resep in resep_list:
                produk = self.repo.get_produk_for_update(resep.id_produk)
                if produk is None:
                    # Produk hilang dari master (rare) — skip, log warning
                    continue
                qty = float(resep.qty or 0)
                stok_sebelum = float(produk.stok_terkini or 0)
                stok_sesudah = self.repo.update_stok_produk(produk, delta=-qty)
                if stok_sesudah < 0:
                    shortfall_warnings.append(f"{produk.nama_produk}: stok jadi minus ({stok_sesudah:g})")
                # P-L5: potong lot FEFO (RETAIL) — ED terdekat keluar dulu
                _fefo = _lot_svc.consume_fefo(
                    tipe_item="PRODUK", lokasi="RETAIL", qty=qty, id_produk=produk.id_produk)
                if (_fefo.get("shortfall") or 0) > 0:
                    shortfall_warnings.append(f"{produk.nama_produk}: lot kurang {_fefo['shortfall']:g} (cache vs lot divergen)")
                # H2/P0-1: rekam lot yang dipotong → void bisa restore ke lot ASLI (ED terjaga).
                self._simpan_lot_terpakai(
                    payload.id_kunjungan, produk.id_produk, _fefo["consumed"],
                    id_resep=resep.id_resep)
                for c in _fefo["consumed"]:
                    batch_terpakai.append(
                        f"{produk.nama_produk}: {c['qty']}x batch {c['batch_no'] or '-'}"
                        + (f" ED {c['tgl_ed']}" if c['tgl_ed'] else "")
                    )
                items_dipotong.append(StokPotongItem(
                    id_produk=produk.id_produk,
                    nama_produk=produk.nama_produk,
                    qty_diserahkan=qty,
                    stok_sebelum=stok_sebelum,
                    stok_sesudah=stok_sesudah,
                ))

            # 3b. Potong stok BAHAN racikan. Yang dipotong = kolom `dipakai` hasil
            # kalkulator (butir sudah CEIL untuk mode MG, gram pro-rata untuk mode GRAM),
            # BUKAN dosis resep. Jalurnya sama persis dengan produk: lock → kurangi stok
            # → FEFO → catat jejak lot, supaya void bisa mengembalikannya ke lot asli.
            for _head, _bahan_rows in racikan_list:
                for _b in _bahan_rows:
                    if not _b.id_produk:
                        continue  # bahan non-inventori — tidak ada stok yang dipotong
                    _qty_b = float(_b.dipakai or 0)
                    if _qty_b <= 0:
                        continue
                    _produk_b = self.repo.get_produk_for_update(_b.id_produk)
                    if _produk_b is None:
                        continue
                    _stok_sebelum_b = float(_produk_b.stok_terkini or 0)
                    _stok_sesudah_b = self.repo.update_stok_produk(_produk_b, delta=-_qty_b)
                    if _stok_sesudah_b < 0:
                        shortfall_warnings.append(
                            f"{_produk_b.nama_produk} (racikan {_head.nama_snapshot}): "
                            f"stok jadi minus ({_stok_sesudah_b:g})"
                        )
                    _fefo_b = _lot_svc.consume_fefo(
                        tipe_item="PRODUK", lokasi="RETAIL",
                        qty=_qty_b, id_produk=_produk_b.id_produk)
                    if (_fefo_b.get("shortfall") or 0) > 0:
                        shortfall_warnings.append(
                            f"{_produk_b.nama_produk} (racikan): lot kurang "
                            f"{_fefo_b['shortfall']:g} (cache vs lot divergen)"
                        )
                    self._simpan_lot_terpakai(
                        payload.id_kunjungan, _produk_b.id_produk, _fefo_b["consumed"],
                        id_kunjungan_racikan=_head.id_kunjungan_racikan)
                    for c in _fefo_b["consumed"]:
                        batch_terpakai.append(
                            f"{_produk_b.nama_produk}: {c['qty']}x batch {c['batch_no'] or '-'}"
                            + (f" ED {c['tgl_ed']}" if c['tgl_ed'] else "")
                        )
                    items_dipotong.append(StokPotongItem(
                        id_produk=_produk_b.id_produk,
                        nama_produk=f"{_produk_b.nama_produk} (racikan {_head.nama_snapshot})",
                        qty_diserahkan=_qty_b,
                        stok_sebelum=_stok_sebelum_b,
                        stok_sesudah=_stok_sesudah_b,
                    ))

            # 3c. Tandai item yang BARU saja diserahkan. Ini yang menggantikan tebakan
            # lama "kunjungan COMPLETED = stok sudah dipotong". Void membaca status ini
            # untuk tahu item mana yang stoknya boleh dikembalikan.
            _waktu = self._now_serah()
            for _r in resep_list:
                _r.status_item = StatusItemResepEnum.DISERAHKAN
                _r.waktu_serah = _waktu
                _r.id_staf_serah = id_staf_apoteker
            for _h, _ in racikan_list:
                _h.status_item = "DISERAHKAN"
                _h.waktu_serah = _waktu
                _h.id_staf_serah = id_staf_apoteker

            # 4. Status kunjungan & daftar tertunda.
            # Kunjungan tetap ditutup walau ada sisa (keputusan dr. Hansen: sisa diurus
            # modul Obat Tertunda yang sudah punya penjadwalan + notifikasi), TAPI
            # tgl_janji_kirim hanya boleh dikosongkan kalau benar-benar tidak ada sisa.
            _status_lama = kunjungan.status_antrian
            if kunjungan.status_antrian == "ANTRI_OBAT":
                self.kunjungan_repo.update_status(kunjungan, "COMPLETED")
            if n_sisa > 0:
                if payload.tgl_janji_kirim_sisa is not None:
                    kunjungan.tgl_janji_kirim = payload.tgl_janji_kirim_sisa
                if payload.catatan_kirim_sisa:
                    kunjungan.catatan_kirim = payload.catatan_kirim_sisa
            else:
                kunjungan.tgl_janji_kirim = None  # tuntas → keluar dari daftar tertunda

            # 5. AUDIT — menyebut item MANA, bukan hanya jumlahnya. Satu kunjungan bisa
            # diserahkan beberapa kali oleh apoteker berbeda; tanpa daftar id, laporan
            # tidak bisa memisahkan kredit antar-event.
            self.audit.log(
                aksi="SERAH_OBAT",
                id_staf=id_staf_apoteker,
                tabel_target="kunjungan",
                id_target=payload.id_kunjungan,
                data_lama={"status_antrian": _status_lama},
                data_baru={
                    "status_antrian": kunjungan.status_antrian,
                    "id_resep": sorted(_id_resep_serah),
                    "id_kunjungan_racikan": sorted(_id_racik_serah),
                    "sisa_item": n_sisa,
                    "tgl_janji_kirim": (
                        str(kunjungan.tgl_janji_kirim) if kunjungan.tgl_janji_kirim else None
                    ),
                },
                keterangan=(
                    f"Serah obat oleh apoteker_id={id_staf_apoteker}. "
                    f"Jumlah item: {len(items_dipotong)}"
                    + (f" (SEBAGIAN, {n_sisa} item masih menunggu). " if n_sisa else ". ")
                    + ("Lot FEFO: " + "; ".join(batch_terpakai) if batch_terpakai else "")
                    + (" | \u26a0 " + "; ".join(shortfall_warnings) if shortfall_warnings else "")
                ),
                request=request,
            )

            self.db.commit()
            return {
                "status": "success",
                "message": (
                    f"Obat berhasil diserahkan ke pasien. "
                    f"{len(items_dipotong)} item ter-potong dari stok. "
                    + (
                        f"\u23f3 {n_sisa} item masih menunggu \u2014 dijadwalkan "
                        f"{kunjungan.tgl_janji_kirim}."
                        if n_sisa else "Perjalanan pasien SELESAI."
                    )
                    + (" \u26a0 Perhatian: " + "; ".join(shortfall_warnings) if shortfall_warnings else "")
                ),
                "data": {
                    "id_kunjungan": payload.id_kunjungan,
                    "jumlah_item": len(items_dipotong),
                    "items_dipotong": [i.model_dump() for i in items_dipotong],
                    "sisa_item": n_sisa,
                    "status_kunjungan_baru": kunjungan.status_antrian,
                },
            }
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gagal serah obat: {str(e)}",
            )

    # =========================================================================
    # WRITE-OFF PRODUK
    # =========================================================================
    def write_off_produk(
        self,
        payload: WriteOffProdukRequest,
        id_staf_apoteker: int,
        request: Optional[Request] = None,
    ) -> dict:
        # Validasi jenis_mutasi
        jenis_upper = payload.jenis_mutasi.upper().strip()
        if jenis_upper not in _VALID_JENIS_WRITEOFF:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"jenis_mutasi '{payload.jenis_mutasi}' tidak valid. "
                    f"Harus salah satu: {sorted(_VALID_JENIS_WRITEOFF)}."
                ),
            )

        # Lock produk
        produk = self.repo.get_produk_for_update(payload.id_produk)
        if produk is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Produk {payload.id_produk} tidak ditemukan.",
            )

        try:
            stok_sebelum = float(produk.stok_terkini or 0)
            stok_sesudah = self.repo.update_stok_produk(
                produk, delta=-payload.qty_dibuang
            )
            # P-L6a: potong lot FEFO (ED terdekat/expired duluan)
            from app.services.inventory_lot_service import InventoryLotService
            _fefo = InventoryLotService(self.db).consume_fefo(
                tipe_item="PRODUK", lokasi="RETAIL",
                qty=float(payload.qty_dibuang), id_produk=produk.id_produk,
            )
            _batch_trace = "; ".join(
                f"{c['qty']}x batch {c['batch_no'] or '-'}" + (f" ED {c['tgl_ed']}" if c['tgl_ed'] else "")
                for c in _fefo["consumed"]
            )

            # AUDIT — pakai aksi spesifik supaya gampang filter rekap
            self.audit.log(
                aksi=f"WRITEOFF_PRODUK_{jenis_upper}",
                id_staf=id_staf_apoteker,
                tabel_target="master_produk",
                id_target=produk.id_produk,
                data_lama={"stok_terkini": stok_sebelum},
                data_baru={"stok_terkini": stok_sesudah},
                keterangan=(
                    f"Write-off produk '{produk.nama_produk}' qty={payload.qty_dibuang} "
                    f"jenis={jenis_upper}. Alasan: {payload.keterangan!r}"
                    + (f" | Lot FEFO: {_batch_trace}" if _batch_trace else "")
                ),
                request=request,
            )

            self.db.commit()
            return {
                "status": "success",
                "message": (
                    f"Stok '{produk.nama_produk}' berhasil dikurangi "
                    f"{payload.qty_dibuang}. Sisa: {stok_sesudah}."
                ),
                "data": {
                    "id_produk": produk.id_produk,
                    "nama_produk": produk.nama_produk,
                    "jenis_mutasi": jenis_upper,
                    "qty_dibuang": payload.qty_dibuang,
                    "stok_sebelum": stok_sebelum,
                    "stok_sesudah": stok_sesudah,
                },
            }
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gagal write-off: {str(e)}",
            )

    # =========================================================================
    # SUGGESTED ORDER
    # =========================================================================
    def suggested_order(self) -> SuggestedOrderResponse:
        """
        Analisa produk yang stok di bawah minimal + estimasi habis.

        Heuristic:
        - Ambil qty terjual 30 & 90 hari dari transaksi_detail_produk
        - rata_pemakaian_harian = qty_90_hari / 90
        - estimasi_hari_habis = stok_terkini / rata_pemakaian_harian
        - Saran order = max(qty terjual 30 hari, stok_minimal − stok_terkini)
        - Kategori:
          * URGENT: stok < (stok_minimal / 2) atau estimasi habis < 7 hari
          * RENDAH: stok < stok_minimal atau estimasi habis < 30 hari
          * AMAN: stok cukup
          * NO_DATA: tidak ada pemakaian 90 hari (barang baru/jarang jual)
        """
        now = datetime.now()  # A4: WIB anchor (banding vs waktu_bayar DB)
        sejak_90 = now - timedelta(days=90)
        sejak_30 = now - timedelta(days=30)

        qty_90_map = self.repo.get_qty_terjual_per_produk(sejak_90)
        qty_30_map = self.repo.get_qty_terjual_per_produk(sejak_30)

        # DYN: reorder point dinamis. Ambang efektif = MAX(stok_minimal manual, ROP dinamis).
        from app.services.reorder_calc import effective_min as _effmin
        from app.db.models import MasterKlinikConfig as _MKC
        _cfg = self.db.get(_MKC, 1)
        _lead = int(getattr(_cfg, "lead_time_hari", 14) or 14)
        _safety = int(getattr(_cfg, "safety_hari", 7) or 7)

        produk_list = self.repo.list_all_produk_active()
        items: list[SuggestedOrderItem] = []
        butuh_order = 0
        for produk in produk_list:
            stok_terkini = float(produk.stok_terkini or 0)
            stok_minimal = float(produk.stok_minimal or 0)
            qty_90 = qty_90_map.get(produk.id_produk, 0.0)
            qty_30 = qty_30_map.get(produk.id_produk, 0.0)
            rata_harian = round(qty_90 / 90.0, 2) if qty_90 > 0 else 0.0
            estimasi_habis = (
                round(stok_terkini / rata_harian, 1)
                if rata_harian > 0 and stok_terkini > 0
                else None
            )

            # DYN: ambang efektif = MAX(manual, ROP dinamis)
            eff_min = _effmin(stok_minimal, qty_90, _lead, _safety)

            # Kategorisasi (pakai ambang EFEKTIF)
            if qty_90 == 0:
                kategori = "NO_DATA"
            elif stok_terkini < (eff_min / 2) or (estimasi_habis is not None and estimasi_habis < 7):
                kategori = "URGENT"
            elif stok_terkini < eff_min or (estimasi_habis is not None and estimasi_habis < 30):
                kategori = "RENDAH"
            else:
                kategori = "AMAN"

            # Saran order — cover 30 hari pemakaian, minimal restock ke ambang efektif
            saran_dari_pemakaian = qty_30 if qty_30 > 0 else 0
            saran_dari_minimal = max(eff_min - stok_terkini, 0)
            saran_qty = round(max(saran_dari_pemakaian, saran_dari_minimal), 1)

            if kategori in ("URGENT", "RENDAH"):
                butuh_order += 1

            tipe = (
                produk.tipe_produk.value
                if hasattr(produk.tipe_produk, "value")
                else (str(produk.tipe_produk) if produk.tipe_produk else None)
            )
            items.append(SuggestedOrderItem(
                id_produk=produk.id_produk,
                kode_produk=produk.kode_produk,
                nama_produk=produk.nama_produk,
                satuan=produk.satuan,
                tipe_produk=tipe,
                stok_terkini=stok_terkini,
                stok_minimal=stok_minimal,
                stok_minimal_efektif=eff_min,
                qty_terjual_90_hari=qty_90,
                qty_terjual_30_hari=qty_30,
                rata_pemakaian_harian=rata_harian,
                estimasi_hari_habis=estimasi_habis,
                saran_order_qty=saran_qty,
                kategori=kategori,
            ))

        # Sort: URGENT first, then RENDAH, AMAN, NO_DATA
        sort_order = {"URGENT": 0, "RENDAH": 1, "AMAN": 2, "NO_DATA": 3}
        items.sort(key=lambda x: (sort_order.get(x.kategori, 9), -x.qty_terjual_90_hari))

        return SuggestedOrderResponse(
            waktu_analisa=now,
            total_produk_dianalisa=len(items),
            total_butuh_order=butuh_order,
            data=items,
        )

    def count_low_stock_effective(self) -> int:
        """DYN: jumlah produk dengan stok <= ambang EFEKTIF (MAX manual, ROP dinamis)."""
        from datetime import datetime as _dt, timedelta as _td
        from app.db.models import MasterKlinikConfig as _MKC
        from app.services.reorder_calc import effective_min as _effmin
        qty90 = self.repo.get_qty_terjual_per_produk(_dt.now() - _td(days=90))
        _cfg = self.db.get(_MKC, 1)
        lead = int(getattr(_cfg, "lead_time_hari", 14) or 14)
        safety = int(getattr(_cfg, "safety_hari", 7) or 7)
        n = 0
        for p in self.repo.list_all_produk_active():
            stok = float(p.stok_terkini or 0)
            q90 = qty90.get(p.id_produk, 0.0)
            eff = _effmin(p.stok_minimal, q90, lead, safety)
            if stok <= eff:
                n += 1
        return n


__all__ = ["ApotekService"]
