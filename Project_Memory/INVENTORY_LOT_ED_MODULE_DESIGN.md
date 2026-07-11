# DESIGN — Modul Inventory Lot + ED + Distributor + Faktur (Apotek/Pengadaan)

**Status:** DRAFT untuk diskusi/approval dr. Hansen — BELUM dikoding.
**Tanggal:** 2026-07-02
**Pemicu:** 5 kebutuhan apoteker/purchasing dr. Hansen (dashboard ED, faktur saat received, laporan harga,
print PO, laporan slow-moving). Ref diskusi 2026-07-02.

---

## 1. Tujuan & ruang lingkup
Melacak stok **per-lot (batch + tanggal kadaluarsa/ED)** untuk memungkinkan: FEFO saat serah/pakai, dashboard
ED, faktur penerimaan, laporan selisih harga, dan slow-moving. **Scope stok: produk retail + bahan/BHP**
(bukan retail saja).

## 2. Keputusan yang SUDAH dipatok (dr. Hansen, 2026-07-02)
1. **Master Distributor** — database tersendiri (seperti master produk/treatment): nama, alamat, telepon, dll.
2. **Inventory LOT penuh (opsi a)** — stok disimpan per-lot; pengeluaran mengurangi lot via **FEFO**
   (first-expired-first-out). Ditegaskan oleh kebutuhan serah-obat yang menampilkan batch+ED otomatis.
3. **Scope:** produk retail **DAN** bahan/BHP.
4. **Batch pembuka (migrasi):** stok lama → 1 lot "pembuka", **ED dikosongkan** dulu.
5. **Lot boleh `batch_no` NULL & `ED` NULL** (kasus khusus, nice-to-have — mis. alat, repack, item tanpa ED).
6. **Harga:** bandingkan **harga saat order (harga PO)** vs **harga saat barang datang (harga terima)**.
7. **Faktur** dibuat saat received; bisa di-print & disimpan; **bisa di-print ulang kapan saja**.
8. **Tampilan Manajemen Stok:** 1 produk = 1 baris (stok total + ED terdekat + warna peringatan) → klik
   **Detail** = rincian per-batch.

## 3. Model data baru / berubah
**`master_distributor` (BARU):** id, nama, alamat, telepon, (email/PIC opsional), is_active.
**`stok_lot` (BARU) — inti:**
- id_lot (PK)
- id_produk (FK) — atau id_bahan (lihat §9: satu tabel dengan tipe, atau dua tabel)
- batch_no (NULLABLE)
- tgl_ed (Date, NULLABLE)
- qty_masuk, qty_sisa (Decimal/Float)
- harga_terima (Decimal, NULLABLE) — harga saat barang datang (snapshot)
- id_receive (FK ke pemesanan_receive, NULLABLE — batch pembuka/penyesuaian bisa tanpa PO)
- id_distributor (FK, NULLABLE)
- tgl_masuk (Date), status (AKTIF/HABIS/EXPIRED/WRITEOFF), created_at
**`pemesanan_receive` (EXTEND):** tambah per-baris terima → batch_no, tgl_ed, harga_terima, id_distributor,
  (nomor_faktur sudah ada). Idealnya 1 receive-line = 1 lot dibuat.
**`master_produk`/bahan:** `stok_terkini` menjadi **turunan** (jumlah qty_sisa lot aktif) — dipertahankan
  sebagai cache untuk performa, diupdate tiap mutasi (atau dihitung on-the-fly + cache).

## 4. FEFO — aturan konsumsi (penting)
Saat stok keluar (serah, jual, pakai, write-off): pilih lot dengan **ED paling dekat lebih dulu**.
- Urutan: `tgl_ed ASC` (yang paling cepat expired keluar duluan).
- **Lot ED NULL** (kasus khusus) → diperlakukan **paling akhir** (unknown expiry = jangan diprioritaskan
  keluar), tie-break `tgl_masuk ASC` (FIFO) di antara sesama ED-NULL.
- Kurangi `qty_sisa` lot; kalau lot habis → status HABIS; kalau butuh > 1 lot → lintasi beberapa lot.
- Semua pengurangan tetap tulis `inventory_history` (jenis mutasi) + sekarang **catat lot mana** yang berkurang.

## 5. Alur Received + Faktur (item 2 — keystone)
Saat PO di-**Receive**, buka window baru "Buat Faktur Penerimaan":
- **Distributor** (dari master): nama, alamat, telepon.
- **Penerima**: nama/alamat klinik (Profil Klinik) + **id penerima = apoteker login**.
- **Tabel barang** (per item PO): nomor pemesanan, tgl pemesanan, nama item, **nomor batch (input)**,
  **ED (input)**, **harga order (auto dari PO)**, **harga terima (input)** — selisih ditandai untuk laporan.
- Tombol **Buat Faktur** → simpan (buat lot per baris) + bisa print; **print ulang kapan saja**.
Catatan: menerima = membuat `stok_lot` per baris (batch/ED/harga_terima) + update stok.

## 6. Serah-obat Apotek (ripple — disepakati)
Bukan lagi "klik & selesai". Halaman serah menampilkan **daftar item yang akan diserahkan + ED + nomor batch
(terisi otomatis FEFO)**. Apoteker verifikasi lalu konfirmasi → lot berkurang FEFO. (Override manual batch =
opsi lanjutan bila perlu.)

## 7. Titik lain yang mengurangi stok → WAJIB FEFO-aware
- **Kasir**: penjualan produk (termasuk "beli produk tanpa konsul").
- **Tindakan**: pemakaian produk/BHP saat tindakan (auto potong BHP).
- **Write-off / opname minus**.
Semua ini sekarang harus kurangi **lot** (FEFO), bukan satu angka. Ini ripple terbesar → dipetakan & ditest per titik.

## 8. Manajemen Stok — tampilan
- **List:** 1 baris/produk = nama, stok total, **ED terdekat** (warna: merah <1bln, amber <3bln, dst), jumlah batch.
- **Detail:** rincian lot (batch_no, ED, qty_sisa, harga_terima, distributor, tgl masuk). Aksi per-lot (write-off lot).

## 9. Bahan/BHP vs Produk — struktur
Opsi: (i) satu tabel `stok_lot` dengan kolom tipe + FK ke produk ATAU bahan; atau (ii) dua tabel terpisah.
✅ **DIPUTUSKAN (i): SATU tabel `stok_lot`** (kolom tipe + FK produk/bahan). Satu mekanisme FEFO + satu laporan.

## 10. Laporan
- **Dashboard ED (item 1):** bucket ED **<1 bulan / <3 bulan / <6 bulan / <1 tahun** (jumlah item/lot per bucket).
- **Slow-moving (item 5):** window **3 bulan**; rasio **stok saat ini : rata-rata pengeluaran/bulan**
  (sumber `inventory_history`); urut naik = paling lambat gerak; kolom + harga; opsi filter ED (<6bln/<1thn).
- **Selisih harga beli (item 3):** per produk, harga order vs harga terima lintas waktu (naik/turun).
- **Print PO (item 4):** template cetak PO (mirip cetak nota). Mandiri, tak butuh lot.

## 11. Migrasi & kasus khusus
- **Batch pembuka:** untuk tiap produk/bahan dengan `stok_terkini > 0` → buat 1 `stok_lot` qty = stok_terkini,
  **batch_no NULL, ED NULL, harga_terima NULL**. ED bisa diisi manual belakangan.
- **Lot batch/ED NULL** didukung penuh (FEFO taruh paling akhir).
- Konsistensi cache `stok_terkini` = Σ qty_sisa lot aktif — skrip verifikasi.

## 12. Opname (perlu keputusan)
✅ **DIPUTUSKAN: opname LANGSUNG per-batch** (hitung fisik per lot; selisih per lot). Bukan agregat-dulu.

## 13. Rencana bertahap (usulan — approve per fase)
- **P-L1** Master Distributor (model + CRUD + halaman master). *(mandiri)*
- **P-L2** Print PO. *(mandiri, quick win — bisa didahulukan)*
- **P-L3** Model `stok_lot` + migrasi batch-pembuka (ED kosong) + cache stok = Σ lot.
- **P-L4** Received → Faktur (tangkap batch/ED/harga terima + buat lot) + print/simpan/print-ulang.
- **P-L5** Engine FEFO + wire ke **serah-obat apotek** (tampil batch/ED).
- **P-L6** Wire FEFO ke **kasir (jual produk)** + **tindakan (potong BHP)** + **write-off**.
- **P-L7** Manajemen Stok display (agregat + detail per-batch).
- **P-L8** Laporan: dashboard ED bucket + slow-moving + selisih harga.
- **P-L9** ✅ SELESAI (DEC-091): opname per-batch PRODUK/RETAIL (selisih ke lot, cache recompute, urut ED→harga jual, batch baru, submit hanya baris terisi). BAHAN tetap agregat.

## 14. Risiko / titik buta
- **Ripple ke alur LIVE (kasir + apotek + tindakan).** Perlu test ketat tiap titik depletion. Fase P-L5/P-L6
  paling berisiko → kerjakan hati-hati + test regresi.
- **Performa:** stok jadi agregasi lot; pakai cache `stok_terkini` + update transaksional.
- **Data historis mutasi** tidak punya info lot (sebelum modul) — laporan lot-based hanya sejak go-live.
- **Konsistensi cache vs lot** — butuh skrip audit berkala.

## 15. Keputusan final (dr. Hansen, 2026-07-02)
1. ✅ **Satu tabel `stok_lot`** untuk produk + bahan/BHP.
2. ✅ **Opname langsung per-batch**.
3. ✅ **Mulai dari Print PO + Master Distributor** (tahap awal), lot & FEFO menyusul.
