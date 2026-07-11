"""
Kasir endpoints — antrian, tagihan, bayar, void, rekap shift.

Routes:
    GET   /api/v1/kasir/antrian                — pasien ANTRI_BAYAR hari ini
    GET   /api/v1/kasir/tagihan/{id_kunjungan} — auto-hitung tagihan (idempotent)
    POST  /api/v1/kasir/bayar                  — eksekusi pembayaran (split payment)
    POST  /api/v1/kasir/void-item              — void resep dengan PIN dokter/admin
    GET   /api/v1/kasir/rekap-shift            — rekap shift kasir sejak login

RBAC:
- Antrian + tagihan + bayar + rekap: Kasir, Admin, Superadmin, Owner
- Void item                         : Kasir (yang request) + PIN Dokter/Admin (otorisasi)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, status

from app.core.deps import CurrentUser, DbSession, role_required
from app.db.models import StafRoleEnum
from app.schemas.kasir import (
    AntrianKasirResponse,
    BayarRequest,
    BayarResponse,
    RekapShiftResponse,
    TagihanResponse,
    VoidItemRequest,
    VoidItemResponse,
)
from app.services.kasir_service import KasirService


router = APIRouter(prefix="/kasir", tags=["Kasir"])


_KASIR_ROLES = role_required(
    StafRoleEnum.KASIR,
    StafRoleEnum.ADMIN,
    StafRoleEnum.SUPERADMIN,
    StafRoleEnum.OWNER,
)


@router.get(
    "/antrian",
    response_model=AntrianKasirResponse,
    status_code=status.HTTP_200_OK,
    summary="Antrian kasir — pasien ANTRI_BAYAR hari ini",
)
def antrian_kasir(
    db: DbSession,
    _: Annotated[object, Depends(_KASIR_ROLES)],
):
    """Pasien status ANTRI_BAYAR hari ini, sorted by nomor_antrean."""
    return KasirService(db).lihat_antrian()


@router.get(
    "/tagihan/{id_kunjungan}",
    response_model=TagihanResponse,
    status_code=status.HTTP_200_OK,
    summary="Auto-hitung tagihan — idempotent (return LUNAS kalau sudah bayar)",
)
def tagihan_kasir(
    db: DbSession,
    _: Annotated[object, Depends(_KASIR_ROLES)],
    id_kunjungan: int = Path(..., ge=1),
):
    """
    Tagihan compound:

    1. **Bulletproof check**: kalau kunjungan ini sudah ada transaksi_kasir,
       return `sudah_lunas: true` dengan total_tagihan = 0 (cegah double billing).
    2. **Treatment**: semua kunjungan_tindakan SELESAI × harga. Tindakan yang
       pakai kuota member → charge 0 di tagihan.
    3. **Produk**: semua kunjungan_resep PENDING × harga_jual.
    4. **Diskon**: dari master_membership berdasarkan tipe_membership pasien
       (Owner bisa update kolom diskon_treatment_persen / diskon_produk_persen
       di DB kapan saja tanpa redeploy).
    5. **Total** = subtotal − nominal_diskon.
    """
    return KasirService(db).get_tagihan(id_kunjungan)


@router.post(
    "/bayar",
    response_model=BayarResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Eksekusi pembayaran (split payment ready, atomic)",
)
def bayar_kasir(
    payload: BayarRequest,
    db: DbSession,
    current_user: CurrentUser,
    request: Request,
    _: Annotated[object, Depends(_KASIR_ROLES)],
):
    """
    Eksekusi pembayaran 1 kunjungan:

    1. Re-fetch tagihan (server source of truth — anti tamper frontend)
    2. Validate total bayar >= total tagihan
    3. INSERT transaksi_kasir + detail_produk (per resep) + pembayaran (per metode)
    4. Mark semua resep PENDING di kunjungan ini → DIBAYAR
    5. Transition status kunjungan:
       - Ada resep di-DIBAYAR → ANTRI_OBAT (lempar ke apotek)
       - Tidak ada → COMPLETED
    6. Return kembalian + status baru

    Atomic — kalau salah satu step gagal, semua rollback.
    """
    return KasirService(db).proses_bayar(
        payload=payload,
        id_staf_kasir=current_user.id_staf,
        request=request,
    )


@router.post(
    "/void-item",
    response_model=VoidItemResponse,
    status_code=status.HTTP_200_OK,
    summary="Void 1 item resep (PIN dokter/admin wajib)",
)
def void_item_kasir(
    payload: VoidItemRequest,
    db: DbSession,
    current_user: CurrentUser,
    request: Request,
    _: Annotated[object, Depends(_KASIR_ROLES)],
):
    """
    Void 1 item resep:

    - Resep harus dalam status PENDING (yang sudah DIBAYAR / BATAL tidak bisa di-void lagi)
    - PIN otorisasi dokter/admin/superadmin/owner WAJIB divalidasi (bcrypt)
    - Audit log catat siapa kasir, siapa otorisator, alasan void

    Pattern PIN ini konsisten dengan upsell otorisasi (DEC pattern).
    """
    return KasirService(db).void_item_resep(
        payload=payload,
        id_staf_kasir=current_user.id_staf,
        request=request,
    )


@router.get(
    "/rekap-shift",
    response_model=RekapShiftResponse,
    status_code=status.HTTP_200_OK,
    summary="Rekap shift kasir sejak login",
)
def rekap_shift_kasir(
    db: DbSession,
    current_user: CurrentUser,
    _: Annotated[object, Depends(_KASIR_ROLES)],
):
    """
    Rekap transaksi sejak `waktu_mulai_shift` (anchor shift):

    - Total transaksi, total omzet
    - Per metode pembayaran: jumlah & nominal
    - Daftar transaksi sorted DESC by waktu_bayar

    Cocok untuk akhir shift cetak laporan untuk handover ke kasir berikutnya
    atau setor ke kantor.
    """
    return KasirService(db).rekap_shift(current_user.id_staf)
