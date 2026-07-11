"""
Apotek endpoints — antrian, detail, serahkan obat, write-off, suggested order.

Routes:
    GET   /api/v1/apotek/antrian                          — pasien ANTRI_OBAT
    GET   /api/v1/apotek/detail/{id_kunjungan}            — daftar resep + aturan + stok check
    POST  /api/v1/apotek/serahkan-obat                    — potong stok produk + COMPLETED
    POST  /api/v1/apotek/write-off-produk                 — buang stok rusak/expired/penyesuaian
    GET   /api/v1/apotek/suggested-order                  — analisa pemakaian → saran restock

RBAC:
- Semua endpoint: Apoteker, Admin, Superadmin, Owner
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, status

from app.core.deps import CurrentUser, DbSession, role_required
from app.db.models import StafRoleEnum
from app.schemas.apotek import (
    AntrianApotekResponse,
    DetailResepResponse,
    SerahkanObatRequest,
    SerahkanObatResponse,
    SuggestedOrderResponse,
    WriteOffProdukRequest,
    WriteOffProdukResponse,
)
from app.services.apotek_service import ApotekService


router = APIRouter(prefix="/apotek", tags=["Apotek"])


_APOTEK_ROLES = role_required(
    StafRoleEnum.APOTEKER,
    StafRoleEnum.ADMIN,
    StafRoleEnum.SUPERADMIN,
    StafRoleEnum.OWNER,
)


@router.get(
    "/antrian",
    response_model=AntrianApotekResponse,
    status_code=status.HTTP_200_OK,
    summary="Antrian apotek — pasien ANTRI_OBAT hari ini",
)
def antrian_apotek(
    db: DbSession,
    _: Annotated[object, Depends(_APOTEK_ROLES)],
):
    """Pasien yang sudah bayar di kasir & siap ambil obat. Sorted by nomor_antrean."""
    return ApotekService(db).lihat_antrian()


@router.get(
    "/detail/{id_kunjungan}",
    response_model=DetailResepResponse,
    status_code=status.HTTP_200_OK,
    summary="Detail resep + stok check per item",
)
def detail_resep_apotek(
    db: DbSession,
    _: Annotated[object, Depends(_APOTEK_ROLES)],
    id_kunjungan: int = Path(..., ge=1),
):
    """
    Detail semua resep di kunjungan (kecuali BATAL):

    - Per item: nama, qty, satuan, aturan pakai, status item, stok produk saat ini
    - Flag `stok_cukup` per item → apoteker tahu mana yang short
    - Flag `semua_stok_cukup` global → quick decision sebelum serahkan
    """
    return ApotekService(db).get_detail_resep(id_kunjungan)


@router.post(
    "/serahkan-obat",
    response_model=SerahkanObatResponse,
    status_code=status.HTTP_200_OK,
    summary="Eksekusi penyerahan obat — potong stok + COMPLETED",
)
def serahkan_obat(
    payload: SerahkanObatRequest,
    db: DbSession,
    current_user: CurrentUser,
    request: Request,
    _: Annotated[object, Depends(_APOTEK_ROLES)],
):
    """
    Eksekusi penyerahan obat ke pasien:

    1. Validasi kunjungan status ANTRI_OBAT
    2. Ambil semua resep DIBAYAR di kunjungan ini
    3. Loop potong `master_produk.stok_terkini` (SELECT FOR UPDATE lock per produk)
    4. Transition status kunjungan: ANTRI_OBAT → COMPLETED
    5. Audit log SERAH_OBAT

    Atomic — kalau gagal di tengah, semua rollback.
    """
    return ApotekService(db).serahkan_obat(
        payload=payload,
        id_staf_apoteker=current_user.id_staf,
        request=request,
    )


@router.post(
    "/write-off-produk",
    response_model=WriteOffProdukResponse,
    status_code=status.HTTP_200_OK,
    summary="Write-off produk POS (rusak/expired/penyesuaian)",
)
def write_off_produk(
    payload: WriteOffProdukRequest,
    db: DbSession,
    current_user: CurrentUser,
    request: Request,
    _: Annotated[object, Depends(_APOTEK_ROLES)],
):
    """
    Buang stok produk dengan alasan:

    - `EXPIRED` — kadaluwarsa
    - `RUSAK` — kemasan pecah/leaked/dll
    - `PENYESUAIAN` — koreksi inventory (mis. hasil stock opname)

    Pakai `SELECT FOR UPDATE` lock supaya race-safe.
    Audit log per jenis (`WRITEOFF_PRODUK_EXPIRED`, dll) supaya gampang filter rekap.

    **Tidak untuk write-off bahan klinik (BHP perawat)** — itu ranah `/inventory`
    endpoint (Phase 2+).
    """
    return ApotekService(db).write_off_produk(
        payload=payload,
        id_staf_apoteker=current_user.id_staf,
        request=request,
    )


@router.get(
    "/suggested-order",
    response_model=SuggestedOrderResponse,
    status_code=status.HTTP_200_OK,
    summary="Saran restock berdasarkan pemakaian 90 hari",
)
def suggested_order(
    db: DbSession,
    _: Annotated[object, Depends(_APOTEK_ROLES)],
):
    """
    Analisa produk yang perlu di-order ulang:

    - **Source pemakaian**: `transaksi_detail_produk` (90 & 30 hari terakhir)
    - **Heuristic**:
      - `rata_pemakaian_harian = qty_90_hari / 90`
      - `estimasi_hari_habis = stok_terkini / rata_harian`
      - `saran_order = max(qty_30_hari, stok_minimal − stok_terkini)`
    - **Kategori**:
      - **URGENT**: stok < ½ minimal atau habis < 7 hari
      - **RENDAH**: stok < minimal atau habis < 30 hari
      - **AMAN**: cukup
      - **NO_DATA**: barang baru / tidak ada penjualan 90 hari

    Sorted: URGENT first, lalu RENDAH/AMAN/NO_DATA.
    """
    return ApotekService(db).suggested_order()
