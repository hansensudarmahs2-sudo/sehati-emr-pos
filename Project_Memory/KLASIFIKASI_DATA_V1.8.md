# Klasifikasi Data — Sehati eMR-POS (ASVS V1.8)

**Dibuat:** 2026-07-07 · **Sifat:** fondasi keputusan enkripsi / masking / audit / tenant-boundary.
Companion: `AUDIT_ASVS_SEHATI_2026-07-03.md`, `AUDIT_ASVS_CATATAN_TINDAK_LANJUT_2026-07-03.md`.

Tujuan: mendaftar tiap jenis data + kelas sensitivitasnya, agar keputusan "apa yang di-enkripsi,
di-mask, di-audit, boleh lintas-klinik" punya dasar tunggal (bukan ad-hoc). Penting menjelang
arah **multi-klinik 1 server** (tenant isolation).

---

## Kelas sensitivitas

| Kelas | Nama | Arti | Aturan penanganan |
|---|---|---|---|
| **K1** | Kredensial / rahasia sistem | password hash, PIN, JWT secret, token API | **Tak pernah** diekspor/di-log/ditampilkan. Hash kuat. Rotasi secret. |
| **K2** | PII Medis | rekam medis/SOAP, diagnosis, penyakit kronis, resep, antropometri | Paling sensitif. Audit-baca WAJIB, tenant-scope WAJIB, enkripsi at-rest (post-deploy), mask saat ke pihak ke-3/AI. |
| **K3** | PII Identitas | nama, no_rm, tgl_lahir, alamat, no_hp, jenis_kelamin | Identifiable. Tenant-scope WAJIB. Mask/pseudonim saat ekspor eksternal. |
| **K4** | Finansial/operasional tertaut pasien | transaksi, pembayaran, komisi staf, membership/kuota | Sensitif bisnis + tertaut pasien. Tenant-scope. Akses per-role. |
| **K5** | Master / rahasia bisnis | produk, treatment, harga jual, **HPP**, distributor, faktur | Rahasia bisnis (bukan PII). Akses per-role (HPP/harga modal ketat). |
| **K6** | Operasional non-sensitif | inventory/lot/ED, antrian, jadwal, nama klinik | Perlindungan standar; sebagian publik. |

---

## Peta data → kelas

| Data / tabel (indikatif) | Kelas | Catatan penanganan |
|---|---|---|
| `master_staf.password_hash`, `.pin` | K1 | Hash; tak pernah keluar. Sudah: policy panjang (8/6 baru). |
| `.env` `JWT_SECRET_KEY`, token konektor | K1 | Startup-guard prod (A6) menolak boot bila default/<32. |
| SOAP/`pemeriksaan` (S/O/A/P, diagnosis) | K2 | Edit-lock (DEC-053) ada. **Audit-baca** kini di dokter/perawat/apotek/detail/riwayat. |
| `penyakit_kronis`, resep/`resep_obat` | K2 | Audit-baca apotek DONE. Nama obat TAK dikirim ke AI (hanya flag). |
| Antropometri / komposisi tubuh | K2 | Di modul terpisah; kontrak intake parsial. |
| `pasien` identitas (nama, no_rm, kontak, alamat) | K3 | Ekspor Owner punya opsi `mask_pii`. Tenant-scope jadi wajib multi-klinik. |
| `transaksi`, `pembayaran` | K4 | VOID dikecualikan agregasi. Ekspor Finance file-drop (DEC-066-R2). |
| `komisi_ledger` | K4 | Kepegawaian + finansial; akses owner/diri sendiri. |
| `membership`, kuota/benefit | K4 | Deferred-revenue di Finance. |
| Master produk/treatment, **harga/HPP** | K5 | HPP/harga modal = rahasia; batasi role. |
| `distributor`, PO, faktur | K5 | Rahasia mitra/harga beli. |
| Inventory/lot/ED, opname | K6 | Operasional. |
| `audit_log` | K6* | Berisi id_staf + id_target pasien. Immutable by design (V7.3.1: batasi GRANT app → INSERT/SELECT). |
| Antrian/booking/jadwal | K6 | Operasional. |

\* audit_log operasional tapi bernilai forensik → jangan bisa di-UPDATE/DELETE.

---

## Implikasi prioritas (menuju multi-klinik)

1. **Tenant-scope wajib untuk K2/K3/K4** — setiap query pasien/transaksi difilter `klinik_id`. (Naik prioritas di catatan ASVS.)
2. **Audit-baca (V7.2.1)** untuk semua titik baca K2 — sebagian besar sudah (detail/riwayat pasien, SOAP dokter, ruang tindakan, resep apotek).
3. **Enkripsi at-rest (K1/K2)** — setelah server ter-provisioning (BitLocker/LUKS).
4. **Masking (K3)** wajib pada ekspor ke AI/pihak ke-3 (opsi `mask_pii` sudah ada di Raw Data Export).
5. **GRANT least-privilege (K1 & audit_log)** di level DB produksi.

> Dokumen hidup — perbarui saat tabel/modul baru atau saat boundary multi-klinik difinalkan.
