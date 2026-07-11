# Security Test Results — Access Control / IDOR / API

**Tanggal:** 2026-06-25
**Metode:** Live test via browser (Chrome DevTools), login role rendah `petugas_fo` (role FO), fetch same-origin membawa cookie/JWT.
**Lingkungan:** localhost:8000 (staging). Aplikasi milik sendiri.

---

## Ringkasan: 🟢 Model otorisasi SOLID

Ketiga pertanyaan inti terjawab. Web (cookie + `require_*_role`) dan API (JWT + `role_required`) **dua-duanya menegakkan batas role dengan benar**. Satu hal yang perlu KEPUTUSAN kebijakan (bukan bug): cakupan data FO ke riwayat klinis pasien.

---

## B2 — Privilege Escalation via URL langsung → ✅ AMAN

Login sebagai FO, akses 10 URL owner-only. **Semua 403:**

| URL | Status |
|-----|--------|
| /web/staf | 403 "Hanya Owner/Superadmin/Admin" |
| /web/reports/audit-log | 403 "Hanya Owner/Superadmin" |
| /web/reports/omzet | 403 |
| /web/reports/void | 403 |
| /web/export | 403 "Hanya Owner" |
| /web/settings/klinik | 403 "Hanya Owner/Superadmin" |
| /web/master/produk · treatment · membership | 403 "Hanya Owner/Superadmin" |
| /web/pengadaan/pemesanan | 403 |

**Kesimpulan:** FO tidak bisa menembus halaman privileged via ketik URL. Guard `require_*_role` aktif & konsisten.

---

## B3 — IDOR (ID berurutan) → 🟡 Role-scoped (perlu keputusan privasi, bukan bug auth)

Sebagai FO:

| URL | Status | Catatan |
|-----|--------|---------|
| /web/dokter/kunjungan/1571/soap | **403** | SOAP dokter ditolak ✅ |
| /web/kasir/tagihan/1571 | **403** | Tagihan kasir ditolak ✅ |
| /web/ruang-tindakan/kunjungan/1571 | **403** | Ruang tindakan ditolak ✅ |
| /web/kasir/cari-transaksi | **403** | Ditolak ✅ |
| /web/pasien/1405, /1404, /1 | **200** | FO bisa baca **SEMUA** pasien dengan ganti ID |
| /web/pasien/1405/riwayat | **200** | FO bisa baca **riwayat klinis lengkap** (SOAP/diagnosa) |

**Analisis:** Ini **bukan IDOR klasik** (bukan auth-bypass). FO role memang diizinkan melihat data pasien, dan di klinik tunggal tidak ada konsep "kepemilikan per-objek" (FO melayani semua pasien). Halaman peran-spesifik (SOAP/tagihan/tindakan) sudah benar ditolak.

**Yang perlu KEPUTUSAN (dr. Hansen):** FO (front office) bisa enumerasi seluruh database pasien + **membaca riwayat klinis/diagnosa** via ganti ID. Pertanyaannya kebijakan, bukan teknis:
- Apakah pantas petugas FO melihat diagnosa medis lengkap? (prinsip minimum-necessary / kerahasiaan medis)
- Kalau tidak: scope kolom klinis (SOAP/diagnosa) supaya FO hanya lihat demografi + status kunjungan, bukan detail medis.
- Kalau ya (FO dipercaya penuh): acceptable untuk klinik tunggal, tapi catat sebagai keputusan sadar.

---

## B4 — API /api/v1/* Role Enforcement → ✅ AMAN

**Tanpa token (cookie web saja):** semua endpoint API → **401 "Not authenticated"**. Cookie web TIDAK memberi akses API (pemisahan realm auth bagus).

**Dengan JWT FO (login via /api/v1/auth/login, form-encoded):**

| Endpoint | Status | Hasil |
|----------|--------|-------|
| /api/v1/auth/me | 200 | profil sendiri (benar) |
| /api/v1/staf | **403** | "Akses ditolak. Role Anda (FO) tidak memiliki izin." ✅ |
| /api/v1/reports/omzet-harian | **403** | role ditolak ✅ |
| /api/v1/pasien/1405 | 200 | FO baca pasien (konsisten dgn web) |

**Kesimpulan:** API menegakkan **autentikasi** (401 tanpa token) DAN **otorisasi** (403 role salah) dengan pesan jelas. Solid.

---

## Verdict & Rekomendasi

- **Privilege escalation & API role enforcement: AMAN.** Tidak ada celah bypass. Tidak butuh perbaikan.
- **IDOR: secara teknis aman** (guard role bekerja); **1 keputusan kebijakan** soal apakah FO boleh lihat riwayat klinis. → ditambahkan sebagai task keputusan.
- **Rate limiting login (C2):** tetap relevan dipasang (rate-limit per-IP, BUKAN account lockout) — terutama bila app diekspos internet. Bila LAN-only, prioritas rendah.

**Sisa yang BELUM ditest (opsional, butuh effort lebih):** session fixation, CSRF bypass (sudah ada middleware DEC-031), JWT tampering/expiry, SQL injection di field input, mass-assignment. Bisa jadi paket security review terpisah kalau Bapak mau menyeluruh.
