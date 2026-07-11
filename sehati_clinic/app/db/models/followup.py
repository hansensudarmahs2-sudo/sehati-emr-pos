"""Followup — model untuk tabel `followup` (modul reminder kontrol/kunjungan ulang).

Konsep: follow-up dihitung PER-ITEM treatment (konsultasi pun master treatment),
jadi 1 kunjungan bisa menghasilkan beberapa follow-up di tanggal berbeda.
Lihat Project_Memory/FOLLOWUP_REMINDER_DESIGN.md.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    TIMESTAMP,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._enums import JenisFollowupEnum, StatusFollowupEnum


class Followup(Base):
    """Tabel `followup` — satu baris per rencana follow-up (konsultasi/treatment)."""

    __tablename__ = "followup"

    id_followup: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    id_pasien: Mapped[int] = mapped_column(
        ForeignKey("pasien.id_pasien"), nullable=False
    )
    id_kunjungan: Mapped[int] = mapped_column(
        ForeignKey("kunjungan.id_kunjungan"), nullable=False,
        comment="Kunjungan sumber yang memicu follow-up",
    )
    id_treatment: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_treatment.id_treatment"), nullable=True,
        comment="NULL untuk follow-up konsultasi generik",
    )

    jenis: Mapped[JenisFollowupEnum] = mapped_column(
        Enum(JenisFollowupEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[StatusFollowupEnum] = mapped_column(
        Enum(StatusFollowupEnum, values_callable=lambda x: [e.value for e in x]),
        default=StatusFollowupEnum.PENDING,
        server_default=StatusFollowupEnum.PENDING.value,
        nullable=False,
    )

    # ----- Workflow handling (diisi tim FO saat aksi) -----
    id_staf_handler: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True,
        comment="Staf yang meng-handle (audit kinerja FO)",
    )
    waktu_handle: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    catatan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_followup_due_status", "due_date", "status"),
        Index("ix_followup_pasien", "id_pasien"),
        Index("ix_followup_kunjungan", "id_kunjungan"),
    )

    def __repr__(self) -> str:
        return (
            f"<Followup(id={self.id_followup}, pasien={self.id_pasien}, "
            f"jenis={self.jenis}, due={self.due_date}, status={self.status})>"
        )
