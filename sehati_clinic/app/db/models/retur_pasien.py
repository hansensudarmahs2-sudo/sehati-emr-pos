"""
ReturPasien + ReturPasienLot — retur obat/produk yang SUDAH diserahkan ke pasien.

Rancangan & keputusan dr. Hansen: Project_Memory/DESAIN_RETUR_DARI_PASIEN.md (§10–§13).
Migrasi: 20261006_0100_retur_pasien.

⚠ SENGAJA tanpa `id_pasien` — lihat docstring migrasi. Pasien = lewat transaksi asal.
⚠ Bentuk yang menjaga uang dijaga DI DB juga (CHECK tepat satu item, qty > 0); model di
  sini mencerminkannya supaya DB yang dibangun dari model (create_all, laptop) tidak
  kehilangan pagarnya — pelajaran Temuan 18/34.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    DECIMAL, TIMESTAMP, Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index,
    Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._enums import AlasanReturPasienEnum, JenisReturPasienEnum


class ReturPasien(Base):
    __tablename__ = "retur_pasien"
    __table_args__ = (
        UniqueConstraint("nomor_retur", name="ux_retur_pasien_nomor"),
        CheckConstraint("(id_resep IS NULL) <> (id_kunjungan_racikan IS NULL)",
                        name="ck_rp_satu_item"),
        CheckConstraint("qty > 0", name="ck_rp_qty_positif"),
        Index("ix_rp_trx_asal", "id_transaksi_asal"),
        Index("ix_rp_resep", "id_resep"),
        Index("ix_rp_racikan", "id_kunjungan_racikan"),
        Index("ix_rp_created", "created_at"),
    )

    id_retur: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # RPS-YYYY-MM-###### — diturunkan dari id_retur saat INSERT (flush dulu), bukan dari
    # COUNT/MAX: pelajaran Temuan 33 (nomor dokumen yang tak pernah diisi) dan 34.
    nomor_retur: Mapped[str] = mapped_column(String(30), nullable=False)
    id_transaksi_asal: Mapped[int] = mapped_column(
        ForeignKey("transaksi_kasir.id_transaksi", name="fk_rp_trx_asal"), nullable=False)
    id_resep: Mapped[Optional[int]] = mapped_column(
        ForeignKey("kunjungan_resep.id_resep", name="fk_rp_resep"), nullable=True)
    id_kunjungan_racikan: Mapped[Optional[int]] = mapped_column(
        ForeignKey("kunjungan_racikan.id_kunjungan_racikan", name="fk_rp_racikan"),
        nullable=True)
    qty: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    is_sebagian: Mapped[bool] = mapped_column(Boolean, nullable=False)
    waktu_serah_asal: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    jenis: Mapped[JenisReturPasienEnum] = mapped_column(
        Enum(JenisReturPasienEnum, name="jenis_retur_pasien",
             values_callable=lambda x: [e.value for e in x]), nullable=False)
    alasan_kode: Mapped[AlasanReturPasienEnum] = mapped_column(
        Enum(AlasanReturPasienEnum, name="alasan_retur_pasien",
             values_callable=lambda x: [e.value for e in x]), nullable=False)
    alasan_teks: Mapped[str] = mapped_column(Text, nullable=False)
    nilai_retur: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    stok_kembali: Mapped[bool] = mapped_column(Boolean, nullable=False)
    nilai_kerugian: Mapped[Decimal] = mapped_column(
        DECIMAL(12, 2), nullable=False, default=0, server_default="0.00")
    id_refund: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transaksi_refund.id_refund", name="fk_rp_refund"), nullable=True)
    id_transaksi_pengganti: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transaksi_kasir.id_transaksi", name="fk_rp_trx_pengganti"), nullable=True)
    nilai_pengganti: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2), nullable=True)
    selisih_dibayar: Mapped[Decimal] = mapped_column(
        DECIMAL(12, 2), nullable=False, default=0, server_default="0.00")
    # Pengganti lebih murah: sisa TIDAK dikembalikan & TIDAK jadi saldo (keputusan 4).
    # Tetap pendapatan penjualan asal; ditandai untuk Finance, bukan dijurnal ulang.
    nilai_hangus: Mapped[Decimal] = mapped_column(
        DECIMAL(12, 2), nullable=False, default=0, server_default="0.00")
    id_kunjungan_retur: Mapped[Optional[int]] = mapped_column(
        ForeignKey("kunjungan.id_kunjungan", name="fk_rp_kunjungan_retur"), nullable=True)
    id_alergi: Mapped[Optional[int]] = mapped_column(
        ForeignKey("pasien_alergi.id_alergi", name="fk_rp_alergi"), nullable=True)
    id_staf: Mapped[int] = mapped_column(
        ForeignKey("master_staf.id_staf", name="fk_rp_staf"), nullable=False)
    id_staf_otorisasi: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf", name="fk_rp_staf_otorisasi"), nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True)


class ReturPasienLot(Base):
    """Lot ASAL yang menerima barang kembali (hanya bila stok_kembali)."""
    __tablename__ = "retur_pasien_lot"
    __table_args__ = (
        CheckConstraint("qty > 0", name="ck_rpl_qty_positif"),
        Index("ix_rpl_retur", "id_retur"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_retur: Mapped[int] = mapped_column(
        ForeignKey("retur_pasien.id_retur", name="fk_rpl_retur"), nullable=False)
    id_lot: Mapped[int] = mapped_column(
        ForeignKey("stok_lot.id_lot", name="fk_rpl_lot"), nullable=False)
    qty: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
