# Project Sehati Clinic — eMR + POS

**Owner / Product Designer:** dr. Hansen
**Lead/Main Programmer:** Claude (AI assistant)
**Tanggal mulai:** 27 April 2026
**Target MVP usable di klinik:** 8 minggu (akhir Juni 2026)

---

## Cara membaca dokumen ini

Folder project ini berisi 6 dokumen utama. Baca **berurutan** kalau ini pertama kali:

| File | Isi | Kapan dibaca |
|------|-----|--------------|
| `00_README.md` | Index ini | Pertama |
| `01_ANALISA_DATABASE.md` | Review konsistensi DB sehati, masalah yang saya temukan, rekomendasi perbaikan schema | Sebelum mulai coding |
| `02_STRUKTUR_PROGRAM.md` | Review usulan GPT, tech stack final, arsitektur, struktur folder | Sebelum mulai coding |
| `04_REVIEW_KODE_SAAT_INI.md` | Review 1.892 baris kode dokter di `main_api.txt` — masalah security, bug, dan logika yang harus dipertahankan | Sebelum mulai refactor |
| **`05_KEPUTUSAN_FINAL.md`** ⭐ | **Single source of truth** — semua keputusan diskusi dr. Hansen × Claude (27 April 2026). Kalau ada konflik antar dokumen, ini yang menang. | **Selalu** rujuk saat ragu |
| `03_WORK_PLAN.md` | Roadmap 8 minggu, milestone per minggu, deliverable, pembagian peran | Setiap minggu untuk tracking |

File asli dari dokter tetap disimpan (referensi sejarah):
- `Tables_in_db_sehati.txt` — skema database + dokumentasi alur klinik
- `jawaban gpt 120b page 1.txt` — usulan struktur dari GPT (referensi)
- `Current python code main_api.txt` — kode FastAPI dokter saat ini (1.892 baris, 27 endpoint)

---

## Pembagian peran (kesepakatan)

**dr. Hansen (Anda):**
- Product designer — menentukan alur klinik, business rules, prioritas fitur
- User tester — coba sistem di kondisi nyata
- UI/UX tester — kasih feedback bagian yang membingungkan staf
- Domain expert — perantara antara saya (programmer) dan kondisi lapangan
- Decision maker — keputusan akhir soal fitur, prioritas, trade-off

**Claude (saya):**
- Main programmer — tulis kode backend + frontend
- Database analyst — analisa konsistensi, rekomendasi perbaikan schema
- System architect — desain arsitektur, pilih library, struktur folder
- Code reviewer & tester — unit test, integration test
- Dokumentator — semua keputusan teknis didokumentasikan

---

## Aturan kerja yang akan saya pegang

1. **Bahasa Indonesia** untuk komunikasi, **English** untuk terminologi teknis & nama variabel/fungsi.
2. Setiap fitur baru = ada **demo singkat** untuk dokter coba dulu sebelum saya lanjut ke fitur berikutnya.
3. Setiap minggu ada **deliverable yang bisa dijalankan** — tidak ada "minggu hilang" tanpa hasil.
4. Saya tidak akan asumsi business rule sendiri — kalau ragu, saya tanya.
5. Kode backend selalu **berlandaskan database yang sudah ada**, bukan saya bikin schema baru tanpa diskusi.
6. Production deployment hanya setelah Phase 1 lulus testing dokter.

---

## Tech stack ringkas (detail di `02_STRUKTUR_PROGRAM.md`)

- **Backend:** Python 3.11+ • FastAPI • SQLAlchemy 2.x (async) • Alembic • MySQL
- **Frontend:** HTMX + Jinja2 + Tailwind CSS (rekomendasi saya untuk fase 1, alasan lihat dok 02)
- **Auth:** JWT + RBAC (role-based, sesuai enum `master_staf.role`)
- **Dev tools:** Poetry, pytest, Docker (opsional di akhir)
- **AI integration (Phase 3):** Google Gemini API

---

## Status project saat ini

**Kondisi:** Dokter sudah menulis 1.892 baris kode FastAPI dengan 27 endpoint kerja. Database `db_sehati` sudah ada dengan 21 tabel. Strategi kita: **refactor bertahap** (Strangler Pattern), bukan rewrite dari nol — supaya effort dokter tidak terbuang dan logika bisnis yang sudah teruji tetap dipertahankan.

```
[✓] Skema database tersedia (21 tabel)
[✓] Dokumentasi alur bisnis tersedia (Tables_in_db_sehati.txt)
[✓] Rancangan awal dari GPT tersedia (referensi)
[✓] Kode FastAPI dokter tersedia (27 endpoint kerja)
[✓] Analisa konsistensi DB selesai → 01_ANALISA_DATABASE.md
[✓] Rancangan struktur program selesai → 02_STRUKTUR_PROGRAM.md
[✓] Review kode saat ini selesai → 04_REVIEW_KODE_SAAT_INI.md
[✓] Work plan 8 minggu selesai → 03_WORK_PLAN.md
[✓] Diskusi keputusan final dengan dokter selesai → 05_KEPUTUSAN_FINAL.md
[✓] File SQL migrasi siap → migrations/sql/
[✓] Backup pre-migrasi (~/backup_sebelum_migrasi_2026-04-27.sql)
[✓] Migrasi 001 — Fix kritis (FK + DECIMAL + index) — 3 Mei 2026
[✓] Migrasi 002 — Alter tabel existing — 3 Mei 2026
[✓] Migrasi 003 — Membership system (4 tabel baru) — 3 Mei 2026
[✓] Migrasi 004 — Audit log — 3 Mei 2026
[✓] Hash password & PIN dengan bcrypt — 3 Mei 2026
[✓] Seed master_membership (VIP + VVIP) — 3 Mei 2026
[✓] Seed benefit kuota VIP (Basic Treatment bulanan + Laser Pico tahunan) — 3 Mei 2026
[✓] Backup post-migrasi (~/backup_post_migrasi_2026-05-03.sql)
[→] Mulai Minggu 1 — Senin 4 Mei 2026

Catatan untuk Minggu 6 (UI Master):
  - Adjust harga aktivasi membership (sekarang placeholder 5jt VIP / 10jt VVIP)
  - Define VVIP benefit kuota treatment (custom — dokter akan kasih konsep)
  - Klarifikasi Laser Pico vs IPL (apakah perlu tambah master treatment IPL terpisah)
  - Set treatment yang butuh_otorisasi=1 (template di seed_data/)
```
