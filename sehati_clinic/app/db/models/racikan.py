"""Racikan models (modul obat racikan — Fase 1).

Tabel:
- master_biaya_racik     : tarif FLAT ongkos racik per jenis (KAPSUL/PUYER/KRIM)
- master_racikan         : Formula Racikan (template) — menyimpan KOMPOSISI, bukan harga
- master_racikan_bahan   : komposisi bahan per formula (produk + dosis per unit)

Prinsip (lihat Project_Memory/DESAIN_MODUL_RACIKAN.md):
- Formula TIDAK menyimpan harga. Harga dihitung saat dipakai, dari harga bahan saat itu.
- Mode MG/tablet : butir = (dosis_per_unit × N) ÷ kekuatan_nilai, dibulatkan KE ATAS, ditagih penuh.
- Mode GRAM/krim : PRO-RATA, harga_per_gram = harga_jual ÷ isi_kemasan.
- TOTAL = Σ biaya bahan + tarif flat master_biaya_racik.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DECIMAL,
    ForeignKey,
    Integer,
    String,
    TIMESTAMP,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MasterBiayaRacik(Base):
    """Tabel `master_biaya_racik` — ongkos racik FLAT per jenis racikan."""

    __tablename__ = "master_biaya_racik"

    id_biaya_racik: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # KAPSUL / PUYER / KRIM — bisa ditambah lewat master, bukan enum supaya fleksibel.
    jenis_racik: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    nama: Mapped[str] = mapped_column(String(50), nullable=False)
    # Tarif FLAT per racikan (bukan per unit). Keputusan dr. Hansen 2026-09-20.
    tarif: Mapped[float] = mapped_column(DECIMAL(12, 2), default=0, server_default="0", nullable=False)
    is_active: Mapped[Optional[bool]] = mapped_column(
        Boolean, default=True, server_default="1", nullable=True
    )

    def __repr__(self) -> str:
        return f"<MasterBiayaRacik({self.jenis_racik!r}, tarif={self.tarif})>"


class MasterRacikan(Base):
    """Tabel `master_racikan` — Formula Racikan (template komposisi)."""

    __tablename__ = "master_racikan"

    id_racikan: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nama: Mapped[str] = mapped_column(String(100), nullable=False)
    jenis_racik: Mapped[str] = mapped_column(String(20), nullable=False)
    # Jumlah unit default (mis. 15 kapsul) — dokter tetap bisa ubah saat meresepkan.
    default_jumlah_unit: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    default_aturan_pakai: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    catatan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[Optional[bool]] = mapped_column(
        Boolean, default=True, server_default="1", nullable=True
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
        return f"<MasterRacikan(id={self.id_racikan}, nama={self.nama!r}, {self.jenis_racik})>"


class MasterRacikanBahan(Base):
    """Tabel `master_racikan_bahan` — komposisi bahan per formula."""

    __tablename__ = "master_racikan_bahan"

    id_racikan_bahan: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_racikan: Mapped[int] = mapped_column(
        ForeignKey("master_racikan.id_racikan"), nullable=False
    )
    id_produk: Mapped[int] = mapped_column(
        ForeignKey("master_produk.id_produk"), nullable=False
    )
    # Dosis per 1 unit racikan (mg untuk tablet, gram untuk krim).
    dosis_per_unit: Mapped[float] = mapped_column(DECIMAL(10, 3), nullable=False)
    satuan_dosis: Mapped[str] = mapped_column(
        String(10), default="mg", server_default="mg", nullable=False
    )
    urutan: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    def __repr__(self) -> str:
        return (
            f"<MasterRacikanBahan(racikan={self.id_racikan}, produk={self.id_produk}, "
            f"dosis={self.dosis_per_unit}{self.satuan_dosis})>"
        )


class KunjunganRacikan(Base):
    """Tabel `kunjungan_racikan` — racikan yang DIRESEPKAN pada satu kunjungan (SNAPSHOT).

    Harga dikunci saat dokter menyimpan SOAP; kasir hanya membaca. Harga bahan boleh
    berubah besok — nota lama tetap utuh. Pola snapshot sama seperti PO/retur/diagnosa.
    """

    __tablename__ = "kunjungan_racikan"

    id_kunjungan_racikan: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_kunjungan: Mapped[int] = mapped_column(
        ForeignKey("kunjungan.id_kunjungan"), nullable=False
    )
    # NULL = racikan ad-hoc (tidak dari formula tersimpan)
    id_racikan: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_racikan.id_racikan"), nullable=True
    )
    nama_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    jenis_racik: Mapped[str] = mapped_column(String(20), nullable=False)
    jumlah_unit: Mapped[int] = mapped_column(Integer, nullable=False)
    aturan_pakai: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    subtotal_bahan: Mapped[float] = mapped_column(DECIMAL(12, 2), default=0, server_default="0", nullable=False)
    biaya_racik: Mapped[float] = mapped_column(DECIMAL(12, 2), default=0, server_default="0", nullable=False)
    total: Mapped[float] = mapped_column(DECIMAL(12, 2), default=0, server_default="0", nullable=False)

    # PENDING (belum ditagih) → DIBAYAR (masuk transaksi kasir) → BATAL (void).
    # Hanya baris PENDING yang boleh diganti saat dokter menyimpan ulang SOAP.
    status_item: Mapped[str] = mapped_column(
        String(20), default="PENDING", server_default="PENDING", nullable=False
    )
    # Fase 3: transaksi kasir yang menagih racikan ini (NULL selama PENDING).
    id_transaksi: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transaksi_kasir.id_transaksi"), nullable=True
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<KunjunganRacikan(id={self.id_kunjungan_racikan}, kunj={self.id_kunjungan}, "
            f"{self.nama_snapshot!r} x{self.jumlah_unit}, total={self.total})>"
        )


class KunjunganRacikanBahan(Base):
    """Tabel `kunjungan_racikan_bahan` — rincian bahan per racikan yang diresepkan (SNAPSHOT).

    `dipakai` = jumlah butir (mode MG, sudah dibulatkan KE ATAS) atau gram (mode GRAM,
    pro-rata). Ini yang dipotong dari stok saat penyerahan (Fase 3).
    """

    __tablename__ = "kunjungan_racikan_bahan"

    id_kunjungan_racikan_bahan: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_kunjungan_racikan: Mapped[int] = mapped_column(
        ForeignKey("kunjungan_racikan.id_kunjungan_racikan"), nullable=False
    )
    id_produk: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_produk.id_produk"), nullable=True
    )
    nama_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)

    dosis_per_unit: Mapped[float] = mapped_column(DECIMAL(10, 3), nullable=False)
    satuan_dosis: Mapped[str] = mapped_column(String(10), nullable=False)
    # Basis hitung saat itu: kekuatan per butir (MG) atau isi kemasan (GRAM)
    kekuatan_snapshot: Mapped[Optional[float]] = mapped_column(DECIMAL(10, 3), nullable=True)
    mode_hitung: Mapped[str] = mapped_column(String(10), default="MG", server_default="MG", nullable=False)

    dipakai: Mapped[float] = mapped_column(DECIMAL(12, 3), nullable=False)
    satuan_dipakai: Mapped[str] = mapped_column(String(10), nullable=False)
    harga_satuan: Mapped[float] = mapped_column(DECIMAL(12, 2), nullable=False)
    subtotal: Mapped[float] = mapped_column(DECIMAL(12, 2), nullable=False)

    def __repr__(self) -> str:
        return (
            f"<KunjunganRacikanBahan({self.nama_snapshot!r}, dipakai={self.dipakai}"
            f"{self.satuan_dipakai}, sub={self.subtotal})>"
        )


class TransaksiDetailRacikan(Base):
    """Tabel `transaksi_detail_racikan` — baris tagihan racikan pada satu transaksi kasir.

    Tabel detail SENDIRI, bukan menumpang `transaksi_detail_produk`, karena di sana
    `id_produk` NOT NULL sedangkan satu racikan terdiri dari banyak bahan. Memaksakannya
    akan merusak reverse-stok void, suggested order, riwayat pasien, dan export.

    Isinya SNAPSHOT: nota lama tetap utuh walau racikan/harga bahan berubah kemudian.
    """

    __tablename__ = "transaksi_detail_racikan"

    id_detail_racikan: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_transaksi: Mapped[int] = mapped_column(
        ForeignKey("transaksi_kasir.id_transaksi"), nullable=False
    )
    id_kunjungan_racikan: Mapped[int] = mapped_column(
        ForeignKey("kunjungan_racikan.id_kunjungan_racikan"), nullable=False
    )

    nama_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    jenis_racik: Mapped[str] = mapped_column(String(20), nullable=False)
    jumlah_unit: Mapped[int] = mapped_column(Integer, nullable=False)

    subtotal_bahan: Mapped[float] = mapped_column(DECIMAL(12, 2), default=0, server_default="0", nullable=False)
    biaya_racik: Mapped[float] = mapped_column(DECIMAL(12, 2), default=0, server_default="0", nullable=False)
    # Diskon member yang BENAR-BENAR dikenakan pada baris ini (keputusan dr. Hansen
    # 2026-09-21: diskon berlaku ke SELURUH total racikan, termasuk ongkos racik).
    diskon_item: Mapped[float] = mapped_column(DECIMAL(12, 2), default=0, server_default="0", nullable=False)
    subtotal: Mapped[float] = mapped_column(DECIMAL(12, 2), nullable=False)

    # Sejajar transaksi_detail_produk: penanda apakah stok bahan sudah dikembalikan saat void.
    void_reverse_stok: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<TransaksiDetailRacikan(trx={self.id_transaksi}, {self.nama_snapshot!r} "
            f"x{self.jumlah_unit}, sub={self.subtotal})>"
        )
