# Handoff — Apa yang BARU di Raw Data Export (untuk Modul Data Analyst)

**Dibuat:** 2026-07-07 · **Sifat:** changelog dataset Owner Raw Data Export.
**Pendamping:** `HANDOFF_DATA_ANALYST_MODULE.md` (prinsip + resep derivasi). **Sumber kebenaran skema terkini:** `/web/export/dictionary.json`.

> Prinsip tetap: Sehati = penyedia RAW DATA. Semua di bawah ini adalah data mentah tambahan; perhitungan/interpretasi di Data Analyst / council AI.

---

## 1. ⭐ HEADLINE — `staff_activity_raw` diperkaya (transisi from→to)

Dataset audit log kini menyertakan **status perpindahan**, sebelumnya hilang:

| Kolom baru | Isi | Catatan |
|---|---|---|
| `status_lama` | status_antrian SEBELUM | terparse, **PII-free** |
| `status_baru` | status_antrian SESUDAH | terparse, **PII-free** — inti untuk timeline |
| `data_lama` | payload mentah sebelum (JSON) | bisa ada PII → **NULL saat `mask_pii`** |
| `data_baru` | payload mentah sesudah (JSON) | bisa ada PII → **NULL saat `mask_pii`** |

**Kenapa penting:** ini yang memungkinkan rekonstruksi **timeline transisi → dwell-time per tahap, insiden antrian merah, pola dokter bolak-balik** (resep di handoff utama §4).

**Taksonomi `aksi` transisi** (tidak seragam — petakan semua sebagai "transisi"): `STATUS_UPDATE` (FO/dokter), `TINDAKAN_START`/`TINDAKAN_END` (perawat/dokter), `SERIES_USE_SESSION` (tebus series → ANTRI_TREATMENT), `VOID_KUNJUNGAN_FORWARD` (void → COMPLETED), pembayaran (→ ANTRI_OBAT/COMPLETED, ber-`data_lama`/`data_baru`), `log_create` (status awal saat daftar/beli-produk/membership). `id_target` = `id_kunjungan`; `id_staf` = pelaku; `waktu` = stempel.

---

## 2. Dataset BARU (tersedia di export, dari kerja bridge Finance — sama-sama dipakai analis)

- **`transaction_items_raw`** — 1 baris per item terjual (PRODUK + TREATMENT), termasuk **`hpp_satuan` (biaya riil per unit)**. Berguna untuk margin, dan untuk **deteksi spike racikan** (join ke master produk untuk flag/kode racik + qty + `waktu_bayar`).
- **`refunds_raw`** — 1 baris per refund. Untuk analisis pembatalan/koreksi.

---

## 3. Kolom BARU di dataset yang sudah ada (dari G1–G12)

Menambah presisi untuk analisis omzet/biaya/waktu (nama pasti lihat data dictionary):
- Header transaksi: **`doc_number`** (nomor dokumen stabil untuk join), **`updated_at`**, **`diskon_item`**.
- Item: **`hpp_satuan`** (biaya riil).
- Inventory: kolom **biaya/HPP** (harga_modal, nilai_mutasi).
- Pajak/penyelesaian: **PPN**, **`tgl_settle`** (bila diaktifkan).

---

## 4. Yang TIDAK ada di export (klarifikasi, biar tak salah cari)

- **`waktu_masuk_status`** (kolom baru di tabel kunjungan) = **hanya penolong UI real-time**, **belum diekspor**. Untuk histori masuk-tahap, pakai transisi di `staff_activity_raw` (§1).
- **Status warna merah/kuning/hijau** = dihitung real-time di UI FO, **tidak disimpan**. Rekonstruksi retroaktif dari transisi (§1) — ambang: Konsul/Treatment kuning≥20/merah≥30 mnt; Bayar kuning≥6/merah≥11 mnt (10 mnt masih kuning); Obat tidak diwarnai.
- **Gangguan POS/EDC** = tidak terekam sistem (manual) → konfirmasi via follow-up ke staf yang bertugas (diketahui dari audit).

---

## 5. Cara pakai

- Ambil via **Owner Raw Data Export** (`/web/export`, owner-only), format CSV/JSON, opsi `mask_pii` bila dikirim ke AI/pihak ke-3 (meredaksi `data_lama`/`data_baru` + PII lain; `status_lama`/`status_baru` tetap aman).
- **Selalu cek `/web/export/dictionary.json`** sebagai daftar kolom terkini (source of truth) sebelum membangun parser.
- Resep derivasi lengkap (insiden merah, dwell-time, bolak-balik, racikan) → `HANDOFF_DATA_ANALYST_MODULE.md` §4.

---

*Changelog ini menandai perubahan raw export s/d 2026-07-07. Perbarui saat ada dataset/kolom baru.*
