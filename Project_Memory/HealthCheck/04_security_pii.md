# 04 — Security + PII Checklist

**Layer:** Security, Privacy, Compliance
**Cadence:** Weekly automated + monthly manual review
**Reference:** `00_PROTOCOL.md`

---

## Tujuan

Untuk klinik kesehatan, data pasien (`nomor_ktp`, `tanggal_lahir`, `alamat`, riwayat medis) adalah **PII (Personally Identifiable Information)** yang regulasinya ketat. Plus credential staff (password, JWT) tidak boleh leak. Health Check ini fokus ke:

1. **CSRF protection** di semua POST form (cegah CSRF attack)
2. **JWT secret management** (tidak hardcoded, rotation-ready)
3. **Cookie security** (HttpOnly, Secure, SameSite)
4. **PII leak prevention** (tidak ada nomor_ktp/alamat di audit_log, log files, atau error messages)
5. **Role gate matrix** (semua role hanya akses page yang seharusnya)
6. **Password hash strength** (bcrypt, no plaintext storage)

---

## Checklist (otomatis)

| # | Check | Severity kalau fail | Cara |
|---|-------|---------------------|------|
| SEC-01 | Semua `<form method="POST">` di templates punya `csrf_input(request)` | 🟠 HIGH | Grep templates for form POST without csrf_input |
| SEC-02 | PII field di audit_log.keterangan (nomor_ktp/tgl_lahir/alamat) | 🔴 CRITICAL | DB query + code scan |
| SEC-03 | Password atau JWT token muncul di response body atau template | 🔴 CRITICAL | Grep templates + responses |
| SEC-04 | `cookie_secure` setting tidak terkonfigurasi | 🟠 HIGH | Cek config |
| SEC-05 | JWT secret hardcoded (bukan dari env) | 🔴 CRITICAL | Code scan |
| SEC-06 | Method password verification yang bypass bcrypt | 🔴 CRITICAL | Code scan |
| SEC-07 | Role check di route tapi role gate helper tidak dipakai | 🟡 MEDIUM | Grep routes for if user.role == vs require_X_role |
| SEC-08 | Audit log entry bisa di-DELETE oleh user role apapun | 🟠 HIGH | Cek tidak ada delete endpoint untuk audit_log |

---

## Checklist Role Gate Matrix (manual atau script)

Tabel ekspektasi akses per role. **X = boleh akses**, **— = harus 403**:

| Page / Endpoint | OWNER | SUPERADMIN | ADMIN | DOKTER | PERAWAT | FO | KASIR | APOTEKER | PURCHASING |
|-----------------|-------|------------|-------|--------|---------|----|----|----------|-----------|
| `/web/dashboard` | X | X | X | X | X | X | X | X | X |
| `/web/pasien` (search) | X | X | X | X | X | X | X | X | X |
| `/web/pasien/baru` | X | X | X | — | — | X | — | — | — |
| `/web/dokter/antrian` | X | X | X | X | — | — | — | — | — |
| `/web/dokter/input-medis/{id}` | X | X | X | X | — | — | — | — | — |
| `/web/ruang-tindakan/antrian` | X | X | X | X (read) | X | — | — | — | — |
| `/web/kasir/antrian` | X | X | X | — | — | — | X | — | — |
| `/web/apotek/antrian` | X | X | X | — | — | — | — | X | — |
| `/web/apotek/suggested-order` | X | X | X | — | — | — | — | X | — |
| `/web/master/treatment` | X | X | — | — | — | — | — | — | — |
| `/web/master/produk` | X | X | — | — | — | — | — | — | — |
| `/web/master/bahan` | X | X | — | — | — | — | — | — | — |
| `/web/pengadaan/pemesanan` | X | X | X | — | — | — | — | X (retail only) | X |
| `/web/pengadaan/pemesanan/baru` | X | X | — | — | — | — | — | X (retail only) | X |
| `/web/pengadaan/opname` | X | X | X | — | — | — | — | — | X |
| `/web/staf` | X | X | — | — | — | — | — | — | — |
| `/web/profil` | X | X | X | X | X | X | X | X | X |

**Cara test manual:** login per role → coba akses semua URL ini. Yang harus 403 harus benar-benar 403, bukan crash 500 atau silent allow.

---

## Checklist (manual)

- [ ] **HTTPS** — di production, server di belakang reverse proxy dengan HTTPS aktif?
- [ ] **JWT secret rotation plan** — kapan terakhir di-rotate? Plan untuk rotate ke depan?
- [ ] **Password policy** — minimum length, complexity untuk staf baru?
- [ ] **Backup encryption** — file backup mysqldump, enkripsi at-rest?
- [ ] **Audit log review** — quick spot-check 10 entries terbaru, normal?

---

## Cara menjalankan

```bash
cd /path/to/sehati_clinic
python ../Project_Memory/HealthCheck/scripts/pii_scan.py
```

---

## Kalau ada finding PII leak

**🔴 INI EMERGENCY** — kalau scan ketemu PII di audit log atau template:

1. **Stop deploy** kalau lagi dalam proses deploy
2. Buat issue di `07_known_issues.md` dengan tag `[health-check-security]` severity CRITICAL
3. Patch dalam 24 jam
4. Setelah patch: **review semua audit_log historis** — apakah PII sudah masuk DB? Kalau ya: sanitize record lama atau redact field.
5. Notify Bapak (atau auditor kalau ada) sesuai compliance requirement

---

## Glossary

- **PII**: Personally Identifiable Information — data yang bisa identifikasi orang. Untuk klinik: nomor_ktp, tanggal_lahir, alamat lengkap, nomor HP, email pribadi, riwayat medis spesifik.
- **CSRF**: Cross-Site Request Forgery. Pakai double-submit token (cookie + form field) untuk prevent attacker submit form atas nama user lain.
- **Role gate**: Helper function di `app/web/routes/_shared.py` yang check apakah user boleh akses page. Format: `require_X_role(user) -> bool`.
