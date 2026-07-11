-- =====================================================================
-- Cleanup SEMUA Data Dummy Audit (DUMMY%) — "DUMMY TEST 2506"
-- Dibuat: 2026-06-25 (UX audit walkthrough via Chrome DevTools)
--
-- Menghapus pasien test + semua jejaknya (kunjungan, SOAP, tindakan,
-- transaksi, pembayaran) yang dibuat saat audit alur-dalam.
--
-- Anchor: nama pasien = 'DUMMY TEST 2506' (id_pasien 1405, RM 260625-001).
--
-- ⚠️  BACKUP DB DULU.  Jalankan Section A (preview) sebelum Section B (delete).
-- ⚠️  Pakai sudo di WSL:  sudo mysql db_sehati < cleanup_dummy_test_2506.sql
-- =====================================================================


-- =====================================================================
-- SECTION A — PREVIEW (read-only)
-- =====================================================================

-- A1. Konfirmasi pasien target
SELECT id_pasien, no_rm, nama, jenis_kelamin, created_at
FROM pasien
WHERE nama LIKE 'DUMMY%';

-- A2. Kunjungan terkait
SELECT id_kunjungan, tgl_kunjungan, status_antrian
FROM kunjungan
WHERE id_pasien IN (SELECT id_pasien FROM pasien WHERE nama LIKE 'DUMMY%');

-- A3. Transaksi terkait
SELECT tk.id_transaksi, tk.id_kunjungan, tk.status_transaksi, tk.total_tagihan
FROM transaksi_kasir tk
WHERE tk.id_kunjungan IN (
    SELECT id_kunjungan FROM kunjungan
    WHERE id_pasien IN (SELECT id_pasien FROM pasien WHERE nama LIKE 'DUMMY%')
);


-- =====================================================================
-- SECTION B — DELETE (urut child → parent, hindari FK error)
-- Bungkus dalam transaction supaya bisa rollback kalau ada yang aneh.
-- =====================================================================

START TRANSACTION;

-- Set variabel daftar kunjungan target
-- (MySQL tidak support array; pakai subquery berulang.)

-- B1. Pembayaran (child transaksi_kasir)
DELETE FROM transaksi_pembayaran
WHERE id_transaksi IN (
    SELECT id_transaksi FROM transaksi_kasir WHERE id_kunjungan IN (
        SELECT id_kunjungan FROM kunjungan WHERE id_pasien IN (
            SELECT id_pasien FROM pasien WHERE nama LIKE 'DUMMY%')));

-- B2. Detail produk transaksi (kalau ada)
DELETE FROM transaksi_detail_produk
WHERE id_transaksi IN (
    SELECT id_transaksi FROM transaksi_kasir WHERE id_kunjungan IN (
        SELECT id_kunjungan FROM kunjungan WHERE id_pasien IN (
            SELECT id_pasien FROM pasien WHERE nama LIKE 'DUMMY%')));

-- B3. Transaksi kasir
DELETE FROM transaksi_kasir
WHERE id_kunjungan IN (
    SELECT id_kunjungan FROM kunjungan WHERE id_pasien IN (
        SELECT id_pasien FROM pasien WHERE nama LIKE 'DUMMY%'));

-- B4. Tindakan + resep + SOAP
DELETE FROM kunjungan_tindakan
WHERE id_kunjungan IN (
    SELECT id_kunjungan FROM kunjungan WHERE id_pasien IN (
        SELECT id_pasien FROM pasien WHERE nama LIKE 'DUMMY%'));

DELETE FROM kunjungan_resep
WHERE id_kunjungan IN (
    SELECT id_kunjungan FROM kunjungan WHERE id_pasien IN (
        SELECT id_pasien FROM pasien WHERE nama LIKE 'DUMMY%'));

DELETE FROM pemeriksaan_klinis
WHERE id_kunjungan IN (
    SELECT id_kunjungan FROM kunjungan WHERE id_pasien IN (
        SELECT id_pasien FROM pasien WHERE nama LIKE 'DUMMY%'));

-- B5. Antropometri kunjungan (kalau ada)
DELETE FROM kunjungan_antropometri
WHERE id_kunjungan IN (
    SELECT id_kunjungan FROM kunjungan WHERE id_pasien IN (
        SELECT id_pasien FROM pasien WHERE nama LIKE 'DUMMY%'));

-- B6. Kunjungan
DELETE FROM kunjungan
WHERE id_pasien IN (SELECT id_pasien FROM pasien WHERE nama LIKE 'DUMMY%');

-- B7. Pasien (terakhir)
DELETE FROM pasien WHERE nama LIKE 'DUMMY%';

-- Cek dulu hasilnya sebelum commit. Kalau OK:
COMMIT;
-- Kalau ada yang salah, ganti COMMIT di atas dengan: ROLLBACK;


-- =====================================================================
-- SECTION C — VERIFIKASI (read-only, jalankan setelah COMMIT)
-- =====================================================================
SELECT COUNT(*) AS sisa_pasien_dummy FROM pasien WHERE nama LIKE 'DUMMY%';
-- Harusnya 0.

-- CATATAN: Master treatment "Facial Acne" yang dipakai TIDAK dihapus
-- (itu data master asli, bukan dummy). Hanya jejak pasien test yang dibuang.
-- =====================================================================
