"""
Reports endpoints — laporan agregat (read-only).

Routes:
    GET /api/v1/reports/omzet-harian?tanggal=YYYY-MM-DD — rekap omzet 1 hari

RBAC:
- Semua endpoint: Admin, Superadmin, Owner (managerial)
"""

from datetime import date as _date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import DbSession, role_required
from app.db.models import StafRoleEnum
from app.schemas.reports import OmzetHarianResponse
from app.services.reports_service import ReportsService


router = APIRouter(prefix="/reports", tags=["Reports"])


_REPORTS_ROLES = role_required(
    StafRoleEnum.ADMIN,
    StafRoleEnum.SUPERADMIN,
    StafRoleEnum.OWNER,
)


@router.get(
    "/omzet-harian",
    response_model=OmzetHarianResponse,
    status_code=status.HTTP_200_OK,
    summary="Rekap omzet harian + breakdown per kasir & per metode bayar",
)
def omzet_harian(
    db: DbSession,
    _: Annotated[object, Depends(_REPORTS_ROLES)],
    tanggal: Optional[_date] = Query(
        default=None,
        description="Format YYYY-MM-DD. Default: hari ini.",
    ),
):
    """
    Rekap omzet untuk 1 tanggal:

    - **total_transaksi**: jumlah transaksi sukses
    - **total_omzet**: sum total_tagihan (sudah dikurangi diskon)
    - **total_diskon**: sum nominal_diskon yang diberikan
    - **rata_per_transaksi**: omzet / transaksi
    - **per_kasir**: breakdown per kasir, sorted DESC by omzet
    - **per_metode**: breakdown per metode bayar (TUNAI/QRIS/DEBIT/dll), sorted DESC by nominal

    Catatan: angka "total_omzet" vs sum "per_metode" mungkin beda kalau ada
    split payment (1 transaksi = N metode). Itu by design — `total_omzet`
    pakai `total_tagihan` (= grand total), `per_metode` pakai `nominal`
    per pembayaran.
    """
    if tanggal is None:
        tanggal = _date.today()
    return ReportsService(db).omzet_harian(tanggal)
