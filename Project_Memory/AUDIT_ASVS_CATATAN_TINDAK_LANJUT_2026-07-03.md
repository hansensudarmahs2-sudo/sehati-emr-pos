# Catatan Tindak Lanjut Audit ASVS — 3 Juli 2026

Companion untuk `AUDIT_ASVS_SEHATI_2026-07-03.md`. Merekam keputusan & klarifikasi dari diskusi dr. Hansen setelah audit. **Bukan perubahan kode** — hanya catatan arah.

---

## Klarifikasi (temuan yang direvisi setelah verifikasi ulang kode)

- **SOAP edit-lock BENAR & solid** (`pemeriksaan_service.py`, DEC-053): rekam hari sebelumnya terkunci permanen untuk semua; same-day hanya dokter pemeriksa asli (`id_staf_dokter`) yang boleh edit/append (dokter lain → 403 WIB); read terbuka untuk semua role klinis. **Ini authorization tulis, BUKAN audit-baca.** Gap V7.2.1 tetap terpisah: tidak ada log saat rekam medis DIBUKA/dibaca.
- **Immutability audit_log:** dikonfirmasi — aplikasi TIDAK PERNAH delete/update row `audit_log` (tidak ada code path). dr. Hansen benar. Rekomendasi V7.3.1 murni defense-in-depth di level DB (batasi GRANT user app jadi INSERT/SELECT saja), bukan perbaikan bug.
- **Finance guard (V13.2.1):** ditunda — modul/role belum ada, endpoint `501`, guard sekarang tak melindungi apa pun. **Aturan:** pasang `Depends(role_required(...))` di PR yang sama saat modul finance diimplementasi. Jangan pernah go-live endpoint finance tanpa guard.

---

## Ditunda / dijadwalkan (dengan alasan)

| Item | ASVS | Keputusan | Kapan |
|------|------|-----------|-------|
| Kebijakan password 12 karakter | V2.1.1 | **Adopsi bertahap.** Kombinasi huruf + angka + tanda khusus (`@#!$` dsb). Catatan: panjang ≥12 adalah bagian terkuat; complexity rule opsional (NIST 800-63B lebih utamakan panjang drpd complexity paksa). | Bertahap |
| Scan dependensi `pip-audit` | V14.5.2 | Jadwalkan (mis. mingguan) via scheduled task / CI | TBD |
| Enkripsi at-rest (BitLocker/LUKS) | V8.1.6 [L3] | Dikerjakan **setelah** fase deployment (server ter-provisioning). Framing dr. Hansen benar. | Post-deployment |
| TLS | V9 | Deployment-layer. Untuk LAN dev belum perlu. **WAJIB** untuk jalur ke cloud (non-negotiable). | Saat deployment/cloud |
| Security headers | V14.4.1 | `nosniff` + `X-Frame-Options` murah (boleh kapan saja). CSP/HSTS baru berarti dengan HTTPS. | Sebelum cloud |
| Idle-timeout sesi | V3.3.2 | Tidak wajib. Alternatif: OS screen-lock. Bisa set 60 mnt idle nanti. | Opsional |
| 2FA | V2.7 | **Owner/Superadmin: dipertimbangkan** (privilege tinggi, login jarang). **Dokter: TIDAK diwajibkan** (login sering → friction tinggi, benefit rendah). Kalau perlu, pakai trusted-device / step-up untuk aksi sensitif saja. | TBD |

---

## Naik prioritas karena arah arsitektur baru (self-host multi-klinik)

> Konteks: ke depan **1 server, 1 jalur ke cloud, melayani beberapa klinik** = sistem jadi **multi-tenant**.

1. **Tenant isolation (was: "IDOR aman by design").** Rating hijau lama berdasar asumsi 1 klinik = 1 pool pasien. Multi-klinik di 1 server berarti **setiap query wajib di-scope per klinik** (kolom `klinik_id` + filter) supaya Klinik A tak bisa baca pasien Klinik B (termasuk via tebak ID). **Jadi requirement desain**, sebaiknya disiapkan sebelum data membesar.
2. **TLS jadi wajib** untuk jalur server→cloud.
3. **Audit akses-baca (V7.2.1)** makin penting untuk akuntabilitas lintas-klinik.
4. **Klasifikasi data (V1.8)** jadi fondasi untuk tenant boundary + keputusan enkripsi/mask.

---

## Penjelasan istilah (untuk referensi)

- **Hardening konfigurasi (V14.1/14.3.2):** pastikan produksi TIDAK jalan mode debug (`APP_DEBUG=false`) supaya error tidak bocorkan stack trace/versi/path ke user; hapus file dev nyasar (`1`, `exit`, `debug_kunjungan.py`); halaman error generik.
- **Klasifikasi data (V1.8):** tabel 1 halaman yang mendaftar tiap jenis data + kelas sensitivitasnya (PII penuh / PII medis / pseudonim / operasional) → fondasi untuk memutuskan apa yang di-enkripsi, di-mask, di-audit, boleh lintas-boundary.
- **Audit akses-baca vs edit-lock:** edit-lock = mencegah perubahan tak sah (sudah ada). Audit-baca = mencatat siapa MEMBUKA rekam medis (belum ada).

---

## Update 2026-07-07 — Quick-wins keamanan (dikerjakan)

- **Header keamanan:** `Permissions-Policy: geolocation=(), microphone=(), camera=()` ditambahkan di `SecurityHeadersMiddleware` (`app/main.py`), melengkapi `nosniff` + `X-Frame-Options: DENY` + `Referrer-Policy` yang sudah ada. (CSP/HSTS tetap menunggu HTTPS.)
- **Audit akses-baca (V7.2.1) dilengkapi:** `AuditService.log_view` kini juga dipanggil saat **perawat** membuka `/ruang-tindakan/kunjungan/{id}` dan **apoteker** membuka `/apotek/kunjungan/{id}`. Sebelumnya audit-baca hanya di detail/riwayat pasien + SOAP dokter. Cetak SOAP sudah teraudit via `PrintService` (PRINT_SOAP). Gagal-audit tak memblokir tampilan (try/except).
- **Klasifikasi data (V1.8):** dibuat `Project_Memory/KLASIFIKASI_DATA_V1.8.md` (kelas K1–K6 + peta data→kelas + implikasi tenant-scope/enkripsi/mask/audit).
- **pip-audit (V14.5.2):** dibuat `Project_Memory/RUNBOOK_PIP_AUDIT.md` + skrip `sehati_clinic/scripts/security_pip_audit.sh` (scan + JSON bertanggal + saran jadwal mingguan). Belum dijadwalkan — perlu diaktifkan di WSL/prod.

Verifikasi: `py_compile` OK, tanpa truncation. Smoke browser (login perawat/apoteker → buka kunjungan → cek row `audit_log` aksi=VIEW) perlu dijalankan user di WSL.
