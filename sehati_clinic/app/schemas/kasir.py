"""
Pydantic schemas untuk KasirService.

Pattern flow:
- GET /kasir/antrian               → list pasien ANTRI_BAYAR hari ini + riwayat hari ini
- GET /kasir/tagihan/{id_kunjungan} → auto-hitung tagihan (treatment + produk - diskon)
- POST /kasir/bayar                → execute pembayaran (split payment ready)
- POST /kasir/void-item            → void resep dengan PIN dokter/admin
- GET /kasir/rekap-shift           → rekap shift kasir (sejak login)
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# ANTRIAN KASIR
# =============================================================================
class AntrianKasirItem(BaseModel):
    """1 baris pasien yang siap dibayar."""
    model_config = ConfigDict(from_attributes=True)

    id_kunjungan: int
    nomor_antrean: Optional[int] = None
    tgl_kunjungan: Optional[datetime] = None
    status_antrian: Optional[str] = None

    id_pasien: int
    no_rm: str
    nama_pasien: str
    tipe_membership: Optional[str] = None

    # Quick info
    jumlah_tindakan: int = 0
    jumlah_resep: int = 0

    # Asal resep — kasir perlu tahu ini BUKAN konsultasi biasa, terutama untuk
    # resep luar (tidak ada komisi dokter) dan tebus lanjut (resep lama).
    jenis_kunjungan: Optional[str] = "KLINIS"
    peresep_luar_nama: Optional[str] = None


class RiwayatBayarItem(BaseModel):
    """1 baris transaksi yang sudah lunas hari ini — untuk akses cetak nota."""
    model_config = ConfigDict(from_attributes=True)

    id_transaksi: int
    id_kunjungan: Optional[int] = None  # M2: NULL utk transaksi MEMBERSHIP
    jenis_transaksi: Optional[str] = "KLINIS"
    waktu_bayar: Optional[datetime] = None

    id_pasien: int
    no_rm: str
    nama_pasien: str

    total_bayar: Decimal
    nama_kasir: Optional[str] = None


class MembershipPendingItem(BaseModel):
    """1 membership PENDING menunggu pembayaran (transaksi terpisah dari klinis)."""
    model_config = ConfigDict(from_attributes=True)

    id_history: int
    id_pasien: int
    no_rm: str
    nama_pasien: str
    tipe_membership_sekarang: Optional[str] = None  # tier aktif pasien saat ini
    nama_tier: str                                   # tier yg dibeli (PENDING)
    harga_aktivasi: Decimal = Decimal("0")


class AntrianKasirResponse(BaseModel):
    status: str = "success"
    tanggal: date
    total: int
    data: list[AntrianKasirItem]
    # Riwayat transaksi hari ini — untuk akses tombol Cetak Nota pasca-bayar
    riwayat: list[RiwayatBayarItem] = Field(default_factory=list)
    riwayat_total: int = 0
    # M2: membership PENDING menunggu bayar (transaksi terpisah)
    membership_pending: list[MembershipPendingItem] = Field(default_factory=list)
    membership_pending_total: int = 0


# =============================================================================
# TAGIHAN — auto-hitung
# =============================================================================
class RincianTindakan(BaseModel):
    """1 baris tindakan di tagihan."""
    id_kunjungan_tindakan: int
    id_treatment: int
    nama_treatment: str
    harga: Decimal
    pakai_kuota_member: bool = False     # kalau pakai kuota, harga jadi 0 untuk tagihan


class RincianProduk(BaseModel):
    """1 baris produk di tagihan."""
    id_resep: int
    id_produk: int
    nama_produk: str
    qty: float
    harga_satuan: Decimal
    subtotal: Decimal
    status_item: Optional[str] = None    # PENDING / BATAL / DIBAYAR


class RincianRacikanBahan(BaseModel):
    """1 bahan di dalam racikan — dipakai apotek untuk memotong stok."""
    id_produk: Optional[int] = None       # NULL = bahan non-inventori
    nama: str
    dipakai: float                        # butir (mode MG, sudah CEIL) atau gram (GRAM)
    satuan_dipakai: str


class RincianRacikan(BaseModel):
    """1 baris racikan di tagihan. Harga sudah DIKUNCI sejak dokter simpan SOAP."""
    id_kunjungan_racikan: int
    nama: str
    jenis_racik: str
    jumlah_unit: int
    aturan_pakai: Optional[str] = None
    subtotal_bahan: Decimal
    biaya_racik: Decimal
    total: Decimal                        # subtotal_bahan + biaya_racik (sebelum diskon)
    status_item: Optional[str] = None     # PENDING / DIBAYAR / BATAL
    bahan: list[RincianRacikanBahan] = Field(default_factory=list)


class RingkasanBiaya(BaseModel):
    subtotal_tindakan: Decimal
    subtotal_produk: Decimal
    subtotal_racikan: Decimal = Decimal("0")
    # #362D - Aktivasi membership (kalau ada pending history utk pasien ini)
    subtotal_aktivasi_membership: Decimal = Decimal("0")
    nama_tier_aktivasi: Optional[str] = None  # mis. "VIP" / "VVIP" untuk display
    id_membership_aktivasi_pending: Optional[int] = None  # FK master_membership
    id_history_pending: Optional[int] = None  # FK pasien_membership_history (untuk update saat bayar)
    subtotal: Decimal                    # tindakan + produk + aktivasi
    persen_diskon_treatment: Decimal
    persen_diskon_produk: Decimal
    nominal_diskon_treatment: Decimal
    nominal_diskon_produk: Decimal
    # Racikan memakai PERSEN produk, tapi dikenakan ke SELURUH total racikan
    # (bahan + ongkos racik) — keputusan dr. Hansen 2026-09-21.
    nominal_diskon_racikan: Decimal = Decimal("0")
    nominal_diskon_total: Decimal
    total_tagihan: Decimal               # subtotal − diskon


class TagihanResponse(BaseModel):
    """
    Auto-hitung tagihan untuk kunjungan. Idempotent — kalau sudah ada
    transaksi_kasir untuk id_kunjungan ini, return informasi LUNAS dengan
    total_tagihan = 0 (anti-duplicate billing).
    """
    status: str = "success"
    message: str = ""

    id_kunjungan: int
    nama_pasien: str
    no_rm: str
    tipe_membership: Optional[str] = None

    sudah_lunas: bool = False
    waktu_bayar: Optional[datetime] = None
    id_transaksi_existing: Optional[int] = None

    # Phase 4 (#364 DEC-063): Display VOID info kalau transaksi sudah di-void
    is_voided: bool = False
    void_at: Optional[datetime] = None
    void_reason_code: Optional[str] = None
    void_reason_note: Optional[str] = None
    voided_by_nama: Optional[str] = None
    late_void: bool = False

    # Phase 7 (#364 DEC-063): Force past-day void eligibility
    # Admin=3 days, Superadmin/Owner=7 days max
    can_force_void_past_day: bool = False
    days_past: int = 0
    max_force_days: int = 0

    rincian_tindakan: list[RincianTindakan] = Field(default_factory=list)
    rincian_produk: list[RincianProduk] = Field(default_factory=list)
    rincian_racikan: list[RincianRacikan] = Field(default_factory=list)
    ringkasan_biaya: RingkasanBiaya


# =============================================================================
# BAYAR — split payment ready
# =============================================================================
class PembayaranItem(BaseModel):
    """1 metode pembayaran (split payment ready)."""
    metode_bayar: str = Field(..., max_length=50, description="TUNAI / QRIS / DEBIT / KREDIT / TRANSFER")
    nominal: Decimal = Field(..., gt=0)


class BayarRequest(BaseModel):
    """
    Eksekusi pembayaran. Frontend kirim id_kunjungan + list pembayaran.

    Backend re-validasi total tagihan (jangan trust frontend),
    pastikan total nominal pembayaran >= total_tagihan.
    """
    id_kunjungan: int = Field(..., ge=1)
    pembayaran: list[PembayaranItem] = Field(default_factory=list)  # Boleh kosong kalau total_tagihan=0 (series sesi 2..N lunas)
    keterangan_promo: str = Field(default="", max_length=100)
    # P0-2: token intent pembayaran per-submit (dari form kasir). Double-click/retry
    # mengirim token sama → ditolak UNIQUE. Split billing = render baru = token baru.
    idempotency_key: Optional[str] = Field(default=None, max_length=64)


class BayarResponse(BaseModel):
    status: str = "success"
    message: str
    data: dict  # { id_transaksi, total_tagihan, total_bayar, kembalian, status_kunjungan_baru }


# =============================================================================
# VOID ITEM — butuh PIN dokter/admin (per DEC pattern upsell)
# =============================================================================
class VoidItemRequest(BaseModel):
    """Void 1 item resep — Phase 1 kasir self-acc + reason note + audit log.

    DEC-063 (#364 SYNC-V1, 10 Juni 2026): Disamakan dengan Void Transaksi.
    Tidak ada PIN authorization saat ini. Schema PIN/TOKEN dibawa ke Phase 2.
    """
    id_resep: int = Field(..., ge=1)
    reason_code: str = Field(..., description="Salah satu dari 6 enum VoidReasonEnum")
    alasan: str = Field(..., min_length=3, max_length=200, description="Catatan bebas penjelasan void")


class VoidItemResponse(BaseModel):
    status: str = "success"
    message: str
    data: dict  # { id_resep, status_item_baru, voided_by, waktu_void }


# =============================================================================
# REKAP SHIFT
# =============================================================================
class RekapShiftItem(BaseModel):
    """1 transaksi di rekap shift."""
    model_config = ConfigDict(from_attributes=True)
    id_transaksi: int
    waktu_bayar: Optional[datetime] = None
    nama_pasien: str
    total_tagihan: Decimal


class RekapPerMetode(BaseModel):
    metode_bayar: str
    jumlah_transaksi: int
    total_nominal: Decimal


class RekapShiftResponse(BaseModel):
    """Rekap shift kasir sejak login (`waktu_mulai_shift` di master_staf)."""
    status: str = "success"
    id_staf_kasir: int
    nama_kasir: str
    waktu_mulai_shift: Optional[datetime] = None
    waktu_rekap: datetime
    total_transaksi: int = 0
    total_omzet: Decimal = Decimal("0")
    per_metode: list[RekapPerMetode] = Field(default_factory=list)
    daftar_transaksi: list[RekapShiftItem] = Field(default_factory=list)


__all__ = [
    "AntrianKasirItem", "AntrianKasirResponse", "RiwayatBayarItem",
    "RincianTindakan", "RincianProduk", "RingkasanBiaya", "TagihanResponse",
    "PembayaranItem", "BayarRequest", "BayarResponse",
    "VoidItemRequest", "VoidItemResponse",
    "RekapShiftItem", "RekapPerMetode", "RekapShiftResponse",
]
