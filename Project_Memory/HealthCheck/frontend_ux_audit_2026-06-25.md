# Frontend / UX Audit — Live (Chrome DevTools MCP)

**Tanggal:** 2026-06-25
**Metode:** Audit live via Chrome DevTools MCP (snapshot a11y tree, screenshot, console, network, performance trace)
**Login:** owner1 (Owner) — akses hampir semua halaman
**Scope:** Owner (dashboard + reports), FO (wizard daftar), Kasir (antrian/POS), Dokter (antrian)
**Catatan data:** Hari audit antrian kosong (tidak ada aktivitas 25 Jun), jadi alur dalam (SOAP form, halaman tagihan, void) belum bisa di-audit visual — perlu pasien di antrian. Lihat "Keterbatasan".

---

## Ringkasan Eksekutif

Secara umum **UI rapi, konsisten, dan profesional** — design language seragam (card rounded, color-coded per status, ikon jelas), empty state ramah, information architecture sidebar tertata baik. Performa lokal **sangat baik** (LCP 260ms, CLS 0.00). 

Yang perlu diperhatikan terutama soal **kesiapan produksi & reliabilitas**, bukan tampilan. Tiga isu paling penting: ketergantungan CDN eksternal (single point of failure), Tailwind mode CDN (bukan production), dan satu bug kosmetik role label yang muncul di hampir semua halaman.

---

## 🔴 Prioritas Tinggi (Reliabilitas / Produksi)

### 1. Semua aset frontend dari CDN eksternal — single point of failure
HTMX (unpkg), Tailwind (cdn.tailwindcss.com), Tom Select (jsdelivr) semua di-load dari internet.
**Risiko:** internet klinik putus/lambat → UI rusak (tanpa styling), interaktivitas mati (HTMX), dropdown searchable mati (Tom Select). Untuk POS klinik yang harus jalan andal, ini blind spot kritis.
**Rekomendasi:** self-host ketiga library (vendor lokal di `/static/`). Sekalian hilangkan ketergantungan internet untuk operasional inti.

### 2. Tailwind dipakai mode CDN (runtime compile) — bukan production
Console warning eksplisit di **setiap halaman**: *"cdn.tailwindcss.com should not be used in production."*
**Dampak:** Tailwind compile di browser saat load (render delay ~246ms dari trace), JS besar, butuh internet.
**Rekomendasi:** build Tailwind via CLI/PostCSS jadi 1 file CSS statis kecil. Masuk akal digabung dengan B3 Deployment Guide.

---

## 🟡 Prioritas Menengah (Polish / Aksesibilitas)

### 3. Bug kosmetik: role tampil "StafRoleEnum.OWNER"
Di hampir semua halaman (header kanan-atas + kartu user sidebar) role di-render sebagai raw Python enum `StafRoleEnum.OWNER`, bukan `Owner`.
**Anomali:** Dashboard menampilkan `Owner` dengan benar — berarti shell layout bersama pakai `user.role` (enum object) sedangkan dashboard pakai `user.role.value`. Inkonsistensi variabel template.
**Dampak:** kelihatan tidak rapi di mata user; menandakan kelas bug yang sama bisa muncul di tempat lain yang render role.
**Rekomendasi:** seragamkan ke `.value` (atau `.name.title()`) di `_shared.py` shell context. Fix 1 tempat → semua halaman ikut benar.

### 4. Aksesibilitas: 17 form field tanpa label terkait (wizard FO)
Console issue di halaman Daftar Pasien Baru: *"No label associated with a form field (count: 17)."* Label kelihatan visual tapi tidak ter-link programatik (`<label for>` / `id` / `aria-label`).
**Dampak:** screen reader tidak bisa asosiasikan label; klik teks label tidak fokus ke input. Kemungkinan sistemik di komponen form lain.
**Rekomendasi:** tambah `id` + `for` (atau `aria-label`) di komponen input. Cek juga form kasir, SOAP, master.

### 5. Indikator step wizard overflow horizontal di desktop
Di layar lebar (1300px) progress 4-step (Identitas → Sumber → Alergi → Antropometri) tetap punya scrollbar horizontal; step 4 kepotong ("Antropometri (opsi...").
**Rekomendasi:** biarkan step bar full-width / wrap di desktop; scroll horizontal hanya untuk layar sempit.

---

## 🟢 Catatan Ringan / Efisiensi

- **Auto-refresh 10 detik** di antrian (Kasir/Dokter) via polling. Nyaman, tapi tiap tab buka = request periodik konstan. Untuk banyak terminal, pertimbangkan refresh on-focus atau interval lebih longgar.
- **HTMX di-load via unpkg dengan 301 redirect** (1 round-trip ekstra). Kalau tetap CDN, pin URL langsung ke `/dist/htmx.min.js`.
- **Dashboard "Semua Menu"** menduplikasi seluruh sidebar sebagai kartu launcher — redundan tapi acceptable (handy untuk tablet).

---

## ✅ Yang Sudah Bagus (pertahankan)

- **Performa lokal:** LCP 260ms, CLS 0.00, TTFB 14ms — sangat baik, tanpa layout shift.
- **Empty state ramah & informatif:** "Tidak ada antrian bayar!", "Antrian Anda kosong! Bapak bisa pulang awal..." — manusiawi, sesuai persona dokter pemilik.
- **Banner penjelasan filter di Antrian Dokter** — menjelaskan logika "siapa yang tampil" langsung di UI. UX edukatif yang bagus.
- **Information architecture sidebar** rapi & ter-grup (Operasional / Klinis / Pengadaan / Master Data / Manajemen / Settings / Akun).
- **Reports Omzet:** chart bar+line bersih, KPI cards jelas, filter intuitif.
- **Konsistensi visual** lintas halaman tinggi (warna status, card, tipografi).

---

## Keterbatasan Audit Ini

Antrian kosong saat audit (25 Jun) → halaman alur-dalam belum di-audit visual:
- Dokter **SOAP form** (tindakan/resep multi-row, searchable dropdown, banner kuota)
- Kasir **halaman tagihan** (split payment, void modal, nota)
- Apoteker serah obat

**Saran:** sesi lanjutan dengan 1 pasien test di antrian → walkthrough penuh alur ini untuk audit efisiensi klik & error tersembunyi di form kompleks (ini halaman paling sering dipakai & paling rawan).

---

## Rekomendasi Prioritas (urut eksekusi)

1. **Self-host HTMX + Tailwind + Tom Select** (reliabilitas — gabung dengan B3 Deployment)
2. **Build Tailwind production** (hilangkan warning + percepat load)
3. **Fix role label `StafRoleEnum.OWNER`** di `_shared.py` (1 baris, efek global)
4. **Tambah label association di form** (aksesibilitas + usability)
5. **Rapikan step bar wizard** di desktop
6. **Walkthrough alur dalam** dengan pasien test (SOAP + tagihan + void)

---

## Update — Walkthrough Alur-Dalam (pasien test DUMMY TEST 2506)

Dijalankan walkthrough penuh dengan pasien dummy: **Daftar → SOAP → Ruang Tindakan → Kasir → Bayar → (Void)**. Pasien `DUMMY TEST 2506` (id 1405, RM 260625-001, kunjungan #1571, transaksi #644). Data ini bisa dihapus (lihat cleanup di bawah).

### Yang Bekerja Baik (alur inti solid)
- **Wizard pendaftaran**: 4-step switching via HTMX tanpa reload, membuat pasien + kunjungan + assign dokter dengan benar.
- **SOAP form**: HTMX "+ Tambah Tindakan/Resep" (partial load mulus), **Tom Select searchable** treatment dropdown (lengkap dengan harga), note kontekstual kuota member ("REGULAR → tidak ada benefit"), validasi "minimal 1 dari S/O/A".
- **Ruang Tindakan**: Start → confirm dialog → End, transisi status benar (ANTRI_TREATMENT → ON_TREATMENT → ANTRI_BAYAR), toast feedback ("✓ Tindakan dimulai").
- **Kasir tagihan**: breakdown biaya jelas, split payment dengan **nominal auto-fill** = total, dukungan multi-metode.
- **Pembayaran Berhasil**: konfirmasi rapi (kembalian highlight), auto-print A5, tombol Void + Cetak Ulang.
- **Void**: warning batas waktu jelas, banner Force Void **role-aware** (Owner = 7 hari). Backend cascade sudah wired (DEC-068).
- **Confirm dialog** pada aksi destruktif (Selesai tindakan) + **toast** feedback = pola UX yang baik.

### Temuan Baru dari Alur-Dalam

🟡 **Inkonsistensi format angka (Rp).** Halaman **Tagihan** pakai koma gaya-US: `Rp 250,000`. Halaman **Pembayaran Berhasil** & **Cari Transaksi** pakai titik sesuai konvensi Indonesia: `Rp 250.000`. Halaman Tagihan adalah outlier — seragamkan ke titik (format Indonesia). Berisiko membingungkan saat angka besar.

🟡 **Aksesibilitas unlabeled fields = sistemik.** Konfirmasi lintas form: wizard daftar **17**, SOAP **8**, tagihan kasir **5** field tanpa label terkait. Bukan satu halaman — pola komponen form global.

🟡 **Overflow horizontal tabel "Antrian Hari Ini".** Di desktop 1300px, kolom aksi ("Ubah Status") kepotong jadi "Ub..." dan butuh scroll horizontal untuk menjangkau tombol. Sama kelas dengan step-bar wizard. Tombol aksi sebaiknya selalu terlihat tanpa scroll.

🟢 **Dua tombol submit di wizard step 4** ("💾 Simpan Pasien" vs "✓ Daftar Pasien Sekarang") — bedanya tidak jelas bagi FO (ternyata: Simpan = simpan profil saja; Daftar = simpan + masuk antrian). Perjelas label/﻿hint, mis. "Simpan tanpa antrian" vs "Simpan & masukkan antrian".

🟢 ~~Input Nominal pembayaran `valuemax="0"`~~ — **DICORET (false alarm).** Cek source: input nominal hanya punya `min="1" step="1" required`, TIDAK ada atribut `max`. "valuemax=0" cuma artefak pelaporan a11y tree (input number tanpa max). `min="1"` sudah cegah nilai negatif/nol. Tidak ada bug, tidak ada perbaikan.

🟠 **Auto-print halaman Pembayaran Berhasil mengganggu interaksi lanjutan.** Saat audit otomatis, setelah bayar, tab auto-print terbuka dan halaman sempat jadi tidak responsif / `about:blank`; klik Void & script time-out. Di hardware nyata ini berarti kasir harus tutup dialog print dulu sebelum bisa Void/navigasi. **Saran:** verifikasi di komputer kasir asli bahwa setelah print muncul, tombol Void & navigasi tetap berfungsi normal (jangan sampai window.open print mereset halaman utama).

🟡 **Role enum leak** (`StafRoleEnum.OWNER`) terkonfirmasi muncul juga di SEMUA halaman alur-dalam (SOAP, tindakan, tagihan, sukses, cari-transaksi). Memperkuat prioritas fix #3.

### Catatan Data Test
Walkthrough meninggalkan data: pasien `DUMMY TEST 2506` + kunjungan #1571 + transaksi #644 (status BAYAR, belum di-void karena interferensi auto-print). Semua bertanda nama "DUMMY TEST 2506" → mudah dihapus. SQL cleanup disediakan terpisah: `seed_data/cleanup_dummy_test_2506.sql`.
