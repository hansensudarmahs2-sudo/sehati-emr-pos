-- =============================================================================
-- MIGRASI 004 — AUDIT LOG
-- =============================================================================
-- Tabel untuk catat semua aksi mutating yang sensitif:
--   - Login/logout
--   - Create/Update/Delete pada: pasien, kunjungan, transaksi, resep,
--     inventory_history (write-off), membership_history
--   - Otorisasi sensitif: void item, transfer paket, penyesuaian stok
-- =============================================================================

USE db_sehati;

CREATE TABLE audit_log (
  id_log BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  id_staf INT NULL COMMENT 'NULL untuk anonymous events (login attempt gagal sebelum auth)',

  -- Apa yang terjadi
  aksi VARCHAR(50) NOT NULL COMMENT 'CREATE, UPDATE, DELETE, LOGIN, LOGOUT, VOID, AUTH_FAIL, dll',
  tabel_target VARCHAR(50) NULL COMMENT 'tabel yang dimodifikasi',
  id_target INT NULL COMMENT 'PK row yang dimodifikasi',

  -- Snapshot data
  data_lama JSON NULL COMMENT 'snapshot before update/delete',
  data_baru JSON NULL COMMENT 'snapshot after create/update',

  -- Konteks
  ip_address VARCHAR(45) NULL COMMENT 'IPv4 max 15 char, IPv6 max 45 char',
  user_agent VARCHAR(255) NULL,
  endpoint VARCHAR(255) NULL COMMENT 'URL yang dipanggil',
  http_method VARCHAR(10) NULL,

  -- Catatan tambahan
  keterangan TEXT NULL COMMENT 'free text untuk konteks (alasan void, dll)',
  status_aksi ENUM('SUCCESS','FAILED') NOT NULL DEFAULT 'SUCCESS',

  waktu DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_al_staf FOREIGN KEY (id_staf) REFERENCES master_staf(id_staf),

  KEY idx_al_staf_waktu (id_staf, waktu),
  KEY idx_al_aksi_waktu (aksi, waktu),
  KEY idx_al_tabel_target (tabel_target, id_target)
) ENGINE=InnoDB CHARSET=utf8mb4
COMMENT='Audit log untuk semua aksi mutating. Append-only, jangan UPDATE/DELETE row di sini.';

-- ----------------------------------------------------------------------------
-- Selesai
-- ----------------------------------------------------------------------------
SELECT '✅ Migrasi 004 selesai. Tabel audit_log siap dipakai.' AS status;
