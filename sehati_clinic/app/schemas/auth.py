"""Pydantic schemas untuk auth endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import StafRoleEnum


# ----- Request schemas -----
class LoginRequest(BaseModel):
    """Request body untuk POST /api/v1/auth/login."""
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)


# ----- Response schemas -----
class UserResponse(BaseModel):
    """Data user yang aman dikirim ke client (no password/PIN)."""
    model_config = ConfigDict(from_attributes=True)

    id_staf: int
    username: str
    nama_staf: str
    role: StafRoleEnum
    is_active: Optional[bool] = None
    is_logged_in: Optional[bool] = None
    waktu_mulai_shift: Optional[datetime] = None


class TokenResponse(BaseModel):
    """Response body untuk login sukses."""
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    user: UserResponse


class LogoutResponse(BaseModel):
    """Response body untuk logout sukses."""
    status: str = "success"
    message: str = "Logout berhasil. Token sudah dicabut."


__all__ = [
    "LoginRequest",
    "UserResponse",
    "TokenResponse",
    "LogoutResponse",
]
