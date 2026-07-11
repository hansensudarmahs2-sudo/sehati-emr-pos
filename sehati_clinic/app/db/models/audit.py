"""AuditLog — record semua aksi mutating sensitif.

Append-only. Jangan UPDATE/DELETE row di sini.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._enums import StatusAksiAuditEnum


class AuditLog(Base):
    """Tabel `audit_log` — catat semua aksi yang penting."""

    __tablename__ = "audit_log"

    id_log: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_staf: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True,
        comment="NULL untuk anonymous events (login attempt gagal)",
    )

    # Apa yang terjadi
    aksi: Mapped[str] = mapped_column(String(50), nullable=False)
    tabel_target: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    id_target: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Snapshot data (JSON)
    data_lama: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    data_baru: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Konteks
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    endpoint: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    http_method: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Catatan
    keterangan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status_aksi: Mapped[StatusAksiAuditEnum] = mapped_column(
        Enum(StatusAksiAuditEnum, values_callable=lambda x: [e.value for e in x]),
        default=StatusAksiAuditEnum.SUCCESS,
        server_default=StatusAksiAuditEnum.SUCCESS.value,
        nullable=False,
    )

    waktu: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id_log}, aksi={self.aksi!r}, status={self.status_aksi.value})>"
