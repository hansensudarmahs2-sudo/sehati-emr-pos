"""
Membership system models.

Tabel:
- master_membership (definisi tier)
- master_membership_benefit_treatment (kuota treatment per tier)
- pasien_membership_history (record aktivasi per pasien)
- pasien_membership_kuota (kuota tersedia per pasien)
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DECIMAL,
    Date,
    Enum,
    ForeignKey,
    Integer,
    String,
    TIMESTAMP,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._enums import PeriodeKuotaEnum


class MasterMembership(Base):
    """Tabel `master_membership` — definisi tier (VIP, VVIP, dst)."""

    __tablename__ = "master_membership"

    id_membership: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nama_tier: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    harga_aktivasi: Mapped[float] = mapped_column(
        DECIMAL(12, 2), default=0.00, server_default="0.00", nullable=False
    )
    durasi_bulan: Mapped[int] = mapped_column(
        Integer, default=12, server_default="12", nullable=False
    )

    # Benefit fix
    free_konsultasi_dokter: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    diskon_treatment_persen: Mapped[float] = mapped_column(
        DECIMAL(5, 2), default=0.00, server_default="0.00", nullable=False
    )
    diskon_produk_persen: Mapped[float] = mapped_column(
        DECIMAL(5, 2), default=0.00, server_default="0.00", nullable=False
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    catatan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    urutan_tampilan: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        server_onupdate=func.current_timestamp(),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<MasterMembership(id={self.id_membership}, tier={self.nama_tier!r})>"


class MasterMembershipBenefitTreatment(Base):
    """Tabel `master_membership_benefit_treatment` — benefit kuota treatment per tier."""

    __tablename__ = "master_membership_benefit_treatment"

    id_benefit: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_membership: Mapped[int] = mapped_column(
        ForeignKey("master_membership.id_membership"), nullable=False
    )
    id_treatment: Mapped[int] = mapped_column(
        ForeignKey("master_treatment.id_treatment"), nullable=False
    )
    kuota_total: Mapped[int] = mapped_column(Integer, nullable=False)
    periode_kuota: Mapped[PeriodeKuotaEnum] = mapped_column(
        Enum(PeriodeKuotaEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    catatan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )


class PasienMembershipHistory(Base):
    """Tabel `pasien_membership_history` — record aktivasi membership."""

    __tablename__ = "pasien_membership_history"

    id_history: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_pasien: Mapped[int] = mapped_column(
        ForeignKey("pasien.id_pasien"), nullable=False
    )
    id_membership: Mapped[int] = mapped_column(
        ForeignKey("master_membership.id_membership"), nullable=False
    )

    tgl_aktif: Mapped[date] = mapped_column(Date, nullable=False)
    tgl_expired: Mapped[date] = mapped_column(Date, nullable=False)
    harga_bayar: Mapped[float] = mapped_column(DECIMAL(12, 2), nullable=False)

    id_transaksi_aktivasi: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transaksi_kasir.id_transaksi"), nullable=True
    )
    id_staf_aktivasi: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    catatan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )


class PasienMembershipKuota(Base):
    """Tabel `pasien_membership_kuota` — kuota treatment tersedia per pasien."""

    __tablename__ = "pasien_membership_kuota"

    id_kuota: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_pasien: Mapped[int] = mapped_column(
        ForeignKey("pasien.id_pasien"), nullable=False
    )
    id_membership_history: Mapped[int] = mapped_column(
        ForeignKey("pasien_membership_history.id_history"), nullable=False
    )
    id_treatment: Mapped[int] = mapped_column(
        ForeignKey("master_treatment.id_treatment"), nullable=False
    )

    periode_kuota: Mapped[PeriodeKuotaEnum] = mapped_column(
        Enum(PeriodeKuotaEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    bulan_periode: Mapped[Optional[str]] = mapped_column(
        String(7), nullable=True,
        comment="YYYY-MM untuk BULANAN, NULL untuk TOTAL_PAKET",
    )

    kuota_total: Mapped[int] = mapped_column(Integer, nullable=False)
    kuota_terpakai: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    expired_at: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )

    @property
    def kuota_sisa(self) -> int:
        return self.kuota_total - self.kuota_terpakai
