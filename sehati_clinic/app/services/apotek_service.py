"""
ApotekService — antrian, detail, serahkan obat, write-off, suggested order.

Per keputusan dr. Hansen Q1 Week 5:
- Stok produk POS dipotong dari `master_produk.stok_terkini` saja
- Tidak ada inventory_history tracking untuk produk POS (Phase 2+ kalau perlu)
- Stok diizinkan minus (filosofi: operasional jangan diblok)
"""

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.models import StafRoleEnum
from app.repositories.apotek_repo import ApotekRepository
from app.repositories.kunjungan_repo import KunjunganRepository
from app.schemas.apotek import (
    AntrianApotekItem,
    AntrianApotekResponse,
    DetailResepResponse,
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

        return DetailResepResponse(
            id_kunjungan=id_kunjungan,
            id_pasien=pasien.id_pasien,
            no_rm=pasien.no_rm,
            nama_pasien=pasien.nama,
            daftar_obat=items,
            total_item=len(items),
            semua_stok_cukup=semua_cukup,
        )

    def _simpan_lot_terpakai(self, id_kunjungan, id_produk, consumed: list) -> int:
        """H2/P0-1 (AUDIT_SEHATI_2026-07-10): rekam lot FEFO yang dipotong saat serah,
        supaya void bisa mengembalikan qty ke lot ASLI (ED terjaga) — bukan VOID-RETURN.

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
            out.append({
                "id_kunjungan": kj.id_kunjungan,
                "id_pasien": kj.id_pasien,
                "no_rm": pasien.no_rm,
                "nama_pasien": pasien.nama,
                "nomor_telepon": pasien.nomor_telepon or "",
                "tgl_janji_kirim": kj.tgl_janji_kirim,
                "catatan_kirim": kj.catatan_kirim or "",
                "obat": obat,
                "overdue": kj.tgl_janji_kirim is not None and kj.tgl_janji_kirim <= today,
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
        if kunjungan.status_antrian != "ANTRI_OBAT":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Hanya kunjungan 'ANTRI_OBAT' yang bisa ditunda (saat ini '{kunjungan.status_antrian}').",
            )
        if tgl_janji_kirim is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tanggal janji kirim/ambil WAJIB diisi.")
        resep_list = self.repo.get_resep_dibayar_for_serah(id_kunjungan)
        if not resep_list:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tidak ada resep DIBAYAR untuk ditunda.")

        kunjungan.tgl_janji_kirim = tgl_janji_kirim
        kunjungan.catatan_kirim = (catatan or None)
        self.kunjungan_repo.update_status(kunjungan, "COMPLETED")
        self.audit.log(
            aksi="OBAT_TUNDA",
            id_staf=id_staf,
            tabel_target="kunjungan",
            id_target=id_kunjungan,
            data_lama={"status_antrian": "ANTRI_OBAT"},
            data_baru={"status_antrian": "COMPLETED", "tgl_janji_kirim": str(tgl_janji_kirim)},
            keterangan=f"Obat ditunda (kirim/ambil {tgl_janji_kirim}). {len(resep_list)} item. Stok belum dipotong.",
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

        # 2. Ambil daftar resep DIBAYAR (yang siap diserahkan)
        resep_list = self.repo.get_resep_dibayar_for_serah(payload.id_kunjungan)
        if not resep_list:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tidak ada resep DIBAYAR di kunjungan ini untuk diserahkan.",
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
                self._simpan_lot_terpakai(payload.id_kunjungan, produk.id_produk, _fefo["consumed"])
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

            # 4. Transition ANTRI_OBAT → COMPLETED (kalau serah normal).
            # Kalau ini serah obat TERTUNDA, kunjungan sudah COMPLETED — cukup bersihkan marker.
            if kunjungan.status_antrian == "ANTRI_OBAT":
                self.kunjungan_repo.update_status(kunjungan, "COMPLETED")
            kunjungan.tgl_janji_kirim = None  # obat sudah benar-benar diserah → keluar dari daftar tertunda

            # 5. AUDIT
            self.audit.log(
                aksi="SERAH_OBAT",
                id_staf=id_staf_apoteker,
                tabel_target="kunjungan",
                id_target=payload.id_kunjungan,
                data_lama={"status_antrian": "ANTRI_OBAT"},
                data_baru={"status_antrian": "COMPLETED"},
                keterangan=(
                    f"Serah obat oleh apoteker_id={id_staf_apoteker}. "
                    f"Jumlah item: {len(items_dipotong)}. "
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
                    "Perjalanan pasien SELESAI."
                    + (" \u26a0 Perhatian: " + "; ".join(shortfall_warnings) if shortfall_warnings else "")
                ),
                "data": {
                    "id_kunjungan": payload.id_kunjungan,
                    "jumlah_item": len(items_dipotong),
                    "items_dipotong": [i.model_dump() for i in items_dipotong],
                    "status_kunjungan_baru": "COMPLETED",
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
