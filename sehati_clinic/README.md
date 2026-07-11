# Sehati Clinic — Backend (FastAPI)

Sistem eMR (Electronic Medical Record) + POS (Point of Sale) untuk Klinik dr. Hansen.

**Stack:** Python 3.11+ • FastAPI • SQLAlchemy 2.x • MySQL • Alembic
**Untuk frontend nanti:** HTMX + Jinja2 + Tailwind CSS

---

## Quick Start

### 1. Install `uv` (Python package manager)

`uv` adalah pengganti `pip + venv` yang 10× lebih cepat. Install sekali saja:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc   # atau restart terminal
uv --version       # verifikasi
```

### 2. Setup project

```bash
# Dari folder project
cd ~/sehati_clinic

# Install Python version yang dibutuhkan + buat venv
uv python install 3.11
uv venv

# Install dependencies (otomatis pakai venv yang baru dibuat)
uv pip install -e ".[dev]"

# Setup config
cp .env.example .env
# Edit .env — terutama JWT_SECRET_KEY (generate dengan command di .env.example)
```

### 3. Run server

```bash
# Aktivasi venv
source .venv/bin/activate

# Start server (auto-reload saat file berubah)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Akses:
- **API root:** http://localhost:8000
- **Swagger UI:** http://localhost:8000/docs
- **Health check:** http://localhost:8000/health
- **DB health:** http://localhost:8000/health/db (test koneksi MySQL)

### 4. Run tests

```bash
pytest
```

---

## Struktur Folder

```
sehati_clinic/
│
├── pyproject.toml          # metadata + dependencies (managed by uv)
├── .env.example            # template environment config
├── .env                    # actual config (JANGAN commit)
├── .gitignore
├── README.md               # ini
├── alembic.ini             # alembic config (di-generate via `alembic init`)
│
├── app/
│   ├── __init__.py
│   ├── main.py             # FastAPI entry point
│   ├── config.py           # Pydantic Settings (load .env)
│   │
│   ├── core/               # security, exceptions, dependencies
│   ├── db/
│   │   ├── base.py         # SQLAlchemy declarative base
│   │   ├── session.py      # engine + SessionLocal + get_db()
│   │   └── models/         # ORM models (1 file per domain) — Minggu 2
│   │
│   ├── schemas/            # Pydantic request/response — Minggu 2+
│   ├── repositories/       # CRUD per tabel — Minggu 2+
│   ├── services/           # Business logic — Minggu 3+
│   ├── api/v1/             # API routers (JSON) — Minggu 3+
│   ├── web/                # Web routers (HTML/HTMX) — Minggu 7
│   ├── templates/          # Jinja2 templates — Minggu 7
│   └── static/             # CSS, JS, images — Minggu 7
│
├── migrations/             # Alembic migrations — di-init di Minggu 1
│   └── versions/
│
└── tests/
    ├── test_smoke.py       # basic smoke test
    ├── unit/               # unit tests — Minggu 2+
    └── integration/        # integration tests — Minggu 3+
```

---

## Development Workflow

### Saat tambah dependency baru

```bash
uv pip install <package_name>
# Lalu tambah manual ke pyproject.toml di section [project.dependencies]
# Lalu re-install editable:
uv pip install -e ".[dev]"
```

### Migrasi database — Alembic = CANONICAL (A11)

> **Sumber kebenaran skema = `migrations/` (Alembic).** Folder `migrations_sql/` hanya
> arsip/referensi SQL historis dan **BUKAN** yang dijalankan untuk membentuk skema.
> Selalu buat/ubah skema lewat Alembic; jangan menambah `.sql` manual di `migrations_sql/`
> sebagai jalur migrasi. `alembic upgrade head` adalah state resmi DB.

### Saat tambah ORM model baru

1. Buat file di `app/db/models/<domain>.py`
2. Import di `app/db/models/__init__.py` (+ tambah ke `__all__`)
3. Generate migration: `alembic revision --autogenerate -m "add table xxx"`
4. Review SQL di `migrations/versions/...py`
5. Apply: `alembic upgrade head`

### Saat reset DB ke kondisi awal

```bash
# Restore dari backup post-migrasi
sudo mysql db_sehati < ~/backup_post_migrasi_2026-05-03.sql
```

---

## Tech Decisions

Detail di `../05_KEPUTUSAN_FINAL.md`:
- Sync SQLAlchemy (bukan async) — lebih sederhana, tidak ada bottleneck di skala klinik
- JWT untuk auth — sesuai logika anchor shift dokter
- bcrypt untuk password — sudah di-hash di migrasi DB
- HTMX + Jinja2 untuk frontend (Minggu 7) — single codebase Python

---

## Troubleshooting

**`pip install` gagal di Ubuntu 24.04:**
- Pakai `uv pip install` (uv handle venv otomatis), atau aktivasi venv dulu: `source .venv/bin/activate`
