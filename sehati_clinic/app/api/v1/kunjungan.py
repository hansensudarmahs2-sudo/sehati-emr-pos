"""
Kunjungan endpoints — daftar pasien lama, antrian, detail, ubah status.

Routes:
    POST   /api/v1/kunjungan/lama                       — pasien existing daftar kunjungan baru
    GET    /api/v1/kunjungan/antrian                    — list antrian hari ini
    GET    /api/v1/kunjungan/{id_kunjungan}             — detail 1 kunjungan
    PATCH  /api/v1/kunjungan/{id_kunjungan}/status      — ubah status

RBAC:
- Daftar kunjungan lama       : FO, Admin, Superadmin, Owner
- List antrian                : FO, Kasir, Perawat, Dokter, Apoteker, Admin, Superadmin, Owner
- Detail kunjungan            : sama dengan list antrian
- Ubah status (non-BATAL)     : Dokter, Perawat, Kasir, Apoteker, FO, Admin, Superadmin, Owner
- Ubah status → BATAL         : FO, Admin, Superadmin, Owner (level lebih tinggi)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.core.deps import CurrentUser, DbSession, role_required
from app.db.models import MasterStaf, StafRoleEnum
from app.schemas.kunjungan import (
    AntrianHariIniResponse,
    KunjunganBaruResponse,
    KunjunganDetailResponse,
    KunjunganLamaRequest,
    UbahStatusRequest,
)
from app.services.kunjungan_service import KunjunganService


router = APIRouter(prefix="/kunjungan", tags=["Kunjungan"])


# =============================================================================
# Role guards
# =============================================================================
_DAFTAR_ROLES = role_required(
    StafRoleEnum.FO,
    StafRoleEnum.ADMIN,
    StafRoleEnum.SUPERADMIN,
    StafRoleEnum.OWNER,
)
_READ_ANTRIAN_ROLES = role_required(
    StafRoleEnum.FO,
    StafRoleEnum.KASIR,
    StafRoleEnum.PERAWAT,
    StafRoleEnum.DOKTER,
    StafRoleEnum.APOTEKER,
    StafRoleEnum.ADMIN,
    StafRoleEnum.SUPERADMIN,
    StafRoleEnum.OWNER,
)
# Semua role klinis bisa ubah status (mis. dokter → ANTRI_TREATMENT, perawat → ON_TREATMENT)
_UBAH_STATUS_ROLES = role_required(
    StafRoleEnum.DOKTER,
    StafRoleEnum.PERAWAT,
    StafRoleEnum.KASIR,
    StafRoleEnum.APOTEKER,
    StafRoleEnum.FO,
    StafRoleEnum.ADMIN,
    StafRoleEnum.SUPERADMIN,
    StafRoleEnum.OWNER,
)
# BATAL terbatas — supaya tidak ada perawat/kasir iseng cancel
_ROLES_BOLEH_BATAL = {
    StafRoleEnum.FO.value,
    StafRoleEnum.ADMIN.value,
    StafRoleEnum.SUPERADMIN.value,
    StafRoleEnum.OWNER.value,
}
# Rekap antrian (lihat data COMPLETED & BATAL) khusus level admin ke atas —
# bukan data operasional harian, jadi terbatas.
_ROLES_BOLEH_REKAP = {
    StafRoleEnum.ADMIN.value,
    StafRoleEnum.SUPERADMIN.value,
    StafRoleEnum.OWNER.value,
}


# =============================================================================
# READ — list antrian hari ini
# =============================================================================
@router.get(
    "/antrian",
    response_model=AntrianHariIniResponse,
    status_code=status.HTTP_200_OK,
    summary="List antrian aktif hari ini (rekap penuh khusus Admin/Owner/Superadmin)",
)
def list_antrian(
    db: DbSession,
    current_user: Annotated[MasterStaf, Depends(_READ_ANTRIAN_ROLES)],
    include_completed: bool = Query(
        default=False,
        description=(
            "Default false — hanya tampilkan antrian yang masih aktif. "
            "Set true untuk rekap lengkap (termasuk COMPLETED & BATAL). "
            "Rekap lengkap hanya boleh Admin/Owner/Superadmin."
        ),
    ),
):
    """
    Dashboard antrian hari ini.

    - **Mode normal** (default): hanya tampilkan yang ACTIVE (exclude COMPLETED & BATAL).
      Untuk semua staf operasional (FO, Kasir, Perawat, Dokter, Apoteker).
    - **Mode rekap** (`include_completed=true`): lihat SEMUA kunjungan hari ini
      termasuk yang sudah selesai/batal. Khusus Admin/Owner/Superadmin —
      role lain dapat 403.
    """
    if include_completed:
        user_role = (
            current_user.role.value
            if hasattr(current_user.role, "value")
            else current_user.role
        )
        if user_role not in _ROLES_BOLEH_REKAP:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Rekap antrian (termasuk COMPLETED & BATAL) hanya boleh diakses "
                    "oleh Admin/Owner/Superadmin."
                ),
            )

    service = KunjunganService(db)
    return service.lihat_antrian_hari_ini(exclude_completed=not include_completed)


@router.get(
    "/{id_kunjungan}",
    response_model=KunjunganDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Detail 1 kunjungan",
)
def detail_kunjungan(
    db: DbSession,
    _: Annotated[object, Depends(_READ_ANTRIAN_ROLES)],
    id_kunjungan: int = Path(..., ge=1),
):
    service = KunjunganService(db)
    return service.get_detail(id_kunjungan)


# =============================================================================
# CREATE — daftar kunjungan untuk pasien lama
# =============================================================================
@router.post(
    "/lama",
    response_model=KunjunganBaruResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Daftar kunjungan baru untuk pasien yang sudah ada",
)
def daftar_kunjungan_lama(
    payload: KunjunganLamaRequest,
    db: DbSession,
    current_user: CurrentUser,
    request: Request,
    _: Annotated[object, Depends(_DAFTAR_ROLES)],
):
    """
    Pasien existing daftar kunjungan baru (mis. kunjungan kontrol).

    Berbeda dengan `POST /pasien/baru` yang sekaligus buat record pasien.
    """
    service = KunjunganService(db)
    return service.kunjungan_lama(
        payload=payload,
        id_staf_fo=current_user.id_staf,
        request=request,
    )


# =============================================================================
# UPDATE — ubah status antrian
# =============================================================================
@router.patch(
    "/{id_kunjungan}/status",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Ubah status kunjungan (alur normal atau BATAL)",
)
def ubah_status_kunjungan(
    payload: UbahStatusRequest,
    db: DbSession,
    request: Request,
    current_user: Annotated[MasterStaf, Depends(_UBAH_STATUS_ROLES)],
    id_kunjungan: int = Path(..., ge=1),
):
    """
    Ubah status antrian kunjungan, dengan validasi transisi.

    Transisi BATAL hanya boleh oleh role FO/Admin/Superadmin/Owner —
    perawat/kasir/apoteker yang coba BATAL akan dapat 403.
    """
    user_role = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else current_user.role
    )
    allow_batal = user_role in _ROLES_BOLEH_BATAL

    service = KunjunganService(db)
    return service.ubah_status(
        id_kunjungan=id_kunjungan,
        status_baru=payload.status_baru,
        allow_batal=allow_batal,
        actor_id_staf=current_user.id_staf,
        request=request,
    )
