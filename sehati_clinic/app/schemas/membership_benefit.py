"""
Pydantic schemas untuk Master Membership Benefit Treatment CRUD (#362B-B).

Definisi kuota treatment per tier membership.
- BULANAN: kuota per bulan (mis. 1x facial/bulan)
- TOTAL_PAKET: kuota sepanjang periode aktif (mis. 12x facial/tahun)
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import PeriodeKuotaEnum


class BenefitTreatmentCreate(BaseModel):
    id_membership: int
    id_treatment: int
    kuota_total: int = Field(..., ge=1, le=1000)
    periode_kuota: PeriodeKuotaEnum
    catatan: Optional[str] = Field(default=None, max_length=200)


class BenefitTreatmentUpdate(BaseModel):
    kuota_total: Optional[int] = Field(default=None, ge=1, le=1000)
    periode_kuota: Optional[PeriodeKuotaEnum] = None
    catatan: Optional[str] = Field(default=None, max_length=200)


class BenefitTreatmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_benefit: int
    id_membership: int
    id_treatment: int
    kuota_total: int
    periode_kuota: PeriodeKuotaEnum
    catatan: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None


__all__ = [
    "BenefitTreatmentCreate",
    "BenefitTreatmentUpdate",
    "BenefitTreatmentResponse",
]
