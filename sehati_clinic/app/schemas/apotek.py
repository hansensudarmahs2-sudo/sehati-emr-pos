"""
Pydantic schemas untuk ApotekService.

Flow:
- GET /apotek/antrian                       → pasien ANTRI_OBAT
- GET /apotek/detail/{id_kunjungan}         → daftar resep + aturan pakai
- POST /apotek/serahkan-obat                → potong master_produk.stok_terkini + COMPLETED
- POST /apotek/write-off-produk             → buang stok produk (rusak/expired/penyesuaian)
- GET /apotek/suggested-order               → produk under stok_minimal + analisa pemakaian
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# ANTRIAN APOTEK
# =============================================================================
class AntrianApotekItem(BaseModel):
    """1 baris pasien yang siap diambil obatnya."""
    model_config = ConfigDict(from_attributes=True)

    id_kunjungan: int
    nomor_antrean: Optional[int] = None
    tgl_kunjungan: Optional[datetime] = None
    status_antrian: Optional[str] = None

    id_pasien: int
    no_rm: str
    nama_pasien: str

    jumlah_item_obat: int = 0


class AntrianApotekResponse(BaseModel):
    status: str = "success"
    tanggal: date
    total: int
    data: list[AntrianApotekItem]


# =============================================================================
# DETAIL RESEP
# =============================================================================
class ResepDetailItem(BaseModel):
    """1 baris detail resep untuk apoteker — produk yg harus disiapkan."""
    model_config = ConfigDict(from_attributes=True)

    id_resep: int
    id_produk: int
    kode_produk: str
    nama_produk: str
    qty: float
    satuan: Optional[str] = None
    aturan_pakai: Optional[str] = None
    status_item: Optional[str] = None        # PENDING / DIBAYAR / BATAL
    stok_terkini: Optional[float] = None     # quick view ketersediaan
    stok_cukup: bool = True                  # qty <= stok_terkini


class DetailResepResponse(BaseModel):
    status: str = "success"
    id_kunjungan: int
    id_pasien: int
    no_rm: str
    nama_pasien: str
    daftar_obat: list[ResepDetailItem] = Field(default_factory=list)
    total_item: int = 0
    semua_stok_cukup: bool = True            # quick flag — kalau false, apoteker hati2


# =============================================================================
# SERAHKAN OBAT
# =============================================================================
class SerahkanObatRequest(BaseModel):
    """Eksekusi penyerahan obat ke pasien."""
    id_kunjungan: int = Field(..., ge=1)


class StokPotongItem(BaseModel):
    """Snapshot per produk yang ter-potong (return ke UI)."""
    id_produk: int
    nama_produk: str
    qty_diserahkan: float
    stok_sebelum: float
    stok_sesudah: float


class SerahkanObatResponse(BaseModel):
    status: str = "success"
    message: str
    data: dict  # { id_kunjungan, jumlah_item, items_dipotong (list StokPotongItem), status_kunjungan_baru }


# =============================================================================
# WRITE-OFF PRODUK
# =============================================================================
class WriteOffProdukRequest(BaseModel):
    """
    Penyesuaian stok produk POS (buang rusak / expired / koreksi inventory).

    Untuk write-off bahan klinik (BHP perawat), pakai endpoint terpisah
    di /inventory (Phase 2+).
    """
    id_produk: int = Field(..., ge=1)
    jenis_mutasi: str = Field(..., description="EXPIRED, RUSAK, atau PENYESUAIAN")
    qty_dibuang: float = Field(..., gt=0)
    keterangan: str = Field(..., min_length=3, max_length=200)


class WriteOffProdukResponse(BaseModel):
    status: str = "success"
    message: str
    data: dict  # { id_produk, nama_produk, jenis_mutasi, qty_dibuang, stok_sebelum, stok_sesudah }


# =============================================================================
# SUGGESTED ORDER
# =============================================================================
class SuggestedOrderItem(BaseModel):
    """1 baris produk yang disarankan di-restock."""
    model_config = ConfigDict(from_attributes=True)

    id_produk: int
    kode_produk: str
    nama_produk: str
    satuan: Optional[str] = None
    tipe_produk: Optional[str] = None
    stok_terkini: float
    stok_minimal: float
    stok_minimal_efektif: float = 0  # DYN-L2: MAX(manual, ROP dinamis)

    # Analytics
    qty_terjual_90_hari: float
    qty_terjual_30_hari: float
    rata_pemakaian_harian: float
    estimasi_hari_habis: Optional[float] = None     # kalau stok / rata_pemakaian
    saran_order_qty: float                          # heuristic: 30 hari pemakaian, min stok_minimal
    kategori: str                                   # "URGENT", "RENDAH", "AMAN", "NO_DATA"


class SuggestedOrderResponse(BaseModel):
    status: str = "success"
    waktu_analisa: datetime
    total_produk_dianalisa: int = 0
    total_butuh_order: int = 0
    data: list[SuggestedOrderItem]


__all__ = [
    "AntrianApotekItem", "AntrianApotekResponse",
    "ResepDetailItem", "DetailResepResponse",
    "SerahkanObatRequest", "StokPotongItem", "SerahkanObatResponse",
    "WriteOffProdukRequest", "WriteOffProdukResponse",
    "SuggestedOrderItem", "SuggestedOrderResponse",
]
