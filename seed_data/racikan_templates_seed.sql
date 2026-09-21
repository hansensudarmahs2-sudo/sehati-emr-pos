-- Konversi 4 template racikan flat -> Formula Racikan (master_racikan + bahan).
-- Idempoten: formula dilewati bila namanya sudah ada; bahan dilewati bila pasangan (formula,produk) sudah ada.
-- CATATAN: produk flat OBM-068..071 SENGAJA TIDAK dinonaktifkan di sini —
--          matikan baru setelah Kartu Racik di SOAP (Fase 2) live.
USE db_sehati;

-- Tab SR (dari OBM-068)
INSERT INTO master_racikan (nama, jenis_racik, default_jumlah_unit, catatan, is_active)
SELECT * FROM (SELECT 'Tab SR' AS a,'KAPSUL' AS b,15 AS c,'Konversi dari produk flat OBM-068.' AS d,1 AS e) x
WHERE NOT EXISTS (SELECT 1 FROM (SELECT nama FROM master_racikan) m WHERE m.nama='Tab SR');
INSERT INTO master_racikan_bahan (id_racikan,id_produk,dosis_per_unit,satuan_dosis,urutan)
SELECT r.id_racikan, p.id_produk, 8.000, 'mg', 1
FROM master_racikan r JOIN master_produk p ON p.kode_produk='OBM-024'
WHERE r.nama='Tab SR' AND NOT EXISTS (SELECT 1 FROM (SELECT id_racikan,id_produk FROM master_racikan_bahan) b WHERE b.id_racikan=r.id_racikan AND b.id_produk=p.id_produk);
INSERT INTO master_racikan_bahan (id_racikan,id_produk,dosis_per_unit,satuan_dosis,urutan)
SELECT r.id_racikan, p.id_produk, 7.000, 'mg', 2
FROM master_racikan r JOIN master_produk p ON p.kode_produk='OBM-019'
WHERE r.nama='Tab SR' AND NOT EXISTS (SELECT 1 FROM (SELECT id_racikan,id_produk FROM master_racikan_bahan) b WHERE b.id_racikan=r.id_racikan AND b.id_produk=p.id_produk);
INSERT INTO master_racikan_bahan (id_racikan,id_produk,dosis_per_unit,satuan_dosis,urutan)
SELECT r.id_racikan, p.id_produk, 2.000, 'mg', 3
FROM master_racikan r JOIN master_produk p ON p.kode_produk='OBM-075'
WHERE r.nama='Tab SR' AND NOT EXISTS (SELECT 1 FROM (SELECT id_racikan,id_produk FROM master_racikan_bahan) b WHERE b.id_racikan=r.id_racikan AND b.id_produk=p.id_produk);

-- Tab SR 2 (dari OBM-069)
INSERT INTO master_racikan (nama, jenis_racik, default_jumlah_unit, catatan, is_active)
SELECT * FROM (SELECT 'Tab SR 2' AS a,'KAPSUL' AS b,15 AS c,'Konversi dari produk flat OBM-069.' AS d,1 AS e) x
WHERE NOT EXISTS (SELECT 1 FROM (SELECT nama FROM master_racikan) m WHERE m.nama='Tab SR 2');
INSERT INTO master_racikan_bahan (id_racikan,id_produk,dosis_per_unit,satuan_dosis,urutan)
SELECT r.id_racikan, p.id_produk, 4.000, 'mg', 1
FROM master_racikan r JOIN master_produk p ON p.kode_produk='OBM-024'
WHERE r.nama='Tab SR 2' AND NOT EXISTS (SELECT 1 FROM (SELECT id_racikan,id_produk FROM master_racikan_bahan) b WHERE b.id_racikan=r.id_racikan AND b.id_produk=p.id_produk);
INSERT INTO master_racikan_bahan (id_racikan,id_produk,dosis_per_unit,satuan_dosis,urutan)
SELECT r.id_racikan, p.id_produk, 5.000, 'mg', 2
FROM master_racikan r JOIN master_produk p ON p.kode_produk='OBM-019'
WHERE r.nama='Tab SR 2' AND NOT EXISTS (SELECT 1 FROM (SELECT id_racikan,id_produk FROM master_racikan_bahan) b WHERE b.id_racikan=r.id_racikan AND b.id_produk=p.id_produk);
INSERT INTO master_racikan_bahan (id_racikan,id_produk,dosis_per_unit,satuan_dosis,urutan)
SELECT r.id_racikan, p.id_produk, 2.000, 'mg', 3
FROM master_racikan r JOIN master_produk p ON p.kode_produk='OBM-075'
WHERE r.nama='Tab SR 2' AND NOT EXISTS (SELECT 1 FROM (SELECT id_racikan,id_produk FROM master_racikan_bahan) b WHERE b.id_racikan=r.id_racikan AND b.id_produk=p.id_produk);

-- Tab SRO (dari OBM-070)
INSERT INTO master_racikan (nama, jenis_racik, default_jumlah_unit, catatan, is_active)
SELECT * FROM (SELECT 'Tab SRO' AS a,'KAPSUL' AS b,15 AS c,'Konversi dari produk flat OBM-070.' AS d,1 AS e) x
WHERE NOT EXISTS (SELECT 1 FROM (SELECT nama FROM master_racikan) m WHERE m.nama='Tab SRO');
INSERT INTO master_racikan_bahan (id_racikan,id_produk,dosis_per_unit,satuan_dosis,urutan)
SELECT r.id_racikan, p.id_produk, 8.000, 'mg', 1
FROM master_racikan r JOIN master_produk p ON p.kode_produk='OBM-024'
WHERE r.nama='Tab SRO' AND NOT EXISTS (SELECT 1 FROM (SELECT id_racikan,id_produk FROM master_racikan_bahan) b WHERE b.id_racikan=r.id_racikan AND b.id_produk=p.id_produk);
INSERT INTO master_racikan_bahan (id_racikan,id_produk,dosis_per_unit,satuan_dosis,urutan)
SELECT r.id_racikan, p.id_produk, 7.000, 'mg', 2
FROM master_racikan r JOIN master_produk p ON p.kode_produk='OBM-019'
WHERE r.nama='Tab SRO' AND NOT EXISTS (SELECT 1 FROM (SELECT id_racikan,id_produk FROM master_racikan_bahan) b WHERE b.id_racikan=r.id_racikan AND b.id_produk=p.id_produk);
INSERT INTO master_racikan_bahan (id_racikan,id_produk,dosis_per_unit,satuan_dosis,urutan)
SELECT r.id_racikan, p.id_produk, 2.000, 'mg', 3
FROM master_racikan r JOIN master_produk p ON p.kode_produk='OBM-075'
WHERE r.nama='Tab SRO' AND NOT EXISTS (SELECT 1 FROM (SELECT id_racikan,id_produk FROM master_racikan_bahan) b WHERE b.id_racikan=r.id_racikan AND b.id_produk=p.id_produk);
INSERT INTO master_racikan_bahan (id_racikan,id_produk,dosis_per_unit,satuan_dosis,urutan)
SELECT r.id_racikan, p.id_produk, 15.000, 'mg', 4
FROM master_racikan r JOIN master_produk p ON p.kode_produk='OBM-018'
WHERE r.nama='Tab SRO' AND NOT EXISTS (SELECT 1 FROM (SELECT id_racikan,id_produk FROM master_racikan_bahan) b WHERE b.id_racikan=r.id_racikan AND b.id_produk=p.id_produk);

-- Tab STR (dari OBM-071)
INSERT INTO master_racikan (nama, jenis_racik, default_jumlah_unit, catatan, is_active)
SELECT * FROM (SELECT 'Tab STR' AS a,'KAPSUL' AS b,15 AS c,'Konversi dari produk flat OBM-071.' AS d,1 AS e) x
WHERE NOT EXISTS (SELECT 1 FROM (SELECT nama FROM master_racikan) m WHERE m.nama='Tab STR');
INSERT INTO master_racikan_bahan (id_racikan,id_produk,dosis_per_unit,satuan_dosis,urutan)
SELECT r.id_racikan, p.id_produk, 6.000, 'mg', 1
FROM master_racikan r JOIN master_produk p ON p.kode_produk='OBM-024'
WHERE r.nama='Tab STR' AND NOT EXISTS (SELECT 1 FROM (SELECT id_racikan,id_produk FROM master_racikan_bahan) b WHERE b.id_racikan=r.id_racikan AND b.id_produk=p.id_produk);
INSERT INTO master_racikan_bahan (id_racikan,id_produk,dosis_per_unit,satuan_dosis,urutan)
SELECT r.id_racikan, p.id_produk, 2.000, 'mg', 2
FROM master_racikan r JOIN master_produk p ON p.kode_produk='OBM-026'
WHERE r.nama='Tab STR' AND NOT EXISTS (SELECT 1 FROM (SELECT id_racikan,id_produk FROM master_racikan_bahan) b WHERE b.id_racikan=r.id_racikan AND b.id_produk=p.id_produk);
INSERT INTO master_racikan_bahan (id_racikan,id_produk,dosis_per_unit,satuan_dosis,urutan)
SELECT r.id_racikan, p.id_produk, 7.000, 'mg', 3
FROM master_racikan r JOIN master_produk p ON p.kode_produk='OBM-019'
WHERE r.nama='Tab STR' AND NOT EXISTS (SELECT 1 FROM (SELECT id_racikan,id_produk FROM master_racikan_bahan) b WHERE b.id_racikan=r.id_racikan AND b.id_produk=p.id_produk);

-- Verifikasi
SELECT r.nama, r.jenis_racik, r.default_jumlah_unit, COUNT(b.id_racikan_bahan) AS jml_bahan
FROM master_racikan r LEFT JOIN master_racikan_bahan b ON b.id_racikan=r.id_racikan
GROUP BY r.id_racikan ORDER BY r.nama;
SELECT jenis_racik, tarif FROM master_biaya_racik ORDER BY jenis_racik;
