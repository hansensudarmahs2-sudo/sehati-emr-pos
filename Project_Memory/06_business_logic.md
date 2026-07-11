# Business Logic — Aturan Operasional Klinik Sehati

> Sumber utama untuk AI reviewer catch blind spot. Aturan ini dari dr. Hansen langsung — sesuai pengalaman operasional klinik real.

---

## Alur Utama Pasien

```
Pasien datang
   ↓
FO daftarkan (baru / lama)
   ↓
Antri konsultasi
   ↓
Dokter SOAP (anamnesa, fisik, diagnosa)
   ↓
   ├──→ Plan treatment (single hari ini ATAU series untuk pertemuan berikut)
   └──→ Resep produk (single ATAU dengan iterasi untuk berulang)
   ↓
Status berubah otomatis berdasarkan output dokter:
   - Ada tindakan single hari ini → ANTRI_TREATMENT
   - Tidak ada tindakan → ANTRI_BAYAR
   ↓
(Bila ANTRI_TREATMENT) → Perawat handle ruang tindakan → END treatment → cek sisa
   - Masih ada sisa tindakan PENDING/PROSES → status tetap ON_TREATMENT
   - Sisa 0 → status → ANTRI_BAYAR
   ↓
Kasir hitung tagihan → terima pembayaran
   - Ada resep → ANTRI_OBAT
   - Tidak ada resep → COMPLETED
   ↓
(Bila ANTRI_OBAT) → Apotek serahkan → COMPLETED
```

---

## Aturan Spesifik (dari dr. Hansen)

### 1. Registrasi Pasien (oleh FO)

**Konvensional:**
- FO buka form, input data lengkap: demografi + alergi (wajib ditanya) + penyakit kronis (wajib) + antropometri (opsional).
- Generate `no_rm` baru format `YYMMDD-NNN` (counter reset harian, anti-kolisi via FOR UPDATE lock).
- Buat 1 row di tabel `kunjungan` dengan nomor antrian harian, status_antrian sesuai pilihan FO (`ANTRI_KONSULTASI`, `ANTRI_TREATMENT`, atau `ANTRI_BAYAR`).

**Pasien Lama:**
- FO cari pasien by `no_rm` ATAU `nama + nomor_telepon`.
- Konfirmasi identitas SOP manusia (di luar sistem).
- Buat row baru di `kunjungan` (tanpa buat pasien baru).
- Pilih tujuan: konsultasi / lanjut series treatment / beli produk bebas (iterasi).

### 2. Series Treatment

- **Sumber rencana:** `DOKTER_PLAN` (rencana dokter), `MEMBERSHIP` (paket member), `PROMO` (paket promo — placeholder Phase 2).
- **Bundling paket hanya untuk member.** Non-member tidak ada paket.
- **Tgl target per sesi** (bukan per paket): dari `master_treatment.default_rentang_mulai_minggu` & `default_rentang_akhir_minggu` (owner bisa override per pasien).
- **Expired keseluruhan paket:** Phase 1 set ke `2030-01-01` (effectively unlimited).
- **Track eksekusi:** kolom `id_kunjungan_eksekusi` di-fill saat eksekusi.
- **Transfer ke pasien lain:** TIDAK BOLEH di Phase 1. Mungkin via owner approval di Phase 2.

### 3. Membership

**Tier saat ini (Phase 1):** REGULAR (non-member), VIP, VVIP.

**Masa berlaku:** 12 bulan (default, bisa di-override di `master_membership.durasi_bulan`).

**Verifikasi oleh FO:** Saat pasien member check-in, FO konfirmasi penggunaan kuota:
- Sistem tampilkan kuota tersedia & paket aktif.
- FO klik "Pakai kuota X" → flag `id_kuota_member` di `kunjungan_tindakan` saat treatment dieksekusi.

**Benefit VIP saat ini (sesuai dr. Hansen):**
- Free konsultasi dokter (kasir auto-skip biaya konsul)
- 1× Basic Treatment per bulan (kuota BULANAN — hangus kalau tidak dipakai)
- 2× Laser Pico per 12 bulan total (kuota TOTAL_PAKET)
- 10% diskon treatment (hardcoded di kode lama, sekarang di `master_membership.diskon_treatment_persen`)
- 3% diskon produk **HANYA untuk produk dengan `eligible_member_discount=1`**

**Aturan Kuota:**
- **Bulanan:** Tidak terpakai bulan ini = HANGUS. Tidak akumulasi.
- **Total Paket:** Bebas kapan saja dalam 12 bulan, dengan **constraint jarak minimum** dari `master_treatment.default_rentang_mulai_minggu` (misal IPL min 4 minggu antar sesi).

### 4. Treatment Paralel

**Skenario:** Pasien sedang facial (oleh perawat) → dokter masuk ruangan, mulai peeling.

**Logic:**
- 1 pasien bisa punya N rows di `kunjungan_tindakan` dengan status `PROSES` bersamaan (paralel).
- Setiap end_treatment cek `COUNT(*) WHERE status IN ('PENDING','PROSES')` di kunjungan tersebut.
- Sisa 0 → status pasien → `ANTRI_BAYAR`.
- Sisa > 0 → status pasien tetap `ON_TREATMENT`.

**Tidak ada batasan jumlah treatment paralel per perawat** (sesuai dokter, ini fitur fleksibilitas).

### 5. Up-Selling di Ruang Tindakan

**Perawat dapat upsell treatment / produk saat pasien sudah on treatment.**

**Treatment dengan `butuh_otorisasi=1`** (misal: Botox, Filler, PRP, Laser CO2, Chemical Peel dalam):
- Perawat **TIDAK BOLEH** langsung add ke keranjang.
- Wajib input **PIN dokter** untuk otorisasi.
- Backend verify PIN match dengan `master_staf.pin` (bcrypt).

**Treatment dengan `butuh_otorisasi=0`** (Facial, Microdermabrasi):
- Perawat langsung add tanpa otorisasi.

### 6. Start/End Treatment di Ruang Tindakan

**Start:**
- Perawat (atau dokter) klik START → update `kunjungan_tindakan.status_tindakan='PROSES'`, `waktu_mulai=NOW()`, `id_staf_pelaksana=current_user.id_staf`.

**End:**
- Klik END → update `status_tindakan='SELESAI'`, `waktu_selesai=NOW()`.
- **Auto potong stok BHP:**
  - Loop `treatment_komponen WHERE id_treatment=X AND kategori='BAHAN'`.
  - Untuk tiap bahan: kurangi `inventory_stok.stok_kabin` sebanyak `qty`.
  - Catat 1 row di `inventory_history` dengan `jenis_mutasi='TINDAKAN'`.
- Pakai `SELECT FOR UPDATE` untuk concurrency safety.
- **Stok boleh minus** (sesuai filosofi dokter — operasional jangan diblok). Tapi ada warning + dashboard "stok bermasalah" untuk admin.

### 7. Iterasi Resep (Resep Berulang)

**Konsep:** Beberapa produk (misal krim malam X) boleh ditebus berulang tanpa harus konsul dokter lagi.

**Setup:**
- `master_produk.default_iterasi` = berapa kali maksimal (0 = no iterasi).
- Dokter bisa override per resep saat input (hanya role Dokter/Owner/Superadmin yang bisa override).

**Flow ambil iterasi:**
1. FO daftarkan pasien (existing) → tujuan: ambil iterasi.
2. Status pasien langsung `ANTRI_BAYAR` (skip konsultasi).
3. Kasir lihat keranjang dari `pasien_resep_iterasi` aktif.
4. Pasien bayar → `sudah_diambil += 1`.
5. Kalau `sudah_diambil >= kuota_maksimal` OR lewat `tgl_kadaluarsa` → `is_active=0`.

**Masa berlaku default iterasi:** 6 bulan dari created_at.

### 8. Kasir / POS

**Tagihan otomatis dihitung dari:**
- `kunjungan_tindakan` yang `status='SELESAI'` × `master_treatment.harga`
- `kunjungan_resep` yang `status_item='PENDING'` × `master_produk.harga_jual` × `qty`

**Diskon membership:**
- Untuk treatment: % dari subtotal treatment (sesuai `master_membership.diskon_treatment_persen`)
- Untuk produk: % dari subtotal produk **HANYA** untuk produk `eligible_member_discount=1`
- Kuota member free → harga tindakan = 0 (gratis), tidak masuk diskon

**Bulletproof double-charge prevention:**
- Sebelum hitung tagihan, cek apakah `kunjungan` ini sudah ada row di `transaksi_kasir`.
- Kalau iya → return "TAGIHAN SUDAH LUNAS" + waktu bayar.

**Split Payment:**
- Bisa N metode bayar per transaksi (Tunai + QRIS + Debit + Transfer).
- `transaksi_pembayaran` N rows per `transaksi_kasir`.

**Void Item:**
- Hanya bisa item dengan `status_item='PENDING'`.
- Wajib otorisasi: input username + password manager (Admin/Superadmin/Owner).
- Update `status_item='BATAL'`, catat `id_staf_void` & `waktu_void`.

### 9. Apotek

**Antrian:** Pasien dengan `kunjungan.status_antrian='ANTRI_OBAT'` (setelah bayar kasir, ada resep).

**Serahkan Obat:**
- Loop `kunjungan_resep WHERE id_kunjungan=X AND status_item='DIBAYAR'`.
- Untuk tiap row: kurangi stok di `inventory_stok` (or `master_produk.stok_terkini` untuk produk jadi).
- Catat di `inventory_history` dengan `jenis_mutasi='PENJUALAN'`.
- Update `kunjungan.status_antrian='COMPLETED'`.

**Write-Off (Stok Rusak/Expired):**
- Apoteker buang stok rusak → catat di `inventory_history` dengan `jenis_mutasi='EXPIRED'`/`'RUSAK'`/`'PENYESUAIAN'`.
- Wajib `keterangan` (alasan).
- Owner approval untuk qty besar (TBD aturan exact).

**Repacking (Bahan → Produk Jadi):**
- HANYA apoteker yang bisa.
- Modul terpisah dari main eMR/POS flow (di Phase 1 minggu 5-6).
- Misal: 1L Serum X → 33 botol 30ml.
- Otomatis kurangi `inventory_stok` (bahan source) + tambah `master_produk.stok_terkini` (hasil pack).

### 10. Anchor Shift Kasir

**Penting untuk rekap shift:**
- Saat login, `master_staf.waktu_mulai_shift` **HANYA** di-update kalau tanggal-nya beda dari hari ini.
- Login ulang di hari sama TIDAK reset shift.
- Saat logout, `waktu_mulai_shift` TIDAK di-reset (tetap utuh).
- Endpoint `/kasir/rekap-shift` filter transaksi `WHERE waktu_bayar >= waktu_mulai_shift`.

### 11. Audit Log

**Wajib catat di `audit_log` untuk aksi sensitif:**
- Login (sukses & gagal)
- Logout
- Void item resep
- Write-off stok
- Reset password / PIN
- Penyesuaian stok minus (oleh admin)
- Delete medical record (soft delete alergi)
- Activate/deactivate user

**Snapshot:**
- `data_lama` (JSON) = state sebelum aksi
- `data_baru` (JSON) = state setelah aksi
- IP, user agent, endpoint, http method auto-filled dari Request

### 12. Status Antrian Final Enum

```
ANTRI_KONSULTASI → KONSULTASI → ANTRI_TREATMENT → ON_TREATMENT 
→ ANTRI_BAYAR → ANTRI_OBAT → COMPLETED
                       ↘ COMPLETED (tanpa resep)

BATAL: dari status apa pun. Hanya FO/Owner/Superadmin.
```

**Note:** `AMBIL_PRODUK` (yang ada di kode lama) DIHAPUS. Pakai `ANTRI_OBAT` saja.

---

## Hal-Hal Khusus dari dr. Hansen

### 13. Pasien Sensitif

Field `pemeriksaan_klinis.saran_treatment`:
- Catatan untuk PERAWAT saat eksekusi treatment.
- Contoh: "hati-hati ekstraksi, pasien sensitif nyeri".
- Tampil sebagai panel warning kuning di UI ruang tindakan.

Field `pemeriksaan_klinis.saran_produk`:
- Instruksi tambahan untuk PASIEN saat pakai produk.
- Contoh: "tipis-tipis selama 1 minggu pertama".
- Tercetak di struk apotek bersama aturan_pakai.

### 14. Soft Delete Medical Record

**Filosofi EMR:** Data medis pasien TIDAK BOLEH dihapus fisik.

- Alergi & penyakit kronis → `is_active=0` (soft delete).
- Transaksi → `status='BATAL'`, jangan DELETE row.
- Inventory_history → append-only, jangan UPDATE/DELETE row.

### 15. Stok Minus

**Sesuai filosofi dokter:** Operasional jangan diblok kalau ada human error input stok.

- Stok bisa minus → tetap eksekusi, tapi return warning di response.
- Dashboard admin/owner tampilkan "Stok Bermasalah" (banner kuning saat login).
- Penyelesaian via Stock Opname: admin input qty fisik aktual → sistem catat selisih sebagai `PENYESUAIAN` dengan keterangan wajib.
- Re-confirm password admin diperlukan untuk Stock Opname.

### 16. Produk Repacking vs Produk Jadi

**Produk Repacking** (sabun, toner, milk cleanser):
- `master_produk.id_bahan_sumber` (FK nullable) → `inventory_stok`.
- `master_produk.qty_per_unit_produk` = ml per botol (misal 30ml).
- Saat dijual 1 botol → otomatis potong 30ml dari `inventory_stok`.

**Produk Jadi dari Distributor** (krim merk X kemasan original):
- `master_produk.id_bahan_sumber = NULL`.
- Stok di `master_produk.stok_terkini` langsung.
- Pembelian dari distributor → tambah `stok_terkini` (Phase 1 minggu 5-6 — modul pembelian).

### 17. Pemeriksaan Antropometri & Kalkulasi Klinis

**Pengukuran:**
- Berat & tinggi badan
- Tekanan darah (VARCHAR, format "120/80")
- 3-site skinfold (titik 1, 2, 3) untuk Pollock
- Lingkar perut
- Suhu tubuh (opsional)

**Kalkulasi (di app/core/kalkulasi_klinis.py — sudah ada di kode dokter, akan di-pindah):**
- BMI = berat_kg / (tinggi_m)²
- Body Fat % = (Jackson-Pollock 3-site formula based on density + Siri equation)
  - Pria: density = 1.10938 − 0.0008267·Σ + 0.0000016·Σ² − 0.0002574·age
  - Wanita: density = 1.0994921 − 0.0009929·Σ + 0.0000023·Σ² − 0.0001392·age
  - Body Fat % = 495/density − 450
- Lean Mass % = 100 − Body Fat %

### 18. Form SOAP Dokter (Layout Mockup dari Dokter)

Header pasien tampilkan:
- **Grid Kiri**: Nama, usia, jenis kelamin + hover detail (no_rm, membership, telepon, alamat)
- **Grid Tengah**: Total alergi + display alergi terbaru + daftar lengkap saat hover
- **Grid Kanan**: Berat, tinggi, BMI, Fat %, Lean %, tekanan darah, tgl ukur

4-Cardbox di bawah header:
- **Kiri Atas**: Riwayat SOAP (anamnesa & diagnosa ringkas, limit 10)
- **Kiri Bawah**: Riwayat pembelian produk (limit 10, status DIBAYAR)
- **Kanan Atas**: Foto before/after (limit 6)
- **Kanan Bawah**: Riwayat treatment (limit 10, status SELESAI)

Form input dokter:
- Anamnesa, PF, Diagnosa (text area)
- Keranjang Tindakan: pilih dari `master_treatment` + flag single/series + jumlah sesi kalau series
- Keranjang Resep: pilih dari `master_produk` + qty + aturan_pakai
- Saran treatment (catatan untuk perawat)
- Saran produk (instruksi untuk pasien)

---

## Edge Cases Worth Knowing

1. **Pasien tanpa nomor telepon** → field kosong OK, tidak validate format.
2. **Pasien tanpa tanggal lahir** → BMI/Body Fat tidak bisa dihitung (butuh umur). Skip kalkulasi, tampilkan tanda "—".
3. **Treatment selesai tapi BHP habis** → tetap selesai, stok jadi minus, warning ke admin.
4. **Member expired di tengah series treatment** → sisa kuota hangus, sisa sesi tetap bisa dilakukan tapi bayar normal.
5. **Pasien batal di tengah** → FO ubah status ke `BATAL`, treatment yang sudah PROSES tetap selesai sampai END (BHP yang sudah kepakai tidak refund).
6. **Login dari 2 device** → logout di device A juga logout di device B (karena cek `is_logged_in` di DB). Bisa di-revisit nanti kalau perlu multi-session.

---

## Open Questions for AI Reviewers

Bila Anda AI reviewer, mohon perhatikan:

1. **Apakah aturan kuota member benar?** — VIP 1× facial/bulan hangus. Apakah ada edge case yang missed?
2. **Repacking workflow** — apakah ada race condition saat 2 apoteker repack bahan sama bersamaan?
3. **Treatment paralel** — apakah ada race condition di smart trigger `COUNT(status IN PENDING/PROSES)`?
4. **No_rm counter** — sudah pakai FOR UPDATE lock. Apakah cukup aman untuk concurrent insert?
5. **Audit log** — apakah ada aksi sensitif yang missed dari list di atas?
6. **Soft delete** — apakah ada tabel lain selain alergi/penyakit yang seharusnya soft delete?
7. **JWT 6 jam expiry** — terlalu lama? Trade-off antara UX (re-login bolak-balik) vs security.

Komentar atau koreksi sangat welcome.
