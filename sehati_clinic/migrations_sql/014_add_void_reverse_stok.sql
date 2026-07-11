-- =============================================================================
-- Migration 014 — Per-item Reverse Stok untuk Void (DEC-063)
-- Tanggal: 10 Juni 2026
-- Konteks: #364 — Saat void, kasir bisa pilih per produk:
--          "stok masih utuh, kembalikan ke stok master_produk?"
--          Kalau dichecklist: stok kembali + inventory_history entry.
--          Kalau tidak: stok tetap kurang (klinik tanggung loss).
--
-- Default: NULL (= "tidak diputuskan" untuk data lama, atau 0 untuk new).
-- Field cuma berlaku saat parent transaksi status = VOID.
--
-- Reverse stok HANYA untuk PRODUK (skincare, dll yang masih utuh).
-- TIDAK ada reverse untuk BHP/treatment (sudah consumed).
-- =============================================================================

ALTER TABLE transaksi_detail_produk
ADD COLUMN void_reverse_stok TINYINT(1) NULL DEFAULT 0
COMMENT 'TRUE kalau saat void parent transaksi, stok produk ini dikembalikan ke master_produk.stok_terkini';

-- ============================================================================
-- Apply instructions:
-- ============================================================================
-- sudo mysql db_sehati < migrations_sql/014_add_void_reverse_stok.sql
--
-- # Verify
-- sudo mysql db_sehati -e "DESCRIBE transaksi_detail_produk;" | grep void_reverse_stok
-- ============================================================================
