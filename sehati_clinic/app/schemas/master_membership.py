"""
Pydantic schemas untuk Master Membership CRUD (#362A).

Flow:
- GET    /web/master/membership                        list
- GET    /web/master/membership/tambah                 form add
- POST   /web/master/membership/tambah                 submit add
- GET    /web/master/membership/{id}                   form edit
- POST   /web/master/membership/{id}                   submit edit
- POST   /web/master/membership/{id}/toggle-active     soft delete toggle
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# CREATE
# =============================================================================
class MasterMembershipCreate(BaseModel):
    """Request register tier membership baru."""
    nama_tier: str = Field(..., min_length=1, max_length=50,
                            description="Harus match MembershipTierEnum (REGULAR/VIP/VVIP) "
                                        "ATAU tier baru. Validasi enum dilakukan di service.")
    harga_aktivasi: Decimal = Field(default=Decimal("0"), ge=0,
                                     description="Harga aktivasi membership (Rp).")
    durasi_bulan: int = Field(default=12, ge=1, le=120,
                              description="Berapa bulan membership berlaku setelah aktivasi.")
    free_konsultasi_dokter: bool = False
    diskon_treatment_persen: Decimal = Field(default=Decimal("0"), ge=0, le=100,
                                              description="Diskon treatment dalam % (0-100).")
    diskon_produk_persen: Decimal = Field(default=Decimal("0"), ge=0, le=100,
                                           description="Diskon produk dalam % (0-100).")
    urutan_tampilan: int = Field(default=0, ge=0,
                                  description="Urutan tampilan di dropdown (ASC).")
    catatan: Optional[str] = Field(default=None, max_length=500)


# =============================================================================
# UPDATE — partial
# =============================================================================
class MasterMembershipUpdate(BaseModel):
    """Request update tier — semua field opsional."""
    nama_tier: Optional[str] = Field(default=None, min_length=1, max_length=50)
    harga_aktivasi: Optional[Decimal] = Field(default=None, ge=0)
    durasi_bulan: Optional[int] = Field(default=None, ge=1, le=120)
    free_konsultasi_dokter: Optional[bool] = None
    diskon_treatment_persen: Optional[Decimal] = Field(default=None, ge=0, le=100)
    diskon_produk_persen: Optional[Decimal] = Field(default=None, ge=0, le=100)
    urutan_tampilan: Optional[int] = Field(default=None, ge=0)
    catatan: Optional[str] = Field(default=None, max_length=500)


# =============================================================================
# RESPONSE
# =============================================================================
class MasterMembershipResponse(BaseModel):
    """Response untuk 1 tier."""
    model_config = ConfigDict(from_attributes=True)

    id_membership: int
    nama_tier: str
    harga_aktivasi: Decimal
    durasi_bulan: int
    free_konsultasi_dokter: bool
    diskon_treatment_persen: Decimal
    diskon_produk_persen: Decimal
    is_active: bool
    urutan_tampilan: int
    catatan: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MasterMembershipListResponse(BaseModel):
    status: str = "success"
    total: int
    data: list[MasterMembershipResponse]


# =============================================================================
# SET ACTIVE
# =============================================================================
class SetActiveMembershipRequest(BaseModel):
    is_active: bool


# =============================================================================
# GENERIC WRAPPER
# =============================================================================
class MembershipGenericResponse(BaseModel):
    """Generic wrapper untuk endpoint set-active, dll."""
    status: str = "success"
    message: str
    data: Optional[MasterMembershipResponse] = None


__all__ = [
    "MasterMembershipCreate",
    "MasterMembershipUpdate",
    "MasterMembershipResponse",
    "MasterMembershipListResponse",
    "SetActiveMembershipRequest",
    "MembershipGenericResponse",
]
