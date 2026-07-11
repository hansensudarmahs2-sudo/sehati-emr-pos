# Rancangan Struktur Program

> Disusun oleh: Claude (lead programmer)
> Berdasarkan: `jawaban gpt 120b page 1.txt` + analisa konsistensi DB + konteks klinik real

---

## Bagian 1: Review usulan GPT — apa yang saya setujui & apa yang saya ubah

GPT memberikan rancangan yang **secara umum sangat baik** untuk programmer berpengalaman. Tapi karena dokter tidak punya background coding dan timeline kita 1-2 bulan, saya akan ubah beberapa keputusan:

### ✅ Saya setujui dari usulan GPT:
- **FastAPI** sebagai web framework — cepat, dokumentasi otomatis (Swagger UI), tipe-safe.
- **SQLAlchemy 2.x** sebagai ORM + **Alembic** untuk migrasi schema.
- **JWT + RBAC** dengan dependency `role_required`.
- **Layered architecture** (models → repos → services → routers).
- **Pytest** untuk testing.
- **Pydantic** untuk validasi request/response.
- Pemisahan domain (patient, booking, visit, treatment, inventory, transaction).

### ⚠️ Yang saya ubah dari usulan GPT:

| Topik | Usulan GPT | Keputusan saya | Alasan |
|-------|------------|----------------|--------|
| **Async vs Sync** | Async SQLAlchemy | **Sync** SQLAlchemy untuk fase 1 | Async lebih kompleks, debugging susah untuk pemula, tidak ada bottleneck I/O signifikan di klinik kecil. Bisa di-async-kan nanti kalau perlu. |
| **Celery + Redis** | Wajib dari awal | **Tunda** ke Phase 3 | Overkill untuk klinik kecil. FastAPI BackgroundTasks cukup untuk send email/notif. Tambah Celery saat masuk fitur AI saja. |
| **Frontend** | Tidak dibahas | **HTMX + Jinja2 + Tailwind** | Lihat bagian 3 di bawah. |
| **Poetry** | Wajib | **uv** atau pip + `requirements.txt` | uv lebih cepat & sederhana untuk pemula. Poetry oke tapi setup lebih ribet. |
| **Auth library** | FastAPI-Users | **Custom JWT** | FastAPI-Users opinionated, susah disesuaikan dengan struktur `master_staf` yang sudah ada. Custom lebih lurus. |

---

## Bagian 2: Tech stack final

### Backend
```
Python              3.11+
FastAPI             ^0.110
SQLAlchemy          ^2.0 (sync mode)
Alembic             latest
PyMySQL / mysqlclient   connector MySQL
Pydantic            ^2.0
python-jose[cryptography]   JWT
passlib[bcrypt]     password hashing
python-multipart    file upload (foto)
Jinja2              template engine
pytest              testing
httpx               testing client
```

### Frontend (rekomendasi saya — penjelasan di bagian 3)
```
HTMX                3.x   — interaksi tanpa JavaScript ribet
Hyperscript         opsional — sintaks event sederhana
Tailwind CSS        3.x   — styling tanpa nulis CSS dari nol
Alpine.js           opsional — state lokal di komponen
```

### Tools
```
uv                  package manager (pengganti pip + virtualenv)
ruff                linter + formatter
git                 version control
DBeaver / phpMyAdmin    DB management (manual)
Insomnia / Postman     API testing manual
Docker              opsional, untuk deployment
```

---

## Bagian 3: Kenapa HTMX + Jinja2 untuk frontend?

Dokter bilang: *"akan ada frontend, tapi saya tidak tahu cara menghubungkan backend to frontend atau frontend menggunakan apa"*.

Saya punya 3 opsi yang biasa dipakai untuk medical/POS app. Saya pilihkan opsi yang **paling cocok untuk konteks dokter Hansen** (1-2 bulan, solo developer, akan dipakai real di klinik):

### Opsi A — React + FastAPI terpisah (modern SPA)
- ❌ Butuh nulis 2 codebase: backend Python + frontend JS/TS
- ❌ Setup ribet (Node.js, npm, build tools, CORS)
- ❌ Susah debug saat ada bug — 2 layer
- ❌ Untuk pemula, mengganggu fokus dari business logic
- ✅ Hasil paling "modern", bagus kalau punya tim besar

### Opsi B — Streamlit (admin panel cepat)
- ✅ Sangat cepat develop, semua di Python
- ❌ **TIDAK COCOK untuk POS / kasir** — input cepat, scan barcode, kasir butuh UX yang Streamlit tidak bisa kasih
- ❌ Tidak cocok untuk multi-user concurrent (FO + dokter + perawat + kasir bareng)
- 💡 Bisa dipakai HANYA untuk admin dashboard di Phase 2

### Opsi C — HTMX + Jinja2 + Tailwind ⭐ (rekomendasi saya)
- ✅ **Satu codebase Python** — backend + frontend di FastAPI yang sama
- ✅ Tidak perlu nulis JavaScript untuk 95% interaksi (form submit, refresh list, modal, dll)
- ✅ Cepat untuk POS — input form, table search, antrian update real-time pakai HTMX `hx-trigger="every 5s"`
- ✅ Hasilnya tetap modern dan responsive
- ✅ Mudah di-test karena server-rendered (tidak ada API mismatch)
- ⚠️ Kurang "wow factor" dibanding React, tapi untuk klinik internal tidak relevan
- ⚠️ Kalau nanti mau bikin mobile app native, perlu rewrite — tapi backend FastAPI tetap reusable sebagai API

**Keputusan:** Pakai Opsi C. Backend FastAPI render Jinja2 + HTMX untuk web internal (FO, kasir, dokter). API terpisah (JSON) tetap di-expose untuk Phase 2 (kiosk, mobile, web pasien).

---

## Bagian 4: Arsitektur layered

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 5 — Presentation                                     │
│  • Jinja2 templates (HTML)                                  │
│  • HTMX partials                                            │
│  • Static files (CSS, gambar)                               │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  LAYER 4 — API Routers (FastAPI)                            │
│  • Endpoint definitions (URL → function)                    │
│  • Request/response Pydantic schemas                        │
│  • Dependency injection (auth, db session)                  │
│  • Render template OR return JSON                           │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  LAYER 3 — Services (Business Logic)                        │
│  • Aturan bisnis: diskon membership, validasi alur klinik   │
│  • Orchestration multi-repo (1 service bisa pakai N repo)   │
│  • Transaksi DB di-manage di sini                           │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  LAYER 2 — Repositories (Data Access)                       │
│  • CRUD per tabel                                           │
│  • Query custom (search, filter, join)                      │
│  • TIDAK ada business logic                                 │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  LAYER 1 — Models (SQLAlchemy ORM)                          │
│  • Mapping tabel ke class Python                            │
│  • Definisi relationship                                    │
│  • Enum, mixin (TimestampMixin, SoftDeleteMixin)            │
└─────────────────────────────────────────────────────────────┘
                         │
                    ┌────▼────┐
                    │  MySQL  │
                    │db_sehati│
                    └─────────┘
```

**Aturan emas:** Layer atas hanya boleh tahu layer tepat di bawahnya. Router tidak boleh akses repo langsung — harus lewat service. Service tidak akses model langsung — harus lewat repo.

---

## Bagian 5: Struktur folder project

```
sehati_clinic/
│
├─ pyproject.toml                  # config project + dependencies
├─ uv.lock                         # lockfile uv
├─ .env.example                    # template env vars
├─ .env                            # secret (TIDAK di-commit ke git)
├─ .gitignore
├─ README.md
├─ Dockerfile                      # untuk deployment (Phase akhir)
├─ docker-compose.yml              # untuk local dev (DB, redis kalau perlu)
│
├─ alembic.ini
├─ migrations/                     # alembic migrations
│   ├─ versions/
│   └─ env.py
│
├─ app/
│   ├─ __init__.py
│   ├─ main.py                     # FastAPI entry point
│   ├─ config.py                   # Settings (DB URL, JWT secret)
│   │
│   ├─ core/
│   │   ├─ security.py             # hash password, JWT encode/decode
│   │   ├─ exceptions.py           # custom exceptions
│   │   ├─ logging.py              # logging config
│   │   └─ deps.py                 # FastAPI dependencies (get_db, get_user, role_required)
│   │
│   ├─ db/
│   │   ├─ base.py                 # Base = declarative_base()
│   │   ├─ session.py              # SessionLocal
│   │   └─ models/                 # 1 file per domain
│   │       ├─ staf.py
│   │       ├─ pasien.py
│   │       ├─ booking.py
│   │       ├─ kunjungan.py
│   │       ├─ pemeriksaan.py
│   │       ├─ treatment.py
│   │       ├─ inventory.py
│   │       ├─ transaksi.py
│   │       └─ audit.py
│   │
│   ├─ schemas/                    # Pydantic schemas
│   │   ├─ staf.py
│   │   ├─ pasien.py
│   │   └─ ...
│   │
│   ├─ repositories/
│   │   ├─ base.py                 # generic CRUD
│   │   ├─ staf_repo.py
│   │   ├─ pasien_repo.py
│   │   └─ ...
│   │
│   ├─ services/
│   │   ├─ auth_service.py
│   │   ├─ pasien_service.py
│   │   ├─ booking_service.py
│   │   ├─ kunjungan_service.py
│   │   ├─ treatment_service.py
│   │   ├─ inventory_service.py
│   │   ├─ kasir_service.py
│   │   ├─ membership_service.py
│   │   └─ audit_service.py
│   │
│   ├─ api/                        # router untuk endpoint JSON (API)
│   │   ├─ v1/
│   │   │   ├─ auth.py
│   │   │   ├─ pasien.py
│   │   │   ├─ booking.py
│   │   │   └─ ...
│   │
│   ├─ web/                        # router untuk halaman HTML (HTMX)
│   │   ├─ auth_page.py
│   │   ├─ fo_page.py              # halaman untuk FO
│   │   ├─ dokter_page.py          # halaman untuk Dokter
│   │   ├─ perawat_page.py
│   │   ├─ apoteker_page.py
│   │   ├─ kasir_page.py
│   │   ├─ owner_page.py
│   │   └─ admin_page.py
│   │
│   ├─ templates/                  # Jinja2 templates
│   │   ├─ base.html
│   │   ├─ auth/
│   │   ├─ fo/
│   │   ├─ dokter/
│   │   ├─ kasir/
│   │   └─ partials/               # HTMX partial responses
│   │
│   └─ static/
│       ├─ css/
│       │   └─ output.css          # tailwind compiled
│       ├─ js/
│       └─ img/
│
└─ tests/
    ├─ conftest.py
    ├─ unit/
    │   ├─ test_pasien_service.py
    │   ├─ test_membership_service.py
    │   └─ ...
    └─ integration/
        ├─ test_alur_pendaftaran.py
        └─ test_alur_kasir.py
```

---

## Bagian 6: Mapping role klinik → fitur web

Sesuai enum `master_staf.role`:

| Role | Halaman utama yang bisa diakses |
|------|--------------------------------|
| **FO** | Pencarian pasien, registrasi pasien baru, daftar booking hari ini, check-in pasien, batalkan booking, daftar pasien antri |
| **Dokter** | Daftar pasien antri konsultasi, form SOAP (anamnesa, diagnosa), buat resep, buat plan series treatment, otorisasi up-selling |
| **Perawat** | Daftar pasien antri treatment, start/end treatment, input antropometri, upload foto before/after, lihat plan treatment |
| **Apoteker** | Daftar resep pending, sediakan obat, update status resep |
| **Kasir** | Daftar transaksi pending, input pembayaran, cetak struk, tutup shift |
| **Admin** | CRUD master (produk, treatment, staff), laporan harian/bulanan |
| **Owner** | Dashboard global, semua laporan, audit log |
| **Superadmin** | Semua di atas + manajemen user, reset password |

Tiap role punya **halaman home sendiri** setelah login. RBAC mencegah role lain akses fitur bukan haknya.

---

## Bagian 7: Naming convention

- **Database:** Tetap pakai bahasa Indonesia (`pasien`, `kunjungan`, `tindakan`) — sudah konsisten.
- **Python class:** PascalCase English semantik tapi nama tetap mirroring tabel — `Pasien`, `Kunjungan`, `MasterTreatment`.
- **Python function/variable:** snake_case English untuk kata teknis, Indonesia untuk konsep domain — `get_pasien_by_rm()`, `create_booking_baru()`. Saya pilih konsisten **snake_case English** untuk semua function biar pemula gampang baca docs Python.
- **URL endpoint:** kebab-case English plural — `/api/v1/pasien`, `/api/v1/treatments/{id}/start`.
- **Template file:** snake_case — `pasien_list.html`, `kunjungan_detail.html`.
- **Variable HTML/Jinja:** snake_case — `{{ pasien.nama }}`.

---

## Bagian 8: Keamanan minimum yang akan saya implementasi

1. **Password storage:** bcrypt (via passlib), tidak pernah plaintext.
2. **JWT:** signed dengan secret yang di-rotate per 24 jam (refresh token).
3. **HTTPS only di production:** redirect HTTP → HTTPS.
4. **CSRF protection:** untuk form HTMX (token di session).
5. **SQL injection:** dicegah otomatis oleh SQLAlchemy ORM (selama tidak pakai raw SQL string concatenation).
6. **Rate limiting:** untuk login endpoint — max 5 attempts / menit (slowapi).
7. **Audit log:** semua aksi sensitif (void, batal booking, edit harga) dicatat.
8. **Backup:** database di-backup harian via mysqldump cron.
9. **Sensitive data:** PIN dokter di-hash juga (jangan plaintext).

---

## Bagian 9: Rencana untuk integrasi AI (Phase 3, bukan sekarang)

Saya catat di sini supaya tidak lupa, tapi **TIDAK akan dikerjakan** di 2 bulan pertama:

- Skin analysis pasien — Gemini Vision API
- USG kulit interpretation — Gemini Vision
- SOAP smart assist — Gemini text completion
- Chat AI member — Gemini chat dengan context dari `kunjungan` history

Persiapan struktur sekarang: saat desain `ai_service.py`, saya tinggalkan **interface kosong** supaya nanti tinggal isi tanpa rombak arsitektur.

---

## Kesimpulan

Stack yang akan kita pakai sederhana, modern, dan **realistis untuk timeline 2 bulan**:

```
Backend  : Python + FastAPI + SQLAlchemy + MySQL
Frontend : HTMX + Jinja2 + Tailwind (server-rendered)
Auth     : JWT + RBAC custom
Deploy   : Docker (akhir project)
```

Kalau dokter setuju dengan rencana ini, saya lanjut ke `03_WORK_PLAN.md` untuk detail timeline 8 minggu.
