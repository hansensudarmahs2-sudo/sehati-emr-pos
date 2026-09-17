"""
FO (Front Office) endpoints — registrasi pasien, search, detail, alergi.

Routes:
    POST   /api/v1/pasien/baru                  — register pasien baru + kunjungan pertama (atomic)
    GET    /api/v1/pasien/cari?keyword=...      — search by nama / no_rm / nomor_telepon
    GET    /api/v1/pasien/{id_pasien}           — detail pasien + alergi + penyakit kronis aktif
    POST   /api/v1/pasien/alergi                — tambah alergi ke pasien existing
    DELETE /api/v1/pasien/alergi/{id_alergi}    — soft delete alergi (medical safe)

RBAC:
- Register pasien baru     : FO, ADMIN, SUPERADMIN, OWNER
- Search & detail (read)   : FO, KASIR, PERAWAT, DOKTER, ADMIN, SUPERADMIN, OWNER
- Tambah alergi            : FO, PERAWAT, DOKTER, ADMIN, SUPERADMIN, OWNER
- Hapus alergi (sensitive) : DOKTER, ADMIN, SUPERADMIN, OWNER
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.core.deps import CurrentUser, DbSession, role_required
from app.db.models import StafRoleEnum
from app.schemas.pasien import (
    AlergiAddRequest,
    AlergiResponse,
    PasienBaruRequest,
    PasienBaruResponse,
    PasienDetailResponse,
    PasienSearchResponse,
    RiwayatPasienResponse,
)
from app.schemas.staf import GenericSuccessResponse
from app.services.pasien_service import PasienService, DuplikatPasienError


router = APIRouter(prefix="/pasien", tags=["Pasien (FO)"])


# =============================================================================
# Role guards — reusable, dipakai berkali-kali di file ini
# =============================================================================
_REGISTER_ROLES = role_required(
    StafRoleEnum.FO,
    StafRoleEnum.ADMIN,
    StafRoleEnum.SUPERADMIN,
    StafRoleEnum.OWNER,
)
_READ_ROLES = role_required(
    StafRoleEnum.FO,
    StafRoleEnum.KASIR,
    StafRoleEnum.PERAWAT,
    StafRoleEnum.DOKTER,
    StafRoleEnum.ADMIN,
    StafRoleEnum.SUPERADMIN,
    StafRoleEnum.OWNER,
)
_TAMBAH_ALERGI_ROLES = role_required(
    StafRoleEnum.FO,
    StafRoleEnum.PERAWAT,
    StafRoleEnum.DOKTER,
    StafRoleEnum.ADMIN,
    StafRoleEnum.SUPERADMIN,
    StafRoleEnum.OWNER,
)
_HAPUS_ALERGI_ROLES = role_required(
    StafRoleEnum.DOKTER,
    StafRoleEnum.ADMIN,
    StafRoleEnum.SUPERADMIN,
    StafRoleEnum.OWNER,
)


# =============================================================================
# READ — search & detail
# =============================================================================
@router.get(
    "/cari",
    response_model=PasienSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Cari pasien by nama / no_rm / nomor_telepon",
)
def cari_pasien(
    db: DbSession,
    _: Annotated[object, Depends(_READ_ROLES)],
    keyword: str = Query(
        ...,
        min_length=1,
        max_length=100,
        description="Kata kunci pencarian (nama, no_rm, atau nomor telepon).",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
        description="Maksimum hasil yang dikembalikan.",
    ),
):
    """Search pasien. Cocok untuk autocomplete di form daftar ulang."""
    service = PasienService(db)
    hasil = service.search(keyword=keyword, limit=limit)
    return PasienSearchResponse(
        total_ditemukan=len(hasil),
        data=hasil,
    )


@router.get(
    "/{id_pasien}",
    response_model=PasienDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Detail pasien + alergi & penyakit kronis aktif",
)
def detail_pasien(
    db: DbSession,
    _: Annotated[object, Depends(_READ_ROLES)],
    id_pasien: int = Path(..., ge=1, description="ID internal pasien."),
):
    """
    Get detail lengkap pasien (data demografi + alergi aktif + penyakit kronis aktif).

    Dipakai untuk:
    - Header dashboard dokter
    - Konfirmasi data sebelum kunjungan baru
    - Display di halaman riwayat pasien
    """
    service = PasienService(db)
    return service.get_detail(id_pasien)


@router.get(
    "/{id_pasien}/riwayat",
    response_model=RiwayatPasienResponse,
    status_code=status.HTTP_200_OK,
    summary="Riwayat pasien — kunjungan, treatment, produk diresepkan & terbayar",
)
def riwayat_pasien(
    db: DbSession,
    _: Annotated[object, Depends(_READ_ROLES)],
    id_pasien: int = Path(..., ge=1, description="ID internal pasien."),
    limit_kunjungan: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Jumlah kunjungan terbaru yang dikembalikan (default 20).",
    ),
):
    """
    Endpoint compound — semua riwayat 1 pasien dalam 1 payload.

    Berisi:
    - **info_pasien**: data demografi
    - **kunjungan**: ringkasan N kunjungan terakhir (default 20, sorted DESC by tgl)
    - **riwayat_treatment**: semua series treatment (pasien_rencana_treatment)
    - **produk_diresepkan**: produk yang diresepkan dokter (kunjungan_resep)
    - **produk_terbayar**: produk yang sudah dibayar pasien (transaksi_kasir)

    Catatan: produk diresepkan vs terbayar sengaja dipisah biar bisa
    tracking compliance — pasien dapat resep vs benar-benar beli.
    """
    service = PasienService(db)
    return service.get_riwayat(
        id_pasien=id_pasien,
        limit_kunjungan=limit_kunjungan,
    )


# =============================================================================
# CREATE — register pasien baru
# =============================================================================
@router.post(
    "/baru",
    response_model=PasienBaruResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register pasien baru + kunjungan pertama (atomic)",
)
def register_pasien_baru(
    payload: PasienBaruRequest,
    db: DbSession,
    current_user: CurrentUser,
    request: Request,
    _: Annotated[object, Depends(_REGISTER_ROLES)],
    konfirmasi_duplikat: bool = False,
):
    """
    Register pasien baru lengkap dengan kunjungan pertama.

    Semua dalam 1 transaksi atomik:
    1. Generate no_rm baru (format YYMMDD-NNN, locked FOR UPDATE)
    2. INSERT pasien
    3. INSERT alergi (kalau ada di payload)
    4. INSERT penyakit kronis (kalau ada di payload)
    5. INSERT kunjungan + assign nomor_antrean hari ini
    6. INSERT antropometri (kalau ada di payload)

    Kalau ada error di tengah, SEMUA di-rollback.
    """
    service = PasienService(db)
    try:
        return service.register_pasien_baru(
            payload=payload,
            id_staf_fo=current_user.id_staf,
            request=request,
            konfirmasi_duplikat=konfirmasi_duplikat,
        )
    except DuplikatPasienError as dup:
        ringkas = "; ".join(f"{c.nama} (RM {c.no_rm})" for c in dup.candidates)
        if dup.kind == "nik":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"NIK sudah terdaftar atas: {ringkas}. Tidak boleh duplikat.",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Pasien dengan identitas mirip ditemukan: {ringkas}. "
                f"Kirim ulang dengan ?konfirmasi_duplikat=true bila memang pasien baru."
            ),
        )


# =============================================================================
# ALERGI — standalone (untuk pasien yang sudah terdaftar)
# =============================================================================
@router.post(
    "/alergi",
    response_model=AlergiResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Tambah alergi ke pasien existing",
)
def tambah_alergi(
    payload: AlergiAddRequest,
    db: DbSession,
    current_user: CurrentUser,
    request: Request,
    _: Annotated[object, Depends(_TAMBAH_ALERGI_ROLES)],
):
    """Tambah catatan alergi ke pasien yang sudah terdaftar."""
    service = PasienService(db)
    return service.tambah_alergi(
        payload=payload,
        id_staf=current_user.id_staf,
        request=request,
    )


@router.delete(
    "/alergi/{id_alergi}",
    response_model=GenericSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Soft delete alergi (jadi tidak aktif, tapi history tetap ada)",
)
def hapus_alergi(
    db: DbSession,
    current_user: CurrentUser,
    request: Request,
    _: Annotated[object, Depends(_HAPUS_ALERGI_ROLES)],
    id_alergi: int = Path(..., ge=1, description="ID alergi yang dihapus."),
):
    """
    Soft delete alergi (set `is_active=False`).

    KENAPA soft delete?
    - Filosofi EMR: medical record tidak boleh hilang.
    - Kalau alergi salah catat, dokter cukup "non-aktifkan" — data lama tetap traceable.
    """
    service = PasienService(db)
    return service.hapus_alergi(
        id_alergi,
        actor_id_staf=current_user.id_staf,
        request=request,
    )
