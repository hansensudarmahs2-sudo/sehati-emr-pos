-- =============================================================================
-- Migration 016: Phase 2 authorization schema ready untuk kunjungan_resep
-- =============================================================================
-- Context: SYNC-V1 (10 Juni 2026) menyamakan void per item dengan filosofi
-- #364 Phase 1 (kasir self-acc). Untuk Phase 2 nanti (PIN/TOKEN/QUEUE),
-- struktur transaksi_kasir sudah siap (migration 013) — sekarang samakan
-- juga di kunjungan_resep agar saat aktivasi Phase 2 tinggal isi field.
--
-- Fields baru di kunjungan_resep:
--   void_approved_by_id_staf  → FK ke master_staf, nullable
--   void_approved_at          → DATETIME, nullable
--   void_approval_method      → VARCHAR(20), nullable (SELF/PIN/TOKEN/QUEUE)
--   void_reason_code          → VARCHAR(40), nullable (6 enum VoidReasonEnum)
--   void_reason_note          → TEXT, nullable
--
-- Idempotent? Tidak — SAFE_RUN_ONCE_ONLY.
-- =============================================================================

ALTER TABLE `kunjungan_resep`
    ADD COLUMN `void_reason_code` VARCHAR(40) NULL AFTER `id_staf_void`,
    ADD COLUMN `void_reason_note` TEXT NULL AFTER `void_reason_code`,
    ADD COLUMN `void_approved_by_id_staf` INT NULL AFTER `void_reason_note`,
    ADD COLUMN `void_approved_at` DATETIME NULL AFTER `void_approved_by_id_staf`,
    ADD COLUMN `void_approval_method` VARCHAR(20) NULL AFTER `void_approved_at`,
    ADD CONSTRAINT `fk_kunjungan_resep_void_approved_by`
        FOREIGN KEY (`void_approved_by_id_staf`)
        REFERENCES `master_staf` (`id_staf`);

-- Verify (manual):
-- DESCRIBE kunjungan_resep;
-- Expect: 5 kolom baru muncul, semua nullable.
