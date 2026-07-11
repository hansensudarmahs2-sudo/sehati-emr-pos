# Design Doc — Faktur Penerimaan (Halaman + Cetak, PPN & Diskon)

**Tanggal:** 2026-07-03
**Status:** DRAFT desain — belum kode. Review dr. Hansen.
**Sumber:** NOTA_PO_FAKTUR_IMPROVEMENTS.md §C (per-delivery, PPN, diskon reverse-calc, status).
**Tujuan akhir:** halaman faktur + cetak faktur yang benar, hilangkan tebak-tebakan harga/diskon asisten apoteker.

---

## 1. Kondisi sekarang

- **"Terima Barang"** (P-L4, `pemesanan_faktur_form`): 1 window input per-item (qty, batch, ED, harga_terima,
  distributor, nomor_faktur) → `receive_item` buat `StokLot` + catat `PemesananReceive` (append-only per event).
- `PemesananReceive` sudah punya: `nomor_faktur`, `harga_terima`, `batch_no`, `tgl_ed`, `id_distributor`.
- **BELUM ADA:** entitas faktur tersendiri, PPN, diskon, total ditagih, status bayar, cetak faktur.
- Cetak/rekap sekarang menggabung SEMUA receive se-PO (bukan per-pengiriman).

---

## 2. Konsep inti (dari §C)

- **1 FAKTUR = 1 PENGIRIMAN** (per submit "Terima Barang"), BUKAN gabungan se-PO. Dari 12 item dipesan,
  3 datang → 1 faktur untuk 3 item itu. PO bisa punya banyak faktur (pengiriman bertahap).
- **Diskon SERAGAM, sebelum PPN** (dikonfirmasi). Asisten cukup input **1 angka: total ditagih (Y)** →
  sistem hitung diskon% & harga terima per item OTOMATIS.
- **Algoritma terbalik:** `d = 1 − Y / (X·(1+t))`, `harga_terima_item = harga_order_item·(1−d)`.
  X = Σ harga order item pengiriman ini (dari PO). t = PPN%. Dua-arah: input d% → hitung Y.

---

## 3. Model data (usulan)

**Tabel baru `faktur_penerimaan`** (header per pengiriman):

| kolom | tipe | catatan |
|---|---|---|
| id_faktur | PK | |
| id_pemesanan | FK pemesanan | PO induk |
| nomor_faktur | str | nomor faktur distributor |
| id_distributor | FK | vendor pengirim |
| tgl_faktur | date | tanggal faktur/terima |
| ppn_persen | decimal | mis. 11.00 (0 = tanpa PPN) |
| diskon_persen | decimal | hasil reverse-calc / input langsung |
| subtotal_order | decimal | X = Σ harga order item di pengiriman ini (pra-diskon, pra-PPN) |
| subtotal_setelah_diskon | decimal | X·(1−d) |
| total_ditagih | decimal | Y = final (setelah diskon + PPN) |
| status_bayar | str | BELUM / LUNAS (opsional fase 2) |
| tgl_jatuh_tempo | date | dari termin PO (opsional fase 2) |
| id_staf_penerima, catatan, created_at | | |

**Link:** tambah `PemesananReceive.id_faktur` (FK, nullable) → tiap event receive tergabung ke satu faktur.
`harga_terima` per receive = harga_order·(1−d) hasil hitung. (Lot terbentuk seperti sekarang, harga_terima
sudah net diskon.)

> Alternatif ringan (kalau tak mau tabel baru): simpan PPN/diskon/total di grup receive by (nomor_faktur+tgl).
> **Tidak disarankan** — rapuh, susah cetak & status. Tabel header lebih bersih. **Rekomendasi: tabel baru.**

---

## 4. Alur "Terima Barang" baru (per pengiriman)

1. Pilih item yang datang di pengiriman ini + qty + batch/ED (seperti sekarang).
2. Input **PPN%** (default dari setting, mis. 11) + **nomor faktur** + **distributor** + **tgl faktur**.
3. Input **Total Ditagih (Y)** → sistem hitung **diskon%** + **harga_terima per item** live (JS) →
   asisten lihat rincian sebelum simpan. (Atau input diskon% → hitung Y. Dua-arah.)
4. Simpan → buat `faktur_penerimaan` + receive events (harga_terima net) + lot; update qty_diterima & status PO.
5. **Cetak faktur** per pengiriman: vendor (distributor) + pembeli (klinik + SIA) + item + subtotal +
   diskon + PPN + total ditagih + nomor faktur + tanggal.

---

## 5. Status PO / faktur (§C1)

- Status PO existing: ORDERED → PARTIAL_RECEIVED → RECEIVED (sudah ada). Cukup; tak perlu istilah baru
  "berjalan/selesai/rilis" kecuali dr. Hansen mau relabel di UI (kosmetik).
- **Status bayar faktur** (BELUM/LUNAS + jatuh tempo dari termin PO) = **dimensi hutang/AP**. Berguna tapi
  menambah cakupan (pelunasan, laporan hutang). **Usul: FASE 2** — fase 1 fokus faktur+PPN+diskon+cetak dulu.

---

## 6. Fase implementasi (usulan)

- **FK-L1** Model `faktur_penerimaan` + `PemesananReceive.id_faktur` + migrasi.
- **FK-L2** Service hitung diskon terbalik (X,t,Y → d, harga per item) + guard (X=0, Y>wajar) + test unit.
- **FK-L3** "Terima Barang" upgrade: input PPN/nomor/Y + preview live (JS) + simpan faktur+receive+lot.
- **FK-L4** Cetak faktur per pengiriman (template baru `print/faktur_a5.html`).
- **FK-L5** Riwayat faktur di detail PO (list per pengiriman + tombol cetak ulang).
- **FK-L6** (FASE 2, opsional) status bayar + jatuh tempo + laporan hutang.
- **FK-L7** Test + housekeeping.

---

## 7. Keputusan TERBUKA (perlu dr. Hansen)

1. **Tabel faktur baru** (rekomendasi) vs grup receive — setuju tabel baru?
2. **PPN**: satu %  per faktur (rekomendasi) atau per item? Default PPN berapa (11%)? Simpan di setting klinik?
3. **Input utama** asisten: "Total Ditagih (Y)" (rekomendasi, sesuai keluhan) — konfirmasi. Perlu juga mode
   input diskon% langsung?
4. **Status bayar/hutang (AP)**: fase 1 sekarang, atau tunda fase 2 (rekomendasi tunda)?
5. **Item harga order kosong/0** (X sebagian 0): diskon terbalik butuh X. Kalau ada item tanpa harga order,
   bagaimana? (usul: minta isi harga order dulu, atau kecualikan dari basis X + warning.)
6. **Cetak faktur**: ini "faktur internal penerimaan" (bukti barang masuk klinik) — bukan faktur pajak resmi
   distributor. Konfirmasi tujuan cetak (arsip internal / lampiran) supaya field-nya pas.

---

## 8. Blind spots / risiko

- **Reverse-calc butuh X akurat** = harga order di PO harus terisi. Kalau PO dibuat tanpa harga, faktur tak
  bisa hitung diskon → dorong isi harga saat buat PO (atau input harga order manual di faktur).
- **Pembulatan**: d dihitung dari Y; harga per item = order·(1−d) bisa ada selisih receh vs Y. Perlu aturan
  pembulatan (mis. selisih receh diserap di item terakhir) supaya Σ = Y persis.
- **Konsistensi lot**: harga_terima lot = net diskon (sudah benar untuk laporan selisih harga P-L8).
- **B-013**: model/migrasi/service via bash + verify (file besar `pengadaan.py` sudah 2× kena).
- Jangan over-build AP/hutang di fase 1 — scope creep.

---

## 9. REVISI — layout faktur riil dr. Hansen (2026-07-03)

**Layout faktur yang dipakai sekarang (jadi acuan cetak FK-L4):**

- **Header kiri:** Nomor faktur · Tanggal · Pemasok/Distributor
- **Header kanan:** Nomor order (= No. PO) · Termin
- **Kolom baris item:** No · Tanggal terima · **Nomor pengiriman** · Nama produk · Jumlah pesanan ·
  Jumlah diterima · Harga satuan · **Diskon** · **Extra diskon** · Pajak · Total · Nama penerima
- **Footer paraf (3):** Pengirim · Penerima · Finance/Owner

**Extra diskon = ember rekonsiliasi (ide dr. Hansen).** Diskon & extra-diskon di faktur riil selalu KOSONG
(distributor tak merinci) → sumber tebak-tebakan. Solusi:
- Kolom **Diskon** = hasil diskon SERAGAM `d` dari reverse-calc (per item, rupiah).
- Kolom **Extra diskon** = **sisa/residual** supaya Σ total = Y PERSIS, dipakai saat `d` seragam tak bisa
  mendarat tepat di Y (pembulatan, atau distributor kasih potongan flat/rupiah, bukan % bersih).
  → menuntaskan blind spot pembulatan (§8) secara transparan & terlihat, bukan disembunyikan di 1 item.

**⚠️ IMPLIKASI GRANULARITAS (perlu keputusan).** Kolom **"Nomor pengiriman"** + **"Tanggal terima"** yang
ada PER BARIS menyiratkan **1 faktur bisa mencakup >1 pengiriman** (surat jalan berbeda per baris). Ini
BERBEDA dari asumsi §2 ("1 faktur = 1 pengiriman"). Dua model:
- **Model A (§2 lama):** 1 faktur = 1 pengiriman. Nomor pengiriman/tgl terima = header (sama semua baris).
  Lebih sederhana; faktur pajak yang gabung beberapa surat jalan tak terwadahi.
- **Model B (implikasi layout):** 1 faktur = dokumen tagih yang menggabung ≥1 pengiriman. Nomor pengiriman &
  tgl terima **per baris**. Lebih umum & cocok dgn form riil, tapi: penerimaan lot terjadi per-pengiriman
  sedangkan tagihan per-faktur → relasi faktur↔receive jadi many, reverse-calc X = Σ semua baris faktur.

→ Perlu dr. Hansen pilih A atau B. (Layout riil condong ke **B**.) Ini mengubah relasi model
`faktur_penerimaan`↔`PemesananReceive` (B = 1 faktur : banyak receive lintas pengiriman).

**Field baru yang muncul dari layout:** `nomor_pengiriman` (surat jalan, ≠ nomor_faktur), `extra_diskon`
(rupiah, faktur-level rekonsiliasi), `nama_penerima` per baris/pengiriman, paraf Finance/Owner (cetak saja).

---

## 10. KEPUTUSAN TERKUNCI (dr. Hansen, 2026-07-03)

- **Granularitas = Model A: 1 faktur = 1 pengiriman** (= 1 submit "Terima Barang"). Kolom "nomor pengiriman"
  & "tanggal terima" jadi faktur-level (tercetak sama di tiap baris — cocok dgn form riil).
- **Nomor pengiriman = DIGENERATE sistem** (nomor internal otomatis tiap penerimaan, mis. `SJ-YYMMDD-NNN`),
  BUKAN input surat jalan distributor. → relasi tetap 1 faktur : banyak receive (dalam 1 pengiriman) — simpel.
- **Extra diskon = ember rekonsiliasi** (residual rupiah agar Σ total = Y persis). Faktur-level.

**Default sisa §7 (dipakai kecuali dr. Hansen koreksi saat implement):**
1. **Tabel `faktur_penerimaan` baru** (bukan numpang receive) — YA.
2. **PPN**: satu % per faktur, **default 11%** (editable per faktur); simpan default di setting klinik (`default_ppn`).
3. **Input utama = Total Ditagih (Y)**; sediakan juga override diskon% manual (dua-arah).
4. **Status bayar/hutang (AP)**: TUNDA ke FK-L6 (fase 2). Fase 1 = faktur+PPN+diskon+extra-diskon+cetak.
5. **Item harga order kosong (X sebagian 0)**: izinkan input harga order manual di faktur; kalau X total = 0
   → nonaktifkan reverse-calc, minta isi harga dulu (warning jelas).
6. **Cetak faktur = arsip internal penerimaan** (bukan faktur pajak resmi). Footer 3 paraf:
   Pengirim · Penerima · Finance/Owner.

**Field final yang perlu (FK-L1):**
- `faktur_penerimaan`: id, id_pemesanan, nomor_faktur (distributor), nomor_pengiriman (auto), id_distributor,
  tgl_faktur/tgl_terima, ppn_persen, diskon_persen, extra_diskon, subtotal_order (X),
  subtotal_setelah_diskon, total_ditagih (Y), nama_penerima (id_staf), catatan, created_at.
- `PemesananReceive.id_faktur` (FK). Per receive: harga_terima = net (order·(1−d)); diskon_rupiah & pajak_rupiah
  bisa dihitung saat cetak (tak wajib disimpan).

**Status desain: SIAP DIIMPLEMENTASI** (FK-L1..L7). Menunggu giliran setelah PO-B lolos test live.

---

## 11. REVISI — cek penerimaan + 2 cetakan (dr. Hansen, 2026-07-03)

**Cek wajib saat barang datang** (di form Terima Barang):
- **Harga**: sesuai / naik / turun (bandingkan harga order PO). Diskon: kalau tak diketahui → algoritma bantu;
  kalau diketahui → input langsung (abaikan algoritma).
- **Jumlah** diterima vs pesanan.
- **Nomor batch** + **Expired date** (wajib untuk lot).

**DUA CETAKAN faktur (beda audiens):**
1. **Faktur FINANCE** — tanpa batch/ED. Fokus angka: item, qty, harga, diskon, extra-diskon, PPN, total.
   (Faktur ini yang dikirim ke finance.)
2. **Faktur/Bukti INVENTORY APOTEK** — DENGAN batch & ED per item (penting untuk telusur stok/FEFO).
→ FK-L4 buat 2 template: `print/faktur_finance_a5.html` + `print/faktur_inventory_a5.html` dari data yang sama.
