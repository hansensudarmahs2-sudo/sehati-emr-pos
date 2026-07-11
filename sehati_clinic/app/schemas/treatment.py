"""
Pydantic schemas untuk TreatmentService (Ruang Tindakan / Perawat workflow).

Endpoints related:
- GET /ruang-tindakan/antrian
- GET /ruang-tindakan/kunjungan/{id}/detail
- POST /ruang-tindakan/start
- POST /ruang-tindakan/end
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Antrian Ruang Tindakan
# =============================================================================
class AntrianRuangTindakanItem(BaseModel):
    """1 baris antrian perawat — pasien dengan status ANTRI_TREATMENT atau ON_TREATMENT."""
    model_config = ConfigDict(from_attributes=True)

    id_kunjungan: int
    nomor_antrean: Optional[int] = None
    status_antrian: Optional[str] = None
    tgl_kunjungan: Optional[datetime] = None
    keluhan_utama: Optional[str] = None

    # Pasien
    id_pasien: int
    no_rm: str
    nama_pasien: str
    tgl_lahir: Optional[date] = None

    # Counter tindakan
    total_tindakan: int = 0
    tindakan_pending: int = 0
    tindakan_proses: int = 0


class AntrianRuangTindakanResponse(BaseModel):
    status: str = "success"
    tanggal: date
    total: int
    data: list[AntrianRuangTindakanItem]


# =============================================================================
# Detail Tindakan (iPad ruang tindakan)
# =============================================================================
class CatatanDokterDetail(BaseModel):
    """Instruksi dokter dari SOAP — untuk perawat baca sebelum tindakan."""
    model_config = ConfigDict(from_attributes=True)
    anamnesa: Optional[str] = None
    pemeriksaan_fisik: Optional[str] = None
    diagnosa: Optional[str] = None
    saran_treatment: Optional[str] = None
    saran_produk: Optional[str] = None


class TindakanDetailItem(BaseModel):
    """1 baris daftar tindakan di kunjungan ini."""
    model_config = ConfigDict(from_attributes=True)
    id_kunjungan_tindakan: int
    id_treatment: int
    nama_treatment: str
    role_pelaksana: Optional[str] = None  # TODO-NEW-5 #33: untuk badge + guardrail
    status_tindakan: Optional[str] = None
    waktu_mulai: Optional[datetime] = None
    waktu_selesai: Optional[datetime] = None
    id_staf_pelaksana: Optional[int] = None
    nama_staf_pelaksana: Optional[str] = None


class DetailRuangTindakanResponse(BaseModel):
    status: str = "success"
    id_kunjungan: int
    id_pasien: int
    no_rm: str
    nama_pasien: str
    status_kunjungan: Optional[str] = None
    instruksi_dokter: Optional[CatatanDokterDetail] = None
    daftar_tindakan: list[TindakanDetailItem] = Field(default_factory=list)


# =============================================================================
# Start / End Treatment
# =============================================================================
class StartTreatmentRequest(BaseModel):
    """Mulai 1 tindakan tertentu (PENDING → PROSES)."""
    id_kunjungan_tindakan: int = Field(..., ge=1)


class EndTreatmentRequest(BaseModel):
    """Selesai 1 tindakan (PROSES → SELESAI), auto potong BHP."""
    id_kunjungan_tindakan: int = Field(..., ge=1)


class StartTreatmentResponse(BaseModel):
    status: str = "success"
    message: str
    data: dict  # { id_kunjungan_tindakan, status_baru, waktu_mulai }


class EndTreatmentResponse(BaseModel):
    status: str = "success"
    message: str
    data: dict  # { id_kunjungan_tindakan, status_baru, waktu_selesai, jumlah_bahan_potong, status_kunjungan }


__all__ = [
    "AntrianRuangTindakanItem",
    "AntrianRuangTindakanResponse",
    "CatatanDokterDetail",
    "TindakanDetailItem",
    "DetailRuangTindakanResponse",
    "StartTreatmentRequest",
    "EndTreatmentRequest",
    "StartTreatmentResponse",
    "EndTreatmentResponse",
    "UpsellRequest",
    "UpsellResponse",
]


# =============================================================================
# UPSELL — perawat tambah treatment/produk on-the-fly di ruang tindakan
# =============================================================================
class UpsellRequest(BaseModel):
    """
    Request upsell dari ruang tindakan.

    Logic PIN authorization:
    - Kalau tipe_item=TREATMENT dan master_treatment.butuh_otorisasi=True,
      field `id_staf_otorisasi` + `pin_otorisasi` WAJIB dikirim.
    - PIN divalidasi dengan bcrypt verify (PIN di DB sudah di-hash).
    """
    id_kunjungan: int = Field(..., ge=1)
    tipe_item: str = Field(..., description="TREATMENT atau PRODUK", max_length=20)
    id_item: int = Field(..., ge=1, description="id_treatment atau id_produk")
    qty: float = Field(default=1.0, gt=0)

    # Hanya wajib kalau item butuh otorisasi
    id_staf_otorisasi: Optional[int] = Field(
        default=None,
        ge=1,
        description="ID dokter yang otorisasi (wajib kalau butuh_otorisasi=1).",
    )
    pin_otorisasi: Optional[str] = Field(
        default=None,
        min_length=4,
        max_length=20,
        description="PIN dokter (wajib kalau butuh_otorisasi=1). Raw PIN — divalidasi bcrypt.",
    )


class UpsellResponse(BaseModel):
    status: str = "success"
    message: str
    data: dict  # { tipe_item, id_record_baru, butuh_otorisasi, otorisasi_oleh, status_kunjungan }
