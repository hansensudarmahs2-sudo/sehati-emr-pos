"""
Pydantic schemas untuk Master Produk CRUD.

Flow:
- GET    /produk?keyword=&tipe=&only_active=
- GET    /produk/{id}
- POST   /produk
- PUT    /produk/{id}
- PATCH  /produk/{id}/set-active
- PATCH  /produk/{id}/restock
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# CREATE
# =============================================================================
class MasterProdukCreate(BaseModel):
    """Request register produk baru."""
    kode_produk: str = Field(..., min_length=1, max_length=20)
    nama_produk: str = Field(..., min_length=1, max_length=100)
    tipe_produk: str = Field(..., description="RETAIL, CABIN, atau ALAT")
    satuan: str = Field(..., min_length=1, max_length=20)
    harga_jual: Decimal = Field(default=Decimal("0"), ge=0)

    # Produk topikal: kandungan boleh tampil; nama_dagang = merk asli (internal)
    kandungan: Optional[str] = Field(default=None, max_length=255)
    nama_dagang: Optional[str] = Field(default=None, max_length=100)
    golongan: Optional[str] = Field(default=None, max_length=50)

    # Stok awal (kalau langsung restock saat create)
    stok_terkini: float = Field(default=0, ge=0)
    stok_minimal: float = Field(default=5, ge=0)

    # Repacking dari bahan klinik (opsional)
    id_bahan_sumber: Optional[int] = Field(default=None, ge=1)
    qty_per_unit_produk: Optional[float] = Field(default=None, gt=0)

    # Member benefit
    eligible_member_discount: bool = False
    default_iterasi: int = Field(default=0, ge=0, description="Default iterasi resep (Phase 2)")

    # TODO-NEW-3 #31 — Auto-fill cara pakai di resep SOAP (opsional)
    default_cara_pakai: Optional[str] = Field(
        default=None, max_length=200,
        description="Default aturan pakai untuk auto-fill di resep SOAP dokter (mis. '3x1 sesudah makan').",
    )

    # KOMISI SYSTEM HYBRID (DEC-060) — opsional saat create
    hpp_per_unit: Optional[Decimal] = Field(default=None, ge=0)
    pajak_persen: Optional[Decimal] = Field(default=None, ge=0, le=100)
    pajak_nominal: Optional[Decimal] = Field(default=None, ge=0)
    komisi_dokter_tipe: Optional[str] = Field(default=None, description="PERSEN_HARGA / PERSEN_MARGIN / NOMINAL")
    komisi_dokter_value: Optional[Decimal] = Field(default=None, ge=0)


# =============================================================================
# UPDATE — semua field opsional, partial update
# =============================================================================
class MasterProdukUpdate(BaseModel):
    """Request update produk. Semua field opsional — partial update."""
    kode_produk: Optional[str] = Field(default=None, min_length=1, max_length=20)
    nama_produk: Optional[str] = Field(default=None, min_length=1, max_length=100)
    tipe_produk: Optional[str] = Field(default=None, description="RETAIL, CABIN, atau ALAT")
    satuan: Optional[str] = Field(default=None, min_length=1, max_length=20)
    harga_jual: Optional[Decimal] = Field(default=None, ge=0)
    stok_minimal: Optional[float] = Field(default=None, ge=0)

    # Produk topikal: kandungan boleh tampil; nama_dagang = merk asli (internal)
    kandungan: Optional[str] = Field(default=None, max_length=255)
    nama_dagang: Optional[str] = Field(default=None, max_length=100)
    golongan: Optional[str] = Field(default=None, max_length=50)

    id_bahan_sumber: Optional[int] = Field(default=None, ge=1)
    qty_per_unit_produk: Optional[float] = Field(default=None, gt=0)

    eligible_member_discount: Optional[bool] = None
    default_iterasi: Optional[int] = Field(default=None, ge=0)

    # TODO-NEW-3 #31 — Auto-fill cara pakai di resep SOAP (opsional)
    default_cara_pakai: Optional[str] = Field(default=None, max_length=200)

    # KOMISI SYSTEM HYBRID (DEC-060) — opsional saat update
    hpp_per_unit: Optional[Decimal] = Field(default=None, ge=0)
    pajak_persen: Optional[Decimal] = Field(default=None, ge=0, le=100)
    pajak_nominal: Optional[Decimal] = Field(default=None, ge=0)
    komisi_dokter_tipe: Optional[str] = Field(default=None, description="PERSEN_HARGA / PERSEN_MARGIN / NOMINAL")
    komisi_dokter_value: Optional[Decimal] = Field(default=None, ge=0)


# =============================================================================
# RESPONSE
# =============================================================================
class MasterProdukResponse(BaseModel):
    """Response untuk 1 produk."""
    model_config = ConfigDict(from_attributes=True)

    id_produk: int
    kode_produk: str
    nama_produk: str
    tipe_produk: Optional[str] = None
    satuan: str
    harga_jual: Optional[Decimal] = None

    stok_terkini: Optional[float] = None
    stok_minimal: Optional[float] = None

    id_bahan_sumber: Optional[int] = None
    qty_per_unit_produk: Optional[float] = None

    default_iterasi: int = 0
    eligible_member_discount: bool = False
    default_cara_pakai: Optional[str] = None  # TODO-NEW-3 #31 auto-fill resep SOAP
    kandungan: Optional[str] = None
    nama_dagang: Optional[str] = None
    golongan: Optional[str] = None
    is_active: Optional[bool] = None
    updated_at: Optional[datetime] = None


class MasterProdukListResponse(BaseModel):
    status: str = "success"
    total: int
    data: list[MasterProdukResponse]


# =============================================================================
# SET ACTIVE
# =============================================================================
class SetActiveProdukRequest(BaseModel):
    is_active: bool


# =============================================================================
# RESTOCK — tambah stok dari supplier
# =============================================================================
class RestockProdukRequest(BaseModel):
    """Tambah stok produk (restock dari supplier)."""
    qty_tambah: float = Field(..., gt=0, description="Qty yang ditambahkan ke stok")
    catatan: Optional[str] = Field(default=None, max_length=200)


# =============================================================================
# GENERIC RESPONSES (wrapper untuk endpoint API)
# =============================================================================
class ProdukGenericResponse(BaseModel):
    """Generic wrapper untuk response endpoint produk (set-active, dll)."""
    status: str = "success"
    message: str
    data: Optional[MasterProdukResponse] = None


class RestockProdukResponse(BaseModel):
    """Response setelah restock produk."""
    status: str = "success"
    message: str
    id_produk: int
    qty_tambah: float
    stok_baru: float
