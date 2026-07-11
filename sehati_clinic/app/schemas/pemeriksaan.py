"""
Pydantic schemas untuk PemeriksaanService (SOAP dokter + tindakan + resep).

Pattern dari kode lama dokter Bapak (`main_api.py` line 1079-1138):
- 1 endpoint compound `POST /dokter/input-medis` yang melakukan 4 hal atomik:
  1. INSERT SOAP (anamnesa, PF, diagnosa)
  2. INSERT tindakan baru (single → kunjungan_tindakan, series → pasien_rencana_treatment)
  3. INSERT resep produk
  4. UPDATE kunjungan.status_antrian (transition KONSULTASI → ANTRI_TREATMENT/ANTRI_BAYAR)
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Sub-schemas untuk InputMedisRequest
# =============================================================================
class TindakanBaruItem(BaseModel):
    """
    1 baris tindakan yang diresepkan dokter di kunjungan ini.

    - is_series=False, jumlah_sesi=1 → Single tindakan hari ini (langsung ke perawat).
    - is_series=True, jumlah_sesi=N → Series plan (N sesi, dimulai dari sesi 1).
    """
    id_treatment: int = Field(..., ge=1)
    is_series: bool = False
    jumlah_sesi: int = Field(default=1, ge=1, le=20)
    catatan_dokter: str = ""  # opsional, untuk perawat/series


class ResepProdukItem(BaseModel):
    """1 baris produk yang diresepkan dokter."""
    id_produk: int = Field(..., ge=1)
    qty: float = Field(..., gt=0)
    aturan_pakai: str = Field(default="", max_length=100)


# =============================================================================
# Request — input medis compound
# =============================================================================
class InputMedisRequest(BaseModel):
    """
    Request untuk endpoint `POST /dokter/input-medis`.

    Semua dalam 1 transaksi atomik. Field SOAP wajib. Tindakan & resep opsional.
    """
    # Identifiers — wajib
    id_kunjungan: int = Field(..., ge=1, description="ID kunjungan yang sedang dikonsultasi.")
    id_pasien: int = Field(..., ge=1, description="ID pasien (dicek match dengan id_kunjungan).")

    # SOAP — boleh kosong field demi field, tapi compulsory ada 1 dari (anamnesa, PF, diagnosa)
    anamnesa: str = ""
    pemeriksaan_fisik: str = ""
    diagnosa: str = ""
    saran_treatment: str = Field(
        default="",
        description="Catatan dokter untuk perawat saat eksekusi (warning, special handling).",
    )
    saran_produk: str = Field(
        default="",
        description="Instruksi tambahan dokter untuk pasien saat pakai produk.",
    )

    # Treatment & resep — opsional
    tindakan_baru: list[TindakanBaruItem] = Field(default_factory=list)
    resep_produk: list[ResepProdukItem] = Field(default_factory=list)


# =============================================================================
# Response — input medis sukses
# =============================================================================
class InputMedisResponse(BaseModel):
    """Response setelah submit input medis. Sertakan summary apa yang dibuat."""
    status: str = "success"
    message: str
    data: dict  # { id_pemeriksaan, jumlah_tindakan_single, jumlah_rencana_series, jumlah_resep, status_kunjungan_baru }


# =============================================================================
# Sub-schemas untuk dashboard dokter (header & summary)
# =============================================================================
class SoapRingkasItem(BaseModel):
    """1 baris riwayat SOAP untuk cardbox kiri-atas dashboard dokter."""
    model_config = ConfigDict(from_attributes=True)
    id_pemeriksaan: int
    tanggal: Optional[datetime] = None
    nama_dokter: Optional[str] = None
    ringkasan_anamnesa: Optional[str] = None
    ringkasan_diagnosa: Optional[str] = None
    full_anamnesa: Optional[str] = None       # untuk pop-up
    full_diagnosa: Optional[str] = None


class ProdukDibeliRingkas(BaseModel):
    """1 baris produk yang sudah dibeli (DIBAYAR) untuk cardbox kiri-bawah."""
    model_config = ConfigDict(from_attributes=True)
    tanggal: Optional[datetime] = None
    nama_produk: str
    qty: float


class TreatmentSelesaiRingkas(BaseModel):
    """1 baris treatment yang sudah SELESAI untuk cardbox kanan-bawah."""
    model_config = ConfigDict(from_attributes=True)
    tanggal: Optional[datetime] = None
    nama_treatment: str


class SummaryDokterResponse(BaseModel):
    """
    Response untuk `GET /dokter/pasien/{id}/summary` — dashboard 4 cardbox.

    Untuk Phase 1, foto module belum diimplementasi — return empty list.
    """
    status: str = "success"
    cardbox_kiri_atas_soap: list[SoapRingkasItem] = Field(default_factory=list)
    cardbox_kiri_bawah_produk: list[ProdukDibeliRingkas] = Field(default_factory=list)
    cardbox_kanan_bawah_treatment: list[TreatmentSelesaiRingkas] = Field(default_factory=list)
    cardbox_kanan_atas_foto: list = Field(default_factory=list)  # placeholder


# =============================================================================
# HEADER PASIEN — 3 grid dashboard atas dokter
# =============================================================================
class DetailHoverIdentitas(BaseModel):
    no_rm: str
    membership: Optional[str] = None
    telepon: Optional[str] = None
    alamat: Optional[str] = None


class GridIdentitas(BaseModel):
    nama: str
    usia: int
    jenis_kelamin: Optional[str] = None
    detail_hover: DetailHoverIdentitas


class AlergiRingkasItem(BaseModel):
    id_alergi: int
    alergen: str
    gejala: Optional[str] = None
    tingkat_keparahan: Optional[str] = None


class GridAlergi(BaseModel):
    total_alergi: int = 0
    alergi_display: Optional[AlergiRingkasItem] = None
    daftar_lengkap: list[AlergiRingkasItem] = Field(default_factory=list)


class AntropometriHeaderData(BaseModel):
    berat_badan: Optional[float] = None
    tinggi_badan: Optional[float] = None
    bmi: Optional[float] = None
    kategori_bmi: Optional[str] = None
    fat_percentage: Optional[float] = None
    lean_percentage: Optional[float] = None
    tekanan_darah: Optional[str] = None
    tgl_ukur: Optional[str] = None


class GridAntropometri(BaseModel):
    has_data: bool
    data: Optional[AntropometriHeaderData] = None


class HeaderPasienResponse(BaseModel):
    status: str = "success"
    grid_kiri_identitas: GridIdentitas
    grid_tengah_alergi: GridAlergi
    grid_kanan_antropometri: GridAntropometri


# =============================================================================
# DOKTER ANTRIAN — kunjungan hari ini yang relevant ke dokter
# =============================================================================
class AntrianDokterItem(BaseModel):
    """1 baris antrian dokter view — kunjungan + ringkasan pasien."""
    model_config = ConfigDict(from_attributes=True)

    # Kunjungan
    id_kunjungan: int
    nomor_antrean: Optional[int] = None
    status_antrian: Optional[str] = None
    tgl_kunjungan: Optional[datetime] = None
    keluhan_utama: Optional[str] = None

    # Pasien
    id_pasien: int
    no_rm: str
    nama_pasien: str
    jenis_kelamin: Optional[str] = None

    # Indikator untuk dokter
    sudah_konsultasi: bool = False  # ada pemeriksaan_klinis di kunjungan ini


class CounterStatusAntrian(BaseModel):
    """Counter per status untuk dashboard dokter — quick view kapan bisa pulang."""
    menunggu_konsultasi: int = 0       # ANTRI_KONSULTASI
    sedang_konsultasi: int = 0         # KONSULTASI
    antri_treatment: int = 0           # ANTRI_TREATMENT
    sedang_treatment: int = 0          # ON_TREATMENT
    antri_bayar: int = 0               # ANTRI_BAYAR
    antri_obat: int = 0                # ANTRI_OBAT


class AntrianDokterResponse(BaseModel):
    """
    Response untuk GET /dokter/antrian.

    Filter logic (per UX dokter):
    - ANTRI_KONSULTASI + KONSULTASI: tampil SEMUA (akan/sedang konsultasi)
    - ANTRI_TREATMENT s.d. ANTRI_OBAT: tampil HANYA yang sudah ada
      pemeriksaan_klinis (= sudah lewat dokter). Pasien yang skip konsultasi
      (mis. langsung beli obat tanpa dokter) TIDAK muncul.
    - COMPLETED & BATAL: tidak tampil di antrian.

    Counter di summary bantu dokter tahu kapan bisa pulang — kalau semua bucket
    `menunggu_konsultasi`, `sedang_konsultasi`, `antri_treatment`, `sedang_treatment`,
    `antri_bayar`, `antri_obat` = 0, artinya tidak ada pasien-nya yang pending.
    """
    status: str = "success"
    tanggal: date
    total: int
    counter: CounterStatusAntrian
    data: list[AntrianDokterItem]


__all__ = [
    "TindakanBaruItem",
    "ResepProdukItem",
    "InputMedisRequest",
    "InputMedisResponse",
    "SoapRingkasItem",
    "ProdukDibeliRingkas",
    "TreatmentSelesaiRingkas",
    "SummaryDokterResponse",
    "DetailHoverIdentitas",
    "GridIdentitas",
    "AlergiRingkasItem",
    "GridAlergi",
    "AntropometriHeaderData",
    "GridAntropometri",
    "HeaderPasienResponse",
    "AntrianDokterItem",
    "CounterStatusAntrian",
    "AntrianDokterResponse",
]
