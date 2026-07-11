-- =============================================================================
-- Migration 009 — FO-ASSIGN-DOKTER (Task #329)
-- Tanggal: 8 Juni 2026
-- Konteks: dr. Hansen mau FO bisa assign dokter saat daftarkan pasien
--          konsultasi. Pasien hanya muncul di antrian dokter yang di-assign.
--          Kalau NULL = bebas claim oleh dokter manapun (back-compat).
-- Reference: DEC-053 + DEC-054 (SOAP-GUARD + TIER-SYS) + DEC-058 (akan dibuat)
-- =============================================================================

-- Tambah kolom id_staf_dokter_assigned (nullable, FK ke master_staf)
ALTER TABLE kunjungan
ADD COLUMN id_staf_dokter_assigned INT NULL
COMMENT 'Dokter yang di-assign FO saat daftarkan antrian konsultasi. NULL = bebas claim';

-- Foreign key constraint ke master_staf
ALTER TABLE kunjungan
ADD CONSTRAINT fk_kunjungan_dokter_assigned
FOREIGN KEY (id_staf_dokter_assigned) REFERENCES master_staf(id_staf)
ON DELETE SET NULL ON UPDATE CASCADE;

-- Index untuk performa filter antrian dokter
CREATE INDEX idx_kunjungan_dokter_assigned
ON kunjungan(id_staf_dokter_assigned);

-- Composite index untuk query antrian dokter "yang relevant ke saya hari ini"
CREATE INDEX idx_kunjungan_status_dokter_tgl
ON kunjungan(status_antrian, id_staf_dokter_assigned, tgl_kunjungan);

-- =============================================================================
-- Apply instruction (run setelah review):
--
-- # Backup dulu (selalu!)
-- sudo mysqldump db_sehati > backup_pre_009_$(date +%Y%m%d).sql
--
-- # Apply ke production
-- sudo mysql db_sehati < migrations_sql/009_add_id_staf_dokter_assigned.sql
--
-- # Apply ke test DB juga
-- sudo mysql db_sehati_test < migrations_sql/009_add_id_staf_dokter_assigned.sql
--
-- # Verify
-- sudo mysql db_sehati -e "DESCRIBE kunjungan;" | grep id_staf_dokter_assigned
-- sudo mysql db_sehati -e "SHOW INDEX FROM kunjungan;" | grep dokter
--
-- =============================================================================
