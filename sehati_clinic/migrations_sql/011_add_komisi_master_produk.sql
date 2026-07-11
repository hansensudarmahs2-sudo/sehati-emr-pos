-- =============================================================================
-- Migration 011 — Komisi System Master Produk (Task #361)
-- Tanggal: 8 Juni 2026
-- Konteks: Dokter dapat komisi saat resepkan produk. Apoteker tidak (sesuai
--          keputusan dr. Hansen). Formula simpler tanpa perawat:
--          laba_bersih = (harga_jual - hpp_per_unit - pajak) / (1 + Pd)
--          komisi_dokter = laba_bersih × persen_dokter
-- =============================================================================

ALTER TABLE master_produk
ADD COLUMN hpp_per_unit DECIMAL(12,2) NULL DEFAULT 0
COMMENT 'Harga Pokok Penjualan per unit. Admin set manual (kelak bisa auto dari pemesanan_detail avg)';

ALTER TABLE master_produk
ADD COLUMN komisi_dokter_persen DECIMAL(5,2) NULL DEFAULT 0
COMMENT 'Persentase komisi dokter dari laba bersih saat produk diresepkan (0-100)';

ALTER TABLE master_produk
ADD COLUMN pajak_persen DECIMAL(5,2) NULL DEFAULT 0
COMMENT 'Pajak per produk (% dari harga jual). NULL atau 0 = tanpa pajak';

ALTER TABLE master_produk
ADD COLUMN pajak_nominal DECIMAL(12,2) NULL
COMMENT 'Pajak nominal alternatif (override pajak_persen kalau diisi). NULL = pakai pajak_persen';

-- Index untuk report
CREATE INDEX idx_master_produk_komisi
ON master_produk(komisi_dokter_persen);

-- =============================================================================
-- Apply: sudo mysql db_sehati < migrations_sql/011_add_komisi_master_produk.sql
-- Verify: sudo mysql db_sehati -e "DESCRIBE master_produk;" | grep -E "komisi|hpp|pajak"
-- =============================================================================
