# 03 — Frontend Manual Checklist per Role

**Layer:** Frontend (HTML/HTMX + Tailwind)
**Cadence:** Bulanan (atau sebelum soft launch & setelah deploy fitur besar)
**Reference:** `00_PROTOCOL.md`

---

## Tujuan

Otomasi tidak bisa cek UX. Checklist ini Bapak ikuti dengan mata + tangan: buka tiap halaman, klik tiap tombol, submit tiap form. Catat hasil di kolom Status.

**Tips:**
- Pakai browser **Incognito / Private** supaya tidak ada cache lama
- Test satu role per session (tidak campur — login → checklist role itu sampai habis → logout → ganti role)
- Catat **kapan** dilakukan dan **environment** mana (dev / staging / production)
- Kalau ketemu issue: catat severity (🔴🟠🟡🟢) di kolom Status, ditambah detail singkat

**Cara mencentang:**
- `[ ]` = belum dicek
- `[x]` = OK (lulus)
- `[!]` = ada issue (tulis detail)
- `[?]` = tidak applicable / not relevant

---

## Header Run

```
Tanggal:      __________________________
Environment:  [ ] dev   [ ] staging   [ ] production
Tested by:    __________________________
Duration:     __________________________
```

---

## A. Login & Dashboard (semua role)

| # | Check | Status |
|---|-------|--------|
| FE-A-01 | Halaman `/web/login` muncul dengan benar | [ ] |
| FE-A-02 | Login salah → error message tampil, tidak crash | [ ] |
| FE-A-03 | Login benar → redirect ke `/web/dashboard` | [ ] |
| FE-A-04 | Dashboard load tanpa banner merah `⚠ Dashboard service error` | [ ] |
| FE-A-05 | Logo "Sehati Clinic" di sidebar bisa diklik kembali ke Dashboard | [ ] |
| FE-A-06 | Logout berhasil — redirect ke `/web/login` dan cookie hilang | [ ] |

---

## B. Role: OWNER (test semua menu, paling lengkap)

**Login sebagai OWNER. Tested by:** __________________

| # | Check | Status |
|---|-------|--------|
| FE-B-01 | Dashboard tampil 4 KPI cards | [ ] |
| FE-B-02 | Dashboard tampil "Antrian per Tahap Hari Ini" 6 cards | [ ] |
| FE-B-03 | Dashboard tampil "Kunjungan Terakhir Hari Ini" tabel | [ ] |
| FE-B-04 | Menu sidebar lengkap (semua group) | [ ] |
| FE-B-05 | `/web/pasien` cari pasien — hasil benar | [ ] |
| FE-B-06 | `/web/pasien/baru` wizard 4-step jalan, daftar pasien baru sukses | [ ] |
| FE-B-07 | `/web/pasien/{id}` detail pasien dengan riwayat | [ ] |
| FE-B-08 | `/web/dokter/antrian` antrian dokter tampil | [ ] |
| FE-B-09 | `/web/dokter/input-medis/{id}` SOAP form bisa submit | [ ] |
| FE-B-10 | `/web/ruang-tindakan/antrian` antrian perawat tampil | [ ] |
| FE-B-11 | `/web/kasir/antrian` antrian kasir tampil | [ ] |
| FE-B-12 | `/web/apotek/antrian` antrian apotek tampil | [ ] |
| FE-B-13 | `/web/apotek/suggested-order` analisa stok dengan 4 kategori | [ ] |
| FE-B-14 | Tombol "Buat PO" di Suggested Order → form PO ter-prefill | [ ] |
| FE-B-15 | `/web/master/treatment` list + create + edit + komponen BHP | [ ] |
| FE-B-16 | `/web/master/produk` list + create + edit | [ ] |
| FE-B-17 | `/web/master/bahan` list + create + edit | [ ] |
| FE-B-18 | `/web/pengadaan/pemesanan` list PO + filter status | [ ] |
| FE-B-19 | `/web/pengadaan/pemesanan/baru` create PO baru | [ ] |
| FE-B-20 | PO transition SUBMITTED → ORDERED (approve) | [ ] |
| FE-B-21 | PO receive item — stok ter-update | [ ] |
| FE-B-22 | `/web/pengadaan/opname` stock opname workflow | [ ] |
| FE-B-23 | `/web/pengadaan/mutasi` history mutasi tampil | [ ] |
| FE-B-24 | `/web/staf` manajemen staf — list + create + edit | [ ] |
| FE-B-25 | `/web/profil` edit nama + ubah PIN + ubah password | [ ] |

---

## C. Role: DOKTER

**Login sebagai DOKTER. Tested by:** __________________

| # | Check | Status |
|---|-------|--------|
| FE-C-01 | Dashboard tampil KPI dokter (Antrian Konsul, Pasien Hari Ini, dst) | [ ] |
| FE-C-02 | Sidebar HANYA tampil menu Dokter — Pasien, Dokter, Ruang Tindakan (read), Profil | [ ] |
| FE-C-03 | Akses `/web/master/produk` → harus 403 | [ ] |
| FE-C-04 | Akses `/web/kasir/antrian` → harus 403 | [ ] |
| FE-C-05 | Akses `/web/staf` → harus 403 | [ ] |
| FE-C-06 | Antrian dokter tampil dengan tombol "Konsultasi" | [ ] |
| FE-C-07 | SOAP form bisa input + tindakan multi-row + resep multi-row | [ ] |
| FE-C-08 | Setelah submit SOAP, pasien pindah ke ANTRI_TREATMENT | [ ] |
| FE-C-09 | "Ubah Konsul" tampil tindakan + resep yang sudah ada | [ ] |
| FE-C-10 | Riwayat pasien — section SOAP + Tindakan terlihat | [ ] |

---

## D. Role: PERAWAT

**Login sebagai PERAWAT. Tested by:** __________________

| # | Check | Status |
|---|-------|--------|
| FE-D-01 | Dashboard tampil KPI perawat | [ ] |
| FE-D-02 | Sidebar HANYA Pasien, Ruang Tindakan, Profil | [ ] |
| FE-D-03 | Akses `/web/dokter/antrian` → harus 403 | [ ] |
| FE-D-04 | Akses `/web/kasir/antrian` → harus 403 | [ ] |
| FE-D-05 | `/web/ruang-tindakan/antrian` tampil dengan auto-refresh 10s | [ ] |
| FE-D-06 | Klik kunjungan → detail tindakan tampil | [ ] |
| FE-D-07 | Tombol "Start Tindakan" jalan, status berubah ke ON_TREATMENT | [ ] |
| FE-D-08 | Tombol "End Tindakan" jalan, auto-deduct BHP | [ ] |
| FE-D-09 | Tombol "+ Upsell" tampil modal | [ ] |
| FE-D-10 | Upsell treatment butuh_otorisasi minta PIN dokter | [ ] |
| FE-D-11 | PIN salah → error, PIN benar → upsell sukses | [ ] |

---

## E. Role: FO (Front Office)

**Login sebagai FO. Tested by:** __________________

| # | Check | Status |
|---|-------|--------|
| FE-E-01 | Dashboard tampil shortcut Antrian Hari Ini + Cari Pasien | [ ] |
| FE-E-02 | Akses `/web/master/produk` → harus 403 | [ ] |
| FE-E-03 | `/web/pasien/baru` wizard 4-step lengkap | [ ] |
| FE-E-04 | Search pasien + tombol "+ Antrian" tampil | [ ] |
| FE-E-05 | "+ Antrian" konsultasi dengan dokter | [ ] |
| FE-E-06 | "+ Antrian" Beli Produk (tanpa konsul) | [ ] |
| FE-E-07 | Halaman antrian hari ini — ubah status, batal antrian | [ ] |

---

## F. Role: KASIR

**Login sebagai KASIR. Tested by:** __________________

| # | Check | Status |
|---|-------|--------|
| FE-F-01 | Dashboard tampil Omzet Shift + Antrian Bayar | [ ] |
| FE-F-02 | Akses `/web/dokter/antrian` → harus 403 | [ ] |
| FE-F-03 | `/web/kasir/antrian` tampil antrian ANTRI_BAYAR | [ ] |
| FE-F-04 | Klik tagihan → detail tagihan tampil | [ ] |
| FE-F-05 | Form bayar split payment jalan (multi-method) | [ ] |
| FE-F-06 | Void item — minta konfirmasi, status ter-update | [ ] |
| FE-F-07 | Setelah lunas → pasien pindah ke ANTRI_OBAT (kalau ada resep) atau COMPLETED | [ ] |

---

## G. Role: APOTEKER

**Login sebagai APOTEKER. Tested by:** __________________

| # | Check | Status |
|---|-------|--------|
| FE-G-01 | Dashboard tampil Antrian Obat + Stok ≤ Minimal | [ ] |
| FE-G-02 | Akses `/web/master/produk` → harus 403 | [ ] |
| FE-G-03 | Akses `/web/staf` → harus 403 | [ ] |
| FE-G-04 | `/web/apotek/antrian` tampil antrian obat | [ ] |
| FE-G-05 | Detail resep — tombol Serahkan, validasi stok | [ ] |
| FE-G-06 | `/web/apotek/suggested-order` 4 kategori + 2 tombol PO baru | [ ] |
| FE-G-07 | "Buat PO" per row → form ter-prefill 1 item | [ ] |
| FE-G-08 | "Buat PO Semua URGENT" → form ter-prefill N items | [ ] |
| FE-G-09 | Apoteker create PO hanya boleh tipe PRODUK, RETAIL | [ ] |
| FE-G-10 | Write-off produk minta jenis_mutasi + alasan | [ ] |

---

## H. Cross-cutting concerns

| # | Check | Status |
|---|-------|--------|
| FE-H-01 | Error 404 → tampil halaman yang ramah, bukan stack trace | [ ] |
| FE-H-02 | Error 500 → tidak expose detail SQL/Python error ke user | [ ] |
| FE-H-03 | Form validation error → tampil dengan jelas, field highlighted | [ ] |
| FE-H-04 | HTMX partial swap berhasil tanpa "flicker" | [ ] |
| FE-H-05 | CSRF token mismatch → error ramah, tidak crash | [ ] |
| FE-H-06 | Session habis (6 jam) → redirect ke login, tidak crash | [ ] |

---

## Setelah selesai

1. **Hitung skor:** total OK / total check (skip yang [?]).
2. **Catat issue per severity** di footer dokumen ini.
3. **Buat entry di log:** `logs/YYYY-MM-DD_frontend_role.md` dengan ringkasan + screenshot kalau perlu.
4. **Promosi CRITICAL/HIGH** ke `07_known_issues.md`.

---

## Footer Run — Issue Ditemukan

| # | ID | Severity | Deskripsi | Reproducible? | Catatan |
|---|-----|----------|-----------|---------------|---------|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |

---

## Tips test efisien

- **Pakai test akun** dengan nama yang jelas: `dokter_test`, `kasir_test`, dll
- **Pakai pasien test** dengan nama yang mudah dikenali: "Pasien Test 01"
- **Catat di hp/notepad** issue yang ditemukan, jangan stop test (kecuali CRITICAL)
- **Screenshot bug** — pakai Win+Shift+S (Windows) atau Cmd+Shift+4 (Mac)
- **Total estimasi waktu:** ~2 jam untuk semua role. Boleh dibagi 2 sesi (pagi + sore).
