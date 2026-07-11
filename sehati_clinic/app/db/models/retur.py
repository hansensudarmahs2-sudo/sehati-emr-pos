"""
ReturProduk — retur produk (mendekati ED) ke distributor (RT-L1).

Alur: buat form retur (DRAFT) → approve (RBAC luas) = OTOMATIS potong lot batch → status APPROVED.
Distributor merespon: TUKAR_BARANG (input nota → lot pengganti) atau REFUND (input nota header → tutup,
ke finance). Ref RETUR_MODULE_DESIGN.md §7/§8. Admin bersih = siap konektor finance (Accurate) kelak.

Status  : DRAFT / APPROVED / SELESAI / CANCELLED  (String, hindari ALTER enum)
Jenis   : REFUND / TUKAR_BARANG  (NULL sampai nota diinput)
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DECIMAL, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ReturProduk(Base):
    __tablename__ = "retur_produk"

    id_retur: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nomor_retur: Mapped[str] = mapped_column(String(50), nullable=False, unique=True,
                                             comment="Nomor permintaan retur (auto RT-YYMMDD-NNN)")
    tgl_retur: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    id_distributor: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_distributor.id_distributor"), nullable=True
    )
    alasan: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Alasan retur (form-level)")

    status: Mapped[str] = mapped_column(String(15), nullable=False, server_default="DRAFT",
                                        comment="DRAFT / APPROVED / SELESAI / CANCELLED")
    jenis_penyelesaian: Mapped[Optional[str]] = mapped_column(
        String(15), nullable=True, comment="REFUND / TUKAR_BARANG (NULL sampai nota diinput)"
    )

    id_staf_pembuat: Mapped[int] = mapped_column(ForeignKey("master_staf.id_staf"), nullable=False)
    # Apoteker penanggung jawab (regulasi: nama + SIPA di Form Retur, bersama SIA klinik)
    id_apoteker: Mapped[Optional[int]] = mapped_column(
        ForeignKey("klinik_apoteker.id_apoteker"), nullable=True
    )
    apoteker_nama: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    apoteker_sipa: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    id_staf_approver: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True
    )
    tgl_approve: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Nota retur (diisi saat respon distributor diterima)
    nomor_nota: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tgl_nota: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    total_nilai: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(14, 2), nullable=True)

    catatan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=True
    )

    items: Mapped[list["ReturProdukItem"]] = relationship(
        "ReturProdukItem", back_populates="retur", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ReturProduk(id={self.id_retur}, nomor={self.nomor_retur!r}, status={self.status})>"


class ReturProdukItem(Base):
    __tablename__ = "retur_produk_item"

    id_retur_item: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_retur: Mapped[int] = mapped_column(
        ForeignKey("retur_produk.id_retur", ondelete="CASCADE"), nullable=False
    )
    id_produk: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_produk.id_produk"), nullable=True
    )
    id_lot: Mapped[Optional[int]] = mapped_column(
        ForeignKey("stok_lot.id_lot"), nullable=True, comment="Lot/batch yang diretur (pilih manual)"
    )
    nama_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    batch_no: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tgl_ed: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    harga_terima: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(12, 2), nullable=True, comment="Snapshot harga terima lot (nilai refund, bisa diedit)"
    )
    alasan_item: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    retur: Mapped["ReturProduk"] = relationship("ReturProduk", back_populates="items")

    def __repr__(self) -> str:
        return f"<ReturProdukItem(id={self.id_retur_item}, produk={self.nama_snapshot!r}, qty={self.qty})>"


__all__ = ["ReturProduk", "ReturProdukItem"]
