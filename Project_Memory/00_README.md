# Project Memory — Multi-AI Context Hub

**Project:** Sehati Clinic — eMR (Electronic Medical Record) + POS (Point of Sale)
**Owner & Product Designer:** dr. Hansen Sudarma
**Lead Programmer (current AI assistant):** Claude (Anthropic)
**Reviewer AIs (planned):** OpenAI GPT, Ollama (local)
**Last updated:** 5 Juni 2026

---

## Tujuan folder ini

Folder `Project_Memory/` adalah **single source of truth** untuk konteks project yang dibaca oleh:

1. **AI yang sedang aktif develop** (Claude di sesi sekarang) — re-orient cepat di awal sesi
2. **AI lain untuk review** (OpenAI, Ollama) — pahami project tanpa baca seluruh codebase
3. **dr. Hansen** — referensi cepat business rules & arsitektur
4. **Developer baru** (kalau ada di masa depan) — onboarding

---

## Daftar Dokumen (Baca Berurutan untuk Konteks Baru)

| # | File | Isi | Audience |
|---|------|-----|----------|
| 00 | `00_README.md` | Index ini | Semua |
| 01 | `01_project_overview.md` | Executive summary 1 halaman | Quick context |
| 02 | `02_architecture.md` | Arsitektur layered (5 lapis) + tech stack | AI Developer |
| 03 | `03_database_schema.md` | Schema lengkap 26 tabel + relasi | AI Developer, dr. |
| 04 | `04_api_rules.md` | Convention REST API + RBAC | AI Developer |
| 05 | `05_coding_style.md` | Python style guide untuk project ini | AI Developer |
| 06 | `06_business_logic.md` | Alur klinik real & business rules | AI Reviewer, dr. |
| 07 | `07_known_issues.md` | Bug, limitation, todo | AI Reviewer |
| 08 | `08_roadmap.md` | Fase 1-5 timeline | dr., AI Reviewer |
| 09 | `09_glossary.md` | Istilah klinik + teknis | Semua |
| 10 | `10_ai_collaboration_guide.md` | Cara AI lain berinteraksi dengan project | AI Reviewer |
| 11 | `11_decisions_log.md` | Keputusan teknis penting dengan reasoning | AI Reviewer |
| 12 | `12_smoke_test_guide.md` | Panduan smoke test setelah deploy | AI Developer, dr. |
| — | `HealthCheck/` | **Health Check Protocol** — sistem audit kesehatan berkala (lihat section di bawah) | dr., AI Developer |
| — | `RawDataExport/` | **Owner Raw Data Export** — design + data dictionary 13 datasets (lihat section di bawah) | dr., AI Developer, Council AI |
| — | `reviews/` | Folder review dari AI reviewer (OpenAI, Ollama) | AI Reviewer |

---

## Health Check Protocol

Sehati Clinic punya **Health Check Protocol** terdokumentasi di `HealthCheck/` untuk audit kesehatan sistem berkala (DB integrity, backend audit gaps, security/PII, frontend per role).

**Entry point:** `HealthCheck/00_PROTOCOL.md`

**Magic command words** — saat dr. Hansen ketik salah satu kalimat ini, AI harus baca `HealthCheck/00_PROTOCOL.md` dulu lalu jalankan workflow yang sesuai:

| Magic Command | Action AI |
|---------------|-----------|
| "jalankan health check" / "check up sistem" / "audit kesehatan" | Run `HealthCheck/scripts/run_health_check.py --mode weekly` lalu baca log hasil dan ringkas |
| "check up DB" / "audit database" | Run `HealthCheck/scripts/db_integrity.py` saja |
| "check up backend" / "audit backend" | Run `HealthCheck/scripts/audit_gaps.py` saja |
| "check up security" / "audit security" / "scan PII" | Run `HealthCheck/scripts/pii_scan.py` saja |
| "frontend check manual" / "manual UAT" | Buka `HealthCheck/03_frontend_per_role.md`, bantu dr. Hansen track progres centangnya |
| "health check post-deploy" | Run dengan flag `--mode post-deploy` setelah deploy fitur besar |

**Jangan** buat protokol check-up sendiri dari nol. SELALU baca `HealthCheck/00_PROTOCOL.md` dulu sebagai konstitusi sistem check.

**Hasil run** otomatis disimpan ke `HealthCheck/logs/YYYY-MM-DD_*.md` dengan format konsisten (overall summary, per-section breakdown, trend vs run sebelumnya, action items). AI harus baca log file, ringkas ke dr. Hansen, dan promote finding CRITICAL/HIGH ke `07_known_issues.md`.

---

## Raw Data Export Module (C2)

Sehati Clinic punya modul **Owner Raw Data Export** untuk feed data raw/semi-raw ke modul Data Analyst (proyek terpisah) → Council AI (Codex project). Design + dictionary tersimpan di `RawDataExport/`.

**Entry points:**
- Design doc: `RawDataExport/00_DESIGN.md` (Revisi 1.1 APPROVED, 15 keputusan locked)
- Data Dictionary: `RawDataExport/01_DATA_DICTIONARY.md` (13 datasets × ~150 kolom)
- Live endpoints (Owner login required):
  - `GET /web/export` — landing UI dengan 3 cards
  - `GET /web/export/pack/{weekly,monthly,custom}.zip` — Pack download
  - `GET /web/export/dataset/{name}/download.{csv,json}` — per-dataset
  - `GET /web/export/dictionary.json` — programmatic schema (Council AI self-discovery)
  - `GET /web/export/dictionary.md` — Markdown text response

**Magic command words** — saat dr. Hansen ketik salah satu kalimat ini, AI harus baca `RawDataExport/00_DESIGN.md` + `01_DATA_DICTIONARY.md` dulu lalu jalankan workflow yang sesuai:

| Magic Command | Action AI |
|---------------|-----------|
| "export weekly" / "export mingguan" | Direct ke endpoint `/web/export/pack/weekly.zip` (default ending_date=today). Owner login required. |
| "export monthly" / "export bulanan" | Direct ke `/web/export/pack/monthly.zip` |
| "export custom dari X sampai Y" | Direct ke `/web/export/pack/custom.zip?tgl_dari=X&tgl_sampai=Y` |
| "export dataset {name}" | Direct ke `/web/export/dataset/{name}/download.csv` (advanced flow) |
| "lihat dictionary" / "data dictionary" | Baca `RawDataExport/01_DATA_DICTIONARY.md` + ringkas schema yang Bapak minta |
| "cek schema dataset {name}" | Fetch endpoint `dictionary.json` lalu cari entry name |
| "list 13 dataset" / "dataset apa saja" | Baca DATASET_REGISTRY di `app/services/export_service.py` |

**Role gate ketat:** **Owner ONLY** (decision #1). Superadmin/Admin defer ke phase berikutnya kalau perlu.

**PII default:** `mask_pii=False`. Selalu rekomendasikan Bapak centang `mask_pii=true` saat export untuk AI external / 3rd party. Field yang affected: `nama_pasien` (visits, transactions_header, membership) + `nama_dokter` (medical_soap).

**Jangan** buat dataset baru atau ubah schema tanpa baca design doc dulu — semua 15 keputusan sudah locked dengan reasoning di DEC-046.

---

## Quick Start untuk AI Baru

Kalau Anda adalah AI yang baru pertama kali touch project ini:

1. **Baca `01_project_overview.md` dulu** (5 menit) — pahami konteks bisnis & teknis.
2. Baca `02_architecture.md` (10 menit) — pahami struktur kode.
3. Baca `06_business_logic.md` (15 menit) — pahami aturan klinik real.
4. Baca `10_ai_collaboration_guide.md` (5 menit) — pahami role Anda.
5. Bila perlu, deep-dive ke dokumen specific (`03_`, `04_`, `05_`).

Setelah 35-40 menit reading, Anda harus punya konteks penuh untuk kontribusi.

---

## Status Project Saat Ini

```
Phase: 1 (MVP — backend + frontend internal) — ~99.9% selesai
Backend status: 22 services, audit log terintegrasi semua mutating ops
Frontend status: ~85 routes, 110+ templates, dashboard per role, semua modul operasional + reports + raw data export
Deployment status: Lokal (development, pre-soft-launch)

Update 5 Juni 2026 (end of session):
  - C1 Reports per role: Omzet Bulanan + Top Treatment + Kinerja Dokter + Audit Log Viewer
  - C2 Owner Raw Data Export: 13 datasets + Pack assembly + Data Dictionary (149 cols)
  - Excel Historical Import: 2,035 rows Mar-Mei 2026 real data tersedia untuk testing
  - Health Check Protocol Lite: weekly cadence + 4 baseline findings cleared
  - Plan A: 7 baseline finding fixed (6 DEC-030 violations + 1 bare except)
  - DEC-043 to DEC-046 ditambahkan di decisions log

Next milestone (sisa Phase 1):
  - B Soft Launch Prep: backup script (mysqldump cron), user manual PDF per role,
    deployment guide (uvicorn systemd + nginx + .env management)
```

---

## File Project Lain (Di Luar Folder Ini)

Project ini punya beberapa dokumen lain di root folder yang juga relevan:

- `../00_README.md` — index project utama
- `../01_ANALISA_DATABASE.md` — analisa awal konsistensi DB
- `../02_STRUKTUR_PROGRAM.md` — rancangan struktur awal
- `../03_WORK_PLAN.md` — roadmap 8 minggu detail
- `../04_REVIEW_KODE_SAAT_INI.md` — review kode dokter sebelum refactor
- `../05_KEPUTUSAN_FINAL.md` — keputusan diskusi 27 April 2026 (legacy reference)
- `../Tables_in_db_sehati.txt` — schema asli + dokumentasi alur klinik
- `../Current python code main_api.txt` — kode kasar dokter 1.892 baris (legacy reference)
- `../sehati_clinic/` — codebase Python aktif

Folder `Project_Memory/` ini berisi **versi terbaru & consolidated** dari semua dokumen di atas, plus dokumen baru untuk multi-AI collaboration.
