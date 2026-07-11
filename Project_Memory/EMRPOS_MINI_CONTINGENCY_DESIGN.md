# Design Note v0.1 — eMR-POS Mini (Contingency Cabang Remote) + Kerangka Re-sync

**Tanggal:** 2026-07-04 · diskusi dr. Hansen · **kerangka awal, belum kode**
**Konteks:** cabang REMOTE (lokasi berbeda), 1 DB pusat (kolam pasien bersama). dr. Hansen MENERIMA risiko
single-point-of-failure (server/internet pusat mati ATAU internet cabang mati → sistem utama lumpuh).
Mitigasi berlapis.

---

## 1. Lapisan contingency (degraded mode)

- **L0 — Normal:** cabang akses **server pusat** (Sehati utama) via internet/VPN + **TLS wajib**. Klinik-aktif
  ditentukan IP/subnet (opsi b, MASTER_KLINIK §9). Semua fitur penuh.
- **L1 — eMR-POS mini (server mini per cabang):** saat pusat/internet putus, cabang jalan di **instance mini
  LOKAL** (subset fitur) supaya operasional tak berhenti. Data dibuat LOKAL selama outage.
- **L2 — Pen & paper:** kalau mini pun mati (listrik/hardware) → manual, lalu entry ke sistem saat pulih.

---

## 2. Scope eMR-POS Mini (SUBSET — sengaja kecil)

**Ada (degraded-critical):**
- Cari & daftar pasien (RM provisional lokal), lihat rekam medis (dari cache lokal).
- Kunjungan + SOAP (catat), cetak resep.
- POS: penjualan produk retail + pembayaran + cetak nota.

**TIDAK ADA di mini (tunggu pusat):** PO/pengadaan, faktur, retur, opname, laporan/komisi, tutup kasir
analitik, master data edit. Ini mengecilkan permukaan sinkronisasi.

---

## 3. TANTANGAN RE-SYNC (bagian tersulit — BELUM ada struktur)

Saat konektivitas balik, data yang dibuat di mini selama outage harus **merge** ke pusat.

- **Duplikat pasien** (bahaya utama): pasien didaftar di mini saat outage, mungkin juga terdaftar di pusat/
  cabang lain di window yang sama → duplikat. Mitigasi: **de-dup by nama + tgl_lahir + no_telepon**;
  **RM provisional** (prefix cabang + tanda "belum tersinkron") → pusat assign RM final + gabung saat merge.
- **Strategi ID:** hindari tabrakan PK saat merge → pakai **prefix cabang / UUID** untuk record yang lahir di
  mini (jangan auto-increment lokal yang bentrok dengan pusat).
- **Transaksi/kunjungan/SOAP = append-only** → konflik rendah, tinggal ditambahkan ke pusat.
- **STOK (implikasi besar):** POS jual di mini saat outage memotong stok. Berarti cabang butuh **stok LOKAL
  per cabang** (kontradiksi dgn "stok terpusat"). → keputusan: stok RETAIL jadi **per-lokasi/cabang** (bukan
  satu angka global). Ini mengubah model stok kalau multi-cabang aktif. (Saat ini 1 klinik = tak masalah.)
- **Protokol sync (usul):** mini simpan **OUTBOX** (log perubahan lokal + timestamp + kode cabang) → saat
  online **push** ke pusat via API → pusat **validasi + de-dup + assign ID final** → balas **mapping
  (id lokal → id pusat)** → mini update ref. Saat online, mini juga **pull snapshot** (pasien + stok cabang +
  master) supaya cache hangat untuk outage berikutnya. Arah: **pusat = otoritas saat konflik.**

---

## 4. Rekomendasi & posisi

- eMR-POS mini + sync engine = **PROYEK BESAR TERSENDIRI** (offline-first + rekonsiliasi). **JANGAN blok**
  pengembangan Sehati utama sekarang.
- **Sampai mini dibangun:** contingency nyata = **pen & paper** saat outage + entry manual ke pusat saat pulih.
  Itu sudah "cukup aman" untuk mulai remote (dgn kesadaran risiko yang dr. Hansen terima).
- Yang bisa **disiapkan lebih dulu di Sehati utama** agar mini/sync tak mahal nanti:
  1. **Stok RETAIL per-cabang** (kalau multi-cabang jadi) — desain sejak awal lebih murah drpd retrofit.
  2. **ID/RM anti-tabrakan** (prefix cabang sudah ada via rm_prefix; siapkan konsep provisional).
  3. **Append-only pada transaksi** (sudah demikian sebagian).

---

## 5. Keputusan TERBUKA (dr. Hansen, untuk lanjutan)
1. Scope mini final (setuju subset §2, atau tambah/kurang?).
2. **Stok saat outage:** stok RETAIL per-cabang (perlu utk POS mini) atau cabang remote TIDAK jual produk
   saat outage (hanya EMR)? Ini menyederhanakan sync drastis kalau POS mini tak menyentuh stok.
3. Aturan de-dup pasien (nama+tgl_lahir+HP cukup? perlu review manual saat merge?).
4. Kapan dikerjakan: ini fase jauh (setelah deployment + cabang ke-2 nyata). Sekarang cukup DIRENCANAKAN.

---

## 6. MODEL RE-SYNC dr. Hansen (2026-07-04) + PENILAIAN

**Status:** eMR-POS mini SUDAH DIBUAT (trial). Re-sync BELUM (butuh perencanaan matang).

**Model dr. Hansen:**
1. **Emergency prefix pada ID:** normal `A-040726-001` (A=cabang, 040726=tgl, 001=urut). Saat mini aktif →
   `E-A-040726-001` (E = prefix darurat). Semua record darurat ber-prefix E → terisolasi & teridentifikasi.
2. **Modul resync (belum ada)** scan **4 hal: id normal, nama, tgl lahir, alamat**. Match SEMUA 4 →
   ID `E-A-...` TIDAK dibuat ID baru, **TIDAK auto-resync**, **perlu validasi manual user**.
3. **POS mini menjual produk saat outage** (stok berkurang lokal). Resync berurutan cek kemiripan 4 hal:
   - Tidak mirip → **auto**: buat ID baru + tulis SOAP + tulis transaksi + kurangi stok (bila retail terjual).
   - Mirip → **validasi manual** user/superadmin/admin.

**Contingency operasional resync (trial):**
- (1) Biarkan mini seharian sampai klinik tutup → resync SETELAH tutup (batch harian).
- (2) Setelah Sehati main pulih pasca-crash → **jeda 60 menit** sebelum balik ke main. Pasien "unfinished"
  (masih di antrian) TIDAK tercatat utk resync → **input manual** oleh user sampai state sama.

### PENILAIAN (jawaban 3 pertanyaan)
**Viable? YA.** Emergency-prefix = pola staging/provisional-ID standar & bersih (namespace darurat tak
tabrakan dgn pusat, mudah di-quarantine). De-dup 4-field + manual-validate-on-match + auto-append-on-no-match
= pola offline-first yang benar.

**Good governance? YA — ini justru KEKUATAN.** Tidak auto-merge identitas rekam medis; match ambigu →
human-in-the-loop (superadmin/admin). Mencegah penggabungan rekam medis yang salah (bahaya klinis/legal).
SYARAT tambahan: tiap record hasil resync WAJIB ditandai provenance (asal=mini, cabang, sesi darurat,
resynced_by/at) → jejak audit medis-legal.

**Terlalu kompleks? TIDAK untuk konsepnya** (level kerumitan sudah pas). Yang berat SATU: **rekonsiliasi
stok** — karena POS mini menjual, cabang butuh **stok RETAIL per-cabang + atribusi batch/lot** saat resync.
Ini bagian terberat & prasyarat yang mengubah model stok bila multi-cabang aktif.

### REFINEMENT usulan (agar makin kokoh)
- **De-dup jangan wajib match-4-eksak:** typo nama/alamat → false-negative (duplikat lolos). Pakai **kunci
  kuat = nama + tgl_lahir** sebagai sinyal duplikat utama; alamat = tiebreaker. Near-match (3/4) → tetap
  masuk antrian validasi manual. Match penuh → 1-klik konfirmasi.
- **Emergency prefix di SEMUA jenis record** (pasien, kunjungan, SOAP, transaksi) → satu batch darurat bisa
  di-resync / di-rollback sebagai unit, dan jadi kunci **idempotensi** (resync ulang tak dobel-apply).
- **Stok resync:** mini catat qty terjual per produk (tanpa batch) → pusat depletion **FEFO** di lot cabang
  saat resync (lebih sederhana drpd mini pilih batch sendiri). Prasyarat: lot per-cabang.
- **Contingency (1) batch-harian = DEFAULT yang disarankan** (kurangi konkurensi, resync 1× saat tutup).
  Contingency (2) 60-menit grace → tambah **snapshot antrian tercetak** saat switchover sebagai alat serah-
  terima in-flight (kurangi risiko pasien mid-treatment terlewat).
- **Resync = idempotent + transaksional per-record**, dengan laporan hasil (berhasil/di-skip/perlu-review).

### Posisi
Model dr. Hansen SOLID & layak jadi dasar. Resync tetap **proyek tersendiri** (matching engine + UI validasi
+ apply-to-central + rekonsiliasi stok). Rencanakan; jangan blok Sehati utama. Prasyarat yang bisa disiapkan
lebih awal di main: **stok RETAIL per-cabang** + konsep **RM/ID provisional (E-prefix)** + **tag provenance**.

---

## 7. KEPUTUSAN & REFINEMENT TERKUNCI (dr. Hansen, 2026-07-04)

**Refinement disetujui:**
1. De-dup **2 anchor = nama + tgl_lahir**; **alamat = tiebreaker**. Near-match → validasi manual.
2. **Emergency prefix (E-) di SEMUA jenis record** (pasien, kunjungan, SOAP, transaksi) → unit resync/rollback + idempotensi.
3. **TIDAK ada pemilihan batch di mini.** Apoteker tulis manual di kertas → dicocokkan saat resync; pusat
   depletion **FEFO** di lot cabang. (Kertas = cross-check QC.)
4. **Resync idempotent + per-record transaksional** (+ laporan berhasil/skip/perlu-review).

**Stok cabang:** DIKONFIRMASI cabang PUNYA stok sendiri (POS mini menjual). → prasyarat **stok RETAIL
per-cabang + lot per-cabang** kalau multi-cabang aktif. **TO BE DISCUSSED** (mengubah model stok utama;
tak perlu sekarang selama 1 klinik).

**Switchover main↔mini — REKOMENDASI: OPSI A (tetap mini sampai klinik tutup).**
- Saat main pulih pasca-crash → **JANGAN switch balik di tengah hari**. Selesaikan hari itu di mini; resync
  1× **setelah klinik tutup**; hari berikutnya kembali ke main. Alasan:
  - 1 sistem per hari, 1 event resync (konkurensi rendah) — paling sederhana & aman.
  - Fitur yang "hilang" saat tetap di mini (PO/faktur/retur/laporan) = back-office → bisa tunggu besok;
    front-line (EMR + POS) tetap jalan di mini.
  - Hindari **double-switch** (main→mini→main) yang menggandakan risiko kehilangan state in-flight.
  - **Grace 60 menit jadi tak relevan** untuk switch-back harian → dihapus dari alur (boleh dipakai sbagai
    "tunggu main stabil 60 menit sebelum mulai resync malam").
- **Snapshot antrian tercetak** hanya diperlukan di SATU titik: **main→mini saat crash** (bawa pasien
  in-flight masuk mini). Opsi A meniadakan kebutuhan snapshot mini→main (tak ada switch-back tengah hari).
- Aturan **tetap (fixed), bukan judgment per-kejadian** → kurangi human error.

**Prasyarat yang bisa disiapkan lebih awal di Sehati MAIN (agar resync murah nanti):**
stok RETAIL per-cabang + lot per-cabang · konsep RM/ID provisional (E-prefix) · tag provenance
(asal=mini, cabang, sesi darurat, resynced_by/at) di record.
