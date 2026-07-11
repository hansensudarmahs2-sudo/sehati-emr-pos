-- =============================================================================
-- MIGRASI 007 — MASTER KLINIK CONFIG (Print Module)
-- =============================================================================
-- Tanggal: 5 Juni 2026
-- Domain: Print Module / Klinik Info
-- Decisions reference: DEC-047 (Print Module Path A — Browser HTML Print)
--
-- Apa yang dilakukan migrasi ini:
--   1. CREATE TABLE master_klinik_config (singleton, id_config = 1)
--   2. INSERT default row dengan placeholder nama klinik
--
-- Singleton pattern:
--   - CHECK constraint id_config = 1 → enforce hanya 1 row di tabel
--   - PRIMARY KEY id_config tidak auto-increment
--   - INSERT IGNORE supaya idempotent (re-run aman)
--
-- ROLLBACK PLAN: ada di bagian bawah file (commented).
-- =============================================================================

START TRANSACTION;

-- =============================================================================
-- CREATE TABLE master_klinik_config
-- =============================================================================
CREATE TABLE IF NOT EXISTS master_klinik_config (
    id_config           INT NOT NULL PRIMARY KEY DEFAULT 1
                            COMMENT 'Singleton — selalu = 1',

    nama_klinik         VARCHAR(100) NOT NULL DEFAULT 'Sehati Clinic'
                            COMMENT 'Nama klinik untuk header dokumen cetak',

    alamat_baris1       VARCHAR(150) NULL
                            COMMENT 'Alamat line 1 (jalan + nomor)',
    alamat_baris2       VARCHAR(150) NULL
                            COMMENT 'Alamat line 2 (kelurahan/RT/RW)',
    alamat_baris3       VARCHAR(150) NULL
                            COMMENT 'Alamat line 3 (kecamatan/kota/kode pos)',

    no_telepon          VARCHAR(50) NULL COMMENT 'Nomor telepon klinik',
    no_whatsapp         VARCHAR(50) NULL COMMENT 'Nomor WhatsApp (opsional)',
    email               VARCHAR(100) NULL COMMENT 'Email klinik',
    website             VARCHAR(200) NULL COMMENT 'URL website (opsional)',

    logo_path           VARCHAR(200) NULL
                            COMMENT 'Path relatif ke logo file (e.g., uploads/logo.png)',

    footer_text         TEXT NULL
                            COMMENT 'Pesan footer di nota (e.g., Terima kasih...)',

    default_paper_nota  VARCHAR(20) NOT NULL DEFAULT 'a5'
                            COMMENT 'Default paper size untuk nota: a5 atau thermal',
    default_paper_soap  VARCHAR(20) NOT NULL DEFAULT 'a5'
                            COMMENT 'Default paper size untuk SOAP: a5 atau thermal',

    ttd_dokter_text     VARCHAR(100) NULL
                            COMMENT 'Optional sign-off untuk SOAP (e.g., Dokter Pemeriksa,)',

    created_at          TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP
                            ON UPDATE CURRENT_TIMESTAMP,

    id_staf_last_edit   INT NULL
                            COMMENT 'Audit — staff yang terakhir edit config',

    CONSTRAINT chk_klinik_config_singleton
        CHECK (id_config = 1),

    CONSTRAINT chk_klinik_config_paper_nota
        CHECK (default_paper_nota IN ('a5', 'thermal')),

    CONSTRAINT chk_klinik_config_paper_soap
        CHECK (default_paper_soap IN ('a5', 'thermal')),

    CONSTRAINT fk_klinik_config_staf
        FOREIGN KEY (id_staf_last_edit) REFERENCES master_staf(id_staf)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Singleton config klinik untuk Print Module (DEC-047)';


-- =============================================================================
-- INSERT default row (idempotent via INSERT IGNORE)
-- =============================================================================
INSERT IGNORE INTO master_klinik_config (
    id_config, nama_klinik, default_paper_nota, default_paper_soap, footer_text
) VALUES (
    1,
    'Sehati Clinic',
    'a5',
    'a5',
    'Terima kasih atas kunjungan Bapak/Ibu. Semoga lekas sembuh.'
);

COMMIT;


-- =============================================================================
-- ROLLBACK PLAN (jangan jalankan kecuali memang perlu rollback)
-- =============================================================================
-- START TRANSACTION;
-- DROP TABLE IF EXISTS master_klinik_config;
-- COMMIT;
