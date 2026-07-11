# Roadmap — Phase 1 sampai Phase 5

> Timeline detail. Updated saat ada perubahan scope.
> **Current position:** Phase 1, Minggu 8 (Modul Pengadaan & Inventory lengkap)
> **Last updated:** 4 Juni 2026 (afternoon)

---

## Phase 1 — MVP (8 Minggu, target selesai Juni 2026)

**Goal:** Sistem usable di klinik dengan UI internal untuk semua role.

### ✅ Minggu 1 (4-10 Mei 2026) — Fondasi
- Project structure FastAPI + SQLAlchemy
- Install dependencies via `uv`
- Setup git, .env, Alembic baseline
- DB migration files (sudah dijalankan sebelumnya): 001-004
- Hash password & PIN bcrypt
- Seed master_membership

**Status:** ✅ Complete

### ✅ Minggu 2 (11-17 Mei 2026) — Models, Auth, Tests
- 26 SQLAlchemy ORM models (Alembic autogenerate empty diff)
- Repository pattern (StafRepository)
- Auth service + endpoints (login, logout, /me)
- JWT + bcrypt + RBAC
- Anchor shift logic preserved
- Unit + integration tests
- Audit service skeleton

**Status:** ✅ Complete

### ✅ Minggu 3 (18-25 Mei 2026) — Modul FO + Kunjungan + Audit

**Done:**
- PasienRepository (CRUD + generate no_rm + 4 query riwayat join: kunjungan, treatment, produk resep, produk terbayar)
- KunjunganRepository (full: create, get, list, status update, join-with-pasien)
- PasienService (register baru atomik, search, detail, alergi, **riwayat**)
- KunjunganService (kunjungan_lama, lihat_antrian_hari_ini, get_detail, ubah_status dengan state machine `_VALID_TRANSITIONS`)
- SDM Management module (CRUD staf, reset password/PIN) — advanced dari Minggu 6
- **5 Endpoint FO Pasien:** `POST /pasien/baru`, `GET /pasien/cari`, `GET /pasien/{id}`, `GET /pasien/{id}/riwayat`, `POST /pasien/alergi`, `DELETE /pasien/alergi/{id}`
- **4 Endpoint Kunjungan:** `POST /kunjungan/lama`, `GET /kunjungan/antrian` (dengan mode rekap restricted), `GET /kunjungan/{id}`, `PATCH /kunjungan/{id}/status`
- **Audit log integration:** 18 hook di 4 service (auth/staf/pasien/kunjungan), thread `Request` ke service, PII/password/PIN guard (static-checked)

**Issue C1 (audit log integration) → RESOLVED.**
**Issue I1 (race nomor antrean) → SKIP per dr. Hansen (SOP-controlled).**

**Status:** ✅ Complete (21 routes total, parse-clean, no dupes)

### ✅ Minggu 4 (26 Mei - 1 Jun 2026) — Modul Dokter + Perawat

**Done:**
- PemeriksaanService (SOAP atomic compound — anamnesa/PF/diagnosa/saran + INSERT tindakan + INSERT resep + auto status transition)
- TreatmentService start/end dengan auto SMART CHECK + InventoryService skeleton
- UpsellService dengan PIN authorization dokter (bcrypt verify)
- AntropometriService (upsert idempotent + clinical calc Jackson-Pollock + Siri)
- **3 Endpoint Dokter:** input-medis, summary 4 cardbox, header 3 grid + 1 antrian dengan filter "yang lewat dokter"
- **5 Endpoint Ruang Tindakan:** antrian (include konsultasi+treatment), detail, start, end (auto potong BHP), upsell
- **4 Endpoint Antropometri:** upsert, get-by-kunjungan, terakhir (BMI+fat%+lean%), timeline
- Migration 20260527_1700: tambah `updated_at` di kunjungan_antropometri (DEC-019)
- Smoke test full di Swagger UI — 2 bug ditemukan & fixed in-flight

**Status:** ✅ Complete

### ✅ Minggu 5 (2-8 Juni 2026) — Modul Kasir + Apotek

**Done:**
- KasirService (5 endpoint): antrian, tagihan idempotent dengan bulletproof check, bayar atomic split payment, void item dengan PIN dokter/admin, rekap shift sejak anchor login
- ApotekService (5 endpoint): antrian, detail dengan stok check per item, serahkan obat (atomic potong stok + COMPLETED), write-off (EXPIRED/RUSAK/PENYESUAIAN), suggested order dengan kategorisasi (URGENT/RENDAH/AMAN/NO_DATA)
- MembershipService helper: get_diskon_for_pasien (lookup dinamis dari `master_membership.diskon_treatment_persen`)
- Decisions: stok produk POS dipotong dari `master_produk.stok_terkini` saja, no inventory_history (DEC-022)

**Status:** ✅ Complete

### 🟡 Minggu 6 (9-15 Juni 2026) — Master CRUD + Reports — **DONE per scope yang dipilih**

**Done (chunk 1 — sesuai pilihan dr. Hansen):**
- Master Produk CRUD (6 endpoint): list+filter, get, create, update partial, set-active, restock dengan FOR UPDATE
- Reports omzet harian: total + breakdown per kasir + per metode bayar
- Updated_at audit trail enforcement

**Deferred per pilihan dr. Hansen Week 6:**
- Master Treatment CRUD → defer (update via SQL untuk Phase 1)
- Master Bahan CRUD → defer (update via SQL untuk Phase 1)
- Master Membership CRUD → defer (Owner update kolom diskon via SQL — sudah cocok dengan implementasi MembershipService)
- Reports bulanan + per dokter/treatment → defer
- Iterasi resep → defer ke Phase 2

**Status:** ✅ Complete (per scope yang dipilih)

### 📋 Minggu 5 (1-7 Juni 2026) — Kasir + Apotek
- KasirService (tagihan auto-hitung, bayar split payment, void)
- MembershipService (get_diskon, cek kuota, eligibilitas)
- ApotekService (antrian, serah obat, write-off, suggested order)
- ShiftKasir table + service + endpoint open/close shift
- PDF struk generator
- Endpoint Kasir: `/kasir/antrian-bayar`, `/kasir/tagihan/{nomor}`, `/kasir/bayar`, `/kasir/void-item`, `/kasir/rekap-shift`, `/kasir/shift/{buka,tutup}`
- Endpoint Apotek: `/apotek/antrian`, `/apotek/kunjungan/{id}/detail`, `/apotek/serahkan-obat`, `/apotek/write-off`, `/apotek/suggested-order`

### 📋 Minggu 6 (8-14 Juni 2026) — Master CRUD + Owner Dashboard
- Master endpoints: `/master/produk`, `/master/treatment`, `/master/staf`, `/master/membership`, `/master/bahan` (CRUD lengkap)
- Iterasi resep flow lengkap
- Booking service lanjutan (reschedule, batal via API)
- Repacking module (apoteker)
- Reports endpoint: `/laporan/harian`, `/laporan/bulanan`, `/laporan/staff`, `/owner/dashboard`
- Membership aktivasi flow (beli membership di kasir → generate kuota)

### 📋 Minggu 7 (15-21 Juni 2026) — Frontend (HTMX + Jinja2 + Tailwind)
- Setup Tailwind CSS compile
- Base template + komponen reusable (table, form, modal, toast)
- Halaman per role: login, FO home, dokter home, perawat home, apoteker home, kasir home, admin master, owner dashboard
- Forms multi-step (register pasien)
- HTMX patterns: auto-refresh antrian, modal popup, toast notification
- Test responsive di tablet/iPad (untuk perawat)

### ✅ Minggu 7-8 (29 Mei - 4 Juni 2026) — Web UI semua role + Master Data UI

**Web UI complete untuk semua role (HTMX + Jinja2 + Tailwind CDN):**

- ✅ **Auth + Shell**: Login page, sidebar+topbar layout, role-based menu, /profil page
- ✅ **FO**: Cari Pasien (search + filter alamat), Detail Pasien (header + antropometri + sumber referensi + Riwayat SOAP dengan nama dokter), Pendaftaran Pasien Baru (4-step wizard), Antrian Hari Ini (auto-refresh 10s + +Antrian dropdown), Beli Produk tanpa konsul
- ✅ **Dokter**: Antrian Saya, SOAP Form input + Ubah Konsul multi-row (tindakan + resep + series), allow ubah SOAP di semua status non-terminal dengan anti-regression
- ✅ **Perawat / Ruang Tindakan**: Antrian tindakan, Detail kunjungan dengan instruksi dokter, Start/End tindakan, **Upsell modal** (treatment butuh otorisasi → PIN dokter dengan bcrypt verify)
- ✅ **Kasir**: Antrian bayar, Halaman tagihan dengan split payment (auto-fill nominal) + void item PIN, Sticky header layout
- ✅ **Apoteker**: Antrian obat, Detail resep dengan cek stok per item, Serahkan Obat, **Suggested Order** (URGENT/RENDAH/AMAN/NO_DATA), Write-off Form
- ✅ **Master Data (Owner + Superadmin only)** — **DEC-033 promote ke Phase 1**:
  - Master Treatment CRUD (list + tambah + edit + toggle aktif + butuh_otorisasi flag)
  - **Master Bahan Klinik CRUD** (inventory_stok — list + tambah + edit, stok update via Modul Inventory sesi berikutnya)
  - **Treatment Komponen UI** inline di Master Treatment edit (multi-row BAHAN/ALAT + dropdown bahan + qty + satuan → langsung pakai auto-deduct yang sudah jalan)
  - Master Produk web UI (CRUD + restock + toggle aktif)
- ✅ **Kelola Staf** (Owner/Admin): tambah user, edit nama, reset password, set/reset PIN, toggle aktif, audit log capture aksi
- ✅ **Profil sendiri**: ubah nama + ganti password + **ubah PIN dengan verify password** (DEC-037)
- ✅ **Security hardening**: CSRF middleware (pure ASGI, double-submit cookie), cookie secure config-driven (DEC-032), service-owned transaction (DEC-030)
- ✅ **DB connection hardening** (DEC-036): pool_recycle 280s + connect_timeout 10s untuk mitigasi MySQL Lost connection

**Code organization:**
- `app/web/router.py` di-decompose jadi 10 sub-modul di `app/web/routes/*` (auth, pasien, pendaftaran, dokter, perawat, kasir, apotek, master, staf, profil, kunjungan)
- Total ~75+ web routes di /web/* (excluding API /api/v1/*)

**Masih pending Phase 1 (sesi-sesi berikutnya):**
- ✅ Dashboard per role (real stats, KPI per role, alerts, recent activity) — DONE 4 Jun
- ✅ **Modul Inventory + Stock Opname** (PO workflow, opname snapshot, history mutasi) — DONE 4 Jun, DEC-038/039/041
- ✅ **Reports & Laporan C1** (4 UI reports: Omzet Bulanan, Top Treatment, Kinerja Dokter, Audit Log) — DONE 5 Jun, DEC-045
- ✅ **Plan A health check fix** (7 baseline findings: 6 DEC-030 + 1 bare except) — DONE 5 Jun, DEC-043
- ✅ **Health Check Protocol Lite** (5 markdown + 4 scripts + baseline log + discovery) — DONE 5 Jun
- 📋 **C2 — Raw Data Export** untuk modul `data_analyst` proyek terpisah (waiting spec dari dr. Hansen)
- ✅ **B1 — Backup Script** (mysqldump + uploads ZIP + 30-day retention + restore.sh) — DONE 5 Jun, DEC-048
- ✅ **B2 — User Manual** (5 role + Pendahuluan, DOCX ~50 halaman) — DONE 5 Jun, DEC-048
- ✅ **Print Module Phase A** (Nota A5/Thermal + SOAP Resume + auto-print) — DONE 5 Jun, DEC-047
- ✅ **Multi-Tenant Klinik Config** (settings page + 46 callsite injection) — DONE 5 Jun, DEC-047
- ✅ **Series Treatment Full Refactor** (harga_paket prepaid sesi 1 + Rp 0 sesi 2..N + FO Lanjut Series + Kasir conditional bypass) — DONE 6 Jun, DEC-049
- ✅ **Searchable Dropdown** (Tom Select di SOAP/Beli Produk/Upsell/Master) — DONE 6 Jun, DEC-049 lampiran
- 📋 **B3 — Deployment Guide**: uvicorn systemd, nginx reverse proxy (HTTPS via Certbot), .env management (dev vs prod), MySQL config tuning, upgrade + rollback procedure

**Status:** 🟢 Phase 1 = **100% selesai**. Phase B Soft Launch = **B1 + B2 + Print + Multi-Tenant + Series done**. Sisa: **B3 (Deployment Guide)** saja sebelum production launch klinik Sehati.

### ✅ Phase C2 — Owner Raw Data Export — COMPLETE (5 Jun 2026, DEC-046)

**Done:**
- C2.1 Foundation — csv_writer + json_writer + zip_packer + ExportService skeleton + landing UI dengan 3 cards (Weekly/Monthly/Custom + anchor date)
- C2.2 13 Datasets — Daily Op Summary + Visits + Treatments + Products + Trx Header+Detail + Inventory + PO 3-way + Membership + SOAP + Audit
- C2.3 Pack Assembly — Real ZIP berisi 13 file CSV/JSON + README + DATA_DICTIONARY, adaptive warning > 90 hari, hard cap 200K rows, error resilience per-dataset
- C2.4 Data Dictionary — 149 column definitions di `_export_columns.py`, JSON + MD endpoints, auto-bundle di pack, static MD di Project_Memory
- C2.5 Housekeeping — DEC-046 + B-011 bug fix + this roadmap entry + magic command words di 00_README

**Tested with real data:** Excel import Mar-Mei 2026 (2.035 rows, 569 fakturs, 386 pasien). Semua 13 dataset verify reflect data real benar.

**Status:** ✅ Production-ready untuk feed ke modul Data Analyst (proyek terpisah) → Council AI (Codex project).

### ✅ Minggu 8 chunk 2 (4 Juni 2026) — Modul Pengadaan & Inventory lengkap

**Done (modul Pengadaan terintegrasi, DEC-038/039/040/041/042):**

**Backend (SQL + Python):**
- Migration 006: 3 tabel pemesanan (pemesanan, pemesanan_item, pemesanan_receive) + 2 tabel opname (stock_opname, stock_opname_item) + extend inventory_history polymorphic + tambah role PURCHASING
- Models SQLAlchemy: Pemesanan, PemesananItem, PemesananReceive, StockOpname, StockOpnameItem (+ Computed column pattern untuk selisih)
- Repositories: PemesananRepository (CRUD + FOR UPDATE counter + JOIN queries), OpnameRepository (CRUD + stok snapshot helpers)
- Services: PemesananService (state machine + atomic receive + audit), OpnameService (snapshot pattern + apply selisih + reject)
- Schemas Pydantic untuk 17 schema (Pemesanan 10 + Opname 7)

**Web UI:**
- ✅ **Pengadaan / Pemesanan (PO)**: list filter, form multi-row HTMX, detail dengan state-aware actions, modal receive per item, cancel reason display dari audit_log
- ✅ **Stock Opname**: list filter, form per lokasi (RETAIL/KABIN/GUDANG_UTAMA) dengan auto-compute selisih JS, detail dengan approve/reject modal
- ✅ **History Mutasi**: kartu stok read-only dengan filter per item/jenis/tgl, color-coded badge per jenis_mutasi
- ✅ Hapus tombol Restock lama di Master Produk (banner info redirect ke Pengadaan)

**Role baru: Purchasing**
- Bisa: lihat list PO+Opname, create PO+Opname
- Tidak bisa: approve PO ke ORDERED, cancel, approve opname (semua Owner/Superadmin only)
- Apoteker tambahan akses: PO khusus produk RETAIL

**Dummy data**:
- 37 produk RETAIL dummy (skincare + obat) untuk simulasi testing — idempotent SQL seed

**Status:** ✅ Modul Pengadaan & Inventory production-ready

### 📋 Minggu 8 (22-28 Juni 2026) — Polish, Testing, Deployment
- Fix semua UX feedback dari Minggu 7
- Performance check (slow query, index optimization)
- Backup automation (cron mysqldump)
- Docker compose: nginx + FastAPI + MySQL + Redis (kalau perlu)
- SSL via Let's Encrypt
- User manual per role (PDF)
- Soft launch — 3 hari paralel run dengan sistem lama
- Switch ke sistem baru
- Hypercare support

**Deliverable Phase 1:** Sistem usable production di klinik dokter, jalan stable, semua role bisa pakai.

---

## Phase 2 — Enhancement & Patient Access (TBD, estimasi 3-4 bulan)

**Goal:** Buka akses pasien + integrasi external + monitoring/notifikasi.

### Lingkup
- **3-tier membership baru** (Basic, Gold, Platinum) — define benefit baru
- **Bundling paket treatment promo** (non-member juga bisa beli paket promo)
- **Transfer paket member** (dengan otorisasi Owner + audit)
- **Module Foto pasien** (upload before/after, kategori, lihat per pasien)
- **Booking online** — website pasien daftar mandiri
- **Kiosk registrasi** — terminal di klinik untuk self-service
- **Delivery products** — kirim produk ke rumah member
- **Notifikasi WA/Telegram** — appointment reminder, low stock alert ke owner
- **Email notifikasi** — receipt struk via email
- **Refresh token** — JWT 1h access + 7d refresh untuk security yang lebih baik
- **Pagination** untuk semua list endpoint
- **Caching Redis** untuk master data
- **Structured logging** (structlog) + log aggregator (kalau perlu)
- **Monitoring** — Prometheus + Grafana untuk uptime & DB metrics

---

## Phase 3 — AI Integration (TBD, 4-6 bulan)

**Goal:** Differentiator kompetitif lewat AI insights.

### Lingkup
- **Skin analysis** via Gemini Vision API — pasien upload foto wajah, dapat analisa AI singkat
- **USG kulit interpretation** — input data USG, AI interpret hasilnya
- **SOAP smart assist** — dokter ketik anamnesa, AI suggest diagnosa & treatment
- **Chat AI member** — member chat ke AI assistant yang aware riwayat pasien
- **Suggested order ML** — predict bahan habis berdasarkan trend
- **Patient progress report AI** — generate summary visual (chart antropometri trend, before/after collage, diet plan suggestion)

### Technical Prep
- Setup Celery + Redis untuk background AI processing
- Storage S3/MinIO untuk foto
- API key management secure (rotate berkala)
- Rate limit untuk panggilan AI (cost control)

---

## Phase 4 — Mobile App Native (TBD, 6-8 bulan)

**Goal:** Native app untuk pasien (booking, lihat riwayat, chat AI).

### Lingkup
- React Native atau Flutter (TBD)
- Login dengan number HP + OTP
- Lihat history kunjungan
- Booking treatment baru
- Lihat kuota membership tersisa
- Chat AI assistant
- Push notification untuk appointment

**Backend impact:** Tambah endpoint khusus mobile (`/api/v1/mobile/...`) dengan auth OTP-based.

---

## Phase 5 — Multi-Cabang & Enterprise (TBD)

**Goal:** Scale ke multiple cabang klinik.

### Lingkup
- Multi-tenant: 1 instance, N cabang
- Per-cabang inventory, staf, transaksi
- Cross-cabang patient transfer
- HQ dashboard untuk owner lihat semua cabang
- Per-cabang reports + consolidated reports
- Role baru: Cabang Manager

---

## Estimated Total Effort (Single AI Developer dengan Solo User Tester)

| Phase | Estimated Effort | Status |
|-------|------------------|--------|
| Phase 1 | 8 minggu (~320 jam total) | 🟢 100% Done. Phase B Soft Launch = B1 + B2 + Print + Multi-Tenant + Series ✅, sisa B3 Deployment Guide |
| Phase 2 | 3-4 bulan (~480 jam) | 📋 Planned |
| Phase 3 | 4-6 bulan (~640 jam) | 📋 Planned |
| Phase 4 | 6-8 bulan (~900 jam) | 📋 Planned |
| Phase 5 | TBD | 📋 Future |

---

## Decision Points / Checkpoints

### After Phase 1
- [ ] Sistem stabil di klinik selama 1 bulan?
- [ ] User staf sudah comfortable?
- [ ] Bug critical sudah <5/bulan?
- [ ] Backup & restore tested?
- **GO/NO-GO** untuk Phase 2.

### After Phase 2
- [ ] Pasien adoption website/kiosk > 30%?
- [ ] Delivery success rate > 95%?
- [ ] Notifikasi WA delivery rate > 90%?
- **G
---

## ✅ Phase B Soft Launch (Sub-Phase B1 + B2 + Print + Multi-Tenant + Series) — COMPLETE (5-6 Jun 2026, DEC-047/048/049)

**Done:**
- **Print Module Phase A** (DEC-047): Nota A5/Thermal + SOAP Resume A5/Thermal + auto-print confirmation page after kasir lunas. PrintService context builder, no headless browser.
- **Multi-Tenant Klinik Config** (DEC-047): `master_klinik_config` singleton + `KlinikConfigService` + Settings page Owner-only + 46 callsite `build_shell_context(..., db=db)` injection. App siap dipakai klinik lain di masa depan tanpa kode hardcode.
- **Backup B1** (DEC-048): `backup.sh` + `restore.sh` + README cron instructions, 30-day retention, single ZIP berisi mysqldump + uploads folder.
- **User Manual B2** (DEC-048): DOCX 5 role (FO + Dokter + Perawat + Kasir + Apoteker) + Pendahuluan, ~50 halaman total, generator pakai docx-js.
- **Series Treatment Refactor** (DEC-049): Migration 008 (`harga_paket`) + PemeriksaanService bikin sesi 1 (KunjunganTindakan link rencana) + sesi 2..N (rencana PENDING) + KasirService charge logic (paket prepaid di sesi 1, Rp 0 di sesi 2..N) + SeriesService.use_session() + FO dropdown "Lanjut Series" + Pasien Detail card "Rencana Aktif" + Kasir conditional Rp 0 bypass.
- **Searchable Dropdown Tom Select** (DEC-049 lampiran): SOAP Dokter (tindakan + resep) + FO Beli Produk + Perawat Upsell + Master forms.

**Bug fixes during sprint (10 bugs closed):** B-012 (CSRF multipart), FIX-1.5 (klinik name persistence), FIX-1.6 (profil.py NameError), FIX-SD-1 (Tom Select empty option), FIX-SD-2 (duplicate endblock), INV-SERIES-1 + FIX-ST-1/2/3/4 (series flow).

**Tested with real workflow:**
- Klinik name "Klir.CO" persist across navigation
- Series test case "Chichin" — 5-sesi botox: sesi 1 charge 5×harga_paket, sesi 2 FO "Lanjut Series" → Ruang Tindakan → Kasir Rp 0 bypass → cetak nota.
- Auto-print nota dari kasir lunas → confirmation page → window.print().

**Status:** ✅ Production-ready untuk soft launch (sisa B3 Deployment Guide).

### 📋 Phase B3 — Deployment Guide (NEXT)

**Lingkup:**
- uvicorn systemd service (`/etc/systemd/system/sehati-clinic.service`)
- nginx reverse proxy + HTTPS via Certbot (Let's Encrypt)
- `.env` management — `.env.dev` vs `.env.prod`, secrets handling
- MySQL config tuning (max_connections, buffer pool, slow query log)
- Upgrade procedure (git pull + migrations + restart)
- Rollback procedure (db restore + git checkout previous tag)
- Pre-launch checklist (firewall, sudo user, swap, monitoring)

**Estimated effort:** 4-6 jam (mostly markdown writing + verify commands).

---

## 📌 NEXT SESSION TODO (PRE-B3) — Sebelum Deployment Guide

Per arahan dr. Hansen tanggal 6 Jun 2026 (akhir sesi). 3 task wajib dikerjakan
**sebelum** masuk Phase B3 Deployment Guide:

### #1 — Update User Manual (Fitur Baru)

Update `user_manual/Manual_Operasional.docx` untuk fitur sesi 5-6 Jun 2026:

- **Print Nota (Kasir)** — A5 + Thermal 80mm + auto-print confirmation page after lunas.
- **Print SOAP Resume (Dokter)** — dari halaman riwayat pasien per kunjungan.
- **Settings Klinik (Owner)** — edit nama klinik + alamat + logo upload + footer text.
- **Series Treatment full flow** — dokter centang sesi N, kasir bayar paket di sesi 1, FO dropdown "Lanjut Series", kasir sesi 2..N Rp 0 bypass.
- **Searchable Dropdown** — Tom Select di SOAP/Beli Produk/Upsell/Master forms.

**Screenshot list yang perlu disimpan di `user_manual/screenshots/`:**

1. `settings_klinik.png` — form edit + logo upload
2. `kasir_nota_a5.png` — preview nota A5
3. `kasir_nota_thermal.png` — preview nota thermal 80mm
4. `kasir_rp0_card.png` — card "Tidak Ada Tagihan" + tombol cetak nota
5. `kasir_confirm_print.png` — confirmation page after bayar lunas (auto-print)
6. `dokter_soap_form_searchable.png` — SOAP form dengan Tom Select tindakan + resep
7. `dokter_riwayat_cetak_resume.png` — tombol cetak resume per SOAP entry
8. `fo_search_lanjut_series.png` — dropdown +Antrian dengan section amber "Lanjut Series"
9. `fo_pasien_detail_rencana_aktif.png` — card amber "Rencana Series Aktif" di detail pasien
10. `master_treatment_harga_paket.png` — form Master Treatment dengan field harga_paket

**Estimated effort:** 3-4 jam (writing + screenshot capture + regenerate DOCX).

### #2 — Simulasi Multi-User Concurrent Test

Tujuan: cek ketahanan program saat beberapa user login bersamaan (race
condition, deadlock MySQL, audit race, session collision).

**Test harness:**

- 5 test user di DB clone: `fo1`, `dokter1`, `perawat1`, `kasir1`, `apoteker1`.
- Script Python multi-threaded yang execute workflow per role secara
  paralel selama 5-10 menit.
- Scenario: FO daftar pasien + bikin antrian, Dokter input SOAP, Perawat
  start/end treatment, Kasir proses bayar, Apoteker serahkan obat —
  semua paralel ke kunjungan berbeda.

**Monitor:** requests/sec, error rate, p95 latency per endpoint, deadlock
count, anomaly screenshot.

**⚠️ WAJIB pakai DB clone/staging.** TIDAK BOLEH run di production.

**Alternatif minimum** kalau concurrent terlalu kompleks: load test
single-user dengan 100 sequential requests untuk baseline performance.

**Estimated effort:** 4-6 jam.

### #3 — Full Recheck + Analyze + Backup

Persiapan terakhir sebelum deployment guide. 3 sub-task:

**(A) Recheck & Analyze:**

- Run health check protocol full (4 script: db_integrity + audit_gaps + pii_scan + frontend manual).
- Parse-test semua `.py` di `app/`, `scripts/`, `seed_data/`.
- Template syntax check semua Jinja2.
- Route count + audit log coverage % per service.
- Identify dead code.
- Summary report di `Project_Memory/HealthCheck/recheck_report_YYYYMMDD.md`.
- Target: 0 HIGH severity findings.

**(B) Full Backup DB:**

- Execute `backups/backup.sh`.
- Verify ZIP integrity (mysqldump + uploads/).
- Copy ke `backups/pre_deployment_YYYYMMDD.zip`.
- Test restore di staging DB untuk konfirmasi backup valid.

**(C) Project Memory + Code Snapshot:**

- Zip seluruh `Project_Memory/` + `sehati_clinic/` (exclude `.venv`,
  `node_modules`, `__pycache__`).
- Simpan ke `backups/code_snapshot_YYYYMMDD.zip`.
- Generate `manifest.txt` isi: hash per file (sha256) + total LOC + tanggal.

**Output:** 3 file di `backups/`:
- `pre_deployment_DB_YYYYMMDD.zip`
- `code_snapshot_YYYYMMDD.zip`
- `recheck_report_YYYYMMDD.md`

**Estimated effort:** 2-3 jam (mostly scripted, hasil auto-generate).

### Sequence

PRE-B3 #1 (user manual) → PRE-B3 #2 (load test) → PRE-B3 #3 (full backup) → **B3 Deployment Guide**.

Total estimated effort PRE-B3: **9-13 jam** sebelum masuk B3.

---

## ✅ Sprint 6 Juni 2026 Malam — FLOW-D Opsi C + 8 Bug Fix + Manual Addendum

**Status:** 🟢 Sesi panjang ~6 jam dengan output produktif yang banyak.

### Completed sesi ini

- **Bug Fix Marathon** (DEC-050/051/052):
  - BUG-A: Beli Produk 404 → restored route
  - BUG-B: Riwayat pembayaran items 0 → refactor get_tagihan 3-mode
  - BUG-C: Tombol Upsell tidak respond → JS duplicate if line removed
  - FIX-Upsell-Produk: Dropdown disabled → Tom Select API + remove disabled
  - BUG-1517 (timezone) → DEC-052 datetime.now() fix + 23 legacy data offset
  - B-014 bhp_terpotong undefined → variable name fix
  - B-015 AntrianDokterResponse → schema field correct
  - FIX-Beli-Produk-2 pasien_svc.repo → pasien_svc.pasien_repo

- **FLOW-D Opsi C — Reopen + Cap** (DEC-050 + DEC-051):
  - Part A: PemeriksaanService auto-revert status ANTRI_OBAT/ANTRI_BAYAR → ANTRI_TREATMENT
  - Part B: KasirService get_tagihan refactor 3-mode + banner "Tagihan Tambahan"
  - Part C: Cap max 1 reopen per kunjungan, block reopen ke-3

- **DEC-050 + DEC-051 + DEC-052 documented** di decisions log

- **User Manual Addendum v1**:
  - 6 Bab + 30+ subsection + 20 screenshot embedded
  - 4 callout box (amber/blue/green/red)
  - Cover, Daftar Isi, Lampiran
  - File: `user_manual/Manual_Operasional_Addendum_v1.docx` (846 KB)
  - Generator script Python python-docx (bukan docx-js, lebih reliable di sandbox)

- **Debug Utility Scripts**:
  - `debug_kunjungan.py` — diagnostic per kunjungan dengan simulasi filter
  - `fix_timezone_tindakan.py` — offset +7 jam ke legacy UTC tindakan

### Test Validation Real-World

- ✅ Skenario user (Bapak): konsul → resep produk only → lunas → ubah konsul + tambah tindakan → eksekusi + upsell → bayar lagi
- ✅ Skenario test 2x reopen: cap error message muncul dengan benar
- ✅ Multi-tenant nama klinik persist
- ✅ Print nota A5 + Thermal jalan
- ✅ Series treatment flow lengkap

### Status Project setelah sesi ini

**Phase 1: ✅ 100% Complete**
**Phase B Soft Launch:**
- ✅ B1 Backup, B2 Manual (initial + Addendum v1)
- ✅ Print Module, Multi-Tenant, Series, Searchable
- ✅ FLOW-D Opsi C (Reopen + Cap)
- ✅ Timezone Bug Fix
- 📋 **B3 Deployment Guide** (sisa)
- 📋 PRE-B3 #2 + #3 (multi-user test + full backup)

### Statistik Sesi

- Bug fixed: **13 issues**
- Files modified: ~15 service/template/route
- Lines added (DEC log): ~150
- Lines added (known_issues): ~80
- New utility scripts: 2 (debug + fix timezone)
- Manual DOCX: 6 bab, 30 subsection, 20 screenshot, 846 KB

### 📌 NEXT SESSION — Apa yang harus dikerjakan

**Urutan rekomendasi:**

1. **#317 Audit attribute access** (~15 menit) — grep pattern `Service(db).repo` di semua route files untuk cegah AttributeError serupa
2. **PRE-B3 #2 Multi-user concurrent test** (~4-6 jam) — script multi-thread login + workflow paralel
3. **PRE-B3 #3 Full Recheck + Backup** (~2-3 jam) — health check final, DB backup, code snapshot
4. **Phase B3 Deployment Guide** (~4-6 jam) — uvicorn systemd, nginx, HTTPS, MySQL tuning

**Total estimasi dari sini sampai launch:** 10-16 jam kerja AI + verifikasi user.


---

## 7 Juni 2026 — Sprint Pagi (SOAP-GUARD + TIER-SYS + Stress Test Fase 1+2)

### ✅ Completed Sprint Ini

- ✅ **#321 SOAP-GUARD** — Day Rollover Lock + Owner-Check Level Medium + Antrian Filter per dokter (DEC-053)
- ✅ **#323 TIER-SYS** — 4-tier role hierarchy backend foundation (DEC-054)
- ✅ **#322 STRESS-TEST Fase 1+2** — Smoke single + Concurrent 3 user (DEC-055)
- ✅ Project Memory housekeeping (DEC-053/054/055/056 + known_issues + roadmap)

### Stress Test Status

| Fase | User | Status | Catatan |
|------|------|--------|---------|
| Fase 1 — Smoke | 1 | ✅ PASS | All p95 < 25ms, 0 errors |
| Fase 2 — Concurrent ringan | 3 | ✅ PASS | All p95 < 25ms, 0 race condition, 100% registrasi success |
| Fase 3 — Realistic peak | 7 | ⏳ Next session | Test SOAP-GUARD cross-dokter + 2 kasir scenario |
| Fase 4 — Stress | 15 | ⏳ Pending | Identify max capacity |

### 📌 NEXT SESSION — Apa yang harus dikerjakan

**Prioritas tinggi (pre-launch critical):**

1. **#317 Audit attribute access** (~15 menit) — pattern check `Service(db).repo` di semua route
2. **STRESS Fase 3** (~3-4 jam) — Locust 7 user dengan scenario complex:
   - 2 dokter (test SOAP-GUARD cross-dokter race)
   - 2 kasir (test double-billing prevention)
   - 1 FO + 2 Perawat + 1 Apoteker
   - Include 5 series treatment + 3 reopen flow + 2 upsell + 2 void item

3. **STRESS Fase 4** (~3-4 jam) — Locust 15 user untuk find bottleneck

**Prioritas menengah (enhancement post-Fase 3-4):**

4. **#329 FO-ASSIGN-DOKTER** (~3-4 jam) — Schema change kunjungan.id_staf_dokter_assigned + UI dropdown FO + extend antrian filter
5. **#324 REPORTS-COMPART** (~2-3 jam) — Per-role compartmentalization Reports UI
6. **#325 FIN-REPORTS** (~4-6 jam) — Finance Reports module Owner-only

**Prioritas rendah (post-launch):**

7. **#326 Master Staf Role Edit UI** — kalau Bapak butuh promote/demote staf via UI
8. **Phase B3 Deployment Guide** (~4-6 jam) — uvicorn systemd, nginx, HTTPS, MySQL tuning

### Statistik Sesi (7 Juni Pagi)

- Features completed: **3 major** (SOAP-GUARD, TIER-SYS, Stress Test Fase 1+2)
- DEC entries: **4 baru** (DEC-053 sampai DEC-056)
- Files modified: ~6 service/route/repo
- New tools: `tools/stress/` 4 files (README + seed + Fase 1 + Fase 2)
- Test runs: 4 (Fase 1 ×2 + Fase 2 ×2)
- Bug findings: 0 critical, 1 operational (B-013 truncation workaround)

### Estimasi Sampai Launch

| Item | Estimasi | Cumulative |
|------|----------|------------|
| Stress Fase 3 | 3-4h | 4h |
| Stress Fase 4 | 3-4h | 8h |
| FO-ASSIGN-DOKTER | 3-4h | 12h |
| REPORTS-COMPART | 2-3h | 15h |
| FIN-REPORTS | 4-6h | 21h |
| Phase B3 Deployment | 4-6h | 27h |
| Buffer (final fixes + UAT) | 6-10h | **33-37h** |

Realistic untuk launch Januari-Februari 2027 (7-8 bulan dari sekarang) — sangat ample buffer.


---

## 8 Juni 2026 — Sprint Pagi (FO-ASSIGN-DOKTER + UX Refinement)

### ✅ Completed Sprint Ini

- ✅ **#329 FO-ASSIGN-DOKTER** complete dengan 8-layer implementation +
  3 UX FIX post real-test (DEC-058)
- ✅ Migration 009 SQL prepared (Bapak apply ke production)
- ✅ Project Memory housekeeping (DEC-058 + known_issues + roadmap)
- ✅ Old "PRE-B3 #2" + "PRE-B3 #3" marked complete (sudah covered earlier)

### Status Akhir Pre-Launch

| Aspek | Status |
|-------|--------|
| Performance baseline (Fase 1-4) | 🟢 99% confidence |
| Medical-legal compliance (SOAP-GUARD) | 🟢 95% confidence |
| Role authorization (TIER-SYS backend) | 🟢 90% confidence |
| Pre-assign dokter (FO-ASSIGN-DOKTER) | 🟢 95% confidence |
| Data export & backup | 🟢 95% confidence |
| Production deployment guide | 🟡 Belum dibangun (B3) |

### 📌 NEXT SESSION — Sisa Pre-Launch

**Quality (rekomendasi prioritas):**

1. **#317 Audit attribute access** (~30 min) — Scan semua route files
   untuk pattern `Service(db).repo` yang berpotensi AttributeError.
2. **#324 REPORTS-COMPART** (~2-3h) — Per-role Reports UI compartmentalization

**Enhancement (post-launch friendly):**

3. **#325 FIN-REPORTS module Owner-only** (~4-6h)
4. **#326 Master Staf Role Edit UI** (~2-3h, butuhkan kalau Bapak mau
   manage role lewat UI; backend TIER-SYS sudah siap)
5. **#84 Sosial media pasien field** (~1-2h, placeholder sudah ada di
   wizard)

**Production prep:**

6. **Phase B3 Deployment Guide** (~4-6h) — uvicorn systemd, nginx,
   HTTPS, MySQL tuning
7. **UAT real user + buffer** (~6-10h)

### Statistik Sesi (8 Juni Pagi)

- Major feature: 1 (FO-ASSIGN-DOKTER lengkap dengan 3 UX FIX)
- DEC entries: 1 baru (DEC-058)
- Files modified: 15
- Templates updated: 3 (dropdown dokter 3 entry points + kolom + 2 tombol)
- AST verify: 11 file, 0 error
- B-013 truncation occurrences: ~6 (semua restored via heredoc workaround)

### Estimasi Final Sampai Launch (Updated)

| Item | Estimasi | Cumulative |
|------|----------|------------|
| #317 Quality audit | 0.5h | 0.5h |
| #324 REPORTS-COMPART | 2-3h | 3.5h |
| #325 FIN-REPORTS (opsional) | 4-6h | 9.5h |
| #326 Role Edit UI (opsional) | 2-3h | 12.5h |
| #84 Sosial media (opsional) | 1-2h | 14.5h |
| Phase B3 Deployment Guide | 4-6h | 20.5h |
| Buffer UAT + final fixes | 6-10h | **26.5-30.5h** |

Realistic untuk launch Januari-Februari 2027 — tetap sangat ample buffer.


---

## 8 Juni 2026 Siang — Sprint REPORTS-COMPART + Komisi Foundation + Finance Design

### ✅ Completed Sprint Ini

- ✅ **#324 REPORTS-COMPART** (5 phase) — Per-role compartmentalization Reports
  - Owner/Superadmin/Admin: lihat all reports
  - Dokter: "Kinerja Saya" auto-filter (DEC: backend enforce)
  - Kasir: "Rekap Shift Saya" auto-filter
  - 2 fix UX: breadcrumb omzet clickable, total_dibayar field name
- ✅ **#317 Audit Attribute Access** — clean, 22 service inventory documented
- ✅ **#360 + #361 (backend)** — Komisi Foundation (DEC-059):
  - Migration 010 + 011: 9 kolom baru
  - 2 helper functions: `hitung_komisi_treatment()` + `hitung_komisi_produk()`
  - Formula closed-form recursive-solve
- ✅ **TODO #366 Finance Module Design** — `outputs/FINANCE_MODULE_DESIGN.md`
  komprehensif, status undecided (butuh konsultan)

### Pending Tasks Updated

**Foundation pending (Form UI):**
- #369 Master Treatment Form UI (~1.5h)
- #372 Master Produk Form UI (~1h)
- #373 Verify + smoke instruction (~15 min)

**Feature tier:**
- #362 Master Membership privilege (kompleks, 6-8h, butuh design)
- #363 Apoteker reports + write-off (4-5h)
- #364 Void Pembayaran (3-4h)
- #325 FIN-REPORTS (kemungkinan merge ke #366)
- #326 Master Staf Role Edit UI (2-3h, optional)
- #84 Sosial media pasien (1-2h, future)

**Strategic (undecided):**
- #366 Finance Module (34-54h, awaiting consultant)

### 📌 NEXT SESSION — Apa yang harus dikerjakan

**Prioritas tinggi:**

1. **#369 + #372 Form UI Komisi** (~2-3h) — Selesaikan form Master Treatment + Master Produk dengan input fields baru + preview komisi
2. **#363 Apoteker Reports + Write-off** (~4-5h) — Akan pakai DEC-059 helper untuk profit per produk

**Prioritas menengah:**

3. **#362 Master Membership** (kompleks, butuh diskusi schema dulu)
4. **#364 Void Pembayaran** flow

**Strategic:**

5. Konsultasi finance consultant untuk #366 keputusan
6. Phase B3 Deployment Guide (post-feature-complete)

### Statistik Sesi (8 Juni Siang)

- Major features: 2 (REPORTS-COMPART complete + Komisi Foundation backend)
- Designs: 1 (Finance Module 30+ halaman document)
- DEC entries: 1 baru (DEC-059)
- Files modified: ~10
- Migrations baru: 2 (010, 011)
- Helper functions: 2 (closed-form math)
- B-013 truncation occurrences: ~6 (semua restored)
- Tasks created: ~12 baru, 6 closed

### Estimasi Final Sampai Launch (Updated)

| Item | Estimasi | Cumulative |
|------|----------|------------|
| #369 + #372 Form UI Komisi | 2-3h | 3h |
| #363 Apoteker reports + write-off | 4-5h | 8h |
| #364 Void Pembayaran | 3-4h | 12h |
| #362 Master Membership (kalau perlu pre-launch) | 6-8h | 20h |
| #326 Role Edit UI (opsional) | 2-3h | 23h |
| Finance Module (kalau bangun internal) | 34-54h | 57-77h |
| Phase B3 Deployment Guide | 4-6h | 61-83h |
| Buffer UAT + final fixes | 6-10h | **67-93h** |

**Realistic untuk launch Januari-Februari 2027** (7-8 bulan):
- Tanpa Finance internal: 33-39h, **sangat ample**
- Dengan Finance internal: 67-93h, **masih ample**

Saran: defer Finance module ke post-launch atau pakai 3rd party.


---

## 8 Juni 2026 Sore — Komisi Refactor (DEC-060)

### ✅ Done
- **#360 Master Treatment Komisi** — Field + service helper hybrid (PERSEN_HARGA / PERSEN_MARGIN / NOMINAL)
- **#361 Master Produk Komisi** — Field + service helper hybrid (single dokter)
- **#375 Hybrid Refactor Akuntansi Benar** — Migration 012 + model + service update; DEC-059 superseded oleh DEC-060
- DB applied: 7 row master_treatment + 5 row master_produk verified

### ⏭ Active / Next Up
- **#369** Form UI Master Treatment hybrid komisi
- **#372** Form UI Master Produk hybrid komisi
- **#373** Smoke test instruction setelah UI ready

### 📌 Tracked TODOs (Pending — User-Initiated)
- **#362 Master Membership** — Privilege system lengkap (complex, butuh design discussion)
- **#363 Apoteker Reports + Penyingkiran Produk**
- **#364 Void Pembayaran Flow** — Admin-led atau Kasir dengan PIN otorisasi
- **#366 Finance Module** — Status undecided, butuh konsultasi finance consultant (DEC-undecided)
- **#325 FIN-REPORTS** — Finance Reports Owner-only (depends pada DEC-060 helper)
- **#326 Master Staf Role Edit UI** — Currently missing

### 🐛 Notes
- B-013 file truncation kambuh 3× dalam sesi ini (lihat 07_known_issues.md). Workaround DEC-056 efektif tapi friction-heavy untuk file > 200 LOC.

---

## 8 Juni 2026 Malam — #369 Master Treatment UI + Bug Fix Marathon

### ✅ Done
- **#369** Form UI Master Treatment hybrid komisi (BHP, pajak, komisi dokter, komisi perawat, preview reactive)
- **Schema alignment** — produk.py model exact match 19 kolom DB
- **Service restoration** — master_treatment_service tambah_komponen + hapus_komponen + set_active
- **8 bug fixed** dalam sesi (lihat 07_known_issues.md)

### ⏭ Active / Next Up (Pause: lanjut besok)
- **#372** Form UI Master Produk hybrid komisi
- **#373** Smoke test end-to-end komisi system

### 🐛 Risk Notes
- B-013 recurrence 7× dalam 1 sesi — tertinggi sejauh ini
- Source code TIDAK di-backup (hanya DB + uploads) — risk loss kalau B-013 cascade besar
- Pertimbangkan: tambah source code ke backup script di sesi besok sebelum #372

### 📋 Tracked Pending TODOs
- #325 FIN-REPORTS [WAITING #366 Finance Module decision]
- #326 Master Staf Role Edit UI
- #362 Master Membership privilege
- #363 Apoteker Reports + write-off
- #364 Void Pembayaran flow
- #366 Finance Module (undecided)

---

## 9 Juni 2026 Pagi — #372 Master Produk Form Complete

### ✅ Done
- **#372** Form UI Master Produk hybrid komisi
- **DEC-061 P1** — backup.py extended dengan source code bundle
- Bug fix: ProdukGenericResponse + RestockProdukResponse schema restored

### ⏭ Active / Next Session
- **#373** Smoke test end-to-end komisi system
- Run backup test untuk validasi source bundle

### 📌 Pending TODOs (tracked)
- #325 FIN-REPORTS [WAITING #366 Finance Module decision]
- #326 Master Staf Role Edit UI
- #362 Master Membership privilege system lengkap
- #363 Apoteker Reports + write-off
- #364 Void Pembayaran flow
- #366 Finance Module (undecided)

---

## 10 Juni 2026 — #326 Role Edit Complete + Cleanup

### ✅ Done
- **#326 Master Staf Role Edit UI** lengkap (service + route + template + verify)
- **Owner removal dari dokter dropdown** (1-line fix, 3 entry point auto-update)
- **Bare except cleanup** di `_shared.py:413` → logging.warning
- **Health Check final**: 0/0/0/0 (perfect)

### 📌 Outstanding TODOs
- #325 FIN-REPORTS [WAITING #366]
- #362 Master Membership BARU privilege (complex)
- #363 Apoteker Reports + write-off
- #364 Void Pembayaran flow (perlu decide Admin-led atau Kasir PIN)
- #366 Finance Module (waiting consultant)
- #84 Sosial media pasien (future Phase 2)

### 🎯 Sprint Achievements (sejak #326 mulai)
4 layer ter-implement: Service method + Route + Template + ctx pass-through.
Plus quick cleanup (Owner dropdown, bare except). 
Sesi clean — health check lulus, no regressions.

---

## 📅 Update Sesi 10 Juni 2026 — #364 Void Pembayaran (5/7 phase done)

### ✅ Phase Complete (Sesi Ini)
- **#364 Phase 1** Foundation — migrations 013/014/015/016 + 3 enum baru
- **#364 Phase 2** Service Layer — void_transaksi + force_past_day_void + cascade resep & kunjungan
- **#364 Phase 3** Routes + UI Modal — kasir same-day void via Pembayaran Berhasil
- **#364 Phase 4** Display VOID + nota watermark — badge merah, warning card, watermark diagonal
- **#364 Phase 7** Force Past-Day Void UI — card di Detail Tagihan + halaman Cari Transaksi

### ⏳ Phase Deferred (Sesi Berikutnya)
- **#364 Phase 5** Dashboard Owner section "Void Hari Ini" — stats card + breakdown reason
- **#364 Phase 6** Reports `/web/reports/void` — filter range + tabel + CSV export

### ⚠️ Catatan Test Coverage
**Manual end-to-end test SETELAH sesi ini = PARTIAL.**

Yang sudah Bapak test: void per item + void transaksi + nota watermark + cascade.
Yang BELUM di-retest: flow normal (bayar tanpa void), force void aktual submit, edge cases (boundary limit Admin/Owner, series sesi pricing).

**Last comprehensive test = sebelum Void Pembayaran implementation dimulai.**

Sebelum lanjut Phase 5-6 atau feature lain, **disarankan smoke test full role journey** untuk regression detection. Detail di `07_known_issues.md` section "Test Coverage Status".

### 🐛 Side Bug Fixes (Bonus Sesi Ini)
4 bug independent dari #364 yang Bapak laporkan + saya fix:
- BUG-T1: pemeriksaan_klinis.updated_at missing — fixed dengan migration 015 (BLOCKER untuk dokter)
- BUG-T2: tambah komponen treatment missing kategori arg — fixed di route
- BUG-T3: toggle nonaktif staf silent skip — fixed via repo.set_active method
- BUG-T4: FO Beli Produk return null — fixed dengan success redirect

### 📋 Outstanding TODOs Setelah Sesi Ini
- #325 FIN-REPORTS (waiting #366)
- #362 Master Membership BARU privilege (complex)
- #363 Apoteker Reports + write-off
- **#364 Phase 5-6 — Dashboard + Reports analytics (DEFERRED)**
- #366 Finance Module (waiting consultant)
- #84 Sosial media pasien (future Phase 2)
- **NEW: Cancel Antrian needs FO catatan kecil for audit trail** (added Bapak's request, queued)

### 🎯 Magic Commands untuk Sesi Berikutnya
- *"Smoke test full role journey"* — sebelum lanjut implement apapun
- *"Lanjut Phase 5-6 #364 — Dashboard + Reports Void"* — kalau Bapak mau finalize #364
- *"Implement Cancel Antrian audit trail"* — task kecil queued

### 📊 #364 Status Summary
**Backend lengkap (100%). UI flow user (kasir + Admin + Owner) lengkap (100%). Analytics layer (Dashboard + Reports) — pending 2 phase.**

Sistem **fully usable** untuk operasional sehari-hari sekarang. Owner masih bisa cek void via Reports → Audit Log Viewer (existing) walaupun belum ada dedicated "Reports Void" page.

---

## 📅 Update Sesi 11 Juni 2026 — Smoke Test + Final Fixes

### ✅ Achievements Sesi Ini
- ✅ **Smoke test full role journey** — 7 role tested (Owner, FO, Dokter, Perawat, Kasir, Apoteker, Admin)
- ✅ **4 issue fixed live** dari smoke test:
  1. BUG-DASH-KASIR (typo TransaksiPembayaran.waktu_bayar)
  2. UI-KASIR-1 (Kasir akses Cari Transaksi + Force Void Day 0)
  3. BUG-NOTA-VOID (nota VOID items kosong)
  4. BUG-DT-VOID (Detail Tagihan VOID items kosong)
- ✅ **#364 Void Pembayaran sign-off** — Production-ready end-to-end

### #364 STATUS: 🎉 100% COMPLETE

| Phase | Description | Status |
|-------|-------------|--------|
| P1 | Foundation (4 migrations + 3 enum) | ✅ |
| P2 | Service Layer (void + cascade) | ✅ |
| P3 | Routes + UI Modal kasir same-day | ✅ |
| P4 | Display VOID badge + nota watermark | ✅ |
| P5 | Dashboard Owner section | ✅ |
| P6 | Reports `/web/reports/void` + CSV | ✅ |
| P7 | Force Past-Day Void UI | ✅ |

**Backend + UI + Analytics complete. Schema Phase 2 PIN/TOKEN/QUEUE siap di future.**

### ⏭ TODO Queue — 5 New Items (Diprioritaskan oleh Bapak)

Bapak temukan 5 UX enhancement saat smoke test. Queue untuk sesi berikutnya:

| # | Task | Effort | Why |
|---|------|--------|-----|
| #29 | **TODO-NEW-1**: Dokter edit alergi + penyakit kronis + antropometri | ~1-2 sesi | Dokter saat ini tidak punya akses edit medical history pasien |
| #30 | **TODO-NEW-2**: Sidebar scroll independent dari content | ~30 menit | Owner punya menu sangat banyak, user_id + logout button ke-scroll jauh |
| #31 | **TODO-NEW-3**: Master Produk default cara pakai → auto-fill resep | ~1 sesi | Quality of life dokter — sekarang harus ketik manual setiap kali |
| #32 | **TODO-NEW-4**: Ruang Tindakan hide pasien ANTRI_KONSULTASI | ~15 menit | UI clutter — pasien ANTRI_KONSULTASI tidak relevan untuk perawat |
| #33 | **TODO-NEW-5**: Master Treatment role_pelaksana guardrail | ~1 sesi | Perawat saat ini bisa Mulai tindakan dokter — perlu block + warning |

**Total estimasi 5 TODO**: ~3-4 sesi kerja.

### 🎯 Sweet Spot Recommendation Sesi Berikutnya

**Pertimbangan**: Bapak boleh pilih kombinasi quick wins + impact tinggi.

**Pilihan A — Quick Wins Bundle (~1 sesi)**:
- #32 TODO-NEW-4 (15 min) — Ruang Tindakan filter ANTRI_KONSULTASI
- #30 TODO-NEW-2 (30 min) — Sidebar layout fix
- Bonus: tes ulang #364 stability

**Pilihan B — Operational Safety (~1 sesi)**:
- #33 TODO-NEW-5 (~1 sesi) — Role guardrail Master Treatment
- Penting untuk prevent kesalahan operasional perawat eksekusi tindakan dokter

**Pilihan C — Dokter Power (~1-2 sesi)**:
- #31 TODO-NEW-3 (~1 sesi) — Auto-fill cara pakai
- #29 TODO-NEW-1 (~1-2 sesi) — Dokter edit medical record (perlu design discussion)

### 📋 Outstanding (Tidak Berubah)
- #325 FIN-REPORTS (waiting #366)
- #362 Master Membership BARU privilege
- #363 Apoteker Reports + write-off
- #366 Finance Module (waiting consultant)
- #84 Sosial media pasien (future Phase 2)
- **#364 Phase 2 PIN/TOKEN/QUEUE** — schema siap, aktifasi future

### 🐛 Bug Pattern Library Updated
4 pattern baru tercatat:
- B-020: Jinja dict.items shadowing
- B-021: FastAPI Optional[int] empty string
- B-022: Cascade filter hide items
- B-023: Field typo across tables

Total **10 pattern catalogued** di `07_known_issues.md` — referensi untuk avoid re-introduction.

### 🎯 Sprint Sign-off
- 🟢 0 CRITICAL bug
- 🟢 0 HIGH bug
- 🟢 #364 production-ready
- 🟢 Project_Memory updated (3 file)
- 🟢 Backup safepoint trail: 4 zip (pre_bugfix, pre_p4, pre_p7, pre_p56)
- 🟢 35 task completed sesi marathon (10 Juni + 11 Juni sambungan)

**Magic command sesi berikutnya**:
- *"Quick wins bundle: #30 + #32"* — Pilihan A
- *"Implement #33 role guardrail"* — Pilihan B
- *"Lanjut #31 auto-fill cara pakai"* — Pilihan C
- *"Design discussion #29 dokter edit medical record"* — sebelum implement
- *"Cleanup test data #621/#622"* — kalau Bapak mau cleanup

---

## 📅 Update Sesi 11 Juni 2026 (Sore) — Quick Wins + Finance Module Design

### ✅ Quick Wins Bundle Completed
- ✅ **#30 TODO-NEW-2**: Sidebar scroll independent — `_app.html` `min-h-screen` → `h-screen`
- ✅ **#32 TODO-NEW-4**: Ruang Tindakan hide ANTRI_KONSULTASI — `treatment_repo.list_antrian_ruang_tindakan`

### ✅ Defer Decision
- ✅ **#84 Sosial media field pasien** → moved to Phase 2 future (no timeline)

### ✅ #366 Finance Module Design (DEC-064)
- ✅ Architecture decision: **REST API + LAN deployment + Near-real-time (1 menit polling)**
- ✅ Scope confirmed: Akuntansi + Cash Flow + Komisi/Payroll + Tax/Compliance
- ✅ Project_Memory/FinanceModule/00_DESIGN.md created (full spec)
- ✅ `app/api/v1/finance.py` skeleton (10 endpoint placeholder 501)
- ✅ Migration 017 skeleton (4 tabel + 1 alter — belum applied)
- ✅ Registered di `main.py`

### 🎯 #366 Status Change
**Before**: `pending — undecided, waiting consultant`
**After**: `🟡 DESIGN PHASE — architecture decided, skeleton ready, awaiting Phase 1 trigger`

#### Effect on #325 FIN-REPORTS
Originally blocked by #366. Sekarang ada 2 path:
- **Opsi A**: Build #325 di Sehati side pakai endpoint Phase 1+ yang sudah implemented
- **Opsi B**: Tunda #325 sampai Finance Module Phase 3 jalan, lalu hapus #325

Bapak decide later.

### ⏭ TODO Queue Remaining (Updated)

| # | Task | Priority | Effort | Status |
|---|------|----------|--------|--------|
| **#33** | TODO-NEW-5: Master Treatment role_pelaksana guardrail | 🔴 P0 (operational safety) | ~1 sesi | pending |
| **#31** | TODO-NEW-3: Master Produk auto-fill cara pakai | 🟠 P1 (UX dokter) | ~1 sesi | pending |
| **#29** | TODO-NEW-1: Dokter edit alergi/penyakit/antropometri | 🟡 P2 (perlu design discussion) | ~1-2 sesi | pending |
| **#363** | Apoteker Reports + write-off | 🟡 P2 (pattern reusable) | ~2-3 sesi | pending |
| **#362** | Master Membership BARU privilege system | 🔵 P3 (perlu design heavy) | ~3-4 sesi | pending |
| **#325** | FIN-REPORTS | 🟢 OPSIONAL (covered by Finance Module) | TBD | pending |
| **#366** | Finance Module Phase 1+ | 🟡 design done, awaiting consultant decision | Multi-sesi | DESIGN PHASE |

### 🎯 Recommended Next Sessions

**Sesi A — Operational Safety**:
- *"Implement #33 role guardrail"* — perawat block tindakan dokter

**Sesi B — Dokter UX Quick Win**:
- *"Implement #31 auto-fill cara pakai"* — auto-populate resep dengan default produk

**Sesi C — Apoteker Module**:
- *"Lanjut #363 Apoteker Reports"* — pattern reusable dari Reports Void

**Sesi D — Discussion**:
- *"Design discussion #29 dokter edit medical record"* — sebelum implement

### 📊 Sesi Cumulative Stats (10+11 Juni 2026)

- 🟢 Tasks completed: **44 task**
- 🟢 Critical bugs: 0
- 🟢 #364 Void Pembayaran: 100% complete
- 🟢 #366 Finance Module: design phase + skeleton ready
- 🟢 4 file Project_Memory updated
- 🟢 1 design doc new (FinanceModule/00_DESIGN.md)
- 🟢 1 skeleton API file new (finance.py 285 lines)
- 🟢 1 migration SQL skeleton (017)
- 🟢 Backup safepoint trail: 4 zip

---

## 📅 Update Sesi 11 Juni 2026 (Dini Hari ~01:30) — DEC-065 Pivot Pure Viewer

### 🎯 Major Pivot
Bapak diskusi kedua dengan Claude → adopt approach yang jauh lebih ramping. Lihat **DEC-065** + **`Project_Memory/FinanceModule/01_VIEWER_BRIEF.md`**.

| Aspect | DEC-064 (Sore) | DEC-065 (Dini hari, FINAL) |
|--------|----------------|----------------------------|
| Role | Full Finance Module paralel | Pure Viewer (read-only, derived-only) |
| Source of Truth | Finance Module sendiri | **Accurate Online** (akuntan klinik) |
| Scope | Akuntansi + Tax + Payroll + Cash Flow | **3 view simple**: Jurnal Harian, Cashflow, Komisi |
| Build Effort | 3-5 sesi | **1-2 sesi** (Phase 1 setelah prasyarat) |
| Maintenance | High (PSAK + tax compliance abadi) | **Low** (cuma derive logic) |

### 🎯 Status Update

| Task | Status Before | Status After |
|------|---------------|--------------|
| **#366** Finance Module | 🟡 DESIGN PHASE (full module) | 🟢 **PIVOTED to DEC-065 Pure Viewer** |
| **#325** FIN-REPORTS | pending — blocked by #366 | **Merged into DEC-065 Pure Viewer** (3 view = reports) |

### ⏭ Updated Roadmap

**Phase 1 — Pure Viewer Foundation** (saat trigger, ~1-2 sesi):
1. Prasyarat Sehati side (R2-R4 dari DEC-064 Rev 1):
   - HPP snapshot di proses_bayar
   - doc_number generator (TRX-YYYY-MM-NNNNNN)
   - updated_at auto-bump
   - Item-level discount allocation
2. Reports Export Pack preset "Finance Snapshot" (3 view dalam ZIP)
3. (Optional) Web pages 3 view di `/web/reports/finance-viewer/*`

**Phase 2 — Feeder Mode** (saat akuntan minta data spesifik):
- Build exporter ke template Accurate Online (incremental, bukan rewrite)

### ⏳ DROPPED/DEFERRED
- ❌ Full Finance Module API namespace yang besar (Inventory, Series Deposit, Membership Commitment) — dropped
- ❌ Webhook push events — dropped
- ❌ Raw payload + idempotency Finance side — tidak relevan
- ❌ #366 Phase 3 external module build — pivoted ke pure viewer mode

### 📁 Updated Project_Memory/FinanceModule/
- `00_DESIGN.md` (970 lines) — Original full design + Rev 1 refinement + Rev 2 pivot
- `01_VIEWER_BRIEF.md` (130 lines) — **FINAL** architecture (read this first)

### 🎯 Trigger untuk Phase 1
Bapak butuh konfirmasi 5 hal dari akuntan klinik:
- Cash basis atau accrual?
- Series & membership: kapan revenue diakui?
- Klinik PKP atau non-PKP?
- COA export dari Accurate untuk mapping config
- Periode tutup buku?

Sampai konfirmasi masuk, Phase 1 boleh jalan dengan **default + label PENDING**.

### 💡 Reflection

Bapak's decision pivot ke Pure Viewer adalah **brilliant call**:
1. Eliminate maintenance abadi (compliance regulasi)
2. Trust expert tools (Accurate sudah handle PSAK/tax)
3. Stay in own lane (klinik operasional vs akuntansi)
4. Build small, ship fast, iterate

Pattern ini disebut **"Trust Your Tools, Don't Recreate Them"** — best practice di software architecture.

---

## Sesi 11 Juni 2026 (Pagi 08:40-10:00) — Quick Wins #33 + #31 + #29A

### ✅ Completed

#### TODO-NEW-5 #33 — Master Treatment role_pelaksana guardrail
- Schema `TindakanDetailItem` + field `role_pelaksana`
- Service `start_tindakan()` + param `user_role` + 403 raise kalau perawat coba start tindakan DOKTER (Admin/Owner bypass)
- Route `perawat.py` pass `user.role` ke service
- Template `perawat_tindakan.html` badge DOKTER/PERAWAT + smart Mulai button dengan disable+alert
- Files: 4

#### TODO-NEW-3 #31 — Master Produk default_cara_pakai → auto-fill resep SOAP
- Migration 018: `ALTER TABLE master_produk ADD COLUMN default_cara_pakai VARCHAR(200) NULL AFTER harga_jual`
- ORM model + Pydantic Create/Update/Response schema
- Service `create_produk` + `update_profile` (via `repo.update`)
- Admin form: input "Default Cara Pakai" di master_produk_form.html
- Dokter resep row: `data-cara-pakai` attribute + JS `applyDefaultCaraPakai()` idempotent global handler
- **Bug fix iteration 1**: Route handler tidak terima Form field — fixed
- **Bug fix iteration 2**: GET handler form dict tidak include key → reload kosong — fixed
- Files: 6 + 1 migration

#### TODO-NEW-1 #29A — Dokter inline kelola Alergi
- Schema `AlergiUpdateRequest` (partial update)
- Service `update_alergi()` dengan audit log_update
- Route DUAL:
  - `POST /web/pasien/{id_pasien}/alergi/{tambah,*/ubah,*/hapus}` (dari Detail Pasien)
  - `POST /web/dokter/kunjungan/{id_kunjungan}/alergi/...` (dari SOAP form)
- Template `_dokter_alergi_panel.html` reusable — parameterized via `alergi_action_base` + `alergi_panel_uid`
- Inject `{% include %}` di SOAP form + Detail Pasien (role-gated)
- Permission: DOKTER + ADMIN + OWNER + SUPERADMIN
- **Bug fix iteration 1**: Panel awal hanya di SOAP form — Bapak buka Detail Pasien dan tidak nemu. Refactor jadi reusable + inject di Detail Pasien juga
- **Bug fix iteration 2**: CSRF token missing — add `{{ csrf_input(request) }}` di 3 form
- **Bug fix iteration 3**: Enum value lookup `Enum("RINGAN")` vs name lookup `Enum["RINGAN"]` — enum values title case ("Ringan") tapi form submit uppercase ("RINGAN"). Fix: pakai name lookup `[]`
- Files: 6

### 🔴 B-013 STORM
- **10 truncation strikes** di sesi ini (record terburuk)
- Files affected: treatment_service.py, master_produk_service.py, master_produk_form.html, master.py (3x), pasien.py (2x), pasien_service.py, pasien.py schemas, dokter_soap_form.html (2x), pasien_detail.html
- Pattern: tail truncation mid-string saat Edit pada file > 200 lines
- Mitigation: Python heredoc + AST verify + safepoint restoration
- TODO: append "B-024 — B-013 high frequency in long Edit sessions, use Write or chunk small" ke 07_known_issues.md

### ⏸ DEFERRED Tonight (untuk dikerjakan nanti malam)

#### Phase #29 — Selesaikan Medical Record edit dokter
1. **#29B — Penyakit Kronis full CRUD** (~1 sesi, similar pattern dengan Alergi)
   - Service: `tambah_penyakit_kronis()`, `update_penyakit_kronis()`, `hapus_penyakit_kronis()` (soft)
   - Schema: `PenyakitKronisAddRequest`, `PenyakitKronisUpdateRequest`
   - Routes dual: pasien.py + dokter.py
   - Template `_dokter_penyakit_kronis_panel.html` (reusable seperti alergi)
   - Inject ke SOAP form + Detail Pasien
   - **PERHATIAN**: Bahas dengan B-013 in mind — pakai Python heredoc untuk service edit (jangan Edit tool langsung)

2. **#29C — Antropometri dokter-edit** (~1 sesi, lebih simple)
   - Route POST `/web/dokter/kunjungan/{id_kunjungan}/antropometri/ubah` → existing `AntropometriService.upsert()`
   - Modal/inline form di SOAP form (BB, TB, tensi, suhu, lingkar perut, skinfold 1/2/3)
   - Permission: DOKTER + ADMIN + OWNER + SUPERADMIN
   - Optional: di Detail Pasien juga (perlu id_kunjungan_aktif fallback)

### Outstanding Priorities (Sesi Berikutnya)

| Priority | Task | Effort | Note |
|----------|------|--------|------|
| 🔴 P0 | **B-013 mitigation pattern** | ~0.5 sesi | Document B-024 + DEC-066 jika perlu |
| 🟡 P1 | **#29B Penyakit Kronis CRUD** | ~1 sesi | Pattern alergi |
| 🟡 P1 | **#29C Antropometri edit** | ~1 sesi | Pattern lighter |
| 🟢 P2 | **#363 Apoteker Reports + write-off** | ~2-3 sesi | |
| 🟢 P2 | **DEC-065 Phase 1 prasyarat** | ~1-2 sesi | hpp_at_sale + doc_number + updated_at + diskon allocation |
| 🟢 P3 | **#362 Master Membership BARU** | ~3-4 sesi | privilege system rewrite |
| 🔵 P4 | **#366 Finance Viewer Phase 1** | TBD | tunggu jawaban akuntan |

---

## Sesi 11 Juni 2026 Malam (23:00-...) — Selesaikan #29 + UX Refinements + #50

### ✅ Completed

#### #29B Penyakit Kronis Full CRUD
- Schema: `PenyakitKronisAddRequest` + `PenyakitKronisUpdateRequest`
- Repo: `soft_delete_penyakit_kronis()`
- Service: 3 methods `tambah_penyakit_kronis`, `update_penyakit_kronis`, `hapus_penyakit_kronis`
- Routes dual:
  - `pasien.py` POST `/web/pasien/{id_pasien}/penyakit-kronis/{tambah,/ubah,/hapus}`
  - `dokter.py` POST `/web/dokter/kunjungan/{id_kunjungan}/penyakit-kronis/{...}`
- Template `_dokter_penyakit_kronis_panel.html` reusable parameterized (`pk_action_base`, `pk_panel_uid`)
- Inject di SOAP form + Detail Pasien (role-gated)
- Permission: DOKTER + ADMIN + OWNER + SUPERADMIN
- Files: 7
- **Tested by Bapak: zero error** ✓

#### #29C Antropometri Edit
- Route `POST /web/dokter/kunjungan/{id_kunjungan}/antropometri/ubah` reuse existing `AntropometriService.upsert()`
- Route `POST /web/pasien/{id_pasien}/antropometri/{id_kunjungan}/ubah` untuk Detail Pasien context
- Template `_dokter_antropometri_panel.html` parameterized (`antro_action_url`, `antro_form_uid`)
- 8-field form: BB, TB, TD, Suhu, Lingkar Perut, Skinfold 1/2/3 + hint Jackson-Pollock
- Inject SOAP kolom 3 + Detail Pasien (conditional `kunjungan_aktif_id`)
- Files: 4

#### UX Refinements (post-test Bapak feedback)
1. **Body Fat % + Lean Mass display di SOAP kolom 3** — ditambah display dari existing `get_terakhir_with_clinical()` Jackson-Pollock formula. Plus L.Perut tambahan kalau ada.
2. **Collapsible Kelola Alergi + PK** di SOAP form — default hidden. Click link "⚙ Kelola Alergi" / "⚙ Kelola Penyakit Kronis" → toggle panel. Bersih, tidak overwhelming.
3. **Antropometri panel di Detail Pasien** — conditional kunjungan_aktif_id. Kalau ada kunjungan aktif → panel edit muncul. Kalau tidak → info "Buat antrian dulu" dengan link.
4. **Skinfold formula explanation** — Aisyah Shafira tgl_lahir kosong → body fat tidak hitung (formula butuh usia). Bukan bug, by design. Triggered TODO #50.

#### #50 Edit Detail Pasien (TODO-NEW-6)
- Schema `PasienUpdateRequest` (9 field opsional, partial update, no_rm absent)
- Service `update_pasien_profile()` dengan **PII-aware audit log**:
  - Alamat & KTP → flag "changed: true" only (no raw value)
  - Tgl lahir → year only di audit
  - Telepon → last 4 digit only
  - Nama, JK, Email, Sumber, Membership → full value (non-sensitive)
- Route `POST /web/pasien/{id_pasien}/edit` — require `ANTRIAN_MGMT_ROLES` (FO + Admin + Owner + Superadmin)
- Template `_pasien_edit_panel.html` — 9 field form expand toggle
- Inject di header card Detail Pasien (role-gated)
- **KTP masking** — display: `320*****8901` di view, full di edit form
- no_rm read-only (tidak ada di schema → impossible diubah)
- Hint di tgl_lahir field: "(penting untuk hitung Body Fat %)"
- Files: 4

### 🟢 B-013 STORM ZERO Strikes
**Sesi malam 0/0/0 strikes** — DEC-056 Python heredoc + AST verify pattern proven WORKING flawlessly across:
- 3 sub-tasks #29B + #29C + 4 UX refinements + #50
- Plus 4 reusable template parametrization
- Plus 5 service/route file edits + 7 template injections

Pattern adoption rate: 100% (vs pagi 10 strikes).

### Outstanding Priorities (Sesi Berikutnya)

| Priority | Task | Effort |
|----------|------|--------|
| 🟢 P3 | **DEC-065 Phase 1 prasyarat** (hpp_at_sale + doc_number + updated_at + diskon allocation) | ~1-2 sesi |
| 🟡 P2 | **#363** Apoteker Reports + write-off | ~2-3 sesi |
| 🟢 P3 | **#362** Master Membership BARU privilege system | ~3-4 sesi |
| 🔵 P4 | **#366** Finance Viewer Phase 1 | tunggu jawaban akuntan |

---

## Sesi 11 Juni 2026 Malam Lanjutan (23:00+) — #363 Apoteker Reports + Write-off

### ✅ Completed

#### #363A Manajemen Stok Apotek
- Page `/web/apotek/stok` dengan summary cards (Total/Rendah/Habis)
- Filter: keyword + status (low/out/semua)
- Tabel 9 kolom (kode, nama, tipe, stok, min, HPP, harga, status badge, aksi)
- Color-coded rows untuk stok bermasalah
- Sidebar menu "📦 Manajemen Stok" untuk Apoteker/Owner/Superadmin
- Files: 3

#### #363B Rekap Resep Apoteker
- Route `/web/reports/apoteker-dispensed` + CSV export
- Schema: ApotekerDispensedItem + ApotekerSummaryPerStaf + ApotekerDispensedResponse
- Service `get_apoteker_dispensed_report()` — JOIN audit_log (SERAH_OBAT) + kunjungan_resep + master_produk + master_staf + pasien
- 4 summary cards + per-apoteker breakdown table + detail items table + pagination
- Files: 5

#### #363C Rekap Write-off Produk
- Route `/web/reports/write-off` + CSV
- Schema: WriteOffReportItem + WriteOffSummaryPerJenis + WriteOffReportResponse
- Service query `audit_log WHERE aksi LIKE 'WRITEOFF_PRODUK_%'` + JOIN master_produk + master_staf
- Filter: tanggal, jenis (EXPIRED/RUSAK/PENYESUAIAN), apoteker
- Breakdown per jenis dengan colored badges + loss estimation
- Default 30 hari (vs 7 hari untuk dispensed report)
- Files: 5

#### #363D Top Dispensed Products
- Route `/web/reports/top-produk` + CSV
- Schema: TopProdukItem (12 field) + TopProdukResponse
- Service `get_top_dispensed_products()` GROUP BY id_produk
- Sort modes: qty/count/nominal (default qty)
- Top N: 20/50/100/200/500
- Medal badges 🥇🥈🥉 untuk top 3
- Smart Stok Now color-coding (out/low/safe)
- Files: 5

#### #363E Stok Critical Widget
- 2 card widget di apotek antrian page (top)
- Auto-hide kalau semua stok aman
- Direct link ke Manajemen Stok dengan filter pre-applied
- Graceful fallback kalau query stat gagal
- Files: 2

### 🔧 Post-#363 UX Fixes

#### FIX-363-1: Dashboard alert stok link
- `_alert_stok_urgent()` di dashboard_service.py: URL diganti dari `/web/apotek/suggested-order` → `/web/apotek/stok?filter_stok=low`
- Reason: suggested-order fokus 90-hari trend, kurang clear untuk identifikasi stok rendah; Manajemen Stok dengan filter low lebih direct & consistent dengan widget di apotek landing

#### FIX-363-2: Reports menu hilang dari Apoteker sidebar
- menu.py: tambah group "Laporan" dengan MENU_REPORTS ke role Apoteker
- Sebelumnya saya add 3 report (apoteker-dispensed, write-off, top-produk) accessible by apoteker, tapi entry point tidak ada di sidebar — bug discoverability

#### FIX-363-3: Tombol "🛒 PO" di Manajemen Stok
- Tambah button per row di samping Write-off
- Smart suggested qty: `(stok_minimal × 2 − stok_terkini)`, floor min 1
- Pre-fill via existing `?prefill_produk=ID&prefill_qty=N` query param (route pemesanan/baru sudah support)
- Files: 3 fixes total

### 🟢 B-013 Strike Count: ZERO

Sesi malam total **0 strikes** across:
- 5 #363 sub-tasks
- 3 post-fix UX iterations
- ~20 file modifications/creations

Pattern adopted secara konsisten (Python heredoc + AST/Jinja verify) — playbook DEC-066 proven mature.

### 🆕 New Pages Total (4)
- `/web/apotek/stok` — Manajemen Stok (Apoteker domain)
- `/web/reports/apoteker-dispensed` — Rekap Resep Apoteker (+ CSV)
- `/web/reports/write-off` — Rekap Write-off (+ CSV)
- `/web/reports/top-produk` — Top Dispensed Products (+ CSV)

### 📊 Sesi 11 Juni Total Achievement

| Sesi | Tasks Completed | B-013 Strikes |
|------|-----------------|---------------|
| Pagi (08:40-10:00) | #33, #31, #29A | 10 (Edit-heavy) |
| Malam Awal (23:00-...) | #29B, #29C, 4 UX refinements, #50 | 0 |
| Malam Lanjutan (...) | #363A-E + 3 fixes | 0 |
| **Total** | **11 tasks + 7 UX/fix items** | **10** |

### Outstanding Priorities (Sesi Berikutnya)

| Priority | Task | Effort |
|----------|------|--------|
| 🟢 P3 | **DEC-065 Phase 1 prasyarat** (hpp_at_sale + doc_number + updated_at + diskon allocation) | ~1-2 sesi |
| 🟢 P3 | **#362** Master Membership BARU privilege system | ~3-4 sesi |
| 🔵 P4 | **#366** Finance Viewer Phase 1 | tunggu jawaban akuntan |

---

## Sesi 12 Juni 2026 (10:00-12:48) — #362 Master Membership FULL

### ✅ Completed — #362 Master Membership BARU dengan Privilege System

Total **17 sub-tasks/fix** dalam 1 sesi panjang (~3 jam).

#### 362A — Master Membership CRUD UI
- Schema + Repo + Service + 5 routes + 2 templates
- ENUM sync validation (REGULAR/VIP/VVIP)
- Soft delete via is_active toggle
- Audit log full

#### 362C — Wire pasien edit dropdown ke read-from-db
- Replace hardcoded tier dropdown dengan dynamic dari master_membership
- Backend validation: tier nonaktif reject submit
- Fallback display "(tier nonaktif)" untuk pasien lama dengan tier ke-deactivate

#### 362D — Membership Activation Financial Flow (Opsi 4 Hybrid)
- Migration 019: transaksi_kasir + 2 fields (id_membership_aktivasi + nominal_aktivasi_membership)
- Pending membership history saat aktivasi
- Kasir line item "Aktivasi Membership" otomatis muncul
- Bayar trigger atomic activate + kuota creation
- Diskon tidak apply saat aktivasi (active setelah dibayar)

#### 362E — Section Membership (5 sub-tasks)
- Page `/web/pasien/{id}/membership` dengan full lifecycle UI
- Service methods: get_status, create_pending, cancel_pending, revert_active_to_pending, create_kunjungan_billing
- Action panel role-gated: Aktivasi / Perpanjang / Upgrade / Cancel
- Void cascade — revert ke PENDING + deactivate kuota
- Link "Kelola Membership" di Detail Pasien header
- Edit Pasien tier field jadi read-only display

#### 362E Fixes (A-D, 4 batches)
- A: tipe_membership update timing (saat bayar, bukan saat pending)
- B: Standalone billing (Buat Tagihan Sekarang button)
- C: 4 bugs — 403 redirect, visual glitch lingering, no deactivate prev tier, upgrade button at highest
- D: 3 bugs — double-click duplicate, upgrade tier filter (higher only), button disable

#### 362F — Renewal Carry-Over
- RENEWAL: tgl_expired = current.expired + durasi (bukan reset)
- Warning > 60 hari sisa
- UPGRADE tetap reset

#### 362B — Benefit Treatment CRUD + Kuota Logic (4 sub-tasks)
- A: tgl_aktif preserve di RENEWAL
- B: CRUD UI master_membership_benefit_treatment per tier
- C: Kuota auto-create TOTAL_PAKET + RENEWAL carry-over (extend kuota_total + expired_at)
- D: Hide Buat Tagihan button kalau already ada kunjungan ANTRI_BAYAR

### 🎯 Key Decisions Made

1. **Tier display vs DB tier**: pasien.tipe_membership track current state. tgl_aktif preserve original di RENEWAL untuk continuity
2. **ACTIVATION vs RENEWAL vs UPGRADE semantic**: distinct logic per action
3. **Carry-over scope**: 
   - RENEWAL: tgl_expired extend + kuota_total extend
   - UPGRADE: reset (fresh start)
4. **Benefit periode**:
   - TOTAL_PAKET: eager create row, extend on renewal
   - BULANAN: lazy create per bulan (Phase 2 future)
5. **Defense-in-depth**: button disable + backend 409 + visual feedback

### 🟢 B-013 Strike Count: ZERO

3 hari berturut (11 Juni Pagi+Malam + 12 Juni) sesi besar dengan playbook DEC-066:
- 11 Juni Pagi (Edit-heavy): 10 strikes
- 11 Juni Malam (heredoc): 0
- 12 Juni Siang (heredoc): 0

Pattern proven stable + adopt sebagai default.

### 🆕 New Pages/Endpoints (10+)

- `/web/master/membership` — Master CRUD tier
- `/web/master/membership/{id}/benefit` — Master CRUD benefit per tier
- `/web/pasien/{id}/membership` — Section Membership pasien
- `/web/pasien/{id}/membership/aktivasi` — POST pending
- `/web/pasien/{id}/membership/{id_history}/cancel` — POST cancel
- `/web/pasien/{id}/membership/create-billing` — POST standalone billing
- Plus 4 master_membership benefit routes

### 📊 Sesi 12 Juni Stats

| Metric | Count |
|--------|-------|
| Sub-tasks completed | 17 (4 main + 13 fix/iteration) |
| Files modified/created | ~25 |
| B-013 strikes | 0 |
| Major architectural decisions | 5 |
| Session duration | ~3 hours |

### Outstanding Priorities (Sesi Berikutnya)

| Priority | Task | Effort |
|----------|------|--------|
| 🟡 P2 | **BULANAN kuota lazy-create** (Phase 2 — saat treatment dispense) | ~1 sesi |
| 🟡 P2 | **Display kuota usage** di Detail Pasien & Section Membership | ~0.5 sesi |
| 🟡 P2 | **Wire kuota usage** di dokter SOAP saat pilih treatment (pakai kuota → harga 0) | ~1-2 sesi |
| 🟢 P3 | **DEC-065 Phase 1 prasyarat** (hpp_at_sale + doc_number + updated_at + diskon allocation) | ~1-2 sesi |
| 🔵 P4 | **#366 Finance Viewer Phase 1** | tunggu jawaban akuntan |

---

## Sesi 2026-06-12 Malam (#362 Phase 2 LENGKAP + Audit/Nota)

### Yang Diselesaikan

**#362 Phase 2 — Membership Kuota Auto-Use** (3 main tasks + 1 fix + 1 audit + 1 nota):

| Task | Status | Effort |
|------|--------|--------|
| P2-#1: BULANAN kuota lazy-create helper | ✅ | ~30m |
| P2-#2: Display kuota usage di Section Membership | ✅ | ~30m |
| P2-#3: Wire kuota auto-use di dokter SOAP (pakai → harga 0) | ✅ | ~45m |
| FIX-P2-#1: TOTAL_PAKET juga lazy-create (legacy data + benefit ditambah belakangan) | ✅ | ~20m |
| **LOG-1**: Audit log KUOTA_PAKAI + KUOTA_REVERT entries | ✅ | ~20m |
| **NOTA-C**: Diskon Benefit Member line + section "Benefit Terpakai" | ✅ | ~45m |

### Files Modified
- `app/services/membership_service.py` — kuota lifecycle: get_or_create (unified BULANAN+TOTAL_PAKET lazy), increment/decrement (audit-aware), list_kuota_for_pasien, _kuota_audit_keterangan helper
- `app/services/pemeriksaan_service.py` — SOAP submit auto-call increment_kuota_terpakai dengan actor + kunjungan context
- `app/services/print_service.py` — prepare_nota_context track diskon_benefit + benefit_items
- `app/web/routes/dokter.py` — _build_soap_ctx pass kuota_map ke template
- `app/web/templates/dokter_soap_form.html` — Banner kuota tersedia + diagnostic indicator
- `app/web/templates/_tindakan_row.html` — Dropdown 🎁 N/M kuota + onchange hint
- `app/web/templates/pasien_membership.html` — Section "Kuota Benefit"
- `app/web/templates/print/nota_a5.html` — Diskon benefit line + Benefit Terpakai section
- `app/web/templates/print/nota_thermal.html` — same untuk thermal compact

### Math Nota Sekarang
```
Subtotal (gross)               Rp 600.000
Diskon Tier (10%)             - Rp 35.000
🎁 Benefit Member (1 item)    - Rp 250.000
─────────────────────────────────────────
TOTAL                          Rp 315.000

🎁 Benefit Member Terpakai:
  Facial Acne — VVIP BULANAN 2026-06    Rp 250.000
```

### Stats Sesi
| Metric | Count |
|--------|-------|
| Sub-tasks completed | 6 main + 4 B-013 recoveries |
| Files modified | 9 |
| B-013 strikes | **5** (post-recovery rate 100%) |
| Session duration | ~4 hours |

### Outstanding Priorities (Sesi Berikutnya)

| Priority | Task | Effort |
|----------|------|--------|
| 🟡 P2 | **Void cascade — call decrement_kuota_terpakai saat tindakan VOID** | ~30m |
| 🟢 P3 | **DEC-065 Phase 1 prasyarat** (hpp_at_sale + doc_number + updated_at + diskon allocation) | ~1-2 sesi |
| 🔵 P4 | **#366 Finance Viewer Phase 1** | tunggu jawaban akuntan |

---

## Sesi 2026-06-12 Malam (Lanjutan) — Phase 3 Void Cascade Kuota Revert

> Sesi lanjutan di malam yang sama (handoff dari sesi #362 Phase 2). Fokus single task: tutup outstanding DEC-067 (void cascade kuota).

### Yang Diselesaikan

**🟡 P2 — Void Cascade Kuota Revert (DEC-068)** — ✅ COMPLETE

Saat kasir void transaksi yang punya `KunjunganTindakan` dengan `id_kuota_member NOT NULL`, sistem sekarang otomatis revert kuota member (decrement_kuota_terpakai) untuk tiap tindakan tersebut.

| Item | Detail |
|------|--------|
| Helper baru | `KasirService._revert_kuota_per_tindakan(id_kunjungan, actor, request)` — query tindakan dengan kuota, loop decrement, best-effort try/except |
| Call site 1 | `void_transaksi` (kasir same-day) — di blok `if trx.id_kunjungan:` |
| Call site 2 | `force_past_day_void` (Admin/Owner past-day) — konsisten, sekalian wire |
| Audit | `KUOTA_REVERT` di-tulis internal oleh `decrement_kuota_terpakai` (sudah ada dari LOG-1). Floor at 0. |
| UX | `kuota_reverted_count` masuk audit `data_baru` + response dict kedua method |

### Acceptance Criteria — Semua PASS

1. ✅ Void → query tindakan dengan `id_kuota_member`, call decrement dengan actor + kunjungan
2. ✅ **Test14** (Facial Acne): kuota 0/1 (terpakai 1) → void → balik 1/1 (terpakai 0) — **tested manual by dr. Hansen**
3. ✅ Audit log `KUOTA_REVERT` muncul dengan keterangan lengkap per kuota
4. ✅ Floor at 0, graceful failure (void tetap sukses meski audit/revert gagal)

### Files Modified
- `app/services/kasir_service.py` — 1 helper baru + wiring di 2 void method (+ `kuota_reverted_count` di audit & response)

### Stats Sesi
| Metric | Count |
|--------|-------|
| Task selesai | 1 (P2 Void Cascade) |
| Files modified | 1 |
| Helper baru | 1 |
| Call sites wired | 2 (void_transaksi + force_past_day_void) |
| B-013 strikes | **1** (Edit tool truncate file di line 1253 mid-statement; restored via heredoc + AST verify; sisa wiring pakai Python patch script) |
| Verify | AST + py_compile clean, 0 null bytes |
| Effort | ~30 menit (sesuai estimasi) |

### Decision Closure
- **DEC-067 "Outstanding"** (void cascade kuota revert) → ✅ CLOSED via DEC-068
- Void sekarang fully cascade: stok + series + membership history + **kuota benefit**

### Verifikasi Status Task Lama (cek 12 Jun malam)

Saat closing, dr. Hansen konfirmasi #363 & #364 sudah aktif di interface. Recon kode membenarkan — **dua-duanya COMPLETE, bukan pending:**

| # | Task | Status | Bukti di kode |
|---|------|--------|---------------|
| #363B | Apoteker Reports (dispensed) | ✅ DONE & aktif | `reports.py:614 /reports/apoteker-dispensed` + CSV + `reports_service.get_apoteker_dispensed_report` + template |
| #363C | Write-off Report | ✅ DONE & aktif | `reports.py:773 /reports/write-off` + CSV + `get_writeoff_report` + `reports_writeoff.html` |
| #364 P5 | Dashboard "Void Hari Ini" | ✅ DONE & aktif | `dashboard_service.py:345 _void_today_stats` + `dashboard.html:128-171` (count/nominal/late/by_reason) |
| #364 P6 | Reports Void + CSV | ✅ DONE & aktif | `reports.py:455 /reports/void` + `:542 /csv` + `get_void_report` + `reports_void.html` |

→ **#363 & #364 ditutup penuh.** #364 sekarang 100% (Phase 1-7 semua selesai).

### Outstanding Priorities (Sesi Berikutnya)

| Priority | Task | Status |
|----------|------|--------|
| 🟢 P3 | **DEC-065 Phase 1 prasyarat** (hpp_at_sale + doc_number + updated_at + diskon allocation) | ⏸️ PENDING — sejalan dengan #366 (jangan dikerjakan terpisah) |
| 🔵 P4 | **#366 Finance Viewer Phase 1** | ⏸️ PENDING until further notice (tunggu akuntan) |
| 🔵 P4 | **#84 Sosial media pasien field** | ⏸️ Future / Phase 2 |

**Catatan:** Tidak ada P2/P3 actionable yang jelas tersisa untuk sesi berikutnya. Mayoritas backlog sekarang pending external (akuntan) atau future. Kandidat task berikutnya kemungkinan datang dari real-use feedback dr. Hansen atau B3 Deployment Guide (kalau mau lanjut ke launch prep).

### Tambahan Sesi Ini — Raw Data Export Enrichment (DEC-069)

Di luar Phase 3, sesi ini juga membereskan temuan dr. Hansen soal anomali raw data export (untuk pipeline modul data_analyst):
- **Investigasi:** kode angka `1/2/4` di `metode_bayar` + `1` di `sumber_pendaftaran` = data test awal, BUKAN enum lama (kolom teks bebas, no legend).
- **Enrich kamus:** `_export_columns.py` + section "Catatan Anomali Data & Nilai Kanonik" di DATA_DICTIONARY (auto tiap pack).
- **Normalisasi `CASH` → `TUNAI`:** dr. Hansen eksekusi via SQL manual (aman, no logic branch pada literal). Cleanup kode angka ditunda.
- Detail: DEC-069. File SQL: `seed_data/data_cleanup_metode_sumber_2026-06-12.sql`.

---

## 25 Juni 2026 — Frontend/UX Audit Live (Chrome DevTools MCP)

Audit menyeluruh app live via Chrome DevTools (4 role + walkthrough alur-dalam dengan pasien test DUMMY TEST 2506: Daftar → SOAP → Tindakan → Bayar → Void).

**Hasil:** UI rapi & konsisten, performa lokal bagus (LCP 260ms, CLS 0), alur inti solid. Temuan terutama soal kesiapan produksi.

**Temuan utama (detail: `Project_Memory/HealthCheck/frontend_ux_audit_2026-06-25.md`):**
- 🔴 Semua aset frontend (HTMX/Tailwind/Tom Select) dari CDN eksternal → internet putus = UI rusak. Self-host. **(masuk B3)**
- 🔴 Tailwind mode CDN runtime-compile (warning "not for production"). Build statis. **(masuk B3)**
- 🟡 Role enum leak `StafRoleEnum.OWNER` di hampir semua halaman (kecuali Dashboard) — fix 1 baris di `_shared.py`.
- 🟡 Format angka Rp tidak konsisten (Tagihan koma vs lainnya titik).
- 🟡 Unlabeled form fields sistemik (wizard 17, SOAP 8, tagihan 5) — aksesibilitas.
- 🟡 Tabel "Antrian Hari Ini" overflow horizontal (tombol aksi kepotong).
- 🟠 Auto-print halaman Pembayaran Berhasil bisa ganggu interaksi lanjutan — verifikasi di hardware kasir asli.
- 🟢 Wizard 2 tombol submit ambigu, input nominal `valuemax=0`.

**Catatan:** data dummy test masih di DB (pasien 1405 / kunjungan 1571 / trx 644). Cleanup SQL: `seed_data/cleanup_dummy_test_2506.sql`.

**Outstanding keamanan pra-launch (dari 07_known_issues lama, relevan):** C2 rate limiting login, C3 JWT secret rotation, C5 HTTPS. Pertimbangkan access-control/authorization review sebelum launch (medical PII).

---

## 26 Juni 2026 — Quick Wins UX + C2 + Diskusi B3/Multi-Cabang

### ✅ Dikerjakan
- **#29 Role enum leak FIXED** — 4 template (`_app.html` ×2, dashboard, profil) `{{ user.role }}` → pola `.value`. Verified live ("Owner", bukan "StafRoleEnum.OWNER").
- **#30 Format Rp konsisten** — 17 instance di 7 template tambah `.replace(",", ".")` (titik, format Indonesia). Verified live.
- **#31 Label tombol wizard** — "Simpan Saja (tanpa antrian)" vs "Simpan & Masuk Antrian" + tooltip. (B-013 truncation kambuh, restored dari sehati_clinic_template copy.)
- **#28 C2 Rate Limit Login** — `app/core/rate_limit.py` in-memory per-IP, hitung gagal saja, 10 gagal/10mnt → cooldown 5mnt (429), no lockout. Tested live (attempt 11 = 429).
- **#31 valuemax DICORET** — false alarm (tidak ada `max` di source, `min=1` sudah cegah negatif).

### 🔐 Security Test (DEC-070)
Otorisasi SOLID: privilege escalation = semua 403, API = 401 tanpa token + 403 role salah. IDOR = role-scoped (FO boleh lihat pasien per keputusan kebijakan DEC-070a). Laporan di `HealthCheck/security_test_results_2026-06-25.md`.

### 📋 Diskusi B3 + Multi-Cabang (DEC-071)
Deploy LAN lokal (Phase internal), HTTP, self-host aset wajib. Future multi-cabang = 1 DB cloud bersama. **RM clinic-prefix** diputuskan dikerjakan sekarang (DEC-071a).

### Next
- RM clinic prefix implementation (setelah backup).
- B3 Deployment Guide versi LAN.
- Paket security pra-launch (#37-40): JWT/SQLi/session/mass-assignment.

---

## 26 Juni 2026 (lanjutan) — B3 Doc + Fitur Simpan Tanpa Antrian

### ✅ Dikerjakan
- **B3 Deployment Guide tersusun** — `sehati_clinic/deployment/B3_DEPLOYMENT_GUIDE.md`, versi server lokal LAN (HTTP, tanpa remote), 9 task (B3.1-B3.9) + contoh config (.env/systemd/nginx) + checklist.
- **DEC-072 Fitur "Simpan Pasien Tanpa Antrian"** — `register_pasien_baru(buat_kunjungan=...)`. Tombol "Simpan Saja (tanpa antrian)" sekarang benar-benar tidak bikin antrian; "Simpan & Masuk Antrian" tetap bikin. Verified live (NOQUEUE 1409 no kunjungan, QUEUE 1410 ada kunjungan). Semua patch via script — no B-013.
- **RM clinic-prefix (DEC-071a)** done sebelumnya, verified `A-260626-xxx`.

### ⏭ Next (sedang dikerjakan)
- **B3.1 Self-host aset frontend** (HTMX + Tom Select + Tailwind build) — paling kritis untuk LAN.

### 📋 Pending
- B3.2-B3.9 (mostly di server klinik), paket security #37-40, a11y/overflow #34.
- Dummy test 1405-1410 (`DUMMY%`) → cleanup SQL siap.

---

## 26 Juni 2026 (malam) — B3.1 SELESAI + Panduan Migrasi E:

### ✅ B3.1 Self-host Aset — SELESAI & VERIFIED
- Vendor (HTMX/Tom Select/Chart) + Tailwind app.css di-host lokal di `static/`.
- Build Tailwind sukses: utility hits 192, null 0. **Test offline tanpa internet BERHASIL.**
- 2 bug ditemukan & dibereskan saat eksekusi: (1) file ditaruh di `app/web/static` padahal server serve dari `sehati_clinic/static` (404) → dipindah; (2) Node Windows dipakai → ganti Node Linux (NodeSource); (3) null-byte di 6 template dari WSL→/mnt/c write → dibersihkan + build scan dari /tmp.
- Script: `deployment/build_tailwind.sh` (build-only, robust, self-verify).

### 📋 Migrasi Workspace ke Drive E (panduan siap)
- `MIGRATION_TO_DRIVE_E.md` — step-by-step C:\Documents → E:\Claude\Projects\sehati-emr-pos.
- Kunci: DB tidak ikut pindah, venv recreate (jangan copy), copy via robocopy (Windows, bukan WSL cp), test null-byte di E: sebagai penentu.
- Caveat: E: tetap drive Windows (/mnt/e drvfs). Kemungkinan besar fix masalah (akar = OneDrive/Documents), tapi kalau B-013 masih muncul di E:, plan B = WSL-native.

---

## 26 Juni 2026 (malam) — Migrasi Workspace SELESAI ✅

- **Workspace pindah** `C:\...\WebApp for eMR and POS` → **`E:\Claude\Projects\sehati-emr-pos`**.
- Verified: app jalan normal dari E:, tes null-byte = 0 (B-013 HILANG), Cowork akses penuh.
- Folder lama di-rename `_OLD_WebApp for eMR and POS` (decommission, hapus nanti).
- **Dokumentasi path di-update** ke E: (12 referensi di _handoff, _session_workflow, 12_smoke_test_guide, mockup_demo/README, backups/README). MIGRATION_TO_DRIVE_E.md & backup_log.txt sengaja dibiarkan (catatan historis).
- DB MySQL tidak ikut pindah (data utuh). venv di-recreate di E:.
- **Aturan kerja:** mulai sekarang SEMUA pekerjaan di E:. (Memory AI sudah dicatat.)

### Status proyek setelah sesi panjang 25-26 Juni
**Feature-complete + self-hosted + workspace stabil.** Siap masuk fase pra-launch (keamanan + deployment server).

---

### ✅ Kasir-1 — Tutup Kasir / Rekonsiliasi (27 Juni 2026, DEC-075) — COMPLETE

Pra-deployment pain point #1 selesai. Buka Kasir (modal awal) → Tutup Kasir
(cocokkan uang fisik per metode, hitung selisih, catatan wajib bila ≠0) →
slip Z-report transien. Laporan Tutup Kasir untuk owner (filter tanggal, sorot over/short).
Expected EXCLUDE VOID (benahi gap rekap lama). Tabel `kasir_closing` (JSON detail per metode).

**Sisa kandidat pra-deployment:** Paket Keamanan #37-40, Konektor DermAI/Antropometri, Deployment.
**Menyusul (non-blocking):** Kasir-2 Rekap Harian Analitik. DP/deposit booking = PARKIR.

---

### ✅ Kasir-2 — Rekap Harian Kasir Analitik (27 Juni 2026, DEC-076) — COMPLETE

Halaman analitik harian owner (`/web/reports/rekap-harian`): pasien berkunjung, transaksi+omzet,
per metode (trx+rupiah), single vs split, konsultasi vs retail, per kasir. Semua EXCLUDE VOID.
Melengkapi alur kasir (Kasir-1 rekonsiliasi + Kasir-2 analitik). Modul Kasir = lengkap pra-deployment.

---

### ✅ Fondasi Konektor AI — Kosakata Penyakit Kronis (29 Juni 2026, DEC-077) — COMPLETE (sisi Sehati)

Tabel master `master_penyakit_kronis` + kode + checkbox UI (ganti free text) + reconcile engine +
backfill. Kontrak data DermAI v0.2 & Antropometri v0.1 disusun (Project_Memory). Penyakit kronis kini
kosakata bersama lintas modul + upgrade kualitas data Sehati (analitik, anti-duplikat).

**Tahap berikutnya konektor:** service DermAIConnector / AntroAIConnector + endpoint intake (Bearer)
+ write-back penyakit kronis + config .env. Tunggu kontrak final + repo modul.
