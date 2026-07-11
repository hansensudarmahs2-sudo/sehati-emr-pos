"""
SDM management endpoints — CRUD staf untuk Owner/Superadmin/Admin.

RBAC:
- List & detail              : Owner, Superadmin, Admin
- Register baru              : Owner, Superadmin
- Update profile             : Owner, Superadmin, Admin
- Reset password/PIN orang lain : Owner, Superadmin
- Set active/inactive        : Owner, Superadmin
"""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.deps import CurrentUser, DbSession, role_required
from app.db.models import StafRoleEnum
from app.schemas.staf import (
    GenericSuccessResponse,
    ResetPasswordRequest,
    ResetPinRequest,
    SetActiveRequest,
    StafCreateRequest,
    StafListResponse,
    StafResponse,
    StafUpdateRequest,
)
from app.services.staf_service import StafService


router = APIRouter(prefix="/staf", tags=["SDM Management"])


# Role guards (reusable)
_READ_ROLES = role_required(
    StafRoleEnum.OWNER, StafRoleEnum.SUPERADMIN, StafRoleEnum.ADMIN
)
_WRITE_ROLES = role_required(
    StafRoleEnum.OWNER, StafRoleEnum.SUPERADMIN, StafRoleEnum.ADMIN
)
_SENSITIVE_ROLES = role_required(
    StafRoleEnum.OWNER, StafRoleEnum.SUPERADMIN
)


# =============================================================================
# READ
# =============================================================================
@router.get(
    "",
    response_model=StafListResponse,
    summary="List semua staf",
)
def list_staf(
    db: DbSession,
    _: Annotated[object, Depends(_READ_ROLES)],
    only_active: bool = Query(default=False, description="Filter hanya yang aktif"),
    role: Optional[StafRoleEnum] = Query(default=None, description="Filter by role"),
):
    """List semua staf dengan optional filter."""
    service = StafService(db)
    staf_list = service.list_all(only_active=only_active, role=role)
    return StafListResponse(total=len(staf_list), data=staf_list)


@router.get(
    "/{id_staf}",
    response_model=StafResponse,
    summary="Detail staf by ID",
)
def get_staf(
    id_staf: int,
    db: DbSession,
    _: Annotated[object, Depends(_READ_ROLES)],
):
    service = StafService(db)
    return service.get_by_id(id_staf)


# =============================================================================
# CREATE
# =============================================================================
@router.post(
    "",
    response_model=StafResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register staf baru — hanya Owner/Superadmin",
)
def register_staf(
    payload: StafCreateRequest,
    db: DbSession,
    request: Request,
    current_user: Annotated[object, Depends(_SENSITIVE_ROLES)],
):
    """Register staf baru. Password & PIN otomatis di-hash bcrypt."""
    service = StafService(db)
    return service.register_staf_baru(
        payload,
        actor_id_staf=current_user.id_staf,
        request=request,
    )


# =============================================================================
# UPDATE — profile
# =============================================================================
@router.put(
    "/{id_staf}",
    response_model=StafResponse,
    summary="Update profile staf (nama, role, username)",
)
def update_profile_staf(
    id_staf: int,
    payload: StafUpdateRequest,
    db: DbSession,
    request: Request,
    current_user: Annotated[object, Depends(_WRITE_ROLES)],
):
    service = StafService(db)
    return service.update_profile(
        id_staf,
        payload,
        actor_id_staf=current_user.id_staf,
        request=request,
    )


# =============================================================================
# UPDATE — sensitive (password, PIN, active)
# =============================================================================
@router.patch(
    "/{id_staf}/reset-password",
    response_model=GenericSuccessResponse,
    summary="Reset password staf — Owner/Superadmin only",
)
def reset_password_staf(
    id_staf: int,
    payload: ResetPasswordRequest,
    db: DbSession,
    request: Request,
    current_user: Annotated[object, Depends(_SENSITIVE_ROLES)],
):
    """Reset password user lain. Otomatis paksa user logout."""
    service = StafService(db)
    return service.reset_password(
        id_staf,
        payload.new_password,
        actor_id_staf=current_user.id_staf,
        request=request,
    )


@router.patch(
    "/{id_staf}/reset-pin",
    response_model=GenericSuccessResponse,
    summary="Set/hapus PIN staf — Owner/Superadmin only",
)
def reset_pin_staf(
    id_staf: int,
    payload: ResetPinRequest,
    db: DbSession,
    request: Request,
    current_user: Annotated[object, Depends(_SENSITIVE_ROLES)],
):
    """Set PIN baru, atau hapus (kirim new_pin: null)."""
    service = StafService(db)
    return service.reset_pin(
        id_staf,
        payload.new_pin,
        actor_id_staf=current_user.id_staf,
        request=request,
    )
