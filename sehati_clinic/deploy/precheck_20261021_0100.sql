-- Prapemeriksaan migrasi 20261021_0100 (bayar dulu tahap 1) — HANYA MEMBACA.
--
-- Tindakan SELESAI di kunjungan yang sudah punya transaksi BAYAR, yang TIDAK bisa
-- dipasangkan ke transaksinya oleh backfill migrasi (tak ada snapshot
-- transaksi_detail_tindakan di transaksi BAYAR, dan tak ada transaksi BAYAR di kunjungannya
-- dengan waktu_bayar >= waktu_selesai). Bila ada, `alembic upgrade` BERHENTI di awal tanpa
-- mengubah apa pun. Hasil kosong = aman di-deploy.
--
-- Catatan: tindakan susulan yang memang BELUM DITAGIH (selesai sesudah pembayaran terakhir)
-- ikut muncul. Jalankan sesudah semua tagihan hari itu lunas (kasir sudah tutup).
--
-- Memakai kolom yang SUDAH ada sebelum migrasi (tanpa kunjungan_tindakan.id_transaksi).
-- Jalankan di mini PC (dari /srv/sehati):
--   docker compose exec -T sehati-db sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" db_sehati' < deploy/precheck_20261021_0100.sql
--
-- ⚠ SELECT di bawah HARUS sama dengan `_SQL_PRECHECK` di
-- migrations/versions/20261021_0100_bayar_dulu_tahap1.py (dijaga
-- tests/integration/test_bayar_dulu_tahap1.py::test_precheck_sql_berkas_sama_dengan_migrasi).
SELECT kt.id_kunjungan_tindakan FROM kunjungan_tindakan kt
WHERE kt.status_tindakan = 'SELESAI'
AND EXISTS (SELECT 1 FROM transaksi_kasir t
WHERE t.id_kunjungan = kt.id_kunjungan AND t.status_transaksi = 'BAYAR')
AND NOT EXISTS (SELECT 1 FROM transaksi_detail_tindakan d
JOIN transaksi_kasir t ON t.id_transaksi = d.id_transaksi
WHERE d.id_kunjungan_tindakan = kt.id_kunjungan_tindakan AND t.status_transaksi = 'BAYAR')
AND NOT EXISTS (SELECT 1 FROM transaksi_kasir t
WHERE t.id_kunjungan = kt.id_kunjungan AND t.status_transaksi = 'BAYAR'
AND kt.waktu_selesai IS NOT NULL AND t.waktu_bayar >= kt.waktu_selesai);
