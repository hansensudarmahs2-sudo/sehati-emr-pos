# Panduan Eksekusi SQL Migrasi

Folder ini berisi file SQL yang **harus dijalankan urut** sebelum project Python di-build di Minggu 1.

## ⚠️ SEBELUM MULAI

**WAJIB BACKUP `db_sehati` DULU.** Migrasi ini mengubah skema dan data. Kalau ada yang salah, kita perlu restore dari backup.

```bash
# Di server klinik, terminal:
mysqldump -u root -p db_sehati > backup_sebelum_migrasi_2026-04-27.sql

# Verifikasi file backup tidak kosong:
ls -lh backup_sebelum_migrasi_2026-04-27.sql

# Test restore di DB lain (opsional tapi disarankan):
mysql -u root -p -e "CREATE DATABASE db_sehati_test;"
mysql -u root -p db_sehati_test < backup_sebelum_migrasi_2026-04-27.sql
mysql -u root -p -e "SHOW TABLES FROM db_sehati_test;"
```

## Urutan Eksekusi

Jalankan **urut**, jangan dilewat. Setiap file aman dijalankan **sekali saja** (idempotent — kalau dijalankan dua kali, error keluar tapi tidak rusak).

| # | File | Isi | Aman dijalankan? |
|---|------|-----|------------------|
| 1 | `001_fix_kritis.sql` | Tambah missing FK, fix tipe data DECIMAL, tambah index | ✅ Bisa langsung |
| 2 | `002_alter_existing.sql` | Tambah kolom baru di tabel existing (id_treatment, id_produk, id_bahan_sumber, dll) | ✅ Bisa langsung |
| 3 | `003_membership_system.sql` | Buat tabel-tabel baru untuk membership system | ✅ Bisa langsung |
| 4 | `004_audit_log.sql` | Buat tabel audit_log | ✅ Bisa langsung |
| 5 | `005_hash_passwords.sql` | **HANYA notes/persiapan**. Hashing actual via Python script. | ⚠️ Lihat catatan |

### Cara jalankan tiap file

```bash
mysql -u root -p db_sehati < migrations/sql/001_fix_kritis.sql
mysql -u root -p db_sehati < migrations/sql/002_alter_existing.sql
mysql -u root -p db_sehati < migrations/sql/003_membership_system.sql
mysql -u root -p db_sehati < migrations/sql/004_audit_log.sql
```

Setelah selesai, jalankan Python script untuk hash password:

```bash
cd path/to/project
python tools/migrate_passwords.py
```

## Setelah Migrasi

Verifikasi struktur:
```sql
USE db_sehati;
SHOW TABLES;
-- Harus ada 25+ tabel sekarang (dari sebelumnya 21)
-- Tabel baru: master_membership, master_membership_benefit_treatment,
-- pasien_membership_history, pasien_membership_kuota, audit_log

DESCRIBE master_produk;
-- Harus ada kolom baru: id_bahan_sumber, qty_per_unit_produk,
-- default_iterasi, eligible_member_discount

DESCRIBE master_treatment;
-- Harus ada kolom baru: default_rentang_mulai_minggu, default_rentang_akhir_minggu

DESCRIBE pasien_rencana_treatment;
-- Harus ada kolom baru: id_treatment, sumber_rencana, id_referensi_sumber,
-- tgl_target_mulai, tgl_target_akhir
```

## Kalau Ada Masalah

Restore dari backup:
```bash
# Drop database dulu
mysql -u root -p -e "DROP DATABASE db_sehati;"
mysql -u root -p -e "CREATE DATABASE db_sehati;"

# Restore
mysql -u root -p db_sehati < backup_sebelum_migrasi_2026-04-27.sql
```

Lalu hubungi saya (Claude) untuk diagnosa.

## Seed Data (Opsional, Setelah Migrasi)

File seed_data berisi data awal yang bisa dipakai untuk testing:
- `seed_data/master_membership_default.sql` — 2 tier VIP & VVIP dengan benefit konkret
- `seed_data/master_treatment_otorisasi_template.sql` — template untuk dokter isi treatment apa yang `butuh_otorisasi=1`

Jalankan setelah dokter review dan setuju datanya.
