-- =============================================================================
-- Migration 017: Finance Module Decoupling Skeleton (DEC-064)
-- =============================================================================
-- Status: 🟡 SKELETON — JANGAN dijalankan dulu. Tunggu Phase 1 Finance Module mulai.
--
-- Tujuan: Struktur penyambung di Sehati eRM-POS side untuk integrasi dengan
--         Finance Module yang akan dibuat terpisah (LAN deployment).
--
-- Reference: Project_Memory/FinanceModule/00_DESIGN.md
-- Discussion: DEC-064 (11_decisions_log.md), 11 Juni 2026
--
-- Decision Date: 11 Juni 2026
-- Apply When: Saat Bapak siap mulai Phase 1 implementasi Finance Module
--
-- Backup BEFORE: Wajib mysqldump full DB sebelum apply (4 schema change + 1 alter).
-- =============================================================================


-- =============================================================================
-- 1. finance_sync_cursor — Track last sync timestamp per Finance module
-- =============================================================================
-- Purpose: Finance lapor balik "saya sudah sync sampai timestamp X" via
--          POST /api/v1/finance/sync-cursor. Sehati simpan untuk audit +
--          query optimization (incremental pull).
CREATE TABLE IF NOT EXISTS `finance_sync_cursor` (
    `id_cursor`         INT PRIMARY KEY AUTO_INCREMENT,
    `module`            VARCHAR(50) NOT NULL
                        COMMENT 'journal_entry | payroll | inventory_valuation | etc.',
    `last_synced_at`    DATETIME NOT NULL,
    `last_processed_id` INT NULL
                        COMMENT 'Optional: ID transaksi/PO terakhir yang diproses',
    `notes`             TEXT NULL,
    `created_at`        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY `uk_module` (`module`)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COMMENT='Phase 0 skeleton — DEC-064 Finance Module integration cursor';


-- =============================================================================
-- 2. external_api_keys — Authentication keys untuk external modules
-- =============================================================================
-- Purpose: Validate Bearer token dari Finance Module (atau BI tool / mobile)
--          saat request /api/v1/finance/*. Bcrypt-hashed key.
CREATE TABLE IF NOT EXISTS `external_api_keys` (
    `id_key`        INT PRIMARY KEY AUTO_INCREMENT,
    `name`          VARCHAR(100) NOT NULL
                    COMMENT 'finance_module | bi_dashboard | mobile_app | etc.',
    `key_hash`      VARCHAR(255) NOT NULL
                    COMMENT 'Bcrypt hash of plain API key (raw key tidak disimpan)',
    `scopes`        TEXT NOT NULL
                    COMMENT 'Comma-separated: finance:read,finance:write,reports:read',
    `is_active`     BOOLEAN DEFAULT TRUE,
    `last_used_at`  DATETIME NULL,
    `expires_at`    DATETIME NULL
                    COMMENT 'Optional expiry. NULL = never expire',
    `created_at`    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `created_by`    INT NULL
                    COMMENT 'FK ke master_staf — siapa generate key ini',
    INDEX `idx_active` (`is_active`),
    UNIQUE KEY `uk_name` (`name`),
    CONSTRAINT `fk_eak_created_by`
        FOREIGN KEY (`created_by`) REFERENCES `master_staf`(`id_staf`)
        ON DELETE SET NULL
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COMMENT='Phase 0 skeleton — DEC-064 external module authentication';


-- =============================================================================
-- 3. external_webhook_configs — Future Phase 2 push events
-- =============================================================================
-- Purpose: Sehati push event ke Finance saat transaksi besar void / PO closed /
--          payroll period end / etc. Webhook URL + HMAC secret untuk verify.
CREATE TABLE IF NOT EXISTS `external_webhook_configs` (
    `id_webhook`        INT PRIMARY KEY AUTO_INCREMENT,
    `name`              VARCHAR(100) NOT NULL,
    `url`               VARCHAR(500) NOT NULL
                        COMMENT 'Target URL Finance Module untuk receive webhook',
    `event_types`       TEXT NOT NULL
                        COMMENT 'Comma: transaksi.created,transaksi.voided,po.received,payroll.period_end',
    `secret`            VARCHAR(255) NOT NULL
                        COMMENT 'HMAC secret untuk verify payload signature',
    `is_active`         BOOLEAN DEFAULT TRUE,
    `last_triggered_at` DATETIME NULL,
    `last_success_at`   DATETIME NULL,
    `failure_count`     INT DEFAULT 0
                        COMMENT 'Consecutive failure count. Auto-disable kalau > threshold',
    `created_at`        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_active` (`is_active`)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COMMENT='Phase 2 reserved — DEC-064 webhook config untuk event push';


-- =============================================================================
-- 4. external_request_log — Audit trail external API calls
-- =============================================================================
-- Purpose: Track siapa pull data kapan dari endpoint mana, untuk monitoring
--          + debug + security audit.
CREATE TABLE IF NOT EXISTS `external_request_log` (
    `id_log`            BIGINT PRIMARY KEY AUTO_INCREMENT,
    `id_key`            INT NULL
                        COMMENT 'FK ke external_api_keys — siapa request',
    `endpoint`          VARCHAR(255) NOT NULL
                        COMMENT 'Full path: /api/v1/finance/transaksi',
    `http_method`       VARCHAR(10) NOT NULL,
    `query_params`      TEXT NULL
                        COMMENT 'JSON snapshot params untuk debug',
    `ip_address`        VARCHAR(45) NULL
                        COMMENT 'Supports IPv6',
    `user_agent`        VARCHAR(255) NULL,
    `status_code`       INT NOT NULL,
    `response_time_ms`  INT NULL,
    `response_size_bytes` INT NULL,
    `error_message`     TEXT NULL,
    `request_at`        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_request_at` (`request_at`),
    INDEX `idx_key_at` (`id_key`, `request_at`),
    INDEX `idx_endpoint_at` (`endpoint`, `request_at`),
    CONSTRAINT `fk_erl_key`
        FOREIGN KEY (`id_key`) REFERENCES `external_api_keys`(`id_key`)
        ON DELETE SET NULL
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COMMENT='Phase 0 skeleton — DEC-064 audit log external API requests';


-- =============================================================================
-- 5. ALTER transaksi_detail_produk — Add hpp_at_sale snapshot
-- =============================================================================
-- Purpose: Saat transaksi bayar, snapshot master_produk.hpp_per_unit ke
--          transaksi_detail_produk. Crucial untuk Cost of Goods Sold (COGS) di
--          Finance — kalau HPP master_produk berubah ke depan, historical COGS
--          tetap akurat (immutable accounting record).
--
-- Backfill: Existing rows hpp_at_sale = NULL. Finance Module harus handle
--           NULL case dengan fallback ke master_produk.hpp_per_unit CURRENT
--           (atau skip dari laporan, tergantung policy).
ALTER TABLE `transaksi_detail_produk`
    ADD COLUMN `hpp_at_sale` DECIMAL(12, 2) NULL
        COMMENT 'Phase 0 (DEC-064): snapshot HPP per unit saat transaksi bayar'
        AFTER `subtotal`;


-- =============================================================================
-- VERIFY (optional, run manual after ALTER)
-- =============================================================================
-- DESCRIBE finance_sync_cursor;
-- DESCRIBE external_api_keys;
-- DESCRIBE external_webhook_configs;
-- DESCRIBE external_request_log;
-- DESCRIBE transaksi_detail_produk;     -- expect hpp_at_sale column muncul

-- Sample insert (optional, untuk testing nanti):
-- INSERT INTO external_api_keys (name, key_hash, scopes, created_by)
-- VALUES ('finance_module', '$2b$12$xxxxxx', 'finance:read', 1);
