# Project Overview — Sehati Clinic eMR + POS

> Executive summary 1 halaman. Cukup untuk dapat konteks bisnis & teknis.

---

## Konteks Bisnis

**Klinik Sehati** adalah klinik kecantikan (aesthetic / dermatology) milik dr. Hansen yang menangani:
- Konsultasi dokter
- Treatment (facial, IPL, laser, dll)
- Penjualan produk perawatan kulit (krim, sabun, serum, dll)
- Membership system (saat ini 2 tier: VIP, VVIP — rencana 3 tier: Basic, Gold, Platinum)

**Skala klinik:** kecil-menengah. 8 staf aktif (FO, dokter, perawat, apoteker, kasir, admin, owner, superadmin).

**Workflow inti:**
```
Pasien datang → FO daftarkan → Dokter SOAP → (Perawat treatment OR Apoteker resep) 
              → Kasir bayar → (Apoteker serahkan obat) → Selesai
```

---

## Konteks Teknis

**Apa yang sudah ada sebelum project ini:**
- Database MySQL `db_sehati` dengan 21 tabel (dipakai aplikasi lama dokter — kode kasar di file `main_api.py`, ~1.892 baris)
- Backend Python FastAPI dasar (login, FO, kasir, dokter, perawat module — tapi messy, security issues)
- Tidak ada frontend

**Apa yang sedang dibangun (project ini):**
- Backend FastAPI **refactored** dengan layered architecture (5 layer)
- Migrasi DB: 4 file SQL fix kritis + tambah 5 tabel baru (membership system, audit log)
- Frontend HTMX + Jinja2 + Tailwind CSS (planned Minggu 7)
- Deployment lokal di klinik (rencana cloud di Phase 2)

**Tech Stack:**
- Python 3.11+
- FastAPI 0.110+
- SQLAlchemy 2.x (sync mode, bukan async)
- Alembic untuk migrasi
- MySQL 8.0 (`db_sehati`)
- bcrypt + python-jose untuk auth (JWT)
- pytest untuk testing
- `uv` sebagai Python package manager

---

## Tim & Peran

| Role | Person/Entity | Tanggung Jawab |
|------|---------------|----------------|
| Owner & Product Designer | **dr. Hansen** | Business rules, prioritas fitur, user testing, UX feedback |
| Lead Programmer | **Claude (Anthropic)** | Tulis kode, arsitektur, code review, testing |
| Reviewer AI (planned) | OpenAI GPT | Independent code review, catch blind spots |
| Reviewer AI (planned) | Ollama (local) | Privacy-sensitive review (kalau ada data sensitif) |

**dr. Hansen tidak punya background coding** — dia product designer & user tester. Coding 100% dilakukan AI dengan supervisi domain expert dokter.

---

## Phase Plan

| Phase | Lingkup | Status |
|-------|---------|--------|
| **Phase 1** | MVP: backend lengkap + frontend internal (HTMX) + deploy lokal | ⏳ In Progress (Minggu 3-4 dari 8) |
| Phase 2 | 3-tier membership, paket promo, booking online, kiosk, foto module, WA/Telegram notifikasi | 📋 Planned |
| Phase 3 | AI integration (Gemini): skin analysis, USG kulit, SOAP smart assist, chat AI member | 📋 Planned |
| Phase 4+ | Mobile app native, multi-cabang | 📋 Future |

---

## Filosofi Project

1. **Pertahankan logika business dr. Hansen** yang sudah teruji — refactor struktur, bukan rewrite logic.
2. **Pemula-friendly** — komentar bahasa Indonesia di domain code, English di technical.
3. **Modular & testable** — layered architecture (models → repositories → services → API).
4. **Security non-negotiable** — bcrypt password, JWT signed, RBAC, audit log untuk aksi sensitif.
5. **Real klinik, real data, real consequences** — sistem ini akan dipakai untuk catat pasien sungguhan, jadi harus reliable.

---

## Key References

- Arsitektur detail → `02_architecture.md`
- Schema DB → `03_database_schema.md`
- Aturan bisnis klinik → `06_business_logic.md`
- Apa yang sudah & belum jalan → `07_known_issues.md`
- Timeline → `08_roadmap.md`
