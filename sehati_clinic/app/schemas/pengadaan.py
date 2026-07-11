"""
Pydantic schemas — Pengadaan (Pemesanan / PO + Receive).

Stock Opname schemas akan ditambah di P5.

Pattern: 
- Request schemas tanpa suffix (PemesananCreateRequest, ReceiveItemRequest)
- Response schemas dengan suffix Response (PemesananResponse, ...)
- Detail compound dengan PemesananDetailResponse (header + items + receives)
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import LokasiOpnameEnum, StatusOpnameEnum, StatusPemesananEnum, TipeItemEnum


# =============================================================================
# REQUEST — Create PO
# =============================================================================
class PemesananItemCreate(BaseModel):
    """1 baris item saat create PO."""
    tipe_item: TipeItemEnum = Field(..., description="PRODUK atau BAHAN")
    id_produk: Optional[int] = Field(default=None, ge=1, description="Wajib kalau tipe=PRODUK")
    id_bahan: Optional[int] = Field(default=None, ge=1, description="Wajib kalau tipe=BAHAN")

    qty_dipesan: float = Field(..., gt=0, description="Qty positif")
    harga_satuan: Optional[Decimal] = Field(default=None, ge=0, description="Untuk total estimasi")
    catatan_item: Optional[str] = Field(default=None, max_length=200)

    @field_validator("id_produk", "id_bahan", mode="before")
    @classmethod
    def _normalize_empty(cls, v):
        if v in (0, "", "0"):
            return None
        return v


class PemesananCreateRequest(BaseModel):
    """Request create PO baru — header + minimal 1 item."""
    supplier_nama: Optional[str] = Field(default=None, max_length=100)
    tgl_perkiraan_datang: Optional[date] = Field(default=None)
    catatan: Optional[str] = Field(default=None, max_length=2000)
    # PO-B (ideal PO)
    termin_hari: Optional[int] = Field(default=None, ge=0, le=3650)
    validitas_hari: Optional[int] = Field(default=None, ge=0, le=3650)
    id_apoteker: Optional[int] = Field(default=None, ge=1, description="Apoteker PJ (wajib dipilih)")
    id_lokasi_pengiriman: Optional[int] = Field(default=None, ge=1, description="Ship-to (opsional)")

    items: list[PemesananItemCreate] = Field(..., min_length=1, description="Minimum 1 item")


class PemesananHeaderUpdate(BaseModel):
    """Update header PO — hanya saat status SUBMITTED."""
    supplier_nama: Optional[str] = Field(default=None, max_length=100)
    tgl_perkiraan_datang: Optional[date] = Field(default=None)
    catatan: Optional[str] = Field(default=None, max_length=2000)


# =============================================================================
# REQUEST — Receive event per item
# =============================================================================
class ReceiveItemRequest(BaseModel):
    """1 event receive untuk 1 item PO."""
    id_pemesanan_item: int = Field(..., ge=1)
    qty_diterima: float = Field(..., gt=0, description="Qty yang diterima event ini")
    nomor_faktur: Optional[str] = Field(default=None, max_length=100)
    catatan: Optional[str] = Field(default=None, max_length=2000)
    # P-L4 (faktur + lot)
    batch_no: Optional[str] = Field(default=None, max_length=50)
    tgl_ed: Optional[date] = Field(default=None)
    harga_terima: Optional[Decimal] = Field(default=None, ge=0)
    id_distributor: Optional[int] = Field(default=None, ge=1)
    id_faktur: Optional[int] = Field(default=None, ge=1)  # FK-L3: link receive ke faktur


# =============================================================================
# RESPONSE
# =============================================================================
class PemesananItemResponse(BaseModel):
    """1 row item PO untuk display."""
    model_config = ConfigDict(from_attributes=True)

    id_item: int
    tipe_item: str
    id_produk: Optional[int] = None
    id_bahan: Optional[int] = None

    nama_snapshot: str
    satuan_snapshot: Optional[str] = None

    qty_dipesan: float
    qty_diterima: float = 0
    harga_satuan: Optional[Decimal] = None
    subtotal: Optional[Decimal] = None
    catatan_item: Optional[str] = None

    # Computed
    qty_sisa: float = 0  # qty_dipesan - qty_diterima
    is_complete: bool = False  # qty_sisa == 0


class PemesananReceiveEventResponse(BaseModel):
    """1 event receive untuk display history."""
    model_config = ConfigDict(from_attributes=True)

    id_receive: int
    id_pemesanan_item: int
    qty_diterima: float
    tgl_terima: datetime
    id_staf_penerima: int
    nama_staf_penerima: Optional[str] = None  # JOIN dari master_staf
    nomor_faktur: Optional[str] = None
    catatan: Optional[str] = None


class PemesananResponse(BaseModel):
    """Header PO untuk list & summary."""
    model_config = ConfigDict(from_attributes=True)

    id_pemesanan: int
    nomor_po: str
    tgl_pemesanan: datetime
    tgl_perkiraan_datang: Optional[date] = None
    supplier_nama: Optional[str] = None
    status: str

    id_staf_pemesan: int
    nama_staf_pemesan: Optional[str] = None
    id_staf_approver: Optional[int] = None
    nama_staf_approver: Optional[str] = None
    tgl_approve: Optional[datetime] = None

    catatan: Optional[str] = None
    total_estimasi_biaya: Optional[Decimal] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PemesananDetailResponse(BaseModel):
    """Compound — header + items + history receives. Untuk halaman detail."""
    status: str = "success"
    pemesanan: PemesananResponse
    items: list[PemesananItemResponse] = Field(default_factory=list)
    history_receive: list[PemesananReceiveEventResponse] = Field(default_factory=list)
    jumlah_item: int = 0
    jumlah_item_complete: int = 0


# =============================================================================
# LIST RESPONSE
# =============================================================================
class PemesananListItem(BaseModel):
    """1 row untuk halaman list/antrian PO."""
    model_config = ConfigDict(from_attributes=True)

    id_pemesanan: int
    nomor_po: str
    tgl_pemesanan: datetime
    tgl_perkiraan_datang: Optional[date] = None
    supplier_nama: Optional[str] = None
    status: str

    nama_staf_pemesan: Optional[str] = None
    jumlah_item: int = 0
    total_estimasi_biaya: Optional[Decimal] = None


class PemesananListResponse(BaseModel):
    status: str = "success"
    total: int = 0
    data: list[PemesananListItem] = Field(default_factory=list)


# =============================================================================
# OPERATION RESPONSES
# =============================================================================
class PemesananCreateResponse(BaseModel):
    status: str = "success"
    message: str
    data: dict  # { id_pemesanan, nomor_po, jumlah_item, status }


class PemesananStatusUpdateResponse(BaseModel):
    status: str = "success"
    message: str
    data: dict  # { id_pemesanan, status_lama, status_baru }


class ReceiveItemResponse(BaseModel):
    status: str = "success"
    message: str
    data: dict
    # { id_receive, id_pemesanan, id_pemesanan_item, qty_diterima, qty_total_diterima,
    #   qty_dipesan, item_complete, status_pemesanan_baru, stok_sebelum, stok_sesudah }


__all__ = [
    # Request
    "PemesananItemCreate",
    "PemesananCreateRequest",
    "PemesananHeaderUpdate",
    "ReceiveItemRequest",
    # Response item-level
    "PemesananItemResponse",
    "PemesananReceiveEventResponse",
    # Response header-level
    "PemesananResponse",
    "PemesananDetailResponse",
    # List
    "PemesananListItem",
    "PemesananListResponse",
    # Operation
    "PemesananCreateResponse",
    "PemesananStatusUpdateResponse",
    "ReceiveItemResponse",
    # Stock Opname schemas (P5)
    "StockOpnameItemInput",
    "StockOpnameCreateRequest",
    "StockOpnameRejectRequest",
    "StockOpnameItemResponse",
    "StockOpnameResponse",
    "StockOpnameDetailResponse",
    "StockOpnameListItem",
    "StockOpnameListResponse",
    "StockOpnameCreateResponse",
    "StockOpnameApproveResponse",
]


# =============================================================================
# STOCK OPNAME — Request schemas
# =============================================================================
class StockOpnameItemInput(BaseModel):
    """1 baris item opname saat create — pelaksana input qty_fisik."""
    tipe_item: TipeItemEnum = Field(..., description="PRODUK atau BAHAN")
    id_produk: Optional[int] = Field(default=None, ge=1)
    id_bahan: Optional[int] = Field(default=None, ge=1)
    qty_fisik: float = Field(..., ge=0, description="Hasil cek fisik gudang/kabin")
    catatan_item: Optional[str] = Field(default=None, max_length=200)
    # P-L9 opname per-batch (PRODUK/RETAIL): id_lot lot yang dihitung.
    # id_lot None + batch_no/tgl_ed terisi = "batch baru ditemukan" → buat lot saat approve.
    id_lot: Optional[int] = Field(default=None, ge=1)
    batch_no: Optional[str] = Field(default=None, max_length=50)
    tgl_ed: Optional[date] = Field(default=None)

    @field_validator("id_produk", "id_bahan", "id_lot", mode="before")
    @classmethod
    def _normalize_empty_opname(cls, v):
        if v in (0, "", "0"):
            return None
        return v


class StockOpnameCreateRequest(BaseModel):
    """Request create opname baru — header + minimal 1 item."""
    lokasi: LokasiOpnameEnum = Field(..., description="KABIN / GUDANG_UTAMA / RETAIL")
    catatan: Optional[str] = Field(default=None, max_length=2000)
    items: list[StockOpnameItemInput] = Field(..., min_length=1)


class StockOpnameRejectRequest(BaseModel):
    """Request reject opname dengan alasan."""
    alasan: str = Field(..., min_length=3, max_length=500)


# =============================================================================
# STOCK OPNAME — Response schemas
# =============================================================================
class StockOpnameItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_opname_item: int
    tipe_item: str
    id_produk: Optional[int] = None
    id_bahan: Optional[int] = None
    nama_snapshot: str
    qty_sistem: float
    qty_fisik: float
    selisih: float = 0  # qty_fisik - qty_sistem (positive=lebih, negative=kurang)
    catatan_item: Optional[str] = None


class StockOpnameResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_opname: int
    nomor_opname: str
    tgl_opname: datetime
    lokasi: str
    status: str
    id_staf_pelaksana: int
    nama_staf_pelaksana: Optional[str] = None
    id_staf_approver: Optional[int] = None
    nama_staf_approver: Optional[str] = None
    tgl_approve: Optional[datetime] = None
    total_selisih_value: Optional[Decimal] = None
    catatan: Optional[str] = None
    created_at: Optional[datetime] = None


class StockOpnameDetailResponse(BaseModel):
    status: str = "success"
    opname: StockOpnameResponse
    items: list[StockOpnameItemResponse] = Field(default_factory=list)
    jumlah_item: int = 0
    jumlah_selisih_positif: int = 0   # qty_fisik > qty_sistem
    jumlah_selisih_negatif: int = 0   # qty_fisik < qty_sistem
    jumlah_match: int = 0             # qty_fisik == qty_sistem


class StockOpnameListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_opname: int
    nomor_opname: str
    tgl_opname: datetime
    lokasi: str
    status: str
    nama_staf_pelaksana: Optional[str] = None
    jumlah_item: int = 0
    total_selisih_value: Optional[Decimal] = None



class StockOpnameListResponse(BaseModel):
    status: str = "success"
    total: int = 0
    data: list[StockOpnameListItem] = Field(default_factory=list)


class StockOpnameCreateResponse(BaseModel):
    status: str = "success"
    message: str
    data: dict  # { id_opname, nomor_opname, jumlah_item, status, jumlah_selisih_*}


class StockOpnameApproveResponse(BaseModel):
    status: str = "success"
    message: str
    data: dict  # { id_opname, total_items_applied, total_selisih_qty, items_detail }
