# Remediation & Security Plan — Pra-Launch

**Tanggal:** 2026-06-25
**Sumber:** Frontend/UX audit (`frontend_ux_audit_2026-06-25.md`) + known issues lama (C2/C3/C5)
**Tujuan:** peta jelas perbaikan sebelum production launch klinik.

---

## Prinsip Sequencing

Tidak perlu memilih "fix audit dulu" ATAU "deploy dulu" — sebagian temuan MEMANG bagian deployment. Urutan:

1. **Quick wins** (~1-2 jam) — kosmetik murah, dikerjakan sebelum launch.
2. **Security pra-launch** — test access-control + fix rate limiting.
3. **B3 Deployment** — sudah termasuk 2 item reliabilitas 🔴 (self-host aset, Tailwind build) + HTTPS + JWT rotation.
4. **Post-launch** — a11y label + overflow (penting tapi tidak memblokir operasional).

---

## TRACK A — Remediasi UX (dari audit)

| # | Task | Kategori | Effort |
|---|------|----------|--------|
| A1 | Fix role enum leak `StafRoleEnum.OWNER` di `_shared.py` | Quick win | ~15m |
| A2 | Seragamkan format Rp (Tagihan koma → titik) | Quick win | ~30m |
| A3 | Fix input nominal `valuemax=0` + label 2 tombol wizard | Quick win | ~30m |
| A4 | Self-host HTMX + Tailwind + Tom Select ke `/static/` | B3 deploy 🔴 | ~2-3h |
| A5 | Build Tailwind produksi (CLI/PostCSS) | B3 deploy 🔴 | ~1-2h |
| A6 | Label association form (wizard 17 / SOAP 8 / tagihan 5) | Post-launch | ~2-3h |
| A7 | Fix overflow horizontal (tabel Antrian + step bar wizard) | Post-launch | ~1-2h |
| A8 | Verifikasi auto-print di hardware kasir asli + cleanup data dummy | Verify | ~30m |

---

## TRACK B — Keamanan Pra-Launch

> Konteks: aplikasi menyimpan PII + data medis. Semua test di **staging/localhost**, BUKAN production. Aplikasi milik sendiri → etis & legal.

### B1 — Fix C2: Rate limiting login (langsung tambal, jangan dites)
`/auth/login` belum ada rate limit (sudah tercatat C2). Pasang `slowapi` + lockout setelah N gagal. `login_failed` sudah ter-audit dengan IP → bisa dipakai deteksi. Brute-force test tidak perlu karena gap sudah diketahui.

### B2 — TEST Privilege Escalation (akses URL langsung)
**Metode:** login role rendah → coba GET URL owner-only:
- `/web/reports/audit-log`, `/web/reports/void`
- `/web/staf`, `/web/export`, `/web/settings/klinik`
- `/web/master/treatment|bahan|produk|membership`

**Ekspektasi:** 403 / redirect ke login/dashboard. **200 = privilege escalation vuln.**

### B3 — TEST IDOR (Insecure Direct Object Reference)
**Metode:** sebagai role rendah / pasien-tak-terkait, akses dengan ID milik orang lain:
- `/web/pasien/{id_lain}` (data pasien)
- `/web/kasir/tagihan/{id_kunjungan_lain}`
- `/web/dokter/kunjungan/{id_lain}/soap`
- Enumerasi: ganti ID berurutan (1405, 1404, 1403...) — bisakah intip semua pasien?

**Ekspektasi:** akses ditolak/scoped sesuai hak. **Bisa intip = IDOR vuln** (serius untuk data medis).

### B4 — TEST API `/api/v1/*` Role Enforcement
**Metode:**
- Hit endpoint API dengan JWT role rendah → cek `role_required` ditegakkan (403).
- Hit tanpa token sama sekali → cek 401, tidak ada endpoint sensitif terbuka.
- `/api/v1/dokter/pasien/{id}/header` → test IDOR via API.

### B5 — Code Review: Coverage `role_required`
Grep semua route (`app/web/routes/*`, `app/api/v1/*`), petakan endpoint yang punya guard (`role_required` / `require_*_role` / `get_user_from_cookie`) vs yang tidak. Cross-check dengan hasil B2-B4. Endpoint mutating tanpa guard = prioritas.

### B6 — Deployment Security (fold ke B3 Deployment Guide)
- **C5** HTTPS via nginx + Certbot, set `COOKIE_SECURE=true`.
- **C3** JWT secret production (bukan dev) + rencana rotasi.

---

## ⚠️ Prasyarat untuk Eksekusi B2-B4

Test live butuh **minimal 1 akun role rendah** (FO atau Kasir) — login `owner1` tidak bisa mendeteksi privilege escalation karena Owner memang boleh akses semua.

**Yang dibutuhkan dari dr. Hansen:** username + password 1 akun FO + 1 akun Kasir (atau Kasir saja). Tanpa ini, hanya B5 (code review) yang bisa jalan — dan B5 sendiri sudah bisa mengungkap mayoritas gap guard tanpa login.

---

## Rekomendasi Urutan Eksekusi

1. **B5 code review** (tidak butuh login) — petakan guard, temukan gap cepat.
2. **B2-B4 live test** (butuh akun role rendah) — konfirmasi di runtime.
3. **B1 fix rate limit** + **A1-A3 quick wins** (batch perbaikan murah).
4. **B3 Deployment** (A4 + A5 + B6).
5. **A6-A7** post-launch.
