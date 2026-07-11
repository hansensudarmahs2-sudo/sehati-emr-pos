# Sehati Clinic — Data Dictionary

**Generated:** 2026-06-05 13:46:18 UTC
**Datasets:** 13
**Total Columns:** 149
**Status:** ✅ APPROVED — DEC-046 (Phase C2.4)

---

## Tentang Dictionary Ini

Dokumen ini menjelaskan schema lengkap setiap dataset yang di-export oleh
modul Owner Raw Data Export. Source-of-truth: `sehati_clinic/app/services/_export_columns.py`.

**Programmatic access untuk AI:**
- Endpoint JSON: `GET /web/export/dictionary.json` (Owner only)
- Endpoint Markdown: `GET /web/export/dictionary.md` (Owner only)
- Bundled di setiap ZIP pack sebagai `DATA_DICTIONARY.md`

**Type convention:**
- `int`, `float`, `str`, `date`, `datetime`, `bool`
- Suffix ` | null` menunjukkan field nullable
- `dict (JSON)` untuk field JSON struktur

**Privacy notes:**
- Field di list `Mask PII affects` akan di-hash kalau flag `mask_pii=true`.
- Selalu pakai `mask_pii=true` saat export untuk AI external / 3rd party.
- `id_*` integer fields TIDAK pernah di-mask (perlu untuk JOIN antar dataset).

---

## 01. `daily_operational_summary`

**Label:** Daily Operational Summary

**Description:** 1 row per hari: kunjungan, pasien baru, konsul, tindakan, transaksi, omzet, diskon, resep.

**Source Tables:** `kunjungan`, `pasien`, `pemeriksaan_klinis`, `kunjungan_tindakan`, `transaksi_kasir`, `kunjungan_resep`

**Filter:** tanggal range (per source pakai field tgl_*/waktu_* masing-masing)

**Mask PII affects:** (none)

**Columns (9):**

| # | Column | Type | Description |
|---|--------|------|-------------|
| 1 | `tanggal` | `date` | Hari yang di-rekap (ISO YYYY-MM-DD). Include hari kosong dengan nilai 0 untuk distribusi lengkap. |
| 2 | `jumlah_kunjungan` | `int` | Count kunjungan dengan tgl_kunjungan di tanggal ini. |
| 3 | `jumlah_pasien_baru` | `int` | Count pasien baru di-create di tanggal ini (filter pasien.created_at). |
| 4 | `jumlah_konsul_dokter` | `int` | Count pemeriksaan_klinis (SOAP) di kunjungan tanggal ini. |
| 5 | `jumlah_tindakan_selesai` | `int` | Count kunjungan_tindakan status=SELESAI dengan waktu_selesai di tanggal ini. |
| 6 | `jumlah_transaksi` | `int` | Count transaksi_kasir dengan waktu_bayar di tanggal ini. |
| 7 | `total_omzet` | `float` | Sum total_tagihan transaksi_kasir di tanggal ini (Rp). |
| 8 | `total_diskon` | `float` | Sum nominal_diskon transaksi_kasir di tanggal ini (Rp). |
| 9 | `jumlah_resep_dibayar` | `int` | Count kunjungan_resep status=DIBAYAR di kunjungan tanggal ini. |

---

## 02. `visits_raw`

**Label:** Visits Raw

**Description:** 1 row per kunjungan dengan info pasien + FO. mask_pii affects nama_pasien.

**Source Tables:** `kunjungan`, `pasien`, `master_staf`

**Filter:** kunjungan.tgl_kunjungan range

**Mask PII affects:** `nama_pasien`

**Columns (11):**

| # | Column | Type | Description |
|---|--------|------|-------------|
| 1 | `id_kunjungan` | `int` | Primary key kunjungan. |
| 2 | `tgl_kunjungan` | `datetime` | Waktu kunjungan. |
| 3 | `id_pasien` | `int` | FK ke pasien.id_pasien. |
| 4 | `no_rm` | `str` | Nomor RM pasien (unique per pasien). |
| 5 | `nama_pasien` | `str` | Nama lengkap pasien. Mask-able via mask_pii → 'PASIEN_HASH_xxxxxxxx'. |
| 6 | `status_antrian` | `str` | Status sekarang (ANTRI_KONSULTASI/KONSULTASI/.../COMPLETED/BATAL). |
| 7 | `sumber_pendaftaran` | `str` | Sumber: WALK_IN / BOOKING / DOKTER_RUJUKAN / dll. |
| 8 | `keluhan_utama` | `str | null` | Keluhan input FO saat daftar (text). |
| 9 | `id_staf_fo` | `int | null` | FK FO yang daftar. |
| 10 | `nama_fo` | `str | null` | Nama staff FO (nullable kalau staf hilang). |
| 11 | `created_at` | `datetime` | Timestamp record di-insert. |

---

## 03. `treatments_raw`

**Label:** Treatments Raw

**Description:** 1 row per tindakan dengan info treatment + pelaksana + durasi aktual.

**Source Tables:** `kunjungan_tindakan`, `master_treatment`, `master_staf`, `kunjungan`

**Filter:** kunjungan.tgl_kunjungan range

**Mask PII affects:** (none)

**Columns (14):**

| # | Column | Type | Description |
|---|--------|------|-------------|
| 1 | `id_kunjungan_tindakan` | `int` | Primary key kunjungan_tindakan. |
| 2 | `id_kunjungan` | `int` | FK ke kunjungan. |
| 3 | `tgl_kunjungan` | `datetime` | Waktu kunjungan (dari kunjungan). |
| 4 | `id_pasien` | `int` | FK ke pasien (denormalized via kunjungan). |
| 5 | `id_treatment` | `int` | FK ke master_treatment. |
| 6 | `nama_treatment` | `str` | Nama treatment dari master. |
| 7 | `role_pelaksana` | `str` | Role yang boleh laksanakan (Dokter/Perawat/dll). |
| 8 | `harga_master` | `float` | Harga di master_treatment.harga (Rp). Pre-diskon. |
| 9 | `status_tindakan` | `str` | PENDING / PROSES / SELESAI. |
| 10 | `id_staf_pelaksana` | `int | null` | FK staff yang execute tindakan. |
| 11 | `nama_pelaksana` | `str | null` | Nama staff pelaksana. |
| 12 | `waktu_mulai` | `datetime | null` | Waktu start tindakan. |
| 13 | `waktu_selesai` | `datetime | null` | Waktu end tindakan. |
| 14 | `durasi_aktual_menit` | `int | null` | Computed: (waktu_selesai − waktu_mulai) dalam menit. |

---

## 04. `products_prescription_sales_raw`

**Label:** Products Prescription Sales Raw

**Description:** 1 row per item resep (produk) dengan qty + harga + status.

**Source Tables:** `kunjungan_resep`, `master_produk`, `kunjungan`

**Filter:** kunjungan.tgl_kunjungan range

**Mask PII affects:** (none)

**Columns (14):**

| # | Column | Type | Description |
|---|--------|------|-------------|
| 1 | `id_resep` | `int` | Primary key kunjungan_resep. |
| 2 | `id_kunjungan` | `int` | FK ke kunjungan. |
| 3 | `tgl_kunjungan` | `datetime` | Waktu kunjungan. |
| 4 | `id_pasien` | `int` | FK pasien (denormalized via kunjungan). |
| 5 | `id_produk` | `int` | FK ke master_produk. |
| 6 | `kode_produk` | `str` | Kode produk (e.g., 'KM01', 'AUTO-0042'). |
| 7 | `nama_produk` | `str` | Nama produk dari master. |
| 8 | `tipe_produk` | `str` | RETAIL / CABIN / ALAT (tipe master_produk). |
| 9 | `harga_satuan_master` | `float` | Harga jual per unit dari master (Rp). Pre-diskon. |
| 10 | `qty` | `float` | Qty diresepkan (pcs/tablet/dll, sesuai satuan master). |
| 11 | `subtotal_estimasi` | `float` | Computed: qty × harga_satuan_master (Rp). Estimasi pre-diskon. |
| 12 | `aturan_pakai` | `str | null` | Instruksi pemakaian (e.g., '3×1 setelah makan'). |
| 13 | `status_item` | `str` | PENDING / BATAL / DIBAYAR. |
| 14 | `id_staf_input` | `int` | FK staff yang input resep (Dokter/FO). |

---

## 05. `transactions_header_raw`

**Label:** Transactions Header Raw

**Description:** 1 row per transaksi kasir dengan total tagihan + diskon. mask_pii affects nama_pasien.

**Source Tables:** `transaksi_kasir`, `kunjungan`, `pasien`, `master_staf`

**Filter:** transaksi_kasir.waktu_bayar range

**Mask PII affects:** `nama_pasien`

**Columns (12):**

| # | Column | Type | Description |
|---|--------|------|-------------|
| 1 | `id_transaksi` | `int` | Primary key transaksi_kasir. |
| 2 | `id_kunjungan` | `int | null` | FK ke kunjungan. |
| 3 | `id_pasien` | `int | null` | FK pasien (denormalized via kunjungan). |
| 4 | `no_rm` | `str | null` | Nomor RM pasien. |
| 5 | `nama_pasien` | `str | null` | Nama pasien. Mask-able via mask_pii. |
| 6 | `waktu_bayar` | `datetime | null` | Timestamp pembayaran selesai. |
| 7 | `id_staf_kasir` | `int | null` | FK kasir yang handle transaksi. |
| 8 | `nama_kasir` | `str | null` | Nama kasir. |
| 9 | `subtotal` | `float` | Subtotal sebelum diskon (Rp). |
| 10 | `nominal_diskon` | `float` | Diskon yang diberi (Rp). |
| 11 | `total_tagihan` | `float` | Total final yang dibayar (Rp) = subtotal − diskon. |
| 12 | `keterangan_promo` | `str | null` | Catatan promo/diskon (e.g., 'Member VIP 10%'). |

---

## 06. `transactions_detail_raw`

**Label:** Transactions Detail Raw

**Description:** 1 row per metode bayar per transaksi (split payment ready).

**Source Tables:** `transaksi_pembayaran`, `transaksi_kasir`

**Filter:** transaksi_kasir.waktu_bayar range

**Mask PII affects:** (none)

**Columns (5):**

| # | Column | Type | Description |
|---|--------|------|-------------|
| 1 | `id_pembayaran` | `int` | Primary key transaksi_pembayaran. |
| 2 | `id_transaksi` | `int` | FK ke transaksi_kasir (parent). |
| 3 | `waktu_bayar` | `datetime | null` | Timestamp dari transaksi_kasir parent (denormalized). |
| 4 | `metode_bayar` | `str` | CASH / DEBIT / KREDIT / QRIS / TRANSFER / dll. |
| 5 | `nominal` | `float` | Nominal yang dibayar via metode ini (Rp). Split payment ready. |

---

## 07. `inventory_movements_raw`

**Label:** Inventory Movements Raw

**Description:** 1 row per mutasi stok (polymorphic produk + bahan).

**Source Tables:** `inventory_history`, `master_produk`, `inventory_stok`, `master_staf`

**Filter:** inventory_history.waktu_mutasi range

**Mask PII affects:** (none)

**Columns (14):**

| # | Column | Type | Description |
|---|--------|------|-------------|
| 1 | `id_history` | `int` | Primary key inventory_history. |
| 2 | `waktu_mutasi` | `datetime` | Timestamp mutasi terjadi. |
| 3 | `tipe_item` | `str` | PRODUK atau BAHAN (polymorphic). Determinant untuk id_produk vs id_bahan. |
| 4 | `id_produk` | `int | null` | FK master_produk. XOR dengan id_bahan. |
| 5 | `nama_produk` | `str | null` | Nama produk (kalau tipe_item=PRODUK). |
| 6 | `id_bahan` | `int | null` | FK inventory_stok. XOR dengan id_produk. |
| 7 | `nama_bahan` | `str | null` | Nama bahan (kalau tipe_item=BAHAN). |
| 8 | `jenis_mutasi` | `str` | PEMBELIAN / TINDAKAN / PENJUALAN / PENYESUAIAN / WRITE_OFF / RETUR. |
| 9 | `qty_perubahan` | `float` | Delta stok. Negatif = keluar, positif = masuk. |
| 10 | `stok_akhir` | `float` | Snapshot stok setelah mutasi (cumulative). |
| 11 | `id_staf` | `int | null` | FK staff yang trigger mutasi. |
| 12 | `nama_staf` | `str | null` | Nama staff actor. |
| 13 | `referensi` | `str | null` | Reference link (e.g., 'Tindakan ID-123', 'PO-260605-001'). |
| 14 | `keterangan` | `str | null` | Catatan bebas tentang mutasi. |

---

## 08. `purchasing_orders_header_raw`

**Label:** Purchasing Orders Header Raw

**Description:** 1 row per PO (header).

**Source Tables:** `pemesanan`, `master_staf`

**Filter:** pemesanan.created_at range

**Mask PII affects:** (none)

**Columns (12):**

| # | Column | Type | Description |
|---|--------|------|-------------|
| 1 | `id_pemesanan` | `int` | Primary key pemesanan (PO). |
| 2 | `nomor_po` | `str` | Nomor PO format 'PO-YYMMDD-NNN'. Unique. |
| 3 | `tgl_pemesanan` | `datetime` | Waktu PO di-create. |
| 4 | `supplier_nama` | `str | null` | Nama supplier (free text). |
| 5 | `tgl_perkiraan_datang` | `date | null` | Estimasi barang tiba. |
| 6 | `status` | `str` | SUBMITTED / ORDERED / PARTIAL_RECEIVED / RECEIVED / CANCELLED. |
| 7 | `id_staf_pemesan` | `int | null` | FK staff yang create PO. |
| 8 | `nama_pemesan` | `str | null` | Nama pemesan. |
| 9 | `total_estimasi_biaya` | `float` | Total estimasi biaya (sum item subtotal) (Rp). |
| 10 | `catatan` | `str | null` | Catatan bebas PO. |
| 11 | `created_at` | `datetime | null` | Timestamp record insert. |
| 12 | `updated_at` | `datetime | null` | Timestamp record last update. |

---

## 09. `purchasing_orders_item_raw`

**Label:** Purchasing Orders Item Raw

**Description:** 1 row per item PO (polymorphic produk + bahan).

**Source Tables:** `pemesanan_item`, `pemesanan`

**Filter:** pemesanan.created_at range (JOIN to parent)

**Mask PII affects:** (none)

**Columns (13):**

| # | Column | Type | Description |
|---|--------|------|-------------|
| 1 | `id_item` | `int` | Primary key pemesanan_item. |
| 2 | `id_pemesanan` | `int` | FK parent pemesanan. |
| 3 | `nomor_po` | `str` | Nomor PO (denormalized untuk easy JOIN). |
| 4 | `tipe_item` | `str` | PRODUK atau BAHAN (polymorphic, XOR). |
| 5 | `id_produk` | `int | null` | FK master_produk kalau tipe_item=PRODUK. |
| 6 | `id_bahan` | `int | null` | FK inventory_stok kalau tipe_item=BAHAN. |
| 7 | `nama_snapshot` | `str` | Nama item snapshot saat PO di-create (resilient terhadap rename master). |
| 8 | `satuan_snapshot` | `str | null` | Satuan snapshot saat PO. |
| 9 | `qty_dipesan` | `float` | Qty yang dipesan. |
| 10 | `qty_diterima` | `float` | Qty yang sudah diterima (akumulasi receive events). 0 ≤ qty_diterima ≤ qty_dipesan. |
| 11 | `harga_satuan` | `float` | Harga per unit (Rp). Bisa NULL kalau belum dikonfirmasi supplier. |
| 12 | `subtotal` | `float` | qty_dipesan × harga_satuan (Rp). |
| 13 | `catatan_item` | `str | null` | Catatan item-level. |

---

## 10. `purchasing_orders_receive_raw`

**Label:** Purchasing Orders Receive Raw

**Description:** 1 row per event receive (partial receive ready).

**Source Tables:** `pemesanan_receive`, `pemesanan`, `master_staf`

**Filter:** pemesanan_receive.tgl_terima range

**Mask PII affects:** (none)

**Columns (10):**

| # | Column | Type | Description |
|---|--------|------|-------------|
| 1 | `id_receive` | `int` | Primary key pemesanan_receive (event log). |
| 2 | `id_pemesanan_item` | `int` | FK ke pemesanan_item (item yang di-receive). |
| 3 | `id_pemesanan` | `int` | FK parent pemesanan (denormalized). |
| 4 | `nomor_po` | `str` | Nomor PO (denormalized untuk easy JOIN). |
| 5 | `qty_diterima_event` | `float` | Qty diterima di event ini (partial receive ready). |
| 6 | `tgl_terima` | `datetime` | Waktu receive event. |
| 7 | `id_staf_penerima` | `int | null` | FK staff yang receive. |
| 8 | `nama_receiver` | `str | null` | Nama receiver. |
| 9 | `nomor_faktur` | `str | null` | Nomor faktur supplier (kalau ada). |
| 10 | `catatan` | `str | null` | Catatan event receive. |

---

## 11. `membership_raw`

**Label:** Membership Raw

**Description:** 1 row per aktivasi membership pasien. mask_pii affects nama_pasien.

**Source Tables:** `pasien_membership_history`, `master_membership`, `pasien`, `master_staf`

**Filter:** pasien_membership_history.created_at range

**Mask PII affects:** `nama_pasien`

**Columns (14):**

| # | Column | Type | Description |
|---|--------|------|-------------|
| 1 | `id_history` | `int` | Primary key pasien_membership_history. |
| 2 | `id_pasien` | `int` | FK pasien. |
| 3 | `no_rm` | `str` | Nomor RM pasien. |
| 4 | `nama_pasien` | `str` | Nama pasien. Mask-able. |
| 5 | `id_membership` | `int` | FK master_membership (tier). |
| 6 | `nama_tier` | `str` | Nama tier (e.g., 'VIP', 'VVIP'). |
| 7 | `tgl_aktif` | `date` | Tanggal mulai aktif membership. |
| 8 | `tgl_expired` | `date` | Tanggal expired. |
| 9 | `harga_bayar` | `float` | Harga yang dibayar pasien untuk aktivasi (Rp). |
| 10 | `is_active` | `bool` | Status aktif/expired sekarang (computed via tgl_expired vs today). |
| 11 | `id_staf_aktivasi` | `int | null` | FK staff yang aktivasi. |
| 12 | `nama_aktivator` | `str | null` | Nama staff yang aktivasi. |
| 13 | `id_transaksi_aktivasi` | `int | null` | FK transaksi_kasir untuk pembayaran aktivasi. |
| 14 | `created_at` | `datetime | null` | Timestamp record insert. |

---

## 12. `medical_soap_raw`

**Label:** Medical SOAP Raw

**Description:** 1 row per SOAP (pemeriksaan_klinis) dengan anamnesa/diagnosa/saran. mask_pii affects nama_dokter.

**Source Tables:** `pemeriksaan_klinis`, `kunjungan`, `master_staf`

**Filter:** kunjungan.tgl_kunjungan range

**Mask PII affects:** `nama_dokter`

**Columns (11):**

| # | Column | Type | Description |
|---|--------|------|-------------|
| 1 | `id_pemeriksaan` | `int` | Primary key pemeriksaan_klinis. |
| 2 | `id_kunjungan` | `int` | FK kunjungan. |
| 3 | `tgl_kunjungan` | `datetime` | Waktu kunjungan (dari kunjungan). |
| 4 | `id_pasien` | `int | null` | FK pasien. |
| 5 | `id_staf_dokter` | `int | null` | FK dokter yang konsul. |
| 6 | `nama_dokter` | `str | null` | Nama dokter. Mask-able via mask_pii → 'DOKTER_HASH_xxxxxxxx'. |
| 7 | `anamnesa` | `str | null` | S - Subjective (free text). PII risk: dokter mungkin tulis nama pasien di sini. |
| 8 | `pemeriksaan_fisik` | `str | null` | O - Objective (free text). |
| 9 | `diagnosa` | `str | null` | A - Assessment (diagnosis). |
| 10 | `saran_treatment` | `str | null` | P partial — catatan dokter untuk perawat saat eksekusi. |
| 11 | `saran_produk` | `str | null` | P partial — instruksi tambahan untuk pasien saat pakai produk. |

---

## 13. `staff_activity_raw`

**Label:** Staff Activity Raw

**Description:** 1 row per audit log event (Mode A: metadata only, no data snapshot).

**Source Tables:** `audit_log`, `master_staf`

**Filter:** audit_log.waktu range

**Mask PII affects:** (none)

**Columns (10):**

| # | Column | Type | Description |
|---|--------|------|-------------|
| 1 | `id_log` | `int` | Primary key audit_log. |
| 2 | `waktu` | `datetime` | Timestamp event terjadi. |
| 3 | `id_staf` | `int | null` | FK staff yang trigger event. NULL untuk LOGIN_FAIL pre-auth. |
| 4 | `nama_staf` | `str | null` | Nama staff. |
| 5 | `role_staf` | `str | null` | Role staff (OWNER/SUPERADMIN/.../FO). |
| 6 | `aksi` | `str` | Action type (CREATE/UPDATE/DELETE/LOGIN_SUCCESS/LOGIN_FAIL/PO_CANCEL/EXPORT_PACK/EXPORT_DATASET/dll). |
| 7 | `tabel_target` | `str | null` | Tabel yang di-affect (pasien/kunjungan/pemesanan/dll). |
| 8 | `id_target` | `int | null` | ID record target di tabel_target. |
| 9 | `status_aksi` | `str` | SUCCESS atau FAILED. |
| 10 | `keterangan` | `str | null` | Detail event (free text). Mode A: tidak include data_lama/data_baru JSON snapshot. |

---

## Changelog

- **2026-06-05** — v1.0 initial (C2.4): 13 datasets, 149 columns. Auto-generated dari `_export_columns.py`.
