-- =============================================================================
-- DUMMY DATA — Produk Retail untuk simulasi Inventory + Pengadaan
-- =============================================================================
-- Tanggal: 4 Juni 2026
-- Total: 37 produk RETAIL
-- Tujuan: testing modul Inventory + Master Produk + Pengadaan
--
-- IDEMPOTENT: pakai INSERT IGNORE — kalau kode_produk sudah ada, di-skip.
-- Aman dijalankan beberapa kali, tidak akan duplikat.
--
-- Kategori (via prefix kode_produk):
--   KM-      Krim Malam (8 varian)
--   KP-      Krim Pagi (8 varian)
--   SA-      Serum Acne (3 varian)
--   SB-      Serum Brightening (3 varian)
--   FW-      Facial Wash (4 tipe)
--   MZ-      Moisturizer (3 varian)
--   TN-      Toner (2 varian)
--   OBT-     Obat Minum (6 SKU)
--
-- eligible_member_discount:
--   Skincare: TRUE (boleh diskon member)
--   Obat:     FALSE (umumnya tidak diskon)
-- =============================================================================

START TRANSACTION;

-- =============================================================================
-- A. KRIM MALAM (8 varian, harga 100k-200k, stok 30-80, min 10)
-- =============================================================================
INSERT IGNORE INTO master_produk
    (kode_produk, nama_produk, tipe_produk, satuan, harga_jual, stok_terkini, stok_minimal, default_iterasi, eligible_member_discount, is_active)
VALUES
    ('KM001', 'Krim Malam Series 1', 'RETAIL', 'botol', 110000, 45, 10, 0, 1, 1),
    ('KM002', 'Krim Malam Series 2', 'RETAIL', 'botol', 125000, 52, 10, 0, 1, 1),
    ('KM003', 'Krim Malam Series 3', 'RETAIL', 'botol', 135000, 38, 10, 0, 1, 1),
    ('KM004', 'Krim Malam Series 4', 'RETAIL', 'botol', 150000, 60, 10, 0, 1, 1),
    ('KM005', 'Krim Malam Series 5', 'RETAIL', 'botol', 165000, 71, 10, 0, 1, 1),
    ('KM006', 'Krim Malam Series 6', 'RETAIL', 'botol', 175000, 33, 10, 0, 1, 1),
    ('KM007', 'Krim Malam Series 7', 'RETAIL', 'botol', 185000, 48, 10, 0, 1, 1),
    ('KM008', 'Krim Malam Series 8', 'RETAIL', 'botol', 195000, 75, 10, 0, 1, 1);

-- =============================================================================
-- B. KRIM PAGI (8 varian, harga 100k-200k, stok 30-80, min 10)
-- =============================================================================
INSERT IGNORE INTO master_produk
    (kode_produk, nama_produk, tipe_produk, satuan, harga_jual, stok_terkini, stok_minimal, default_iterasi, eligible_member_discount, is_active)
VALUES
    ('KP001', 'Krim Pagi Series 1', 'RETAIL', 'botol', 115000, 50, 10, 0, 1, 1),
    ('KP002', 'Krim Pagi Series 2', 'RETAIL', 'botol', 120000, 42, 10, 0, 1, 1),
    ('KP003', 'Krim Pagi Series 3', 'RETAIL', 'botol', 130000, 65, 10, 0, 1, 1),
    ('KP004', 'Krim Pagi Series 4', 'RETAIL', 'botol', 140000, 36, 10, 0, 1, 1),
    ('KP005', 'Krim Pagi Series 5', 'RETAIL', 'botol', 155000, 55, 10, 0, 1, 1),
    ('KP006', 'Krim Pagi Series 6', 'RETAIL', 'botol', 170000, 68, 10, 0, 1, 1),
    ('KP007', 'Krim Pagi Series 7', 'RETAIL', 'botol', 180000, 30, 10, 0, 1, 1),
    ('KP008', 'Krim Pagi Series 8', 'RETAIL', 'botol', 198000, 78, 10, 0, 1, 1);

-- =============================================================================
-- C. SERUM ACNE (3 varian, harga 150k-300k, stok 20-50, min 8)
-- =============================================================================
INSERT IGNORE INTO master_produk
    (kode_produk, nama_produk, tipe_produk, satuan, harga_jual, stok_terkini, stok_minimal, default_iterasi, eligible_member_discount, is_active)
VALUES
    ('SA001', 'Serum Acne A', 'RETAIL', 'botol', 175000, 28, 8, 0, 1, 1),
    ('SA002', 'Serum Acne B', 'RETAIL', 'botol', 225000, 35, 8, 0, 1, 1),
    ('SA003', 'Serum Acne C', 'RETAIL', 'botol', 285000, 45, 8, 0, 1, 1);

-- =============================================================================
-- D. SERUM BRIGHTENING (3 varian, harga 150k-300k, stok 20-50, min 8)
-- =============================================================================
INSERT IGNORE INTO master_produk
    (kode_produk, nama_produk, tipe_produk, satuan, harga_jual, stok_terkini, stok_minimal, default_iterasi, eligible_member_discount, is_active)
VALUES
    ('SB001', 'Serum Brightening A', 'RETAIL', 'botol', 185000, 22, 8, 0, 1, 1),
    ('SB002', 'Serum Brightening B', 'RETAIL', 'botol', 245000, 40, 8, 0, 1, 1),
    ('SB003', 'Serum Brightening C', 'RETAIL', 'botol', 295000, 32, 8, 0, 1, 1);

-- =============================================================================
-- E. FACIAL WASH (4 tipe, harga 50k-75k, stok 40-100, min 15)
-- =============================================================================
INSERT IGNORE INTO master_produk
    (kode_produk, nama_produk, tipe_produk, satuan, harga_jual, stok_terkini, stok_minimal, default_iterasi, eligible_member_discount, is_active)
VALUES
    ('FW-NORMAL', 'Facial Wash Normal', 'RETAIL', 'botol', 55000, 80, 15, 0, 1, 1),
    ('FW-ACNE',   'Facial Wash Acne',   'RETAIL', 'botol', 60000, 95, 15, 0, 1, 1),
    ('FW-OILY',   'Facial Wash Oily',   'RETAIL', 'botol', 65000, 55, 15, 0, 1, 1),
    ('FW-SENSI',  'Facial Wash Sensitive', 'RETAIL', 'botol', 72000, 45, 15, 0, 1, 1);

-- =============================================================================
-- F. MOISTURIZER (3 varian, harga 100k-200k, stok 25-70, min 10)
-- =============================================================================
INSERT IGNORE INTO master_produk
    (kode_produk, nama_produk, tipe_produk, satuan, harga_jual, stok_terkini, stok_minimal, default_iterasi, eligible_member_discount, is_active)
VALUES
    ('MZ001', 'Moisturizer A', 'RETAIL', 'botol', 115000, 30, 10, 0, 1, 1),
    ('MZ002', 'Moisturizer B', 'RETAIL', 'botol', 145000, 48, 10, 0, 1, 1),
    ('MZ003', 'Moisturizer C', 'RETAIL', 'botol', 190000, 62, 10, 0, 1, 1);

-- =============================================================================
-- G. TONER (2 varian, harga 50k flat, stok 25-60, min 10)
-- =============================================================================
INSERT IGNORE INTO master_produk
    (kode_produk, nama_produk, tipe_produk, satuan, harga_jual, stok_terkini, stok_minimal, default_iterasi, eligible_member_discount, is_active)
VALUES
    ('TN001', 'Toner A', 'RETAIL', 'botol', 50000, 35, 10, 0, 1, 1),
    ('TN002', 'Toner B', 'RETAIL', 'botol', 50000, 55, 10, 0, 1, 1);

-- =============================================================================
-- H. OBAT MINUM (6 SKU, eligible_member_discount=FALSE)
-- =============================================================================
INSERT IGNORE INTO master_produk
    (kode_produk, nama_produk, tipe_produk, satuan, harga_jual, stok_terkini, stok_minimal, default_iterasi, eligible_member_discount, is_active)
VALUES
    -- Doxycycline 100mg — per butir, Rp3.000
    ('OBT-DOXY100', 'Doxycycline 100mg', 'RETAIL', 'butir', 3000, 200, 50, 0, 0, 1),
    -- Triamcinolone 4mg — per butir, Rp3.000
    ('OBT-TRIAM4',  'Triamcinolone 4mg', 'RETAIL', 'butir', 3000, 200, 50, 0, 0, 1),
    -- Vitamin Acne — botol isi 30, Rp250.000/botol
    ('OBT-VITACN',  'Vitamin Acne (botol isi 30)', 'RETAIL', 'botol', 250000, 40, 10, 0, 0, 1),
    -- Isotretinoin 10mg — per butir, Rp5.000
    ('OBT-ISO10',   'Isotretinoin 10mg', 'RETAIL', 'butir', 5000, 150, 50, 0, 0, 1),
    -- Isotretinoin 20mg — per butir, Rp5.000
    ('OBT-ISO20',   'Isotretinoin 20mg', 'RETAIL', 'butir', 5000, 150, 50, 0, 0, 1),
    -- Glutathione 500mg — per strip (1 strip = 6 butir), Rp60.000/strip
    ('OBT-GLUT500', 'Glutathione 500mg Strip isi 6', 'RETAIL', 'strip', 60000, 80, 20, 0, 0, 1);

COMMIT;


-- =============================================================================
-- VERIFICATION QUERIES — jalankan setelah seed selesai
-- =============================================================================

-- A. Total dummy produk yang ada di DB sekarang
SELECT 'Total dummy produk:' AS verify, COUNT(*) AS jumlah
FROM master_produk
WHERE kode_produk IN (
    'KM001','KM002','KM003','KM004','KM005','KM006','KM007','KM008',
    'KP001','KP002','KP003','KP004','KP005','KP006','KP007','KP008',
    'SA001','SA002','SA003',
    'SB001','SB002','SB003',
    'FW-NORMAL','FW-ACNE','FW-OILY','FW-SENSI',
    'MZ001','MZ002','MZ003',
    'TN001','TN002',
    'OBT-DOXY100','OBT-TRIAM4','OBT-VITACN','OBT-ISO10','OBT-ISO20','OBT-GLUT500'
);
-- Expected: 37

-- B. Group by kategori (via kode_produk prefix)
SELECT
    CASE
        WHEN kode_produk LIKE 'KM%' THEN 'Krim Malam'
        WHEN kode_produk LIKE 'KP%' THEN 'Krim Pagi'
        WHEN kode_produk LIKE 'SA%' THEN 'Serum Acne'
        WHEN kode_produk LIKE 'SB%' THEN 'Serum Brightening'
        WHEN kode_produk LIKE 'FW-%' THEN 'Facial Wash'
        WHEN kode_produk LIKE 'MZ%' THEN 'Moisturizer'
        WHEN kode_produk LIKE 'TN%' THEN 'Toner'
        WHEN kode_produk LIKE 'OBT-%' THEN 'Obat Minum'
        ELSE 'Lainnya'
    END AS kategori,
    COUNT(*) AS jumlah,
    ROUND(AVG(harga_jual), 0) AS harga_rata,
    SUM(stok_terkini) AS total_stok,
    SUM(stok_minimal) AS total_stok_min,
    SUM(harga_jual * stok_terkini) AS value_inventory
FROM master_produk
WHERE kode_produk REGEXP '^(KM|KP|SA|SB|FW-|MZ|TN|OBT-)'
GROUP BY kategori
ORDER BY kategori;
-- Expected breakdown:
--   Krim Malam:        8 row
--   Krim Pagi:         8 row
--   Serum Acne:        3 row
--   Serum Brightening: 3 row
--   Facial Wash:       4 row
--   Moisturizer:       3 row
--   Toner:             2 row
--   Obat Minum:        6 row

-- C. Cek stok di bawah minimum (harusnya 0)
SELECT 'Stok di bawah minimum (harusnya 0):' AS verify;
SELECT kode_produk, nama_produk, satuan,
       stok_terkini, stok_minimal,
       (stok_minimal - stok_terkini) AS kurang
FROM master_produk
WHERE stok_terkini < stok_minimal
  AND kode_produk REGEXP '^(KM|KP|SA|SB|FW-|MZ|TN|OBT-)'
ORDER BY kurang DESC;

-- D. Sample 5 produk teratas dari setiap kategori (untuk visual sanity check)
SELECT 'Sample produk per kategori:' AS verify;
SELECT kode_produk, nama_produk, satuan, harga_jual,
       stok_terkini, stok_minimal,
       IF(eligible_member_discount, 'YA', 'TIDAK') AS member_diskon
FROM master_produk
WHERE kode_produk REGEXP '^(KM|KP|SA|SB|FW-|MZ|TN|OBT-)'
ORDER BY kode_produk
LIMIT 10;


-- =============================================================================
-- CLEANUP — jangan jalankan kecuali memang mau hapus dummy
-- =============================================================================
-- DELETE FROM master_produk
-- WHERE kode_produk IN (
--     'KM001','KM002','KM003','KM004','KM005','KM006','KM007','KM008',
--     'KP001','KP002','KP003','KP004','KP005','KP006','KP007','KP008',
--     'SA001','SA002','SA003',
--     'SB001','SB002','SB003',
--     'FW-NORMAL','FW-ACNE','FW-OILY','FW-SENSI',
--     'MZ001','MZ002','MZ003',
--     'TN001','TN002',
--     'OBT-DOXY100','OBT-TRIAM4','OBT-VITACN','OBT-ISO10','OBT-ISO20','OBT-GLUT500'
-- );
