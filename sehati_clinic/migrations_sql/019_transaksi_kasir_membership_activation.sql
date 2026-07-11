-- =============================================================================
-- Migration 019: Membership Activation Financial Flow (#362D)
-- =============================================================================
-- Context: FO daftar pasien VIP/VVIP -> pasien_membership_history row PENDING
--          (is_active=False, id_transaksi_aktivasi NULL). Di kasir auto line item
--          "Aktivasi Membership VIP" Rp 5jt muncul. Bayar trigger atomic:
--          activate history + create pasien_membership_kuota.
--
-- Schema change: transaksi_kasir + 2 fields untuk track aktivasi.
--
-- Reference: 12 Juni 2026 (DEC-067 Opsi 4 Hybrid)
-- Safe? Yes - kolom nullable, tidak break existing transaksi.
-- =============================================================================

ALTER TABLE `transaksi_kasir`
    ADD COLUMN `id_membership_aktivasi` INT NULL
        COMMENT 'FK master_membership - kalau transaksi ini juga aktivasi membership',
    ADD COLUMN `nominal_aktivasi_membership` DECIMAL(12, 2) NULL DEFAULT 0.00
        COMMENT 'Nominal aktivasi membership (snapshot harga_aktivasi saat bayar)';

ALTER TABLE `transaksi_kasir`
    ADD CONSTRAINT `fk_trx_membership_aktivasi`
        FOREIGN KEY (`id_membership_aktivasi`)
        REFERENCES `master_membership`(`id_membership`)
        ON DELETE SET NULL;

-- Verify:
-- DESCRIBE transaksi_kasir;
-- SHOW INDEX FROM transaksi_kasir;
