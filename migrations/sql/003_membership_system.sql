-- =============================================================================
-- MIGRASI 003 — MEMBERSHIP SYSTEM
-- =============================================================================
-- Tabel-tabel baru untuk dukung membership dengan kuota treatment + diskon.
--
-- Tabel yang dibuat:
--   1. master_membership                  — definisi tier (VIP, VVIP, dst)
--   2. master_membership_benefit_treatment — benefit kuota treatment per tier
--   3. pasien_membership_history           — record aktivasi membership
--   4. pasien_membership_kuota             — kuota tersedia per pasien
-- =============================================================================

USE db_sehati;

-- ----------------------------------------------------------------------------
-- 3.1. master_membership — definisi tier
-- ----------------------------------------------------------------------------

CREATE TABLE master_membership (
  id_membership INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  nama_tier VARCHAR(50) NOT NULL UNIQUE COMMENT 'VIP, VVIP, BASIC, GOLD, PLATINUM',
  harga_aktivasi DECIMAL(12,2) NOT NULL DEFAULT 0.00 COMMENT 'harga beli membership',
  durasi_bulan INT NOT NULL DEFAULT 12 COMMENT 'masa berlaku dalam bulan',

  -- Benefit fix
  free_konsultasi_dokter TINYINT(1) NOT NULL DEFAULT 0,
  diskon_treatment_persen DECIMAL(5,2) NOT NULL DEFAULT 0.00,
  diskon_produk_persen DECIMAL(5,2) NOT NULL DEFAULT 0.00 COMMENT 'berlaku untuk produk dengan eligible_member_discount=1',

  -- Metadata
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  catatan TEXT NULL,
  urutan_tampilan INT NOT NULL DEFAULT 0 COMMENT 'urutan di UI, makin kecil makin atas',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB CHARSET=utf8mb4;

-- ----------------------------------------------------------------------------
-- 3.2. master_membership_benefit_treatment — kuota treatment per tier
-- ----------------------------------------------------------------------------
-- Contoh isi untuk VIP:
--   (id_membership=1, id_treatment=Facial,  kuota=1, periode='BULANAN')
--   (id_membership=1, id_treatment=IPL,     kuota=2, periode='TOTAL_PAKET')

CREATE TABLE master_membership_benefit_treatment (
  id_benefit INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  id_membership INT NOT NULL,
  id_treatment INT NOT NULL,
  kuota_total INT NOT NULL COMMENT 'jumlah sesi yang dikasih',
  periode_kuota ENUM('BULANAN','TOTAL_PAKET') NOT NULL,
  catatan TEXT NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_mmbt_membership FOREIGN KEY (id_membership) REFERENCES master_membership(id_membership),
  CONSTRAINT fk_mmbt_treatment FOREIGN KEY (id_treatment) REFERENCES master_treatment(id_treatment),
  UNIQUE KEY uk_membership_treatment (id_membership, id_treatment)
) ENGINE=InnoDB CHARSET=utf8mb4;

-- ----------------------------------------------------------------------------
-- 3.3. pasien_membership_history — record aktivasi
-- ----------------------------------------------------------------------------

CREATE TABLE pasien_membership_history (
  id_history INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  id_pasien INT NOT NULL,
  id_membership INT NOT NULL,
  tgl_aktif DATE NOT NULL,
  tgl_expired DATE NOT NULL,
  harga_bayar DECIMAL(12,2) NOT NULL,
  id_transaksi_aktivasi INT NULL COMMENT 'link ke transaksi_kasir saat beli membership',
  is_active TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'auto-set ke 0 setelah expired (cron)',
  catatan TEXT NULL,
  id_staf_aktivasi INT NULL COMMENT 'kasir yang aktivasi',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_pmh_pasien FOREIGN KEY (id_pasien) REFERENCES pasien(id_pasien),
  CONSTRAINT fk_pmh_membership FOREIGN KEY (id_membership) REFERENCES master_membership(id_membership),
  CONSTRAINT fk_pmh_transaksi FOREIGN KEY (id_transaksi_aktivasi) REFERENCES transaksi_kasir(id_transaksi),
  CONSTRAINT fk_pmh_staf FOREIGN KEY (id_staf_aktivasi) REFERENCES master_staf(id_staf),

  KEY idx_pmh_pasien_aktif (id_pasien, is_active, tgl_expired)
) ENGINE=InnoDB CHARSET=utf8mb4;

-- ----------------------------------------------------------------------------
-- 3.4. pasien_membership_kuota — kuota tersedia per pasien
-- ----------------------------------------------------------------------------
-- Contoh isi setelah pasien VIP aktivasi:
--   12 row untuk facial bulanan: bulan_periode='2026-04','2026-05', dst (1 row per bulan)
--   1 row untuk IPL total: periode='TOTAL_PAKET', bulan_periode=NULL, kuota_total=2

CREATE TABLE pasien_membership_kuota (
  id_kuota INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  id_pasien INT NOT NULL,
  id_membership_history INT NOT NULL COMMENT 'aktivasi yang generate kuota ini',
  id_treatment INT NOT NULL,

  periode_kuota ENUM('BULANAN','TOTAL_PAKET') NOT NULL,
  bulan_periode VARCHAR(7) NULL COMMENT "format YYYY-MM, NULL kalau periode TOTAL_PAKET",

  kuota_total INT NOT NULL,
  kuota_terpakai INT NOT NULL DEFAULT 0,

  is_active TINYINT(1) NOT NULL DEFAULT 1,
  expired_at DATE NOT NULL COMMENT 'sama dengan history.tgl_expired untuk TOTAL_PAKET; akhir bulan untuk BULANAN',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_pmk_pasien FOREIGN KEY (id_pasien) REFERENCES pasien(id_pasien),
  CONSTRAINT fk_pmk_history FOREIGN KEY (id_membership_history) REFERENCES pasien_membership_history(id_history),
  CONSTRAINT fk_pmk_treatment FOREIGN KEY (id_treatment) REFERENCES master_treatment(id_treatment),

  KEY idx_pmk_pasien_treatment (id_pasien, id_treatment, is_active),
  KEY idx_pmk_bulan (id_pasien, bulan_periode)
) ENGINE=InnoDB CHARSET=utf8mb4;

-- ----------------------------------------------------------------------------
-- 3.5. FK kunjungan_tindakan.id_kuota_member → pasien_membership_kuota
-- ----------------------------------------------------------------------------
-- Sekarang baru bisa add karena tabel kuota sudah dibuat.

ALTER TABLE kunjungan_tindakan
  ADD CONSTRAINT fk_kt_kuota_member FOREIGN KEY (id_kuota_member) REFERENCES pasien_membership_kuota(id_kuota);

-- ----------------------------------------------------------------------------
-- Selesai
-- ----------------------------------------------------------------------------
SELECT '✅ Migrasi 003 selesai. 4 tabel membership dibuat.' AS status;
