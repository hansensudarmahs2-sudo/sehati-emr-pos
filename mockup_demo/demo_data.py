"""
Demo Preset Data — Klinik ABC.

Pure in-memory data dict. NO DATABASE.
Realistic data: 18 pasien, 3 dokter, 7 hari omzet, antrian hari ini 5 orang.
"""

from datetime import date, datetime, timedelta
from typing import Any

# =============================================================================
# BRANDING
# =============================================================================
KLINIK = {
    "nama": "Klinik ABC",
    "alamat": "Jl. Demo Sehat No. 123, Jakarta",
    "telp": "021-555-0100",
    "tagline": "Layanan Estetika & Perawatan Kulit",
}

# =============================================================================
# DEMO USERS (login simulation)
# =============================================================================
DEMO_USERS = [
    {"username": "owner", "nama": "dr. Andi Pratama (Owner)", "role": "Owner"},
    {"username": "dokter", "nama": "dr. Budi Hartono", "role": "Dokter"},
    {"username": "kasir", "nama": "Citra Wulandari", "role": "Kasir"},
    {"username": "fo", "nama": "Diana Putri", "role": "FO"},
]

# =============================================================================
# 3 DOKTER (untuk kinerja chart)
# =============================================================================
DOKTER = [
    {"id": 1, "nama": "dr. Andi Pratama", "spesialis": "Estetika"},
    {"id": 2, "nama": "dr. Budi Hartono", "spesialis": "Dermatologi"},
    {"id": 3, "nama": "dr. Erika Sari", "spesialis": "Anti-Aging"},
]

# =============================================================================
# 18 PASIEN
# =============================================================================
PASIEN = [
    {"id": 1, "no_rm": "RM-001", "nama": "Anisa Rahmawati", "jk": "P", "umur": 32, "telp": "0812-3456-7891", "alamat": "Jakarta Selatan"},
    {"id": 2, "no_rm": "RM-002", "nama": "Bayu Setiawan", "jk": "L", "umur": 45, "telp": "0813-2345-6782", "alamat": "Jakarta Pusat"},
    {"id": 3, "no_rm": "RM-003", "nama": "Citra Lestari", "jk": "P", "umur": 28, "telp": "0856-7890-1234", "alamat": "Tangerang"},
    {"id": 4, "no_rm": "RM-004", "nama": "Dewi Sartika", "jk": "P", "umur": 38, "telp": "0878-9012-3456", "alamat": "Bekasi"},
    {"id": 5, "no_rm": "RM-005", "nama": "Eko Nugroho", "jk": "L", "umur": 52, "telp": "0815-3456-7890", "alamat": "Depok"},
    {"id": 6, "no_rm": "RM-006", "nama": "Fitri Handayani", "jk": "P", "umur": 29, "telp": "0857-1234-5678", "alamat": "Jakarta Timur"},
    {"id": 7, "no_rm": "RM-007", "nama": "Gunawan Wijaya", "jk": "L", "umur": 41, "telp": "0858-9876-5432", "alamat": "Jakarta Barat"},
    {"id": 8, "no_rm": "RM-008", "nama": "Hesti Purnama", "jk": "P", "umur": 35, "telp": "0812-1111-2222", "alamat": "Tangerang Selatan"},
    {"id": 9, "no_rm": "RM-009", "nama": "Indra Kusuma", "jk": "L", "umur": 47, "telp": "0813-3333-4444", "alamat": "Bogor"},
    {"id": 10, "no_rm": "RM-010", "nama": "Jasmin Aulia", "jk": "P", "umur": 26, "telp": "0856-5555-6666", "alamat": "Jakarta Selatan"},
    {"id": 11, "no_rm": "RM-011", "nama": "Kartika Sari", "jk": "P", "umur": 33, "telp": "0878-7777-8888", "alamat": "Bekasi"},
    {"id": 12, "no_rm": "RM-012", "nama": "Lukman Hakim", "jk": "L", "umur": 39, "telp": "0815-9999-0000", "alamat": "Jakarta Utara"},
    {"id": 13, "no_rm": "RM-013", "nama": "Maya Anggraini", "jk": "P", "umur": 30, "telp": "0857-1212-3434", "alamat": "Tangerang"},
    {"id": 14, "no_rm": "RM-014", "nama": "Nurul Hidayah", "jk": "P", "umur": 27, "telp": "0858-5656-7878", "alamat": "Jakarta Selatan"},
    {"id": 15, "no_rm": "RM-015", "nama": "Oki Pramudya", "jk": "L", "umur": 36, "telp": "0812-9090-1010", "alamat": "Depok"},
    {"id": 16, "no_rm": "RM-016", "nama": "Putri Maharani", "jk": "P", "umur": 31, "telp": "0813-2323-4545", "alamat": "Jakarta Timur"},
    {"id": 17, "no_rm": "RM-017", "nama": "Rudi Hartono", "jk": "L", "umur": 44, "telp": "0856-6767-8989", "alamat": "Jakarta Pusat"},
    {"id": 18, "no_rm": "RM-018", "nama": "Sinta Dewi", "jk": "P", "umur": 34, "telp": "0878-1010-2020", "alamat": "Tangerang"},
]

# =============================================================================
# MASTER TREATMENT (demo)
# =============================================================================
TREATMENT = [
    {"id": 1, "nama": "Facial Whitening", "harga": 350000, "durasi": 60},
    {"id": 2, "nama": "Chemical Peeling", "harga": 750000, "durasi": 45},
    {"id": 3, "nama": "Laser Toning", "harga": 1200000, "durasi": 30},
    {"id": 4, "nama": "Botox Forehead", "harga": 2500000, "durasi": 30},
    {"id": 5, "nama": "Microneedling RF", "harga": 1800000, "durasi": 60},
    {"id": 6, "nama": "PRP Wajah", "harga": 2200000, "durasi": 45},
    {"id": 7, "nama": "Mesotherapy Hair", "harga": 1500000, "durasi": 45},
    {"id": 8, "nama": "Konsultasi Dokter", "harga": 200000, "durasi": 30},
]

# =============================================================================
# MASTER PRODUK (skincare untuk resep)
# =============================================================================
PRODUK = [
    {"id": 1, "kode": "PRD-001", "nama": "Vitamin C Serum 30ml", "harga": 450000, "satuan": "botol"},
    {"id": 2, "kode": "PRD-002", "nama": "Retinol Night Cream", "harga": 380000, "satuan": "jar"},
    {"id": 3, "kode": "PRD-003", "nama": "Sunscreen SPF50 PA+++", "harga": 250000, "satuan": "tube"},
    {"id": 4, "kode": "PRD-004", "nama": "Hyaluronic Acid Toner", "harga": 320000, "satuan": "botol"},
    {"id": 5, "kode": "PRD-005", "nama": "Niacinamide Serum 10%", "harga": 280000, "satuan": "botol"},
]

# =============================================================================
# ANTRIAN HARI INI (5 pasien)
# =============================================================================
ANTRIAN_HARI_INI = [
    {
        "id": 101, "no_antrian": "A-01", "id_pasien": 1,
        "nama_pasien": "Anisa Rahmawati", "no_rm": "RM-001",
        "jenis": "KONSULTASI", "status": "ANTRI_KONSULTASI",
        "dokter": "dr. Andi Pratama", "jam_daftar": "08:15",
        "keluhan": "Wajah kusam, jerawat sesekali, ingin treatment whitening",
    },
    {
        "id": 102, "no_antrian": "A-02", "id_pasien": 6,
        "nama_pasien": "Fitri Handayani", "no_rm": "RM-006",
        "jenis": "KONSULTASI", "status": "ANTRI_TINDAKAN",
        "dokter": "dr. Erika Sari", "jam_daftar": "08:30",
        "keluhan": "Mau lanjut sesi Chemical Peeling ke-3",
    },
    {
        "id": 103, "no_antrian": "A-03", "id_pasien": 10,
        "nama_pasien": "Jasmin Aulia", "no_rm": "RM-010",
        "jenis": "KONSULTASI", "status": "ANTRI_KASIR",
        "dokter": "dr. Andi Pratama", "jam_daftar": "08:45",
        "keluhan": "Konsul anti-aging + treatment Botox",
    },
    {
        "id": 104, "no_antrian": "A-04", "id_pasien": 13,
        "nama_pasien": "Maya Anggraini", "no_rm": "RM-013",
        "jenis": "KONSULTASI", "status": "ANTRI_KONSULTASI",
        "dokter": "dr. Budi Hartono", "jam_daftar": "09:00",
        "keluhan": "Eczema di area pipi, perlu treatment topikal",
    },
    {
        "id": 105, "no_antrian": "A-05", "id_pasien": 16,
        "nama_pasien": "Putri Maharani", "no_rm": "RM-016",
        "jenis": "KONSULTASI", "status": "ANTRI_KONSULTASI",
        "dokter": "dr. Erika Sari", "jam_daftar": "09:15",
        "keluhan": "Microneedling sesi pertama, konsul awal",
    },
]

# =============================================================================
# RIWAYAT SOAP (untuk pasien #1 Anisa — demo flow utama)
# =============================================================================
RIWAYAT_SOAP_ANISA = [
    {
        "tgl": "2026-05-15",
        "dokter": "dr. Andi Pratama",
        "keluhan": "Konsul awal, wajah kusam, pigmentasi ringan",
        "diagnosa": "Hiperpigmentasi grade I, kulit dehidrasi",
        "plan": "Series Chemical Peeling 4 sesi + skincare regimen",
        "tindakan": "Konsultasi Dokter",
        "produk": ["Vitamin C Serum 30ml", "Sunscreen SPF50"],
    },
    {
        "tgl": "2026-05-29",
        "dokter": "dr. Andi Pratama",
        "keluhan": "Sesi 1 Chemical Peeling — wajah masih sensitif",
        "diagnosa": "Progress baik, peeling Day 7",
        "plan": "Lanjut sesi 2 dalam 2 minggu",
        "tindakan": "Chemical Peeling (Sesi 1/4)",
        "produk": [],
    },
]

# =============================================================================
# OMZET 7 HARI TERAKHIR (untuk chart dashboard)
# =============================================================================
def get_omzet_7_hari() -> list[dict]:
    """Return list of {tgl, omzet} untuk 7 hari terakhir, realistic Rp 30-50jt/hari."""
    today = date.today()
    omzet_values = [38500000, 42300000, 35100000, 47800000, 41200000, 33600000, 45900000]
    return [
        {
            "tgl": (today - timedelta(days=6 - i)).isoformat(),
            "label": (today - timedelta(days=6 - i)).strftime("%d %b"),
            "omzet": omzet_values[i],
        }
        for i in range(7)
    ]

# =============================================================================
# KINERJA DOKTER (untuk chart)
# =============================================================================
KINERJA_DOKTER = [
    {"nama": "dr. Andi Pratama", "pasien": 47, "omzet": 89500000, "komisi": 11650000},
    {"nama": "dr. Budi Hartono", "pasien": 38, "omzet": 71200000, "komisi": 9270000},
    {"nama": "dr. Erika Sari", "pasien": 52, "omzet": 104800000, "komisi": 13620000},
]

# =============================================================================
# TOP TREATMENT (7 hari)
# =============================================================================
TOP_TREATMENT = [
    {"nama": "Facial Whitening", "qty": 38, "omzet": 13300000},
    {"nama": "Chemical Peeling", "qty": 24, "omzet": 18000000},
    {"nama": "Laser Toning", "qty": 18, "omzet": 21600000},
    {"nama": "Microneedling RF", "qty": 12, "omzet": 21600000},
    {"nama": "Botox Forehead", "qty": 8, "omzet": 20000000},
]

# =============================================================================
# DASHBOARD STATS (Owner view)
# =============================================================================
DASHBOARD_STATS = {
    "pasien_hari_ini": 12,
    "pasien_total": 1247,
    "omzet_hari_ini": 45900000,
    "omzet_bulan_ini": 1284500000,
    "antrian_aktif": 5,
    "transaksi_hari_ini": 14,
    "stok_menipis": 3,
}

# =============================================================================
# TAGIHAN DEMO (untuk Kasir flow — pasien Jasmin Aulia A-03)
# =============================================================================
TAGIHAN_DEMO = {
    "id_kunjungan": 103,
    "no_antrian": "A-03",
    "pasien": "Jasmin Aulia",
    "no_rm": "RM-010",
    "tgl": date.today().isoformat(),
    "dokter": "dr. Andi Pratama",
    "items": [
        {"jenis": "TREATMENT", "nama": "Konsultasi Dokter", "qty": 1, "harga": 200000, "subtotal": 200000},
        {"jenis": "TREATMENT", "nama": "Botox Forehead", "qty": 1, "harga": 2500000, "subtotal": 2500000},
        {"jenis": "PRODUK", "nama": "Vitamin C Serum 30ml", "qty": 1, "harga": 450000, "subtotal": 450000},
        {"jenis": "PRODUK", "nama": "Sunscreen SPF50 PA+++", "qty": 1, "harga": 250000, "subtotal": 250000},
    ],
    "subtotal": 3400000,
    "diskon": 0,
    "total": 3400000,
}

# =============================================================================
# NOTA DEMO (setelah bayar)
# =============================================================================
def get_nota_demo() -> dict:
    """Nota untuk Jasmin A-03 setelah pembayaran TUNAI."""
    return {
        **TAGIHAN_DEMO,
        "nota_no": f"NOTA-{date.today().strftime('%Y%m%d')}-0014",
        "tgl_bayar": datetime.now().isoformat(timespec="minutes"),
        "metode": "TUNAI",
        "nominal_bayar": 3500000,
        "kembalian": 100000,
        "kasir": "Citra Wulandari",
    }
