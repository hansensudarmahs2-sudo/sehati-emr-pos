"""
InventoryLotService — engine FEFO untuk stok_lot (P-L5).

FEFO = First-Expired-First-Out: keluar dari lot dengan ED terdekat dulu.
Aturan urutan: tgl_ed ASC, lot ED NULL PALING AKHIR (unknown expiry jangan diprioritaskan keluar),
tie-break tgl_masuk ASC (FIFO), lalu id_lot.

Toleransi masa transisi: kalau total lot < qty diminta (mis. penjualan lama belum kurangi lot),
`consume_fefo` mengurangi yang tersedia + kembalikan `shortfall` (TIDAK memblokir alur; cache
stok_terkini tetap otoritas 'stok cukup' sampai FEFO tuntas di-wire di semua titik).
"""
from typing import Optional

from sqlalchemy import select

from app.db.models import StokLot

_EPS = 1e-6


class InventoryLotService:
    def __init__(self, db):
        self.db = db

    def _query_fefo(self, tipe_item, id_produk, id_bahan, lokasi):
        conds = [
            StokLot.status == "AKTIF",
            StokLot.qty_sisa > 0,
            StokLot.lokasi == lokasi,
            StokLot.tipe_item == tipe_item,
        ]
        if tipe_item == "PRODUK":
            conds.append(StokLot.id_produk == id_produk)
        else:
            conds.append(StokLot.id_bahan == id_bahan)
        return (
            select(StokLot).where(*conds)
            .order_by(
                StokLot.tgl_ed.is_(None),   # False (ada ED) dulu, True (NULL) terakhir
                StokLot.tgl_ed.asc(),
                StokLot.tgl_masuk.asc(),
                StokLot.id_lot.asc(),
            )
        )

    def peek_fefo(self, *, tipe_item: str, lokasi: str, qty: float,
                  id_produk: Optional[int] = None, id_bahan: Optional[int] = None) -> list:
        """Lihat lot MANA yang akan dipotong FEFO (tanpa mengubah). Untuk preview UI."""
        qty = float(qty or 0)
        if qty <= 0:
            return []
        lots = self.db.execute(self._query_fefo(tipe_item, id_produk, id_bahan, lokasi)).scalars().all()
        out = []
        remaining = qty
        for lot in lots:
            if remaining <= _EPS:
                break
            take = min(float(lot.qty_sisa or 0), remaining)
            if take <= 0:
                continue
            out.append({"id_lot": lot.id_lot, "batch_no": lot.batch_no, "tgl_ed": lot.tgl_ed, "qty": take})
            remaining -= take
        return out

    def consume_fefo(self, *, tipe_item: str, lokasi: str, qty: float,
                     id_produk: Optional[int] = None, id_bahan: Optional[int] = None) -> dict:
        """Potong stok FEFO. Return {'consumed': [...], 'shortfall': float}. FLUSH (caller commit)."""
        qty = float(qty or 0)
        if qty <= 0:
            return {"consumed": [], "shortfall": 0.0}
        lots = self.db.execute(self._query_fefo(tipe_item, id_produk, id_bahan, lokasi)).scalars().all()
        consumed = []
        remaining = qty
        for lot in lots:
            if remaining <= _EPS:
                break
            take = min(float(lot.qty_sisa or 0), remaining)
            if take <= 0:
                continue
            lot.qty_sisa = float(lot.qty_sisa or 0) - take
            if lot.qty_sisa <= _EPS:
                lot.qty_sisa = 0
                lot.status = "HABIS"
            remaining -= take
            consumed.append({"id_lot": lot.id_lot, "batch_no": lot.batch_no, "tgl_ed": lot.tgl_ed, "qty": take})
        if consumed:
            self.db.flush()
        return {"consumed": consumed, "shortfall": (remaining if remaining > _EPS else 0.0)}


__all__ = ["InventoryLotService"]
