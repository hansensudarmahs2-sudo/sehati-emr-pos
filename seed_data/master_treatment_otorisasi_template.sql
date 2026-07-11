-- =============================================================================
-- SEED — master_treatment.butuh_otorisasi (TEMPLATE untuk dokter isi)
-- =============================================================================
-- Sesuai dokumentasi alur dokter:
--   "UP SELLING : bisa oleh dokter bisa oleh perawat. ada up selling treatment
--    tanpa verifikasi dokter. ada yang perlu verifikasi"
--
-- Treatment yang butuh_otorisasi=1 = perawat tidak bisa langsung add ke keranjang
-- saat upsell di ruang tindakan, harus PIN dokter dulu.
--
-- ⚠️ DOKTER WAJIB EDIT FILE INI:
--    1. Lihat daftar treatment yang ada:
--         SELECT id_treatment, nama_treatment FROM master_treatment;
--    2. Tentukan mana yang butuh otorisasi (biasanya: invasif, mahal, risiko tinggi)
--    3. Update statement-nya berdasarkan ID
--
-- Contoh treatment yang BIASANYA butuh otorisasi (tergantung klinik dokter):
--   - Botox / Filler injection
--   - Thread lift
--   - PRP / Mesotherapy
--   - Laser CO2 / Laser ablative
--   - Chemical peeling medium-deep
--
-- Treatment yang BIASANYA tidak butuh otorisasi:
--   - Facial standar
--   - Microdermabrasi
--   - IPL (kalau klinik dokter izinkan perawat)
--   - HydraFacial
-- =============================================================================

USE db_sehati;

-- ----------------------------------------------------------------------------
-- TEMPLATE — uncomment dan isi sesuai daftar dokter
-- ----------------------------------------------------------------------------

-- Set semua jadi tidak butuh otorisasi dulu (default), lalu update yang ya:
-- UPDATE master_treatment SET butuh_otorisasi = 0;

-- UPDATE master_treatment SET butuh_otorisasi = 1
-- WHERE id_treatment IN (
--   <id_botox>,
--   <id_filler>,
--   <id_thread_lift>,
--   <id_prp>,
--   <id_laser_co2>,
--   <id_chemical_peel_dalam>
-- );

-- ----------------------------------------------------------------------------
-- TEMPLATE — default rentang sesi untuk series treatment
-- ----------------------------------------------------------------------------
-- Sesuai keputusan: per treatment punya default rentang minggu untuk series.
-- Misal Botox bisa diulang 3-4 bulan, IPL bisa diulang 4-8 minggu, dst.

-- Contoh:
-- UPDATE master_treatment SET
--   default_rentang_mulai_minggu = 12,  -- min 3 bulan
--   default_rentang_akhir_minggu = 24   -- max 6 bulan
-- WHERE nama_treatment LIKE '%Botox%';

-- UPDATE master_treatment SET
--   default_rentang_mulai_minggu = 4,
--   default_rentang_akhir_minggu = 8
-- WHERE nama_treatment LIKE '%IPL%';

-- UPDATE master_treatment SET
--   default_rentang_mulai_minggu = 2,
--   default_rentang_akhir_minggu = 4
-- WHERE nama_treatment LIKE '%Facial%';

-- ----------------------------------------------------------------------------
SELECT 'ℹ️  Template ini di-comment semua. Edit dulu lalu uncomment.' AS instruksi;
SELECT '   Cek daftar treatment: SELECT id_treatment, nama_treatment FROM master_treatment;' AS hint;
