# Backlog Terkubur — Konsolidasi Security / Deployment / Task Lama

**Dibuat:** 2026-09-17 · **Sifat:** inventaris item terbuka (bukan perubahan kode).
**Metode:** sisir Project_Memory (AUDIT_SEHATI_2026-07-10, AUDIT_ASVS + tindak-lanjut,
08_roadmap, TODO_SEHATI, RUNBOOK_PIP_AUDIT, HealthCheck) + verifikasi silang ke disk.
**Konteks penting:** banyak item lama ditulis pra-deploy (Jul 2026, rencana native
systemd+nginx). Realita sekarang = **Docker Compose + Tailscale serve di mini PC
`joderma-jemur`** (Sep 2026). Item deployment lama sudah sebagian usang → di-reframe di sini.

---

## ✅ Sudah ditutup (jangan dikejar lagi)

- Semua **P0/P1 uang+keamanan** audit 2026-07-10: void-stok overstate (P0-1, +lot-provenance),
  double-payment/double-komisi (P0-2, idempotency key + FOR UPDATE), XSS `|safe` (P1-4),
  CSV formula injection (P1-5), XFF rate-limit bypass (P1-3), rollback membership (P2-5),
  float→Decimal komisi/qty (P2-1/P2-2).
- **A1–A12** TODO tindak-lanjut audit: exclude VOID di agregasi uang, test jalur uang,
  timezone WIB, boot-guard JWT lemah, rate-limit bertingkat, helper `_shared` 403/redirect,
  idle-timeout sesi 60 mnt, audit akses-baca (perawat/apoteker/dokter), Klasifikasi Data V1.8,
  security header nosniff/X-Frame/Referrer/Permissions-Policy.
- **Higiene A7** (file dev nyasar): `debug_kunjungan.py`, `fix_timezone_tindakan.py`,
  `master.py.bak_restored`, `kunjungan.py.new`, `1`, `exit` → terverifikasi **sudah bersih**.
- **.gitignore** menutup `.env`, `backup_*.sql`, `backups/`, `deploy/schema_only.sql` → push-safety OK.
- **.env produksi template** benar: APP_ENV=production, APP_DEBUG=false, JWT_SECRET_KEY (≥32),
  COOKIE_SECURE=true. Deploy Docker mini PC sukses (boot-guard lolos → JWT prod terisi).
- **TLS**: terpenuhi via Tailscale serve (`.ts.net` HTTPS) + COOKIE_SECURE=true.
- **Follow-up Reminder** (#7) shipped & live.

---

## 🔒 KEAMANAN — masih terbuka

| ID | Item | Catatan | Prioritas |
|----|------|---------|-----------|
| S1 | **CSP + HSTS header** | Dulu nunggu HTTPS; sekarang HTTPS Tailscale sudah ada → bisa dikerjakan. Header dasar lain sudah ada. | Cepat-berdampak |
| S2 | **pip-audit terjadwal (Docker-aware)** | Unit `sehati-pipaudit.service/.timer` sudah ada tapi utk native (`/opt`, `User=sehati`). Mini PC = Docker → belum terpasang. Perlu versi jalan di/atas container. Ref: RUNBOOK_PIP_AUDIT.md | Cepat-berdampak |
| S3 | **Least-privilege DB + immutability audit_log** | GRANT user app hanya INSERT/SELECT di `audit_log` + user MySQL non-root (ASVS V7.3.1/V1.2). Cek user DB di stack Docker. | Menengah |
| S4 | **Enkripsi at-rest (LUKS)** disk mini PC | Belum terverifikasi. Photodex mensyaratkan; Sehati numpang mesin sama. (ASVS V8.1.6) | Menengah |
| S5 | **Kebijakan password ≥12 + cek bocor + paksa ganti login pertama** | Sekarang min 8, tanpa complexity/breach check. Adopsi bertahap (NIST: panjang > complexity). (V2.1.1/2.1.7) | Bertahap |
| S6 | **2FA TOTP Owner/Superadmin** | Dipertimbangkan (privilege tinggi, login jarang). Dokter TIDAK (friction). (V2.7) | Rendah |
| S7 | **Finance API auth guard** | `api/v1/finance.py` tanpa auth; aman krn semua endpoint 501. WAJIB `Depends(role_required)` di PR yang sama saat modul Finance dibangun. (P2-4 / V13.2.1) | Gate saat Finance |
| S8 | **Baca PHI hanya di-gate login, tanpa batas role** | Tiap staf bisa buka rekam penuh pasien mana pun. Konsisten model 1-klinik + akses sudah teraudit. Keputusan PHI yg perlu dicatat eksplisit / diputuskan. (P3) | Keputusan |

---

## 🚀 DEPLOYMENT — perlu reconcile dgn Docker+Tailscale

| ID | Item | Catatan | Prioritas |
|----|------|---------|-----------|
| D1 | **B3 Deployment Guide lama usang** | Guide systemd+nginx+Certbot digantikan Docker Compose + Tailscale. Tandai obsolete; rapikan runbook upgrade (rebuild image + alembic) / rollback (restore.sh) jalur Docker di README-DOCKER-MINIPC. | Menengah |
| D2 | **Higiene file di folder canonical E: (terverifikasi masih ada)** | `Current python code main_api.txt` (monolit legacy 83KB), artefak nyasar `ziFKtzj6`, folder duplikat **`sehati_clinic_template/`** (punya `.env` + `backup_*.sql` sendiri) + `sehati_clinic_template.zip`, tumpukan `backup_*.sql` di dalam `sehati_clinic/`. Push-safety OK, tapi PHI/secret nganggur di folder tersinkron. Rapikan/pindahkan keluar repo. | Cepat-berdampak |
| D3 | **MySQL tuning** | Container mysql:8.0 pakai default (max_connections, buffer pool, wait_timeout>280s). Minor utk skala klinik tunggal. | Rendah |
| D4 | **Verifikasi git safety-gate di E:** | Jalankan `git ls-files \| grep -iE '(^\|/)\.env$\|backup.*\.(sql\|zip)\|/backups/\|medis'` — pastikan nihil sebelum push berikutnya. | Cepat (cek) |

---

## 🗂️ TASK FITUR LAMA TERKUBUR (non-security)

| ID | Item | Catatan | Ref |
|----|------|---------|-----|
| F1 | **+Antrian kontekstual** | "Antri Tindakan" belum punya wadah tindakan prabayar/terjadwal (redeemable kunjungan berikutnya); "Antri Bayar" belum disabled saat nihil tagihan. Perlu design doc. | TODO §G |
| F2 | **Komisi Fase 2** | Skema komisi dokter (UNCAPPED / THRESHOLD_HALF / THRESHOLD_GUARANTEED) + config per-dokter + clawback VOID lintas-periode payroll. | TODO §E, KOMISI_MODULE_DESIGN |
| F3 | **P2-3 snapshot line-item Finance** | `transaksi_detail_tindakan` tak pernah ditulis; `diskon_item`/`hpp_satuan` kosong di `proses_bayar`. Prasyarat modul Finance untuk margin/COGS per-baris. | AUDIT 07-10 P2-3 |
| F4 | **Modul Absensi + work-session (AT300)** | Lapisan defense-in-depth: batasi akses eMR-POS di luar jam kerja. Modul besar, perlu design + breakdown. | TODO §F |
| F5 | **`_create_pending_membership_history_if_needed` tak ter-wire** | Diputuskan: buang atau sambungkan (history PENDING saat daftar). | DEAD_CODE_SWEEP, AUDIT 07-10 P3 |
| F6 | **Tenant-scoping `klinik_id`** | Belum ada kolom/filter per-klinik. Siapkan SEBELUM multi-klinik/data membesar. Nyambung ke arah multi-site. | P2-6, EMR_INTEGRASI_MULTISITE_DESIGN |
| F7 | **Dead-code sweep ~13 fungsi** | Report-only; cek intent+test per fungsi, jangan hapus buta. | TODO A11, DEAD_CODE_SWEEP |
| F8 | **Booking Fase 2** | Deposit/DP berbayar, reminder/notifikasi, booking online mandiri. PARKIR (tunggu visi jual ke klinik lain). | TODO §D |

---

## Saran urutan (cepat-berdampak dulu)

1. **D2 + D4** higiene file & cek safety-gate (murah, nutup celah PHI/secret).
2. **S1 CSP/HSTS** + **S2 pip-audit Docker-aware** (murah, nutup celah keamanan).
3. **S3 least-privilege DB** + **S4 verifikasi LUKS** (hardening mesin).
4. Baru masuk item besar (F1/F2/F3) sesuai kebutuhan operasional.

> Item S5/S6/S7/S8 = keputusan bertahap/kondisional, bukan blocker.
> Semua di atas MINTA APPROVAL sebelum eksekusi (perubahan schema/config besar).
