"""Inventory models — InventoryStok (master bahan) & InventoryHistory (mutasi)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    DECIMAL,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._enums import JenisMutasiEnum


class InventoryStok(Base):
    """Tabel `inventory_stok` — master bahan klinik (untuk treatment)."""

    __tablename__ = "inventory_stok"

    id_bahan: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nama_bahan: Mapped[str] = mapped_column(String(100), nullable=False)
    stok_gudang_utama: Mapped[Optional[float]] = mapped_column(
        Float, default=0, server_default="0", nullable=True
    )
    stok_kabin: Mapped[Optional[float]] = mapped_column(
        Float, default=0, server_default="0", nullable=True
    )
    satuan: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    satuan_pembelian: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    rasio_konversi: Mapped[Optional[float]] = mapped_column(
        Float, default=1, server_default="1", nullable=True
    )

    # FINANCE BRIDGE (M-FIN-3, Tier 2)
    harga_modal: Mapped[Optional[float]] = mapped_column(
        DECIMAL(12, 2), nullable=True,
        comment="Harga modal per unit bahan/BHP (cost). Untuk menilai mutasi & COGS treatment.",
    )

    def __repr__(self) -> str:
        return f"<InventoryStok(id={self.id_bahan}, nama={self.nama_bahan!r})>"


class InventoryHistory(Base):
    """Tabel `inventory_history` — buku riwayat mutasi stok (audit trail).

    Append-only — jangan UPDATE/DELETE row di sini.

    Polymorphic (DEC-039, migrasi 006): mutasi bisa untuk BAHAN (inventory_stok)
    atau PRODUK (master_produk). Salah satu dari id_bahan / id_produk wajib isi
    sesuai tipe_item — dijaga oleh CHECK constraint chk_inv_hist_xor di DB.
    """

    __tablename__ = "inventory_history"

    id_history: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Polymorphic source — salah satu wajib
    tipe_item: Mapped[str] = mapped_column(
        Enum("PRODUK", "BAHAN", name="tipe_item_enum"),
        nullable=False,
        default="BAHAN",
        server_default="BAHAN",
    )
    id_bahan: Mapped[Optional[int]] = mapped_column(
        ForeignKey("inventory_stok.id_bahan"), nullable=True
    )
    id_produk: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_produk.id_produk"), nullable=True
    )

    id_staf: Mapped[int] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=False
    )

    jenis_mutasi: Mapped[JenisMutasiEnum] = mapped_column(
        Enum(JenisMutasiEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    qty_perubahan: Mapped[float] = mapped_column(Float, nullable=False)
    stok_akhir: Mapped[float] = mapped_column(Float, nullable=False)

    referensi: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    keterangan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    waktu_mutasi: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=True
    )

    # FINANCE BRIDGE (M-FIN-3, Tier 2) — nilai mutasi untuk Finance (G7)
    hpp_satuan: Mapped[Optional[float]] = mapped_column(
        DECIMAL(12, 2), nullable=True,
        comment="Snapshot cost per unit saat mutasi (produk hpp_per_unit / bahan harga_modal).",
    )
    nilai_mutasi: Mapped[Optional[float]] = mapped_column(
        DECIMAL(14, 2), nullable=True,
        comment="Nilai mutasi = qty_perubahan x hpp_satuan (Rp).",
    )

    def __repr__(self) -> str:
        target = f"produk={self.id_produk}" if self.tipe_item == "PRODUK" else f"bahan={self.id_bahan}"
        return (
            f"<InventoryHistory(id={self.id_history}, "
            f"jenis={self.jenis_mutasi.value}, {target}, qty={self.qty_perubahan})>"
        )
