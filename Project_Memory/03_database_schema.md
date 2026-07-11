# Database Schema — db_sehati

> Schema final post-migrasi (4 file SQL + seed). 26 tabel.
> Untuk schema asli pre-migrasi, lihat `../Tables_in_db_sehati.txt`.

---

## ER Overview (High-level)

```
                        ┌──────────────┐
                        │ master_staf  │ (Owner, Dokter, Perawat, Apoteker, Kasir, FO, Admin, Superadmin)
                        └──────┬───────┘
                               │
            ┌──────────────────┼─────────────────────────┐
            │                  │                         │
    ┌───────▼────────┐  ┌──────▼────────┐    ┌──────────▼────────────┐
    │     pasien     │  │  kunjungan    │    │   audit_log           │
    └───┬────────────┘  └──────┬────────┘    └───────────────────────┘
        │                      │
        │   ┌──────────────────┴────────────┐
        │   │                               │
        │   │  pasien_alergi                │
        │   │  pasien_penyakit_kronis       │
        │   │                               │
        ▼   ▼                               ▼
   pasien_membership_history     pemeriksaan_klinis (SOAP)
   pasien_membership_kuota       kunjungan_antropometri
   pasien_rencana_treatment      kunjungan_foto
   pasien_resep_iterasi          kunjungan_resep
                                 kunjungan_tindakan
                                       │
                                       ▼
                                 master_treatment
                                 treatment_komponen
                                       │
                                       ▼
                                 inventory_stok ↔ inventory_history
                                       │
                                       ▼
                                 master_produk

                                 transaksi_kasir
                                       ├─ transaksi_detail_produk
                                       └─ transaksi_pembayaran
                                 
                                 master_membership
                                 master_membership_benefit_treatment
                                 
                                 jadwal_booking
```

---

## 26 Tabel (Grouped by Domain)

### Group 1: Identitas & Auth
| Tabel | Kolom Penting | Catatan |
|-------|---------------|---------|
| `master_staf` | id_staf, username, password_hash, pin, role, is_active, is_logged_in, token_expired_at, waktu_mulai_shift | Auth + anchor shift logic |
| `audit_log` | id_log, id_staf, aksi, tabel_target, id_target, data_lama, data_baru, ip_address, waktu | Append-only audit trail |

### Group 2: Pasien
| Tabel | Kolom Penting | Catatan |
|-------|---------------|---------|
| `pasien` | id_pasien, **no_rm** (format `YYMMDD-NNN`), nama, jenis_kelamin, tgl_lahir, nomor_telepon, tipe_membership, status_verifikasi | Master pasien |
| `pasien_alergi` | id_alergi, id_pasien, alergen, gejala, tingkat_keparahan, is_active | Soft delete (is_active=0) |
| `pasien_penyakit_kronis` | id_penyakit, id_pasien, nama_penyakit, catatan, is_active | Soft delete |

### Group 3: Booking & Kunjungan
| Tabel | Kolom Penting | Catatan |
|-------|---------------|---------|
| `jadwal_booking` | id_booking, id_pasien, tgl_rencana, jam_rencana, status_booking | Phase 1 minimal |
| `kunjungan` | id_kunjungan, id_pasien, id_booking, id_staf_fo, tgl_kunjungan, **nomor_antrean** (per hari), status_antrian | 1 row per pasien per visit |
| `kunjungan_antropometri` | id_antropometri, id_kunjungan, berat_badan, tinggi_badan, skinfold_titik_1/2/3, lingkar_perut, tekanan_darah | Untuk hitung BMI + Body Fat (Pollock) |
| `kunjungan_foto` | id_foto, id_kunjungan, id_pasien, kategori (BEFORE/AFTER/PROGRESS), url_path | Placeholder, implement Phase 2 |
| `kunjungan_resep` | id_resep, id_kunjungan, id_produk, qty, aturan_pakai, status_item, id_staf_input, id_staf_void | Produk yang diresep dokter |
| `kunjungan_tindakan` | id_kunjungan_tindakan, id_kunjungan, id_treatment, status_tindakan, id_staf_pelaksana, **id_kuota_member**, **id_rencana**, waktu_mulai, waktu_selesai | Treatment yang dieksekusi |
| `pemeriksaan_klinis` | id_pemeriksaan, id_kunjungan, id_pasien, id_staf_dokter, anamnesa, pemeriksaan_fisik, diagnosa, **saran_treatment** (catatan untuk perawat), **saran_produk** (instruksi untuk pasien) | SOAP dokter |

### Group 4: Treatment
| Tabel | Kolom Penting | Catatan |
|-------|---------------|---------|
| `master_treatment` | id_treatment, nama_treatment, role_pelaksana, durasi_menit, harga, butuh_otorisasi, **default_rentang_mulai_minggu**, **default_rentang_akhir_minggu** | Catalog treatment |
| `treatment_komponen` | id_komponen, id_treatment, kategori (BAHAN/ALAT), id_bahan, qty, satuan | Formula treatment |
| `pasien_rencana_treatment` | id_rencana, id_pasien, **id_treatment** (FK baru), nama_tindakan (snapshot), urutan_sesi, **sumber_rencana** (DOKTER_PLAN/MEMBERSHIP/PROMO), **tgl_target_mulai**, **tgl_target_akhir**, status, id_kunjungan_eksekusi | Series treatment plan |
| `pasien_resep_iterasi` | id_iterasi, id_pasien, **id_produk** (FK baru), nama_produk (snapshot), kuota_maksimal, sudah_diambil, **qty_per_iterasi**, **tgl_kadaluarsa**, id_kunjungan_pembuat, id_staf_dokter | Resep yang bisa diulang |

### Group 5: Inventory & Produk
| Tabel | Kolom Penting | Catatan |
|-------|---------------|---------|
| `inventory_stok` | id_bahan, nama_bahan, stok_gudang_utama, stok_kabin, satuan, satuan_pembelian, rasio_konversi | Master bahan klinik |
| `inventory_history` | id_history, id_bahan, id_staf, jenis_mutasi (TINDAKAN/PENJUALAN/RESTOCK/EXPIRED/RUSAK/PENYESUAIAN), qty_perubahan, stok_akhir, referensi, keterangan, waktu_mutasi | Append-only kartu stok |
| `master_produk` | id_produk, kode_produk, nama_produk, tipe_produk (RETAIL/CABIN/ALAT), **id_bahan_sumber** (FK nullable ke inventory_stok kalau repacking), **qty_per_unit_produk**, satuan, harga_jual, stok_terkini, **default_iterasi**, **eligible_member_discount** | Produk untuk POS |

### Group 6: Transaksi
| Tabel | Kolom Penting | Catatan |
|-------|---------------|---------|
| `transaksi_kasir` | id_transaksi, id_kunjungan, id_staf_kasir, rincian_tagihan (TEXT snapshot), subtotal **DECIMAL(12,2)**, nominal_diskon **DECIMAL(12,2)**, total_tagihan **DECIMAL(12,2)**, waktu_bayar | 1 per pembayaran |
| `transaksi_detail_produk` | id_detail, id_transaksi, id_produk, qty, harga_satuan, subtotal | Rincian produk |
| `transaksi_pembayaran` | id_pembayaran, id_transaksi, metode_bayar, nominal | Split payment ready (N rows per transaksi) |

### Group 7: Membership (Tabel Baru — Migrasi 003)
| Tabel | Kolom Penting | Catatan |
|-------|---------------|---------|
| `master_membership` | id_membership, nama_tier (VIP, VVIP, …), harga_aktivasi, durasi_bulan, free_konsultasi_dokter, diskon_treatment_persen, diskon_produk_persen, is_active | Definisi tier |
| `master_membership_benefit_treatment` | id_benefit, id_membership, id_treatment, kuota_total, periode_kuota (BULANAN/TOTAL_PAKET) | Benefit kuota per tier |
| `pasien_membership_history` | id_history, id_pasien, id_membership, tgl_aktif, tgl_expired, harga_bayar, id_transaksi_aktivasi, is_active | Record aktivasi |
| `pasien_membership_kuota` | id_kuota, id_pasien, id_membership_history, id_treatment, periode_kuota, **bulan_periode** (YYYY-MM kalau BULANAN, NULL kalau TOTAL), kuota_total, kuota_terpakai, expired_at | Kuota tersedia per pasien |

---

## ENUM Values (Match Python & MySQL)

| ENUM | Values |
|------|--------|
| `StafRoleEnum` | Owner, Dokter, Perawat, Apoteker, Kasir, FO, Admin, Superadmin |
| `GenderEnum` | L, P |
| `MembershipTierEnum` | REGULAR, VIP, VVIP |
| `VerifikasiEnum` | UNVERIFIED, VERIFIED |
| `TingkatKeparahanAlergiEnum` | Ringan, Sedang, Berat |
| `StatusBookingEnum` | BOOKED, CONFIRMED, RESCHEDULED, CANCELLED, CHECKED_IN |
| `StatusAntrianEnum` | ANTRI_KONSULTASI, KONSULTASI, ANTRI_TREATMENT, ON_TREATMENT, ANTRI_BAYAR, ANTRI_OBAT, COMPLETED, BATAL |
| `StatusTindakanEnum` | PENDING, PROSES, SELESAI |
| `StatusItemResepEnum` | PENDING, BATAL, DIBAYAR |
| `StatusRencanaTreatmentEnum` | PENDING, SCHEDULED, DONE, CANCELLED, EXPIRED |
| `SumberRencanaEnum` | DOKTER_PLAN, MEMBERSHIP, PROMO |
| `TipeProdukEnum` | RETAIL, CABIN, ALAT |
| `JenisMutasiEnum` | TINDAKAN, PENJUALAN, RESTOCK, EXPIRED, RUSAK, PENYESUAIAN |
| `KategoriKomponenTreatmentEnum` | BAHAN, ALAT |
| `KategoriFotoEnum` | BEFORE, AFTER, PROGRESS |
| `PeriodeKuotaEnum` | BULANAN, TOTAL_PAKET |
| `StatusAksiAuditEnum` | SUCCESS, FAILED |

---

## Important Schema Notes

### 1. Format Nomor RM
`YYMMDD-NNN`. Counter reset harian. Pakai `SELECT FOR UPDATE` di `PasienRepository.generate_next_no_rm()` untuk anti-kolisi.
- Example: `260520-001`, `260520-002`, dst.
- Limit 999 pasien baru per hari (cukup untuk klinik kecil-menengah).

### 2. Soft Delete Medical Record
- `pasien_alergi.is_active = 0` (soft delete) — JANGAN hard DELETE.
- `pasien_penyakit_kronis.is_active = 0` — sama.
- Filosofi EMR: medical record tidak boleh hilang.

### 3. Append-only Tables
- `inventory_history` — kartu stok, jangan UPDATE/DELETE.
- `audit_log` — audit trail, jangan UPDATE/DELETE.

### 4. Snapshot Columns (Denormalisasi Sengaja)
- `pasien_rencana_treatment.nama_tindakan` — snapshot saat plan dibuat (kalau treatment di-rename, history tetap akurat).
- `pasien_resep_iterasi.nama_produk` — sama.
- `transaksi_kasir.rincian_tagihan` (TEXT) — snapshot untuk reprint struk persis seperti waktu cetak.

### 5. Anchor Shift Logic
`master_staf.waktu_mulai_shift` HANYA di-update saat login kalau tanggal-nya beda dari hari ini. Login ulang di hari sama TIDAK reset shift. Ini critical untuk rekap kasir.

### 6. Decimal Money
Semua kolom uang pakai `DECIMAL(12,2)` setelah migrasi 001. Tidak pakai INT lagi.

### 7. Foreign Keys (Post-Migrasi)
Semua FK yang seharusnya ada sudah di-add di migrasi 001. Kalau ada query yang error karena FK constraint, kemungkinan business logic salah (insert child sebelum parent, dll).

---

## Connection Info

```
Host: localhost
Port: 3306
Database: db_sehati
User: klinik_dev
Password: Klinik123!  (default dev — ganti di production via .env)

Authentication: 
  - root@localhost → auth_socket (login via sudo, tidak pakai password)
  - klinik_dev@localhost → password (normal MySQL auth)
```

---

## Migration History

```
migrations/sql/
├── 001_fix_kritis.sql              # FK missing, DECIMAL fix, index
├── 002_alter_existing.sql          # Add kolom baru di tabel existing
├── 003_membership_system.sql       # Create 4 tabel membership
├── 004_audit_log.sql               # Create audit_log
└── 005_hash_passwords.sql          # (notes only — actual via Python script)

tools/
└── migrate_passwords.py             # Hash bcrypt semua password+PIN existing

seed_data/
├── master_membership_default.sql   # VIP & VVIP tier
└── master_treatment_otorisasi_template.sql  # template untuk dokter isi

migrations/versions/
└── 20260503_0000_baseline_existing_schema.py  # Alembic baseline (kosong)
```

Setelah ini, semua schema change harus via `alembic revision --autogenerate -m "..."` → review → `alembic upgrade head`.
