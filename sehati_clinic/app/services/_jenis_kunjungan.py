"""Jenis kunjungan yang BUKAN kunjungan klinis — satu definisi untuk semua penghitung.

Kunjungan `RETUR_PASIEN` dibuat oleh retur obat karena alergi (wadah draf SOAP untuk
dokter, DESAIN_RETUR_DARI_PASIEN.md §10b). Keputusan dr. Hansen 2026-10-05 (11.2): TIDAK
dihitung sebagai kunjungan di rekap, dashboard, dan ekspor ringkasan; tetap tampil di
riwayat pasien.

⚠ `jenis_kunjungan` VARCHAR — nilai baru tidak ditolak DB. Penghitung kunjungan BARU wajib
menyaring dengan konstanta ini (CLAUDE.md §4.1). Modul sengaja kecil & tanpa impor supaya
dashboard/rekap/ekspor bisa memakainya tanpa siklus impor.
"""

JENIS_RETUR = "RETUR_PASIEN"
JENIS_KUNJUNGAN_BUKAN_KLINIS = (JENIS_RETUR,)
