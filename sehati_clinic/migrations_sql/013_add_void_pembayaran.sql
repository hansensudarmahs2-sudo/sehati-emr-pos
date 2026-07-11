-- =============================================================================
-- Migration 013 — Void Pembayaran Phase 1 (DEC-063)
-- Tanggal: 10 Juni 2026
-- Konteks: #364 — Void transaksi kasir setelah pembayaran.
--          Phase 1: kasir self-acc dengan audit log + reason wajib.
--          Schema disiapkan untuk Phase 2 (authorization layer) di masa depan.
--
-- Yang berubah di table `transaksi_kasir`:
-- 1. ADD status_transaksi (BAYAR / VOID) — default BAYAR untuk data lama
-- 2. ADD 8 field void (semua NULL untuk data lama)
-- 3. ADD 2 FK constraints ke master_staf
-- 4. ADD 1 index untuk Dashboard Owner query "void hari ini"
--
-- Aman untuk apply ke production: TIDAK ada data yang berubah/hilang,
-- cuma penambahan kolom NULL/default.
-- =============================================================================

-- 1. Status transaksi — default BAYAR untuk data existing
ALTER TABLE transaksi_kasir
ADD COLUMN status_transaksi VARCHAR(20) NOT NULL DEFAULT 'BAYAR'
COMMENT 'Status transaksi: BAYAR (default) atau VOID';

-- 2. Field-field void
ALTER TABLE transaksi_kasir
ADD COLUMN void_at DATETIME NULL
COMMENT 'Kapan transaksi di-void (NOW saat void)',
ADD COLUMN void_by_id_staf INT NULL
COMMENT 'Siapa request void (= kasir di Phase 1)',
ADD COLUMN void_reason_code VARCHAR(40) NULL
COMMENT 'Enum: SALAH_INPUT / CUSTOMER_CANCEL / REFUND_PASCA_TINDAKAN / ITEM_RUSAK / DUPLICATE_TRANSAKSI / OTHER',
ADD COLUMN void_reason_note TEXT NULL
COMMENT 'Note bebas dari kasir (wajib min 5/10/20 char tergantung reason)',
ADD COLUMN void_approved_by_id_staf INT NULL
COMMENT 'Approver di Phase 2. Phase 1: same as void_by_id_staf (auto-approve)',
ADD COLUMN void_approved_at DATETIME NULL
COMMENT 'Phase 2 timestamp approval. Phase 1: same as void_at',
ADD COLUMN void_approval_method VARCHAR(20) NULL
COMMENT 'Enum: SELF (default Phase 1) / PIN / TOKEN / QUEUE (Phase 2)',
ADD COLUMN late_void TINYINT(1) NOT NULL DEFAULT 0
COMMENT 'TRUE kalau force past-day void (Admin max 3 hari, Superadmin/Owner max 7 hari)';

-- 3. FK constraints
ALTER TABLE transaksi_kasir
ADD CONSTRAINT fk_trans_kasir_void_by
  FOREIGN KEY (void_by_id_staf) REFERENCES master_staf(id_staf),
ADD CONSTRAINT fk_trans_kasir_void_approved_by
  FOREIGN KEY (void_approved_by_id_staf) REFERENCES master_staf(id_staf);

-- 4. Index untuk query Owner Dashboard "void today" + Reports filter
CREATE INDEX idx_transaksi_kasir_status_void
ON transaksi_kasir(status_transaksi, void_at);

-- ============================================================================
-- Apply instructions:
-- ============================================================================
-- # Backup dulu (kalau belum)
-- python scripts/backup.py
--
-- # Apply ke production
-- sudo mysql db_sehati < migrations_sql/013_add_void_pembayaran.sql
--
-- # Apply ke test DB (kalau ada)
-- sudo mysql db_sehati_test < migrations_sql/013_add_void_pembayaran.sql 2>/dev/null
--
-- # Verify (harus ada 9 kolom baru)
-- sudo mysql db_sehati -e "DESCRIBE transaksi_kasir;" | grep -E "status_transaksi|void_|late_void"
-- ============================================================================
