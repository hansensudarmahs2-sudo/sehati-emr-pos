-- =============================================================================
-- MIGRASI 002 — ALTER TABEL EXISTING
-- =============================================================================
-- Tujuan: Tambah kolom-kolom baru di tabel existing untuk dukung fitur baru.
--   - master_produk: id_bahan_sumber, qty_per_unit_produk, default_iterasi,
--                    eligible_member_discount
--   - master_treatment: default_rentang_mulai_minggu, default_rentang_akhir_minggu
--   - pasien_rencana_treatment: id_treatment, sumber_rencana, dll
--   - pasien_resep_iterasi: id_produk, id_staf_dokter, tgl_kadaluarsa, qty_per_iterasi
--   - kunjungan_tindakan: id_kuota_member
--   - master_staf: catatan untuk PIN hashing (di file 005)
-- =============================================================================

USE db_sehati;

-- ----------------------------------------------------------------------------
-- 2.1. master_produk — extend untuk repacking, iterasi, member discount
-- ----------------------------------------------------------------------------

ALTER TABLE master_produk
  -- mapping ke bahan source kalau produk hasil repack (NULL = produk jadi)
  ADD COLUMN id_bahan_sumber INT NULL AFTER tipe_produk,
  ADD COLUMN qty_per_unit_produk FLOAT NULL DEFAULT NULL AFTER id_bahan_sumber,
  -- default iterasi: 0 = tidak ada iterasi, > 0 = boleh diulang sebanyak ini
  ADD COLUMN default_iterasi INT NOT NULL DEFAULT 0 AFTER stok_minimal,
  -- flag: produk ini dapat diskon member?
  ADD COLUMN eligible_member_discount TINYINT(1) NOT NULL DEFAULT 0 AFTER default_iterasi;

ALTER TABLE master_produk
  ADD CONSTRAINT fk_mp_bahan_sumber FOREIGN KEY (id_bahan_sumber) REFERENCES inventory_stok(id_bahan);

-- ----------------------------------------------------------------------------
-- 2.2. master_treatment — extend untuk default rentang sesi
-- ----------------------------------------------------------------------------

ALTER TABLE master_treatment
  -- default rentang minggu untuk series planning
  -- mulai: minimal X minggu setelah sesi sebelumnya
  -- akhir: maksimal Y minggu setelah sesi sebelumnya (kalau lewat, dianggap expired)
  ADD COLUMN default_rentang_mulai_minggu INT NOT NULL DEFAULT 0 AFTER butuh_otorisasi,
  ADD COLUMN default_rentang_akhir_minggu INT NOT NULL DEFAULT 12 AFTER default_rentang_mulai_minggu;

-- ----------------------------------------------------------------------------
-- 2.3. pasien_rencana_treatment — refactor major
-- ----------------------------------------------------------------------------

ALTER TABLE pasien_rencana_treatment
  -- ganti dari nama_tindakan VARCHAR ke id_treatment FK
  -- nama_tindakan tetap dipertahankan sebagai snapshot historis
  ADD COLUMN id_treatment INT NULL AFTER id_pasien,
  ADD COLUMN sumber_rencana ENUM('DOKTER_PLAN','MEMBERSHIP','PROMO') NOT NULL DEFAULT 'DOKTER_PLAN' AFTER nama_tindakan,
  ADD COLUMN id_referensi_sumber INT NULL COMMENT 'kalau dari MEMBERSHIP/PROMO, link ke ID-nya' AFTER sumber_rencana,
  ADD COLUMN id_kunjungan_pembuat INT NULL COMMENT 'kunjungan saat plan dibuat' AFTER id_referensi_sumber,
  ADD COLUMN tgl_target_mulai DATE NULL AFTER status,
  ADD COLUMN tgl_target_akhir DATE NULL AFTER tgl_target_mulai,
  ADD COLUMN tgl_eksekusi DATETIME NULL AFTER id_kunjungan_eksekusi,
  ADD COLUMN catatan_dokter TEXT NULL AFTER tgl_eksekusi;

-- Normalize status existing dulu — kalau ada nilai non-standard,
-- ubah ke 'PENDING' supaya MODIFY COLUMN ENUM tidak fail dengan error 1265
UPDATE pasien_rencana_treatment
SET status = 'PENDING'
WHERE status IS NULL
   OR status NOT IN ('PENDING','SCHEDULED','DONE','CANCELLED','EXPIRED');

-- Ubah enum status agar lebih jelas
ALTER TABLE pasien_rencana_treatment
  MODIFY COLUMN status ENUM('PENDING','SCHEDULED','DONE','CANCELLED','EXPIRED') NOT NULL DEFAULT 'PENDING';

ALTER TABLE pasien_rencana_treatment
  ADD CONSTRAINT fk_prt_treatment FOREIGN KEY (id_treatment) REFERENCES master_treatment(id_treatment),
  ADD CONSTRAINT fk_prt_kunjungan_pembuat FOREIGN KEY (id_kunjungan_pembuat) REFERENCES kunjungan(id_kunjungan);

CREATE INDEX idx_prt_pasien_status ON pasien_rencana_treatment(id_pasien, status);
CREATE INDEX idx_prt_target ON pasien_rencana_treatment(tgl_target_akhir, status);

-- ----------------------------------------------------------------------------
-- 2.4. pasien_resep_iterasi — refactor
-- ----------------------------------------------------------------------------

ALTER TABLE pasien_resep_iterasi
  -- ganti dari nama_produk VARCHAR ke id_produk FK
  -- nama_produk dipertahankan sebagai snapshot historis
  ADD COLUMN id_produk INT NULL AFTER id_pasien,
  ADD COLUMN qty_per_iterasi FLOAT NOT NULL DEFAULT 1.0 AFTER kuota_maksimal,
  ADD COLUMN tgl_kadaluarsa DATE NULL COMMENT 'default: created_at + 6 bulan' AFTER qty_per_iterasi,
  ADD COLUMN id_kunjungan_pembuat INT NULL AFTER tgl_kadaluarsa,
  ADD COLUMN id_staf_dokter INT NULL AFTER id_kunjungan_pembuat;

ALTER TABLE pasien_resep_iterasi
  ADD CONSTRAINT fk_pri_produk FOREIGN KEY (id_produk) REFERENCES master_produk(id_produk),
  ADD CONSTRAINT fk_pri_kunjungan FOREIGN KEY (id_kunjungan_pembuat) REFERENCES kunjungan(id_kunjungan),
  ADD CONSTRAINT fk_pri_dokter FOREIGN KEY (id_staf_dokter) REFERENCES master_staf(id_staf);

CREATE INDEX idx_pri_pasien_active ON pasien_resep_iterasi(id_pasien, is_active);

-- ----------------------------------------------------------------------------
-- 2.5. kunjungan_tindakan — link ke kuota member
-- ----------------------------------------------------------------------------

ALTER TABLE kunjungan_tindakan
  -- nullable: kalau pasien pakai kuota member, link ke pasien_membership_kuota
  --           kalau bayar normal, NULL
  ADD COLUMN id_kuota_member INT NULL AFTER id_staf_pelaksana,
  -- link ke rencana series treatment kalau eksekusi dari series
  ADD COLUMN id_rencana INT NULL AFTER id_kuota_member;

ALTER TABLE kunjungan_tindakan
  ADD CONSTRAINT fk_kt_rencana FOREIGN KEY (id_rencana) REFERENCES pasien_rencana_treatment(id_rencana);
-- FK ke pasien_membership_kuota di-add di file 003 setelah tabel kuota dibuat

-- ----------------------------------------------------------------------------
-- 2.6. kunjungan — index tambahan
-- ----------------------------------------------------------------------------

CREATE INDEX idx_kunjungan_booking ON kunjungan(id_booking);

-- ----------------------------------------------------------------------------
-- 2.7. master_staf — placeholder untuk hash password/PIN nanti
-- ----------------------------------------------------------------------------

-- Kolom password_hash dan pin sudah ada VARCHAR(255).
-- bcrypt hash pas di 60 chars, jadi tidak perlu alter struktur.
-- Migrasi value dilakukan oleh tools/migrate_passwords.py

-- ----------------------------------------------------------------------------
-- Selesai
-- ----------------------------------------------------------------------------
SELECT '✅ Migrasi 002 selesai. Cek DESCRIBE master_produk; dll untuk verifikasi.' AS status;
