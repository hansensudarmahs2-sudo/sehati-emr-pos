"""
FakturPenerimaan — faktur/bukti penerimaan barang (FK-L1).

1 faktur = 1 pengiriman (Model A, dr. Hansen). Menghubungkan beberapa event penerimaan
(PemesananReceive.id_faktur) di bawah satu dokumen tagih. Menyimpan PPN + diskon (seragam, sebelum PPN)
+ extra_diskon (rekonsiliasi agar Σ = total ditagih). Ref FAKTUR_MODULE_DESIGN.md §3/§10.

Diskon dihitung terbalik dari total ditagih (Y): d = 1 − Y/(X·(1+PPN%)); harga_terima item = order·(1−d).
Status bayar / hutang (AP) = fase 2 (FK-L6), belum di sini.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DECIMAL, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FakturPenerimaan(Base):
    __tablename__ = "faktur_penerimaan"

    id_faktur: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_pemesanan: Mapped[int] = mapped_column(
        ForeignKey("pemesanan.id_pemesanan"), nullable=False
    )

    nomor_faktur: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="Nomor faktur dari distributor"
    )
    nomor_pengiriman: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="Nomor pengiriman internal (auto, mis. SJ-YYMMDD-NNN)"
    )
    id_distributor: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_distributor.id_distributor"), nullable=True
    )

    tgl_faktur: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    tgl_terima: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )

    # Keuangan
    ppn_persen: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(5, 2), nullable=True, comment="PPN % (mis. 11.00). 0/NULL = tanpa PPN"
    )
    diskon_persen: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(5, 2), nullable=True, comment="Diskon seragam % (hasil reverse-calc / input)"
    )
    extra_diskon: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(14, 2), nullable=True, comment="Rekonsiliasi rupiah agar Σ total = total ditagih"
    )
    subtotal_order: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(14, 2), nullable=True, comment="X = Σ harga order item pengiriman ini (pra-diskon, pra-PPN)"
    )
    subtotal_setelah_diskon: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(14, 2), nullable=True, comment="X·(1−d) − extra_diskon"
    )
    total_ditagih: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(14, 2), nullable=True, comment="Y = final (setelah diskon + extra + PPN)"
    )

    id_staf_penerima: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True
    )
    catatan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=True
    )

    def __repr__(self) -> str:
        return (f"<FakturPenerimaan(id={self.id_faktur}, po={self.id_pemesanan}, "
                f"faktur={self.nomor_faktur!r}, total={self.total_ditagih})>")
