"""
Master Lokasi Pengiriman — daftar alamat "kirim ke" (ship-to) untuk PO.

Fleksibel & terpisah dari identitas klinik (SHIP-L1): bisa berupa klinik, gudang, atau alamat
purchasing. Dipakai sebagai dropdown "Kirim ke" saat buat PO; alamat di-snapshot ke PO agar cetakan
historis akurat. Ref NOTA_PO_FAKTUR_IMPROVEMENTS §E + diskusi 2026-07-03 (Opsi A, bukan master_klinik).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, String, Text, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LokasiPengiriman(Base):
    __tablename__ = "lokasi_pengiriman"

    id_lokasi: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nama: Mapped[str] = mapped_column(String(100), nullable=False, comment="mis. Klinik Acnova / Gudang Pusat")
    alamat: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    telepon: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    kontak_person: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_default: Mapped[bool] = mapped_column(
        Boolean, server_default="0", default=False, nullable=False,
        comment="Lokasi terpilih otomatis saat buat PO",
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
        return f"<LokasiPengiriman(id={self.id_lokasi}, nama={self.nama!r}, aktif={self.is_active})>"
