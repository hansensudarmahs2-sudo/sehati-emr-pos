-- =============================================================================
-- Migration 015: Add updated_at column ke pemeriksaan_klinis
-- =============================================================================
-- Context: Model PemeriksaanKlinis sudah punya field `updated_at` (server_default
-- CURRENT_TIMESTAMP + ON UPDATE CURRENT_TIMESTAMP) tapi DB belum.
-- Konsekuensi: setiap SELECT lewat ORM untuk SOAP gagal dengan
--   "Unknown column 'pemeriksaan_klinis.updated_at' in 'field list'"
-- Bug terdeteksi 10 Juni 2026 sesi bugfix-T1.
--
-- Aksi: ALTER TABLE tambah kolom dengan auto-bump.
--
-- Apakah idempotent? Tidak — SAFE_RUN_ONCE_ONLY.
-- Backup: backups/safepoint_pre_bugfix_20260610_032532.zip (source)
-- =============================================================================

ALTER TABLE `pemeriksaan_klinis`
    ADD COLUMN `updated_at` TIMESTAMP NULL
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
        AFTER `created_at`;

-- Verify (optional, dijalankan manual setelah ALTER):
-- DESCRIBE pemeriksaan_klinis;
-- Expect: kolom updated_at muncul dengan DEFAULT CURRENT_TIMESTAMP on update CURRENT_TIMESTAMP
