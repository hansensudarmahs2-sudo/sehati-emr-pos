# Smoke Test Checklist — Post Sesi 10 Juni 2026

**Tujuan**: Validasi regression setelah marathon sesi 10 Juni 2026 (#364 Void Pembayaran + 4 side bug + Cancel Antrian audit + housekeeping).

**Cara pakai**:
- Login per role sesuai instruksi
- Centang `[x]` kalau lulus, `[!]` kalau ada bug (catat di section "Bug Findings" di bawah)
- Skip kalau role tidak ada / fitur tidak relevan untuk klinik Bapak

**Waktu estimasi**: ~1-1.5 jam manual

---

## 🔧 Pre-Flight

- [ ] Uvicorn fresh restart (Ctrl+C → `uvicorn app.main:app --reload`)
- [ ] Browser hard refresh (Ctrl+Shift+R) untuk clear cache
- [ ] Logout dari semua session lama
- [ ] Buka DevTools (F12) → tab Network → centang **Disable cache** (sambil DevTools terbuka)

---

## 1️⃣ ROLE: Owner (test paling banyak karena dashboard + reports baru)

**Login**: Owner

### A. Dashboard
- [ ] Buka `/web/dashboard` → page load tanpa error
- [ ] Section KPI: 4 tile (Omzet, Pasien, Kunjungan, Tindakan Selesai) — angka masuk akal
- [ ] Section "Antrian Per Tahap" — bar chart visible
- [ ] Section "Alerts" — stok urgent + PO outstanding + opname draft (kalau ada)
- [ ] Section "Kunjungan Terakhir Hari Ini" — tabel 5 row terbaru
- [ ] **🆕 Section "Void Pembayaran Hari Ini"** — muncul (kalau Bapak ada void hari ini)
  - [ ] 3 stat tile: Jumlah / Total Nominal / Late Void count
  - [ ] Horizontal bar breakdown per reason
  - [ ] Link "Lihat Laporan Lengkap →" jump ke `/web/reports/void`
  - [ ] **Empty state**: kalau tidak ada void, tampil "✅ Tidak ada void hari ini"

### B. Menu Sidebar
- [ ] Group **Operasional**: Pasien, Pasien Baru, Antrian Hari Ini, **Kasir/POS**, **🆕 Cari Transaksi**, Apotek
- [ ] Group **Klinis**: Antrian Dokter, Ruang Tindakan
- [ ] Group **Pengadaan**: Pemesanan, Opname, Mutasi
- [ ] Group **Master Data**: Treatment, Bahan, Produk
- [ ] Group **Manajemen**: Staf, Reports, Export
- [ ] Group **Settings**: Settings Klinik
- [ ] Group **Akun**: Profil & Password

### C. Reports Landing
- [ ] Buka `/web/reports` → card grid muncul
- [ ] Card "Omzet Bulanan" visible
- [ ] Card "Top Treatment" visible
- [ ] Card "Kinerja Dokter" visible
- [ ] Card "Rekap Kasir" visible (Owner bisa lihat semua kasir)
- [ ] **🆕 Card "Void Pembayaran"** visible (merah dengan icon ⚠)
- [ ] Card "Audit Log Viewer" visible

### D. Reports Void (Phase 6 baru)
- [ ] Klik card "Void Pembayaran" → `/web/reports/void` load tanpa error
- [ ] Filter card: 5 field (Dari, Sampai, Alasan Void, Kasir ID, Per Halaman)
- [ ] Default rentang: 7 hari terakhir (kalau buka pertama)
- [ ] 3 summary tile: Jumlah / Total Nominal / Late Void count
- [ ] Tabel: 9 kolom (Trx, Void At, Pasien, Total, Reason, Note, Kasir, Voider, Late)
- [ ] **Test filter alasan**: pilih SALAH_INPUT → submit → hanya void dengan reason SALAH_INPUT muncul
- [ ] **Test filter kasir kosong**: submit dengan Kasir ID kosong → tidak error 422 (BUG-RV2 fix)
- [ ] **Test filter kasir terisi**: ketik ID kasir (mis. 5) → submit → filtered
- [ ] **Test Reset button**: klik Reset → kembali ke default tanpa filter
- [ ] **Test pagination**: kalau ada > 100 entries, klik Next → halaman 2 muncul
- [ ] **Test Export CSV**: klik "⬇ Export CSV" → download `void_report_YYYY-MM-DD_to_YYYY-MM-DD.csv`
- [ ] Open CSV di Excel → header + data lengkap (13 kolom)
- [ ] **Test link Trx number**: klik `#622` → jump ke `/web/kasir/tagihan/{id_kunjungan}` (detail tagihan dengan badge VOID)

### E. Reports Audit Log
- [ ] Buka `/web/reports/audit-log` → load tanpa error
- [ ] **Test filter id_staf kosong**: submit tanpa isi User → tidak error 422 (BUG-RV2 fix)
- [ ] Filter Aksi: ketik "BATAL_ANTRIAN" → muncul entries kemarin
- [ ] Filter Aksi: ketik "VOID_TRANSAKSI" → muncul entries void
- [ ] Detail row: data_lama/data_baru JSON terlihat

### F. Kasir / Cari Transaksi (Phase 7)
- [ ] Buka `/web/kasir/cari-transaksi` (lewat menu Operasional)
- [ ] Default 7 hari terakhir → tabel populated
- [ ] Card kuning info: "Sebagai Owner, Bapak bisa Force Void sampai 7 hari lalu"
- [ ] Row BAYAR day 0-7 → ada button **⚡ Force Void**
- [ ] Row VOID → tidak ada Force Void button, tampil status VOID
- [ ] **Klik Detail** pada row → buka `/web/kasir/tagihan/{id_kunjungan}`

### G. Detail Tagihan dari sisi Owner (Phase 4 + 7)
- [ ] **Buka detail transaksi BAYAR hari ini** (yang belum di-void): muncul card kuning "Force Void Available (Admin Override)"
- [ ] **Buka detail transaksi BAYAR 3 hari lalu**: muncul card kuning "Force Past-Day Void Available"
- [ ] **Buka detail transaksi VOID**: badge "TRANSAKSI VOID" merah + warning card lengkap (alasan + catatan + oleh + waktu) + button "Cetak Nota Void (A5)" merah
- [ ] **Klik Cetak Nota Void**: page nota muncul dengan watermark "VOID" diagonal + banner info void

### H. Settings Klinik
- [ ] Buka `/web/settings/klinik`
- [ ] Form load: nama klinik, alamat, no telepon
- [ ] **JANGAN ubah apapun** (kecuali Bapak mau test)

### I. Manajemen Staf
- [ ] Buka `/web/staf` → list staf load
- [ ] Klik 1 staf → detail page muncul
- [ ] **Test toggle Nonaktifkan** (BUG-T3 fix): pilih staf bukan Bapak → klik Nonaktifkan → status berubah ke "Non-Aktif" badge merah
- [ ] **Test Aktifkan Kembali** staf yang baru di-nonaktif → status balik Aktif

---

## 2️⃣ ROLE: FO

**Login**: FO

### A. Dashboard
- [ ] Buka `/web/dashboard` → KPI FO (Pasien Baru, Antrian Konsultasi, dll)
- [ ] Section Antrian Per Tahap visible
- [ ] Section "Akses Cepat" (shortcuts) visible

### B. Daftar Pasien Baru (4-step wizard)
- [ ] Buka `/web/pasien/baru` (atau dari shortcut)
- [ ] Step 1 → input nama + no telp + tanggal lahir → Selanjutnya
- [ ] Step 2 → alamat + sumber referensi → Selanjutnya
- [ ] Step 3 → alergi (boleh kosong) → Selanjutnya
- [ ] Step 4 → review + **Simpan & Daftarkan ke Antrian Konsultasi**
- [ ] Verify: redirect ke antrian, pasien muncul dengan status ANTRI_KONSULTASI
- [ ] **Test pilih dokter** (FO-ASSIGN-DOKTER #329): dropdown dokter muncul, pilih 1 → tersimpan

### C. Search Pasien + Tambah Antrian
- [ ] Buka `/web/pasien` → ketik nama pasien existing → search result muncul
- [ ] Klik dropdown **+Antrian** → muncul opsi konsultasi + opsi series (kalau ada) + **🛒 Beli Produk (tanpa konsul)**

### D. **BUG-T4 Test — FO Beli Produk**
- [ ] Klik **🛒 Beli Produk (tanpa konsul)** dari dropdown
- [ ] Form pilih produk muncul (Tom Select searchable dropdown)
- [ ] Pilih produk + qty + aturan pakai → Submit
- [ ] **Expected**: redirect ke `/web/kunjungan?ok=Pasien+didaftarkan+beli+produk...` 
- [ ] **JANGAN muncul "null"** seperti bug sebelumnya
- [ ] Verify di antrian hari ini: pasien muncul dengan status ANTRI_BAYAR

### E. Antrian Hari Ini
- [ ] Buka `/web/kunjungan` → tabel pasien hari ini
- [ ] Auto-refresh 10 detik
- [ ] **Test Ubah Status** dropdown per row
- [ ] **🆕 Test Batal Antrian** (Cancel Antrian audit trail):
  - [ ] Klik tombol Batal pada 1 pasien → modal "Batalkan Antrian" muncul
  - [ ] Submit dengan catatan kosong → HTML5 required validation block
  - [ ] Isi "ab" (2 char) → klik submit → alert "Catatan minimal 5 karakter"
  - [ ] Isi "pasien telepon batal" (≥ 5 char) → submit → confirm dialog → OK
  - [ ] Redirect ke antrian dengan flash "Kunjungan dibatalkan"
  - [ ] Pasien hilang dari antrian aktif
- [ ] **Verify audit log** (lewat Owner login):
  ```sql
  SELECT id_log, aksi, JSON_EXTRACT(data_baru,'$.catatan_fo') AS catatan, keterangan, waktu 
  FROM audit_log WHERE aksi = 'BATAL_ANTRIAN' ORDER BY id_log DESC LIMIT 3\G
  ```

### F. Detail Pasien
- [ ] Klik nama pasien dari search atau antrian → `/web/pasien/{id}` load
- [ ] Header: foto + nama + no_rm + tipe membership
- [ ] Section antropometri (kalau ada data)
- [ ] Section riwayat kunjungan
- [ ] Link "Riwayat Lengkap" → buka riwayat page

---

## 3️⃣ ROLE: Dokter (BUG-T1 fix)

**Login**: Dokter

### A. Antrian Dokter
- [ ] Buka `/web/dokter/antrian` → list pasien yang di-assign ke dokter ini (atau semua kalau no scoping)
- [ ] Pasien dengan status ANTRI_KONSULTASI ada tombol **Konsultasi**

### B. **BUG-T1 Test — Mulai Konsultasi**
- [ ] Klik **Konsultasi** pada pasien antrian
- [ ] **Expected**: SOAP form muncul TANPA error 500 "Unknown column updated_at"
- [ ] Form: keluhan, anamnesa, pemeriksaan fisik, diagnosa, tindakan multi-row, resep multi-row
- [ ] Pilih treatment (Tom Select searchable)
- [ ] Pilih produk resep
- [ ] Submit → redirect ke antrian dengan status pasien jadi KONSULTASI

### C. Ubah Konsul
- [ ] Cari pasien yang sudah konsul tadi → klik **Ubah Konsul**
- [ ] Form populated dengan data sebelumnya
- [ ] Edit + submit → terupdate

### D. Cetak Resume SOAP (existing fitur)
- [ ] Lewat `/web/pasien/{id}/riwayat` → klik tombol Cetak Resume per SOAP entry
- [ ] Page cetak A5 dengan SOAP + tindakan + resep + ttd dokter

---

## 4️⃣ ROLE: Perawat (BUG-T1 fix)

**Login**: Perawat

### A. Ruang Tindakan / Antrian
- [ ] Buka `/web/ruang-tindakan/antrian` → list pasien ANTRI_TREATMENT

### B. **BUG-T1 Test — Kerjakan Tindakan**
- [ ] Klik **Kerjakan** pada pasien
- [ ] **Expected**: page tindakan muncul TANPA error 500 "Unknown column updated_at"
- [ ] Detail kunjungan + list tindakan
- [ ] Klik Start Tindakan → waktu_mulai tercatat
- [ ] Klik End Tindakan → waktu_selesai + status SELESAI

### C. Upsell Tindakan
- [ ] Pada page tindakan, klik **+ Upsell** → modal terbuka
- [ ] Pilih treatment + isi PIN dokter
- [ ] Submit → tindakan baru ditambahkan

---

## 5️⃣ ROLE: Kasir (banyak ke-touch sesi ini)

**Login**: Kasir

### A. Antrian Kasir
- [ ] Buka `/web/kasir/antrian`
- [ ] List pasien ANTRI_BAYAR
- [ ] Riwayat Bayar Hari Ini (section bawah) — tampil transaksi yang sudah lunas hari ini

### B. Proses Pembayaran Normal (regression test!)
- [ ] Klik 1 pasien ANTRI_BAYAR → buka `/web/kasir/tagihan/{id_kunjungan}`
- [ ] Sticky header card: nama + no_rm + REGULAR/VIP/VVIP badge
- [ ] Section Tindakan + Produk/Resep
- [ ] Section Ringkasan Biaya
- [ ] Form Pembayaran:
  - [ ] Default 1 row metode TUNAI dengan auto-fill nominal = total
  - [ ] Klik **+ Tambah Pembayaran (Split)** → row baru
- [ ] **Test Void Per Item** (sebelum bayar):
  - [ ] Klik tombol **Void** pada 1 produk PENDING
  - [ ] Modal "Batalkan Item Resep" muncul (NO PIN field, SYNC-V1)
  - [ ] Pilih reason + ketik catatan ≥ 5 char → Submit
  - [ ] Status produk → BATAL, opacity dim, tagihan berkurang
- [ ] Bayar dengan nominal cukup → klik "✓ Proses Pembayaran"
- [ ] **Expected**: redirect ke `/web/kasir/bayar/sukses/{id_transaksi}` dengan auto-print A5 tab

### C. Void Transaksi Same-Day
- [ ] Di halaman Pembayaran Berhasil, klik **Void Transaksi**
- [ ] Modal muncul: dropdown 6 reason + catatan + per-item checkbox reverse stok
- [ ] **Test validation**: pilih SALAH_INPUT + catatan "ab" → alert
- [ ] Isi catatan valid → confirm → redirect ke `/web/kasir/antrian` flash hijau
- [ ] **Verify**: kasir_tagihan page nanti tampil badge "TRANSAKSI VOID"

### D. Cetak Nota
- [ ] Klik **Cetak Ulang (A5)** → page nota A5 muncul (untuk transaksi BAYAR: normal, untuk VOID: dengan watermark merah)

---

## 6️⃣ ROLE: Apoteker

**Login**: Apoteker

### A. Antrian Apotek
- [ ] Buka `/web/apotek` → list pasien ANTRI_OBAT dengan resep DIBAYAR
- [ ] **CRITICAL**: pasien yang transaksi-nya VOID **TIDAK MUNCUL** lagi (cascade FLOW-V6)

### B. Serahkan Obat
- [ ] Klik salah satu pasien → detail resep
- [ ] Klik Serahkan → status item → DISERAHKAN, kunjungan → COMPLETED

### C. Suggested Order
- [ ] Buka menu Suggested Order → list produk yang stok < minimal
- [ ] Klik "Buat PO" → redirect ke form Pemesanan dengan prefill

---

## 7️⃣ ROLE: Admin (BUG-T2 fix)

**Login**: Admin

### A. Dashboard Admin
- [ ] KPI tampil (4 tile)
- [ ] Tidak ada void section (Admin tidak melihat omzet)

### B. **BUG-T2 Test — Tambah Komponen Treatment**
- [ ] Buka `/web/master/treatment` → klik salah satu treatment → edit
- [ ] Scroll ke section Komponen (BHP / Alat)
- [ ] Form Tambah Komponen: pilih bahan + qty + kategori (BAHAN/ALAT)
- [ ] Submit → **Expected**: komponen tersimpan, TIDAK error "missing argument 'kategori'"

### C. Master Bahan
- [ ] CRUD bahan jalan

### D. Cari Transaksi (Admin limit 3 hari)
- [ ] Buka `/web/kasir/cari-transaksi`
- [ ] Card info: "Sebagai Admin, Bapak bisa Force Void sampai 3 hari lalu"
- [ ] Transaksi day 0-3 BAYAR → ada Force Void button
- [ ] Transaksi day 4+ BAYAR → TIDAK ada Force Void button

---

## 8️⃣ ROLE: Superadmin

**Login**: Superadmin

### A. Semua menu sama dengan Owner kecuali tanpa Export module
- [ ] Verify menu structure
- [ ] Buka dashboard → void section juga muncul (Owner+Superadmin)

---

## 9️⃣ ROLE: Purchasing

**Login**: Purchasing

### A. Menu terbatas
- [ ] Hanya group Pengadaan: Pemesanan, Opname, Mutasi
- [ ] Akses pasien/kasir/apotek → 403 atau menu tidak muncul

---

## 🐛 Bug Findings

Catat di sini bug yang ditemukan saat smoke test:

```
[Bug 1]
Role:
Halaman:
Step reproduce:
Expected:
Actual:
Severity (Low/Med/High/Critical):

[Bug 2]
...
```

---

## ✅ Sign-off

Setelah selesai semua section:
- [ ] Total checklist passed: __ / __
- [ ] Bug found: __ items
- [ ] Severity distribution: Critical __, High __, Med __, Low __
- [ ] **Production-ready confirmation**: ☐ YES / ☐ NO (jelaskan di catatan bawah)

**Tanggal test**: ___________  
**Tester**: ___________

---

## 📋 Notes untuk Claude

Kalau Bapak temukan bug saat smoke test, kabari saya dengan format:
- Role + halaman
- Step reproduce (1, 2, 3, ...)
- Screenshot kalau ada
- Severity perkiraan

Saya akan fix urutan dari Critical → High → Med → Low. Kalau Critical block flow, kita fix dulu sebelum lanjut.
