"""
PemesananRepository — CRUD untuk pemesanan + queries.

Critical patterns:
- generate_next_nomor_po: FOR UPDATE lock counter harian (anti-race PO-YYMMDD-NNN)
- create_with_items: atomic insert header + items dalam 1 flush
- add_receive_event: append-only audit per receive
- list_with_filter: filter status/tipe/tgl + JOIN nama_staf
"""

from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    InventoryStok,
    MasterProduk,
    MasterStaf,
    Pemesanan,
    PemesananItem,
    PemesananReceive,
    StatusPemesananEnum,
)


class PemesananRepository:
    """CRUD pemesanan + items + receive events."""

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # GET
    # =========================================================================
    def get_by_id(self, id_pemesanan: int) -> Optional[Pemesanan]:
        return self.db.get(Pemesanan, id_pemesanan)

    def get_by_nomor_po(self, nomor_po: str) -> Optional[Pemesanan]:
        stmt = select(Pemesanan).where(Pemesanan.nomor_po == nomor_po).limit(1)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_item_by_id(self, id_item: int) -> Optional[PemesananItem]:
        return self.db.get(PemesananItem, id_item)

    def get_item_for_update(self, id_item: int) -> Optional[PemesananItem]:
        """SELECT ... FOR UPDATE — untuk receive atomic."""
        stmt = (
            select(PemesananItem)
            .where(PemesananItem.id_item == id_item)
            .with_for_update()
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_items_by_po(self, id_pemesanan: int) -> list[PemesananItem]:
        stmt = (
            select(PemesananItem)
            .where(PemesananItem.id_pemesanan == id_pemesanan)
            .order_by(PemesananItem.id_item.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_receives_by_po(
        self, id_pemesanan: int
    ) -> list[tuple[PemesananReceive, Optional[MasterStaf]]]:
        """Receive events untuk 1 PO + JOIN nama staf penerima."""
        stmt = (
            select(PemesananReceive, MasterStaf)
            .outerjoin(MasterStaf, PemesananReceive.id_staf_penerima == MasterStaf.id_staf)
            .where(PemesananReceive.id_pemesanan == id_pemesanan)
            .order_by(PemesananReceive.tgl_terima.desc())
        )
        rows = self.db.execute(stmt).all()
        return [(r, s) for r, s in rows]

    # =========================================================================
    # NOMOR PO GENERATOR — FOR UPDATE counter pattern (sama dengan no_rm)
    # =========================================================================
    def generate_next_nomor_po(self, today: Optional[date] = None) -> str:
        """
        Generate nomor PO format PO-YYMMDD-NNN, counter reset harian.

        Pakai FOR UPDATE pada baris pemesanan hari ini supaya 2 Purchasing
        yang submit PO bersamaan tidak kolisi.

        Example: PO-260604-001, PO-260604-002, ...
        """
        if today is None:
            today = date.today()
        prefix = today.strftime("%y%m%d")
        prefix_full = f"PO-{prefix}-"

        # Lock baris-baris PO hari ini (kalau ada) supaya tidak ada concurrent insert
        # yang dapat counter sama.
        stmt = (
            select(Pemesanan)
            .where(Pemesanan.nomor_po.like(f"{prefix_full}%"))
            .with_for_update()
        )
        rows = list(self.db.execute(stmt).scalars().all())

        max_counter = 0
        for p in rows:
            # Format: PO-YYMMDD-NNN, ambil 3 digit terakhir
            try:
                counter = int(p.nomor_po.split("-")[-1])
                if counter > max_counter:
                    max_counter = counter
            except (ValueError, IndexError):
                continue

        next_counter = max_counter + 1
        return f"{prefix_full}{next_counter:03d}"

    # =========================================================================
    # CREATE
    # =========================================================================
    def create_with_items(
        self,
        pemesanan: Pemesanan,
        items: list[PemesananItem],
    ) -> Pemesanan:
        """
        Atomic insert header + N items. Caller HARUS commit nanti.

        Items akan punya id_pemesanan ter-isi otomatis via relationship setelah flush.
        """
        self.db.add(pemesanan)
        self.db.flush()  # supaya pemesanan.id_pemesanan tersedia
        for it in items:
            it.id_pemesanan = pemesanan.id_pemesanan
            self.db.add(it)
        self.db.flush()
        return pemesanan

    # =========================================================================
    # UPDATE
    # =========================================================================
    def update_header(self, pemesanan: Pemesanan, data: dict) -> Pemesanan:
        """Update field-field header — caller harus pastikan status SUBMITTED."""
        for k, v in data.items():
            if hasattr(pemesanan, k):
                setattr(pemesanan, k, v)
        self.db.flush()
        return pemesanan

    def update_status(
        self,
        pemesanan: Pemesanan,
        status_baru: StatusPemesananEnum,
        id_staf_approver: Optional[int] = None,
    ) -> Pemesanan:
        """Update status PO. id_staf_approver di-set saat transition SUBMITTED→ORDERED."""
        pemesanan.status = status_baru
        if id_staf_approver is not None:
            pemesanan.id_staf_approver = id_staf_approver
            pemesanan.tgl_approve = datetime.now()
        self.db.flush()
        return pemesanan

    def update_item_qty_diterima(
        self,
        item: PemesananItem,
        delta_qty: float,
    ) -> float:
        """Increment qty_diterima. Return total qty_diterima akhir."""
        baru = (item.qty_diterima or 0) + delta_qty
        item.qty_diterima = baru
        self.db.flush()
        return baru

    # =========================================================================
    # RECEIVE EVENT (append-only)
    # =========================================================================
    def add_receive_event(
        self,
        id_pemesanan: int,
        id_pemesanan_item: int,
        qty_diterima: float,
        id_staf_penerima: int,
        nomor_faktur: Optional[str] = None,
        catatan: Optional[str] = None,
        batch_no: Optional[str] = None,
        tgl_ed=None,
        harga_terima=None,
        id_distributor: Optional[int] = None,
        id_faktur: Optional[int] = None,
    ) -> PemesananReceive:
        receive = PemesananReceive(
            id_pemesanan=id_pemesanan,
            id_pemesanan_item=id_pemesanan_item,
            qty_diterima=qty_diterima,
            id_staf_penerima=id_staf_penerima,
            nomor_faktur=nomor_faktur,
            catatan=catatan,
            batch_no=batch_no,
            tgl_ed=tgl_ed,
            harga_terima=harga_terima,
            id_distributor=id_distributor,
            id_faktur=id_faktur,
        )
        self.db.add(receive)
        self.db.flush()
        return receive

    # =========================================================================
    # LIST + FILTER
    # =========================================================================
    def list_with_filter(
        self,
        status: Optional[StatusPemesananEnum] = None,
        tgl_dari: Optional[date] = None,
        tgl_sampai: Optional[date] = None,
        id_staf_pemesan: Optional[int] = None,
        limit: int = 100,
    ) -> list[tuple[Pemesanan, Optional[MasterStaf], int]]:
        """
        List PO dengan filter. Return list of (Pemesanan, MasterStaf pemesan, jumlah_item).
        """
        stmt = (
            select(Pemesanan, MasterStaf)
            .outerjoin(MasterStaf, Pemesanan.id_staf_pemesan == MasterStaf.id_staf)
        )
        conds = []
        if status is not None:
            conds.append(Pemesanan.status == status)
        if tgl_dari is not None:
            conds.append(Pemesanan.tgl_pemesanan >= datetime.combine(tgl_dari, time.min))
        if tgl_sampai is not None:
            conds.append(Pemesanan.tgl_pemesanan <= datetime.combine(tgl_sampai, time.max))
        if id_staf_pemesan is not None:
            conds.append(Pemesanan.id_staf_pemesan == id_staf_pemesan)
        if conds:
            stmt = stmt.where(and_(*conds))
        stmt = stmt.order_by(Pemesanan.tgl_pemesanan.desc()).limit(limit)
        rows = self.db.execute(stmt).all()

        # Hitung jumlah item per PO via separate query (skala kecil OK)
        result = []
        for po, pemesan in rows:
            count_stmt = (
                select(func.count(PemesananItem.id_item))
                .where(PemesananItem.id_pemesanan == po.id_pemesanan)
            )
            jumlah = int(self.db.execute(count_stmt).scalar() or 0)
            result.append((po, pemesan, jumlah))
        return result

    # =========================================================================
    # HELPER untuk service — get target stok (FOR UPDATE)
    # =========================================================================
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


__all__ = ["PemesananRepository"]
