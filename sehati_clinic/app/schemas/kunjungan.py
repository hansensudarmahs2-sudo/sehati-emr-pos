"""
Pydantic schemas untuk kunjungan + antrian + status flow.

Catatan filosofi:
- Pakai `AntropometriCreate` dari schemas.pasien (jangan duplicate).
- Status antrian divalidasi pakai `StatusAntrianEnum` di service layer.
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import GenderEnum, MembershipTierEnum, StatusAntrianEnum
from app.schemas.pasien import AntropometriCreate


# =============================================================================
# Request — kunjungan lama (pasien existing daftar kunjungan baru)
# =============================================================================
class KunjunganLamaRequest(BaseModel):
    """
    Pasien lama (sudah ada di DB) daftar untuk kunjungan baru.

    Beda dengan `PasienBaruRequest`:
    - Tidak buat pasien baru — hanya butuh `id_pasien` referensi.
    - Tidak buat alergi/penyakit kronis (kalau perlu update, pakai endpoint terpisah).
    """
    id_pasien: int = Field(..., ge=1, description="ID pasien yang sudah terdaftar.")
    keluhan_utama: str = ""
    status_antrian: str = Field(
        default="ANTRI_KONSULTASI",
        description="Status awal kunjungan. Default antri konsultasi.",
    )
    sumber_pendaftaran: str = Field(
        default="WALK_IN",
        description="WALK_IN, BOOKING_ONLINE, dll.",
    )
    antropometri: Optional[AntropometriCreate] = None
    # FO-ASSIGN-DOKTER (Task #329): dokter yang di-assign FO. NULL = bebas claim.
    id_staf_dokter_assigned: Optional[int] = Field(
        default=None,
        ge=1,
        description="ID dokter yang di-assign untuk konsultasi. NULL = semua dokter bisa claim.",
    )


# =============================================================================
# Request — ubah status kunjungan
# =============================================================================
class UbahStatusRequest(BaseModel):
    """Request untuk pindah status antrian (mis. KONSULTASI → ANTRI_TREATMENT)."""
    status_baru: StatusAntrianEnum
    catatan: str = ""  # opsional, mis. alasan BATAL


# =============================================================================
# Response — kunjungan baru (setelah daftar)
# =============================================================================
class KunjunganBaruResponse(BaseModel):
    """Response setelah register kunjungan baru (untuk pasien lama)."""
    status: str = "success"
    message: str
    data: dict  # { id_kunjungan, nomor_antrean, id_pasien }


# =============================================================================
# Response — item antrian (kunjungan + ringkasan pasien)
# =============================================================================
class KunjunganAntrianItem(BaseModel):
    """1 baris antrian — kunjungan + ringkasan pasien (sudah di-join di repo)."""
    model_config = ConfigDict(from_attributes=True)

    # Kunjungan fields
    id_kunjungan: int
    nomor_antrean: Optional[int] = None
    status_antrian: Optional[str] = None
    keluhan_utama: Optional[str] = None
    tgl_kunjungan: Optional[datetime] = None
    sumber_pendaftaran: Optional[str] = None
    waktu_masuk_status: Optional[datetime] = None

    # Pasien fields (snapshot di antrian biar UI tidak perlu fetch lagi)
    id_pasien: int
    no_rm: str
    nama_pasien: str
    jenis_kelamin: Optional[GenderEnum] = None
    tgl_lahir: Optional[date] = None
    tipe_membership: Optional[str] = None

    # FO-ASSIGN-DOKTER (Task #329 FIX-1): dokter yang di-assign FO
    id_staf_dokter_assigned: Optional[int] = None
    dokter_dituju_nama: Optional[str] = None


class AntrianHariIniResponse(BaseModel):
    """Response untuk endpoint list antrian hari ini."""
    status: str = "success"
    tanggal: date
    total: int
    data: list[KunjunganAntrianItem]


# =============================================================================
# Response — detail 1 kunjungan
# =============================================================================
class KunjunganDetailResponse(BaseModel):
    """Detail 1 kunjungan + info pasien-nya (untuk halaman detail kunjungan)."""
    model_config = ConfigDict(from_attributes=True)

    id_kunjungan: int
    id_pasien: int
    no_rm: str
    nama_pasien: str

    nomor_antrean: Optional[int] = None
    status_antrian: Optional[str] = None
    keluhan_utama: Optional[str] = None
    tgl_kunjungan: Optional[datetime] = None
    tgl_kontrol_selanjutnya: Optional[date] = None
    sumber_pendaftaran: Optional[str] = None
    created_at: Optional[datetime] = None


__all__ = [
    "KunjunganLamaRequest",
    "UbahStatusRequest",
    "KunjunganBaruResponse",
    "KunjunganAntrianItem",
    "AntrianHariIniResponse",
    "KunjunganDetailResponse",
]
