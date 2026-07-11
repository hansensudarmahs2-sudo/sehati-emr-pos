"""Pydantic schemas untuk SDM management (CRUD staf)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import StafRoleEnum


# =============================================================================
# Response
# =============================================================================
class StafResponse(BaseModel):
    """Data staf yang aman dikirim ke client (no password/PIN)."""
    model_config = ConfigDict(from_attributes=True)

    id_staf: int
    username: str
    nama_staf: str
    role: StafRoleEnum
    is_active: Optional[bool] = None
    is_logged_in: Optional[bool] = None
    waktu_mulai_shift: Optional[datetime] = None
    has_pin: bool = False
    created_at: Optional[datetime] = None

    @classmethod
    def from_orm_with_pin_check(cls, staf):
        """Factory: build response + compute has_pin dari kolom pin."""
        data = cls.model_validate(staf).model_dump()
        data["has_pin"] = staf.pin is not None and staf.pin != ""
        return cls(**data)


class StafListResponse(BaseModel):
    status: str = "success"
    total: int
    data: list[StafResponse]


# =============================================================================
# Request — Create
# =============================================================================
class StafCreateRequest(BaseModel):
    """Register staf baru. Password & PIN di-hash di service layer."""
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    # A11 (audit P3): user BARU min 8 char. Reset/ganti user lama sengaja tetap 6
    # (mudahkan test saat ini) — hanya penambahan user baru yang diperketat.
    password: str = Field(..., min_length=8, max_length=100,
                          description="Password plaintext (min 8 utk user baru), di-hash bcrypt")
    nama_staf: str = Field(..., min_length=1, max_length=100)
    role: StafRoleEnum
    pin: Optional[str] = Field(
        default=None, min_length=6, max_length=20,
        description="PIN otorisasi (opsional; min 6 utk user baru)",
    )


# =============================================================================
# Request — Update profile (non-sensitive)
# =============================================================================
class StafUpdateRequest(BaseModel):
    """Update profile staf. Tidak include password/PIN/is_active."""
    nama_staf: Optional[str] = Field(default=None, min_length=1, max_length=100)
    role: Optional[StafRoleEnum] = None
    username: Optional[str] = Field(
        default=None, min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$"
    )


# =============================================================================
# Request — Password & PIN reset (sensitive)
# =============================================================================
class ResetPasswordRequest(BaseModel):
    """Reset password user lain (oleh Owner/Superadmin)."""
    new_password: str = Field(..., min_length=6, max_length=100)


class ResetPinRequest(BaseModel):
    """Reset/set PIN user lain (oleh Owner/Superadmin)."""
    new_pin: Optional[str] = Field(
        default=None, min_length=4, max_length=20,
        description="Kirim NULL/empty untuk hapus PIN",
    )


class ChangeOwnPasswordRequest(BaseModel):
    """User ganti password sendiri — wajib pakai password lama."""
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=100)


# =============================================================================
# Request — Activate/Deactivate
# =============================================================================
class SetActiveRequest(BaseModel):
    is_active: bool


# =============================================================================
# Standard responses
# =============================================================================
class GenericSuccessResponse(BaseModel):
    status: str = "success"
    message: str


__all__ = [
    "StafResponse",
    "StafListResponse",
    "StafCreateRequest",
    "StafUpdateRequest",
    "ResetPasswordRequest",
    "ResetPinRequest",
    "ChangeOwnPasswordRequest",
    "SetActiveRequest",
    "GenericSuccessResponse",
]
