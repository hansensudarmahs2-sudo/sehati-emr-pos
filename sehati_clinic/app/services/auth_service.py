"""
AuthService — business logic untuk login/logout.

Pertahankan logika anchor shift dokter (waktu_mulai_shift tidak di-reset
kalau login ulang di hari yang sama).
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import create_access_token, verify_password
from app.db.models import MasterStaf
from app.repositories.staf_repo import StafRepository
from app.schemas.auth import TokenResponse, UserResponse
from app.services.audit_service import AuditService


class AuthService:
    """Service untuk login, logout, current user."""

    def __init__(self, db: Session):
        self.db = db
        self.staf_repo = StafRepository(db)
        self.audit = AuditService(db)

    def login(
        self,
        username: str,
        password: str,
        request: Optional[Request] = None,
    ) -> TokenResponse:
        """
        Authenticate staf, generate JWT, set session aktif.

        Raises:
            HTTPException 401: kalau username/password salah
            HTTPException 403: kalau akun non-aktif
        """
        # 1. Cari staf by username
        staf = self.staf_repo.get_by_username(username)
        if not staf:
            # AUDIT login failed (username tidak ada)
            self.audit.log_login(
                id_staf=0,
                username=username,
                success=False,
                request=request,
                keterangan="Username tidak ditemukan",
            )
            self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Username atau password salah.",
            )

        # 2. Verifikasi password (bcrypt)
        if not verify_password(password, staf.password_hash):
            # AUDIT login failed (password salah) — id_staf dicatat supaya bisa
            # tracking siapa yang akun-nya jadi target brute-force
            self.audit.log_login(
                id_staf=staf.id_staf,
                username=username,
                success=False,
                request=request,
                keterangan="Password salah",
            )
            self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Username atau password salah.",
            )

        # 3. Cek akun aktif
        if not staf.is_active:
            self.audit.log_login(
                id_staf=staf.id_staf,
                username=username,
                success=False,
                request=request,
                keterangan="Akun non-aktif",
            )
            self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Akun tidak aktif. Hubungi admin.",
            )

        # 4. Generate token & expiry
        expires_delta = timedelta(hours=settings.jwt_access_token_expire_hours)
        # NOTE: pakai naive datetime di DB karena kolom-nya DATETIME tanpa TZ
        now_naive = datetime.utcnow()
        token_expired_at = now_naive + expires_delta

        # 5. Update session (anchor shift logic preserved)
        self.staf_repo.mark_logged_in(
            staf=staf,
            token_expired_at=token_expired_at,
            shift_anchor=now_naive,
        )

        # AUDIT login success
        self.audit.log_login(
            id_staf=staf.id_staf,
            username=username,
            success=True,
            request=request,
        )

        self.db.commit()
        self.db.refresh(staf)

        # 6. Generate JWT
        jwt_payload = {
            "sub": str(staf.id_staf),
            "role": staf.role.value,
            "username": staf.username,
        }
        access_token = create_access_token(jwt_payload, expires_delta=expires_delta)

        # 7. Build response
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in_seconds=int(expires_delta.total_seconds()),
            user=UserResponse.model_validate(staf),
        )

    def logout(
        self,
        staf: MasterStaf,
        request: Optional[Request] = None,
    ) -> None:
        """
        Logout: set is_logged_in=False, clear token_expired_at.
        waktu_mulai_shift TIDAK di-reset (untuk rekap shift kasir).
        """
        self.staf_repo.mark_logged_out(staf)
        # AUDIT logout
        self.audit.log_logout(id_staf=staf.id_staf, request=request)
        self.db.commit()

    def get_current_user_data(self, staf: MasterStaf) -> UserResponse:
        """Return data user yang aman dikirim ke client."""
        return UserResponse.model_validate(staf)


__all__ = ["AuthService"]
