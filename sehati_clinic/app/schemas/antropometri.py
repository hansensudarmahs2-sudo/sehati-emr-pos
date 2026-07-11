"""
Pydantic schemas untuk AntropometriService.

Antropometri = pengukuran fisik pasien per kunjungan:
- berat_badan, tinggi_badan, tekanan_darah, suhu_tubuh
- skinfold 3 titik (untuk body fat Pollock)
- lingkar_perut

Field opsional — boleh isi sebagian. Tapi minimal salah satu wajib (validasi di service).
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# =============================================================================
# REQUEST — upsert (INSERT atau UPDATE) per kunjungan
# =============================================================================
class AntropometriUpsertRequest(BaseModel):
    """
    Tambah atau update antropometri untuk 1 kunjungan.

    Backend deteksi: kalau kunjungan ini sudah punya antropometri row,
    UPDATE; kalau belum, INSERT. Selalu 1 row per kunjungan (no duplicate).
    """
    id_kunjungan: int = Field(..., ge=1)
    berat_badan: Optional[float] = Field(default=None, ge=0, le=500)
    tinggi_badan: Optional[float] = Field(default=None, ge=0, le=300)
    tekanan_darah: str = Field(default="", max_length=20)
    suhu_tubuh: Optional[float] = Field(default=None, ge=30, le=45)
    skinfold_titik_1: Optional[float] = Field(default=None, ge=0, le=100)
    skinfold_titik_2: Optional[float] = Field(default=None, ge=0, le=100)
    skinfold_titik_3: Optional[float] = Field(default=None, ge=0, le=100)
    lingkar_perut: Optional[float] = Field(default=None, ge=0, le=300)

    @model_validator(mode="after")
    def cek_minimal_satu_field(self) -> "AntropometriUpsertRequest":
        """Minimal salah satu metric harus diisi (jangan submit kosong semua)."""
        has_data = any([
            self.berat_badan is not None,
            self.tinggi_badan is not None,
            self.tekanan_darah and self.tekanan_darah.strip(),
            self.suhu_tubuh is not None,
            self.skinfold_titik_1 is not None,
            self.skinfold_titik_2 is not None,
            self.skinfold_titik_3 is not None,
            self.lingkar_perut is not None,
        ])
        if not has_data:
            raise ValueError("Minimal salah satu field antropometri harus diisi.")
        return self


# =============================================================================
# RESPONSE — 1 record antropometri (raw, no computed)
# =============================================================================
class AntropometriResponse(BaseModel):
    """1 record antropometri — data mentah."""
    model_config = ConfigDict(from_attributes=True)

    id_antropometri: int
    id_kunjungan: int
    id_staf: Optional[int] = None
    berat_badan: Optional[float] = None
    tinggi_badan: Optional[float] = None
    tekanan_darah: Optional[str] = None
    suhu_tubuh: Optional[float] = None
    skinfold_titik_1: Optional[float] = None
    skinfold_titik_2: Optional[float] = None
    skinfold_titik_3: Optional[float] = None
    lingkar_perut: Optional[float] = None
    created_at: Optional[datetime] = None


class AntropometriUpsertResponse(BaseModel):
    status: str = "success"
    message: str
    data: dict  # { id_antropometri, id_kunjungan, action: "created"/"updated" }


# =============================================================================
# RESPONSE — Antropometri terakhir + nilai klinis terhitung
# =============================================================================
class AntropometriTerakhirResponse(BaseModel):
    """
    Antropometri terbaru pasien + nilai klinis terhitung otomatis.

    Untuk header dokter (grid kanan): bisa langsung tampilkan tanpa
    frontend perlu hitung BMI/body fat sendiri.
    """
    status: str = "success"
    has_data: bool

    # Raw data (kalau ada)
    berat_badan: Optional[float] = None
    tinggi_badan: Optional[float] = None
    tekanan_darah: Optional[str] = None
    suhu_tubuh: Optional[float] = None
    skinfold_titik_1: Optional[float] = None
    skinfold_titik_2: Optional[float] = None
    skinfold_titik_3: Optional[float] = None
    lingkar_perut: Optional[float] = None
    tgl_ukur: Optional[date] = None

    # Computed clinical values
    bmi: Optional[float] = None
    kategori_bmi: Optional[str] = None        # underweight/normal/overweight/obese
    sum_skinfold: Optional[float] = None
    body_fat_pct: Optional[float] = None
    lean_mass_pct: Optional[float] = None
    usia_saat_ukur: Optional[int] = None


# =============================================================================
# RESPONSE — Timeline antropometri pasien
# =============================================================================
class AntropometriTimelineItem(BaseModel):
    """1 baris timeline — data + BMI computed (untuk plot grafik)."""
    model_config = ConfigDict(from_attributes=True)

    id_antropometri: int
    id_kunjungan: int
    tgl_ukur: Optional[datetime] = None
    berat_badan: Optional[float] = None
    tinggi_badan: Optional[float] = None
    tekanan_darah: Optional[str] = None
    bmi: Optional[float] = None
    body_fat_pct: Optional[float] = None
    lingkar_perut: Optional[float] = None


class AntropometriTimelineResponse(BaseModel):
    status: str = "success"
    id_pasien: int
    total: int
    data: list[AntropometriTimelineItem]


__all__ = [
    "AntropometriUpsertRequest",
    "AntropometriResponse",
    "AntropometriUpsertResponse",
    "AntropometriTerakhirResponse",
    "AntropometriTimelineItem",
    "AntropometriTimelineResponse",
]
