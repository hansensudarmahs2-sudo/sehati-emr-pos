"""
Auth endpoints — login, logout, current user, change own password.

Routes:
    POST /api/v1/auth/login              — public
    POST /api/v1/auth/logout             — requires auth
    GET  /api/v1/auth/me                 — requires auth
    POST /api/v1/auth/change-password    — requires auth
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.deps import CurrentUser, DbSession
from app.schemas.auth import LogoutResponse, TokenResponse, UserResponse
from app.schemas.staf import ChangeOwnPasswordRequest, GenericSuccessResponse
from app.services.auth_service import AuthService
from app.services.staf_service import StafService


router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Login staf — dapat JWT token",
)
def login(
    db: DbSession,
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
):
    """Login pakai username + password. Return JWT token + user info."""
    service = AuthService(db)
    return service.login(
        username=form_data.username,
        password=form_data.password,
        request=request,
    )


@router.post(
    "/logout",
    response_model=LogoutResponse,
    status_code=status.HTTP_200_OK,
    summary="Logout — cabut session aktif",
)
def logout(
    current_user: CurrentUser,
    db: DbSession,
    request: Request,
):
    """Logout. waktu_mulai_shift TIDAK di-reset (untuk rekap shift kasir)."""
    service = AuthService(db)
    service.logout(staf=current_user, request=request)
    return LogoutResponse()


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Info staf yang sedang login",
)
def get_me(current_user: CurrentUser):
    return UserResponse.model_validate(current_user)


@router.post(
    "/change-password",
    response_model=GenericSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="User ganti password sendiri",
)
def change_own_password(
    payload: ChangeOwnPasswordRequest,
    current_user: CurrentUser,
    db: DbSession,
    request: Request,
):
    """
    User ganti password sendiri. Wajib pakai password lama untuk verifikasi.
    Setelah sukses, session di-paksa logout — user harus login ulang.
    """
    service = StafService(db)
    return service.change_own_password(
        current_user=current_user,
        old_password=payload.old_password,
        new_password=payload.new_password,
        request=request,
    )
