-- =====================================================================
-- Data Cleanup — metode_bayar & sumber_pendaftaran
-- Dibuat: 2026-06-12 (sesi raw data export review)
-- Tujuan: bersihkan anomali data untuk pipeline Data Analyst
--
-- ⚠️  WAJIB BACKUP DB DULU sebelum jalankan UPDATE.
-- ⚠️  Jalankan di DB DEVELOPMENT/STAGING dulu untuk test.
-- ⚠️  Baca tiap section. Jalankan SELECT preview dulu, baru UPDATE.
--
-- Konteks (temuan investigasi):
--   - metode_bayar & sumber_pendaftaran = kolom TEKS BEBAS (String 50),
--     bukan enum integer. Tidak ada tabel lookup / legend.
--   - Nilai kanonik live: metode_bayar = TUNAI/QRIS/DEBIT/KREDIT/TRANSFER,
--     sumber_pendaftaran = WALK_IN/MEMBERSHIP_ONLY.
--   - Anomali 1: import historical pakai 'CASH' (= TUNAI).
--   - Anomali 2: 7 transaksi test paling awal (id 1-7) berisi kode angka
--     1/2/4 tanpa legend. + kunjungan legacy dengan sumber '1'.
-- =====================================================================


-- =====================================================================
-- SECTION A — PREVIEW (read-only, aman, jalankan dulu)
-- =====================================================================

-- A1. Lihat semua metode_bayar berupa kode angka mentah (test data awal)
SELECT id_pembayaran, id_transaksi, metode_bayar, nominal
FROM transaksi_pembayaran
WHERE metode_bayar REGEXP '^[0-9]+$'
ORDER BY id_transaksi, id_pembayaran;

-- A2. Lihat semua sumber_pendaftaran berupa kode angka mentah
SELECT id_kunjungan, tgl_kunjungan, status_antrian, sumber_pendaftaran
FROM kunjungan
WHERE sumber_pendaftaran REGEXP '^[0-9]+$'
ORDER BY id_kunjungan;

-- A3. Lihat berapa baris metode_bayar = 'CASH' (legacy import = TUNAI)
SELECT metode_bayar, COUNT(*) AS jumlah, SUM(nominal) AS total_nominal
FROM transaksi_pembayaran
WHERE metode_bayar = 'CASH'
GROUP BY metode_bayar;

-- A4. Distribusi lengkap metode_bayar (sanity check sebelum & sesudah)
SELECT metode_bayar, COUNT(*) AS jumlah
FROM transaksi_pembayaran
GROUP BY metode_bayar
ORDER BY jumlah DESC;


-- =====================================================================
-- SECTION B — CLEANUP kode angka test → 'UNKNOWN_LEGACY'
-- (non-destruktif: relabel supaya analyst bisa filter/exclude.
--  TIDAK dipetakan ke cash/qris karena tidak ada legend otoritatif.)
-- =====================================================================

-- B1. metode_bayar angka → UNKNOWN_LEGACY
UPDATE transaksi_pembayaran
SET metode_bayar = 'UNKNOWN_LEGACY'
WHERE metode_bayar REGEXP '^[0-9]+$';

-- B2. sumber_pendaftaran angka → UNKNOWN_LEGACY
UPDATE kunjungan
SET sumber_pendaftaran = 'UNKNOWN_LEGACY'
WHERE sumber_pendaftaran REGEXP '^[0-9]+$';


-- =====================================================================
-- SECTION C — NORMALISASI 'CASH' → 'TUNAI'
-- (samakan label legacy import dengan nilai live, semantik identik)
-- =====================================================================

-- C1. CASH → TUNAI
UPDATE transaksi_pembayaran
SET metode_bayar = 'TUNAI'
WHERE metode_bayar = 'CASH';


-- =====================================================================
-- SECTION D — VERIFIKASI PASCA-UPDATE (read-only)
-- =====================================================================

-- D1. Pastikan tidak ada lagi kode angka
SELECT COUNT(*) AS sisa_metode_angka
FROM transaksi_pembayaran
WHERE metode_bayar REGEXP '^[0-9]+$';

SELECT COUNT(*) AS sisa_sumber_angka
FROM kunjungan
WHERE sumber_pendaftaran REGEXP '^[0-9]+$';

-- D2. Pastikan tidak ada lagi 'CASH'
SELECT COUNT(*) AS sisa_cash
FROM transaksi_pembayaran
WHERE metode_bayar = 'CASH';

-- D3. Distribusi akhir metode_bayar (harusnya bersih:
--     TUNAI/QRIS/DEBIT/KREDIT/TRANSFER + UNKNOWN_LEGACY saja)
SELECT metode_bayar, COUNT(*) AS jumlah
FROM transaksi_pembayaran
GROUP BY metode_bayar
ORDER BY jumlah DESC;

-- =====================================================================
-- CATATAN:
-- - Kalau Bapak prefer EXCLUDE total 7 baris test (bukan relabel),
--   kasih tahu saya — bisa diganti jadi DELETE dengan cascade hati-hati.
-- - Setelah cleanup, regen static dictionary (opsional):
--   Project_Memory/RawDataExport/01_DATA_DICTIONARY.md
--   (DATA_DICTIONARY.md di dalam ZIP pack auto-update dari kode).
-- =====================================================================
