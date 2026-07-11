═══════════════════════════════════════════════════════════
SESSION HANDOFF — Deployment & Go-Live Sehati eMR-POS
Disusun: 2026-06-26 · untuk sesi deployment (saat server klinik siap)
═══════════════════════════════════════════════════════════

## ROLE
Claude = lead programmer Sehati. dr. Hansen = dokter pemilik (non-programmer), Bahasa Indonesia
casual. Workspace: `E:\Claude\Projects\sehati-emr-pos\sehati_clinic` (sudah pindah dari C:, B-013
hilang). Target deploy: **server lokal LAN klinik (Linux/Ubuntu), HTTP, tanpa remote**.

## ⚠️ KAPAN SESI INI DIPAKAI
Saat **hardware server klinik sudah siap**. Mayoritas langkah B3.2-B3.9 dikerjakan DI SERVER
KLINIK, bukan dari sini. Sebelum deploy, sebaiknya **paket keamanan pra-launch (#37-40) sudah
beres** (lihat "Prasyarat" bawah).

## PANDUAN UTAMA (sudah lengkap)
`sehati_clinic/deployment/B3_DEPLOYMENT_GUIDE.md` — panduan langkah-demi-langkah versi server
lokal LAN, dengan contoh config (.env/systemd/nginx) + checklist. **Baca itu sebagai sumber utama.**

═══════════════════════════════════════════════════════════
## STATUS B3
═══════════════════════════════════════════════════════════
- ✅ **B3.1 Self-host aset** — SELESAI & verified (HTMX/Tom Select/Chart/Tailwind lokal, test
  offline berhasil). Script: `deployment/build_tailwind.sh`, vendor di `static/vendor/`.
- 📋 **B3.2-B3.9 — BELUM** (dikerjakan di server klinik):

  | # | Task | Tempat | Effort |
  |---|------|--------|--------|
  | B3.2 | `.env` produksi (APP_ENV=production, DEBUG=false, COOKIE_SECURE=false utk HTTP LAN, JWT secret baru, RM_CLINIC_PREFIX=A) | server | ~30m |
  | B3.3 | uvicorn → systemd service (auto-start saat boot + auto-restart) 🔴 | server | ~1h |
  | B3.4 | nginx reverse proxy (opsional; biar akses `http://192.168.1.x` tanpa :8000) | server | ~1h |
  | B3.5 | IP statis server (reservasi DHCP di router) + cara akses workstation/Android | server/router | ~30m |
  | B3.6 | Tuning MySQL (wait_timeout>280s, max_connections, auto-start) | server | ~30m |
  | B3.7 | Backup cron harian + salinan offsite + tes restore 🔴 | server | ~1h |
  | B3.8 | Prosedur upgrade & rollback (runbook) | doc | ~1h |
  | B3.9 | Checklist pra-launch + smoke test final di hardware | server | ~1h |

  🔴 = inti wajib. Total sisa ~5-6 jam (mostly di server).

═══════════════════════════════════════════════════════════
## PERSIAPAN GO-LIVE (keputusan + aksi, sebelum/saat deploy)
═══════════════════════════════════════════════════════════
1. **Keputusan data produksi:** mulai KOSONG (full reset) atau bawa data historis Excel
   (Mar-Mei 2026)? → menentukan pakai "reset total" atau "cleanup selektif".
2. **Cleanup data dummy/test:** `seed_data/cleanup_dummy_test_2506.sql` (anchor `nama LIKE 'DUMMY%'`)
   menghapus pasien test 1405-1410. ATAU full production reset (wipe transaksional, keep master).
   Disiplin: semua data test WAJIB diawali penanda (DUMMY/TEST).
3. **#35 Verifikasi auto-print** di printer kasir asli (A5/thermal) — setelah bayar, pastikan
   tombol Void & navigasi tetap normal setelah tab print muncul.
4. **Verifikasi B-013 final:** sudah hilang di E: (tes null-byte = 0). Pastikan deploy dari E:.

═══════════════════════════════════════════════════════════
## PRASYARAT — Paket Keamanan Pra-Launch (#37-40)
═══════════════════════════════════════════════════════════
Sebaiknya tuntas SEBELUM go-live (data medis + PII). Bisa dikerjakan di dev (tidak butuh hardware):
- #37 JWT tampering & expiry test (ubah payload/role, alg-none, expiry, reuse pasca-logout)
- #38 SQL injection test di field input (search/login/filter) — ORM umumnya aman, cek raw query
- #39 Session fixation test (cookie regenerate pasca-login, flags HttpOnly/SameSite)
- #40 Mass-assignment test (POST set field tak seharusnya: role/id/harga via param ekstra)
- + **C2 rate-limit login** sudah DONE; **C5 HTTPS** = N/A untuk LAN-HTTP (lihat DEC-070/071).
Detail rencana: `HealthCheck/remediation_security_plan_2026-06-25.md`.

═══════════════════════════════════════════════════════════
## START SEQUENCE (saat server siap)
═══════════════════════════════════════════════════════════
1. Pastikan paket keamanan #37-40 sudah dijalankan (atau putuskan ditunda dengan sadar).
2. Buka `deployment/B3_DEPLOYMENT_GUIDE.md` → ikuti B3.2-B3.9 berurutan di server klinik.
3. Jalankan persiapan go-live (keputusan data + cleanup + auto-print test).
4. Smoke test full 7 role di hardware → sign-off launch.
═══════════════════════════════════════════════════════════
