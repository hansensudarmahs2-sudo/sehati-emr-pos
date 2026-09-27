"""
Pydantic schemas untuk pasien & related (alergi, penyakit kronis, antropometri).

Pattern: request schemas tanpa suffix, response schemas dengan suffix 'Response'.
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.db.models import (
    GenderEnum,
    MembershipTierEnum,
    TingkatKeparahanAlergiEnum,
    VerifikasiEnum,
)


# =============================================================================
# Sub-schemas untuk register pasien baru
# =============================================================================
class AlergiCreate(BaseModel):
    """Input alergi saat register pasien baru."""
    alergen: str = Field(..., min_length=1, max_length=100)
    gejala: str = ""
    tingkat_keparahan: TingkatKeparahanAlergiEnum


class PenyakitKronisCreate(BaseModel):
    """Input penyakit kronis saat register pasien baru."""
    nama_penyakit: str = Field(..., min_length=1, max_length=100)
    catatan: str = ""


class AntropometriCreate(BaseModel):
    """Input antropometri (opsional saat registrasi)."""
    berat_badan: Optional[float] = Field(default=None, ge=0, le=500)
    tinggi_badan: Optional[float] = Field(default=None, ge=0, le=300)
    tekanan_darah: str = ""
    suhu_tubuh: Optional[float] = Field(default=None, ge=30, le=45)
    skinfold_titik_1: Optional[float] = Field(default=None, ge=0, le=100)
    skinfold_titik_2: Optional[float] = Field(default=None, ge=0, le=100)
    skinfold_titik_3: Optional[float] = Field(default=None, ge=0, le=100)
    lingkar_perut: Optional[float] = Field(default=None, ge=0, le=300)


# =============================================================================
# Register pasien baru (the big request)
# =============================================================================
class PasienBaruRequest(BaseModel):
    """
    Request untuk register pasien baru (sekalian buat kunjungan + antropometri).

    Pattern dari kode dokter `main_api.py` line 126-150 — dipertahankan logika
    1 transaksi atomik untuk pasien + alergi + penyakit + kunjungan + antropometri.
    """
    # --- 1. Data demografi ---
    nama: str = Field(..., min_length=1, max_length=100)
    jenis_kelamin: GenderEnum
    alamat: str = ""
    tgl_lahir: Optional[date] = None
    nomor_telepon: str = ""
    nomor_ktp: str = ""
    sumber_referensi: str = ""
    email_address: str = ""  # bukan EmailStr karena bisa kosong
    tipe_membership: MembershipTierEnum = MembershipTierEnum.REGULAR

    # --- 2. Data kunjungan ---
    status_antrian: str = "ANTRI_KONSULTASI"
    keluhan_utama: str = ""
    # FO-ASSIGN-DOKTER (Task #329): dokter dituju kalau langsung daftar antrian.
    id_staf_dokter_assigned: Optional[int] = Field(
        default=None,
        ge=1,
        description="ID dokter dituju (opsional). NULL = bebas claim.",
    )

    # --- 3. Data medis tambahan (list) ---
    alergi: list[AlergiCreate] = Field(default_factory=list)
    penyakit_kronis: list[PenyakitKronisCreate] = Field(default_factory=list)

    # --- 4. Data opsional ---
    antropometri: Optional[AntropometriCreate] = None


# =============================================================================
# Response schemas
# =============================================================================
class AlergiResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_alergi: int
    alergen: str
    gejala: Optional[str] = None
    tingkat_keparahan: TingkatKeparahanAlergiEnum
    is_active: Optional[bool] = None
    created_at: Optional[datetime] = None


class PenyakitKronisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_penyakit: int
    nama_penyakit: str
    kode_penyakit: Optional[int] = None
    catatan: Optional[str] = None
    is_active: Optional[bool] = None


class PasienResponse(BaseModel):
    """Data pasien yang dikembalikan ke client."""
    model_config = ConfigDict(from_attributes=True)

    id_pasien: int
    no_rm: str
    nama: str
    jenis_kelamin: Optional[GenderEnum] = None
    alamat: Optional[str] = None
    tgl_lahir: Optional[date] = None
    nomor_telepon: Optional[str] = None
    nomor_ktp: Optional[str] = None
    email_address: Optional[str] = None
    sumber_referensi: Optional[str] = None
    tipe_membership: Optional[str] = None
    status_verifikasi: Optional[VerifikasiEnum] = None
    tgl_verifikasi: Optional[datetime] = None
    created_at: Optional[datetime] = None


class PasienDetailResponse(PasienResponse):
    """PasienResponse + alergi & penyakit kronis (untuk header dokter)."""
    alergi: list[AlergiResponse] = Field(default_factory=list)
    penyakit_kronis: list[PenyakitKronisResponse] = Field(default_factory=list)


class PasienBaruResponse(BaseModel):
    """Response setelah register pasien baru — match output kode dokter."""
    status: str = "success"
    message: str
    data: dict  # { no_rm, id_pasien, id_kunjungan, nomor_antrean }


class PasienSearchResponse(BaseModel):
    """Response untuk search pasien."""
    status: str = "success"
    total_ditemukan: int
    data: list[PasienResponse]


# =============================================================================
# Standalone alergi add (di luar register)
# =============================================================================
class AlergiAddRequest(BaseModel):
    """Request untuk tambah alergi ke pasien yang sudah ada."""
    id_pasien: int
    alergen: str = Field(..., min_length=1, max_length=100)
    gejala: str = ""
    tingkat_keparahan: TingkatKeparahanAlergiEnum = TingkatKeparahanAlergiEnum.RINGAN


class PasienUpdateRequest(BaseModel):
    """Request edit profile pasien existing - TODO-NEW-6 #50.

    Semua field opsional - partial update.
    no_rm read-only (tidak ada di sini).
    """
    nama: Optional[str] = Field(default=None, min_length=1, max_length=100)
    jenis_kelamin: Optional[GenderEnum] = None
    tgl_lahir: Optional[date] = None
    alamat: Optional[str] = Field(default=None, max_length=500)
    nomor_telepon: Optional[str] = Field(default=None, max_length=20)
    nomor_ktp: Optional[str] = Field(default=None, max_length=30)
    email_address: Optional[str] = Field(default=None, max_length=100)
    sumber_referensi: Optional[str] = Field(default=None, max_length=100)
    tipe_membership: Optional[str] = None


class AlergiUpdateRequest(BaseModel):
    """Request edit alergi existing - TODO-NEW-1 #29A dokter access.

    Semua field opsional; hanya yang di-set yang di-update.
    """
    alergen: Optional[str] = Field(default=None, min_length=1, max_length=100)
    gejala: Optional[str] = None
    tingkat_keparahan: Optional[TingkatKeparahanAlergiEnum] = None


class PenyakitKronisAddRequest(BaseModel):
    """Request tambah penyakit kronis ke pasien existing - TODO-NEW-1 #29B."""
    id_pasien: int
    nama_penyakit: str = Field(..., min_length=1, max_length=100)
    catatan: str = ""


class PenyakitKronisUpdateRequest(BaseModel):
    """Request edit penyakit kronis existing - TODO-NEW-1 #29B.

    Semua field opsional; hanya yang di-set yang di-update.
    """
    nama_penyakit: Optional[str] = Field(default=None, min_length=1, max_length=100)
    catatan: Optional[str] = None

# =============================================================================
# RIWAYAT PASIEN — untuk FO version (lihat sekilas saat daftar ulang)
# =============================================================================
class KunjunganRingkasItem(BaseModel):
    """Ringkasan 1 kunjungan untuk panel riwayat (bukan detail penuh)."""
    model_config = ConfigDict(from_attributes=True)

    id_kunjungan: int
    tgl_kunjungan: Optional[datetime] = None
    status_antrian: Optional[str] = None
    keluhan_utama: Optional[str] = None
    nomor_antrean: Optional[int] = None
    # Asal resep (2026-09-25). Tanpa ini, kunjungan penebusan resep tampak sama
    # persis dengan kunjungan konsultasi biasa di riwayat pasien — padahal
    # peresepnya bisa dokter luar, dan itu penting diketahui pembaca rekam medis.
    jenis_kunjungan: Optional[str] = None
    peresep_luar_nama: Optional[str] = None
    peresep_luar_asal: Optional[str] = None
    id_kunjungan_asal: Optional[int] = None


class RiwayatTreatmentItem(BaseModel):
    """1 baris series treatment (dari pasien_rencana_treatment)."""
    model_config = ConfigDict(from_attributes=True)

    id_rencana: int
    urutan_sesi: int
    nama_tindakan: str
    status: str                              # PENDING / SCHEDULED / DONE / CANCELLED
    tgl_target_mulai: Optional[date] = None
    tgl_target_akhir: Optional[date] = None
    tgl_eksekusi: Optional[datetime] = None
    catatan_dokter: Optional[str] = None
    created_at: Optional[datetime] = None


class RiwayatProdukResepItem(BaseModel):
    """1 baris produk yang DIRESEPKAN dokter (belum tentu sudah dibayar)."""
    model_config = ConfigDict(from_attributes=True)

    id_resep: int
    id_kunjungan: int
    tgl_resep: Optional[datetime] = None     # = tgl_kunjungan
    nama_produk: str                          # snapshot via JOIN ke master_produk
    qty: float
    aturan_pakai: Optional[str] = None
    status_item: Optional[str] = None         # PENDING / TERAMBIL / VOID


class RiwayatTindakanDiresepkanItem(BaseModel):
    """1 baris tindakan SINGLE yang diresepkan dokter via SOAP (kunjungan_tindakan)."""
    model_config = ConfigDict(from_attributes=True)

    id_kunjungan_tindakan: int
    id_kunjungan: int
    tgl_diresepkan: Optional[datetime] = None  # = tgl_kunjungan
    nama_treatment: str                         # snapshot via JOIN ke master_treatment
    harga: float
    status_tindakan: Optional[str] = None       # PENDING / IN_PROGRESS / COMPLETED / BATAL


class RiwayatProdukTerbayarItem(BaseModel):
    """1 baris produk yang SUDAH DIBAYAR (via transaksi kasir)."""
    model_config = ConfigDict(from_attributes=True)

    id_detail: int
    id_transaksi: int
    tgl_bayar: Optional[datetime] = None
    nama_produk: str
    qty: float
    harga_satuan: float
    subtotal: float


class RiwayatPasienResponse(BaseModel):
    """
    Compound response — semua riwayat 1 pasien dalam 1 payload.

    Cocok untuk FO panel saat daftar ulang ("kapan terakhir datang,
    treatment apa, beli produk apa") tanpa bolak-balik ke endpoint lain.
    """
    status: str = "success"

    # Info pasien dasar (snapshot saat ini)
    info_pasien: PasienResponse

    # Riwayat kunjungan (sorted DESC by tgl)
    total_kunjungan: int
    kunjungan: list[KunjunganRingkasItem] = Field(default_factory=list)

    # Riwayat treatment (series plan, sorted by urutan_sesi)
    riwayat_treatment: list[RiwayatTreatmentItem] = Field(default_factory=list)

    # Tindakan SINGLE yang diresepkan dokter (dari kunjungan_tindakan)
    # Tindakan SINGLE yang diresepkan dokter (dari kunjungan_tindakan)
    riwayat_tindakan_diresepkan: list[RiwayatTindakanDiresepkanItem] = Field(default_factory=list)

    # Produk - 2 list paralel (resep vs terbayar)
    produk_diresepkan: list[RiwayatProdukResepItem] = Field(default_factory=list)
    produk_terbayar: list[RiwayatProdukTerbayarItem] = Field(default_factory=list)


__all__ = [
    "PasienBaruRequest",
    "AlergiCreate",
    "PenyakitKronisCreate",
    "AntropometriCreate",
    "PasienBaruResponse",
    "PasienResponse",
    "PasienDetailResponse",
    "PasienSearchResponse",
    "AlergiResponse",
    "PenyakitKronisResponse",
    "AntropometriCreate",
    "AntropometriResponse",
]
