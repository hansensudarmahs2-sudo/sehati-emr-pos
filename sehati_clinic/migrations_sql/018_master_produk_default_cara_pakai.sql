-- =============================================================================
-- Migration 018: master_produk.default_cara_pakai untuk auto-fill resep SOAP
-- =============================================================================
-- Context: Bapak request TODO-NEW-3 (#31). Dokter sekarang harus ketik manual
--          aturan_pakai tiap kali tulis resep. Dengan field ini, default
--          ditampilkan langsung dan dokter tinggal edit kalau perlu beda.
--
-- Reference: 11 Juni 2026 Quality of Life dokter UX
--
-- Safe? Yes — kolom nullable, tidak break existing data.
-- =============================================================================

ALTER TABLE `master_produk`
    ADD COLUMN `default_cara_pakai` VARCHAR(200) NULL
        COMMENT 'Default aturan pakai auto-fill saat dokter pilih produk di resep SOAP'
        AFTER `harga_jual`;

-- Verify:
-- DESCRIBE master_produk;
-- Expect: default_cara_pakai column muncul setelah harga_jual.
