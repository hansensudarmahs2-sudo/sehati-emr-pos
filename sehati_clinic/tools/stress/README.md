# Stress Test Framework — Sehati Clinic

> Multi-fase stress test untuk validasi sistem sebelum launch.
> Reference: `outputs/PRE_LAUNCH_ROADMAP.md` Decision B.

## Strategi Database

**db_sehati** (PRODUCTION) — TIDAK PERNAH disentuh stress test. Tetap jalan di uvicorn port 8000.

**db_sehati_test** (TEST) — DB terpisah, di-seed dummy data, di-attach ke uvicorn ke-2 di port 8001.

Risiko = 0 karena production database tidak pernah jadi target test.

## Pre-requisite Setup (sekali saja)

### Step 1 — Buat db_sehati_test + import schema

Run di terminal WSL:

```bash
cd ~/path/ke/sehati_clinic

# 1. Generate fresh schema dump dari db_sehati
sudo mysqldump --no-data --routines --triggers --skip-comments db_sehati > /tmp/schema_test.sql

# 2. Create DB baru + grant access ke klinik_dev
sudo mysql -e "
CREATE DATABASE IF NOT EXISTS db_sehati_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON db_sehati_test.* TO 'klinik_dev'@'localhost';
FLUSH PRIVILEGES;
"

# 3. Import schema
sudo mysql db_sehati_test < /tmp/schema_test.sql

# 4. Verify (harusnya ~26 tabel)
sudo mysql -e "USE db_sehati_test; SHOW TABLES;" | wc -l
```

### Step 2 — Seed dummy data

```bash
# Pastikan venv active
source .venv/bin/activate

# Run seed (idempotent — aman di-rerun)
python tools/stress/02_seed_test_data.py
```

Output yang diharapkan:
```
[seed] Connecting to db_sehati_test...
[seed] master_klinik_config: 1 row
[seed] master_staf: 6 rows (1 owner + 2 dokter + 1 fo + 1 kasir + 1 perawat)
[seed] master_treatment: 15 rows (10 single + 5 series)
[seed] master_produk: 50 rows (25 obat + 25 retail)
[seed] master_membership: 4 levels
[seed] pasien: 100 dummy
[seed] DONE in 2.3s
```

### Step 3 — Start test uvicorn (terminal terpisah)

**TERMINAL BARU** (production tetap di terminal lain):

```bash
cd ~/path/ke/sehati_clinic
source .venv/bin/activate

# Override DB_NAME via env var (pydantic-settings akan honor)
export DB_NAME=db_sehati_test

# Start uvicorn di port 8001
uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Verifikasi: buka http://localhost:8001 — harusnya login page, login dengan `superadmin / admin123` (test DB).

## Run Fase 1 — Smoke Test (Single User)

Setelah pre-req setup selesai dan test uvicorn jalan di :8001:

```bash
# Terminal ke-3
source .venv/bin/activate
python tools/stress/03_fase1_smoke.py
```

Output: 
- Real-time progress ke stdout
- Hasil ringkas di console
- Full report: `outputs/STRESS_TEST_FASE1_REPORT_<timestamp>.md`

## File Index

| File | Tujuan |
|------|--------|
| `README.md` | Panduan ini |
| `01_setup_test_db.sh` | Helper untuk setup DB (opsional, manual juga OK) |
| `02_seed_test_data.py` | Seed dummy data idempotent |
| `03_fase1_smoke.py` | Fase 1 — Single user smoke test |
| `04_fase2_locust.py` | (TBD) Fase 2 — 3 user concurrent via Locust |
| `_helpers.py` | Shared helpers (login session, faker, metrics) |

## Cleanup

Untuk reset state test DB tanpa drop:

```bash
python tools/stress/02_seed_test_data.py --reset
```

Untuk full drop:

```bash
sudo mysql -e "DROP DATABASE db_sehati_test;"
```

## Catatan

- Test uvicorn :8001 dan production uvicorn :8000 bisa jalan paralel — beda DB, beda port, no conflict
- Stop test uvicorn cukup Ctrl+C di terminal-nya — production tidak terganggu
- Stress test seharusnya dijalankan **diluar jam operasional klinik** untuk safety (mesin yang sama dengan production)
- Reference: `outputs/PRE_LAUNCH_ROADMAP.md` untuk full plan Fase 1-4
