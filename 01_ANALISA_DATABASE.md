# Analisa Konsistensi Database `db_sehati`

> Review oleh: Claude (lead programmer)
> Tanggal: 27 April 2026
> Source: `Tables_in_db_sehati.txt`

Database sudah cukup matang untuk skala klinik kecil-menengah. Struktur tabelnya **logis** dan sudah merefleksikan alur klinik dengan baik. Tapi ada beberapa **masalah konsistensi** yang harus dibereskan sebelum kita mulai coding — kalau dibiarkan, akan jadi bug halus di kemudian hari.

Saya kelompokkan temuan jadi 3 tingkat keparahan:

- **🔴 KRITIS** — harus diperbaiki sebelum coding dimulai
- **🟡 PENTING** — sebaiknya diperbaiki di Phase 1
- **🟢 SARAN** — bisa ditunda ke Phase 2

---

## 🔴 MASALAH KRITIS

### 1. Foreign Key (FK) yang hilang atau tidak eksplisit

Beberapa kolom yang **secara logika adalah FK** tidak ditandai dengan `MUL` (key index) di skema. Ini bahaya karena MySQL tidak akan validasi referential integrity.

| Tabel | Kolom | Seharusnya FK ke | Status sekarang |
|-------|-------|------------------|-----------------|
| `kunjungan_resep` | `id_produk` | `master_produk.id_produk` | ❌ Tidak ada FK |
| `kunjungan_resep` | `id_kunjungan` | `kunjungan.id_kunjungan` | ❌ Tidak ada FK |
| `kunjungan_resep` | `id_staf_input` | `master_staf.id_staf` | ❌ Tidak ada FK |
| `kunjungan_resep` | `id_staf_void` | `master_staf.id_staf` | ❌ Tidak ada FK |
| `kunjungan_foto` | `id_kunjungan` | `kunjungan.id_kunjungan` | ❌ Tidak ada FK |
| `kunjungan_foto` | `id_pasien` | `pasien.id_pasien` | ❌ Tidak ada FK |
| `transaksi_kasir` | `id_staf_kasir` | `master_staf.id_staf` | ❌ Tidak ada FK |
| `pemeriksaan_klinis` | `id_staf_dokter` | `master_staf.id_staf` | ❌ Tidak ada FK |
| `pasien_rencana_treatment` | `id_kunjungan_eksekusi` | `kunjungan.id_kunjungan` | ❌ Tidak ada FK |

**Action:** Saya akan generate file SQL `migrations/001_add_missing_fks.sql` di minggu 1.

---

### 2. Denormalisasi: pakai `varchar` padahal ada master tabelnya

Ini lebih bahaya dari masalah #1. Kolom-kolom ini menyimpan **nama** (varchar), padahal seharusnya pakai **ID** dari master tabel:

| Tabel | Kolom (sekarang) | Seharusnya |
|-------|------------------|------------|
| `pasien_rencana_treatment` | `nama_tindakan VARCHAR(100)` | `id_treatment INT` FK → `master_treatment` |
| `pasien_resep_iterasi` | `nama_produk VARCHAR(100)` | `id_produk INT` FK → `master_produk` |

**Mengapa bahaya:**
- Kalau dokter rename treatment di `master_treatment`, data history jadi tidak konsisten.
- Tidak bisa join untuk laporan (misal "berapa kali treatment X dijual sebagai series?").
- Typo manual oleh staff = data rusak permanen.

**Action:** Saya akan tambahkan kolom `id_treatment` dan `id_produk`, **kolom varchar lama disimpan dulu** untuk backward compat. Migrasi data dilakukan setelah validasi.

---

### 3. Tipe data `transaksi_kasir` tidak konsisten

```
subtotal         INT
nominal_diskon   INT
total_tagihan    INT
```

Tapi di `transaksi_detail_produk`:
```
harga_satuan     DECIMAL(12,2)
subtotal         DECIMAL(12,2)
```

Dan di `master_produk`:
```
harga_jual       DECIMAL(12,2)
```

**Masalah:** Saat menghitung `subtotal_kasir = SUM(detail_produk.subtotal)`, hasilnya DECIMAL tapi harus disimpan ke INT — Rupiah pecahan bisa hilang. Untuk klinik kecantikan yang sering ada diskon membership %, ini bermasalah.

**Action:** Ubah ketiga kolom di `transaksi_kasir` jadi `DECIMAL(12,2)`.

---

### 4. `transaksi_kasir.rincian_tagihan TEXT` — denormalisasi berbahaya

Kolom ini menyimpan rincian tagihan dalam bentuk TEXT (bebas), padahal sudah ada:
- `transaksi_detail_produk` untuk produk
- `kunjungan_tindakan` untuk treatment

**Risiko:** Data dobel, bisa beda antara TEXT dan tabel detail. Susah di-query untuk laporan.

**Action:** Tinggalkan `rincian_tagihan` sebagai snapshot/backup string saja (untuk reprint struk persis seperti waktu cetak), tapi **sumber kebenaran** harus dari tabel detail. Atau hapus saja dan generate ulang dari detail saat reprint.

---

## 🟡 MASALAH PENTING

### 5. Stok tersimpan di 2 tempat — risk of inconsistency

```
master_produk.stok_terkini       (untuk produk retail)
inventory_stok.stok_gudang_utama (untuk bahan)
inventory_stok.stok_kabin        (untuk bahan)
```

Pertanyaan ke dokter:
- **Apakah `master_produk` (retail/cabin/alat) dan `inventory_stok` (bahan) dua hal yang berbeda?** Atau ada overlap?
- Kalau treatment pakai produk RETAIL juga (misal serum yang juga dijual), apakah stoknya dipotong dari `master_produk.stok_terkini` atau `inventory_stok`?

**Action:** Perlu klarifikasi dokter sebelum saya desain `inventory_service`. Saran saya: **pisahkan tegas** — `master_produk` untuk yang dijual ke pasien (POS), `inventory_stok` untuk bahan klinik (treatment). Kalau ada produk yang dipakai keduanya, harus ada logic mapping eksplisit.

---

### 6. Tidak ada tabel `master_membership`

`pasien.tipe_membership` adalah enum `('REGULAR','VIP','VVIP')`. Tapi:
- Berapa diskon untuk masing-masing tier? Tidak ada di DB.
- Apa benefit per tier (free product, free delivery, dll)? Tidak ada di DB.
- Berapa harga membership? Berapa lama berlaku? Tidak ada di DB.

**Sekarang kemungkinan di-hardcode di program** — tapi kalau dokter mau ubah diskon, harus suruh programmer ubah kode.

**Action:** Tambah tabel:
```sql
master_membership (
  id_membership INT PK,
  nama_tier VARCHAR(20),  -- REGULAR, VIP, VVIP
  diskon_treatment_persen DECIMAL(5,2),
  diskon_produk_persen DECIMAL(5,2),
  harga_member DECIMAL(12,2),
  durasi_bulan INT,
  benefit_list TEXT,  -- JSON: list of free products/services
  is_active TINYINT(1)
)
```

---

### 7. `master_treatment.id_staf` ambigu

Kolom ini ada di `master_treatment` tapi tidak jelas:
- Siapa yang ditunjuk? Pembuat treatment? Dokter penanggung jawab?
- Apa hanya satu staf yang boleh melakukan treatment ini?

Padahal `kunjungan_tindakan.id_staf_pelaksana` juga sudah ada untuk track siapa eksekusi.

**Action:** Tanya dokter. Kemungkinan rename jadi `id_staf_creator` (yang bikin entry master).

---

### 8. `master_treatment.role_pelaksana VARCHAR(50)` tidak konsisten dengan enum role

`master_staf.role` adalah ENUM. Tapi `master_treatment.role_pelaksana` adalah VARCHAR bebas. Bisa terjadi typo "Dokter" vs "dokter" vs "DOKTER".

**Action:** Ubah jadi enum sama, atau pakai SET untuk multi-role (misal treatment bisa dilakukan dokter ATAU perawat).

---

### 9. Tidak ada tabel `audit_log` / `activity_log`

Catatan dari dokter: *"tracing id dan timestamp selalu ada di semua database"* (untuk track FO yang batalin booking, dll). Sebagian sudah ada via `created_at`, tapi belum ada audit untuk **UPDATE** dan **DELETE** (kalau ada).

**Action:** Tambah tabel `audit_log`:
```sql
audit_log (
  id_log INT PK auto_increment,
  id_staf INT,
  aksi VARCHAR(50),     -- 'CREATE','UPDATE','DELETE','LOGIN','VOID'
  tabel_target VARCHAR(50),
  id_target INT,
  data_lama TEXT,       -- JSON snapshot before
  data_baru TEXT,       -- JSON snapshot after
  ip_address VARCHAR(45),
  waktu DATETIME DEFAULT CURRENT_TIMESTAMP
)
```

---

### 10. Tidak ada tabel untuk shift kasir / closing kasir

POS biasanya butuh:
- Shift open / shift close
- Saldo kas awal vs akhir
- Daftar transaksi per shift

Belum ada di skema. Padahal `master_staf.waktu_mulai_shift` ada, tapi tidak ada catatan shift complete-nya.

**Action:** Tambah tabel `shift_kasir` di Phase 1 minggu 5-6 (saat fitur kasir dibangun).

---

## 🟢 SARAN PENINGKATAN

### 11. Kurang index untuk query laporan

Untuk fitur laporan progress pasien & laporan harian kasir, query sering filter by `tgl_kunjungan`, `waktu_bayar`, `tgl_rencana`. Saran tambah composite index:

```sql
CREATE INDEX idx_kunjungan_pasien_tgl ON kunjungan(id_pasien, tgl_kunjungan);
CREATE INDEX idx_transaksi_waktu ON transaksi_kasir(waktu_bayar);
CREATE INDEX idx_booking_tgl_status ON jadwal_booking(tgl_rencana, status_booking);
CREATE INDEX idx_inventory_history_bahan ON inventory_history(id_bahan, waktu_mutasi);
```

### 12. Soft delete vs hard delete

Beberapa tabel pakai `is_active TINYINT(1)` (soft delete). Tapi tabel transaksi (`transaksi_kasir`, `kunjungan_resep`) tidak punya. Apakah transaksi yang divoid akan di-hard-delete?

Saran: jangan pernah hard delete data transaksi atau kunjungan. Pakai status (`PENDING/BATAL/DIBAYAR/VOIDED`).

### 13. Belum ada tabel untuk Phase 2/3

Fitur masa depan butuh tabel baru — saya catat sebagai backlog, **tidak dibuat sekarang**:

- `skin_analysis` — hasil AI Gemini (Phase 3)
- `usg_kulit` — data USG kulit + interpretasi AI (Phase 3)
- `chat_ai_session` — sesi chat AI member (Phase 3)
- `delivery_order` — pengiriman produk ke rumah member (Phase 2)
- `kiosk_registration_temp` — registrasi mandiri via kiosk (Phase 2)
- `webportal_user` — login pasien di website (Phase 2)

### 14. Naming consistency

Mayoritas tabel pakai bahasa Indonesia (`pasien`, `kunjungan`, `tindakan`). Tapi ada beberapa English (`booking`, `inventory`). Tidak masalah secara fungsional, tapi untuk konsistensi pertimbangkan rename jadi:
- `inventory_stok` → `bahan_stok`
- `inventory_history` → `bahan_mutasi`
- `jadwal_booking` → `jadwal_kunjungan` (atau biarkan)

**Action:** Skip rename — risk vs benefit tidak sepadan. Biarkan untuk konsistensi backward.

---

## Pertanyaan untuk dokter (perlu dijawab sebelum coding)

Saya susun pertanyaan kritis yang akan membentuk kode kita. Boleh dijawab nanti, tapi sebelum minggu 2:

1. **Inventory:** Apakah `master_produk` (retail) dan `inventory_stok` (bahan) **terpisah total**, atau ada produk yang termasuk dua-duanya?
2. **Membership diskon:** Berapa persen diskon REGULAR/VIP/VVIP saat ini? Apakah diskon flat atau ada syarat (min. transaksi, dll)?
3. **Series treatment:** Setelah dokter buat plan dengan rentang minggu, siapa yang reschedule? Sistem otomatis atau FO manual?
4. **Iterasi resep:** Apakah pasien bisa ambil resep iterasi tanpa kunjungan baru, atau tetap harus daftar di FO dulu?
5. **Up-selling:** Treatment apa saja yang `butuh_otorisasi=1` (perlu acc dokter)? Kasih daftar awal supaya saya seed data.
6. **Shift kasir:** Apakah ada saldo kas fisik (modal awal di laci kasir)? Bagaimana flow closing kasir saat ini?
7. **Login PIN vs Password:** Di `master_staf` ada `password_hash` dan `pin`. Mana yang dipakai? Atau dua-duanya (password untuk login, PIN untuk approval)?

---

## Kesimpulan

Database **siap dipakai** dengan catatan: 4 masalah kritis (#1–#4) harus diselesaikan di **minggu 1** sebelum coding service layer. Masalah penting (#5–#10) bisa diselesaikan paralel selama Phase 1. Saran (#11–#14) diserap ke roadmap atau dijadwalkan ke Phase 2.

Saya akan generate semua file migrasi SQL di minggu 1, dokter tinggal review & jalankan.
