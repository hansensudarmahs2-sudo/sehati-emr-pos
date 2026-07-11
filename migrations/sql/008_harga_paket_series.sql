-- =========================================================================
-- Migration 008 — Tambah harga_paket ke master_treatment untuk Series Pricing
-- =========================================================================
-- Konteks: Series treatment (e.g., 6x Ozone) butuh harga paket khusus yang
-- lebih rendah dari harga normal. Total tagihan di sesi 1 series =
-- jumlah_sesi × harga_paket. Sesi 2..N tidak ditagih (sudah paid di sesi 1).
--
-- DEC-049: Series treatment flow
--   - Sesi 1 dieksekusi hari ini + total dibayar saat itu
--   - Sesi 2..N dijadwalkan via FO booking saat pasien kembali
--   - Pricing: jumlah_sesi × harga_paket (fallback: harga normal kalau paket NULL)
--
-- Backward compatible: kolom NULL — treatment tanpa paket tetap pakai harga normal.
-- =========================================================================

ALTER TABLE master_treatment
ADD COLUMN harga_paket DECIMAL(15,2) NULL
COMMENT 'Harga per sesi pada paket series (lebih rendah dari harga normal). NULL = tidak ada paket khusus, fallback ke harga.'
AFTER harga;

-- Verify
SELECT
    id_treatment,
    nama_treatment,
    harga,
    harga_paket
FROM master_treatment
LIMIT 5;
