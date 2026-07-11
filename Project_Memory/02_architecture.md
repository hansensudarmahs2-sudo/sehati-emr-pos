# Architecture — Sehati Clinic Backend

> Arsitektur layered + tech stack detail. Untuk AI Developer.

---

## Tech Stack (Final)

### Backend
| Layer | Choice | Reason |
|-------|--------|--------|
| Language | **Python 3.11+** | Modern syntax (`Mapped[...]`, `match`, dll), wide ecosystem |
| Web framework | **FastAPI 0.110+** | Type-safe, auto OpenAPI/Swagger, async-ready |
| ORM | **SQLAlchemy 2.x (sync)** | Mature, type-safe new syntax. Sync (bukan async) — sederhana untuk pemula, no bottleneck di skala klinik |
| Migrations | **Alembic** | Standard SQLAlchemy migration tool |
| Database | **MySQL 8.0** | Already exist (`db_sehati`), production-grade |
| DB Driver | **PyMySQL** | Pure Python, no compilation needed |
| Validation | **Pydantic 2.x** | Match FastAPI ecosystem, fast |
| Auth | **JWT (python-jose) + bcrypt** | Industry standard. JWT sesuai logika anchor shift dokter (6 jam expiry) |
| Package manager | **uv** | 10× faster than pip, modern |
| Testing | **pytest + httpx** | Standard |
| Linter | **ruff** | Fast, all-in-one |

### Frontend (Planned Minggu 7)
| Layer | Choice | Reason |
|-------|--------|--------|
| Templates | **Jinja2** | Server-rendered, 1 codebase Python |
| Interactivity | **HTMX** | No-JS interaction, perfect for internal apps |
| CSS | **Tailwind CSS** | Utility-first, fast to prototype |
| Optional state | **Alpine.js** | Lightweight if needed |

### Deployment
| Layer | Choice | Reason |
|-------|--------|--------|
| Container | **Docker + docker-compose** | Reproducible setup |
| Reverse proxy | **nginx** | HTTPS termination |
| Server | **gunicorn + uvicorn workers** | Production WSGI |

---

## Layered Architecture (5 Layers)

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 5 — Presentation (Phase 1 minggu 7)                  │
│  app/templates/  &  app/static/                             │
│  • Jinja2 HTML templates                                    │
│  • HTMX partials                                            │
│  • Tailwind CSS                                             │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  LAYER 4 — API / Web Routers                                │
│  app/api/v1/  (JSON endpoints)                              │
│  app/web/     (HTML endpoints — Phase 1 minggu 7)           │
│  • URL → function mapping                                   │
│  • Dependency injection (auth, db, role_required)           │
│  • Render template OR return JSON                           │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  LAYER 3 — Services (Business Logic)                        │
│  app/services/                                              │
│  • Aturan bisnis (diskon membership, validasi alur)         │
│  • Orchestration multi-repo (1 service → N repo)            │
│  • Transaction management (commit/rollback)                 │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  LAYER 2 — Repositories (Data Access)                       │
│  app/repositories/                                          │
│  • CRUD per tabel                                           │
│  • Query custom (search, filter, join)                      │
│  • NO business logic                                        │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  LAYER 1 — ORM Models                                       │
│  app/db/models/                                             │
│  • SQLAlchemy mapping ke tabel MySQL                        │
│  • Enums, relationships                                     │
└─────────────────────────────────────────────────────────────┘
                         │
                    ┌────▼─────┐
                    │  MySQL   │
                    │db_sehati │
                    └──────────┘
```

**Aturan layering ketat:**
- Router → Service → Repository → Model.
- **Layer atas hanya boleh tahu layer tepat di bawah-nya.**
- Router **TIDAK boleh** akses Repository atau Model langsung.
- Service **TIDAK boleh** akses Model langsung (kecuali untuk construct object yang akan dikirim ke Repository).

---

## Struktur Folder Lengkap

```
sehati_clinic/
│
├── pyproject.toml              # metadata + dependencies (managed by uv)
├── uv.lock                     # lockfile
├── .env.example                # template env
├── .env                        # secret config (NOT in git)
├── .gitignore
├── README.md
├── alembic.ini                 # alembic config
│
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI entry point + router registration
│   ├── config.py               # Pydantic Settings (load .env)
│   │
│   ├── core/                   # Reusable infrastructure
│   │   ├── security.py         # bcrypt + JWT
│   │   └── deps.py             # FastAPI deps (get_db, get_current_user, role_required)
│   │
│   ├── db/
│   │   ├── base.py             # SQLAlchemy declarative Base
│   │   ├── session.py          # engine + SessionLocal + get_db()
│   │   └── models/             # 1 file per domain
│   │       ├── __init__.py     # import semua untuk Alembic
│   │       ├── _enums.py       # ENUM Python (match dengan MySQL)
│   │       ├── staf.py
│   │       ├── pasien.py
│   │       ├── booking.py
│   │       ├── kunjungan.py    # kunjungan + antropometri + foto + resep + tindakan + pemeriksaan
│   │       ├── treatment.py    # master + komponen + rencana + iterasi
│   │       ├── inventory.py
│   │       ├── produk.py
│   │       ├── transaksi.py
│   │       ├── membership.py
│   │       └── audit.py
│   │
│   ├── schemas/                # Pydantic request/response
│   │   ├── auth.py
│   │   ├── staf.py
│   │   ├── pasien.py           # incl. AlergiCreate, PenyakitKronisCreate, AntropometriCreate
│   │   └── ...
│   │
│   ├── repositories/           # CRUD per tabel
│   │   ├── staf_repo.py
│   │   ├── pasien_repo.py
│   │   ├── kunjungan_repo.py
│   │   └── ...
│   │
│   ├── services/               # Business logic
│   │   ├── auth_service.py
│   │   ├── staf_service.py
│   │   ├── pasien_service.py
│   │   ├── audit_service.py
│   │   └── ...
│   │
│   ├── api/                    # JSON API endpoints
│   │   ├── v1/
│   │   │   ├── auth.py
│   │   │   ├── staf.py
│   │   │   ├── pasien.py       # (planned)
│   │   │   └── ...
│   │
│   ├── web/                    # HTML endpoints (Phase 1 minggu 7)
│   │   └── (empty for now)
│   │
│   ├── templates/              # Jinja2 (Phase 1 minggu 7)
│   └── static/                 # CSS, JS, images
│
├── migrations/                 # Alembic
│   ├── env.py                  # custom — load DB URL dari .env
│   ├── script.py.mako
│   └── versions/
│       └── 20260503_0000_baseline_existing_schema.py
│
└── tests/
    ├── conftest.py
    ├── test_smoke.py
    ├── unit/
    │   └── test_security.py
    └── integration/
        └── test_auth_endpoints.py
```

---

## Dependency Injection Flow

```python
# Contoh endpoint:
@router.post("/pasien/baru")
def register_pasien(
    payload: PasienBaruRequest,
    db: DbSession,                              # ← Depends(get_db)
    current_user: CurrentUser,                  # ← Depends(get_current_user)
    _: Annotated[..., Depends(role_required(StafRoleEnum.FO))],
):
    service = PasienService(db)
    return service.register_pasien_baru(payload, id_staf_fo=current_user.id_staf)
```

**Chain:**
1. FastAPI inject `db` (SQLAlchemy Session) via `get_db()`.
2. FastAPI inject `current_user` (MasterStaf) via `get_current_user()` — yang decode JWT.
3. `role_required(...)` validate user role, throw 403 kalau tidak match.
4. Router instantiate Service dengan db.
5. Service orchestrate repositories untuk lakukan business logic.
6. Service commit transaction (atau rollback).
7. Router return response (Pydantic auto-serialize).

---

## Transaction Management

- **1 request = 1 session = 1 transaction** (pattern Unit of Work).
- Session di-yield oleh `get_db()`, otomatis close setelah response sent.
- Service yang panggil `db.commit()` atau `db.rollback()` di akhir operasi.
- Exception unhandled → SQLAlchemy auto-rollback di session close.

**Penting:** Multi-table operations (misal register pasien yang touch 5 tabel) **HARUS** dalam 1 service method yang call commit di akhir. Jangan commit per-INSERT.

---

## Security Model

| Aspect | Implementation |
|--------|----------------|
| Password storage | bcrypt (rounds=12), auto-truncate 72 bytes |
| Session | JWT signed (HS256), 6 jam expiry |
| Authentication | Bearer token via `Authorization: Bearer <jwt>` |
| Authorization | RBAC via `role_required(...)` dependency |
| Force logout | Set `is_logged_in=False` + `token_expired_at=NULL` (cek di `get_current_user`) |
| SQL Injection | Prevented by SQLAlchemy ORM (no raw string concat) |
| CORS | Whitelist domain di `settings.cors_allowed_origins` |
| HTTPS (production) | nginx reverse proxy + Let's Encrypt |
| Audit log | Tabel `audit_log` untuk aksi mutating sensitif |

---

## Important Conventions

1. **Naming:**
   - DB tables: snake_case Indonesia (`master_staf`, `pasien_alergi`)
   - Python classes: PascalCase (`MasterStaf`, `PasienAlergi`)
   - Functions/variables: snake_case English (`get_by_id`, `register_pasien_baru`)
   - URL endpoints: kebab-case English (`/api/v1/pasien/baru`)

2. **File organization:** 1 domain = 1 file. Saat tabel banyak (kunjungan punya 6 turunan), boleh group dalam 1 file (`kunjungan.py`).

3. **Enum:** Python enum di `app/db/models/_enums.py`, value-nya HARUS match dengan ENUM di MySQL (case-sensitive).

4. **Re-exports:** `app/db/models/__init__.py` re-export semua model + enum supaya import sederhana:
   ```python
   from app.db.models import Pasien, StafRoleEnum  # ← bukan from app.db.models.pasien import ...
   ```

5. **`get_db()` dependency** untuk semua endpoint yang touch DB. Jangan create session manual di router.

---

## What's NOT Yet Implemented

Lihat `07_known_issues.md` untuk gaps & todo list lengkap.
