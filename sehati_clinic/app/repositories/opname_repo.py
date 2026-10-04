"""
OpnameRepository — CRUD untuk stock_opname + items + helper stok snapshot.

Critical patterns:
- generate_next_nomor_opname: FOR UPDATE counter pattern (sama dengan PO)
- create_with_items: atomic insert header + items
- get_stok_snapshot: ambil stok sistem saat ini untuk pre-fill qty_sistem
"""

from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    InventoryStok,
    LokasiOpnameEnum,
    MasterProduk,
    MasterStaf,
    StatusOpnameEnum,
    StockOpname,
    StockOpnameItem,
)


class OpnameRepository:
    """CRUD stock_opname + items."""

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # GET
    # =========================================================================
    def get_by_id(self, id_opname: int) -> Optional[StockOpname]:
        return self.db.get(StockOpname, id_opname)

    def get_by_id_for_update(self, id_opname: int) -> Optional[StockOpname]:
        """SELECT ... FOR UPDATE — kunci baris opname sampai transaksi commit.

        Dipakai approve & reject. Tanpa ini, pagar `status != DRAFT` TIDAK BERLAKU
        di bawah konkurensi: dua approve bersamaan sama-sama membaca DRAFT dan
        sama-sama jalan. Terbukti 2026-10-04 — dua lot penyesuaian dibuat untuk
        satu opname, sementara `stok_terkini` menulis angka satu-approve, sehingga
        buku lot (10) dan cache stok (5) BERSELISIH tanpa error apa pun.
        Lihat `AUDIT_ALUR_UANG_2026-10-04.md` Temuan 20.

        Penamaannya mengikuti pola yang sudah ada di proyek ini:
        `apotek_repo.get_produk_for_update`, `inventory_repo.get_stok_for_update`,
        `kunjungan_repo.get_by_id_for_update`.
        """
        return self.db.execute(
            select(StockOpname).where(StockOpname.id_opname == id_opname).with_for_update()
        ).scalar_one_or_none()

    def get_by_nomor(self, nomor: str) -> Optional[StockOpname]:
        stmt = select(StockOpname).where(StockOpname.nomor_opname == nomor).limit(1)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_items_by_opname(self, id_opname: int) -> list[StockOpnameItem]:
        stmt = (
            select(StockOpnameItem)
            .where(StockOpnameItem.id_opname == id_opname)
            .order_by(StockOpnameItem.id_opname_item.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    # =========================================================================
    # NOMOR OPNAME GENERATOR
    # =========================================================================
    def generate_next_nomor(self, today: Optional[date] = None) -> str:
        """Generate nomor opname format OPN-YYMMDD-NNN. FOR UPDATE counter."""
        if today is None:
            today = date.today()
        prefix_full = f"OPN-{today.strftime('%y%m%d')}-"

        stmt = (
            select(StockOpname)
            .where(StockOpname.nomor_opname.like(f"{prefix_full}%"))
            .with_for_update()
        )
        rows = list(self.db.execute(stmt).scalars().all())

        max_counter = 0
        for o in rows:
            try:
                c = int(o.nomor_opname.split("-")[-1])
                if c > max_counter:
                    max_counter = c
            except (ValueError, IndexError):
                continue
        return f"{prefix_full}{max_counter + 1:03d}"

    # =========================================================================
    # CREATE
    # =========================================================================
    def create_with_items(
        self,
        opname: StockOpname,
        items: list[StockOpnameItem],
    ) -> StockOpname:
        """Atomic insert header + items. Caller wajib commit."""
        self.db.add(opname)
        self.db.flush()
        for it in items:
            it.id_opname = opname.id_opname
            self.db.add(it)
        self.db.flush()
        return opname

    # =========================================================================
    # UPDATE
    # =========================================================================
    def update_status(
        self,
        opname: StockOpname,
        status_baru: StatusOpnameEnum,
        id_staf_approver: Optional[int] = None,
        total_selisih_value: Optional[float] = None,
    ) -> StockOpname:
        opname.status = status_baru
        if id_staf_approver is not None:
            opname.id_staf_approver = id_staf_approver
            opname.tgl_approve = datetime.now()
        if total_selisih_value is not None:
            opname.total_selisih_value = total_selisih_value
        self.db.flush()
        return opname

    # =========================================================================
    # LIST + FILTER
    # =========================================================================
    def list_with_filter(
        self,
        status: Optional[StatusOpnameEnum] = None,
        lokasi: Optional[LokasiOpnameEnum] = None,
        tgl_dari: Optional[date] = None,
        tgl_sampai: Optional[date] = None,
        limit: int = 100,
    ) -> list[tuple[StockOpname, Optional[MasterStaf], int]]:
        """Return list of (StockOpname, MasterStaf pelaksana, jumlah_item)."""
        stmt = (
            select(StockOpname, MasterStaf)
            .outerjoin(MasterStaf, StockOpname.id_staf_pelaksana == MasterStaf.id_staf)
        )
        conds = []
        if status is not None:
            conds.append(StockOpname.status == status)
        if lokasi is not None:
            conds.append(StockOpname.lokasi == lokasi)
        if tgl_dari is not None:
            conds.append(StockOpname.tgl_opname >= datetime.combine(tgl_dari, time.min))
        if tgl_sampai is not None:
            conds.append(StockOpname.tgl_opname <= datetime.combine(tgl_sampai, time.max))
        if conds:
            stmt = stmt.where(and_(*conds))
        stmt = stmt.order_by(StockOpname.tgl_opname.desc()).limit(limit)
        rows = self.db.execute(stmt).all()

        result = []
        for op, pelaksana in rows:
            count_stmt = (
                select(func.count(StockOpnameItem.id_opname_item))
                .where(StockOpnameItem.id_opname == op.id_opname)
            )
            jumlah = int(self.db.execute(count_stmt).scalar() or 0)
            result.append((op, pelaksana, jumlah))
        return result

    # =========================================================================
    # HELPER untuk service — snapshot stok sistem berdasarkan lokasi
    # =========================================================================
    def get_stok_sistem_produk(self, id_produk: int) -> float:
        """Get stok master_produk.stok_terkini (untuk lokasi RETAIL)."""
        produk = self.db.get(MasterProduk, id_produk)
        return float(produk.stok_terkini or 0) if produk else 0.0

    def get_stok_sistem_bahan(self, id_bahan: int, lokasi: LokasiOpnameEnum) -> float:
        """Get stok inventory_stok.stok_kabin atau stok_gudang_utama berdasarkan lokasi."""
        bahan = self.db.get(InventoryStok, id_bahan)
        if not bahan:
            return 0.0
        if lokasi == LokasiOpnameEnum.KABIN:
            return float(bahan.stok_kabin or 0)
        elif lokasi == LokasiOpnameEnum.GUDANG_UTAMA:
            return float(bahan.stok_gudang_utama or 0)
        else:
            return 0.0

    def get_produk_for_update(self, id_produk: int) -> Optional[MasterProduk]:
        stmt = (
            select(MasterProduk)
            .where(MasterProduk.id_produk == id_produk)
            .with_for_update()
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_bahan_for_update(self, id_bahan: int) -> Optional[InventoryStok]:
        stmt = (
            select(InventoryStok)
            .where(InventoryStok.id_bahan == id_bahan)
            .with_for_update()
        )
        return self.db.execute(stmt).scalar_one_or_none()


__all__ = ["OpnameRepository"]
