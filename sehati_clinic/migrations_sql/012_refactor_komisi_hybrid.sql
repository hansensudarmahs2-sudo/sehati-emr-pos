-- =============================================================================
-- Migration 012 — Refactor Komisi ke Hybrid Mode (DEC-060)
-- Tanggal: 8 Juni 2026 (siang)
-- Konteks: Diskusi dr. Hansen — komisi seharusnya MASUK HPP/COGS
--          (akuntansi standar), bukan recursive % dari laba bersih.
--          Plus support 3 mode (% harga / % margin / nominal) per pelaku.
--
-- Yang berubah:
-- 1. DROP komisi_dokter_persen dari master_treatment + master_produk (+ index)
-- 2. DROP komisi_perawat_persen dari master_treatment
-- 3. ADD field hybrid: komisi_*_tipe (ENUM) + komisi_*_value (DECIMAL)
--
-- Field LAMA dipertahankan (bhp, hpp, pajak_*) — masih relevan.
-- =============================================================================

-- ============================================================================
-- 1. master_treatment: DROP old + ADD new
-- ============================================================================

-- Drop composite index dulu (kalau ada)
ALTER TABLE master_treatment
DROP INDEX idx_master_treatment_komisi;

-- Drop old fields
ALTER TABLE master_treatment
DROP COLUMN komisi_dokter_persen;

ALTER TABLE master_treatment
DROP COLUMN komisi_perawat_persen;

-- Add hybrid fields untuk dokter
ALTER TABLE master_treatment
ADD COLUMN komisi_dokter_tipe VARCHAR(20) NULL
COMMENT 'Tipe komisi: PERSEN_HARGA / PERSEN_MARGIN / NOMINAL. NULL = tanpa komisi';

ALTER TABLE master_treatment
ADD COLUMN komisi_dokter_value DECIMAL(12,2) NULL DEFAULT 0
COMMENT 'Nilai komisi. Interpretasi tergantung tipe (% atau rupiah)';

-- Add hybrid fields untuk perawat
ALTER TABLE master_treatment
ADD COLUMN komisi_perawat_tipe VARCHAR(20) NULL
COMMENT 'Tipe komisi perawat: PERSEN_HARGA / PERSEN_MARGIN / NOMINAL. NULL = tanpa komisi';

ALTER TABLE master_treatment
ADD COLUMN komisi_perawat_value DECIMAL(12,2) NULL DEFAULT 0
COMMENT 'Nilai komisi perawat. Interpretasi tergantung tipe';

-- Reindex untuk filter report komisi
CREATE INDEX idx_master_treatment_komisi_tipe
ON master_treatment(komisi_dokter_tipe, komisi_perawat_tipe);


-- ============================================================================
-- 2. master_produk: DROP old + ADD new (hanya dokter)
-- ============================================================================

ALTER TABLE master_produk
DROP INDEX idx_master_produk_komisi;

ALTER TABLE master_produk
DROP COLUMN komisi_dokter_persen;

ALTER TABLE master_produk
ADD COLUMN komisi_dokter_tipe VARCHAR(20) NULL
COMMENT 'Tipe komisi dokter produk: PERSEN_HARGA / PERSEN_MARGIN / NOMINAL';

ALTER TABLE master_produk
ADD COLUMN komisi_dokter_value DECIMAL(12,2) NULL DEFAULT 0
COMMENT 'Nilai komisi dokter produk';

CREATE INDEX idx_master_produk_komisi_tipe
ON master_produk(komisi_dokter_tipe);


-- ============================================================================
-- Apply instructions:
-- ============================================================================
-- # Backup dulu!
-- sudo mysqldump db_sehati > backup_pre_012_$(date +%Y%m%d_%H%M%S).sql
--
-- # Apply ke production
-- sudo mysql db_sehati < migrations_sql/012_refactor_komisi_hybrid.sql
--
-- # Apply juga ke test DB
-- sudo mysql db_sehati_test < migrations_sql/012_refactor_komisi_hybrid.sql
--
-- # Verify (harus muncul tipe + value, BUKAN persen)
-- sudo mysql db_sehati -e "DESCRIBE master_treatment;" | grep -E "komisi|bhp|pajak"
-- sudo mysql db_sehati -e "DESCRIBE master_produk;" | grep -E "komisi|hpp|pajak"
--
-- Expected output (master_treatment 7 row):
--   bhp_per_pakai_nominal     decimal(12,2)
--   komisi_dokter_tipe        varchar(20)
--   komisi_dokter_value       decimal(12,2)
--   komisi_perawat_tipe       varchar(20)
--   komisi_perawat_value      decimal(12,2)
--   pajak_persen              decimal(5,2)
--   pajak_nominal             decimal(12,2)
--
-- Expected output (master_produk 5 row):
--   hpp_per_unit             decimal(12,2)
--   komisi_dokter_tipe       varchar(20)
--   komisi_dokter_value      decimal(12,2)
--   pajak_persen             decimal(5,2)
--   pajak_nominal            decimal(12,2)
-- ============================================================================
