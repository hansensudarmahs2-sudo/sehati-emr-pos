-- =============================================================================
-- Migration 010 — Komisi System Master Treatment (Task #360)
-- Tanggal: 8 Juni 2026
-- Konteks: dr. Hansen design — komisi dokter & perawat dihitung dari laba bersih.
--          Formula closed-form (recursive solved):
--          laba_bersih = (harga - BHP - pajak) / (1 + Pd + Pp)
--          komisi_dokter = laba_bersih × persen_dokter
--          komisi_perawat = laba_bersih × persen_perawat
--          BHP otomatis dihitung dari treatment_komponen × harga_satuan_bahan.
-- =============================================================================

-- BHP per pakai (manual input, simpler MVP):
-- Kelak bisa di-auto-calc dari treatment_komponen kalau InventoryStok dapat field harga.
ALTER TABLE master_treatment
ADD COLUMN bhp_per_pakai_nominal DECIMAL(12,2) NULL DEFAULT 0
COMMENT 'BHP (Bahan Habis Pakai) per 1x treatment, nominal rupiah. Manual input admin';

ALTER TABLE master_treatment
ADD COLUMN komisi_dokter_persen DECIMAL(5,2) NULL DEFAULT 0
COMMENT 'Persentase komisi dokter dari laba bersih (0-100). NULL atau 0 = tanpa komisi';

ALTER TABLE master_treatment
ADD COLUMN komisi_perawat_persen DECIMAL(5,2) NULL DEFAULT 0
COMMENT 'Persentase komisi perawat dari laba bersih (0-100). NULL atau 0 = tanpa komisi';

ALTER TABLE master_treatment
ADD COLUMN pajak_persen DECIMAL(5,2) NULL DEFAULT 0
COMMENT 'Pajak per treatment (% dari harga jual). NULL atau 0 = tanpa pajak';

ALTER TABLE master_treatment
ADD COLUMN pajak_nominal DECIMAL(12,2) NULL
COMMENT 'Pajak nominal alternatif (override pajak_persen kalau diisi). NULL = pakai pajak_persen';

-- Index untuk query report komisi
CREATE INDEX idx_master_treatment_komisi
ON master_treatment(komisi_dokter_persen, komisi_perawat_persen);

-- =============================================================================
-- Apply: sudo mysql db_sehati < migrations_sql/010_add_komisi_master_treatment.sql
-- Verify: sudo mysql db_sehati -e "DESCRIBE master_treatment;" | grep komisi
-- =============================================================================
