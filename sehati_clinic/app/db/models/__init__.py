"""
SQLAlchemy ORM models — 1 file per domain.

Pattern: import semua models di sini supaya:
1. Base.metadata aware tentang semua tabel (untuk Alembic autogenerate).
2. Aplikasi bisa import sederhana: `from app.db.models import Pasien`.

Saat tambah model baru:
1. Buat file di app/db/models/<domain>.py
2. Tambah import-nya di sini
3. Tambah ke __all__ list di bawah
"""

# Enum (re-export untuk convenience)
from app.db.models._enums import (
    GenderEnum,
    JenisFollowupEnum,
    JenisMutasiEnum,
    KategoriFotoEnum,
    KategoriKomponenTreatmentEnum,
    LokasiOpnameEnum,
    MembershipTierEnum,
    PeriodeKuotaEnum,
    StafRoleEnum,
    StatusAksiAuditEnum,
    StatusAntrianEnum,
    StatusAktivasiEnum,
    StatusBookingEnum,
    StatusFollowupEnum,
    StatusItemResepEnum,
    StatusOpnameEnum,
    StatusPemesananEnum,
    StatusRencanaTreatmentEnum,
    StatusTindakanEnum,
    StatusTransaksiEnum,
    SumberRencanaEnum,
    TingkatKeparahanAlergiEnum,
    TipeItemEnum,
    TipeProdukEnum,
    VerifikasiEnum,
    VoidApprovalMethodEnum,
    VoidReasonEnum,
)

# Models — staf & pasien
from app.db.models.staf import MasterStaf
from app.db.models.pasien import (
    MasterPenyakitKronis,
    Pasien,
    PasienAlergi,
    PasienPenyakitKronis,
)

# Models — booking & kunjungan
from app.db.models.booking import JadwalBooking
from app.db.models.kunjungan import (
    Kunjungan,
    KunjunganAntropometri,
    KunjunganFoto,
    KunjunganResep,
    KunjunganTindakan,
    PemeriksaanKlinis,
)
from app.db.models.followup import Followup

# Models — treatment & inventory
from app.db.models.treatment import (
    MasterTreatment,
    PasienRencanaTreatment,
    PasienResepIterasi,
    TreatmentKomponen,
)
from app.db.models.inventory import InventoryHistory, InventoryStok
from app.db.models.produk import MasterProduk
from app.db.models.klinik_config import KlinikApoteker, MasterKlinikConfig

# Models — pengadaan (PO + stock opname, DEC-038/039/040)
from app.db.models.pengadaan import (
    Pemesanan,
    PemesananItem,
    PemesananReceive,
    StockOpname,
    StockOpnameItem,
)

# Models — transaksi
from app.db.models.transaksi import (
    KasirClosing,
    TransaksiDetailProduk,
    TransaksiDetailTindakan,
    TransaksiKasir,
    TransaksiPembayaran,
    TransaksiRefund,
)

# Models — membership
from app.db.models.membership import (
    MasterMembership,
    MasterMembershipBenefitTreatment,
    PasienMembershipHistory,
    PasienMembershipKuota,
)

# Models — audit
from app.db.models.audit import AuditLog
from app.db.models.komisi import KomisiLedger
from app.db.models.distributor import MasterDistributor
from app.db.models.lokasi_pengiriman import LokasiPengiriman
from app.db.models.faktur import FakturPenerimaan
from app.db.models.retur import ReturProduk, ReturProdukItem
from app.db.models.stok_lot import StokLot, KunjunganLotTerpakai


__all__ = [
    # ----- Enums -----
    "GenderEnum",
    "JenisFollowupEnum",
    "JenisMutasiEnum",
    "KategoriFotoEnum",
    "KategoriKomponenTreatmentEnum",
    "LokasiOpnameEnum",
    "MembershipTierEnum",
    "PeriodeKuotaEnum",
    "StafRoleEnum",
    "StatusAksiAuditEnum",
    "StatusAntrianEnum",
    "StatusAktivasiEnum",
    "StatusBookingEnum",
    "StatusFollowupEnum",
    "StatusItemResepEnum",
    "StatusOpnameEnum",
    "StatusPemesananEnum",
    "StatusRencanaTreatmentEnum",
    "StatusTindakanEnum",
    "StatusTransaksiEnum",
    "SumberRencanaEnum",
    "TipeItemEnum",
    "TingkatKeparahanAlergiEnum",
    "TipeProdukEnum",
    "VerifikasiEnum",
    "VoidApprovalMethodEnum",
    "VoidReasonEnum",
    # ----- Staf & Pasien -----
    "MasterStaf",
    "Pasien",
    "PasienAlergi",
    "PasienPenyakitKronis",
    "MasterPenyakitKronis",
    # ----- Booking & Kunjungan -----
    "JadwalBooking",
    "Kunjungan",
    "KunjunganAntropometri",
    "KunjunganFoto",
    "KunjunganResep",
    "KunjunganTindakan",
    "PemeriksaanKlinis",
    "Followup",
    # ----- Treatment & Inventory -----
    "MasterTreatment",
    "TreatmentKomponen",
    "PasienRencanaTreatment",
    "PasienResepIterasi",
    "InventoryHistory",
    "InventoryStok",
    "MasterProduk",
    "MasterKlinikConfig",
    "KlinikApoteker",
    "LokasiPengiriman",
    "FakturPenerimaan",
    "ReturProduk",
    "ReturProdukItem",
    # ----- Pengadaan (DEC-038) -----
    "Pemesanan",
    "PemesananItem",
    "PemesananReceive",
    "StockOpname",
    "StockOpnameItem",
    # ----- Transaksi -----
    "KasirClosing",
    "TransaksiDetailProduk",
    "TransaksiDetailTindakan",
    "TransaksiKasir",
    "TransaksiPembayaran",
    "TransaksiRefund",
    # ----- Membership -----
    "MasterMembership",
    "MasterMembershipBenefitTreatment",
    "PasienMembershipHistory",
    "PasienMembershipKuota",
    # ----- Audit -----
    "AuditLog",  # A11: sudah di-import, lengkapi ekspor publik
    # ----- Komisi -----
    "KomisiLedger",
    # ----- Distributor -----
    "MasterDistributor",
    # ----- Inventory Lot -----
    "StokLot",
    "KunjunganLotTerpakai",
]
