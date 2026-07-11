"""
Models — Pengadaan & Stock Opname (modul Pengadaan, DEC-038, migrasi 006).

5 tabel:
- Pemesanan          → header PO
- PemesananItem      → detail row PO (polymorphic PRODUK/BAHAN)
- PemesananReceive   → append-only audit per event receive
- StockOpname        → header sesi opname
- StockOpnameItem    → detail item opname dengan selisih auto-computed

Constraint XOR (id_produk vs id_bahan) dijaga di DB via CHECK constraint
yang dibuat di migration 006_pengadaan_inventory.sql.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    DECIMAL,
    Computed,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models._enums import (
    LokasiOpnameEnum,
    StatusOpnameEnum,
    StatusPemesananEnum,
)
from app.db.base import Base


# =============================================================================
# Pemesanan (PO)
# =============================================================================
class Pemesanan(Base):
    """Tabel `pemesanan` — header Purchase Order."""

    __tablename__ = "pemesanan"

    id_pemesanan: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nomor_po: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)

    tgl_pemesanan: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    tgl_perkiraan_datang: Mapped[Optional[date]] = mapped_column(nullable=True)
    supplier_nama: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    status: Mapped[StatusPemesananEnum] = mapped_column(
        Enum(StatusPemesananEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=StatusPemesananEnum.SUBMITTED,
        server_default=StatusPemesananEnum.SUBMITTED.value,
    )

    id_staf_pemesan: Mapped[int] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=False
    )
    id_staf_approver: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True
    )
    tgl_approve: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    catatan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_estimasi_biaya: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(14, 2), nullable=True
    )

    # PO-B (ideal PO): termin & validitas & apoteker penanggung jawab
    termin_hari: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Jatuh tempo bayar (hari) setelah barang diterima"
    )
    validitas_hari: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Masa berlaku PO (hari sejak tgl PO). NULL = tanpa batas"
    )
    id_apoteker: Mapped[Optional[int]] = mapped_column(
        ForeignKey("klinik_apoteker.id_apoteker"), nullable=True,
        comment="Apoteker penanggung jawab PO (wajib dipilih saat buat)",
    )
    apoteker_nama: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="Snapshot nama apoteker saat buat PO",
    )
    apoteker_sipa: Mapped[Optional[str]] = mapped_column(
        String(60), nullable=True, comment="Snapshot No. SIPA saat buat PO",
    )

    # SHIP-L1: alamat "kirim ke" (ship-to) — bisa klinik/gudang/purchasing
    id_lokasi_pengiriman: Mapped[Optional[int]] = mapped_column(
        ForeignKey("lokasi_pengiriman.id_lokasi"), nullable=True
    )
    kirim_ke_nama: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    kirim_ke_alamat: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=True
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        server_onupdate=func.current_timestamp(),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<Pemesanan(id={self.id_pemesanan}, nomor={self.nomor_po!r}, status={self.status.value})>"


# =============================================================================
# PemesananItem
# =============================================================================
class PemesananItem(Base):
    """Tabel `pemesanan_item` — detail row PO (polymorphic)."""

    __tablename__ = "pemesanan_item"

    id_item: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_pemesanan: Mapped[int] = mapped_column(
        ForeignKey("pemesanan.id_pemesanan", ondelete="CASCADE"), nullable=False
    )

    tipe_item: Mapped[str] = mapped_column(
        Enum("PRODUK", "BAHAN", name="tipe_item_pemesanan_enum"),
        nullable=False,
    )
    id_produk: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_produk.id_produk"), nullable=True
    )
    id_bahan: Mapped[Optional[int]] = mapped_column(
        ForeignKey("inventory_stok.id_bahan"), nullable=True
    )

    # Snapshot — anti-perubahan master
    nama_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    satuan_snapshot: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    qty_dipesan: Mapped[float] = mapped_column(Float, nullable=False)
    qty_diterima: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, server_default="0"
    )
    harga_satuan: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(12, 2), nullable=True
    )
    subtotal: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(14, 2), nullable=True
    )
    catatan_item: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<PemesananItem(id={self.id_item}, tipe={self.tipe_item}, "
            f"nama={self.nama_snapshot!r}, dipesan={self.qty_dipesan})>"
        )


# =============================================================================
# PemesananReceive (append-only)
# =============================================================================
class PemesananReceive(Base):
    """Tabel `pemesanan_receive` — audit per event receive."""

    __tablename__ = "pemesanan_receive"

    id_receive: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_pemesanan: Mapped[int] = mapped_column(
        ForeignKey("pemesanan.id_pemesanan"), nullable=False
    )
    id_pemesanan_item: Mapped[int] = mapped_column(
        ForeignKey("pemesanan_item.id_item"), nullable=False
    )

    qty_diterima: Mapped[float] = mapped_column(Float, nullable=False)
    tgl_terima: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    id_staf_penerima: Mapped[int] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=False
    )
    nomor_faktur: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    catatan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # P-L4 (faktur + lot): tangkap batch/ED/harga terima + distributor
    batch_no: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tgl_ed: Mapped[Optional["date"]] = mapped_column(Date, nullable=True)
    harga_terima: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2), nullable=True)
    id_distributor: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_distributor.id_distributor"), nullable=True
    )
    # FK-L1: gabung event receive ke satu faktur (1 faktur = 1 pengiriman)
    id_faktur: Mapped[Optional[int]] = mapped_column(
        ForeignKey("faktur_penerimaan.id_faktur"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<PemesananReceive(id={self.id_receive}, item={self.id_pemesanan_item}, qty={self.qty_diterima})>"


# =============================================================================
# StockOpname
# =============================================================================
class StockOpname(Base):
    """Tabel `stock_opname` — header sesi opname."""

    __tablename__ = "stock_opname"

    id_opname: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nomor_opname: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)

    tgl_opname: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    lokasi: Mapped[LokasiOpnameEnum] = mapped_column(
        Enum(LokasiOpnameEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    status: Mapped[StatusOpnameEnum] = mapped_column(
        Enum(StatusOpnameEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=StatusOpnameEnum.DRAFT,
        server_default=StatusOpnameEnum.DRAFT.value,
    )

    id_staf_pelaksana: Mapped[int] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=False
    )
    id_staf_approver: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True
    )
    tgl_approve: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    total_selisih_value: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(14, 2), nullable=True
    )
    catatan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=True
    )

    def __repr__(self) -> str:
        return f"<StockOpname(id={self.id_opname}, nomor={self.nomor_opname!r}, status={self.status.value})>"


# =============================================================================
# StockOpnameItem (selisih auto-computed di DB)
# =============================================================================
class StockOpnameItem(Base):
    """Tabel `stock_opname_item` — detail item opname.

    `selisih` adalah GENERATED ALWAYS AS (qty_fisik - qty_sistem) STORED di DB.
    Python read-only — jangan set langsung, DB akan compute.
    """

    __tablename__ = "stock_opname_item"

    id_opname_item: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_opname: Mapped[int] = mapped_column(
        ForeignKey("stock_opname.id_opname", ondelete="CASCADE"), nullable=False
    )

    tipe_item: Mapped[str] = mapped_column(
        Enum("PRODUK", "BAHAN", name="tipe_item_opname_enum"),
        nullable=False,
    )
    id_produk: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_produk.id_produk"), nullable=True
    )
    id_bahan: Mapped[Optional[int]] = mapped_column(
        ForeignKey("inventory_stok.id_bahan"), nullable=True
    )

    nama_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    qty_sistem: Mapped[float] = mapped_column(Float, nullable=False)
    qty_fisik: Mapped[float] = mapped_column(Float, nullable=False)
    # selisih: GENERATED ALWAYS AS (qty_fisik - qty_sistem) STORED — read-only di Python.
    # Computed() memberi tahu SQLAlchemy untuk skip kolom ini di INSERT/UPDATE
    # supaya MySQL tidak error 3105 (generated column not allowed in INSERT).
    selisih: Mapped[Optional[float]] = mapped_column(
        Float,
        Computed("qty_fisik - qty_sistem", persisted=True),
        nullable=True,
    )

    catatan_item: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # P-L9 (opname per-batch, PRODUK/RETAIL): 1 baris = 1 lot.
    # id_lot NULL + tipe PRODUK + qty_fisik>0 = "batch baru ditemukan" saat opname
    # (batch_no & tgl_ed diisi petugas → dibuat StokLot baru saat approve).
    # BAHAN tetap agregat (id_lot selalu NULL, path lama).
    id_lot: Mapped[Optional[int]] = mapped_column(
        ForeignKey("stok_lot.id_lot"), nullable=True
    )
    batch_no: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tgl_ed: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<StockOpnameItem(id={self.id_opname_item}, tipe={self.tipe_item}, "
            f"nama={self.nama_snapshot!r}, selisih={self.selisih})>"
        )


__all__ = [
    "Pemesanan",
    "PemesananItem",
    "PemesananReceive",
    "StockOpname",
    "StockOpnameItem",
]
