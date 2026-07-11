"""
Pydantic schemas untuk Reports module.

Phase 1 scope:
- GET /reports/omzet-harian?tanggal=YYYY-MM-DD
  → total transaksi, omzet, per kasir, per metode bayar
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


# =============================================================================
# OMZET HARIAN
# =============================================================================
class OmzetPerKasir(BaseModel):
    """Breakdown omzet per kasir untuk tanggal tertentu."""
    id_staf_kasir: int
    nama_kasir: str
    jumlah_transaksi: int
    total_omzet: Decimal


class OmzetPerMetode(BaseModel):
    """Breakdown omzet per metode pembayaran."""
    metode_bayar: str
    jumlah_pembayaran: int
    total_nominal: Decimal


class OmzetHarianResponse(BaseModel):
    """Rekap omzet harian — total + breakdown per kasir + per metode."""
    status: str = "success"
    tanggal: date
    waktu_rekap: datetime

    total_transaksi: int = 0
    total_omzet: Decimal = Decimal("0")
    total_diskon: Decimal = Decimal("0")
    rata_per_transaksi: Decimal = Decimal("0")

    per_kasir: list[OmzetPerKasir] = Field(default_factory=list)
    per_metode: list[OmzetPerMetode] = Field(default_factory=list)


# =============================================================================
# OMZET BULANAN
# =============================================================================
class OmzetPerBulan(BaseModel):
    """1 row per bulan dalam rentang."""
    tahun: int
    bulan: int  # 1-12
    bulan_label: str  # "Jan 2026"
    jumlah_transaksi: int
    total_omzet: Decimal
    total_diskon: Decimal
    rata_per_transaksi: Decimal


class OmzetBulananResponse(BaseModel):
    """Rekap omzet bulanan untuk rentang tahun+bulan tertentu."""
    status: str = "success"
    tahun: int
    bulan_dari: int
    bulan_sampai: int
    waktu_rekap: datetime

    # KPI summary rentang
    total_transaksi: int = 0
    total_omzet: Decimal = Decimal("0")
    total_diskon: Decimal = Decimal("0")
    rata_per_bulan: Decimal = Decimal("0")
    peak_bulan_label: str = ""  # bulan dengan omzet tertinggi
    peak_bulan_omzet: Decimal = Decimal("0")

    per_bulan: list[OmzetPerBulan] = Field(default_factory=list)
    per_metode: list[OmzetPerMetode] = Field(default_factory=list)


# =============================================================================
# TOP TREATMENT
# =============================================================================
class TopTreatmentItem(BaseModel):
    """1 row per treatment dengan ranking + omzet."""
    rank: int
    id_treatment: int
    nama_treatment: str
    role_pelaksana: str
    harga_satuan: Decimal
    jumlah_dilakukan: int
    estimasi_omzet: Decimal
    persen_kontribusi: float  # 0-100, dari total omzet rentang


class TopTreatmentResponse(BaseModel):
    """Ranking treatment paling sering + paling profitable dalam rentang tanggal."""
    status: str = "success"
    tgl_dari: date
    tgl_sampai: date
    status_filter: str  # "SELESAI" | "ALL"
    waktu_rekap: datetime

    # KPI summary rentang
    total_tindakan: int = 0
    total_estimasi_omzet: Decimal = Decimal("0")
    paling_laris_label: str = ""
    paling_laris_count: int = 0
    paling_profitable_label: str = ""
    paling_profitable_omzet: Decimal = Decimal("0")

    items: list[TopTreatmentItem] = Field(default_factory=list)


# =============================================================================
# KINERJA DOKTER
# =============================================================================
class KinerjaDokterItem(BaseModel):
    """1 row per dokter dengan stats kinerja."""
    rank: int
    id_staf: int
    nama_dokter: str
    pasien_unique: int
    jumlah_konsul: int
    konsul_dengan_tindakan: int  # konsul yang follow-up jadi tindakan
    jumlah_tindakan: int
    estimasi_omzet: Decimal
    conversion_rate: float  # konsul_dengan_tindakan / jumlah_konsul × 100


class KinerjaDokterResponse(BaseModel):
    """Ranking kinerja dokter dalam rentang tanggal."""
    status: str = "success"
    tgl_dari: date
    tgl_sampai: date
    waktu_rekap: datetime

    total_dokter: int = 0
    total_konsul: int = 0
    total_tindakan: int = 0
    total_estimasi_omzet: Decimal = Decimal("0")
    top_omzet_label: str = ""
    top_omzet_value: Decimal = Decimal("0")

    items: list[KinerjaDokterItem] = Field(default_factory=list)


# =============================================================================
# AUDIT LOG VIEWER
# =============================================================================
class AuditLogItem(BaseModel):
    """1 row audit log."""
    id_log: int
    waktu: datetime
    id_staf: int | None = None
    nama_staf: str | None = None
    role_staf: str | None = None
    aksi: str
    tabel_target: str | None = None
    id_target: int | None = None
    status_aksi: str
    keterangan: str | None = None
    data_lama: dict | None = None
    data_baru: dict | None = None


class AuditLogResponse(BaseModel):
    """Paginated audit log result + filter info."""
    status: str = "success"
    tgl_dari: date
    tgl_sampai: date
    filter_id_staf: int | None = None
    filter_aksi: str | None = None
    filter_tabel: str | None = None
    filter_status: str | None = None
    waktu_rekap: datetime

    # Pagination
    total_count: int = 0
    page: int = 1
    page_size: int = 100
    total_pages: int = 1

    items: list[AuditLogItem] = Field(default_factory=list)


# =============================================================================
# Phase 6 (#364 DEC-063) — Void Report
# =============================================================================
class VoidReportItem(BaseModel):
    """1 baris void transaksi untuk laporan."""
    id_transaksi: int
    id_kunjungan: int | None = None
    no_rm: str
    nama_pasien: str
    waktu_bayar: datetime | None = None
    void_at: datetime | None = None
    total_tagihan: float = 0
    void_reason_code: str | None = None
    void_reason_note: str | None = None
    void_approval_method: str | None = None
    late_void: bool = False
    kasir_nama: str | None = None
    voider_nama: str | None = None


class VoidReportResponse(BaseModel):
    """Paginated void report dengan summary stats."""
    status: str = "success"
    tgl_dari: date
    tgl_sampai: date
    filter_kasir_id: int | None = None
    filter_voider_id: int | None = None
    filter_reason: str | None = None
    waktu_rekap: datetime

    # Summary
    total_count: int = 0
    total_nominal: float = 0
    late_void_count: int = 0

    # Pagination
    page: int = 1
    page_size: int = 100
    total_pages: int = 1

    items: list[VoidReportItem] = Field(default_factory=list)


# =============================================================================
# #363B - Apoteker Resep Dispensed Report
# =============================================================================
class ApotekerDispensedItem(BaseModel):
    """1 baris resep item yang diserahkan apoteker."""
    id_kunjungan: int
    id_resep: int
    id_produk: int
    kode_produk: str
    nama_produk: str
    qty: float
    harga_satuan: float
    subtotal: float
    aturan_pakai: str | None = None
    waktu_serah: datetime | None = None
    no_rm: str
    nama_pasien: str
    apoteker_nama: str
    id_staf_apoteker: int


class ApotekerSummaryPerStaf(BaseModel):
    """Summary breakdown per apoteker."""
    id_staf_apoteker: int
    apoteker_nama: str
    total_resep_item: int
    total_kunjungan: int
    total_qty: float
    total_nominal: float


class ApotekerDispensedResponse(BaseModel):
    """Paginated rekap resep dispensed apoteker."""
    status: str = "success"
    tgl_dari: date
    tgl_sampai: date
    filter_apoteker_id: int | None = None
    waktu_rekap: datetime

    # Summary
    total_kunjungan: int = 0
    total_resep_item: int = 0
    total_qty: float = 0
    total_nominal: float = 0

    # Per-apoteker breakdown
    per_apoteker: list[ApotekerSummaryPerStaf] = Field(default_factory=list)

    # Pagination
    page: int = 1
    page_size: int = 100
    total_pages: int = 1

    items: list[ApotekerDispensedItem] = Field(default_factory=list)


# =============================================================================
# #363C - Write-off Produk Report
# =============================================================================
class WriteOffReportItem(BaseModel):
    """1 baris write-off produk."""
    id_log: int
    waktu: datetime | None = None
    id_produk: int
    kode_produk: str
    nama_produk: str
    jenis_mutasi: str  # EXPIRED / RUSAK / PENYESUAIAN
    qty_dibuang: float
    hpp_per_unit: float
    nominal_loss: float
    stok_sebelum: float
    stok_sesudah: float
    id_staf_apoteker: int
    apoteker_nama: str
    keterangan: str | None = None


class WriteOffSummaryPerJenis(BaseModel):
    """Breakdown per jenis mutasi."""
    jenis_mutasi: str
    count: int
    total_qty: float
    total_nominal_loss: float


class WriteOffReportResponse(BaseModel):
    """Paginated write-off report dengan summary."""
    status: str = "success"
    tgl_dari: date
    tgl_sampai: date
    filter_apoteker_id: int | None = None
    filter_jenis_mutasi: str | None = None
    waktu_rekap: datetime

    # Summary
    total_count: int = 0
    total_qty: float = 0
    total_nominal_loss: float = 0

    # Breakdown
    per_jenis: list[WriteOffSummaryPerJenis] = Field(default_factory=list)

    # Pagination
    page: int = 1
    page_size: int = 100
    total_pages: int = 1

    items: list[WriteOffReportItem] = Field(default_factory=list)


# =============================================================================
# #363D - Top Dispensed Products
# =============================================================================
class TopProdukItem(BaseModel):
    """1 produk dalam ranking top dispensed."""
    rank: int
    id_produk: int
    kode_produk: str
    nama_produk: str
    tipe_produk: str | None = None
    satuan: str
    total_qty: float
    total_dispensed_count: int  # jumlah kali muncul di resep DIBAYAR
    total_unique_kunjungan: int
    total_nominal: float
    avg_qty_per_kunjungan: float
    harga_satuan: float
    stok_terkini: float


class TopProdukResponse(BaseModel):
    """Top N produk dispensed dalam rentang tanggal."""
    status: str = "success"
    tgl_dari: date
    tgl_sampai: date
    limit: int = 50
    sort_by: str = "qty"  # qty | nominal | count
    waktu_rekap: datetime

    total_unique_produk: int = 0
    total_dispensing_events: int = 0
    total_nominal: float = 0

    items: list[TopProdukItem] = Field(default_factory=list)


__all__ = [
    "OmzetPerKasir", "OmzetPerMetode", "OmzetHarianResponse",
    "OmzetPerBulan", "OmzetBulananResponse",
    "TopTreatmentItem", "TopTreatmentResponse",
    "KinerjaDokterItem", "KinerjaDokterResponse",
    "AuditLogItem", "AuditLogResponse",
    "VoidReportItem", "VoidReportResponse",
    "ApotekerDispensedItem", "ApotekerSummaryPerStaf", "ApotekerDispensedResponse",
    "WriteOffReportItem", "WriteOffSummaryPerJenis", "WriteOffReportResponse",
    "TopProdukItem", "TopProdukResponse",
]
