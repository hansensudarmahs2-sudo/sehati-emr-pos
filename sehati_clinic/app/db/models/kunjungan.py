"""
Kunjungan dan tabel turunannya.

Tabel:
- kunjungan (master per kunjungan)
- kunjungan_antropometri
- kunjungan_foto
- kunjungan_resep
- kunjungan_tindakan
- pemeriksaan_klinis (SOAP dokter)
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    event,
    Float,
    ForeignKey,
    Integer,
    String,
    TIMESTAMP,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm.base import NO_VALUE

from app.db.base import Base
from app.db.models._enums import (
    KategoriFotoEnum,
    StatusItemResepEnum,
    StatusTindakanEnum,
)


class Kunjungan(Base):
    """Tabel `kunjungan` — 1 baris per kunjungan pasien."""

    __tablename__ = "kunjungan"

    id_kunjungan: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_pasien: Mapped[int] = mapped_column(
        ForeignKey("pasien.id_pasien"), nullable=False
    )
    id_booking: Mapped[Optional[int]] = mapped_column(
        ForeignKey("jadwal_booking.id_booking"), nullable=True
    )
    id_staf_fo: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True
    )
    # FO-ASSIGN-DOKTER (Task #329, DEC-058): dokter yang di-assign FO saat
    # daftarkan antrian konsultasi. NULL = bebas claim oleh dokter manapun
    # (back-compat dengan kunjungan existing).
    id_staf_dokter_assigned: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True
    )

    tgl_kunjungan: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=True
    )
    nomor_antrean: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status_antrian: Mapped[Optional[str]] = mapped_column(
        String(50), default="ANTRI_KONSULTASI", server_default="ANTRI_KONSULTASI", nullable=True
    )
    sumber_pendaftaran: Mapped[Optional[str]] = mapped_column(
        String(50), default="WALK_IN", server_default="WALK_IN", nullable=True
    )

    # --- Asal resep (task apotek 2026-09-25) --------------------------------
    # Sebelum ini TIDAK ADA kolom yang membedakan kunjungan konsultasi dari
    # beli-produk-saja; pembedanya cuma `"flow": "BELI_PRODUK_ONLY"` di JSON audit_log,
    # yang tidak bisa di-query untuk UI maupun laporan.
    jenis_kunjungan: Mapped[str] = mapped_column(
        String(20), default="KLINIS", server_default="KLINIS", nullable=False,
        comment="KLINIS / RESEP_LUAR / RESEP_ONLINE / TEBUS_LANJUT",
    )
    # Diisi hanya untuk RESEP_LUAR. Diletakkan di kunjungan, bukan kunjungan_resep:
    # satu lembar resep berlaku untuk semua obat di dalamnya.
    peresep_luar_nama: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    peresep_luar_asal: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    # TEBUS_LANJUT membuat kunjungan BARU yang menunjuk ke asalnya — bukan menghidupkan
    # kunjungan lama, karena antrian kasir & apotek menyaring HARI INI.
    id_kunjungan_asal: Mapped[Optional[int]] = mapped_column(
        ForeignKey("kunjungan.id_kunjungan"), nullable=True
    )

    keluhan_utama: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tgl_kontrol_selanjutnya: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    catatan_kontrol: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
        comment="Catatan rencana kontrol/follow-up dari dokter (modul #7)",
    )

    # OBAT TERTUNDA (P1-1): obat sudah dibayar tapi diserah/dikirim belakangan.
    tgl_janji_kirim: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True,
        comment="Tanggal janji kirim/ambil obat tertunda (diisi apotek saat Tunda serah)",
    )
    catatan_kirim: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
        comment="Catatan/alamat/kurir untuk obat tertunda",
    )

    # WARNA_ANTRIAN_FO: waktu pasien masuk status_antrian saat ini (untuk hitung wait per-tahap).
    # server_default → baris baru otomatis = waktu masuk (ANTRI_KONSULTASI); transisi di-stempel event listener (EOF).
    waktu_masuk_status: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=True
    )

    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<Kunjungan(id={self.id_kunjungan}, antrean={self.nomor_antrean}, "
            f"status={self.status_antrian!r})>"
        )


class KunjunganAntropometri(Base):
    """Tabel `kunjungan_antropometri` — pengukuran fisik pasien per kunjungan."""

    __tablename__ = "kunjungan_antropometri"

    id_antropometri: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_kunjungan: Mapped[int] = mapped_column(
        ForeignKey("kunjungan.id_kunjungan"), nullable=False
    )
    id_staf: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True
    )

    berat_badan: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tinggi_badan: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tekanan_darah: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    suhu_tubuh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    skinfold_titik_1: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    skinfold_titik_2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    skinfold_titik_3: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lingkar_perut: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )
    # updated_at — auto-bump saat row di-UPDATE (MySQL ON UPDATE CURRENT_TIMESTAMP).
    # Dipakai untuk endpoint `/antropometri/pasien/{id}/terakhir` supaya yang
    # terakhir di-edit dokter menang (bukan yang terakhir di-INSERT).
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        server_onupdate=func.current_timestamp(),
        nullable=True,
    )


class KunjunganFoto(Base):
    """Tabel `kunjungan_foto` — foto before/after/progress pasien.

    Phase 1: tabel placeholder, upload logic dikerjakan di Phase 2.
    """

    __tablename__ = "kunjungan_foto"

    id_foto: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_kunjungan: Mapped[int] = mapped_column(
        ForeignKey("kunjungan.id_kunjungan"), nullable=False
    )
    id_pasien: Mapped[int] = mapped_column(
        ForeignKey("pasien.id_pasien"), nullable=False
    )

    kategori: Mapped[Optional[KategoriFotoEnum]] = mapped_column(
        Enum(KategoriFotoEnum, values_callable=lambda x: [e.value for e in x]),
        default=KategoriFotoEnum.BEFORE,
        server_default=KategoriFotoEnum.BEFORE.value,
        nullable=True,
    )
    url_path: Mapped[str] = mapped_column(String(255), nullable=False)
    keterangan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )


class KunjunganResep(Base):
    """Tabel `kunjungan_resep` — produk yang diresepkan dokter per kunjungan."""

    __tablename__ = "kunjungan_resep"

    id_resep: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_kunjungan: Mapped[int] = mapped_column(
        ForeignKey("kunjungan.id_kunjungan"), nullable=False
    )
    id_produk: Mapped[int] = mapped_column(
        ForeignKey("master_produk.id_produk"), nullable=False
    )

    qty: Mapped[float] = mapped_column(Float, nullable=False)
    aturan_pakai: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status_item: Mapped[Optional[StatusItemResepEnum]] = mapped_column(
        Enum(StatusItemResepEnum, values_callable=lambda x: [e.value for e in x]),
        default=StatusItemResepEnum.PENDING,
        server_default=StatusItemResepEnum.PENDING.value,
        nullable=True,
    )

    id_staf_input: Mapped[int] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=False
    )
    id_staf_void: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True
    )
    waktu_input: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=True
    )
    waktu_void: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)

    # Task #54 — penyerahan PER ITEM. Diisi saat item benar-benar diserahkan (stok
    # dipotong), bukan saat kunjungan selesai. Dipakai laporan apoteker supaya kredit
    # jatuh ke orang yang menyerahkan item itu, walau satu kunjungan diserahkan
    # beberapa kali oleh orang berbeda.
    waktu_serah: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    id_staf_serah: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True
    )

    # Tebus lanjut: baris ini SALINAN dari resep lama yang baru ditebus sekarang.
    # Keberadaan salinan = penanda baris asal SUDAH ditebus. Sengaja TIDAK ada kolom
    # "sudah_ditebus" di baris asal: dua penanda untuk satu fakta bisa berselisih.
    id_resep_asal: Mapped[Optional[int]] = mapped_column(
        ForeignKey("kunjungan_resep.id_resep"), nullable=True
    )


class KunjunganTindakan(Base):
    """Tabel `kunjungan_tindakan` — treatment yang dieksekusi per kunjungan."""

    __tablename__ = "kunjungan_tindakan"

    id_kunjungan_tindakan: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_kunjungan: Mapped[int] = mapped_column(
        ForeignKey("kunjungan.id_kunjungan"), nullable=False
    )
    id_treatment: Mapped[int] = mapped_column(
        ForeignKey("master_treatment.id_treatment"), nullable=False
    )

    status_tindakan: Mapped[Optional[StatusTindakanEnum]] = mapped_column(
        Enum(StatusTindakanEnum, values_callable=lambda x: [e.value for e in x]),
        default=StatusTindakanEnum.PENDING,
        server_default=StatusTindakanEnum.PENDING.value,
        nullable=True,
    )
    id_staf_pelaksana: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True
    )

    # K-L0 (komisi): 2 pelaksana untuk atribusi komisi (DEC-087)
    id_dokter_pelaksana: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True,
        comment="Dokter pelaksana (komisi_dokter). Auto = dokter assigned kunjungan.",
    )
    id_perawat_pelaksana: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True,
        comment="Perawat pelaksana (komisi_perawat) = perawat yang memulai tindakan.",
    )

    # Link ke kuota member (kalau pakai kuota) & rencana series
    id_kuota_member: Mapped[Optional[int]] = mapped_column(
        ForeignKey("pasien_membership_kuota.id_kuota"), nullable=True
    )
    id_rencana: Mapped[Optional[int]] = mapped_column(
        ForeignKey("pasien_rencana_treatment.id_rencana"), nullable=True
    )

    waktu_mulai: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    waktu_selesai: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class PemeriksaanKlinis(Base):
    """Tabel `pemeriksaan_klinis` — SOAP dokter per kunjungan."""

    __tablename__ = "pemeriksaan_klinis"

    id_pemeriksaan: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_kunjungan: Mapped[int] = mapped_column(
        ForeignKey("kunjungan.id_kunjungan"), nullable=False
    )
    id_pasien: Mapped[int] = mapped_column(
        ForeignKey("pasien.id_pasien"), nullable=False
    )
    id_staf_dokter: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True
    )

    anamnesa: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pemeriksaan_fisik: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    diagnosa: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Repurposed: catatan untuk perawat (saat eksekusi) & instruksi pasien (saat pakai produk)
    saran_treatment: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Catatan dokter untuk perawat saat eksekusi (warning, special handling)",
    )
    saran_produk: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Instruksi pemakaian produk untuk pasien (cara pakai, dosis)",
    )

    # --- Draf SOAP oleh apoteker (konsultasi online) ------------------------
    # Apoteker menyalin inti percakapan jadi DRAF; dokter membaca, menyunting bila perlu,
    # lalu menyetujuinya jadi SOAP miliknya. Draf menumpang tabel ini (bukan tabel
    # terpisah) supaya begitu disetujui ia otomatis ikut ke riwayat, resume medis, dan
    # tautan diagnosa.
    #
    # ⚠ KONSEKUENSI: setiap query atas tabel ini kini bisa ikut menarik draf yang BELUM
    # disetujui. Semua harus menyaring `status_soap == "FINAL"` kecuali memang sengaja
    # ingin melihat draf. Pola kegagalannya sama dengan `_produk_stok_sudah_dipotong`:
    # satu tabel dipakai dua arti, query lama masih mengira artinya cuma satu.
    status_soap: Mapped[str] = mapped_column(
        String(20), default="FINAL", server_default="FINAL", nullable=False,
        comment="DRAFT_APOTEK = belum disetujui dokter. FINAL = sah.",
    )
    # TIDAK dihapus saat dokter menyetujui: asal-usul catatan tetap terbaca, dan justru
    # melindungi dokter — rantainya jelas kalau kelak ditanya atas dasar apa ia menyetujui.
    id_staf_penyusun: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_staf.id_staf"), nullable=True
    )
    # Dua waktu yang BERBEDA. SOAP yang disetujui tiga hari kemudian tidak boleh terbaca
    # seolah pemeriksaannya terjadi hari itu.
    waktu_konsultasi: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    waktu_disetujui: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

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
        return f"<PemeriksaanKlinis(id={self.id_pemeriksaan}, kunjungan={self.id_kunjungan})>"


# =============================================================================
# WARNA_ANTRIAN_FO: stempel waktu_masuk_status setiap status_antrian BERUBAH.
# Menangkap transisi antar-tahap di titik mana pun (satu tempat, low-surface).
# Dijaga: lewati set pertama (init/load: oldvalue NO_VALUE) & set tak berubah →
# failure mode aman (under-stamp → fallback tgl_kunjungan, bukan salah stempel).
# =============================================================================
@event.listens_for(Kunjungan.status_antrian, "set", propagate=True)
def _stamp_waktu_masuk_status(target, value, oldvalue, initiator):
    if value is None or oldvalue is NO_VALUE or value == oldvalue:
        return
    target.waktu_masuk_status = datetime.now()
