"""
OpnameService — orchestrator stock opname.

State machine:
    DRAFT ──→ APPROVED  (apply selisih ke stok target + inventory_history PENYESUAIAN)
       │
       └──→ REJECTED  (catat, tidak apply)

Lokasi → target stok:
    RETAIL       → master_produk.stok_terkini
    KABIN        → inventory_stok.stok_kabin
    GUDANG_UTAMA → inventory_stok.stok_gudang_utama

Key behaviors:
- create_opname: validate tipe_item kompatibel dengan lokasi, snapshot qty_sistem
                 saat insert (anti-race kalau stok bergerak antara create dan approve)
- approve: atomic apply selisih per item, write inventory_history dengan
           jenis_mutasi=PENYESUAIAN dan referensi=nomor_opname
- reject: simple state update, no stock change

Audit log aksi: OPNAME_CREATE, OPNAME_APPROVE, OPNAME_REJECT
"""

from datetime import date, datetime
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    JenisMutasiEnum,
    LokasiOpnameEnum,
    MasterStaf,
    StatusOpnameEnum,
    StockOpname,
    StockOpnameItem,
    StokLot,
)
from app.repositories.inventory_repo import InventoryRepository
from app.repositories.opname_repo import OpnameRepository
from app.schemas.pengadaan import (
    StockOpnameCreateRequest,
    StockOpnameRejectRequest,
)
from app.services.audit_service import AuditService


class OpnameService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = OpnameRepository(db)
        self.inv_repo = InventoryRepository(db)
        self.audit = AuditService(db)

    # =========================================================================
    # CREATE OPNAME (status DRAFT)
    # =========================================================================
    def create_opname(
        self,
        payload: StockOpnameCreateRequest,
        actor: MasterStaf,
        request: Optional[Request] = None,
    ) -> StockOpname:
        """
        Validate lokasi vs tipe_item kompatibilitas, snapshot qty_sistem,
        atomic insert header + items dengan status DRAFT.

        Aturan lokasi:
        - RETAIL: hanya boleh tipe_item=PRODUK (master_produk)
        - KABIN/GUDANG_UTAMA: hanya boleh tipe_item=BAHAN (inventory_stok)
        """
        lokasi = payload.lokasi
        lokasi_value = lokasi.value if hasattr(lokasi, "value") else str(lokasi)

        # ----- 1. Build snapshot items -----
        item_models: list[StockOpnameItem] = []
        for idx, it in enumerate(payload.items):
            tipe_value = it.tipe_item.value if hasattr(it.tipe_item, "value") else str(it.tipe_item)

            # Kompatibilitas lokasi vs tipe
            if lokasi_value == "RETAIL" and tipe_value != "PRODUK":
                raise HTTPException(
                    400,
                    f"Item #{idx+1}: lokasi RETAIL hanya untuk PRODUK, bukan {tipe_value}.",
                )
            if lokasi_value in ("KABIN", "GUDANG_UTAMA") and tipe_value != "BAHAN":
                raise HTTPException(
                    400,
                    f"Item #{idx+1}: lokasi {lokasi_value} hanya untuk BAHAN, bukan {tipe_value}.",
                )

            # Resolve nama snapshot + qty_sistem snapshot
            nama_snap = ""
            qty_sistem = 0.0
            id_lot_val = None
            batch_val = None
            ed_val = None
            if tipe_value == "PRODUK":
                if it.id_produk is None:
                    raise HTTPException(400, f"Item #{idx+1}: id_produk wajib untuk PRODUK.")
                from app.db.models import MasterProduk as _MP
                produk = self.db.get(_MP, it.id_produk)
                if produk is None:
                    raise HTTPException(404, f"Item #{idx+1}: Produk id={it.id_produk} tidak ditemukan.")
                nama_snap = produk.nama_produk
                # P-L9 per-batch: id_lot terisi = hitung lot itu (snapshot qty_sisa lot).
                # id_lot kosong = "batch baru ditemukan" saat opname (sistem=0, buat lot saat approve).
                if it.id_lot is not None:
                    lot = self.db.get(StokLot, it.id_lot)
                    if lot is None:
                        raise HTTPException(404, f"Item #{idx+1}: Lot id={it.id_lot} tidak ditemukan.")
                    qty_sistem = float(lot.qty_sisa or 0)
                    id_lot_val = lot.id_lot
                    batch_val = lot.batch_no
                    ed_val = lot.tgl_ed
                else:
                    qty_sistem = 0.0
                    batch_val = (it.batch_no or None)
                    ed_val = it.tgl_ed
            else:  # BAHAN (tetap agregat, path lama)
                if it.id_bahan is None:
                    raise HTTPException(400, f"Item #{idx+1}: id_bahan wajib untuk BAHAN.")
                from app.db.models import InventoryStok as _IS
                bahan = self.db.get(_IS, it.id_bahan)
                if bahan is None:
                    raise HTTPException(404, f"Item #{idx+1}: Bahan id={it.id_bahan} tidak ditemukan.")
                nama_snap = bahan.nama_bahan
                qty_sistem = self.repo.get_stok_sistem_bahan(it.id_bahan, lokasi)

            item_models.append(StockOpnameItem(
                tipe_item=tipe_value,
                id_produk=it.id_produk if tipe_value == "PRODUK" else None,
                id_bahan=it.id_bahan if tipe_value == "BAHAN" else None,
                id_lot=id_lot_val,
                batch_no=batch_val,
                tgl_ed=ed_val,
                nama_snapshot=nama_snap,
                qty_sistem=qty_sistem,
                qty_fisik=float(it.qty_fisik),
                catatan_item=it.catatan_item,
            ))

        # ----- 2. Generate nomor + create header -----
        nomor = self.repo.generate_next_nomor()
        opname = StockOpname(
            nomor_opname=nomor,
            tgl_opname=datetime.now(),
            lokasi=lokasi,
            status=StatusOpnameEnum.DRAFT,
            id_staf_pelaksana=actor.id_staf,
            catatan=payload.catatan,
        )

        try:
            self.repo.create_with_items(opname, item_models)
            self.audit.log_create(
                id_staf=actor.id_staf,
                tabel="stock_opname",
                id_target=opname.id_opname,
                data_baru={
                    "nomor_opname": opname.nomor_opname,
                    "lokasi": lokasi_value,
                    "status": "DRAFT",
                    "jumlah_item": len(item_models),
                },
                request=request,
            )
            self.db.commit()
            self.db.refresh(opname)
            return opname
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal create opname: {e!s}")

    # =========================================================================
    # APPROVE — apply selisih ke stok
    # =========================================================================
    def approve(
        self,
        id_opname: int,
        actor: MasterStaf,
        request: Optional[Request] = None,
    ) -> dict:
        """
        Atomic apply selisih per item:
        1. Lock target stok (master_produk atau inventory_stok) FOR UPDATE
        2. Hitung selisih = qty_fisik - qty_sistem_saat_opname (snapshot)
           Note: kita PAKAI qty_sistem snapshot, bukan stok saat ini, supaya
           opname konsisten dengan kondisi saat fisik dicek.
        3. Apply selisih ke stok target
        4. Insert inventory_history (jenis=PENYESUAIAN, referensi=nomor_opname)
        5. Audit log per item + opname-level
        """
        # KUNCI BARIS — pagar `status != DRAFT` di bawah ini tidak berlaku
        # di bawah konkurensi tanpa ini (Temuan 20).
        opname = self.repo.get_by_id_for_update(id_opname)
        if opname is None:
            raise HTTPException(404, f"Opname {id_opname} tidak ditemukan.")
        if opname.status != StatusOpnameEnum.DRAFT:
            raise HTTPException(
                400,
                f"Opname status {opname.status.value} — hanya DRAFT yang bisa di-approve.",
            )

        items = self.repo.get_items_by_opname(id_opname)
        if not items:
            raise HTTPException(400, "Opname tidak punya item. Tidak bisa di-approve.")

        lokasi = opname.lokasi
        lokasi_value = lokasi.value if hasattr(lokasi, "value") else str(lokasi)
        items_applied = []
        total_selisih_qty = 0.0

        try:
            for it in items:
                selisih = float(it.qty_fisik) - float(it.qty_sistem)
                if selisih == 0:
                    continue  # match, no apply

                # Lock + apply
                stok_sebelum = 0.0
                stok_sesudah = 0.0
                if it.tipe_item == "PRODUK":
                    # P-L9: terapkan selisih ke LOT spesifik, lalu recompute cache stok_terkini.
                    if it.id_lot is not None:
                        lot = self.db.get(StokLot, it.id_lot)
                        if lot is None:
                            continue
                        lot.qty_sisa = float(lot.qty_sisa or 0) + selisih
                        if lot.qty_sisa <= 1e-6:
                            lot.qty_sisa = 0
                            lot.status = "HABIS"
                    else:
                        # "batch baru ditemukan": hanya buat lot kalau fisik (selisih) > 0
                        if selisih <= 1e-6:
                            continue
                        lot = StokLot(
                            tipe_item="PRODUK",
                            id_produk=it.id_produk,
                            lokasi="RETAIL",
                            batch_no=(it.batch_no or None),
                            tgl_ed=it.tgl_ed,
                            qty_masuk=selisih,
                            qty_sisa=selisih,
                            status="AKTIF",
                            tgl_masuk=date.today(),
                        )
                        self.db.add(lot)
                    self.db.flush()
                    # Recompute cache = Σ qty_sisa lot AKTIF produk (lokasi RETAIL)
                    produk = self.repo.get_produk_for_update(it.id_produk)
                    if produk is None:
                        continue
                    stok_sebelum = float(produk.stok_terkini or 0)
                    new_total = float(self.db.execute(
                        select(func.coalesce(func.sum(StokLot.qty_sisa), 0)).where(
                            StokLot.tipe_item == "PRODUK",
                            StokLot.id_produk == it.id_produk,
                            StokLot.lokasi == "RETAIL",
                            StokLot.status == "AKTIF",
                        )
                    ).scalar() or 0)
                    produk.stok_terkini = new_total
                    stok_sesudah = new_total
                    self.db.flush()
                    self.inv_repo.add_history(
                        tipe_item="PRODUK",
                        id_produk=it.id_produk,
                        id_staf=actor.id_staf,
                        jenis=JenisMutasiEnum.PENYESUAIAN,
                        qty_perubahan=selisih,
                        stok_akhir=stok_sesudah,
                        referensi=opname.nomor_opname,
                        keterangan=(
                            f"Opname {opname.nomor_opname} {lokasi_value} "
                            f"batch={it.batch_no or '-'}: {it.nama_snapshot} "
                            f"fisik={it.qty_fisik} sistem={it.qty_sistem} selisih={selisih:+g}"
                        ),
                    )
                else:  # BAHAN
                    bahan = self.repo.get_bahan_for_update(it.id_bahan)
                    if bahan is None:
                        continue
                    # Apply ke lokasi yang benar
                    if lokasi_value == "KABIN":
                        stok_sebelum = float(bahan.stok_kabin or 0)
                        bahan.stok_kabin = stok_sebelum + selisih
                        stok_sesudah = bahan.stok_kabin
                    else:  # GUDANG_UTAMA
                        stok_sebelum = float(bahan.stok_gudang_utama or 0)
                        bahan.stok_gudang_utama = stok_sebelum + selisih
                        stok_sesudah = bahan.stok_gudang_utama
                    self.db.flush()
                    self.inv_repo.add_history(
                        tipe_item="BAHAN",
                        id_bahan=it.id_bahan,
                        id_staf=actor.id_staf,
                        jenis=JenisMutasiEnum.PENYESUAIAN,
                        qty_perubahan=selisih,
                        stok_akhir=stok_sesudah,
                        referensi=opname.nomor_opname,
                        keterangan=(
                            f"Opname {opname.nomor_opname} {lokasi_value}: "
                            f"{it.nama_snapshot} fisik={it.qty_fisik} sistem={it.qty_sistem} "
                            f"selisih={selisih:+g}"
                        ),
                    )

                items_applied.append({
                    "id_opname_item": it.id_opname_item,
                    "nama_snapshot": it.nama_snapshot,
                    "tipe_item": it.tipe_item,
                    "selisih": selisih,
                    "stok_sebelum": stok_sebelum,
                    "stok_sesudah": stok_sesudah,
                })
                total_selisih_qty += selisih

            # Update status header + audit
            self.repo.update_status(
                opname=opname,
                status_baru=StatusOpnameEnum.APPROVED,
                id_staf_approver=actor.id_staf,
            )
            self.audit.log(
                aksi="OPNAME_APPROVE",
                id_staf=actor.id_staf,
                tabel_target="stock_opname",
                id_target=id_opname,
                data_lama={"status": "DRAFT"},
                data_baru={
                    "status": "APPROVED",
                    "items_terapan": len(items_applied),
                    "total_selisih_qty": total_selisih_qty,
                },
                keterangan=(
                    f"Opname {opname.nomor_opname} lokasi {lokasi_value} approved. "
                    f"{len(items_applied)} item terapan selisih ke stok."
                ),
                request=request,
            )
            self.db.commit()
            self.db.refresh(opname)
            return {
                "status": "success",
                "message": (
                    f"Opname {opname.nomor_opname} approved. "
                    f"{len(items_applied)} item ter-apply selisih ke stok."
                ),
                "data": {
                    "id_opname": id_opname,
                    "nomor_opname": opname.nomor_opname,
                    "items_applied": len(items_applied),
                    "total_selisih_qty": total_selisih_qty,
                    "items_detail": items_applied,
                },
            }
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal approve opname: {e!s}")

    # =========================================================================
    # REJECT (no stock change)
    # =========================================================================
    def reject(
        self,
        id_opname: int,
        payload: StockOpnameRejectRequest,
        actor: MasterStaf,
        request: Optional[Request] = None,
    ) -> StockOpname:
        # KUNCI BARIS — pagar `status != DRAFT` di bawah ini tidak berlaku
        # di bawah konkurensi tanpa ini (Temuan 20).
        opname = self.repo.get_by_id_for_update(id_opname)
        if opname is None:
            raise HTTPException(404, f"Opname {id_opname} tidak ditemukan.")
        if opname.status != StatusOpnameEnum.DRAFT:
            raise HTTPException(
                400,
                f"Opname status {opname.status.value} — hanya DRAFT yang bisa di-reject.",
            )
        try:
            self.repo.update_status(
                opname=opname,
                status_baru=StatusOpnameEnum.REJECTED,
                id_staf_approver=actor.id_staf,
            )
            self.audit.log(
                aksi="OPNAME_REJECT",
                id_staf=actor.id_staf,
                tabel_target="stock_opname",
                id_target=id_opname,
                data_lama={"status": "DRAFT"},
                data_baru={"status": "REJECTED"},
                keterangan=(
                    f"Opname {opname.nomor_opname} rejected. Alasan: {payload.alasan}"
                ),
                request=request,
            )
            self.db.commit()
            self.db.refresh(opname)
            return opname
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal reject opname: {e!s}")


__all__ = ["OpnameService"]
