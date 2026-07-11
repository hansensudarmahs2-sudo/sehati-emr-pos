"""
Master Distributor — pemasok/distributor untuk pengadaan (PO + faktur penerimaan).

Ref INVENTORY_LOT_ED_MODULE_DESIGN.md §2/§3 (P-L1). Diperlakukan seperti master lain
(produk/treatment/bahan): data referensi yang dipakai di PO & faktur.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, String, Text, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MasterDistributor(Base):
    __tablename__ = "master_distributor"

    id_distributor: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nama: Mapped[str] = mapped_column(String(100), nullable=False)
    alamat: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    telepon: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    kontak_person: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="PIC / narahubung (opsional)"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="1", default=True, nullable=False)

    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(),
        server_onupdate=func.current_timestamp(), nullable=True
    )

    def __repr__(self) -> str:
        return f"<MasterDistributor(id={self.id_distributor}, nama={self.nama!r}, aktif={self.is_active})>"
