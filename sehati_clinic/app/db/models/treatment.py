"""
Treatment models.

Tabel:
- master_treatment (catalog treatment)
- treatment_komponen (formula bahan & alat per treatment)
- pasien_rencana_treatment (series plan per pasien)
- pasien_resep_iterasi (resep berulang per pasien)
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DECIMAL,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    TIMESTAMP,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._enums import (
    KategoriKomponenTreatmentEnum,
    StatusRencanaTreatmentEnum,
    SumberRencanaEnum,
)


class MasterTreatment(Base):
    """Tabel `master_treatment` — catalog treatment yang ditawarkan."""

    __tablename__ = "master_treatment"

    id_treatment: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nama_treatment: Mapped[str] = mapped_column(String(100), nullable=False)
    role_pelaksana: Mapped[str] = mapped_column(String(50), nullable=False)
    durasi_menit: Mapped[int] = mapped_column(Integer, nullable=False)
    harga: Mapped[float] = mapped_column(DECIMAL(12, 2), nullable=False)
    # Harga per-sesi pada paket series (lebih murah dari harga normal).
    # NULL = tidak ada paket khusus → fallback ke harga normal × jumlah_sesi.
    # DEC-049: pricing untuk series treatment.
    harga_paket: Mapped[Optional[float]] = mapped_column(DECIMAL(15, 2), nullable=True)

    # KOMISI SYSTEM HYBRID (Task #360, DEC-060):
    # Akuntansi standar: komisi MASUK HPP/COGS (bukan recursive % laba bersih).
    #   HPP = BHP + komisi_dokter + komisi_perawat
    #   laba_bersih = harga - HPP - pajak
    # Komisi dihitung berdasarkan tipe (3 mode hybrid, independent per pelaku):
    #   - "PERSEN_HARGA": value % × harga jual
    #   - "PERSEN_MARGIN": value % × (harga - BHP)
    #   - "NOMINAL": value rupiah flat
    bhp_per_pakai_nominal: Mapped[Optional[float]] = mapped_column(
        DECIMAL(12, 2), default=0, server_default="0", nullable=True
    )
    komisi_dokter_tipe: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    komisi_dokter_value: Mapped[Optional[float]] = mapped_column(
        DECIMAL(12, 2), default=0, server_default="0", nullable=True
    )
    komisi_perawat_tipe: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    komisi_perawat_value: Mapped[Optional[float]] = mapped_column(
        DECIMAL(12, 2), default=0, server_default="0", nullable=True
    )
    pajak_persen: Mapped[Optional[float]] = mapped_column(
        DECIMAL(5, 2), default=0, server_default="0", nullable=True
    )
    # Pajak nominal: kalau diisi, override pajak_persen. NULL = pakai persen.
    pajak_nominal: Mapped[Optional[float]] = mapped_column(DECIMAL(12, 2), nullable=True)

    is_active: Mapped[Optional[bool]] = mapped_column(
        Boolean, default=True, server_default="1", nullable=True
    )
    butuh_otorisasi: Mapped[Optional[bool]] = mapped_column(
        Boolean, default=False, server_default="0", nullable=True
    )

    # Default rentang minggu antar sesi untuk series planning
    default_rentang_mulai_minggu: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    default_rentang_akhir_minggu: Mapped[int] = mapped_column(
        Integer, default=12, server_default="12", nullable=False
    )

    id_staf: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
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
        return f"<MasterTreatment(id={self.id_treatment}, nama={self.nama_treatment!r})>"


class TreatmentKomponen(Base):
    """Tabel `treatment_komponen` — formula bahan & alat per treatment."""

    __tablename__ = "treatment_komponen"

    id_komponen: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_treatment: Mapped[int] = mapped_column(
        ForeignKey("master_treatment.id_treatment"), nullable=False
    )
    kategori: Mapped[KategoriKomponenTreatmentEnum] = mapped_column(
        Enum(KategoriKomponenTreatmentEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    id_bahan: Mapped[Optional[int]] = mapped_column(
        ForeignKey("inventory_stok.id_bahan"), nullable=True
    )
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    satuan: Mapped[str] = mapped_column(String(20), nullable=False)

    def __repr__(self) -> str:
        return (
            f"<TreatmentKomponen(id={self.id_komponen}, "
            f"kategori={self.kategori.value}, qty={self.qty})>"
        )


class PasienRencanaTreatment(Base):
    """Tabel `pasien_rencana_treatment` — series plan treatment per pasien."""

    __tablename__ = "pasien_rencana_treatment"

    id_rencana: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_pasien: Mapped[int] = mapped_column(
        ForeignKey("pasien.id_pasien"), nullable=False
    )
    id_treatment: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_treatment.id_treatment"), nullable=True
    )
    urutan_sesi: Mapped[int] = mapped_column(Integer, nullable=False)
    nama_tindakan: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="Snapshot nama saat plan dibuat (kalau treatment di-rename, history tetap akurat)",
    )

    sumber_rencana: Mapped[SumberRencanaEnum] = mapped_column(
        Enum(SumberRencanaEnum, values_callable=lambda x: [e.value for e in x]),
        default=SumberRencanaEnum.DOKTER_PLAN,
        server_default=SumberRencanaEnum.DOKTER_PLAN.value,
        nullable=False,
    )
    id_referensi_sumber: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    id_kunjungan_pembuat: Mapped[Optional[int]] = mapped_column(
        ForeignKey("kunjungan.id_kunjungan"), nullable=True
    )

    status: Mapped[StatusRencanaTreatmentEnum] = mapped_column(
        Enum(StatusRencanaTreatmentEnum, values_callable=lambda x: [e.value for e in x]),
        default=StatusRencanaTreatmentEnum.PENDING,
        server_default=StatusRencanaTreatmentEnum.PENDING.value,
        nullable=False,
    )

    tgl_target_mulai: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    tgl_target_akhir: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    id_kunjungan_eksekusi: Mapped[Optional[int]] = mapped_column(
        ForeignKey("kunjungan.id_kunjungan"), nullable=True
    )
    tgl_eksekusi: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    catatan_dokter: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<PasienRencanaTreatment(id={self.id_rencana}, "
            f"sesi={self.urutan_sesi}, status={self.status.value})>"
        )


class PasienResepIterasi(Base):
    """Tabel `pasien_resep_iterasi` — resep yang bisa diulang sebanyak N kali."""

    __tablename__ = "pasien_resep_iterasi"

    id_iterasi: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_pasien: Mapped[int] = mapped_column(
        ForeignKey("pasien.id_pasien"), nullable=False
    )
    id_produk: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_produk.id_produk"), nullable=True
    )
    nama_produk: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="Snapshot nama saat iterasi dibuat (untuk audit history)",
    )

    qty_per_iterasi: Mapped[float] = mapped_column(
        Float, default=1.0, server_default="1.0", nullable=False
    )
    tgl_kadaluarsa: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )
