-- =============================================================================
-- SEED DATA — master_membership default (sesuai keputusan diskusi)
-- =============================================================================
-- Membership saat ini: VIP & VVIP (sesuai enum existing pasien.tipe_membership)
--
-- VIP:
--   - Harga aktivasi: 5.000.000 (placeholder, tolong dokter konfirmasi/edit)
--   - Durasi: 12 bulan
--   - Free konsultasi dokter: YA
--   - Diskon treatment: 10% (sesuai kode lama dokter)
--   - Diskon produk: 3% (untuk produk dengan eligible_member_discount=1)
--   - Benefit kuota:
--       * 1× facial / bulan
--       * 2× IPL / total paket
--
-- VVIP:
--   - Harga aktivasi: 10.000.000 (placeholder)
--   - Durasi: 12 bulan
--   - Free konsultasi dokter: YA
--   - Diskon treatment: 20% (sesuai kode lama)
--   - Diskon produk: 3%
--   - Benefit kuota: TBD (dokter tentukan)
-- =============================================================================
--
-- ⚠️ DOKTER WAJIB EDIT FILE INI sebelum run:
--    1. harga_aktivasi: angka real klinik
--    2. master_membership_benefit_treatment: id_treatment harus match dengan
--       data master_treatment di klinik dokter (cari ID via:
--          SELECT id_treatment, nama_treatment FROM master_treatment;)
-- =============================================================================

USE db_sehati;

-- ----------------------------------------------------------------------------
-- 1. Tier definition
-- ----------------------------------------------------------------------------

INSERT INTO master_membership (
  nama_tier, harga_aktivasi, durasi_bulan,
  free_konsultasi_dokter, diskon_treatment_persen, diskon_produk_persen,
  is_active, urutan_tampilan, catatan
) VALUES
  -- VIP
  ('VIP',  5000000.00, 12, 1, 10.00, 3.00, 1, 1,
   'Tier dasar member: free konsul, kuota facial bulanan, kuota IPL tahunan, diskon 3% produk eligible'),

  -- VVIP
  ('VVIP', 10000000.00, 12, 1, 20.00, 3.00, 1, 2,
   'Tier premium member: benefit VIP + diskon treatment lebih besar (kuota TBD)');

-- ----------------------------------------------------------------------------
-- 2. Benefit kuota treatment
-- ----------------------------------------------------------------------------
-- ⚠️ EDIT id_treatment sesuai master_treatment di klinik dokter.
-- Contoh berikut MENGASUMSIKAN id_treatment seperti ini:
--   1 = Konsultasi (free buat member)
--   2 = Facial Premium
--   3 = IPL
-- Cek ID real:
--   SELECT id_treatment, nama_treatment FROM master_treatment;

-- VIP: 1× facial per bulan + 2× IPL total paket
-- INSERT INTO master_membership_benefit_treatment
--   (id_membership, id_treatment, kuota_total, periode_kuota, catatan)
-- VALUES
--   (1, <id_facial>, 1, 'BULANAN',     '1× facial per bulan untuk VIP'),
--   (1, <id_ipl>,    2, 'TOTAL_PAKET', '2× IPL bebas tanggal selama 12 bulan untuk VIP');

-- VVIP: TBD (dokter tentukan)
-- INSERT INTO master_membership_benefit_treatment
--   (id_membership, id_treatment, kuota_total, periode_kuota, catatan)
-- VALUES
--   (2, <id_treatment_x>, <kuota>, '<BULANAN/TOTAL_PAKET>', '<keterangan>');

-- ----------------------------------------------------------------------------
SELECT '✅ Seed master_membership selesai. Cek SELECT * FROM master_membership;' AS status;
SELECT '⚠️  Insert master_membership_benefit_treatment di-comment, edit dulu id_treatment lalu uncomment.' AS warning;
