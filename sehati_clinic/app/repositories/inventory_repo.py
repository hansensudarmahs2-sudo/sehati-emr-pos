"""
InventoryRepository — operasi stok & history.

Critical: pakai SELECT ... FOR UPDATE untuk hindari race kalau 2 perawat
end_treatment bersamaan untuk bahan yang sama.
"""

from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import InventoryHistory, InventoryStok, JenisMutasiEnum


class InventoryRepository:
    """CRUD stok kabin + buku riwayat mutasi."""

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # Lock-aware get stok (FOR UPDATE)
    # =========================================================================
    def get_stok_for_update(self, id_bahan: int) -> Optional[InventoryStok]:
        """
        SELECT ... FOR UPDATE — lock baris stok ini sampai transaksi commit/rollback.

        Pertahankan logika dokter lama (line 1521) — penting untuk 2 perawat
        end_treatment bersamaan.
        """
        stmt = (
            select(InventoryStok)
            .where(InventoryStok.id_bahan == id_bahan)
            .with_for_update()
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_stok(self, id_bahan: int) -> Optional[InventoryStok]:
        return self.db.get(InventoryStok, id_bahan)

    # =========================================================================
    # CRUD master bahan — untuk halaman Master Bahan (Owner/Superadmin)
    # =========================================================================
    def list_all(
        self, keyword: Optional[str] = None, limit: int = 500
    ) -> list[InventoryStok]:
        """List semua bahan klinik dengan filter optional."""
        stmt = select(InventoryStok)
        if keyword and keyword.strip():
            term = f"%{keyword.strip()}%"
            stmt = stmt.where(InventoryStok.nama_bahan.ilike(term))
        stmt = stmt.order_by(InventoryStok.nama_bahan.asc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def create_bahan(self, bahan: InventoryStok) -> InventoryStok:
        self.db.add(bahan)
        self.db.flush()
        return bahan

    def update_bahan(self, bahan: InventoryStok, data: dict) -> InventoryStok:
        for k, v in data.items():
            if hasattr(bahan, k):
                setattr(bahan, k, v)
        self.db.flush()
        return bahan

    # =========================================================================
    # Update stok kabin
    # =========================================================================
    def update_stok_kabin(
        self,
        bahan: InventoryStok,
        delta: float,
    ) -> float:
        """
        Kurangi (atau tambah) stok_kabin. Return stok_akhir setelah update.

        `delta` negatif untuk POTONG (mis. delta=-2.5).
        Stok diizinkan minus per filosofi dokter (operasional jangan diblok).
        """
        stok_lama = bahan.stok_kabin or 0
        stok_baru = stok_lama + delta
        bahan.stok_kabin = stok_baru
        self.db.flush()
        return stok_baru

    # =========================================================================
    # Tulis ke buku riwayat
    # =========================================================================
    def add_history(
        self,
        id_staf: int,
        jenis: JenisMutasiEnum,
        qty_perubahan: float,
        stok_akhir: float,
        id_bahan: Optional[int] = None,
        id_produk: Optional[int] = None,
        tipe_item: str = "BAHAN",
        referensi: Optional[str] = None,
        keterangan: Optional[str] = None,
    ) -> InventoryHistory:
        """
        Polymorphic — bisa untuk BAHAN (inventory_stok) atau PRODUK (master_produk).

        Default tipe_item='BAHAN' supaya backward compat dengan caller existing
        (mis. InventoryService.deduct_for_treatment yang cuma kirim id_bahan).

        Untuk PRODUK: pass tipe_item='PRODUK' + id_produk.
        XOR constraint dijaga DB (chk_inv_hist_xor).
        """
        entry = InventoryHistory(
            tipe_item=tipe_item,
            id_bahan=id_bahan,
            id_produk=id_produk,
            id_staf=id_staf,
            jenis_mutasi=jenis,
            qty_perubahan=qty_perubahan,
            stok_akhir=stok_akhir,
            referensi=referensi,
            keterangan=keterangan,
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    # =========================================================================
    # CRUD master bahan — untuk halaman Master Bahan (Owner/Superadmin)
    # =========================================================================
    def list_all(
        self, keyword: Optional[str] = None, limit: int = 500
    ) -> list[InventoryStok]:
        """List semua bahan klinik dengan filter optional."""
        stmt = select(InventoryStok)
        if keyword and keyword.strip():
            term = f"%{keyword.strip()}%"
            stmt = stmt.where(InventoryStok.nama_bahan.ilike(term))
        stmt = stmt.order_by(InventoryStok.nama_bahan.asc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def create_bahan(self, bahan: InventoryStok) -> InventoryStok:
        self.db.add(bahan)
        self.db.flush()
        return bahan

    def update_bahan(self, bahan: InventoryStok, data: dict) -> InventoryStok:
        for k, v in data.items():
            if hasattr(bahan, k):
                setattr(bahan, k, v)
        self.db.flush()
        return bahan


__all__ = ["InventoryRepository"]
