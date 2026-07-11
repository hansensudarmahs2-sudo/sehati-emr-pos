"""
MasterStaf — model untuk tabel master_staf.

Tabel ini menyimpan semua user yang punya akses ke sistem:
Owner, Dokter, Perawat, Apoteker, Kasir, FO, Admin, Superadmin.

Note: kolom is_active, is_logged_in di-set nullable=True untuk match
skema existing (default punya server_default jadi tidak masalah).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._enums import StafRoleEnum


class MasterStaf(Base):
    """Tabel `master_staf` — semua staff klinik yang bisa login."""

    __tablename__ = "master_staf"

    # ----- Primary key -----
    id_staf: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ----- Identitas & auth -----
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    pin: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[StafRoleEnum] = mapped_column(
        Enum(StafRoleEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    nama_staf: Mapped[str] = mapped_column(String(100), nullable=False)

    # ----- Status & session -----
    is_active: Mapped[Optional[bool]] = mapped_column(
        Boolean, default=True, server_default="1", nullable=True
    )
    is_logged_in: Mapped[Optional[bool]] = mapped_column(
        Boolean, default=False, server_default="0", nullable=True
    )
    token_expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    waktu_mulai_shift: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # ----- Audit -----
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )

    def __repr__(self) -> str:
        return f"<MasterStaf(id={self.id_staf}, username={self.username!r}, role={self.role.value})>"

    @property
    def is_session_valid(self) -> bool:
        """Cek apakah session masih aktif (login + token belum expired)."""
        if not self.is_logged_in or not self.token_expired_at:
            return False
        return self.token_expired_at > datetime.utcnow()
