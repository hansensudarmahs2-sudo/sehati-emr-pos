# DESIGN — Modul Komisi Staf (Laporan + Dashboard + Skema Dokter)

**Status:** DRAFT untuk diskusi/approval dr. Hansen — BELUM dikoding.
**Tanggal:** 2026-07-02
**Ref:** DEC-085/B-030 (komisi = fitur separuh-jadi: rate tersimpan, payroll belum), finance API `/komisi/staf` (501).

---

## 1. Tujuan
Laporan & dashboard komisi untuk 2 role penerima (Dokter, Perawat): total komisi per periode
(harian / mingguan / bulanan / rentang), rincian per baris, plus skema komisi dokter yang bisa
berbeda-beda (fixed / threshold / guaranteed) di kemudian hari.

## 2. Keputusan yang SUDAH dipatok (dr. Hansen, 2026-07-02)
1. **Snapshot saat bayar** — nilai komisi dikunci ke DB saat transaksi lunas. Ubah rate master nanti
   TIDAK mengubah komisi masa lalu (payroll akurat).
2. **Basis tanggal = tanggal bayar (kasir)** — komisi diakui saat uang masuk. VOID dikecualikan.
3. **Atribusi = pelaksana** — komisi mengikuti staf yang mengeksekusi (`kunjungan_tindakan.id_staf_pelaksana`).
4. **Design-first** — dokumen ini di-approve dulu sebelum koding.

## 3. Model Atribusi — FINAL (dr. Hansen, 2026-07-02)
Master treatment simpan DUA rate independen: `komisi_dokter_*` & `komisi_perawat_*`
(✅ terverifikasi: form master treatment punya keduanya; `hitung_komisi_treatment` menghitung keduanya).

**Aturan (Usulan A dikonfirmasi) — pada tindakan SELESAI & dibayar:**
- **komisi_dokter** (bila rate>0) → **dokter yang melakukan** tindakan.
- **komisi_perawat** (bila rate>0) → **perawat yang melakukan** tindakan.
- Bisa dua-duanya (facial: dokter 75.000 + perawat 25.000 → 2 baris ledger) atau satu saja
  (pico: komisi_perawat 0 → hanya dokter).

**Siapa "pelaksana" (2 kolom baru nullable di `kunjungan_tindakan`):**
- `id_dokter_pelaksana` (IMPLEMENTASI K-L0, disempurnakan): di-set saat **Mulai Tindakan** —
  * operator **Dokter** → `id_dokter_pelaksana` = dokter itu (benar utk dokter assigned, pengganti,
    maupun pasien "bebas"/tanpa assign).
  * operator **Perawat** → `id_dokter_pelaksana` = dokter **pengawas** (yang di-assign kunjungan).
  Alasan: lebih akurat + tahan kasus "bebas"/pengganti tanpa perlu FO re-assign. Konsekuensi: **filter
  antrian per-dokter TIDAK lagi wajib** untuk kebenaran komisi (jadi opsional/UX saja — bisa ditambah nanti
  kalau dr. Hansen tetap ingin dokter pengganti diblok dari antrian sampai FO re-assign).
- `id_perawat_pelaksana` = **perawat yang klik "Mulai Tindakan"** (pola pelaksana yg sudah ada). Sekali
  dimulai, terkunci — perawat lain tak bisa memulai tindakan-baris yang sama. (1 pasien bisa punya >1
  tindakan yg dikerjakan perawat berbeda; bisa juga 1 tindakan.)
- Ledger dokter pakai `id_dokter_pelaksana`; ledger perawat pakai `id_perawat_pelaksana`. Rate 0 /
  pelaksana kosong → tak ada baris ledger untuk role itu.
- (Bug fixed 2026-07-02: role Dokter kini punya menu **Ruang Tindakan** — akses memang sudah diizinkan.)

**Produk (komisi_dokter saja):** → dokter peresep. "Beli tanpa konsul" = TANPA komisi. ✅
**Konsultasi = sumber komisi, TAPI bukan tipe ketiga:** konsultasi didaftarkan sebagai **item di
master_treatment** (punya komisi_dokter sendiri) → dihitung & masuk ledger sebagai TINDAKAN biasa. ✅
**VOID:** tindakan/transaksi di-VOID → **baris ledger komisi terkait ikut di-VOID**. ✅ (konsekuensi detail
mis. klawback dibahas lagi nanti.)
**Backfill:** tidak ada — komisi dihitung sejak fitur live. ✅  **Role penerima:** hanya Dokter & Perawat. ✅

## 4. Snapshot Komisi — tabel LEDGER baru (`komisi_ledger`)
Ditulis saat **kasir proses-bayar commit** (hanya item yang benar-benar dibayar). Satu baris per
komisi yang diperoleh:

| kolom | isi |
|---|---|
| id_komisi (PK) | auto |
| tanggal | date(waktu_bayar) — snapshot |
| id_transaksi / id_kunjungan | sumber |
| id_staf + role_snapshot | penerima + rolenya saat itu |
| sumber | TINDAKAN / PRODUK |
| id_ref | id_kunjungan_tindakan atau id_resep |
| id_pasien | untuk kolom pasien (nama di-join saat tampil) |
| nama_item | nama treatment/produk (snapshot) |
| harga_jual | snapshot |
| komisi_tipe + komisi_value | snapshot rate |
| komisi_nominal | Rupiah komisi (snapshot, hasil hitung) |
| status | AKTIF / VOID (ikut VOID kalau transaksinya di-void) |

Keuntungan ledger (vs kolom di kunjungan_tindakan): bersih, 1 baris = 1 pendapatan, gampang
di-query & di-agregasi, tahan perubahan rate master. VOID transaksi → baris ledger terkait ditandai VOID.

## 5. Laporan & Dashboard (Phase 1 — uncapped)
**Filter:** periode harian / mingguan / bulanan / rentang tanggal + pilih staf (atau semua).
**Dashboard (kartu atas):** Total Komisi Produk · Total Komisi Tindakan · Total Komisi Keseluruhan.
**Tabel rincian per baris:** Tanggal · No. RM/ID Pasien · Nama Pasien · Nama Tindakan/Produk ·
Harga Jual · Komisi (baris). Footer = total.
**Sumber data:** query `komisi_ledger` (status AKTIF) by tanggal bayar + staf.

## 6. Skema Komisi DOKTER (Phase 2) — konfigurasi per-dokter
Komisi dokter (bukan perawat) bisa punya skema berbeda. Config per dokter (usulan: kolom di
`master_staf` atau tabel `master_komisi_skema`):
- `skema`: `UNCAPPED` (Opsi-1) / `THRESHOLD_HALF` (Opsi-2) / `THRESHOLD_GUARANTEED` (Opsi-3).
- `threshold_nominal`: mis. 25.000.000.
- `guaranteed_nominal`: mis. untuk Opsi-3 (by kontrak).

**Opsi-1 UNCAPPED (sudah = perilaku sekarang):** komisi bulanan = Σ ledger, tanpa batas.
**Opsi-2 THRESHOLD_HALF:** setelah total komisi bulan lewat threshold, kelebihannya dibayar 1/2.
  Formula: `komisi_dibayar = threshold + (total_gross − threshold) / 2` (kalau total_gross > threshold),
  else `= total_gross`. Contoh: threshold 25jt, gross 40jt → 25jt + (15jt/2) = **32,5jt**.
**Opsi-3 THRESHOLD_GUARANTEED:** seperti Opsi-2 + jaminan minimal (guaranteed fee) — by agreement.
  (Detail formula diselesaikan saat Phase 2 karena varian kontrak bisa macam-macam.)

**Penting:** transformasi skema ini di lapisan **agregasi/laporan** (payroll), BUKAN mengubah baris
ledger (ledger tetap gross per baris). Jadi laporan rinci per baris = gross; ringkasan payroll dokter =
setelah skema. Perawat: SELALU uncapped (gaji fix, komisi = tambahan).

## 7. Perubahan data model + migrasi
- Tabel baru `komisi_ledger` (§4).
- Phase 2: config skema per-dokter (`master_staf` +3 kolom ATAU tabel `master_komisi_skema`).
- Migrasi Alembic terpisah per fase.
- **Backfill:** data transaksi lama belum punya ledger. Opsi: (a) biarkan (komisi mulai dihitung sejak
  fitur live), atau (b) skrip backfill dari transaksi lama (hitung dari master rate saat ini —
  kurang akurat utk rate yg pernah berubah). ➡️ **Konfirmasi: mulai dari sekarang saja, atau backfill?**

## 8. Titik integrasi (di mana ledger ditulis)
`kasir_service` proses-bayar: setelah transaksi BAYAR commit, untuk tiap tindakan (SELESAI) & produk
(dibayar) yang punya rate komisi → tulis baris `komisi_ledger`. VOID → tandai baris ledger terkait VOID.
(Mengikuti pola atomicity + exclude-VOID yang sudah ada, A1/DEC-079.)

## 9. Akses/role
- Owner/Superadmin: lihat semua staf.
- Dokter/Perawat: lihat komisi DIRI SENDIRI saja (pola REPORTS-COMPART #324, spt Rekap Shift kasir).
- Kartu baru "Komisi Saya / Komisi Staf" di halaman Reports + breadcrumb.

## 10. Rencana implementasi bertahap (setelah approval)
- **K-L0 (prasyarat):** `kunjungan_tindakan` + kolom `id_dokter_pelaksana` (auto = dokter assigned) &
  `id_perawat_pelaksana` (perawat yang mulai); pastikan Ruang Tindakan menyetel keduanya + antrian tindakan
  dokter terfilter per-assigned. Migrasi.
- **K-L1:** migrasi `komisi_ledger` + model.
- **K-L2:** tulis ledger saat proses-bayar (+ void handling) + test.
- **K-L3:** service laporan komisi (agregasi + rincian) + test angka offline.
- **K-L4:** route + template dashboard/laporan + kartu Reports + akses role.
- **K-L5:** test + housekeeping (DEC + roadmap).
- **Phase 2 (sesi terpisah):** config skema dokter + transformasi threshold/guaranteed + UI + test.

## 11. Status keputusan
**FINAL (siap koding):** snapshot saat bayar · tanggal bayar · atribusi Usulan A (per role, per pelaksana) ·
`id_dokter_pelaksana`=auto dokter assigned + `id_perawat_pelaksana`=perawat yang mulai · konsultasi = item
master_treatment (bukan tipe ke-3) · produk tanpa konsul = tanpa komisi · VOID tindakan → VOID komisi ·
tanpa backfill · hanya 2 role · menu Dokter→Ruang Tindakan sudah diperbaiki.

**Ditunda (Phase 2, setelah Phase 1 selesai):** skema komisi dokter (UNCAPPED / THRESHOLD_HALF /
THRESHOLD_GUARANTEED) + konfigurasi per-dokter di owner/superadmin. Konsekuensi detail VOID komisi
(clawback bila periode payroll sudah ditutup) juga dibahas di situ.
