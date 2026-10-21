# Bayar Dulu — Tahap 2: Tindakan Prabayar — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kasir bisa menagih tindakan yang belum dikerjakan (dibayar di muka) dengan peringatan dan centang wajib; komisi tindakan dicatat saat tindakan sudah dibayar DAN sudah selesai; void transaksi prabayar melepas tindakan yang belum dikerjakan; nota menandai "dibayar di muka".

**Architecture:** "Bisa ditagih" melebar dari `SELESAI` ke "bukan BATAL" (satu definisi di `_status_kunjungan.kondisi_K` + `get_tagihan`). Tanda bayar tetap `kunjungan_tindakan.id_transaksi` (tahap 1). Komisi tindakan pindah ke aturan tunggal "dibayar & selesai, mana yang terakhir". Void prabayar mengembalikan tindakan hidup ke "belum ditagih" tanpa menyentuh kuota/series-nya.

**Tech Stack:** FastAPI · SQLAlchemy 2.0 · MySQL 8 (REPEATABLE-READ) · Jinja2 · pytest (sesi rollback, `commit = flush`).

**Spec:** `Project_Memory/DESAIN_BAYAR_DULU_BERCABANG.md` §3.4, §3.5, §3.8 (disetujui 2026-10-15). Tahap 1: `Project_Memory/RENCANA_BAYAR_DULU_TAHAP1.md` (termasuk lampiran Ruling 1–15).

## Global Constraints

- **Tahap 2 TIDAK di-deploy ke mini PC tanpa tahap 4** (hak pasien + uang kembali per tindakan). Tanpa tahap 4, tindakan yang sudah dibayar di muka lalu ditolak pasien tidak punya jalan keluar (Batalkan hanya untuk yang belum dibayar) dan menahan tutup kasir.
- Uang: harga, diskon, kuota, harga paket series tetap dari `_compute_charge` dan dikunci di `transaksi_detail_tindakan` (tidak ada rumus baru). `_refund_bukuan.terhitung_omzet()` tetap saringan omzet.
- Satu definisi: "tindakan bisa ditagih" = `status_tindakan != 'BATAL'` dan `id_transaksi IS NULL` — dipakai `kondisi_K` dan `get_tagihan`; jangan menulis kueri kedua.
- Pola baca-segar & kunci tidak berubah (`mulai_baca_segar` → kunci kunjungan → `get_tagihan` segar → sidik → tulis).
- Pesan peringatan prabayar (layar & server): `"Tindakan berikut belum dikerjakan — dibayar di muka."`; tolak tanpa centang (400): `"Ada tindakan yang belum dikerjakan di tagihan ini. Centang konfirmasi 'dibayar di muka' untuk melanjutkan."`; keterangan nota: `"dibayar di muka"`.
- Lingkungan, test helper, baseline, aturan commit: sama dengan tahap 1 (`lingkungan.md` di workspace SDD; implementer commit lokal, controller push sesudah review).
- Test baru di `sehati_clinic/tests/integration/test_bayar_dulu_tahap2.py`; test penutup cacat harus GAGAL di kode lama.

## Review Focus

1. Void transaksi prabayar yang tindakannya belum dikerjakan: tindakan kembali "belum ditagih", kuota TIDAK dikembalikan (masih dipegang tindakan hidup), series TIDAK dibatalkan; kemudian Batalkan mengembalikan kuota tepat sekali. → Task 4.
2. Tindakan prabayar selesai sesudah transaksi pembayarnya di-VOID tidak menghasilkan komisi. → Task 3.
3. Split billing: bayar T1 (tindakan A dikerjakan, B prabayar), B selesai → komisi B tercatat sekali, terikat T1, bertanggal selesai; susulan T2 tidak mencatatnya lagi. → Task 3.
4. API v1 tanpa field konfirmasi + tagihan berisi tindakan belum dikerjakan → ditolak (layar bukan pagar); tagihan tanpa tindakan prabayar → jalan seperti sekarang. → Task 2.
5. Nota cetak ulang SESUDAH tindakan prabayar selesai tetap menulis "dibayar di muka" (ditentukan dari waktu, bukan status saat cetak). → Task 5.

---

### Task 1: Tagih tindakan bukan BATAL tanpa `id_transaksi`

**Files:** `app/services/_status_kunjungan.py` (`kondisi_K`), `app/repositories/kasir_repo.py` (`get_tindakan_selesai_for_billing` → ganti nama `get_tindakan_untuk_tagihan`, semua pemanggil ikut), `app/services/kasir_service.py` (`get_tagihan`), `app/schemas/kasir.py` (`RincianTindakan.status_tindakan: str`), test.

**Interfaces:** Produces `KasirRepository.get_tindakan_untuk_tagihan(id_kunjungan) -> list[tuple[KunjunganTindakan, MasterTreatment]]` (bukan BATAL); `RincianTindakan.status_tindakan` (PENDING/PROSES/SELESAI). `kondisi_K` klausa tindakan = bukan BATAL & `id_transaksi IS NULL`.

- [ ] **Step 1: Test** — `test_bayar_menagih_tindakan_pending` (SOAP + tindakan PENDING → `get_tagihan` memuatnya dengan `status_tindakan == "PENDING"`, `_bayar` → `id_transaksi` terisi, label `ANTRI_TREATMENT`; `start`+`end` → `COMPLETED` tanpa susulan); `test_tindakan_batal_tidak_ditagih`; `test_view_only_menampilkan_tindakan_yang_dibayar` (mode lunas memuat tindakan ber-`id_transaksi` apa pun statusnya). Sesuaikan test tahap 1 yang menegaskan "PENDING tidak ditagih" (cari di `test_bayar_dulu_tahap1.py`; tulis komentar "tahap 2").
- [ ] **Step 2: GAGAL di kode lama. Step 3: implementasi** (mode view-only: tindakan bukan BATAL ber-`id_transaksi`). **Step 4: suite.** **Step 5: commit** `Bayar dulu T2-1: tindakan yang belum dikerjakan bisa ditagih`.

### Task 2: Konfirmasi "dibayar di muka"

**Files:** `app/schemas/kasir.py` (`BayarRequest.konfirmasi_prabayar: bool = False`), `app/services/kasir_service.py` (`proses_bayar`, sesudah sidik), `app/web/routes/kasir.py` (baca checkbox `konfirmasi_prabayar`), `app/web/templates/kasir_tagihan.html` (kotak kuning + checkbox di form bayar & form Rp 0; tampil hanya bila ada baris `status_tindakan != SELESAI`; baris itu diberi label "belum dikerjakan"), test.

- [ ] **Step 1: Test** — ditolak 400 (pesan Global Constraints) tanpa konfirmasi; diterima dengan konfirmasi; tagihan tanpa tindakan prabayar tidak butuh konfirmasi; render TestClient memuat kotak & checkbox (pola `test_layar_void_lampau_meminta_penyetuju_dan_pin`); route meneruskan checkbox (POST TestClient). API v1 tanpa field → ditolak bila ada prabayar.
- [ ] **Step 2–4.** Kelas Tailwind hanya yang sudah ada (`scripts/cek_kelas_tailwind.py kasir_tagihan.html`). **Step 5: commit** `Bayar dulu T2-2: kotak kuning + centang wajib untuk tindakan dibayar di muka`.

### Task 3: Komisi tindakan = dibayar DAN selesai

**Files:** `app/services/komisi_service.py` (`catat_komisi_transaksi` + fungsi baru), `app/services/treatment_service.py` (`end_tindakan`), `app/services/kasir_service.py` (pemanggil), test.

**Interfaces:** Produces `KomisiService.catat_komisi_tindakan(*, kt: KunjunganTindakan, id_transaksi: int, tanggal: date, request=None) -> int` — satu tindakan, anti-dobel per `id_ref` AKTIF yang sudah ada, basis harga master (pola sekarang). `catat_komisi_transaksi` bagian tindakan: hanya tindakan dengan `id_transaksi == id_transaksi` ini **dan** `SELESAI`, memanggil `catat_komisi_tindakan`.

- [ ] **Step 1: Test** — Review Focus 2 & 3; bayar sesudah selesai → komisi saat bayar (perilaku lama, tanggal bayar); selesai sesudah bayar → komisi saat `end_tindakan`, `id_transaksi` = pembayar, `tanggal` = tanggal selesai; tindakan SELESAI tak ditagih di kunjungan tidak lagi berkomisi saat transaksi LAIN dibayar.
- [ ] **Step 2–4. Step 5: commit** `Bayar dulu T2-3: komisi tindakan dicatat saat dibayar dan selesai`.

### Task 4: Void transaksi prabayar

**Files:** `app/services/kasir_service.py` (`_cascade_void_kunjungan`, `_revert_kuota_per_tindakan`, `_cancel_series_sesi_pending` — keduanya jalur void lewat helper bersama), test.

- Tindakan dalam lingkup yang **belum SELESAI** (PENDING/PROSES): `id_transaksi = NULL` (kembali "belum ditagih"); kuota-nya TIDAK dikembalikan; series yang sesi 1-nya tindakan hidup itu TIDAK dibatalkan. Tindakan SELESAI dalam lingkup tetap diblok pagar void (tidak berubah).
- [ ] **Step 1: Test** — Review Focus 1, kedua jalur void (`void_transaksi`, `force_past_day_void` + PIN, pola K4-1); sesudah void tindakan muncul lagi di tagihan; `batalkan_tindakan` sesudah void diterima dan mengembalikan kuota sekali.
- [ ] **Step 2–4. Step 5: commit** `Bayar dulu T2-4: void transaksi prabayar melepas tindakan yang belum dikerjakan`.

### Task 5: Nota "dibayar di muka"

**Files:** `app/services/print_service.py` (`_baris_snapshot` tindakan), `app/web/templates/print/nota_a5.html`, `nota_thermal.html`, test.

- "Dibayar di muka" = tindakan `waktu_selesai IS NULL` atau `waktu_selesai > trx.waktu_bayar` (Review Focus 5).
- [ ] **Step 1: Test** di `tests/integration/test_nota_snapshot.py` pola yang ada: cetak saat PENDING dan sesudah SELESAI → keterangan ada keduanya; tindakan selesai sebelum bayar → tanpa keterangan; jumlah baris − diskon = total tetap.
- [ ] **Step 2–4. Step 5: commit** `Bayar dulu T2-5: nota menandai tindakan dibayar di muka`.

### Task 6: Dokumentasi & pemeriksa

**Files:** `CLAUDE.md` (§4.1 baris status ringkasan: "bisa ditagih" = bukan BATAL; komisi tindakan; tahap 2 hanya deploy bersama tahap 4), `Project_Memory/DESAIN_BAYAR_DULU_BERCABANG.md` (status tahap 2), `Project_Memory/UJI_UI_AUDIT_2026-10-05.md` (U73 bayar tindakan di muka + centang; U74 komisi muncul saat perawat selesai; U75 void prabayar lalu Batalkan; U76 nota "dibayar di muka").
- [ ] Pemeriksa: suite, smoke, `cek_finance_pack`, `jejak_uji_ui`, `cek_status_kunjungan --hari 30`, `cek_tunda_item`, `cek_tebus_resep`. **Commit** `Bayar dulu T2-6: dokumentasi tahap 2`.
