"""
Pasien dan tabel turunannya (alergi, penyakit kronis).

Tabel di file ini:
- pasien (master pasien)
- pasien_alergi (1 pasien : N alergi)
- pasien_penyakit_kronis (1 pasien : N penyakit kronis)
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    TIMESTAMP,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models._enums import (
    GenderEnum,
    MembershipTierEnum,
    TingkatKeparahanAlergiEnum,
    VerifikasiEnum,
)


class Pasien(Base):
    """Tabel `pasien` — master pasien klinik."""

    __tablename__ = "pasien"

    # ----- Primary key -----
    id_pasien: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ----- Identitas -----
    no_rm: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    nama: Mapped[str] = mapped_column(String(100), nullable=False)
    jenis_kelamin: Mapped[Optional[GenderEnum]] = mapped_column(
        Enum(GenderEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=True,
    )
    alamat: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tgl_lahir: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    nomor_telepon: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    no_member: Mapped[Optional[str]] = mapped_column(String(30), unique=True, nullable=True, comment="Nomor member (diisi saat aktivasi CS)")
    nomor_ktp: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    email_address: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sumber_referensi: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # ----- Membership (snapshot — source of truth tier ada di master_membership) -----
    tipe_membership: Mapped[Optional[MembershipTierEnum]] = mapped_column(
        Enum(MembershipTierEnum, values_callable=lambda x: [e.value for e in x]),
        default=MembershipTierEnum.REGULAR,
        server_default=MembershipTierEnum.REGULAR.value,
        nullable=True,
    )

    # ----- Verifikasi (untuk Phase 2 — kiosk/web pasien) -----
    status_verifikasi: Mapped[Optional[VerifikasiEnum]] = mapped_column(
        Enum(VerifikasiEnum, values_callable=lambda x: [e.value for e in x]),
        default=VerifikasiEnum.VERIFIED,
        server_default=VerifikasiEnum.VERIFIED.value,
        nullable=True,
    )
    tgl_verifikasi: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # ----- Audit -----
    id_staf: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True,
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )

    # ----- Relationships -----
    alergi: Mapped[list["PasienAlergi"]] = relationship(
        "PasienAlergi",
        back_populates="pasien",
        cascade="save-update, merge",
    )
    penyakit_kronis: Mapped[list["PasienPenyakitKronis"]] = relationship(
        "PasienPenyakitKronis",
        back_populates="pasien",
        cascade="save-update, merge",
    )

    def __repr__(self) -> str:
        return f"<Pasien(id={self.id_pasien}, no_rm={self.no_rm!r}, nama={self.nama!r})>"


class PasienAlergi(Base):
    """Tabel `pasien_alergi` — riwayat alergi pasien.

    Sesuai dokumentasi dokter:
    - FO/Perawat/Dokter bisa TAMBAH alergi
    - Hanya Dokter yang bisa UBAH/HAPUS (soft delete via is_active=0)
    """

    __tablename__ = "pasien_alergi"

    id_alergi: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_pasien: Mapped[Optional[int]] = mapped_column(
        ForeignKey("pasien.id_pasien"), nullable=True
    )
    alergen: Mapped[str] = mapped_column(String(100), nullable=False)
    gejala: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tingkat_keparahan: Mapped[TingkatKeparahanAlergiEnum] = mapped_column(
        Enum(TingkatKeparahanAlergiEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    is_active: Mapped[Optional[bool]] = mapped_column(
        Boolean, default=True, server_default="1", nullable=True
    )

    # Audit
    id_staf: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True,
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )

    # Relationships
    pasien: Mapped["Pasien"] = relationship("Pasien", back_populates="alergi")

    def __repr__(self) -> str:
        return (
            f"<PasienAlergi(id={self.id_alergi}, "
            f"alergen={self.alergen!r}, tingkat={self.tingkat_keparahan.value})>"
        )


class PasienPenyakitKronis(Base):
    """Tabel `pasien_penyakit_kronis` — riwayat penyakit kronis pasien."""

    __tablename__ = "pasien_penyakit_kronis"

    id_penyakit: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_pasien: Mapped[int] = mapped_column(
        ForeignKey("pasien.id_pasien"), nullable=False
    )
    nama_penyakit: Mapped[str] = mapped_column(String(100), nullable=False)
    kode_penyakit: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_penyakit_kronis.kode"), nullable=True,
        comment="Kode kanonik (master_penyakit_kronis). NULL=data lama; 99=Lain-lain free text",
    )
    catatan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[Optional[bool]] = mapped_column(
        Boolean, default=True, server_default="1", nullable=True
    )

    # Relationships
    pasien: Mapped["Pasien"] = relationship("Pasien", back_populates="penyakit_kronis")

    def __repr__(self) -> str:
        return f"<PasienPenyakitKronis(id={self.id_penyakit}, nama={self.nama_penyakit!r})>"


class MasterPenyakitKronis(Base):
    """Master kanonik penyakit kronis — kosakata BERSAMA Sehati + modul AI (Antropometri/DermAI).

    `kode` = identitas STABIL (jangan diubah/dipakai ulang). Tambah penyakit baru = kode baru.
    `kode = 99` dipakukan untuk "Lain-lain (free text)" — nilai free text disimpan di
    pasien_penyakit_kronis.nama_penyakit. Ref CONTRACT_SEHATI_ANTROPOMETRI_v0.1.md §5.
    """

    __tablename__ = "master_penyakit_kronis"

    kode: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    nama: Mapped[str] = mapped_column(String(100), nullable=False)
    urutan: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="Urutan tampil")
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )

    def __repr__(self) -> str:
        return f"<MasterPenyakitKronis(kode={self.kode}, nama={self.nama!r})>"
