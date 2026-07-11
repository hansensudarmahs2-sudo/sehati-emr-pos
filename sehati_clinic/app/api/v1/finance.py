"""
Finance Module API — Skeleton (Phase 0)

Status: 🟡 PLACEHOLDER — All endpoints return 501 Not Implemented.

Reserved API namespace untuk Finance Module decoupling (DEC-064, 11 Juni 2026).
Lihat Project_Memory/FinanceModule/00_DESIGN.md untuk full spec.

Saat Phase 1 mulai, isi implementasi per endpoint. Schema response sudah didefinisikan
di docstring sebagai kontrak referensi.

Authentication: TBD (akan pakai external_api_keys table + Bearer token middleware).
Rate limiting: TBD (60 req/menit per API key).
"""

from typing import Optional
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query, status


router = APIRouter(prefix="/api/v1/finance", tags=["Finance Module API"])


# ============================================================================
# Helper — 501 Not Implemented response
# ============================================================================
def _not_yet_implemented(endpoint_name: str) -> HTTPException:
    """Standardize 501 response untuk skeleton endpoints."""
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            f"Endpoint '{endpoint_name}' belum diimplementasi. "
            f"Reserved untuk Finance Module integration (DEC-064 Phase 1). "
            f"Lihat Project_Memory/FinanceModule/00_DESIGN.md."
        ),
    )


# ============================================================================
# 1. Transaksi Penjualan (Source of Truth Omzet)
# ============================================================================
@router.get("/transaksi", summary="List transaksi penjualan untuk Finance pull")
def list_transaksi_for_finance(
    since: Optional[datetime] = Query(None, description="ISO8601 cursor — last sync timestamp"),
    until: Optional[datetime] = Query(None, description="ISO8601 — default: now"),
    include_void: bool = Query(True, description="Include VOID status_transaksi"),
    page: int = Query(1, ge=1),
    page_size: int = Query(500, ge=1, le=1000),
):
    """
    Pull transaksi baru/updated since last sync.

    Response schema (saat implemented):
    {
        "items": [
            {
                "id_transaksi", "id_kunjungan", "waktu_bayar", "status_transaksi",
                "void_at", "void_reason_code", "void_reason_note", "late_void",
                "no_rm", "nama_pasien", "tipe_membership",
                "id_staf_kasir", "nama_kasir",
                "subtotal", "nominal_diskon", "total_tagihan", "keterangan_promo",
                "items": [{ tipe, id_treatment, id_produk, nama, qty,
                            harga_satuan, subtotal, hpp_at_sale, id_kuota_member,
                            id_rencana }],
                "pembayaran": [{ metode_bayar, nominal }]
            }
        ],
        "total_count", "page", "total_pages", "cursor_next"
    }

    Authentication: Bearer API key required.
    Use case: Finance pull → record Jurnal Entry (Sales, COGS, Cash/Bank, Discount).
    """
    raise _not_yet_implemented("list_transaksi_for_finance")


@router.get("/transaksi/{id_transaksi}", summary="Detail transaksi tunggal")
def get_transaksi_detail_for_finance(id_transaksi: int):
    """Single transaksi detail (untuk debug/reconciliation manual)."""
    raise _not_yet_implemented("get_transaksi_detail_for_finance")


# ============================================================================
# 2. Pengadaan / PO (Cost Side)
# ============================================================================
@router.get("/pengadaan", summary="List PO untuk Finance pull (Cost side)")
def list_pengadaan_for_finance(
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
    status_filter: Optional[str] = Query(
        None, description="RECEIVED | PARTIAL_RECEIVED | ORDERED | CANCELLED | all"
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(500, ge=1, le=1000),
):
    """
    Pull PO + items_received untuk record Purchases / Inventory increase.

    Response: list pengadaan dengan items_received (per receive event).

    Use case: Finance record Cost of Goods Purchased + Accounts Payable +
              Inventory asset increase. Plus 3-way match validation.
    """
    raise _not_yet_implemented("list_pengadaan_for_finance")


# ============================================================================
# 3. Komisi & Payroll
# ============================================================================
@router.get("/komisi/staf", summary="Komisi staf per periode untuk payroll")
def get_komisi_staf(
    periode_dari: date = Query(..., description="Tanggal mulai (inclusive)"),
    periode_sampai: date = Query(..., description="Tanggal akhir (inclusive)"),
    id_staf: Optional[int] = Query(None, description="Filter staf tertentu"),
):
    """
    Aggregate komisi dokter/perawat per periode (mis. bulanan untuk slip gaji).

    Response:
    {
        "summary": [
            { id_staf, nama_staf, role, komisi_treatment, komisi_produk, total_komisi }
        ],
        "detail": [
            { id_staf, tanggal, source_type, id_source, nama_item,
              base_value, komisi_persen, komisi_nominal }
        ]
    }

    Validation: Skip transaksi VOID + resep BATAL (jangan hitung komisi yang dibatalkan).
    Reference: DEC-060 Hybrid Komisi formula.
    """
    raise _not_yet_implemented("get_komisi_staf")


# ============================================================================
# 4. Inventory Snapshot (Untuk Neraca)
# ============================================================================
@router.get("/inventory/stok-value", summary="Snapshot nilai stok untuk Neraca")
def get_inventory_stok_value(
    at_timestamp: Optional[datetime] = Query(None, description="Default: now"),
):
    """
    Snapshot nilai stok = sum(stok_terkini × hpp_per_unit) semua items.

    Response:
    {
        "timestamp",
        "total_stok_value",
        "breakdown": { "produk_retail", "produk_cabin", "produk_alat", "bahan_habis_pakai" },
        "items_sample": [{ tipe, nama, stok, hpp_per_unit, value }]   ← top 20
    }

    Use case: Finance record Inventory Asset di Neraca per akhir periode.
    """
    raise _not_yet_implemented("get_inventory_stok_value")


# ============================================================================
# 5. Cash Flow per Metode Bayar
# ============================================================================
@router.get("/cashflow/per-metode", summary="Cash flow per metode bayar")
def get_cashflow_per_metode(
    periode_dari: date = Query(...),
    periode_sampai: date = Query(...),
    per: str = Query("harian", description="harian | mingguan | bulanan"),
):
    """
    Aggregate per metode pembayaran (TUNAI, QRIS, DEBIT, KREDIT, TRANSFER).

    Response: list per periode (tanggal/minggu/bulan) dengan breakdown metode + void_amount.

    Use case: Finance reconciliation kas vs setoran bank, validasi mesin EDC.
    """
    raise _not_yet_implemented("get_cashflow_per_metode")


# ============================================================================
# 6. Series Prepaid Liability (Customer Deposit)
# ============================================================================
@router.get("/series-deposit", summary="Outstanding series prepaid")
def get_series_deposit(
    active_only: bool = Query(True, description="Filter status PENDING + SCHEDULED"),
):
    """
    List sesi treatment yang sudah dibayar tapi belum digunakan = Customer Deposit Liability.

    Response: outstanding per pasien dengan list rencana (urutan_sesi, total_sesi, harga_paket).

    Use case: Finance record Customer Deposit Liability di Neraca.
              Saat pasien pakai sesi → revenue recognition + liability decrement.
    """
    raise _not_yet_implemented("get_series_deposit")


# ============================================================================
# 7. Membership Commitment
# ============================================================================
@router.get("/membership-commitment", summary="Outstanding membership benefit kuota")
def get_membership_commitment():
    """
    List kuota benefit treatment yang masih outstanding per pasien aktif.

    Response: per pasien × per treatment, sisa kuota + outstanding value.

    Use case: Finance treat sebagai Contingent Liability atau Deferred Revenue.
    """
    raise _not_yet_implemented("get_membership_commitment")


# ============================================================================
# 8. Sync Cursor (Idempotency)
# ============================================================================
@router.post("/sync-cursor", summary="Finance lapor balik last sync timestamp")
def update_sync_cursor():
    """
    Finance Module lapor "saya sudah sync sampai timestamp X" untuk module Y.

    Body:
    {
        "module": str,   ← "journal_entry" | "payroll" | "inventory_valuation"
        "last_synced_at": ISO8601 datetime,
        "last_processed_id": int | null,
        "notes": str | null
    }

    Response: { "status": "recorded", "cursor_id": int }

    Sehati simpan di table `finance_sync_cursor` untuk audit + future optimization.
    """
    raise _not_yet_implemented("update_sync_cursor")


# ============================================================================
# 9. Health Check & Metadata
# ============================================================================
@router.get("/health", summary="Health check untuk monitoring Finance Module")
def finance_health_check():
    """Simple liveness check. Tidak butuh authentication."""
    return {
        "status": "ok",
        "service": "sehati-erm-pos-finance-api",
        "server_time": datetime.now().isoformat(),
        "version": "0.1.0-skeleton",
        "phase": "DESIGN — endpoints return 501",
    }


@router.get("/metadata", summary="Metadata klinik + supported endpoints")
def finance_metadata():
    """
    Metadata untuk Finance Module discovery.

    Saat implemented:
    {
        "klinik_id", "klinik_nama",
        "version_schema",
        "supported_endpoints": [...],
        "rate_limit_per_minute": int
    }
    """
    return {
        "klinik_id": "TBD",
        "klinik_nama": "TBD — read from master_klinik_config",
        "version_schema": "0.1.0-skeleton",
        "supported_endpoints": [
            "GET /api/v1/finance/transaksi",
            "GET /api/v1/finance/transaksi/{id_transaksi}",
            "GET /api/v1/finance/pengadaan",
            "GET /api/v1/finance/komisi/staf",
            "GET /api/v1/finance/inventory/stok-value",
            "GET /api/v1/finance/cashflow/per-metode",
            "GET /api/v1/finance/series-deposit",
            "GET /api/v1/finance/membership-commitment",
            "POST /api/v1/finance/sync-cursor",
            "GET /api/v1/finance/health",
            "GET /api/v1/finance/metadata",
        ],
        "implementation_status": "ALL 501 NOT IMPLEMENTED — see Project_Memory/FinanceModule/00_DESIGN.md",
        "rate_limit_per_minute": "TBD",
    }


__all__ = ["router"]
