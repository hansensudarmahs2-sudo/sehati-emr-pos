-- =============================================================================
-- MIGRASI 006 — PENGADAAN & INVENTORY (Purchase Order + Stock Opname)
-- =============================================================================
-- Tanggal: 4 Juni 2026
-- Domain: Pengadaan / Inventory
-- Decisions reference: DEC-038 (Pemesanan workflow), DEC-039 (inventory_history
--                       generalize), DEC-040 (Restock direct removed)
--
-- Apa yang dilakukan migrasi ini:
--   1. Tambah role Purchasing ke ENUM master_staf.role
--   2. Generalize inventory_history → cover PRODUK + BAHAN (tambah tipe_item +
--      id_produk, id_bahan jadi nullable)
--   3. CREATE tabel pemesanan (header PO)
--   4. CREATE tabel pemesanan_item (detail row PO)
--   5. CREATE tabel pemesanan_receive (audit per receive event)
--   6. CREATE tabel stock_opname (header opname session)
--   7. CREATE tabel stock_opname_item (detail per item opname)
--
-- Backward compatibility:
--   - inventory_history data lama akan punya tipe_item='BAHAN' (default)
--     dan id_bahan tetap berisi. id_produk NULL. CHECK constraint pass.
--   - Tidak ada data drop / loss.
--
-- ROLLBACK PLAN: ada di bagian bawah file (commented). Jalankan kalau perlu undo.
-- =============================================================================

START TRANSACTION;

-- =============================================================================
-- 1. ALTER master_staf — tambah role Purchasing
-- =============================================================================
ALTER TABLE master_staf 
    MODIFY COLUMN role 
        ENUM('Owner','Dokter','Perawat','Apoteker','Kasir','FO','Admin','Superadmin','Purchasing')
        NOT NULL
        COMMENT 'Role staf — Purchasing ditambah di migrasi 006 untuk modul Pengadaan';


-- =============================================================================
-- 2. ALTER inventory_history — generalize untuk PRODUK + BAHAN
-- =============================================================================
-- Tambah kolom tipe_item dengan default BAHAN supaya data lama auto-fill
ALTER TABLE inventory_history
    ADD COLUMN tipe_item ENUM('PRODUK','BAHAN') NOT NULL DEFAULT 'BAHAN' 
        COMMENT 'Tipe item — PRODUK (master_produk) atau BAHAN (inventory_stok)'
        AFTER id_staf;

-- Tambah kolom id_produk nullable (FK)
ALTER TABLE inventory_history
    ADD COLUMN id_produk INT NULL 
        COMMENT 'FK ke master_produk kalau tipe_item=PRODUK'
        AFTER id_bahan;

-- Drop FK lama supaya bisa modify column id_bahan jadi nullable
-- Catatan: nama FK exact bisa berbeda — adjust kalau perlu
-- SET @fk_name = (SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE
--                 WHERE TABLE_NAME='inventory_history' AND COLUMN_NAME='id_bahan' 
--                 AND REFERENCED_TABLE_NAME='inventory_stok' LIMIT 1);
-- ALTER TABLE inventory_history DROP FOREIGN KEY @fk_name;

-- Modify id_bahan jadi nullable
ALTER TABLE inventory_history
    MODIFY COLUMN id_bahan INT NULL 
        COMMENT 'FK ke inventory_stok kalau tipe_item=BAHAN';

-- Add FK ke master_produk
ALTER TABLE inventory_history
    ADD CONSTRAINT fk_inv_hist_produk 
        FOREIGN KEY (id_produk) REFERENCES master_produk(id_produk);

-- Add check constraint XOR
ALTER TABLE inventory_history
    ADD CONSTRAINT chk_inv_hist_xor CHECK (
        (tipe_item='BAHAN' AND id_bahan IS NOT NULL AND id_produk IS NULL) OR
        (tipe_item='PRODUK' AND id_produk IS NOT NULL AND id_bahan IS NULL)
    );

-- Add composite index untuk query mutasi produk
ALTER TABLE inventory_history
    ADD INDEX idx_inv_hist_produk (id_produk, waktu_mutasi DESC);


-- =============================================================================
-- 3. CREATE pemesanan (header PO)
-- =============================================================================
CREATE TABLE pemesanan (
    id_pemesanan         INT AUTO_INCREMENT PRIMARY KEY,
    nomor_po             VARCHAR(50) NOT NULL UNIQUE 
                         COMMENT 'Format: PO-YYMMDD-NNN, auto-generate dengan FOR UPDATE counter',
    tgl_pemesanan        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tgl_perkiraan_datang DATE NULL 
                         COMMENT 'Estimasi delivery dari supplier',
    supplier_nama        VARCHAR(100) NULL 
                         COMMENT 'String bebas Phase 1, tabel master_supplier nanti',
    
    status               ENUM('SUBMITTED','ORDERED','PARTIAL_RECEIVED','RECEIVED','CANCELLED')
                         NOT NULL DEFAULT 'SUBMITTED'
                         COMMENT 'State machine: SUBMITTED→ORDERED→PARTIAL→RECEIVED, atau →CANCELLED',
    
    id_staf_pemesan      INT NOT NULL 
                         COMMENT 'Yang submit PO (PURCHASING/OWNER/SUPERADMIN/APOTEKER for retail)',
    id_staf_approver     INT NULL 
                         COMMENT 'Yang approve SUBMITTED→ORDERED',
    tgl_approve          DATETIME NULL,
    
    catatan              TEXT NULL,
    total_estimasi_biaya DECIMAL(14,2) NULL 
                         COMMENT 'Snapshot total saat ORDERED',
    
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (id_staf_pemesan) REFERENCES master_staf(id_staf),
    FOREIGN KEY (id_staf_approver) REFERENCES master_staf(id_staf),
    INDEX idx_pemesanan_status (status),
    INDEX idx_pemesanan_tgl (tgl_pemesanan DESC),
    INDEX idx_pemesanan_pemesan (id_staf_pemesan, status)
) COMMENT='Header Purchase Order — modul Pengadaan';


-- =============================================================================
-- 4. CREATE pemesanan_item (detail row PO)
-- =============================================================================
CREATE TABLE pemesanan_item (
    id_item            INT AUTO_INCREMENT PRIMARY KEY,
    id_pemesanan       INT NOT NULL,
    
    tipe_item          ENUM('PRODUK','BAHAN') NOT NULL,
    id_produk          INT NULL 
                       COMMENT 'FK master_produk kalau tipe_item=PRODUK',
    id_bahan           INT NULL 
                       COMMENT 'FK inventory_stok kalau tipe_item=BAHAN',
    
    nama_snapshot      VARCHAR(100) NOT NULL 
                       COMMENT 'Snapshot nama saat PO dibuat — anti-perubahan master',
    satuan_snapshot    VARCHAR(20) NULL,
    
    qty_dipesan        FLOAT NOT NULL,
    qty_diterima       FLOAT NOT NULL DEFAULT 0 
                       COMMENT 'Akumulasi dari semua pemesanan_receive untuk item ini',
    harga_satuan       DECIMAL(12,2) NULL 
                       COMMENT 'Opsional — pakai untuk total estimasi',
    subtotal           DECIMAL(14,2) NULL,
    catatan_item       VARCHAR(200) NULL,
    
    FOREIGN KEY (id_pemesanan) REFERENCES pemesanan(id_pemesanan) ON DELETE CASCADE,
    FOREIGN KEY (id_produk) REFERENCES master_produk(id_produk),
    FOREIGN KEY (id_bahan) REFERENCES inventory_stok(id_bahan),
    
    CONSTRAINT chk_pemesanan_item_xor CHECK (
        (tipe_item='PRODUK' AND id_produk IS NOT NULL AND id_bahan IS NULL) OR
        (tipe_item='BAHAN' AND id_bahan IS NOT NULL AND id_produk IS NULL)
    ),
    CONSTRAINT chk_pemesanan_item_qty CHECK (qty_dipesan > 0 AND qty_diterima >= 0),
    CONSTRAINT chk_pemesanan_item_diterima CHECK (qty_diterima <= qty_dipesan),
    
    INDEX idx_po_item (id_pemesanan),
    INDEX idx_po_item_produk (id_produk),
    INDEX idx_po_item_bahan (id_bahan)
) COMMENT='Detail item PO — polymorphic PRODUK/BAHAN';


-- =============================================================================
-- 5. CREATE pemesanan_receive (per receive event, append-only)
-- =============================================================================
CREATE TABLE pemesanan_receive (
    id_receive           INT AUTO_INCREMENT PRIMARY KEY,
    id_pemesanan         INT NOT NULL,
    id_pemesanan_item    INT NOT NULL,
    
    qty_diterima         FLOAT NOT NULL 
                         COMMENT 'Qty yang diterima di event ini, akan terakumulasi ke pemesanan_item.qty_diterima',
    tgl_terima           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id_staf_penerima     INT NOT NULL,
    nomor_faktur         VARCHAR(100) NULL 
                         COMMENT 'Delivery note / faktur supplier',
    catatan              TEXT NULL,
    
    FOREIGN KEY (id_pemesanan) REFERENCES pemesanan(id_pemesanan),
    FOREIGN KEY (id_pemesanan_item) REFERENCES pemesanan_item(id_item),
    FOREIGN KEY (id_staf_penerima) REFERENCES master_staf(id_staf),
    
    CONSTRAINT chk_receive_qty CHECK (qty_diterima > 0),
    
    INDEX idx_receive_po (id_pemesanan),
    INDEX idx_receive_item (id_pemesanan_item),
    INDEX idx_receive_tgl (tgl_terima DESC)
) COMMENT='Buku audit penerimaan per item, append-only';


-- =============================================================================
-- 6. CREATE stock_opname (header session)
-- =============================================================================
CREATE TABLE stock_opname (
    id_opname            INT AUTO_INCREMENT PRIMARY KEY,
    nomor_opname         VARCHAR(50) NOT NULL UNIQUE 
                         COMMENT 'Format: OPN-YYMMDD-NNN',
    tgl_opname           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    lokasi               ENUM('KABIN','GUDANG_UTAMA','RETAIL') NOT NULL 
                         COMMENT 'KABIN=inventory_stok.stok_kabin, GUDANG_UTAMA=inventory_stok.stok_gudang_utama, RETAIL=master_produk.stok_terkini',
    
    status               ENUM('DRAFT','APPROVED','REJECTED') NOT NULL DEFAULT 'DRAFT'
                         COMMENT 'DRAFT=belum apply, APPROVED=selisih terapan ke stok, REJECTED=ditolak',
    
    id_staf_pelaksana    INT NOT NULL,
    id_staf_approver     INT NULL,
    tgl_approve          DATETIME NULL,
    
    total_selisih_value  DECIMAL(14,2) NULL 
                         COMMENT 'Snapshot total selisih × harga saat approve',
    catatan              TEXT NULL,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (id_staf_pelaksana) REFERENCES master_staf(id_staf),
    FOREIGN KEY (id_staf_approver) REFERENCES master_staf(id_staf),
    INDEX idx_opname_status (status),
    INDEX idx_opname_tgl (tgl_opname DESC),
    INDEX idx_opname_lokasi (lokasi, status)
) COMMENT='Header stock opname session';


-- =============================================================================
-- 7. CREATE stock_opname_item (detail per item)
-- =============================================================================
CREATE TABLE stock_opname_item (
    id_opname_item    INT AUTO_INCREMENT PRIMARY KEY,
    id_opname         INT NOT NULL,
    
    tipe_item         ENUM('PRODUK','BAHAN') NOT NULL,
    id_produk         INT NULL,
    id_bahan          INT NULL,
    
    nama_snapshot     VARCHAR(100) NOT NULL,
    qty_sistem        FLOAT NOT NULL 
                      COMMENT 'Stok di sistem saat opname dibuat (snapshot)',
    qty_fisik         FLOAT NOT NULL 
                      COMMENT 'Hasil cek fisik gudang',
    selisih           FLOAT GENERATED ALWAYS AS (qty_fisik - qty_sistem) STORED 
                      COMMENT 'Auto: positive = stok lebih, negative = stok kurang',
    
    catatan_item      VARCHAR(200) NULL,
    
    FOREIGN KEY (id_opname) REFERENCES stock_opname(id_opname) ON DELETE CASCADE,
    FOREIGN KEY (id_produk) REFERENCES master_produk(id_produk),
    FOREIGN KEY (id_bahan) REFERENCES inventory_stok(id_bahan),
    
    CONSTRAINT chk_opname_item_xor CHECK (
        (tipe_item='PRODUK' AND id_produk IS NOT NULL AND id_bahan IS NULL) OR
        (tipe_item='BAHAN' AND id_bahan IS NOT NULL AND id_produk IS NULL)
    ),
    CONSTRAINT chk_opname_item_qty CHECK (qty_sistem >= 0 AND qty_fisik >= 0),
    
    INDEX idx_opname_item (id_opname),
    INDEX idx_opname_item_produk (id_produk),
    INDEX idx_opname_item_bahan (id_bahan)
) COMMENT='Detail item opname dengan selisih auto-computed';


COMMIT;


-- =============================================================================
-- VERIFY — jalankan setelah COMMIT untuk konfirmasi
-- =============================================================================
-- SELECT 'master_staf role enum' AS check_item, 
--        COLUMN_TYPE FROM information_schema.COLUMNS 
--        WHERE TABLE_NAME='master_staf' AND COLUMN_NAME='role';
-- 
-- SELECT 'inventory_history columns' AS check_item, COLUMN_NAME, DATA_TYPE, IS_NULLABLE
--        FROM information_schema.COLUMNS 
--        WHERE TABLE_NAME='inventory_history';
-- 
-- SHOW TABLES LIKE 'pemesanan%';
-- SHOW TABLES LIKE 'stock_opname%';


-- =============================================================================
-- ROLLBACK PLAN (jangan jalankan kecuali memang perlu rollback migrasi)
-- =============================================================================
-- START TRANSACTION;
-- DROP TABLE IF EXISTS stock_opname_item;
-- DROP TABLE IF EXISTS stock_opname;
-- DROP TABLE IF EXISTS pemesanan_receive;
-- DROP TABLE IF EXISTS pemesanan_item;
-- DROP TABLE IF EXISTS pemesanan;
-- 
-- -- Rollback inventory_history changes
-- ALTER TABLE inventory_history 
--     DROP CONSTRAINT chk_inv_hist_xor,
--     DROP FOREIGN KEY fk_inv_hist_produk,
--     DROP INDEX idx_inv_hist_produk,
--     DROP COLUMN id_produk,
--     DROP COLUMN tipe_item,
--     MODIFY COLUMN id_bahan INT NOT NULL;
-- 
-- -- Rollback master_staf role enum
-- ALTER TABLE master_staf 
--     MODIFY COLUMN role 
--         ENUM('Owner','Dokter','Perawat','Apoteker','Kasir','FO','Admin','Superadmin') 
--         NOT NULL;
-- COMMIT;
