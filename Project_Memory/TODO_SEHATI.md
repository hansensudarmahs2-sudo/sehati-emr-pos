# TODO / PLAN — Sehati eMR-POS (living backlog)

**Update:** 2026-07-02 (komisi Fase 1 done + backlog +Antrian) · Sumber: AUDIT + roadmap + handoff + diskusi dr. Hansen.
**Sifat:** Rencana, BELUM dieksekusi. Centang/urut saat dikerjakan. Gantikan keharusan baca roadmap panjang.

> Keamanan dikonfirmasi: SQL injection TIDAK mungkin (ORM parameterized), XSS ter-mitigasi (Jinja auto-escape, tanpa `|safe`).

---

## A. Tindak lanjut AUDIT (paling berdampak dulu)

### 🔴 P0
- [x] **A1. Exclude VOID di semua agregasi uang.** ✅ DONE 2026-06-29 (DEC-079) Tambah filter `status_transaksi='BAYAR'` di:
  `reports_service` (omzet_harian, omzet_bulanan, rekap_kasir_shift), `dashboard_service` (KPI omzet/transaksi/kasir-stats),
  `export_service` (omzet/transaksi/pembayaran + tambah kolom status), `kasir_repo` (list_transaksi_shift, aggregate_pembayaran_shift → rekap_shift).
  Bikin 1 helper bersama `only_bayar()` supaya tak terulang. + test regresi.

### 🟠 P1
- [x] **A2. Test jalur uang/POS** ✅ DONE 2026-06-29 — `tests/integration/test_kasir_void_exclusion.py` (5 test non-destruktif): omzet/rekap/closing exclude VOID + void-balikkan-stok + parity preview vs rekap. 3 pertama sudah PASS di mesin dr. Hansen.
- [x] **A3. Rollback di tengah transaksi membership** ✅ DONE 2026-06-29 (DEC-081, savepoint begin_nested) (`membership_service.py:668` di dalam pemeriksaan save) → savepoint/begin_nested atau biarkan exception naik.
- [x] **A4. Timezone** ✅ DONE 2026-06-29 (DEC-080) — sweep + unifikasi ke WIB (`datetime.now()`) di titik korektif+display; export UTC & token (self-consistent) dibiarkan.
- [ ] **A5. Auth guard pada finance API router** — DOKUMENTASI saja dulu (semua endpoint masih 501, tak ada data bocor). Dipertimbangkan SETELAH live test perdana.

### 🟡 P2
- [x] **A6.** ✅ DONE 2026-07-02 — Startup guard: `config.py` `_guard_production_secret` tolak boot kalau `app_env=production` dan `jwt_secret_key` default/`<32 char`. Non-aktif di development.
  > ⚠️ **AKSI POST-DEVELOPMENT / PRODUCT-READY (WAJIB sebelum go-live):** guard ini **SENGAJA menolak boot produksi** selama `JWT_SECRET_KEY` belum di-set. Sebelum deploy pertama ke `APP_ENV=production`, WAJIB set `JWT_SECRET_KEY` di `.env` prod dengan string acak ≥ 32 char — generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Kalau lupa, app **tidak akan start** (fail-secure, by design). Lihat juga B1/B2 (config prod). Selama masih dev/test, tidak berdampak.
- [ ] **A7.** Hapus file duplikat usang: `master.py.bak_restored`, `kunjungan.py.new`; bersihkan file nyasar (`1`, `exit`, `debug_kunjungan.py`, `fix_timezone_tindakan.py`); pastikan `backups/` + `*.sql` di .gitignore.
- [x] **A8.** ✅ DONE 2026-07-02 (DEC-084) — Helper bersama di `_shared.py`: `login_redirect()`, `forbidden(detail,partial)`, `session_expired(partial)`, `web_guard()`. Bentuk 403 dibakukan. `booking.py` diadopsi sbg referensi. **Migrasi ~180 call-site lama = BERTAHAP** (route baru wajib pakai; legacy migrasi saat disentuh, TIDAK mass-migrate buta).
- [x] **A9.** ✅ DONE 2026-07-02 — Decimal (bukan float) di 3 loop akumulasi uang `reports_service` (apoteker dispensed, write-off, top-produk): akumulasi `Decimal`, convert `float` hanya di boundary output (tipe output tak berubah). Sisa `float()` = persen / single DB-sum cast (sudah benar). Perlu test endpoint Reports.
- [x] **A10.** ✅ DONE (folded ke A4/DEC-080) — `resep.waktu_void = datetime.now()` (WIB, match `void_at`) di `kasir_service:1012` & `kasir_repo:219`.

### 🟢 P3
- [x] **A12. Rate-limit cooldown BERTINGKAT** ✅ DONE 2026-06-29 (DEC-082) — Ganti flat 5 menit → **cascade 1, 2, 3, 4, … menit** per blokir berulang (simpan 'strike count' per IP; reset setelah jeda bersih). Cukup mempersulit brute-force tanpa mengganggu operasional. In-memory cukup; Redis hanya bila multi-worker.
- [x] **A11.** ✅ DONE 2026-07-02 (DEC-084) — `/health/db` tak lagi bocor versi/error; logout `POST`+CSRF (route+`_app.html`); password/PIN user baru 8/6 (reset lama tetap 6/4); `AuditLog` ke `__all__`; README "Alembic canonical". Dead code: hapus `pasien_repo.get_by_no_rm`; **KEEP** `count_transaksi_for_kunjungan` (intent reopen FLOW-D) & `get_for_update/add_stok` (concurrency).
  > Sisa ~13 fungsi dead → **sweep khusus** nanti (cek intent+test per fungsi, jangan hapus buta).

---

## B. Pra-deployment (menuju go-live)
- [ ] **B0. (dari A6) Set `JWT_SECRET_KEY` di `.env` produksi** — string acak ≥ 32 char (`python -c "import secrets; print(secrets.token_urlsafe(48))"`). WAJIB: tanpa ini, boot `APP_ENV=production` **ditolak** oleh startup guard A6. Set juga `COOKIE_SECURE=true` + `APP_ENV=production` saat go-live.
- [ ] **B1. Paket Keamanan / hardening** — overlap A5/A6/A8 + C2/C5 (rate-limit sudah; tinggal prod config + HTTPS).
- [ ] **B2. B3 Deployment Guide** — systemd, nginx + HTTPS, `.env` prod, tuning MySQL, upgrade/rollback, rencana port (DEC-078).
- [ ] **B3. Verifikasi self-host aset** untuk offline (Sehati sudah; pastikan modul DermAI/Antro ikut).

---

## C. Konektor AI (sisi Sehati — setelah kontrak final + repo modul siap)
Ref: CONTRACT_SEHATI_DERMAI_v0.2.md, CONTRACT_SEHATI_ANTROPOMETRI_v0.1.md, ARSITEKTUR_EKOSISTEM_DEPLOYMENT.md.
- [ ] **C1.** Finalkan kontrak + tambah `return_url` ke schema kedua kontrak.
- [ ] **C2.** DB: `is_acne`/`acne_severity`/`dermai_case_id` (pemeriksaan); `antro_assessment_id`.
- [ ] **C3.** Service `DermAIConnector` + `AntroAIConnector` (rakit payload, POST /intake Bearer, simpan id, buka url).
- [ ] **C4.** SOAP toggle Acne/Non-acne + tombol "Analisa Foto (DermAI)" / "Foto DermAI" / "Buat Laporan Komposisi Tubuh".
- [ ] **C5.** Endpoint write-back penyakit kronis (engine reconcile SUDAH ada — tinggal endpoint + token B).
- [ ] **C6.** Config `.env` (base_url + token A/B) + signed-url.

---

## D. Modul Booking — ✅ FASE 1 DONE (2026-07-01, DEC-083)
Arahan dr. Hansen (2026-06-29). Dibangun bertahap L1–L5, terverifikasi live-test.
- [x] **D1.** Rancang modul → BOOKING_MODULE_DESIGN.md (approved).
- [x] **D2.** Implement Fase 1:
  - [x] L1 migrasi + model (extend `jadwal_booking`, kolom RESERVED siap-bayar).
  - [x] L2 `BookingService` (gate member VIP/VVIP + CRUD + reschedule) + test.
  - [x] L3 route + 3 template kalender + menu (FO/Kasir/Admin/Owner/Superadmin).
  - [x] L4 check-in → Kunjungan (ANTRI_KONSULTASI / ANTRI_TREATMENT), guard hari-H.
  - [x] L5 test + housekeeping (DEC-083, B-028 pelajaran Tailwind-purge).
- Spec terpenuhi: kalender + top-3/tanggal + Detail + Add; **member-only**; **deposit PARKIR** (kolom RESERVED ada).
- **Fase 2 (PARKIR):** aktivasi booking berbayar/deposit (untuk jual ke klinik lain), reminder/notifikasi, booking online mandiri pasien.

---

## E. Modul Komisi Staf — ✅ FASE 1 DONE (2026-07-02, DEC-087/088)
Komisi Dokter & Perawat. Ref `KOMISI_MODULE_DESIGN.md`.
- [x] **K-L0** 2 kolom pelaksana (`id_dokter_pelaksana`/`id_perawat_pelaksana`) + Ruang Tindakan set + filter antrian dokter.
- [x] **K-L1** tabel `komisi_ledger` (snapshot).
- [x] **K-L2** tulis komisi saat bayar + void handling + test.
- [x] **K-L3** service laporan (agregasi + rincian).
- [x] **K-L4** halaman Reports → Komisi Staf + akses per-role (owner semua; dokter/perawat sendiri).
- [x] **K-L5** test + housekeeping.
- **Opsi A (DEC-088):** komisi tindakan gratis (series/kuota) tetap dibayar — enumerasi SELESAI saat bayar.
- **Fase 2 (DITUNDA, decide-after):** skema komisi DOKTER (UNCAPPED / THRESHOLD_HALF / THRESHOLD_GUARANTEED)
  + config per-dokter di owner/superadmin + detail clawback VOID (kalau periode payroll sudah ditutup).

---

## G. +Antrian: opsi kontekstual + "tindakan dibeli/dijadwalkan nanti" (BARU — perlu design)
Temuan dr. Hansen (2026-07-02) saat modul komisi. Menu +Antrian punya 4 opsi: Antri Konsultasi, Antri Tindakan,
Antri Bayar, Beli Produk tanpa konsul. Dua celah logika:
1. **"Antri Tindakan" belum punya penampung untuk "tindakan dibeli/dijadwalkan nanti".** Skenario yang belum ada:
   - Pasien **beli tindakan** (mis. facial/basic treatment oleh perawat) untuk dilakukan **di hari lain**.
   - Dokter sudah menyimpan rencana tindakan di **SOAP** tapi pasien **tidak menebus/melakukan hari itu** → harusnya
     bisa dilanjutkan di kunjungan berikutnya.
   Saat ini "Antri Tindakan" hanya bermakna kalau ADA series / kuota membership / tindakan pending. Di luar itu, tak
   ada wadah "kredit tindakan prabayar/terjadwal".
2. **"Antri Bayar" harus DISABLED kalau tak ada item belum dibayar.** Opsi tak boleh dipilih saat tak ada tagihan.

**Arah solusi (draft, perlu design doc sendiri):**
- Opsi +Antrian jadi **kontekstual**: enable hanya kalau valid (Antri Tindakan aktif kalau ada rencana/series/kuota/
  tindakan-prabayar; Antri Bayar aktif kalau ada item outstanding).
- "Tindakan dibeli/dijadwalkan nanti" kemungkinan **memakai ulang `pasien_rencana_treatment`** (rencana treatment)
  — ditandai prabayar/terjadwal → muncul sebagai item redeemable di Antri Tindakan kunjungan berikutnya. Perlu cek
  interaksi dengan kasir (bayar di muka), kuota, dan komisi (komisi ditulis saat tindakan SELESAI — sudah cocok Opsi A).
- Butuh breakdown + approval sebelum coding (seperti Booking/Absensi).

---

## F. Modul Absensi + Work-Session (penguatan keamanan — DEFENSE IN DEPTH)
Status: RENCANA, belum diimplementasi. Modul besar (perlu design doc + breakdown sebelum coding, mirip Booking).
Tujuan: absensi karyawan + membatasi akses eMR-POS di luar jam kerja (anti data-mining/eksploitasi).
Disadari ini lapisan **sekunder**, bukan pengaman primer.

**Spec (dr. Hansen, 2026-06-29):**
1. Mesin absensi **AT300** connect via LAN/wireless → live absensi di **modul Absensi** (modul baru).
2. Modul Absensi menerbitkan **token `work_session`** saat check-in.
3. `work_session` berakhir saat **absen pulang/check-out** ATAU **pk 23:59** (prioritas: check-out).
4. **Mesin absen error** → admin/superadmin/owner berwenang **mematikan `work_session`** untuk 1 hari penuh
   (batas 23:59) + WAJIB catatan **audit trail**.
5. **Lembur lewat 23:59** → absen ulang ATAU bypass superadmin/owner (sangat langka — siapkan **contingency**).
6. Superadmin/owner bisa **memperpanjang** `work_session` diri sendiri & karyawan lain + **audit trail**.
7. `work_session` = bagian absensi + **penyulit akses eMR-POS di luar jam kerja**. Bukan pengaman primer.

**Catatan desain / open questions (saat dirancang nanti):**
- Integrasi AT300: pastikan model + protokol/SDK (mesin tipe ZKTeco umumnya push/pull TCP).
- Gate akses: middleware cek "ada `work_session` aktif utk user ini?" sebelum izinkan akses; tanpa itu → tolak
  (kecuali override owner/admin utk darurat).
- Hubungan dgn login/JWT: work_session = lapisan TAMBAHAN di atas login. Login valid tapi work_session habis → akses ditolak.
- Fail-safe saat mesin mati di check-in: override manual admin/owner (audit) = contingency utama.
- Owner/Admin jangan terkunci total (mereka pemberi override).
- Basis waktu 23:59 = WIB → konsisten dgn A4 (timezone).

## PARKIR / Future
- Deposit/uang muka booking (tunggu kebutuhan jual ke klinik lain).
- Series severity re-assessment (DermAI Phase 1).
- Phase 2–5 (akses pasien, AI integration, app native mobile, multi-cabang).

---

# MASTER TO-DO (konsolidasi 2026-07-04) — mulai dari Deployment/B3

## A. DEPLOYMENT (B3) — GATE ke produksi
> 2026-07-04: Guide di-REFRESH + file config siap-pakai (deployment/sehati-clinic.service, nginx_sehati.conf,
> .env.prod.example). Target: 1 klinik, Ubuntu native, LAN, HTTP. Sisa = eksekusi DI SERVER oleh dr.Hansen/teknisi.
- [x] Deployment Guide + config files (B3_DEPLOYMENT_GUIDE.md refreshed). SISA: eksekusi server (systemd, IP,
      MySQL grant, cron backup, setup data awal, smoke test fisik).
- [ ] HTTPS/TLS (Certbot atau self-signed/internal CA) → set COOKIE_SECURE=true.
- [ ] .env.prod: APP_DEBUG=false, APP_ENV=production (boot-guard sudah menolak debug di prod), JWT_SECRET kuat.
- [ ] MySQL tuning (max_connections, buffer pool, wait_timeout>280s), backup cron (backup.sh sudah ada).
- [ ] Prosedur upgrade (git pull + alembic upgrade head + restart) & rollback (restore.sh + git tag).
- [ ] Pre-launch checklist (firewall, swap, monitoring).

## B. KEAMANAN TERJADWAL (audit ASVS) — sebagian GATE sebelum keluar LAN/cloud
- [ ] TLS produksi (V9) — WAJIB saat non-LAN/cloud.
- [ ] Security headers CSP/HSTS (V14.4.1) — setelah TLS (nosniff/X-Frame sudah ada, DEC-093).
- [ ] Enkripsi at-rest (V8.1.6) — BitLocker/LUKS pasca-provisioning.
- [x] Idle-timeout sesi (V3.3.2) — DONE 2026-07-08: client-side (interaksi nyata + localStorage), 60 mnt + peringatan 2 mnt, seragam. Env: SESSION_IDLE_MINUTES/SESSION_IDLE_WARN_MINUTES. Teruji live (warn+reset+auto-logout).
- [ ] Password ≥12 + cek bocor (V2.1.1/2.1.7) — bertahap.
- [ ] 2FA TOTP Owner/Superadmin (V2.7) — dipertimbangkan (dokter tidak).
- [ ] pip-audit dependensi (V14.5.2) — scheduled task mingguan.
- [ ] Immutability audit: GRANT app hanya INSERT/SELECT di audit_log (V7.3.1) + least-privilege DB (V1.2).
- [ ] Klasifikasi data PII (V1.8).
- [ ] Finance guard finance.py — pasang Depends(role_required) SAAT modul finance dibangun (V13.2.1).

## C. FITUR TERTUNDA / DISKUSI
- [ ] ~~FK-L6 AP/hutang faktur~~ → DIPINDAH ke MODUL FINANCE (keputusan dr. Hansen 2026-07-04):
      status bayar faktur + jatuh tempo (dari termin PO) + laporan hutang ke distributor = ranah finance,
      dikerjakan sebagai bagian modul Finance tersendiri (bukan sub-faktur). Data faktur/retur sudah rapi utk ini.
- [ ] Rename master_klinik_config→master_klinik multi-cabang. TUNDA sampai cabang ke-2. TO BE DISCUSSED.
- [ ] P-L6c — tindakan potong BHP → FEFO bahan (task #62). DITUNDA.
- [ ] +Antrian kontekstual (antri tindakan prabayar/terjadwal; antri bayar disabled bila nihil) — TODO §G, perlu design doc.
- [ ] Booking DP/deposit — PARKIR (tunggu visi booking-membership).

## D. INTEGRASI (Phase 2)
- [ ] Konektor DermAI + Antropometri (kontrak v0.2/v0.1 sudah ada) — butuh cloud/hardware.
- [ ] Konektor Finance pihak ketiga (Accurate) — administrasi faktur/retur sudah dirapikan untuk ini.

## E. POLISH / OPSIONAL
- [ ] Relabel status PO "Partial" → "Berjalan" (kosmetik). (dr. Hansen: SKIP untuk sekarang.)
- [ ] Filter aksi=VIEW eksplisit di Audit Log Viewer.
- [ ] Sisa NOTA_PO_FAKTUR §B/§C bila ada yang belum (mayoritas sudah: PO ideal + faktur PPN/diskon/parsial).

## UI / MOBILE (2026-07-04)
- [x] Nav drawer + hamburger HP (<768px) di _app.html — DEC-098.
- [x] Bersih tombol dev: Header Dokter (JSON) dihapus, Swagger UI gate Owner — DEC-098.
- [ ] Mobile-friendly ALUR FOTO perawat/dokter (patient quick-view + tombol intake DermAI +
      halaman return_url). DITUNDA s/d DermAI ada. Kamera = ranah DermAI (syarat kontrak: responsif HP).
      Bukan redesign mobile penuh — hanya surface kecil alur foto. Operasional lain tetap tablet/desktop.

## SESI 2026-07-07 — SELESAI
- [x] Smart Export ke Finance (UI owner/superadmin + fingerprint, file-drop, ingest_batch formal).
- [x] Security quick-wins: Permissions-Policy, audit-baca perawat/apotek, KLASIFIKASI_DATA_V1.8, RUNBOOK_PIP_AUDIT.
- [x] Cache fondasi (ttl_cache + 5 endpoint antrian + indeks audit_log).
- [x] Warna wait antrian FO (waktu_masuk_status + kartu berwarna konsul/treatment/bayar).
- [x] Nomor antrian: cetak thermal + auto-print daftar + cetak-ulang (reset harian 00:01 WIB).
- [x] Badge per-role di menu (ANTRI_KONSULTASI/TREATMENT/BAYAR/OBAT).
- [x] #4 Riwayat SOAP panel + revamp layout form SOAP 60/40.
- [x] Data Analyst: run JSON-aware + toleran dataset kosong + modul movement + status_maps refresh.
- [x] Intercompany settlement (design-only, finance-ai/26).

## NEXT (primed) — #7 FOLLOW-UP REMINDER
- [ ] Bangun modul follow-up per FOLLOWUP_REMINDER_DESIGN.md (G1 model → G6 menu+smoke).
      Field min/max minggu & override dokter sudah ada; yang baru: tabel followup + halaman list
      weekly/daily + workflow 4-tombol beraudit. MINTA APPROVAL, mulai dari G1.

## BACKLOG (ditunda, urutan longgar)
- [ ] Landing page + QR nomor antrian → PHASE setelah live-run ≥6 bulan.
- [ ] Queue orchestration L2–L5 = SOP OFFLINE (bukan software).
- [ ] Pre-deployment B0–B3 (eksekusi di server oleh dr.Hansen/teknisi).
- [ ] Security lanjutan: 2FA Owner/Superadmin, immutability audit GRANT, CSP/HSTS pasca-TLS, pip-audit terjadwal.

## SESI 2026-07-08 — SELESAI
- [x] #7 Follow-up Reminder (G1–G6) SHIPPED & live. Migrasi head = 20260707_0400.
      Tabel followup + generation on-SOAP-save + halaman worklist 4-tombol beraudit + menu.

## SESI 2026-07-08 (lanjutan) — POLISH
- [x] QA sweep webapp (Chrome DevTools): 7 role, 0×5xx, RBAC benar, Follow-up gating sesuai. (QA_SWEEP_2026-07-08.md)
- [x] Dead-code sweep: analisis 19 kandidat (report-only, 0 dihapus). Temuan: #362D membership PENDING mungkin putus. (DEAD_CODE_SWEEP_2026-07-08.md)
- [x] Audit Log Viewer: filter eksplisit "Akses Baca (VIEW)" (Semua/Hanya/Tanpa) + datalist aksi.
      BUG-FIX sekalian: dropdown User(Staf)/Tabel Target selama ini KOSONG (template baca dropdowns.staf/tabel_target,
      service kirim staf_list/tabel_list) → diselaraskan. Verified live: 118 = 23 VIEW + 95 non-VIEW.
- [x] pip-audit TERJADWAL mingguan: skrip diperkuat (auto-venv, hitung temuan, retensi 12, exit2+marker) +
      systemd service+timer (deployment/sehati-pipaudit.*) + runbook cara pasang. Logika teruji (parser+retensi).
      SISA: pasang unit di server (sudo cp + enable --now) — perintah di RUNBOOK_PIP_AUDIT.md.
- [x] Idle-timeout sesi 60 mnt (auto-logout) — _app.html script + config.py env knobs + _shared globals.
      Basis interaksi nyata (bukan request → auto-refresh 10s tak mengganggu). Verified via Chrome: warn @58m, reset, logout @60m.
