"""Diagnosa models (modul #24–#27).

Tabel:
- ref_diagnosa          : kamus diagnosa (ICD-10 WHO + estetik internal JD-xxx)
- diagnosa_paket_item   : paket tindakan/produk default per diagnosa (auto-fill)
- kunjungan_diagnosa    : diagnosa tercatat per kunjungan (multi, primer/sekunder)

Desain: Project_Memory/DESAIN_MODUL_DIAGNOSA_ICD_ESTETIK.md
Pola snapshot mengikuti pengadaan/retur (rekam medis tahan rename master).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DECIMAL,
    Enum,
    ForeignKey,
    Integer,
    String,
    TIMESTAMP,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._enums import SistemDiagnosaEnum, TipeItemPaketEnum


class RefDiagnosa(Base):
    """Tabel `ref_diagnosa` — kamus diagnosa ICD-10 + estetik internal."""

    __tablename__ = "ref_diagnosa"
    __table_args__ = (
        UniqueConstraint("sistem", "kode", name="uq_refdiagnosa_sistem_kode"),
    )

    id_diagnosa: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sistem: Mapped[SistemDiagnosaEnum] = mapped_column(
        Enum(SistemDiagnosaEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    kode: Mapped[str] = mapped_column(String(20), nullable=False)
    nama: Mapped[str] = mapped_column(String(255), nullable=False)
    # Nama Inggris asli (ICD) — untuk klaim/SatuSehat. NULL untuk estetik internal.
    nama_en: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    kategori: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Default hari kontrol saat diagnosa ini jadi primer (ICD=7, estetik=14; override per kode).
    default_kontrol_hari: Mapped[int] = mapped_column(
        Integer, default=7, server_default="7", nullable=False
    )
    is_active: Mapped[Optional[bool]] = mapped_column(
        Boolean, default=True, server_default="1", nullable=True
    )
    catatan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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
        return f"<RefDiagnosa(id={self.id_diagnosa}, {self.sistem.value}:{self.kode!r})>"


class DiagnosaPaketItem(Base):
    """Tabel `diagnosa_paket_item` — paket tindakan/produk default per diagnosa."""

    __tablename__ = "diagnosa_paket_item"

    id_paket_item: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_diagnosa: Mapped[int] = mapped_column(
        ForeignKey("ref_diagnosa.id_diagnosa"), nullable=False
    )
    tipe_item: Mapped[TipeItemPaketEnum] = mapped_column(
        Enum(TipeItemPaketEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    id_treatment: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_treatment.id_treatment"), nullable=True
    )
    id_produk: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_produk.id_produk"), nullable=True
    )
    qty_default: Mapped[Optional[float]] = mapped_column(
        DECIMAL(12, 2), default=1, server_default="1", nullable=True
    )
    # Auto-fill aturan pakai (khusus PRODUK) ke baris resep.
    aturan_pakai_default: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    urutan: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    catatan: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<DiagnosaPaketItem(id={self.id_paket_item}, dx={self.id_diagnosa}, "
            f"{self.tipe_item.value})>"
        )


class KunjunganDiagnosa(Base):
    """Tabel `kunjungan_diagnosa` — diagnosa per kunjungan (multi, primer/sekunder)."""

    __tablename__ = "kunjungan_diagnosa"

    id_kunjungan_diagnosa: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_kunjungan: Mapped[int] = mapped_column(
        ForeignKey("kunjungan.id_kunjungan"), nullable=False
    )
    # NULL = diagnosa teks bebas (tidak ada di kamus).
    id_diagnosa: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ref_diagnosa.id_diagnosa"), nullable=True
    )
    # Snapshot — tahan terhadap rename/nonaktif master di kemudian hari.
    sistem_snapshot: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    kode_snapshot: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    nama_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)

    is_primer: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    urutan: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    catatan: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<KunjunganDiagnosa(id={self.id_kunjungan_diagnosa}, "
            f"kunj={self.id_kunjungan}, {self.kode_snapshot!r}, primer={self.is_primer})>"
        )
