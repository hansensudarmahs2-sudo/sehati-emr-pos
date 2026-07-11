# Keputusan Final — Hasil Diskusi dr. Hansen × Claude

> Tanggal diskusi: 27 April 2026
> Dokumen ini adalah **single source of truth** untuk semua keputusan teknis dan bisnis. Kalau ada konflik antar dokumen, dokumen ini menang.

---

## A. Security & Authentication

| Topik | Keputusan |
|-------|-----------|
| Password storage | bcrypt hash (passlib). Password lama di-hash via script migrasi sekali jalan. Tidak ada pengumuman ke staff (kode belum production). |
| PIN dokter | Sama seperti password — bcrypt hash. |
| Session/Auth | JWT (signed, expired 6 jam — sesuai logika `token_expired_at` dokter). Logika anchor `waktu_mulai_shift` dipertahankan. |
| RBAC | Dependency `role_required(["FO","Dokter",...])` di semua endpoint. Verifikasi per role tidak lagi manual seperti `verifikasi_fo` di kode lama. |
| Plaintext sensitive | Tidak ada plaintext password / PIN di logs, response, atau audit log. |

## B. Database Consistency

| Topik | Keputusan |
|-------|-----------|
| Foreign keys missing | Semua FK yang hilang akan di-add via migration. Lihat `migrations/sql/001_fix_kritis.sql`. |
| `pasien_rencana_treatment.nama_tindakan` | Tambah kolom `id_treatment INT FK`. Kolom `nama_tindakan` dipertahankan sebagai snapshot historis (kalau treatment di-rename, plan lama tetap akurat). |
| `pasien_resep_iterasi.nama_produk` | Tambah kolom `id_produk INT FK`. Sama strategi snapshot historis. |
| `transaksi_kasir.subtotal/nominal_diskon/total_tagihan` | Ubah dari INT ke `DECIMAL(12,2)`. |
| `transaksi_kasir.rincian_tagihan TEXT` | Dipertahankan sebagai snapshot string untuk reprint struk persis seperti waktu cetak. **Source of truth tetap dari tabel detail**, bukan dari kolom ini. |
| Index untuk laporan | Tambah composite index sesuai rekomendasi `01_ANALISA_DATABASE.md`. |

## C. Inventory & Produk

| Topik | Keputusan |
|-------|-----------|
| `master_produk` vs `inventory_stok` | **Pisah tegas**. master_produk = barang dijual via POS. inventory_stok = bahan klinik. |
| Repacking bahan → produk | **Modul terpisah** "Produksi" di Apotek. Hanya apoteker yang bisa eksekusi. Bukan alur main eMR/POS. |
| Mapping produk hasil repack | Tambah kolom `master_produk.id_bahan_sumber` (FK nullable → inventory_stok) + `qty_per_unit_produk` (FLOAT). |
| Produk jadi dari distributor | `id_bahan_sumber = NULL`. Stok ditambah via "Pembelian Produk" (ditangani Phase 1 minggu 5-6). |
| Stok minus | Diizinkan (tidak diblok). Sistem tampilkan warning + masuk dashboard "Stok Bermasalah" untuk admin/owner. |
| Penyelesaian stok minus | Endpoint "Stock Opname" — admin input qty fisik aktual, sistem catat selisih sebagai `jenis_mutasi='PENYESUAIAN'` dengan keterangan wajib + password admin re-confirm. |
| Notifikasi stok minus | Phase 1: banner di dashboard saat admin/owner login. Phase 2: WA/Telegram/Email. |

## D. Status Antrian — Final Enum

```
ANTRI_KONSULTASI → KONSULTASI → ANTRI_TREATMENT → ON_TREATMENT 
→ ANTRI_BAYAR → ANTRI_OBAT → COMPLETED
                         ↘ COMPLETED (kalau tidak ada resep)

BATAL: dari status apa pun. Hanya FO/Owner/Superadmin.
```

**Catatan:** `AMBIL_PRODUK` dihilangkan. Pakai `ANTRI_OBAT` saja. Endpoint `kasir/bayar` di-update set status ke `ANTRI_OBAT` (kalau ada resep) atau `COMPLETED` (kalau tidak ada).

## E. SOAP — kolom `saran_treatment` & `saran_produk`

**Repurpose, tidak hapus.**
- `saran_treatment` = catatan dokter untuk **perawat** saat eksekusi. Tampil di panel warning kuning di UI ruang tindakan. Contoh: "hati-hati ekstraksi, pasien sensitif nyeri".
- `saran_produk` = instruksi dokter untuk **pasien** saat pakai produk (di luar `aturan_pakai` standar). Tercetak di struk apotek. Contoh: "tipis-tipis selama 1 minggu pertama".

## F. Series Treatment

| Topik | Keputusan |
|-------|-----------|
| Sumber rencana | ENUM `('DOKTER_PLAN','MEMBERSHIP','PROMO')`. Promo disimpan untuk future use. |
| Bundling paket | **Hanya untuk member**. Non-member tidak ada paket. |
| `tgl_target_mulai/akhir` | Per sesi, bukan per paket. Default dari `master_treatment.default_rentang_mulai_minggu` & `default_rentang_akhir_minggu`. |
| Expired keseluruhan paket | Phase 1: set `2030-01-01` (effectively unlimited). Phase 2 saat formalisasi paket promo, tambah field di `master_paket_treatment`. |
| Track sesi yang sudah dieksekusi | Kolom `id_kunjungan_eksekusi` & `tgl_eksekusi` di-fill saat eksekusi. Status updated. |
| Transfer paket ke pasien lain | **Tidak boleh** di Phase 1. Evaluasi Phase 2. |

## G. Membership System (DETAIL)

### G.1. Tier saat ini & masa depan

- Phase 1 (sekarang): 2 tier — VIP, VVIP (sesuai enum existing) + non-member ('REGULAR' atau tidak terdaftar).
- Phase 2: 3 tier baru — Basic, Gold, Platinum dengan benefit berbeda dalam konsep yang sama.
- Database struktur **fleksibel** — tinggal tambah row di `master_membership` untuk tier baru.

### G.2. Masa berlaku
- Default 12 bulan (1 tahun).
- Disimpan di `master_membership.durasi_bulan` agar owner bisa override.

### G.3. Benefit per tier (contoh VIP saat ini)

| Benefit | Cara di sistem |
|---------|----------------|
| Free konsultasi dokter | `master_membership.free_konsultasi_dokter = 1` → kasir auto-skip biaya konsultasi. |
| Kuota treatment bulanan (1× facial/bulan) | Generate 12 row di `pasien_membership_kuota` saat aktivasi (1 row per bulan). |
| Kuota treatment tahunan (2× IPL/12 bulan) | Generate 1 row di `pasien_membership_kuota` dengan `total_kuota=2, periode=TOTAL_PAKET`. |
| Diskon produk 3% (parsial) | `master_membership.diskon_produk_persen = 3.00` + flag per produk `master_produk.eligible_member_discount = 1`. |
| Diskon treatment | `master_membership.diskon_treatment_persen` (default 0 untuk VIP saat ini, owner bisa setup tier lain). |

### G.4. Aturan kuota

- **Bulanan:** Kalau tidak terpakai bulan ini, **HANGUS**. Tidak akumulasi ke bulan berikutnya. (Pertanyaan #1 → A)
- **Tahunan (TOTAL_PAKET):** Bebas dipakai kapan saja dalam masa berlaku, dengan **constraint jarak minimum** dari `master_treatment.default_rentang_mulai_minggu`. Misal IPL min 4 minggu antar sesi. (Pertanyaan #2 → B)
- Diskon produk: flag eligible per produk + flat persen per tier. (Pertanyaan #3 → A)
- Transfer ke pasien lain: tidak boleh. (Pertanyaan #4 → A)

### G.5. Verifikasi paket/kuota oleh FO (tambahan dokter)

Saat FO check-in pasien member:
1. Sistem otomatis tampilkan panel "Paket & Kuota Aktif":
   - Membership tier + tgl expired
   - Daftar kuota tersedia bulan ini & total paket
   - Daftar rencana series treatment yang masih PENDING/SCHEDULED
2. FO **konfirmasi penggunaan**:
   - Klik "Pakai kuota X" → flag pasien akan eksekusi via kuota tersebut
   - Atau "Tidak pakai kuota, bayar normal" → flag membayar full
3. Saat treatment selesai → sistem auto-link `kunjungan_tindakan.id_kuota_member` ke kuota terpilih + `kuota.terpakai += 1`.

**Konsekuensi struktur:** Tambah kolom di `kunjungan_tindakan`:
- `id_kuota_member INT FK` (nullable) — link ke `pasien_membership_kuota` kalau pakai kuota.

## H. Iterasi Resep

| Topik | Keputusan |
|-------|-----------|
| Default iterasi | Per produk: tambah `master_produk.default_iterasi INT DEFAULT 0`. |
| Override default | Hanya role **Dokter, Owner, Superadmin** bisa override saat input resep. |
| Auto-create row | Saat dokter input resep produk dengan `default_iterasi > 0` (atau dokter set manual > 0), sistem auto-create row di `pasien_resep_iterasi`. |
| Masa berlaku iterasi | Default 6 bulan (`tgl_kadaluarsa = created_at + 6 months`). Bisa di-override per kasus oleh dokter. |
| Pasien beli OTC tanpa resep | Tetap bisa via flow normal (kasir langsung), tidak masuk ke `pasien_resep_iterasi`. |

## I. Format Nomor RM

- Format: `YYMMDD-NNN` — contoh `260427-001`.
- Counter reset harian.
- Implementasi anti-kolisi: `SELECT FOR UPDATE` saat ambil counter terakhir hari ini.
- Caveat: limit 999 pasien baru/hari. Re-evaluasi kalau klinik scale.

## J. Audit Log

Tabel baru `audit_log` mencatat semua aksi mutating yang sensitif:
- Login/logout
- Create/Update/Delete pada: pasien, kunjungan, transaksi, resep (terutama void), inventory_history (write-off), membership_history.
- Format: id_staf, aksi, tabel_target, id_target, data_lama (JSON), data_baru (JSON), ip_address, waktu.

## K. Halaman Master Setup (Owner/Superadmin only)

UI untuk semua master setup (Phase 1 minggu 6):
- Master Produk (CRUD + flag `eligible_member_discount`, `default_iterasi`)
- Master Treatment (CRUD + flag `butuh_otorisasi`, `default_rentang_mulai_minggu`, `default_rentang_akhir_minggu`)
- Master Bahan / inventory_stok (CRUD)
- Master Membership (tier, durasi, diskon, benefit, kuota treatment)
- Master Staf (Admin/Superadmin — CRUD + reset password + role assign)
- Treatment Komponen (formula bahan & alat per treatment)

## L. Bug Fixes dari Kode Saat Ini

| ID | Fix |
|----|-----|
| K1 | Hash password & PIN. |
| K2 | JWT auth. |
| K3 | Hapus `end_treatment` versi pertama (line 1347 di file lama), pakai versi enterprise (line 1470). |
| K4 | `transaksi_detail_produk` insert dengan `harga_satuan` & `subtotal` real (JOIN ke master_produk saat insert). |
| K5 | try/except wrap untuk rollback semua transaksi DB. |
| Status | `eksekusi_pembayaran` set status ke `ANTRI_OBAT` (kalau ada resep) atau `COMPLETED` (tanpa resep). Bukan `AMBIL_PRODUK`. |
| `get_rekap_shift` | Hapus `return` dobel (dead code). |

## M. Yang Dipertahankan dari Kode Dokter (DO NOT CHANGE LOGIC)

- Anchor shift kasir (`waktu_mulai_shift` reset hanya kalau beda tanggal)
- Bulletproof double-charge prevention di `kasir/tagihan`
- Smart trigger `end_treatment` → `ANTRI_BAYAR` saat semua treatment di kunjungan selesai
- PIN otorisasi untuk upsell `butuh_otorisasi=1`
- Auto potong stok BHP di `end_treatment` (versi enterprise) + `FOR UPDATE` lock
- Kalkulasi BMI + Body Fat Pollock 3-site (formula sudah benar)
- Kalkulator suggested order (AMC + UoM)
- Soft delete untuk medical record (alergi)
- Split payment (multi-method per transaksi)
- Auto-generate `no_rm` (format akan diubah ke `YYMMDD-NNN`)

---

## Phase Plan Final

| Phase | Lingkup | Estimasi |
|-------|---------|----------|
| **Phase 1 (8 minggu, MVP)** | Refactor + frontend HTMX + 2 tier membership (VIP/VVIP) + production deploy | 4 Mei – 27 Juni 2026 |
| **Phase 2** | 3 tier membership baru + bundling paket promo + module foto + booking online + kiosk + delivery + WA/Telegram notifikasi | TBD setelah Phase 1 stabil |
| **Phase 3** | AI integration (Gemini): skin analysis, USG kulit, SOAP smart assist, chat AI member | TBD |
| **Phase 4+** | Mobile app native, multi-cabang | TBD |

---

## Sign-off

- ✅ dr. Hansen — keputusan A-L sudah dikonfirmasi via diskusi 27 April 2026
- ✅ Claude — siap eksekusi Minggu 1 mulai 4 Mei 2026

Pertanyaan susulan dari dokter di tengah perjalanan tetap diterima — kita update dokumen ini sebagai living document.
