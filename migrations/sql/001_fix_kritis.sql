-- =============================================================================
-- MIGRASI 001 — FIX KRITIS
-- =============================================================================
-- Tujuan:
--   1. Tambah FOREIGN KEY yang hilang (referential integrity)
--   2. Ubah tipe data uang di transaksi_kasir dari INT ke DECIMAL(12,2)
--   3. Tambah index untuk query laporan
--
-- Aman dijalankan: Ya. Kalau sudah dijalankan, MySQL akan return error
--                  "Duplicate key" — tidak merusak data.
--
-- Estimasi waktu: < 30 detik untuk DB sehati skala saat ini.
-- =============================================================================

USE db_sehati;

-- ----------------------------------------------------------------------------
-- 1.1. Tambah FOREIGN KEY yang hilang
-- ----------------------------------------------------------------------------

-- kunjungan_resep
ALTER TABLE kunjungan_resep
  ADD CONSTRAINT fk_kr_kunjungan FOREIGN KEY (id_kunjungan) REFERENCES kunjungan(id_kunjungan),
  ADD CONSTRAINT fk_kr_produk FOREIGN KEY (id_produk) REFERENCES master_produk(id_produk),
  ADD CONSTRAINT fk_kr_staf_input FOREIGN KEY (id_staf_input) REFERENCES master_staf(id_staf),
  ADD CONSTRAINT fk_kr_staf_void FOREIGN KEY (id_staf_void) REFERENCES master_staf(id_staf);

-- kunjungan_foto
ALTER TABLE kunjungan_foto
  ADD CONSTRAINT fk_kf_kunjungan FOREIGN KEY (id_kunjungan) REFERENCES kunjungan(id_kunjungan),
  ADD CONSTRAINT fk_kf_pasien FOREIGN KEY (id_pasien) REFERENCES pasien(id_pasien);

-- transaksi_kasir
ALTER TABLE transaksi_kasir
  ADD CONSTRAINT fk_tk_staf_kasir FOREIGN KEY (id_staf_kasir) REFERENCES master_staf(id_staf);

-- pemeriksaan_klinis
ALTER TABLE pemeriksaan_klinis
  ADD CONSTRAINT fk_pk_staf_dokter FOREIGN KEY (id_staf_dokter) REFERENCES master_staf(id_staf);

-- pasien_rencana_treatment.id_kunjungan_eksekusi
ALTER TABLE pasien_rencana_treatment
  ADD CONSTRAINT fk_prt_kunjungan_eksekusi FOREIGN KEY (id_kunjungan_eksekusi) REFERENCES kunjungan(id_kunjungan);

-- ----------------------------------------------------------------------------
-- 1.2. Ubah tipe data uang di transaksi_kasir
-- ----------------------------------------------------------------------------
-- Note: data existing INT akan di-convert otomatis (Rp tanpa pecahan jadi
--       Rp.00). Tidak ada data loss.

ALTER TABLE transaksi_kasir
  MODIFY COLUMN subtotal DECIMAL(12,2) DEFAULT 0.00,
  MODIFY COLUMN nominal_diskon DECIMAL(12,2) DEFAULT 0.00,
  MODIFY COLUMN total_tagihan DECIMAL(12,2) NOT NULL DEFAULT 0.00;

-- transaksi_pembayaran.nominal juga harus DECIMAL untuk konsisten
ALTER TABLE transaksi_pembayaran
  MODIFY COLUMN nominal DECIMAL(12,2) NOT NULL;

-- ----------------------------------------------------------------------------
-- 1.3. Index untuk performance laporan
-- ----------------------------------------------------------------------------

CREATE INDEX idx_kunjungan_pasien_tgl ON kunjungan(id_pasien, tgl_kunjungan);
CREATE INDEX idx_kunjungan_status_tgl ON kunjungan(status_antrian, tgl_kunjungan);
CREATE INDEX idx_transaksi_waktu ON transaksi_kasir(waktu_bayar);
CREATE INDEX idx_transaksi_staf_waktu ON transaksi_kasir(id_staf_kasir, waktu_bayar);
CREATE INDEX idx_booking_tgl_status ON jadwal_booking(tgl_rencana, status_booking);
CREATE INDEX idx_inventory_history_bahan ON inventory_history(id_bahan, waktu_mutasi);
CREATE INDEX idx_inventory_history_jenis ON inventory_history(jenis_mutasi, waktu_mutasi);
CREATE INDEX idx_kunjungan_tindakan_status ON kunjungan_tindakan(status_tindakan);
CREATE INDEX idx_kunjungan_resep_status ON kunjungan_resep(status_item);

-- ----------------------------------------------------------------------------
-- Selesai
-- ----------------------------------------------------------------------------
SELECT '✅ Migrasi 001 selesai. Cek SHOW INDEX FROM kunjungan; untuk verifikasi.' AS status;
