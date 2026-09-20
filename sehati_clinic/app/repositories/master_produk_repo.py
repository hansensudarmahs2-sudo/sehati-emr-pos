"""
MasterProdukRepository — CRUD untuk master_produk.

Plus query helper untuk list+filter & restock dengan FOR UPDATE lock.
"""

from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import MasterProduk


class MasterProdukRepository:
    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # READ
    # =========================================================================
    def get_by_id(self, id_produk: int) -> Optional[MasterProduk]:
        return self.db.get(MasterProduk, id_produk)

    def get_by_kode(self, kode: str) -> Optional[MasterProduk]:
        """Untuk unique check saat create / update."""
        stmt = select(MasterProduk).where(MasterProduk.kode_produk == kode).limit(1)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_for_update(self, id_produk: int) -> Optional[MasterProduk]:
        """SELECT ... FOR UPDATE — untuk restock (anti race condition)."""
        stmt = (
            select(MasterProduk)
            .where(MasterProduk.id_produk == id_produk)
            .with_for_update()
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_with_filter(
        self,
        keyword: Optional[str] = None,
        tipe: Optional[str] = None,
        only_active: bool = False,
        limit: int = 100,
    ) -> list[MasterProduk]:
        """
        List produk dengan filter optional.

        - keyword: cari di kode_produk / nama_produk / kandungan / golongan (case-insensitive)
        - tipe: RETAIL / CABIN / ALAT
        - only_active: hanya is_active=True
        """
        stmt = select(MasterProduk)
        if keyword and keyword.strip():
            term = f"%{keyword.strip()}%"
            stmt = stmt.where(
                or_(
                    MasterProduk.kode_produk.ilike(term),
                    MasterProduk.nama_produk.ilike(term),
                    MasterProduk.kandungan.ilike(term),
                    MasterProduk.golongan.ilike(term),
                )
            )
        if tipe:
            stmt = stmt.where(MasterProduk.tipe_produk == tipe.upper())
        if only_active:
            stmt = stmt.where(MasterProduk.is_active.is_(True))
        stmt = stmt.order_by(MasterProduk.nama_produk.asc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    # =========================================================================
    # CRUD MUTATING
    # =========================================================================
    def create(self, produk: MasterProduk) -> MasterProduk:
        self.db.add(produk)
        self.db.flush()
        return produk

    def update(self, produk: MasterProduk, data: dict) -> MasterProduk:
        """Partial update — only fields present in data."""
        for key, value in data.items():
            if hasattr(produk, key):
                setattr(produk, key, value)
        self.db.flush()
        return produk

    def set_active(self, produk: MasterProduk, is_active: bool) -> MasterProduk:
        produk.is_active = is_active
        self.db.flush()
        return produk

    def add_stok(self, produk: MasterProduk, qty: float) -> float:
        """
        Tambah stok_terkini (positive only — untuk restock).

        Return stok_akhir.
        """
        stok_lama = produk.stok_terkini or 0
        stok_baru = stok_lama + qty
        produk.stok_terkini = stok_baru
        self.db.flush()
        return stok_baru


__all__ = ["MasterProdukRepository"]
