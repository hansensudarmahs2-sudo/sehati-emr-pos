-- =============================================================================
-- Update 80 produk topikal (TPK-%): stok awal 100 + pajak 11% + komisi dokter 5% margin
-- Scoped ke kode_produk LIKE 'TPK-%' (tidak menyentuh produk/treatment lain).
-- Jalankan:  mysql -u klinik_dev -p db_sehati < update_topikal_stok_pajak_komisi.sql
-- =============================================================================
USE db_sehati;

-- 1) Set pajak 11%, komisi dokter 5% dari MARGIN, stok cache 100
UPDATE master_produk
SET pajak_persen        = 11.00,
    pajak_nominal       = NULL,             -- pakai persen, bukan nominal
    komisi_dokter_tipe  = 'PERSEN_MARGIN',
    komisi_dokter_value = 5.00,
    stok_terkini        = 100
WHERE kode_produk LIKE 'TPK-%';

-- 2) Buat 1 lot awal AKTIF per produk (provenance FEFO; hindari warning cache-vs-lot)
--    Idempoten: hanya insert kalau belum ada lot 'INIT-JD' utk produk itu.
INSERT INTO stok_lot
  (tipe_item, id_produk, lokasi, batch_no, tgl_ed, qty_masuk, qty_sisa, harga_terima, tgl_masuk, status)
SELECT 'PRODUK', p.id_produk, 'RETAIL', 'INIT-JD', NULL, 100, 100,
       COALESCE(p.hpp_per_unit, 0), CURDATE(), 'AKTIF'
FROM master_produk p
WHERE p.kode_produk LIKE 'TPK-%'
  AND NOT EXISTS (
    SELECT 1 FROM stok_lot l
    WHERE l.id_produk = p.id_produk AND l.batch_no = 'INIT-JD'
  );

-- 3) Verifikasi
SELECT COUNT(*) AS produk_updated,
       SUM(stok_terkini=100) AS stok100,
       SUM(pajak_persen=11)  AS pajak11,
       SUM(komisi_dokter_tipe='PERSEN_MARGIN' AND komisi_dokter_value=5) AS komisi5margin
FROM master_produk WHERE kode_produk LIKE 'TPK-%';

SELECT COUNT(*) AS lot_init_dibuat FROM stok_lot WHERE batch_no='INIT-JD';

SELECT kode_produk, nama_produk, harga_jual, hpp_per_unit, pajak_persen,
       komisi_dokter_tipe, komisi_dokter_value, stok_terkini
FROM master_produk WHERE kode_produk LIKE 'TPK-%' ORDER BY id_produk LIMIT 5;
