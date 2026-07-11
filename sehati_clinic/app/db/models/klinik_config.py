"""
MasterKlinikConfig — profil/identitas klinik untuk Print Module + PO.

Saat ini SINGLETON (1 row id_config=1). MK-L1 (aditif) menambah field identitas untuk PO
(no_sia, rm_prefix, kode_klinik, is_default, is_active) + tabel anak `klinik_apoteker`
(daftar apoteker + SIPA, dipakai dropdown saat buat PO).

Rename fisik tabel -> `master_klinik` + multi-baris (multi-cabang) DITUNDA sampai cabang ke-2
benar-benar dideploy (lihat MASTER_KLINIK_MODULE_DESIGN.md). Field sengaja dinamai klinik_* agar
forward-compatible. Ref: DEC-047 (Print Module) + DEC-091/master_klinik design.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MasterKlinikConfig(Base):
    """Tabel `master_klinik_config` — profil/identitas klinik (kini singleton)."""

    __tablename__ = "master_klinik_config"

    id_config: Mapped[int] = mapped_column(
        Integer, primary_key=True,
        comment="PK klinik (kini singleton=1; kelak id_klinik multi-cabang)",
    )

    # --- Identitas cabang (MK-L1) ---
    kode_klinik: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True, comment="Kode cabang, mis. 'A' / 'ACN'",
    )
    rm_prefix: Mapped[Optional[str]] = mapped_column(
        String(5), nullable=True, comment="Prefix No. RM klinik ini (fallback ke env rm_clinic_prefix)",
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="1", default=True,
        comment="Klinik default (fallback identitas). Tepat 1 default.",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="1", default=True,
    )

    nama_klinik: Mapped[str] = mapped_column(
        String(100), nullable=False, default="Klinik Anda",
        server_default="Klinik Anda",
    )

    alamat_baris1: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    alamat_baris2: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    alamat_baris3: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)

    no_telepon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    no_whatsapp: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # --- Izin apotek (untuk PO) MK-L1 ---
    no_sia: Mapped[Optional[str]] = mapped_column(
        String(60), nullable=True, comment="Surat Izin Apotek (izin apotek/klinik) — untuk PO",
    )

    # --- Reorder point dinamis (DYN-L1): lead time + cadangan (hari), tunable global ---
    lead_time_hari: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="14", default=14,
        comment="Perkiraan waktu tunggu barang datang (hari) — untuk stok minimal dinamis",
    )
    safety_hari: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="7", default=7,
        comment="Hari cadangan (buffer) di atas lead time",
    )

    logo_path: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True,
        comment="Path relatif ke logo file (e.g., uploads/logo.png)",
    )

    mini_logo_path: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True,
        comment="Path relatif ke mini-logo (ikon topbar). Kosong = pakai huruf pertama nama klinik.",
    )

    footer_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    default_paper_nota: Mapped[str] = mapped_column(
        String(20), nullable=False, default="a5", server_default="a5",
        comment="a5 atau thermal",
    )
    default_paper_soap: Mapped[str] = mapped_column(
        String(20), nullable=False, default="a5", server_default="a5",
        comment="a5 atau thermal",
    )

    ttd_dokter_text: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="Optional sign-off untuk SOAP (e.g., Dokter Pemeriksa,)",
    )

    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True,
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        server_onupdate=func.current_timestamp(),
        nullable=True,
    )

    id_staf_last_edit: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True,
        comment="Audit — staff yang terakhir edit config",
    )

    apotekers: Mapped[list["KlinikApoteker"]] = relationship(
        "KlinikApoteker", back_populates="klinik", cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<MasterKlinikConfig(id={self.id_config}, "
            f"nama={self.nama_klinik!r}, paper_nota={self.default_paper_nota!r})>"
        )


class KlinikApoteker(Base):
    """Tabel `klinik_apoteker` — daftar apoteker + SIPA per klinik (dropdown saat buat PO).

    Bisa >1 apoteker; ada masa transisi perpanjangan SIPA → pakai is_active/masa_berlaku.
    PO meminjam SIPA dari sini (nama apoteker mengikuti SIPA yang dipilih).
    """

    __tablename__ = "klinik_apoteker"

    id_apoteker: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_klinik: Mapped[int] = mapped_column(
        ForeignKey("master_klinik_config.id_config"), nullable=False,
        comment="FK ke klinik (kini selalu 1)",
    )
    nama_apoteker: Mapped[str] = mapped_column(String(100), nullable=False)
    no_sipa: Mapped[Optional[str]] = mapped_column(
        String(60), nullable=True, comment="Surat Izin Praktik Apoteker",
    )
    masa_berlaku: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, comment="Tgl berakhir SIPA (opsional, untuk pengingat)",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="1", default=True,
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True,
    )

    klinik: Mapped["MasterKlinikConfig"] = relationship(
        "MasterKlinikConfig", back_populates="apotekers",
    )

    def __repr__(self) -> str:
        return (f"<KlinikApoteker(id={self.id_apoteker}, nama={self.nama_apoteker!r}, "
                f"sipa={self.no_sipa!r}, aktif={self.is_active})>")


__all__ = ["MasterKlinikConfig", "KlinikApoteker"]
