"""
Master Produk endpoints — CRUD + restock + set-active.

Routes:
    GET    /api/v1/produk                          — list dengan filter (keyword, tipe, only_active)
    GET    /api/v1/produk/{id_produk}              — detail
    POST   /api/v1/produk                          — create produk baru
    PUT    /api/v1/produk/{id_produk}              — update profile (partial)
    PATCH  /api/v1/produk/{id_produk}/set-active   — toggle is_active (soft delete)
    PATCH  /api/v1/produk/{id_produk}/restock      — tambah stok dari supplier

RBAC:
- Read              : Semua role klinis & administratif
- Create / Update   : Owner, Superadmin, Admin
- Set active        : Owner, Superadmin, Admin
- Restock           : Apoteker juga (yang biasanya terima barang dari supplier)
"""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Path, Query, Request, status

from app.core.deps import CurrentUser, DbSession, role_required
from app.db.models import StafRoleEnum
from app.schemas.master_produk import (
    MasterProdukCreate,
    MasterProdukListResponse,
    MasterProdukResponse,
    MasterProdukUpdate,
    ProdukGenericResponse,
    RestockProdukRequest,
    RestockProdukResponse,
    SetActiveProdukRequest,
)
from app.services.master_produk_service import MasterProdukService


router = APIRouter(prefix="/produk", tags=["Master Produk"])


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
_WRITE_ROLES = role_required(
    StafRoleEnum.ADMIN,
    StafRoleEnum.SUPERADMIN,
    StafRoleEnum.OWNER,
)
_RESTOCK_ROLES = role_required(
    StafRoleEnum.APOTEKER,
    StafRoleEnum.ADMIN,
    StafRoleEnum.SUPERADMIN,
    StafRoleEnum.OWNER,
)


# =============================================================================
# READ
# =============================================================================
@router.get(
    "",
    response_model=MasterProdukListResponse,
    status_code=status.HTTP_200_OK,
    summary="List produk dengan filter",
)
def list_produk(
    db: DbSession,
    _: Annotated[object, Depends(_READ_ROLES)],
    keyword: Optional[str] = Query(default=None, description="Cari di kode_produk / nama_produk"),
    tipe: Optional[str] = Query(default=None, description="RETAIL / CABIN / ALAT"),
    only_active: bool = Query(default=False, description="Filter hanya yang is_active=True"),
    limit: int = Query(default=100, ge=1, le=500),
):
    """List master produk dengan filter opsional."""
    service = MasterProdukService(db)
    produk_list = service.list_all(
        keyword=keyword, tipe=tipe, only_active=only_active, limit=limit,
    )
    return MasterProdukListResponse(
        total=len(produk_list),
        data=[MasterProdukResponse.model_validate(p) for p in produk_list],
    )


@router.get(
    "/{id_produk}",
    response_model=MasterProdukResponse,
    status_code=status.HTTP_200_OK,
    summary="Detail 1 produk",
)
def get_produk(
    db: DbSession,
    _: Annotated[object, Depends(_READ_ROLES)],
    id_produk: int = Path(..., ge=1),
):
    service = MasterProdukService(db)
    return MasterProdukResponse.model_validate(service.get_by_id(id_produk))


# =============================================================================
# CREATE
# =============================================================================
@router.post(
    "",
    response_model=MasterProdukResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register produk baru",
)
def create_produk(
    payload: MasterProdukCreate,
    db: DbSession,
    current_user: CurrentUser,
    request: Request,
    _: Annotated[object, Depends(_WRITE_ROLES)],
):
    """
    Validasi:
    - `kode_produk` harus unique
    - `tipe_produk` ∈ {RETAIL, CABIN, ALAT}
    - kalau `id_bahan_sumber` di-set (produk repack), `qty_per_unit_produk` wajib
    """
    service = MasterProdukService(db)
    produk = service.create_produk(
        payload=payload,
        actor_id_staf=current_user.id_staf,
        request=request,
    )
    return MasterProdukResponse.model_validate(produk)


# =============================================================================
# UPDATE — partial
# =============================================================================
@router.put(
    "/{id_produk}",
    response_model=MasterProdukResponse,
    status_code=status.HTTP_200_OK,
    summary="Update profile produk (partial — only fields yang dikirim)",
)
def update_produk(
    id_produk: int,
    payload: MasterProdukUpdate,
    db: DbSession,
    current_user: CurrentUser,
    request: Request,
    _: Annotated[object, Depends(_WRITE_ROLES)],
):
    """
    Partial update — kirim hanya field yang ingin di-ubah.

    Stok TIDAK bisa di-update via endpoint ini (pakai /restock atau write-off
    via apotek). Mencegah accidental stock manipulation tanpa audit trail proper.
    """
    service = MasterProdukService(db)
    produk = service.update_profile(
        id_produk=id_produk,
        payload=payload,
        actor_id_staf=current_user.id_staf,
        request=request,
    )
    return MasterProdukResponse.model_validate(produk)


# =============================================================================
# SET ACTIVE
# =============================================================================
@router.patch(
    "/{id_produk}/set-active",
    response_model=ProdukGenericResponse,
    status_code=status.HTTP_200_OK,
    summary="Aktifkan / non-aktifkan produk",
)
def set_active_produk(
    id_produk: int,
    payload: SetActiveProdukRequest,
    db: DbSession,
    current_user: CurrentUser,
    request: Request,
    _: Annotated[object, Depends(_WRITE_ROLES)],
):
    """
    Soft delete equivalent — produk yang `is_active=False` tidak muncul di
    katalog Apotek/Dokter, tapi history transaksi lama tetap ada.
    """
    service = MasterProdukService(db)
    return service.set_active(
        id_produk=id_produk,
        is_active=payload.is_active,
        actor_id_staf=current_user.id_staf,
        request=request,
    )


# =============================================================================
# RESTOCK
# =============================================================================
@router.patch(
    "/{id_produk}/restock",
    response_model=RestockProdukResponse,
    status_code=status.HTTP_200_OK,
    summary="Tambah stok dari supplier (qty positif)",
)
def restock_produk(
    id_produk: int,
    payload: RestockProdukRequest,
    db: DbSession,
    current_user: CurrentUser,
    request: Request,
    _: Annotated[object, Depends(_RESTOCK_ROLES)],
):
    """
    Tambah stok produk:

    - `qty` HARUS positif (mau kurangi stok pakai write-off di /apotek)
    - `keterangan` wajib (no. PO / faktur / supplier)
    - Audit log aksi `RESTOCK_PRODUK`

    Pakai `SELECT FOR UPDATE` lock untuk race-safe kalau 2 apoteker
    restock produk yang sama bersamaan.
    """
    service = MasterProdukService(db)
    return service.restock(
        id_produk=id_produk,
        payload=payload,
        actor_id_staf=current_user.id_staf,
        request=request,
    )
