"""MasterProduk — model untuk tabel master_produk.

Master produk yang dijual via POS (RETAIL, CABIN, ALAT).
Kalau produk hasil repacking dari bahan klinik, id_bahan_sumber di-set.

Schema sesuai DB (19 kolom). DEC-060 hybrid komisi applied.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DECIMAL,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    TIMESTAMP,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._enums import TipeProdukEnum


class MasterProduk(Base):
    """Tabel `master_produk` — semua barang yang dijual via POS."""

    __tablename__ = "master_produk"

    id_produk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kode_produk: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    nama_produk: Mapped[str] = mapped_column(String(100), nullable=False)
    tipe_produk: Mapped[TipeProdukEnum] = mapped_column(
        Enum(TipeProdukEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )

    # Mapping ke bahan (kalau produk repack)
    id_bahan_sumber: Mapped[Optional[int]] = mapped_column(
        ForeignKey("inventory_stok.id_bahan"), nullable=True,
    )
    qty_per_unit_produk: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    satuan: Mapped[str] = mapped_column(String(20), nullable=False)
    harga_jual: Mapped[Optional[float]] = mapped_column(
        DECIMAL(12, 2), default=0.00, server_default="0.00", nullable=True
    )

    # TODO-NEW-3 #31 — Auto-fill cara pakai di resep SOAP
    # Saat dokter pilih produk di dropdown resep, field aturan_pakai otomatis
    # ter-isi dengan nilai ini (kalau ada). Dokter bisa edit kalau perlu beda.
    default_cara_pakai: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True,
    )

    stok_terkini: Mapped[Optional[float]] = mapped_column(
        Float, default=0, server_default="0", nullable=True
    )
    stok_minimal: Mapped[Optional[float]] = mapped_column(
        Float, default=5, server_default="5", nullable=True
    )

    # Iterasi & member discount
    default_iterasi: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    eligible_member_discount: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )

    is_active: Mapped[Optional[bool]] = mapped_column(
        Boolean, default=True, server_default="1", nullable=True
    )

    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        server_onupdate=func.current_timestamp(),
        nullable=True,
    )

    # KOMISI SYSTEM HYBRID (Task #361, DEC-060)
    # Akuntansi standar: komisi MASUK HPP/COGS. Tidak ada recursion.
    # Tipe komisi (3 mode hybrid):
    #   - "PERSEN_HARGA": value % × harga_jual
    #   - "PERSEN_MARGIN": value % × (harga_jual - hpp_per_unit)
    #   - "NOMINAL": value rupiah flat
    hpp_per_unit: Mapped[Optional[float]] = mapped_column(
        DECIMAL(12, 2), default=0, server_default="0", nullable=True
    )
    pajak_persen: Mapped[Optional[float]] = mapped_column(
        DECIMAL(5, 2), default=0, server_default="0", nullable=True
    )
    pajak_nominal: Mapped[Optional[float]] = mapped_column(DECIMAL(12, 2), nullable=True)

    komisi_dokter_tipe: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    komisi_dokter_value: Mapped[Optional[float]] = mapped_column(
        DECIMAL(12, 2), default=0, server_default="0", nullable=True
    )

    # Produk topikal: nama_produk = KODE SEDIAAN (yang tampil). kandungan boleh ditampilkan.
    # nama_dagang = merk asli (internal, untuk PO/pembelian — TIDAK tampil ke pasien).
    kandungan: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    nama_dagang: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
