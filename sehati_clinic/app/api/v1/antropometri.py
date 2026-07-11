"""
Antropometri endpoints — pengukuran fisik pasien.

Routes:
    POST  /api/v1/antropometri                              — upsert (INSERT atau UPDATE per kunjungan)
    GET   /api/v1/antropometri/kunjungan/{id_kunjungan}     — get 1 record by kunjungan
    GET   /api/v1/antropometri/pasien/{id_pasien}/terakhir  — last + BMI/fat%/lean% computed
    GET   /api/v1/antropometri/pasien/{id_pasien}/timeline  — semua riwayat + BMI per row

RBAC:
- Upsert        : FO, Perawat, Dokter, Admin, Owner, Superadmin (operasional klinis)
- Read          : Semua staf operasional + admin/owner
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, status

from app.core.deps import CurrentUser, DbSession, role_required
from app.db.models import StafRoleEnum
from app.schemas.antropometri import (
    AntropometriResponse,
    AntropometriTerakhirResponse,
    AntropometriTimelineResponse,
    AntropometriUpsertRequest,
    AntropometriUpsertResponse,
)
from app.services.antropometri_service import AntropometriService


router = APIRouter(prefix="/antropometri", tags=["Antropometri"])


# =============================================================================
# Role guards
# =============================================================================
_WRITE_ROLES = role_required(
    StafRoleEnum.FO,
    StafRoleEnum.PERAWAT,
    StafRoleEnum.DOKTER,
    StafRoleEnum.ADMIN,
    StafRoleEnum.SUPERADMIN,
    StafRoleEnum.OWNER,
)
_READ_ROLES = role_required(
    StafRoleEnum.FO,
    StafRoleEnum.KASIR,
    StafRoleEnum.PERAWAT,
    StafRoleEnum.DOKTER,
    StafRoleEnum.APOTEKER,
    StafRoleEnum.ADMIN,
    StafRoleEnum.SUPERADMIN,
    StafRoleEnum.OWNER,
)


# =============================================================================
# UPSERT — INSERT atau UPDATE per kunjungan
# =============================================================================
@router.post(
    "",
    response_model=AntropometriUpsertResponse,
    status_code=status.HTTP_200_OK,
    summary="Tambah / update antropometri kunjungan (1 row per kunjungan)",
)
def upsert_antropometri(
    payload: AntropometriUpsertRequest,
    db: DbSession,
    current_user: CurrentUser,
    request: Request,
    _: Annotated[object, Depends(_WRITE_ROLES)],
):
    """
    Upsert antropometri untuk 1 kunjungan.

    - Kalau kunjungan ini sudah punya antropometri row → UPDATE (perbaikan data)
    - Kalau belum → INSERT baru

    Minimal salah satu field (berat_badan / tinggi_badan / tekanan_darah /
    suhu_tubuh / skinfold / lingkar_perut) harus diisi.
    """
    service = AntropometriService(db)
    return service.upsert(
        payload=payload,
        id_staf=current_user.id_staf,
        request=request,
    )


# =============================================================================
# GET — by kunjungan
# =============================================================================
@router.get(
    "/kunjungan/{id_kunjungan}",
    response_model=AntropometriResponse,
    status_code=status.HTTP_200_OK,
    summary="Get antropometri untuk 1 kunjungan",
)
def get_antropometri_kunjungan(
    db: DbSession,
    _: Annotated[object, Depends(_READ_ROLES)],
    id_kunjungan: int = Path(..., ge=1),
):
    """Data mentah tanpa kalkulasi klinis. 404 kalau belum ada."""
    service = AntropometriService(db)
    return service.get_for_kunjungan(id_kunjungan)


# =============================================================================
# GET — antropometri terakhir + computed clinical (untuk header dokter)
# =============================================================================
@router.get(
    "/pasien/{id_pasien}/terakhir",
    response_model=AntropometriTerakhirResponse,
    status_code=status.HTTP_200_OK,
    summary="Antropometri terbaru pasien + BMI/fat%/lean% computed",
)
def get_antropometri_terakhir(
    db: DbSession,
    _: Annotated[object, Depends(_READ_ROLES)],
    id_pasien: int = Path(..., ge=1),
):
    """
    Data terbaru + nilai klinis terhitung:
    - BMI + kategori (underweight/normal/overweight/obese)
    - Body fat % (Jackson-Pollock 3-site + Siri)
    - Lean mass % (100 - body fat)

    Kalau pasien belum ada antropometri pernah dicatat, `has_data=false`.
    """
    service = AntropometriService(db)
    return service.get_terakhir_with_clinical(id_pasien)


# =============================================================================
# GET — timeline (untuk grafik tracking)
# =============================================================================
@router.get(
    "/pasien/{id_pasien}/timeline",
    response_model=AntropometriTimelineResponse,
    status_code=status.HTTP_200_OK,
    summary="Timeline antropometri pasien (untuk grafik BB/BMI over time)",
)
def get_antropometri_timeline(
    db: DbSession,
    _: Annotated[object, Depends(_READ_ROLES)],
    id_pasien: int = Path(..., ge=1),
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    Semua riwayat antropometri pasien, sorted DESC by tgl_ukur.
    BMI dan body fat % di-compute per row.
    """
    service = AntropometriService(db)
    return service.get_timeline(id_pasien=id_pasien, limit=limit)
