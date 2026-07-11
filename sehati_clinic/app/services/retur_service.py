"""
ReturService — retur produk ke distributor (RT-L2/L3).

create_retur: header + item (pilih LOT manual, snapshot batch/ED/harga) status DRAFT.
approve_retur: RBAC luas → POTONG lot qty_sisa per item + recompute cache stok_terkini + inventory_history
               (PENYESUAIAN, keterangan RETUR) → status APPROVED.
input_nota: TUKAR_BARANG → buat lot pengganti; REFUND → catat nota header → status SELESAI. (RT-L3)
Ref RETUR_MODULE_DESIGN §7/§8.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    JenisMutasiEnum,
    KlinikApoteker,
    MasterProduk,
    MasterStaf,
    ReturProduk,
    ReturProdukItem,
    StokLot,
)
from app.repositories.inventory_repo import InventoryRepository
from app.services.audit_service import AuditService

_EPS = 1e-6


class ReturService:
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService(db)
        self.inv_repo = InventoryRepository(db)

    def _gen_nomor(self) -> str:
        prefix = f"RT-{datetime.now().strftime('%y%m%d')}-"
        last = (self.db.query(ReturProduk)
                .filter(ReturProduk.nomor_retur.like(prefix + "%"))
                .order_by(ReturProduk.nomor_retur.desc()).first())
        n = 1
        if last:
            try:
                n = int(last.nomor_retur.split("-")[-1]) + 1
            except (ValueError, IndexError):
                n = 1
        return f"{prefix}{n:03d}"

    def _recompute_produk_cache(self, id_produk: int) -> float:
        total = float(self.db.execute(
            select(func.coalesce(func.sum(StokLot.qty_sisa), 0)).where(
                StokLot.tipe_item == "PRODUK", StokLot.id_produk == id_produk,
                StokLot.lokasi == "RETAIL", StokLot.status == "AKTIF",
            )
        ).scalar() or 0)
        produk = self.db.get(MasterProduk, id_produk)
        if produk is not None:
            produk.stok_terkini = total
            self.db.flush()
        return total

    # -------------------------------------------------------------------------
    def create_retur(self, id_distributor: Optional[int], alasan: Optional[str],
                     items_input: list, actor: MasterStaf, id_apoteker: Optional[int] = None,
                     request: Optional[Request] = None) -> ReturProduk:
        """items_input: list dict {id_lot, qty, alasan_item}."""
        ap_nama = ap_sipa = None
        if id_apoteker is not None:
            ap = self.db.get(KlinikApoteker, id_apoteker)
            if ap is None or not ap.is_active:
                raise HTTPException(400, "Apoteker tidak ditemukan atau tidak aktif.")
            ap_nama, ap_sipa = ap.nama_apoteker, ap.no_sipa
        retur = ReturProduk(
            nomor_retur=self._gen_nomor(),
            tgl_retur=datetime.now(),
            id_distributor=id_distributor,
            alasan=(alasan or "").strip() or None,
            status="DRAFT",
            id_staf_pembuat=actor.id_staf,
            id_apoteker=id_apoteker,
            apoteker_nama=ap_nama,
            apoteker_sipa=ap_sipa,
        )
        item_models = []
        for it in items_input:
            id_lot = it.get("id_lot")
            qty = float(it.get("qty") or 0)
            if id_lot is None or qty <= 0:
                continue
            lot = self.db.get(StokLot, id_lot)
            if lot is None:
                raise HTTPException(404, f"Lot {id_lot} tidak ditemukan.")
            if qty > float(lot.qty_sisa or 0) + _EPS:
                raise HTTPException(400, f"Qty retur ({qty}) melebihi sisa lot ({lot.qty_sisa}) "
                                         f"batch {lot.batch_no or '-'}.")
            produk = self.db.get(MasterProduk, lot.id_produk) if lot.id_produk else None
            item_models.append(ReturProdukItem(
                id_produk=lot.id_produk, id_lot=lot.id_lot,
                nama_snapshot=produk.nama_produk if produk else "-",
                batch_no=lot.batch_no, tgl_ed=lot.tgl_ed, qty=qty,
                harga_terima=lot.harga_terima,
                alasan_item=(it.get("alasan_item") or "").strip() or None,
            ))
        if not item_models:
            raise HTTPException(400, "Minimal 1 item (lot + qty) untuk retur.")
        retur.items = item_models
        try:
            self.db.add(retur)
            self.db.flush()
            self.audit.log_create(id_staf=actor.id_staf, tabel="retur_produk", id_target=retur.id_retur,
                                  data_baru={"nomor_retur": retur.nomor_retur, "jumlah_item": len(item_models)},
                                  request=request)
            self.db.commit()
            self.db.refresh(retur)
            return retur
        except HTTPException:
            self.db.rollback(); raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal buat retur: {e!s}")

    def approve_retur(self, id_retur: int, actor: MasterStaf,
                      request: Optional[Request] = None) -> ReturProduk:
        retur = self.db.get(ReturProduk, id_retur)
        if retur is None:
            raise HTTPException(404, f"Retur {id_retur} tidak ditemukan.")
        if retur.status != "DRAFT":
            raise HTTPException(400, f"Retur status {retur.status} — hanya DRAFT yang bisa di-approve.")
        items = self.db.query(ReturProdukItem).filter(ReturProdukItem.id_retur == id_retur).all()
        if not items:
            raise HTTPException(400, "Retur tidak punya item.")
        try:
            for it in items:
                if it.id_lot is None:
                    continue
                lot = self.db.get(StokLot, it.id_lot)
                if lot is None:
                    raise HTTPException(400, f"Lot batch {it.batch_no or '-'} sudah tak ada.")
                qty = float(it.qty)
                sisa = float(lot.qty_sisa or 0)
                if qty > sisa + _EPS:
                    raise HTTPException(400, f"Qty retur {qty} melebihi sisa lot {sisa} "
                                             f"(batch {lot.batch_no or '-'}) — stok berubah sejak draft.")
                lot.qty_sisa = sisa - qty
                if lot.qty_sisa <= _EPS:
                    lot.qty_sisa = 0
                    lot.status = "HABIS"
                self.db.flush()
                if lot.id_produk:
                    new_total = self._recompute_produk_cache(lot.id_produk)
                    self.inv_repo.add_history(
                        tipe_item="PRODUK", id_produk=lot.id_produk, id_staf=actor.id_staf,
                        jenis=JenisMutasiEnum.PENYESUAIAN, qty_perubahan=-qty, stok_akhir=new_total,
                        referensi=retur.nomor_retur,
                        keterangan=(f"RETUR {retur.nomor_retur} ke distributor: {it.nama_snapshot} "
                                    f"batch {it.batch_no or '-'} qty {qty:g}"),
                    )
            retur.status = "APPROVED"
            retur.id_staf_approver = actor.id_staf
            retur.tgl_approve = datetime.now()
            self.audit.log(aksi="RETUR_APPROVE", id_staf=actor.id_staf, tabel_target="retur_produk",
                           id_target=id_retur, data_lama={"status": "DRAFT"}, data_baru={"status": "APPROVED"},
                           keterangan=f"Retur {retur.nomor_retur} approved — lot dipotong.", request=request)
            self.db.commit()
            self.db.refresh(retur)
            return retur
        except HTTPException:
            self.db.rollback(); raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal approve retur: {e!s}")


    # -------------------------------------------------------------------------
    # RT-L3 — input NOTA RETUR (respon distributor)
    # -------------------------------------------------------------------------
    def _validate_for_nota(self, id_retur: int) -> "ReturProduk":
        r = self.db.get(ReturProduk, id_retur)
        if r is None:
            raise HTTPException(404, f"Retur {id_retur} tidak ditemukan.")
        if r.status != "APPROVED":
            raise HTTPException(400, f"Nota hanya bisa diinput untuk retur APPROVED (kini {r.status}).")
        return r

    def input_nota_refund(self, id_retur: int, nomor_nota, tgl_nota, total_nilai,
                          catatan, actor: MasterStaf, request: Optional[Request] = None) -> ReturProduk:
        """Refund uang: catat nota header, tutup retur (ke finance). Tanpa perubahan stok."""
        r = self._validate_for_nota(id_retur)
        try:
            r.jenis_penyelesaian = "REFUND"
            r.nomor_nota = (nomor_nota or "").strip() or None
            r.tgl_nota = tgl_nota
            r.total_nilai = total_nilai
            if catatan:
                r.catatan = ((r.catatan or "") + " | " + catatan).strip(" |")
            r.status = "SELESAI"
            self.audit.log(aksi="RETUR_NOTA_REFUND", id_staf=actor.id_staf, tabel_target="retur_produk",
                           id_target=id_retur, data_baru={"jenis": "REFUND", "total_nilai": str(total_nilai or "")},
                           keterangan=f"Retur {r.nomor_retur} SELESAI (refund). Nota {r.nomor_nota or '-'}.",
                           request=request)
            self.db.commit()
            self.db.refresh(r)
            return r
        except HTTPException:
            self.db.rollback(); raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal input nota refund: {e!s}")

    def input_nota_tukar(self, id_retur: int, nomor_nota, tgl_nota, replacements: list,
                         actor: MasterStaf, request: Optional[Request] = None) -> ReturProduk:
        """Tukar barang: barang pengganti (produk sama, batch/ED/qty/harga baru) MASUK LOT."""
        r = self._validate_for_nota(id_retur)
        try:
            total = Decimal("0")
            n_lot = 0
            for rep in replacements:
                id_produk = rep.get("id_produk")
                qty = float(rep.get("qty") or 0)
                if id_produk is None or qty <= 0:
                    continue
                harga = rep.get("harga")
                lot = StokLot(
                    tipe_item="PRODUK", id_produk=int(id_produk), lokasi="RETAIL",
                    batch_no=(rep.get("batch") or None), tgl_ed=rep.get("ed"),
                    qty_masuk=qty, qty_sisa=qty, harga_terima=harga,
                    status="AKTIF", tgl_masuk=date.today(),
                )
                self.db.add(lot)
                self.db.flush()
                new_total = self._recompute_produk_cache(int(id_produk))
                self.inv_repo.add_history(
                    tipe_item="PRODUK", id_produk=int(id_produk), id_staf=actor.id_staf,
                    jenis=JenisMutasiEnum.RESTOCK, qty_perubahan=qty, stok_akhir=new_total,
                    referensi=r.nomor_retur,
                    keterangan=(f"RETUR TUKAR {r.nomor_retur}: barang pengganti batch "
                                f"{rep.get('batch') or '-'} qty {qty:g}"),
                )
                if harga is not None:
                    total += Decimal(str(harga)) * Decimal(str(qty))
                n_lot += 1
            if n_lot == 0:
                raise HTTPException(400, "Minimal 1 barang pengganti (produk + qty).")
            r.jenis_penyelesaian = "TUKAR_BARANG"
            r.nomor_nota = (nomor_nota or "").strip() or None
            r.tgl_nota = tgl_nota
            r.total_nilai = total
            r.status = "SELESAI"
            self.audit.log(aksi="RETUR_NOTA_TUKAR", id_staf=actor.id_staf, tabel_target="retur_produk",
                           id_target=id_retur, data_baru={"jenis": "TUKAR_BARANG", "lot_baru": n_lot},
                           keterangan=f"Retur {r.nomor_retur} SELESAI (tukar). {n_lot} lot pengganti dibuat.",
                           request=request)
            self.db.commit()
            self.db.refresh(r)
            return r
        except HTTPException:
            self.db.rollback(); raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal input nota tukar: {e!s}")


__all__ = ["ReturService"]
