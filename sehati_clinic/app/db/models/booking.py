"""JadwalBooking — model untuk tabel jadwal_booking."""

from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import (
    Date,
    DECIMAL,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    TIMESTAMP,
    Time,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._enums import StatusBookingEnum


class JadwalBooking(Base):
    """Tabel `jadwal_booking` — booking pasien (konvensional, kiosk, atau web)."""

    __tablename__ = "jadwal_booking"

    id_booking: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_pasien: Mapped[int] = mapped_column(
        ForeignKey("pasien.id_pasien"), nullable=False
    )

    tgl_rencana: Mapped[date] = mapped_column(Date, nullable=False)
    jam_rencana: Mapped[time] = mapped_column(Time, nullable=False)

    sumber_pendaftaran: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status_booking: Mapped[Optional[StatusBookingEnum]] = mapped_column(
        Enum(StatusBookingEnum, values_callable=lambda x: [e.value for e in x]),
        default=StatusBookingEnum.BOOKED,
        server_default=StatusBookingEnum.BOOKED.value,
        nullable=True,
    )
    id_booking_lama: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ----- Booking module (2026-06-29) -----
    id_staf_dokter_dituju: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True,
        comment="Dokter yang dituju (opsional)",
    )
    keluhan_utama: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    catatan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    id_staf_input: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True,
        comment="Staf pembuat/pengubah booking (audit)",
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        nullable=True,
    )

    # ----- RESERVED: siap-bayar (PARKIR, belum dipakai) -----
    biaya_booking: Mapped[Optional[float]] = mapped_column(
        DECIMAL(12, 2), nullable=True,
        comment="RESERVED: biaya booking (fitur booking berbayar, belum aktif)",
    )
    status_pembayaran_booking: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
        comment="RESERVED: NONE/DP/LUNAS (belum aktif)",
    )

    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )

    def __repr__(self) -> str:
        return f"<JadwalBooking(id={self.id_booking}, tgl={self.tgl_rencana}, status={self.status_booking})>"
