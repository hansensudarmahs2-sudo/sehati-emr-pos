-- =============================================================================
-- MIGRASI 005 — HASH PASSWORDS & PIN (catatan/persiapan)
-- =============================================================================
-- File ini TIDAK menjalankan hashing — hashing dilakukan oleh Python script
-- karena bcrypt butuh library Python.
--
-- File ini hanya:
--   1. Memverifikasi struktur kolom siap (sudah VARCHAR(255), cukup untuk bcrypt 60 char)
--   2. Menampilkan command untuk dijalankan
-- =============================================================================

USE db_sehati;

-- Verifikasi kolom password_hash dan pin
SELECT
  COLUMN_NAME,
  DATA_TYPE,
  CHARACTER_MAXIMUM_LENGTH
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'db_sehati'
  AND TABLE_NAME = 'master_staf'
  AND COLUMN_NAME IN ('password_hash', 'pin');

-- Output yang diharapkan:
-- password_hash | varchar | 255  ✅ cukup untuk bcrypt
-- pin           | varchar | 255  ✅ cukup untuk bcrypt

-- ----------------------------------------------------------------------------
-- LANGKAH BERIKUTNYA: Jalankan Python script untuk hash actual
-- ----------------------------------------------------------------------------
--
-- Dari root project:
--   python tools/migrate_passwords.py
--
-- Script akan:
--   1. Connect ke db_sehati
--   2. Ambil semua row di master_staf
--   3. Untuk setiap row:
--      - Read password_hash existing (saat ini plaintext)
--      - Hash dengan bcrypt
--      - Update kolom password_hash
--      - Sama untuk pin
--   4. Verifikasi: count row yang sudah di-hash
--
-- Script SAFE:
--   - Pakai transaction (rollback otomatis kalau error di tengah)
--   - Skip row yang password_hash-nya sudah terlihat seperti bcrypt
--     (mulai dengan $2b$ atau $2a$)
--   - Print before/after untuk audit
-- ----------------------------------------------------------------------------

SELECT 'ℹ️  File ini hanya verifikasi. Jalankan tools/migrate_passwords.py untuk hashing actual.' AS instruksi;
