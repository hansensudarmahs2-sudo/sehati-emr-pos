"""
Menu navigasi sidebar — config per role.

Format menu item:
    {
        "label": str,           # nama yang tampil di sidebar
        "url": str,             # path target (mis. /web/pasien)
        "icon": str,            # SVG path (atau emoji untuk simplicity)
        "active_when": str,     # path prefix untuk highlight active state
    }

Group: {"group": str, "items": [...]}

Helper:
    get_menu_for_role(role) → list of groups
    is_active(item_url, current_path) → bool
"""

# Menu definitions — semua possible items
MENU_PASIEN = {
    "label": "Cari Pasien",
    "url": "/web/pasien",
    "icon": "👥",
    "active_when": "/web/pasien",
}
MENU_PASIEN_BARU = {
    "label": "Daftar Pasien Baru",
    "url": "/web/pendaftaran-pasien",
    "icon": "➕",
    "active_when": "/web/pendaftaran-pasien",
}
MENU_KUNJUNGAN_ANTRIAN = {
    "label": "Antrian Hari Ini",
    "url": "/web/kunjungan",
    "icon": "📋",
    "active_when": "/web/kunjungan",
}
MENU_BOOKING = {
    "label": "Booking",
    "url": "/web/booking",
    "icon": "📅",
    "active_when": "/web/booking",
}
MENU_FOLLOWUP = {
    "label": "Follow-up",
    "url": "/web/followup",
    "icon": "🔔",
    "active_when": "/web/followup",
}
MENU_DOKTER_ANTRIAN = {
    "label": "Antrian Saya",
    "url": "/web/dokter/antrian",
    "icon": "🩺",
    "active_when": "/web/dokter",
    "badge_status": "ANTRI_KONSULTASI",
}
MENU_RUANG_TINDAKAN = {
    "label": "Ruang Tindakan",
    "url": "/web/ruang-tindakan/antrian",
    "icon": "💉",
    "active_when": "/web/ruang-tindakan",
    "badge_status": "ANTRI_TREATMENT",
}
MENU_KASIR = {
    "label": "Kasir / POS",
    "url": "/web/kasir/antrian",
    "icon": "💰",
    "active_when": "/web/kasir",
    "badge_status": "ANTRI_BAYAR",
}
MENU_KASIR_CARI_TRANSAKSI = {
    "label": "Cari Transaksi",
    "url": "/web/kasir/cari-transaksi",
    "icon": "🔍",
    "active_when": "/web/kasir/cari-transaksi",
}
MENU_KASIR_TUTUP = {
    "label": "Tutup Kasir",
    "url": "/web/kasir/tutup",
    "icon": "🧾",
    "active_when": "/web/kasir/tutup",
}
MENU_APOTEK = {
    "label": "Apotek",
    "url": "/web/apotek",
    "icon": "💊",
    "active_when": "/web/apotek",
    "badge_status": "ANTRI_OBAT",
}
MENU_APOTEK_STOK = {
    "label": "Manajemen Stok",
    "url": "/web/apotek/stok",
    "icon": "📦",
    "active_when": "/web/apotek/stok",
}
MENU_PRODUK = {
    "label": "Master Produk",
    "url": "/web/master/produk",
    "icon": "📦",
    "active_when": "/web/master/produk",
}
MENU_TREATMENT = {
    "label": "Master Treatment",
    "url": "/web/master/treatment",
    "icon": "💉",
    "active_when": "/web/master/treatment",
}
MENU_BAHAN = {
    "label": "Master Bahan Klinik",
    "url": "/web/master/bahan",
    "icon": "🧪",
    "active_when": "/web/master/bahan",
}
MENU_MEMBERSHIP = {
    "label": "Master Membership",
    "url": "/web/master/membership",
    "icon": "🎖️",
    "active_when": "/web/master/membership",
}
MENU_DISTRIBUTOR = {
    "label": "Master Distributor",
    "url": "/web/master/distributor",
    "icon": "🚚",
    "active_when": "/web/master/distributor",
}
MENU_LOKASI = {
    "label": "Lokasi Pengiriman",
    "url": "/web/master/lokasi-pengiriman",
    "icon": "📍",
    "active_when": "/web/master/lokasi-pengiriman",
}
MENU_PEMESANAN = {
    "label": "Pemesanan / PO",
    "url": "/web/pengadaan/pemesanan",
    "icon": "📋",
    "active_when": "/web/pengadaan/pemesanan",
}
MENU_OPNAME = {
    "label": "Stock Opname",
    "url": "/web/pengadaan/opname",
    "icon": "✓",
    "active_when": "/web/pengadaan/opname",
}
MENU_RETUR = {
    "label": "Retur Produk",
    "url": "/web/pengadaan/retur",
    "icon": "↩",
    "active_when": "/web/pengadaan/retur",
}
MENU_MUTASI = {
    "label": "History Mutasi",
    "url": "/web/pengadaan/mutasi",
    "icon": "📊",
    "active_when": "/web/pengadaan/mutasi",
}
MENU_REPORTS = {
    "label": "Rekap & Laporan",
    "url": "/web/reports",
    "icon": "📊",
    "active_when": "/web/reports",
}
MENU_EXPORT = {
    "label": "Raw Data Export",
    "url": "/web/export",
    "icon": "📥",
    "active_when": "/web/export",
}
MENU_FINANCE_EXPORT = {
    "label": "Export ke Finance",
    "url": "/web/finance-export",
    "icon": "📤",
    "active_when": "/web/finance-export",
}
MENU_SETTINGS_KLINIK = {
    "label": "Profil Klinik",
    "url": "/web/settings/klinik",
    "icon": "🏥",
    "active_when": "/web/settings",
}
MENU_STAF = {
    "label": "Kelola Staf",
    "url": "/web/staf",
    "icon": "👤",
    "active_when": "/web/staf",
}
MENU_PROFIL = {
    "label": "Profil & Password",
    "url": "/web/profil",
    "icon": "⚙️",
    "active_when": "/web/profil",
}


# Menu config per role — group dengan items
_MENU_BY_ROLE = {
    "Owner": [
        {"group": "Operasional", "items": [
            MENU_PASIEN, MENU_PASIEN_BARU, MENU_KUNJUNGAN_ANTRIAN, MENU_BOOKING, MENU_FOLLOWUP,
            MENU_KASIR, MENU_KASIR_TUTUP, MENU_KASIR_CARI_TRANSAKSI, MENU_APOTEK, MENU_APOTEK_STOK,
        ]},
        {"group": "Klinis", "items": [
            MENU_DOKTER_ANTRIAN, MENU_RUANG_TINDAKAN,
        ]},
        {"group": "Pengadaan", "items": [
            MENU_PEMESANAN, MENU_OPNAME, MENU_RETUR, MENU_MUTASI,
        ]},
        {"group": "Master Data", "items": [
            MENU_TREATMENT, MENU_BAHAN, MENU_PRODUK, MENU_MEMBERSHIP, MENU_DISTRIBUTOR, MENU_LOKASI,
        ]},
        {"group": "Manajemen", "items": [
            MENU_STAF, MENU_REPORTS, MENU_EXPORT, MENU_FINANCE_EXPORT,
        ]},
        {"group": "Settings", "items": [
            MENU_SETTINGS_KLINIK,
        ]},
        {"group": "Akun", "items": [MENU_PROFIL]},
    ],
    "Superadmin": [
        {"group": "Operasional", "items": [
            MENU_PASIEN, MENU_PASIEN_BARU, MENU_KUNJUNGAN_ANTRIAN, MENU_BOOKING, MENU_FOLLOWUP,
            MENU_KASIR, MENU_KASIR_TUTUP, MENU_KASIR_CARI_TRANSAKSI, MENU_APOTEK, MENU_APOTEK_STOK,
        ]},
        {"group": "Klinis", "items": [
            MENU_DOKTER_ANTRIAN, MENU_RUANG_TINDAKAN,
        ]},
        {"group": "Pengadaan", "items": [
            MENU_PEMESANAN, MENU_OPNAME, MENU_RETUR, MENU_MUTASI,
        ]},
        {"group": "Master Data", "items": [
            MENU_TREATMENT, MENU_BAHAN, MENU_PRODUK, MENU_MEMBERSHIP, MENU_DISTRIBUTOR, MENU_LOKASI,
        ]},
        {"group": "Manajemen", "items": [
            MENU_STAF, MENU_REPORTS, MENU_FINANCE_EXPORT,
        ]},
        {"group": "Settings", "items": [
            MENU_SETTINGS_KLINIK,
        ]},
        {"group": "Akun", "items": [MENU_PROFIL]},
    ],
    "Purchasing": [
        {"group": "Pengadaan", "items": [
            MENU_PEMESANAN, MENU_OPNAME, MENU_RETUR, MENU_MUTASI,
        ]},
        {"group": "Master Data", "items": [
            MENU_DISTRIBUTOR, MENU_LOKASI,
        ]},
        {"group": "Akun", "items": [MENU_PROFIL]},
    ],
    "Admin": [
        {"group": "Operasional", "items": [
            MENU_PASIEN, MENU_PASIEN_BARU, MENU_KUNJUNGAN_ANTRIAN, MENU_BOOKING, MENU_FOLLOWUP,
            MENU_KASIR_CARI_TRANSAKSI,
        ]},
        {"group": "Manajemen", "items": [
            MENU_REPORTS,
        ]},
        {"group": "Akun", "items": [MENU_PROFIL]},
    ],
    "Dokter": [
        {"group": "Klinis", "items": [
            MENU_DOKTER_ANTRIAN, MENU_RUANG_TINDAKAN, MENU_PASIEN,
        ]},
        # REPORTS-COMPART (#324): Dokter bisa akses Kinerja Saya
        {"group": "Laporan", "items": [
            MENU_REPORTS,
        ]},
        {"group": "Akun", "items": [MENU_PROFIL]},
    ],
    "Perawat": [
        {"group": "Klinis", "items": [
            MENU_RUANG_TINDAKAN, MENU_PASIEN,
        ]},
        # Perawat bisa lihat Komisi Saya (REPORTS-COMPART)
        {"group": "Laporan", "items": [
            MENU_REPORTS,
        ]},
        {"group": "Akun", "items": [MENU_PROFIL]},
    ],
    "Kasir": [
        {"group": "Operasional", "items": [
            MENU_KASIR, MENU_KASIR_TUTUP, MENU_KASIR_CARI_TRANSAKSI, MENU_PASIEN, MENU_BOOKING, MENU_FOLLOWUP,
        ]},
        # REPORTS-COMPART (#324): Kasir bisa akses Rekap Shift Saya
        {"group": "Laporan", "items": [
            MENU_REPORTS,
        ]},
        {"group": "Akun", "items": [MENU_PROFIL]},
    ],
    "Apoteker": [
        {"group": "Operasional", "items": [
            MENU_APOTEK, MENU_APOTEK_STOK,
        ]},
        {"group": "Pengadaan", "items": [
            MENU_PEMESANAN,
        ]},
        {"group": "Laporan", "items": [
            MENU_REPORTS,
        ]},
        {"group": "Akun", "items": [MENU_PROFIL]},
    ],
    "FO": [
        {"group": "Operasional", "items": [
            MENU_PASIEN, MENU_PASIEN_BARU, MENU_KUNJUNGAN_ANTRIAN, MENU_BOOKING, MENU_FOLLOWUP,
        ]},
        {"group": "Akun", "items": [MENU_PROFIL]},
    ],
}


def get_menu_for_role(role: str) -> list[dict]:
    """Return list of menu groups untuk role tertentu. Empty list kalau role unknown."""
    return _MENU_BY_ROLE.get(role, [])


def is_active(item_url_prefix: str, current_path: str) -> bool:
    """Cek apakah menu item active berdasarkan current URL path."""
    if not item_url_prefix or not current_path:
        return False
    return current_path.startswith(item_url_prefix)


__all__ = ["get_menu_for_role", "is_active"]
