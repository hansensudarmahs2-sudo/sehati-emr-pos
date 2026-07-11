"""
Reusable enums — match persis dengan ENUM di MySQL.

Letakkan SEMUA enum di sini supaya:
1. Tidak duplikasi di banyak file model.
2. Mudah dicari & di-update kalau ada perubahan business rule.
3. Bisa di-import oleh service/schema layer juga.

PENTING: nilai enum di Python HARUS sama dengan ENUM di DB (case-sensitive).
"""

import enum


# ---------------------------------------------------------------------------
# Staff
# ---------------------------------------------------------------------------
class StafRoleEnum(str, enum.Enum):
    """Role staf — sesuai ENUM di master_staf.role."""
    OWNER = "Owner"
    DOKTER = "Dokter"
    PERAWAT = "Perawat"
    APOTEKER = "Apoteker"
    KASIR = "Kasir"
    FO = "FO"
    ADMIN = "Admin"
    SUPERADMIN = "Superadmin"
    PURCHASING = "Purchasing"  # Ditambah di migrasi 006 (DEC-038) untuk modul Pengadaan


# ---------------------------------------------------------------------------
# Pasien
# ---------------------------------------------------------------------------
class GenderEnum(str, enum.Enum):
    """Jenis kelamin — sesuai ENUM di pasien.jenis_kelamin."""
    LAKI_LAKI = "L"
    PEREMPUAN = "P"


class MembershipTierEnum(str, enum.Enum):
    """Tier membership di pasien.tipe_membership.

    Catatan: enum ini cuma untuk validasi cepat. Source of truth tier
    sebenarnya ada di tabel master_membership.
    """
    REGULAR = "REGULAR"
    VIP = "VIP"
    VVIP = "VVIP"


class VerifikasiEnum(str, enum.Enum):
    """Status verifikasi pasien — pasien.status_verifikasi."""
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"


class TingkatKeparahanAlergiEnum(str, enum.Enum):
    """Tingkat keparahan alergi — pasien_alergi.tingkat_keparahan."""
    RINGAN = "Ringan"
    SEDANG = "Sedang"
    BERAT = "Berat"


# ---------------------------------------------------------------------------
# Booking & Kunjungan
# ---------------------------------------------------------------------------
class StatusBookingEnum(str, enum.Enum):
    """Status booking — jadwal_booking.status_booking."""
    BOOKED = "BOOKED"
    CONFIRMED = "CONFIRMED"
    RESCHEDULED = "RESCHEDULED"
    CANCELLED = "CANCELLED"
    CHECKED_IN = "CHECKED_IN"


class StatusAntrianEnum(str, enum.Enum):
    """
    Status antrian pasien — kunjungan.status_antrian.

    Alur normal:
        ANTRI_KONSULTASI → KONSULTASI → ANTRI_TREATMENT → ON_TREATMENT →
        ANTRI_BAYAR → ANTRI_OBAT → COMPLETED

    BATAL bisa dari status apa pun (hanya FO/Owner/Superadmin).

    Catatan: kolom DB-nya VARCHAR(50) bukan ENUM (untuk fleksibilitas).
    Enum ini untuk validasi di application layer.
    """
    ANTRI_KONSULTASI = "ANTRI_KONSULTASI"
    KONSULTASI = "KONSULTASI"
    ANTRI_TREATMENT = "ANTRI_TREATMENT"
    ON_TREATMENT = "ON_TREATMENT"
    ANTRI_BAYAR = "ANTRI_BAYAR"
    ANTRI_OBAT = "ANTRI_OBAT"
    COMPLETED = "COMPLETED"
    BATAL = "BATAL"


# ---------------------------------------------------------------------------
# Tindakan & Treatment
# ---------------------------------------------------------------------------
class StatusTindakanEnum(str, enum.Enum):
    """Status tindakan di ruang treatment — kunjungan_tindakan.status_tindakan."""
    PENDING = "PENDING"
    PROSES = "PROSES"
    SELESAI = "SELESAI"


class StatusItemResepEnum(str, enum.Enum):
    """Status item resep — kunjungan_resep.status_item."""
    PENDING = "PENDING"
    BATAL = "BATAL"
    DIBAYAR = "DIBAYAR"


class StatusRencanaTreatmentEnum(str, enum.Enum):
    """Status rencana series treatment — pasien_rencana_treatment.status."""
    PENDING = "PENDING"
    SCHEDULED = "SCHEDULED"
    DONE = "DONE"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class SumberRencanaEnum(str, enum.Enum):
    """Sumber series treatment — pasien_rencana_treatment.sumber_rencana."""
    DOKTER_PLAN = "DOKTER_PLAN"
    MEMBERSHIP = "MEMBERSHIP"
    PROMO = "PROMO"


# ---------------------------------------------------------------------------
# Inventory & Produk
# ---------------------------------------------------------------------------
class TipeProdukEnum(str, enum.Enum):
    """Tipe produk — master_produk.tipe_produk."""
    RETAIL = "RETAIL"
    CABIN = "CABIN"
    ALAT = "ALAT"


class JenisMutasiEnum(str, enum.Enum):
    """Jenis mutasi stok — inventory_history.jenis_mutasi."""
    TINDAKAN = "TINDAKAN"
    PENJUALAN = "PENJUALAN"
    RESTOCK = "RESTOCK"
    EXPIRED = "EXPIRED"
    RUSAK = "RUSAK"
    PENYESUAIAN = "PENYESUAIAN"


class KategoriKomponenTreatmentEnum(str, enum.Enum):
    """Kategori komponen treatment — treatment_komponen.kategori."""
    BAHAN = "BAHAN"
    ALAT = "ALAT"


# ---------------------------------------------------------------------------
# Foto
# ---------------------------------------------------------------------------
class KategoriFotoEnum(str, enum.Enum):
    """Kategori foto pasien — kunjungan_foto.kategori."""
    BEFORE = "BEFORE"
    AFTER = "AFTER"
    PROGRESS = "PROGRESS"


# ---------------------------------------------------------------------------
# Membership Benefit
# ---------------------------------------------------------------------------
class PeriodeKuotaEnum(str, enum.Enum):
    """Periode kuota benefit — master_membership_benefit_treatment.periode_kuota."""
    BULANAN = "BULANAN"
    TOTAL_PAKET = "TOTAL_PAKET"


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------
class StatusAksiAuditEnum(str, enum.Enum):
    """Status aksi audit — audit_log.status_aksi.

    Hanya 2 nilai: SUCCESS (aksi berhasil) atau FAILED (aksi gagal).
    Detail aksi disimpan di kolom audit_log.aksi (string bebas, mis. "CREATE_PASIEN").
    """
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


# ---------------------------------------------------------------------------
# Pengadaan / Purchase Order (DEC-038, migrasi 006)
# ---------------------------------------------------------------------------
class StatusPemesananEnum(str, enum.Enum):
    """Status PO — pemesanan.status."""
    SUBMITTED = "SUBMITTED"               # Draft, bisa edit/cancel
    ORDERED = "ORDERED"                   # Locked, supplier dihubungi
    PARTIAL_RECEIVED = "PARTIAL_RECEIVED" # Sebagian sudah diterima
    RECEIVED = "RECEIVED"                 # Closed
    CANCELLED = "CANCELLED"


class StatusOpnameEnum(str, enum.Enum):
    """Status stock opname — stock_opname.status."""
    DRAFT = "DRAFT"          # Belum apply ke stok
    APPROVED = "APPROVED"    # Selisih sudah terapan
    REJECTED = "REJECTED"


class LokasiOpnameEnum(str, enum.Enum):
    """Lokasi stok untuk opname — stock_opname.lokasi.

    KABIN = stok yang ada di kabin/treatment room (untuk BHP)
    GUDANG_UTAMA = stok di gudang utama (untuk bahan)
    RETAIL = stok produk retail (master_produk.stok_terkini) — dijual via POS
    """
    KABIN = "KABIN"
    GUDANG_UTAMA = "GUDANG_UTAMA"
    RETAIL = "RETAIL"  # FIX: service/schema/opname_repo sudah pakai RETAIL, enum ketinggalan


class TipeItemEnum(str, enum.Enum):
    """Tipe item polymorphic — pemesanan_item.tipe_item, stock_opname_item.tipe_item, inventory_history.tipe_item."""
    PRODUK = "PRODUK"  # → master_produk
    BAHAN = "BAHAN"    # → inventory_stok




# =============================================================================
# Void Pembayaran (DEC-063, #364) — Phase 1
# =============================================================================
class StatusTransaksiEnum(str, enum.Enum):
    """Status transaksi_kasir — DEC-063."""
    BAYAR = "BAYAR"    # Sudah dibayar (default)
    VOID = "VOID"      # Sudah di-void


class VoidReasonEnum(str, enum.Enum):
    """Reason code untuk void transaksi — DEC-063.

    Enum stabil — jangan ganti value nanti (historical data break).
    """
    SALAH_INPUT = "SALAH_INPUT"
    CUSTOMER_CANCEL = "CUSTOMER_CANCEL"
    REFUND_PASCA_TINDAKAN = "REFUND_PASCA_TINDAKAN"
    ITEM_RUSAK = "ITEM_RUSAK"
    DUPLICATE_TRANSAKSI = "DUPLICATE_TRANSAKSI"
    OTHER = "OTHER"


class VoidApprovalMethodEnum(str, enum.Enum):
    """Cara approval void — Phase 1 selalu SELF, Phase 2 add PIN/TOKEN/QUEUE."""
    SELF = "SELF"      # Phase 1: kasir self-acc
    PIN = "PIN"        # Phase 2: authorizer enter PIN
    TOKEN = "TOKEN"    # Phase 2: one-time token
    QUEUE = "QUEUE"    # Phase 2: in-app approval queue


# ---------------------------------------------------------------------------
# Follow-up reminder (2026-07-08) — modul #7
# ---------------------------------------------------------------------------
class JenisFollowupEnum(str, enum.Enum):
    """Jenis follow-up — followup.jenis."""
    KONSULTASI = "KONSULTASI"
    TREATMENT = "TREATMENT"


class StatusFollowupEnum(str, enum.Enum):
    """Status follow-up — followup.status (workflow 4-state + PENDING awal)."""
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    RESCHEDULED = "RESCHEDULED"
    NO_ANSWER = "NO_ANSWER"
    CANCELLED = "CANCELLED"
