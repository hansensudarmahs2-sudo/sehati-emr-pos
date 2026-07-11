"""
Ruang Tindakan endpoints — perawat workflow.

Routes:
    GET   /api/v1/ruang-tindakan/antrian                       — list pasien hari ini ANTRI/ON treatment
    GET   /api/v1/ruang-tindakan/kunjungan/{id}/detail         — SOAP dokter + daftar tindakan
    POST  /api/v1/ruang-tindakan/start                         — PENDING → PROSES (stopwatch on)
    POST  /api/v1/ruang-tindakan/end                           — PROSES → SELESAI + auto potong BHP
    POST  /api/v1/ruang-tindakan/upsell                        — tambah treatment/produk (PIN dokter kalau perlu)

RBAC:
- Antrian & detail (read)    : Perawat, Dokter, Admin, Superadmin, Owner
- Start & end tindakan       : Perawat, Dokter (kalau dokter eksekusi sendiri), Admin, Owner
- Upsell                     : Perawat, Dokter, Admin, Owner (PIN dokter wajib kalau butuh_otorisasi=1)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, status

from app.core.deps import CurrentUser, DbSession, role_required
from app.db.models import StafRoleEnum
from app.schemas.treatment import (
    AntrianRuangTindakanResponse,
    DetailRuangTindakanResponse,
    EndTreatmentRequest,
    EndTreatmentResponse,
    StartTreatmentRequest,
    StartTreatmentResponse,
    UpsellRequest,
    UpsellResponse,
)
from app.services.treatment_service import TreatmentService
from app.services.upsell_service import UpsellService


router = APIRouter(prefix="/ruang-tindakan", tags=["Ruang Tindakan (Perawat)"])


# =============================================================================
# Role guards
# =============================================================================
_READ_ROLES = role_required(
    StafRoleEnum.PERAWAT,
    StafRoleEnum.DOKTER,
    StafRoleEnum.ADMIN,
    StafRoleEnum.SUPERADMIN,
    StafRoleEnum.OWNER,
)
_EXECUTE_ROLES = role_required(
    StafRoleEnum.PERAWAT,
    StafRoleEnum.DOKTER,
    StafRoleEnum.ADMIN,
    StafRoleEnum.SUPERADMIN,
    StafRoleEnum.OWNER,
)


# =============================================================================
# READ — antrian & detail
# =============================================================================
@router.get(
    "/antrian",
    response_model=AntrianRuangTindakanResponse,
    status_code=status.HTTP_200_OK,
    summary="Antrian Ruang Tindakan hari ini (ANTRI_TREATMENT + ON_TREATMENT)",
)
def list_antrian(
    db: DbSession,
    _: Annotated[object, Depends(_READ_ROLES)],
):
    """Dashboard perawat. Sorted by nomor_antrean. Include counter tindakan pending/proses."""
    service = TreatmentService(db)
    return service.lihat_antrian()


@router.get(
    "/kunjungan/{id_kunjungan}/detail",
    response_model=DetailRuangTindakanResponse,
    status_code=status.HTTP_200_OK,
    summary="Detail tindakan (SOAP dokter + daftar tindakan)",
)
def detail_tindakan(
    db: DbSession,
    _: Annotated[object, Depends(_READ_ROLES)],
    id_kunjungan: int = Path(..., ge=1),
):
    """
    Kolom kiri iPad ruang tindakan:
    - Instruksi dokter (anamnesa, PF, diagnosa, saran_treatment, saran_produk)
    - Daftar semua kunjungan_tindakan untuk kunjungan ini (status + waktu + pelaksana)
    """
    service = TreatmentService(db)
    return service.get_detail(id_kunjungan)


# =============================================================================
# WRITE — start & end tindakan
# =============================================================================
@router.post(
    "/start",
    response_model=StartTreatmentResponse,
    status_code=status.HTTP_200_OK,
    summary="Start tindakan (PENDING → PROSES). Stopwatch aktif.",
)
def start_tindakan(
    payload: StartTreatmentRequest,
    db: DbSession,
    current_user: CurrentUser,
    request: Request,
    _: Annotated[object, Depends(_EXECUTE_ROLES)],
):
    """
    Pasien menerima tindakan. Status tindakan PENDING → PROSES.
    Otomatis transition kunjungan ke ON_TREATMENT (kalau belum).
    """
    service = TreatmentService(db)
    return service.start_tindakan(
        id_kunjungan_tindakan=payload.id_kunjungan_tindakan,
        id_staf_pelaksana=current_user.id_staf,
        request=request,
    )


@router.post(
    "/end",
    response_model=EndTreatmentResponse,
    status_code=status.HTTP_200_OK,
    summary="End tindakan (PROSES → SELESAI). Auto potong BHP + smart check.",
)
def end_tindakan(
    payload: EndTreatmentRequest,
    db: DbSession,
    current_user: CurrentUser,
    request: Request,
    _: Annotated[object, Depends(_EXECUTE_ROLES)],
):
    """
    Tindakan selesai. Status PROSES → SELESAI. Auto:
    1. Potong stok kabin untuk semua treatment_komponen kategori BAHAN.
    2. Tulis ke inventory_history (jenis_mutasi=TINDAKAN).
    3. SMART CHECK: kalau tidak ada tindakan lain PENDING/PROSES di kunjungan ini,
       transition kunjungan ke ANTRI_BAYAR (lempar ke kasir).

    Pakai SELECT ... FOR UPDATE untuk hindari race condition saat 2 perawat
    end_treatment bahan yang sama bersamaan.
    """
    service = TreatmentService(db)
    return service.end_tindakan(
        id_kunjungan_tindakan=payload.id_kunjungan_tindakan,
        id_staf_pelaksana=current_user.id_staf,
        request=request,
    )


# =============================================================================
# UPSELL — tambah treatment/produk on-the-fly (PIN dokter kalau perlu)
# =============================================================================
@router.post(
    "/upsell",
    response_model=UpsellResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upsell treatment/produk dari ruang tindakan",
)
def upsell(
    payload: UpsellRequest,
    db: DbSession,
    current_user: CurrentUser,
    request: Request,
    _: Annotated[object, Depends(_EXECUTE_ROLES)],
):
    """
    Perawat tambah treatment atau produk on-the-fly saat pasien ON_TREATMENT.

    Logic PIN authorization:
    - Kalau `tipe_item=TREATMENT` dan `master_treatment.butuh_otorisasi=True`,
      `id_staf_otorisasi` + `pin_otorisasi` WAJIB. PIN divalidasi bcrypt.
    - Dokter otorisasi harus role DOKTER/OWNER/SUPERADMIN dan is_active.
    - Kalau gagal otorisasi, 401 + audit log "UPSELL_REJECTED_PIN_INVALID".

    Setelah lolos:
    - TREATMENT → INSERT kunjungan_tindakan (status PENDING)
    - PRODUK → INSERT kunjungan_resep
    - Status kunjungan dipaksa kembali ke ON_TREATMENT
    """
    service = UpsellService(db)
    return service.submit_upsell(
        payload=payload,
        id_staf_pengusul=current_user.id_staf,
        request=request,
    )
