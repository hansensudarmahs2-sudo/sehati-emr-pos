# Known Issues, Limitations & TODO

> Snapshot apa yang sudah & belum jalan. Updated berkala saat progress.
> **Last updated:** 4 Juni 2026 (afternoon) — Modul Pengadaan & Inventory lengkap (PO + Stock Opname + History Mutasi)

---

## Implementation Status (Per-Module)

### ✅ COMPLETE — Sudah jalan production-ready

| Module | Coverage | Notes |
|--------|----------|-------|
| Database Schema | 26 tabel + 5 file SQL migrasi | Baseline Alembic di `0000_baseline` |
| Authentication | Login, logout, /me, JWT 6h, bcrypt, change-password | Anchor shift dokter preserved, audit terintegrasi |
| RBAC | `role_required(*roles)` dependency | 8 role mapped |
| SDM Management | CRUD staf, reset password/PIN, set active, change own password | Owner/Superadmin/Admin, audit terintegrasi |
| ORM Models | 26 tabel + ENUM | Match schema persis (Alembic autogenerate empty) |
| Repository Layer | StafRepository, PasienRepository (full + riwayat), KunjunganRepository (full) | Pattern jelas, join-aware |
| **Pasien Module (FO)** | Service + 5 endpoint: `POST /pasien/baru`, `GET /pasien/cari`, `GET /pasien/{id}`, `GET /pasien/{id}/riwayat`, `POST /pasien/alergi`, `DELETE /pasien/alergi/{id}` | ✅ Selesai dengan audit |
| **Kunjungan Module** | Service + 4 endpoint: `POST /kunjungan/lama`, `GET /kunjungan/antrian`, `GET /kunjungan/{id}`, `PATCH /kunjungan/{id}/status` | ✅ Selesai dengan audit + state machine validasi transisi |
| **Riwayat Pasien** | `GET /pasien/{id}/riwayat` — compound: info + kunjungan + treatment + produk resep + produk terbayar | ✅ Side-by-side resep vs terbayar (compliance tracking) |
| **Audit Service** | Service + integration di 13 mutating endpoint (auth/staf/pasien/kunjungan), 18 audit hook total | ✅ Password/PIN/PII tidak pernah masuk audit log (static-checked) |
| **Dokter Module** | SOAP atomic input + Summary 4 cardbox + Header 3 grid + Antrian relevant-to-dokter dengan counter | ✅ 4 endpoint dengan filter EXISTS subquery pemeriksaan_klinis |
| **Ruang Tindakan (Perawat)** | Antrian + Detail + Start (PENDING→PROSES) + End (PROSES→SELESAI dengan auto potong BHP) + Upsell (PIN dokter) | ✅ 5 endpoint, auto SMART CHECK transition |
| **InventoryService** | Skeleton untuk auto-potong BHP saat end_treatment | ✅ FOR UPDATE lock, log ke inventory_history |
| **Antropometri Module** | Upsert (idempotent) + Get terakhir (BMI + body fat + lean computed) + Timeline | ✅ 4 endpoint, formula Jackson-Pollock 3-site + Siri, kolom updated_at dengan tiebreaker |
| **Kasir Module** | Antrian + Tagihan (idempotent bulletproof) + Bayar (atomic split payment) + Void (PIN dokter) + Rekap shift | ✅ 5 endpoint, diskon dinamis dari master_membership |
| **MembershipService** | get_diskon_for_pasien (lookup dinamis dari DB) | ✅ Owner update kolom diskon via SQL/admin endpoint tanpa redeploy |
| **Apotek Module** | Antrian + Detail dengan stok check + Serahkan (atomic potong stok + COMPLETED) + Write-off + Suggested order | ✅ 5 endpoint, FOR UPDATE lock, analytics dari transaksi_detail_produk |
| **Master Produk CRUD** | List + Get + Create + Update partial + Set Active + Restock | ✅ 6 endpoint, repacking integrity validation, stok hanya via /restock atau /apotek |
| **Reports Module** | Omzet harian + breakdown per kasir + per metode | ✅ 1 endpoint, RBAC managerial only |
| Testing | 11 unit test security + 45 integration test (auth/pasien/kunjungan/dokter/antropometri/ruang-tindakan) | Pytest with markers + seed data + tiebreaker fixture |

### 🟡 PARTIAL — Sudah ada sebagian

| Module | Done | Missing |
|--------|------|---------|
| Test coverage | Auth + security unit tests | Integration test untuk pasien/kunjungan/riwayat endpoint (Week 3) |

### 📋 PLANNED — Belum dimulai (sesuai roadmap)

| Module | Priority | Phase |
|--------|----------|-------|
| ~~Endpoint FO (pasien, kunjungan)~~ | ~~🔴 HIGH~~ | ~~Phase 1, Minggu 3-4~~ ✅ **DONE Week 3** |
| ~~Dokter SOAP module (PemeriksaanService)~~ | ~~🔴 HIGH~~ | ~~Phase 1, Minggu 4~~ ✅ **DONE Week 4** |
| ~~Treatment service & endpoint (single + series)~~ | ~~🔴 HIGH~~ | ~~Phase 1, Minggu 4~~ ✅ **DONE Week 4** |
| ~~Upsell service + PIN authorization~~ | ~~🔴 HIGH~~ | ~~Phase 1, Minggu 4~~ ✅ **DONE Week 4** |
| ~~Antropometri service (standalone)~~ | ~~🟡 MEDIUM~~ | ~~Phase 1, Minggu 4~~ ✅ **DONE Week 4** |
| ~~Inventory service skeleton (potong stok BHP)~~ | ~~🟡 MEDIUM~~ | ~~Phase 1, Minggu 4~~ ✅ **DONE Week 4** |
| ~~Ruang tindakan (perawat) endpoints~~ | ~~🔴 HIGH~~ | ~~Phase 1, Minggu 4~~ ✅ **DONE Week 4** |
| ~~Kasir module (tagihan, bayar, void, rekap)~~ | ~~🔴 HIGH~~ | ~~Phase 1, Minggu 5~~ ✅ **DONE Week 5** |
| ~~Apotek module (antrian, detail, serahkan, write-off, suggested)~~ | ~~🔴 HIGH~~ | ~~Phase 1, Minggu 5~~ ✅ **DONE Week 5** |
| ~~Master Produk CRUD~~ | ~~🟡 MEDIUM~~ | ~~Phase 1, Minggu 6~~ ✅ **DONE Week 6** |
| ~~Reports omzet harian~~ | ~~🟡 MEDIUM~~ | ~~Phase 1, Minggu 6~~ ✅ **DONE Week 6** |
| Master Treatment / Bahan / Membership CRUD | 🟢 LOW | Phase 1, Minggu 6 (per keputusan dr. Hansen: defer — update via SQL untuk MVP) |
| Frontend HTMX + Jinja2 + Tailwind | 🔴 HIGH | Phase 1, Minggu 7 — **AKTIF SEKARANG** |
| Iterasi resep (workflow apoteker) | 🟢 LOW | Defer ke Phase 2 (per keputusan dr. Hansen Week 6) |
| Membership flow (aktivasi member + kuota check) | 🟡 MEDIUM | Phase 1, Minggu 6 (deferred — endpoint aktivasi belum, kuota tracking sudah ada di model) |
| Repacking module (apoteker bikin produk dari bahan) | 🟢 LOW | Phase 2 — workflow advanced |
| Reports bulanan + per dokter/treatment | 🟡 MEDIUM | Phase 2 — Phase 1 cukup omzet harian |
| Backup automation (cron mysqldump) | 🔴 HIGH | Phase 1, Minggu 8 |
| Production deployment (Docker + nginx + HTTPS) | 🔴 HIGH | Phase 1, Minggu 8 |
| Module Foto pasien | 🟢 LOW | Phase 2 |
| Booking online (web pasien) | 🟢 LOW | Phase 2 |
| Kiosk registrasi mandiri | 🟢 LOW | Phase 2 |
| Delivery products | 🟢 LOW | Phase 2 |
| WA/Telegram notification | 🟢 LOW | Phase 2 |
| Skin analysis AI (Gemini) | 🟢 LOW | Phase 3 |
| USG kulit interpretation AI | 🟢 LOW | Phase 3 |
| SOAP smart assist AI | 🟢 LOW | Phase 3 |
| Chat AI member | 🟢 LOW | Phase 3 |
| Mobile app native | 🟢 LOW | Phase 4 |
| Multi-cabang | 🟢 LOW | Phase 5 |

---

## Known Issues / Tech Debt

### 🔴 Critical — Harus diselesaikan sebelum production

| ID | Issue | Impact | Mitigation |
|----|-------|--------|------------|
| ~~C1~~ | ~~Tidak ada audit log integration di endpoint mutating~~ | ~~Tidak bisa trace aksi sensitif kalau ada masalah~~ | ✅ **RESOLVED Week 3** — 18 audit hook di 4 service. Password/PIN/PII tidak masuk log (static-checked). |
| C2 | Tidak ada rate limiting di `/auth/login` | Brute force possible | Add `slowapi` di Phase 1 minggu 7-8. **Catatan: login_failed sekarang ter-audit dengan IP — bisa pakai data ini untuk detect attack pattern.** |
| C3 | JWT secret di `.env` development — bukan rotated | Token bocor = forever access sampai expiry | Production: pakai secret manager + rotate berkala |
| C4 | Tidak ada backup automation | Crash = data hilang | Cron `mysqldump` di Minggu 8 |
| C5 | Production HTTPS belum di-setup | Token bisa di-sniff di jaringan | nginx + Let's Encrypt di Minggu 8. ⚠ **Progress Week 7 (Juni 3 2026):** cookie `secure` flag sudah config-driven via `settings.cookie_secure` (default `True`, dev `.env` override `false`). Sisa kerja: setup nginx + cert + set `COOKIE_SECURE=true` di production `.env`. Lihat DEC-032. |

### 🟡 Important — Harus dibereskan Phase 1

| ID | Issue | Impact | Mitigation |
|----|-------|--------|------------|
| I1 | `nomor_antrean` per hari tidak ada lock global | Race condition kalau 2 FO daftar bersamaan | **Decision Week 3** (per dr. Hansen): SKIP technical fix, kunci pakai SOP "1 FO aktif saat daftar". Future: tambah lock kalau ada kasus 2 FO simultan. |
| ~~I8~~ | ~~`POST /kunjungan/lama` allow duplicate kunjungan untuk pasien sama di hari yang sama~~ | ~~FO bisa salah klik → 2 antrian untuk 1 pasien~~ | ✅ **RESOLVED Week 7 (Juni 3 2026)** — di-flip jadi 409 Conflict di service layer. `KunjunganService.kunjungan_lama` cek `get_active_kunjungan_today(id_pasien)` sebelum INSERT. Pesan jelas: "Pasien '{nama}' sudah ada di antrian hari ini (no.antrean #X, status Y). Pakai tombol Ubah/Batal di halaman antrian kalau perlu koreksi." Approach lebih kuat dari frontend warning karena enforce di backend juga. |
| I9 | Tidak ada endpoint "dokter rekap pasien hari ini" (termasuk COMPLETED) | Dokter tidak bisa lihat seberapa banyak pasien yang sudah dia handle hari ini tanpa minta Admin | **Decision Week 4 smoke test** (per dr. Hansen): defer ke Week 5/6 (kasir/master CRUD phase). Saat ini dokter pakai `/dokter/antrian` untuk yang aktif; rekap COMPLETED bisa ditambah nanti via `/dokter/rekap-hari-ini` atau extend `/pasien/cari` dengan filter `tanggal`. |
| I10 | `datetime.utcnow()` deprecated di Python 3.12+ | Warning di pytest, akan break di Python 3.14+ | Refactor ke `datetime.now(datetime.UTC)` saat Phase 1 polish (Week 8). Lokasi: `app/services/auth_service.py:95` (anchor shift logic). Plus banyak service lain pakai pattern sama. |
| I11 | Omzet harian `total_omzet` vs sum `per_metode.total_nominal` bisa beda kalau kasir terima overpayment | Confusing untuk laporan akuntansi | **Decision Week 6** (per dr. Hansen, tunggu konfirmasi): saat ini intentional — `per_metode.nominal` = uang masuk, `total_omzet` = revenue. Kalau Bapak prefer angka cocok 1:1, perlu split kolom `nominal_bayar` vs `nominal_diterima`. |
| I12 | Tidak ada endpoint untuk Master Treatment/Bahan/Membership CRUD di Phase 1 | Owner/Admin perlu update langsung via SQL untuk tier diskon, treatment baru, bahan klinik | **Decision Week 6** (per dr. Hansen): MVP-acceptable — Owner update via SQL untuk skala klinik tunggal. Endpoint CRUD akan ditambah saat ada pain point real, atau Phase 2 multi-cabang. |
| I13 | Tidak ada rate limiting di endpoint sensitive (login, void, write-off) | Brute force / spam risk di production | C2 dependency — `slowapi` integration di Week 8 polish. |
| I2 | Endpoint `/health/db` expose MySQL version | Information disclosure ringan | Restrict ke admin saja di production |
| ~~I3~~ | ~~Tidak ada CSRF protection~~ | ~~Risk untuk form HTMX di frontend nanti~~ | ✅ **RESOLVED Week 7 (Juni 3 2026)** — custom `CSRFMiddleware` (pure ASGI) di `app/core/csrf.py`, double-submit cookie pattern. Cookie `sehati_csrf` (256-bit random), validate via `secrets.compare_digest` (constant-time). 9 web POST form punya `{{ csrf_input(request) }}` via Jinja2 global. Skip `/api/v1/*` (JWT bearer immune). Pure ASGI dipilih untuk hindari body-consumption bug di `BaseHTTPMiddleware`. Lihat DEC-031. |
| I4 | Belum ada logging structured (cuma `print()`) | Susah debug di production | Pakai `structlog` di Phase 1 minggu 7-8 |
| I5 | `master_treatment.id_staf` masih ambigu (creator? PIC?) | Kolom unclear semantics | Konfirmasi dokter, document atau rename |
| I6 | Treatment paralel — tidak ada lock di smart trigger `COUNT(status...)` | Theoretical race condition end_treatment vs start_treatment | Add explicit lock atau transaction isolation |
| I7 | Tidak ada validasi `pin` strength (kalau Owner set PIN "1234") | Weak PIN | Add validation min 4 digit, no sequential |

### 🟢 Nice-to-Have — Phase 2+

| ID | Issue | Mitigation |
|----|-------|------------|
| N1 | Tidak ada pagination di list endpoint | Add `?page=&limit=` saat data > 100 row |
| N2 | Tidak ada caching untuk master data (produk, treatment) | Redis cache untuk yang sering di-read |
| N3 | Foto module belum implement | Phase 2 |
| N4 | Refresh token tidak ada | Phase 2 (saat ini cuma access token) |
| N5 | Multi-device session tidak independen (logout di A = logout di B karena cek `is_logged_in` di DB) | Pertimbangkan stateless JWT pure tanpa cek DB |
| N6 | Membership "Promo" enum disiapkan tapi tidak ada flow | Phase 2 |
| N7 | Transfer paket member ke pasien lain belum ada | Phase 2 — butuh approval Owner |

---

## Design Decisions yang Bisa Di-Review Ulang

> Ini bukan issues, tapi keputusan yang AI reviewer (atau dokter) mungkin punya pendapat berbeda.

1. **Sync SQLAlchemy vs Async** — saat ini sync untuk simplicity pemula. Bisa di-async-kan di Phase 2 kalau ada concurrency issue.

2. **JWT 6h expiry** — sengaja panjang untuk match logika anchor shift. Trade-off: lebih lama berarti token bocor lebih dangerous. Alternatif: 1h access + 7d refresh token.

3. **Stok minus diizinkan** — sesuai filosofi dokter (operasional jangan diblok). Alternatif: blok hard kecuali ada override admin password.

4. **`waktu_mulai_shift` di kolom `master_staf`** — denormalisasi sengaja untuk performance. Alternatif: tabel `shift_kasir` terpisah (di plan untuk Minggu 5).

5. **Soft delete vs is_active flag** — saat ini cuma alergi & penyakit pakai is_active. Apakah tabel lain perlu sama? (e.g., master_produk discontinued?)

6. **No validation untuk format `nomor_telepon` dan `nomor_ktp`** — terlalu strict bisa annoying, terlalu loose data sampah. Currently loose.

7. **`pemeriksaan_klinis.saran_treatment` & `saran_produk`** — repurposed dari kolom existing. Alternatif: hapus & tambah tabel `kunjungan_catatan(id_kunjungan, jenis, isi)` terpisah.

8. **Audit log via JSON column** — flexible tapi susah di-query. Alternatif: structured columns terpisah per `aksi`.

9. **Anchor shift dari `master_staf.waktu_mulai_shift`** — single shift per staf. Tidak support multiple shifts in one day (jarang di klinik). OK untuk MVP.

10. **No event sourcing / CQRS** — overkill untuk skala klinik kecil. OK tetap CRUD.

---

## Bugs Discovered (Live List)

> Append di sini kalau ada bug ditemukan saat testing.

| Bug ID | Discovered | Status | Description |
|--------|------------|--------|-------------|
| B-001 | 4 Jun 2026 | ✅ Fixed | Nested HTML form di master_treatment_form.html — Toggle Aktif/Nonaktif nested di dalam form Simpan → button submit malah trigger form luar dengan data lama. Fix: pindah ke card terpisah di luar form Simpan. Pelajaran: HTML tidak boleh nested forms; cek manual semua template POST. |
| B-002 | 4 Jun 2026 | ✅ Mitigated | MySQL "Lost connection to MySQL server during query" intermittent saat klik Tambah Treatment. Akar: `pool_recycle=3600s` terlalu lama untuk MySQL wait_timeout pendek. Fix: pool_recycle=280s + connect_timeout=10s (DEC-036). Production: pastikan MySQL `wait_timeout > 280s`. |
| B-003 | 3 Jun 2026 | ✅ Fixed | KunjunganResep beli_produk silent fail — `id_staf_input` NOT NULL tapi service tidak set. Fix: service set `id_staf_input=id_staf_fo`. |
| B-004 | 3 Jun 2026 | ✅ Fixed | Wizard "Selanjutnya" pendaftaran pasien tidak respond — btnNext variable undefined. Fix: re-add `const btnNext = document.getElementById('btn-next')`. |
| B-005 | 3 Jun 2026 | ✅ Fixed | +Antrian dropdown clipped + tidak auto-close on click outside. Fix: custom button+menu div + JS click-outside handler + scroll/resize close. |
| B-006 | 4 Jun 2026 | ✅ Fixed | pengadaan.py import `Base` dari `app.db.session` (salah path) — saat ini di `app.db.base`. Fix: ganti ke `from app.db.base import Base`. Pelajaran: cek pattern import existing model lain sebelum buat file baru. |
| B-007 | 4 Jun 2026 | ✅ Fixed | Edit Header PO error 500 "Object of type date is not JSON serializable" karena `tgl_perkiraan_datang` di-pass langsung ke audit log JSON. Fix: helper `_to_json_safe()` convert date/datetime/Decimal ke ISO string/float sebelum kirim ke audit. |
| B-008 | 4 Jun 2026 | ✅ Fixed | Submit opname error MySQL 3105 "value not allowed for generated column 'selisih'". MySQL GENERATED column tidak boleh muncul di INSERT. Fix: pakai `sqlalchemy.Computed("qty_fisik - qty_sistem", persisted=True)` di model — DEC-042 pattern untuk future. |

---

## ✅ RESOLVED — Issues yang sudah diselesaikan

| Issue | Resolved | Notes |
|-------|----------|-------|
| Master Treatment + Bahan Owner update via SQL | 4 Jun 2026 (DEC-033) | Web UI lengkap dengan komponen treatment inline. Auto-deduct BHP yang sudah ada sekarang fully usable untuk Owner. Master Membership masih SQL (Phase 2). |
| Stock opname & restock multi-produk via SQL | (DEFER) | Tracking task #149 — Modul Inventory lengkap di sesi berikutnya. |
| I3 — Login CSRF protection missing | 3 Jun 2026 (DEC-031) | CSRF middleware pure ASGI dengan double-submit cookie pattern. Semua form POST punya `{{ csrf_input(request) }}`. |
| I8 — Duplicate kunjungan pasien hari sama | 3 Jun 2026 | Backend `get_active_kunjungan_today` guard di KunjunganService raise 409 kalau ada kunjungan aktif. |
| Cookie secure flag hardcoded False | 3 Jun 2026 (DEC-032) | Config-driven via `settings.cookie_secure`, default True (failure-secure), dev override via .env. |
| ValueError/TypeError di get_user_from_cookie crash 500 | 3 Jun 2026 | Defensive try/except di `_shared.get_user_from_cookie` — return None kalau JWT payload aneh. |
| Redundant db.commit() di router | 3 Jun 2026 (DEC-030) | Service-owned transaction pattern. Router NEVER commits. Pre-audited lalu cleanup. |
| Restock direct di Master Produk (no PO audit trail) | 4 Jun 2026 (DEC-040) | Tombol Restock + route POST `/restock` dihapus. Workflow wajib via Pengadaan (PO+Receive). Stock Opname untuk koreksi. Backend service tetap di-keep dipanggil internal oleh receive. |
| Modul Inventory + Stock Opname pending | 4 Jun 2026 (DEC-038/039/041) | Modul Pengadaan & Inventory lengkap: PO workflow + Stock Opname dengan snapshot pattern + History Mutasi UI. Audit trail dari ORDER sampai RECEIVE 100% tracked. |
| Master Bahan Klinik (inventory_stok) update via SQL | 4 Jun 2026 (DEC-033) | Master Bahan web UI lengkap. Owner/Superadmin bisa CRUD via /web/master/bahan. |
| Master Treatment update via SQL | 4 Jun 2026 (DEC-033) | Master Treatment web UI lengkap dengan komponen BHP inline. |

---

## Items untuk AI Reviewer Focus

Bila Anda OpenAI atau Ollama membaca ini untuk review:

### Priority 1 — Logic correctness
- `app/services/pasien_service.py` — `register_pasien_baru()` — apakah 1 transaksi atomik benar-benar atomic? Apakah ada path yang bisa commit partial? **Update Week 3: audit log_create dipanggil 2x dalam try-block; kalau audit fail, business rollback ikut?**
- `app/services/auth_service.py` — `login()` — anchor shift logic. Apakah edge case (login lewat tengah malam) ter-handle? **Update Week 3: setiap failed login sekarang `db.commit()` audit row dulu sebelum raise — apakah commit di branch error path bisa leak partial state?**
- `app/repositories/pasien_repo.py` — `generate_next_no_rm()` — apakah FOR UPDATE lock cukup, atau perlu tambah serializable isolation?
- `app/services/kunjungan_service.py` — `_VALID_TRANSITIONS` state machine — apakah transisi `ON_TREATMENT → COMPLETED` (yang baru, untuk member kuota) ada risk false-positive (kasir lupa generate tagihan)? **Idealnya validasi prepaid status di TreatmentService Week 4.**

### Priority 2 — Security
- `app/core/security.py` — bcrypt 72-byte truncate. Apakah ada cara bypass yang missed?
- `app/core/deps.py` — `get_current_user()` — apakah JWT decode error handling lengkap?
- `app/services/staf_service.py` — `reset_password()` — apakah otomatis logout sudah cukup, atau perlu juga invalidate semua refresh token (yang belum ada)?

### Priority 3 — Performance
- N+1 query potential di `PasienRepository.get_by_id(with_relations=True)`? Saat ini pakai `selectinload`, sudah OK.
- Query `MAX(nomor_antrean)` di `kunjungan` — sudah ada index `idx_kunjungan_pasien_tgl`. Cukup atau perlu index khusus `(tgl_kunjungan)`?

### Priority 4 — Maintainability
- File `app/db/models/kunjungan.py` cukup besar (6 class). Apakah perlu split per file?
- Imports di `__init__.py` cukup banyak (130 baris). Apakah pakai `*` import dari sub-module lebih clean? (Saya tahu best practice menentang `*`, jadi keep explicit.)

---

## Things Already Considered & Rejected (Untuk Reviewer)

> Supaya reviewer tidak suggest hal yang sudah dipertimbangkan.

| Idea | Why Rejected |
|------|--------------|
| Pakai async SQLAlchemy | Too complex untuk pemula. No real bottleneck di skala klinik kecil. |
| FastAPI-Users library | Opinionated, susah custom integration dengan schema `master_staf` existing. |
| Celery + Redis dari awal | Overkill. `FastAPI.BackgroundTasks` cukup untuk MVP. |
| React frontend | Dual stack (Python + JS), terlalu kompleks untuk solo dev pemula. HTMX cukup. |
| Multi-tenant dari awal | Future Phase 5 saja. Klinik dokter solo dulu. |
| GraphQL | Overkill. REST sudah cukup ekspresif. |
| MongoDB / NoSQL | DB sudah MySQL exist + ada existing data. Tidak ada use case yang justify NoSQL. |
| Microservices | Klinik kecil, monolith FastAPI cukup. |
| Real-time WebSocket | Tidak ada use case real-time critical. Polling HTMX cukup untuk antrian. |
| Event sourcing | Klinik kecil, overkill. CRUD dengan audit_log sudah cukup. |
ktu_mulai_shift`** — single shift per staf. Tidak support multiple shifts in one day (jarang di klinik). OK untuk MVP.

10. **No event sourcing / CQRS** — overkill untuk skala klinik kecil. OK tetap CRUD.

---

## Bugs Discovered (Live List)

> Append di sini kalau ada bug ditemukan saat testing.

| Bug ID | Discovered | Status | Description |
|--------|------------|--------|-------------|
| BUG-1 | 27 Mei 2026 (smoke test) | ✅ Fixed | `PATCH /kunjungan/{id}/status` truncation di endpoint file → ResponseValidationError. Fix: re-append return statement. |
| BUG-2 | 27 Mei 2026 (smoke test) | ✅ Fixed | `GET /antropometri/pasien/{id}/terakhir` salah ambil row karena ORDER BY created_at unstable (sub-microsecond ties). Fix: tambah kolom `updated_at` + ORDER BY coalesce + tiebreaker id_antropometri DESC. |

---

## Items untuk AI Reviewer Focus

Bila Anda OpenAI atau Ollama membaca ini untuk review:

### Priority 1 — Logic correctness
- `app/services/pasien_service.py` — `register_pasien_baru()` — apakah 1 transaksi atomik benar-benar atomic?
- `app/services/auth_service.py` — `login()` — anchor shift logic edge case lewat tengah malam.
- `app/repositories/pasien_repo.py` — `generate_next_no_rm()` — FOR UPDATE lock cukup?
- `app/services/kasir_service.py` — `proses_bayar()` — atomic INSERT transaksi+detail+pembayaran. Race condition kalau 2 kasir bayar pasien sama bersamaan?
- `app/services/apotek_service.py` — `serahkan_obat()` — FOR UPDATE lock per produk sufficient?

### Priority 2 — Security
- `app/core/security.py` — bcrypt 72-byte truncate. Apakah ada cara bypass yang missed?
- `app/services/kasir_service.py` — `void_item_resep()` PIN verify. Apakah ada timing attack risk?
- `app/services/master_produk_service.py` — `restock()` qty validation, prevent negative?

### Priority 3 — Performance
- N+1 query potential di `KasirRepository.list_antrian_bayar` (per-row count tindakan/resep). OK untuk skala kecil tapi perlu join window function kalau scale up.
- Suggested order query — 2 separate aggregate (90 hari & 30 hari). Could be 1 query dengan multiple selects.

### Priority 4 — Maintainability
- File `app/services/kasir_service.py` ~483 baris, banyak responsibility (tagihan, bayar, void, rekap). Apakah perlu split?

---

## Things Already Considered & Rejected (Untuk Reviewer)

| Idea | Why Rejected |
|------|--------------|
| Pakai async SQLAlchemy | Too complex untuk pemula. No real bottleneck di skala klinik kecil. |
| FastAPI-Users library | Opinionated, susah custom integration dengan schema `master_staf` existing. |
| Celery + Redis dari awal | Overkill. `FastAPI.BackgroundTasks` cukup untuk MVP. |
| React frontend | Dual stack (Python + JS), terlalu kompleks untuk solo dev pemula. HTMX cukup. |
| Multi-tenant dari awal | Future Phase 5 saja. Klinik dokter solo dulu. |
| GraphQL | Overkill. REST sudah cukup ekspresif. |
| MongoDB / NoSQL | DB sudah MySQL exist + ada existing data. Tidak ada use case yang justify NoSQL. |
| Microservices | Klinik kecil, monolith FastAPI cukup. |
| Real-time WebSocket | Tidak ada use case real-time critical. Polling HTMX cukup untuk antrian. |
| Event sourcing | Klinik kecil, overkill. CRUD dengan audit_log sudah cukup. |
| Inventory_history untuk produk POS | Per DEC-022 — over-engineering untuk Phase 1. transaksi_detail_produk + audit_log generic sudah cukup. |
| Master CRUD untuk treatment/bahan/membership | Per DEC-027 — Owner update via SQL untuk klinik tunggal. Endpoint kalau ada UI pain point. |
| Iterasi resep workflow | Per DEC-028 — defer ke Phase 2 patient portal. |

## Health Check — Baseline & Trend (NEW — sejak 5 Jun 2026)

Sehati Clinic sekarang punya **Health Check Protocol** terdokumentasi di
`Project_Memory/HealthCheck/`. Setiap run otomatis catat finding ke
`HealthCheck/logs/YYYY-MM-DD_*.md`. CRITICAL/HIGH otomatis di-promote ke
section bawah ini.

| Run | Date | Mode | CRITICAL | HIGH | MEDIUM | LOW | Status |
|-----|------|------|----------|------|--------|-----|--------|
| Baseline | 5 Jun 2026 | baseline | 0 | 6 | 1 | 0 | All resolved → DEC-043 |
| Post-fix | 5 Jun 2026 | post-deploy | 0 | 0 | 0 | 0 | ✅ Clean |

### Closed Findings (Plan A — 5 Jun 2026)

| Finding ID | Severity | Lokasi | Fix |
|------------|----------|--------|-----|
| BE-02 (kunjungan.py:144) | HIGH | `app/web/routes/kunjungan.py` | Hapus redundant `db.commit()` — service yang commit (DEC-030/043) |
| BE-02 (kunjungan.py:192) | HIGH | `app/web/routes/kunjungan.py` | Sama seperti atas |
| BE-02 (master.py:628) | HIGH | `app/web/routes/master.py` | Delegasi ke `InventoryService.create_bahan_with_audit()` |
| BE-02 (master.py:717) | HIGH | `app/web/routes/master.py` | Delegasi ke `InventoryService.update_bahan_with_audit()` |
| BE-02 (master.py:793) | HIGH | `app/web/routes/master.py` | Delegasi ke `MasterTreatmentService.tambah_komponen()` |
| BE-02 (master.py:835) | HIGH | `app/web/routes/master.py` | Delegasi ke `MasterTreatmentService.hapus_komponen()` |
| BE-04 (csrf.py:135) | MEDIUM | `app/core/csrf.py` | Graceful by design — tambah `# noqa: BLE001` + `_logger.warning()` |

---

## Bugs Discovered (Live List) — Update 5 Jun 2026

| Bug ID | Discovered | Status | Description |
|--------|------------|--------|-------------|
| B-009 | 5 Jun 2026 | 🟡 Workflow caveat (open, mitigated) | File truncation pattern saat edit file `> 100 baris` via Edit/Write tool. Plus null byte injection (~1000 nulls per edit). Suspected: Windows path → WSL mount translation bug di file tool layer. **Mitigation:** untuk rewrite file > 100 baris, prefer `bash heredoc`. Setelah setiap edit besar, verify dengan `ast.parse()` atau `wc -l`. Detection check direncanakan masuk ke `audit_gaps.py` (BE-09 null bytes scan). Tracked di DEC-044. |

---

## Dev Workflow Notes (NEW)

Pelajaran dari sesi 4-5 Juni 2026:

1. **File integrity** bukan asumsi. Setelah setiap edit:
   - Untuk file Python: `python3 -c "import ast; ast.parse(open(f).read())"`.
   - Untuk file Jinja: `from jinja2 import Environment, FileSystemLoader; env.get_template(...)`.
   - Cek `wc -l` dan `tail -c 200` kalau file terasa tidak lengkap.

2. **Bash heredoc** lebih reliable daripada Write tool untuk file `> 100 baris`:
   ```bash
   cat > path/to/file.py << 'PYEOF'
   ... full file content ...
   PYEOF
   ```

3. **Null byte cleanup** kalau muncul:
   ```bash
   python3 -c "data=open('f','rb').read().replace(b'\x00',b''); open('f','wb').write(data)"
   ```

4. **Run health check** setelah setiap edit besar (especially routes/services):
   ```bash
   python3 ../Project_Memory/HealthCheck/scripts/run_health_check.py --mode post-deploy --by "Hansen"
   ```


## Bugs Discovered (Live List) — Update 5 Jun 2026 (continued)

| Bug ID | Discovered | Status | Description |
|--------|------------|--------|-------------|
| B-010 | 5 Jun 2026 | ✅ Fixed | Audit Log Viewer error 500 saat render: `TypeError: 'str' object cannot be interpreted as an integer`. Penyebab: `it.waktu` adalah `datetime` object (Pydantic v2 `model_dump()` default mode keep as datetime), template pakai `.replace('T', ' ')[:19]` — Python interpret sebagai `datetime.replace(year, ...)` method yang expect integer. Fix: ganti ke `it.waktu.strftime('%Y-%m-%d %H:%M:%S')`. Pelajaran: render test harus pakai data shape identik production (datetime object, bukan string ISO yang convenient). |

---

## Reports Module C1 — Complete (5 Jun 2026, DEC-045)

✅ 4 UI Reports lengkap dan tested:
- Omzet Bulanan (Owner/Superadmin/Admin) — chart bar+line, breakdown per metode
- Top Treatment (Owner/Superadmin/Admin) — ranking + horizontal bar
- Kinerja Dokter (Owner/Superadmin/Admin) — konsul vs tindakan + conversion rate
- Audit Log Viewer (Owner/Superadmin only) — filter multi + JSON diff + pagination

**Known limitations** (acceptable untuk Phase 1):
- Top Treatment + Kinerja Dokter omzet = `count × master_treatment.harga` (estimasi pre-diskon).
  Re-architect di Phase 2 kalau diskon membership heavy used.
- Audit Log Viewer hanya view, tidak ada export. Export raw akan tersedia di Phase C2.

**Next pending Phase 1:**
- 📋 C2 — Raw Data Export untuk modul `data_analyst` (waiting spec dari dr. Hansen)
- 📋 B — Soft Launch Prep: backup automation, user manual PDF, deployment guide


## Bugs Discovered (Live List) — Update 5 Jun 2026 (C2 batch)

| Bug ID | Discovered | Status | Description |
|--------|------------|--------|-------------|
| B-011 | 5 Jun 2026 | ✅ Fixed | Klik Download Pack error 500: `NameError: name 'nl' is not defined`. Penyebab: saat patch C2.4.C, regex `re.sub()` untuk replace placeholder DATA_DICTIONARY block tidak hapus full block — tinggalkan 3 baris orphan yang reference variabel `nl = chr(10)` yang sudah di-define di body lama (terhapus). Plus redundant `add_data_dictionary()` ke-2 call. Fix: hapus 3 baris orphan + 1 redundant call, sisakan hanya 3 baris bersih (`md_text = ...` + `add_data_dictionary(md_text.encode())`). Pelajaran: regex `re.sub()` untuk block code → **selalu verify visual context** setelah patch via Read line range, atau simulasi call path (smoke test). AST parse tidak detect karena syntactically valid (NameError = runtime error). |

---

## Raw Data Export Module C2 — Complete (5 Jun 2026, DEC-046)

✅ Module Owner Raw Data Export lengkap dan tested:
- **Foundation** (C2.1): csv_writer + json_writer + zip_packer + ExportService skeleton + landing UI
- **13 Datasets** (C2.2): Daily Op Summary + Visits + Treatments + Products + Trx Header+Detail + Inventory + PO 3-way + Membership + SOAP + Audit
- **Pack Assembly** (C2.3): Weekly/Monthly/Custom dengan anchor date + adaptive warning + error resilience
- **Data Dictionary** (C2.4): 149 column definitions di `_export_columns.py`, JSON + MD endpoints, auto-bundle di pack, static file di Project_Memory
- **Housekeeping** (C2.5): DEC-046 + this entry + roadmap update + magic command words

**Tested with real data:** Excel import Mar-Mei 2026 (2.035 rows, 569 fakturs,
386 pasien) → semua 13 dataset export reflect data real benar.

**Known limitations** (acceptable untuk Phase 1, defer ke future):
- Audit Mode B (`data_lama`/`data_baru` JSON snapshot) tidak include di pack default. Decision #6: defer ke advanced flow nanti dengan flag `?include_snapshots=true`.
- Estimasi omzet pakai master harga (sama dengan limitation Reports C1) — diskon membership tidak considered. Re-architect kalau diskon heavy used.
- Hardcoded language Indonesian di README + dictionary. Future: i18n support.

---

## Phase 1 Status Update — 5 Jun 2026 (post-C2 closure)

**Status:** 🟢 Phase 1 ~99.9% selesai. Sisa: **B Soft Launch Prep** (backup automation + user manual PDF + deployment guide).

**Completed in Phase 1 (recap):**
- Auth + SDM Management
- Pasien + Kunjungan + Antrian + 8 status workflow
- Dokter SOAP + Antropometri + Riwayat
- Perawat Ruang Tindakan + Auto-deduct BHP + Upsell PIN
- Kasir Tagihan + Split Payment + Void
- Apotek Antrian + Serahkan + Write-off + Suggested Order
- Master Data Web UI (Treatment + Bahan + Produk) — Owner/Superadmin
- Pengadaan & Inventory (PO + Stock Opname + History Mutasi)
- Dashboard per role
- C1 Reports (4 UI: Omzet Bulanan + Top Treatment + Kinerja Dokter + Audit Log Viewer)
- C2 Owner Raw Data Export (13 datasets + Pack assembly + Dictionary)
- Health Check Protocol (Lite) + 4 baseline + 1 trend tracking
- Excel Historical Import (real data Mar-Mei 2026 tersedia untuk testing)

**Pending Phase 1:**
- 📋 **B Soft Launch Prep**: backup script (mysqldump cron daily), user manual per role (5-10 halaman PDF per role), deployment guide (uvicorn systemd, nginx reverse proxy, .env management, MySQL config)

---

## Phase B Soft Launch — Sub-Phase B1+B2 Complete + Sprint Tambahan (6 Jun 2026)

**Status:** 🟢 B1 (Backup) + B2 (User Manual) + Print Module (Phase A) +
Multi-Tenant Klinik Config + Series Treatment Refactor + Tom Select
Searchable Dropdown — semua selesai end-to-end test di production-equivalent
environment (real data, real workflow).

### Completed sejak 5 Jun 2026

- **Print Module Phase A (DEC-047)**: Nota A5 + Thermal + SOAP Resume A5 +
  Thermal + auto-print confirmation page after kasir lunas.
- **Multi-Tenant Klinik Config (DEC-047)**: `master_klinik_config`
  singleton + Settings page Owner-only + 46 callsite `build_shell_context`
  injection.
- **Backup Phase B1 (DEC-048)**: `backup.sh` + `restore.sh` + README cron
  instructions + 30-day retention. Manual schedule (klinik configure cron).
- **User Manual Phase B2 (DEC-048)**: DOCX 5 role + Pendahuluan,
  ~50 halaman total, docx-js generator.
- **Series Treatment Refactor (DEC-049)**: harga_paket schema + sesi 1
  paket prepaid + sesi 2..N Rp 0 + SeriesService + FO dropdown "Lanjut
  Series" + Kasir conditional Rp 0 bypass + Pasien Detail card "Rencana
  Aktif".
- **Searchable Dropdown (DEC-049 lampiran)**: Tom Select 2.3.1 di SOAP
  Dokter, FO Beli Produk, Perawat Upsell, Master forms.

### Bugs ditemukan + closed (sejak DEC-046)

| ID | Issue | Status | Fix |
|----|-------|--------|-----|
| B-012 | CSRF middleware tolak multipart/form-data (logo upload 403) | ✅ Closed | DEC-047: skip CSRF kalau Content-Type starts with `multipart/`, audit log compensation |
| FIX-1.5 | Klinik name revert ke "Klinik Anda" saat pindah halaman | ✅ Closed | Inject `db=db` ke 46 callsite `build_shell_context` |
| FIX-1.6 | profil.py 500 NameError 'db' di `_profil_ctx` helper | ✅ Closed | Tambah db param + update 18 caller |
| FIX-SD-1 | Tom Select empty option masih kelihatan saat user ketik | ✅ Closed | `score` function filter `value === ""` |
| FIX-SD-2 | pasien_beli_produk duplicate endblock | ✅ Closed | Remove duplicate `{% endblock %}` |
| INV-SERIES-1 | Series treatment invisible di Ruang Tindakan + Kasir error | ✅ Closed | DEC-049 full refactor |
| FIX-ST-1 | `StatusRencanaEnum` ImportError (typo) | ✅ Closed | Rename ke `StatusRencanaTreatmentEnum` |
| FIX-ST-2 | Duplicate `detail=` kwarg di KasirService HTTPException | ✅ Closed | `sed -i '498d'` |
| FIX-ST-3 | FO +Antrian dropdown tidak ada opsi lanjut series | ✅ Closed | search_partial join series_pending + tombol di dropdown |
| FIX-ST-4 | Hard-stop Rp 0 untuk sesi series 2..N | ✅ Closed | Conditional bypass kalau `total_tagihan == 0` |

### Bugs baru ditemukan (open / monitoring)

- **B-013 (RECURRENT)**: File truncation bug saat Edit tool dipakai di file
  besar — DEC-044 sudah dokumentasi pattern. **Update 6 Jun 2026:** Pattern
  workaround `head + heredoc` masih jadi standar. Recommendation: hindari
  Edit tool untuk file > 400 lines, langsung pakai bash heredoc untuk
  rewrite section per section. **Severity:** workflow caveat (no production
  impact), **owner:** AI assistant.
- **B-014 (LOW)**: `buat-antrian-series` route — kalau `SeriesService.use_session()`
  gagal setelah `KunjunganService.kunjungan_lama()` sukses, kunjungan baru
  tetap committed (orphan ANTRI_TREATMENT tanpa tindakan). User dapat
  flash error tapi harus manual batalkan kunjungan. **Severity:** LOW (edge
  case — validasi rencana sudah di-cek pre-create). **Future fix:** wrap
  dua operasi dalam savepoint nested transaction. **Workaround sekarang:**
  flash error sebut id_kunjungan supaya FO bisa batal manual via halaman
  Antrian.

---

## Phase 1 Status Update — 6 Jun 2026 (post-DEC-049 closure)

**Status:** 🟢 Phase 1 = **100% selesai**. Phase B Soft Launch = **B1 + B2
done, B3 (Deployment Guide) sisa**.

**Sisa Phase B Soft Launch:**
- 📋 **B3 Deployment Guide**: uvicorn systemd service, nginx reverse proxy
  (HTTPS via Certbot), .env management (dev vs prod), MySQL config tuning,
  upgrade procedure, rollback procedure.

**Backlog after Phase B3:**
- Task #84 [FUTURE] field sosial media pasien (Instagram, WhatsApp link).
- Multi-cabang support (kalau klinik buka cabang ke-2 di masa depan).
- Push notification / WhatsApp reminder appointment (out of scope Phase 1).

---

## Sprint 6 Juni 2026 Malam — Bug Fix Marathon + DEC-050/051/052

**Status:** 🟢 8 bug closed dalam 1 sesi (~6 jam). FLOW-D Opsi C lengkap
(Part A + B + C). Timezone bug fundamental ditemukan & di-fix.

### Bug Fixed (sesi 6 Jun 2026 malam)

| ID | Issue | Closed Via |
|----|-------|-----------|
| BUG-A | Beli Produk tanpa konsul → 404 Page Not Found | Restore route `/web/pasien/{id}/beli-produk` GET + POST yang hilang akibat B-013 truncation sesi sebelumnya |
| BUG-B | Halaman riwayat pembayaran tampilkan items 0 + total Rp 0 walau nota benar | Refactor `KasirService.get_tagihan()` jadi 3-mode + populate rincian dari snapshot existing transaksi |
| BUG-C | Tombol +Upsell di Perawat tidak respond saat diklik | JS syntax error duplicate `if (!pinInput.value...)` line di perawat_tindakan.html, IIFE fail → window.openUpsellModal undefined |
| FLOW-D | Status kunjungan tidak revert saat dokter add tindakan post-lunas | Auto-revert ANTRI_OBAT/ANTRI_BAYAR → ANTRI_TREATMENT di PemeriksaanService (DEC-050) |
| FIX-ST-1 | StatusRencanaEnum ImportError (typo, real name `StatusRencanaTreatmentEnum`) | sed rename di 2 file service |
| FIX-ST-2 | Duplicate `detail=` kwarg di KasirService raise HTTPException | `sed -i '498d'` |
| FIX-ST-3 | FO dropdown +Antrian tidak ada opsi Lanjut Series | `pasien_search_partial` join series_pending + tombol di dropdown |
| FIX-ST-4 | Hard-stop Rp 0 di Kasir untuk series sesi 2..N | Conditional bypass `total_tagihan == 0` |
| **BUG-1517** | **Tindakan tambahan miss di tagihan setelah upsell** | **TreatmentService pakai `datetime.utcnow()` vs `datetime.now()` di rest of codebase. Selisih 7 jam (WIB-UTC). Fix di DEC-052 + script offset +7 jam ke 23 legacy tindakan.** |
| B-014 | `bhp_terpotong is not defined` error saat end tindakan | Variable salah di restored code, ganti ke `len(hasil_potong)` |
| B-015 | AntrianDokterResponse 500 — field `data` vs `items` mismatch | Schema requires `data` + `tanggal` + `total`, fix construct dengan correct field names |
| FIX-Upsell-Produk | Dropdown produk di Upsell modal tidak bisa dipilih | Hapus `disabled` initial + manage Tom Select via API enable/disable |
| FIX-Beli-Produk-2 | AttributeError `'PasienService' has no attribute 'repo'` | Ganti `pasien_svc.repo` → `pasien_svc.pasien_repo` |

### FLOW-D Opsi C — Implementation Recap

| Part | Status | What |
|------|--------|------|
| A | ✅ | Auto-revert status di PemeriksaanService kalau dokter add tindakan post-lunas |
| B | ✅ | KasirService timestamp-based detection of items_belum_berbayar + "Tagihan Tambahan" banner |
| C | ✅ | Cap max 1 reopen per kunjungan (DEC-051), block reopen ke-3 dengan error message clear |

### Workflow Caveats Updated

**B-013 (rekuren) — File truncation saat Edit/heredoc**: Pattern masih
mengganggu sesi panjang. Mitigation di sesi ini:
- Pakai `Write` tool untuk file replace atomic (lebih reliable).
- Sebelum heredoc append, baca tail dulu untuk tahu boundary.
- Setelah operasi besar, verify dengan `ast.parse` + `tail -3`.
- Hindari operasi besar di file > 500 lines, prefer rewrite via head + heredoc.

**B-016 (NEW) — Timezone consistency**: Lihat DEC-052. Selalu pakai
`datetime.now()` (local), bukan `datetime.utcnow()`. Test scenario harus
include flow yang span multiple events di hari yang sama untuk catch
timezone bug.

### Test Coverage Improvements (sesi ini)

- ✅ Real-world test scenario "konsul → resep saja → lunas → tambah tindakan
  via Ubah Konsul → eksekusi + upsell → bayar lagi" — flow lengkap berjalan.
- ✅ Series Treatment flow lengkap test (Setup harga paket → SOAP centang →
  Kasir tagih paket → FO booking sesi lanjutan via dropdown).
- ✅ Cap 1 reopen: error message muncul saat coba reopen ke-3.
- ✅ Print Module: nota cetak benar dengan auto-print after lunas.
- ✅ Multi-tenant: nama klinik persist across navigation.

### Phase 1 Status — 100% complete, Phase B status update

**Phase B Soft Launch:**
- ✅ B1 Backup Script
- ✅ B2 User Manual (initial) + **B2.1 Addendum v1** (sesi ini, 6 bab + 20 screenshot)
- ✅ Print Module Phase A
- ✅ Multi-Tenant Klinik Config
- ✅ Series Treatment Refactor
- ✅ Searchable Dropdown
- ✅ **FLOW-D Opsi C lengkap (Part A + B + C)** ← NEW sesi ini
- ✅ **Timezone Bug Fix (DEC-052)** ← NEW sesi ini
- 📋 **B3 Deployment Guide** (sisa)
- 📋 PRE-B3 #2 Multi-user concurrent test
- 📋 PRE-B3 #3 Full Recheck + Backup

## Sprint 7 Juni 2026 Pagi — SOAP-GUARD + TIER-SYS + Stress Test Fase 1+2

### Closed in This Sprint

- ✅ **#321 SOAP-GUARD** — Day Rollover Lock + Owner-Check Level Medium implementasi.
  Test PASS semua 4 scenario user. (DEC-053)
- ✅ **#323 TIER-SYS** — 4-tier role hierarchy backend foundation. Hard guard
  OWNER role + tier-based promotion check. (DEC-054)
- ✅ **#322 STRESS-TEST Fase 1+2** — Smoke single + Concurrent 3 user. Zero
  errors, p95 < 25ms semua endpoint. (DEC-055)

### B-013 — File Truncation Recurring (Updated)

**Status:** Open (operational workaround documented di DEC-056).

**Strike 2026-07-02:** kambuh 2× di sesi nota — `print_service.py` (potong di `_audit_print`) &
`nota_thermal.html` (buang endblock terakhir, 127 null byte) saat `Edit` kecil. Dipulihkan via bash
splice/re-append. Cek null byte pakai `python3 -c "...count(b'\x00')"` — BUKAN `grep -c $'\x00'`
(bash kolaps ke empty pattern → false-positive semua baris). Lihat DEC-090.

**Pattern terdeteksi:**
- Multiple file modifications via Edit tool kadang truncate file mid-statement
- Belum bisa identify trigger spesifik
- Workaround: AST parse setelah every edit + head + heredoc restore

**Sepanjang 7 Juni pagi terjadi 4x:**
1. pemeriksaan_service.py (line ~558 truncated mid-string "AN)
2. kunjungan_repo.py (line 256 mid-statement "for key, value")
3. dokter.py (line 362 "template_name = (" tanpa closing)
4. tools/stress/04_fase2_locust.py (line 262 mid-print SQL string)

Semua berhasil di-restore via heredoc + AST verify.

### Findings Tracked Sebagai Pending Task

- **Task #326** — Master Staf UI lacks role edit form (intentional safe state).
  Backend guard tier sudah siap kalau UI dibangun nanti.
- **Task #329** — FO-ASSIGN-DOKTER insight dari real test:
  saat FO daftarkan pasien konsultasi, opsional pilih dokter yang dituju.
  Schema change: kunjungan.id_staf_dokter_assigned (nullable).
  Implementation post-launch.
- **Task #324** — REPORTS-COMPART (per-role compartmentalization Reports UI).
  Backend tier helpers ready, UI work pending.
- **Task #325** — FIN-REPORTS module Owner-only. Belum implementasi.

### Stress Test Infrastructure

- `tools/stress/` folder dibuat dengan README + 3 script (seed + Fase 1 + Fase 2)
- `db_sehati_test` DB terpisah, isolated dari production
- Test uvicorn pattern: `DB_NAME=db_sehati_test uvicorn ... --port 8001`
- Fase 3+4 (7 user + 15 user) di-defer ke sesi berikutnya


## Sprint 8 Juni 2026 Pagi — FO-ASSIGN-DOKTER + UX Refinement

### Closed in This Sprint

- ✅ **#329 FO-ASSIGN-DOKTER** — Pre-assign dokter di FO registrasi flow
  (DEC-058). 8 layer implementation + 3 UX fix post real-test.
- ✅ **#309 PRE-B3 #2** — Multi-user concurrent test sudah dilakukan via
  STRESS Fase 1-4 (DEC-055/057). Marked complete.
- ✅ **#310 PRE-B3 #3** — Backup script sudah ada (B1.1-1.4), healthcheck
  sudah complete (#192-197). Marked complete.

### FO-ASSIGN-DOKTER Workflow Coverage

| Entry Point | Field "Dokter Dituju"? |
|-------------|------------------------|
| Pendaftaran pasien baru wizard | ✅ |
| Search pasien existing → +Antrian dropdown | ✅ |
| Antrian Hari Ini → Ubah Dokter (terpisah dari Ubah Status) | ✅ |
| Beli Produk | ❌ excluded per spec dr. Hansen |
| Lanjut Series | ❌ excluded (direct ANTRI_TREATMENT) |

### UX Findings dari dr. Hansen Real-Test

1. **Kolom "Dokter Dituju" perlu di Antrian Hari Ini list** —
   FO perlu lihat distribusi beban per dokter.

2. **Tombol "Ubah" misleading semantics** —
   Awalnya 1 tombol yang campurkan pilih dokter + ubah status.
   Klik tombol status mengubah keduanya. Pisahkan jadi 2 tombol jelas:
   "🩺 Dokter" untuk reassign (status tetap) dan "Ubah Status" untuk
   transisi state machine.

3. **Real-time reassign visibility** — sudah aktif dari backend P3
   antrian filter scoping. FO ubah Dr. X → Y, refresh Dokter X = pasien
   hilang, refresh Dokter Y = muncul.

### Status Pending Tasks (Updated)

**Quality / Pre-launch:**
- #317 Audit attribute access pattern (Quality scan, ~30 min) — pending
- #324 REPORTS-COMPART per-role compartmentalization (~2-3h) — pending

**Optional / Post-launch friendly:**
- #325 FIN-REPORTS module Owner-only (~4-6h) — pending
- #326 Master Staf Role Edit UI (~2-3h) — pending (backend TIER-SYS ready)
- #84 Sosial media pasien field (~1-2h) — pending future

**Documented but not blocking:**
- B-013 file truncation workaround tetap operasional practice (DEC-056)


## #317 Audit Attribute Access — Completed Clean (8 Juni 2026 pagi)

**Status:** Closed clean. Codebase tidak punya AttributeError potential di
pattern `Service(db).attribute` atau `var = Service(db); var.attr`.

### Service Attribute Inventory (Reference Matrix)

| Service | Valid Attributes (instance vars di `__init__`) |
|---------|----------------------------------------------|
| AntropometriService | `db`, `kunjungan_repo`, `pasien_repo`, `audit` |
| ApotekService | `db`, `repo`, `kunjungan_repo`, `audit` |
| AuthService | `db`, `staf_repo`, `audit` |
| DashboardService | `db` |
| ExportService | `db` |
| InventoryService | `db`, `inv_repo`, `treatment_repo` |
| KasirService | `db`, `repo`, `kunjungan_repo`, `staf_repo`, `membership`, `audit` |
| KlinikConfigService | `db` |
| KunjunganService | `db`, `kunjungan_repo`, `pasien_repo`, `audit` |
| MasterProdukService | `db`, `repo`, `audit` |
| MasterTreatmentService | `db`, `repo`, `audit` |
| MembershipService | `db` |
| OpnameService | `db`, `repo`, `inv_repo`, `audit` |
| PasienService | `db`, `pasien_repo`, `kunjungan_repo`, `audit` |
| PemeriksaanService | `db`, `pemeriksaan_repo`, `kunjungan_repo`, `pasien_repo`, `antropometri`, `audit` |
| PemesananService | `db`, `repo`, `produk_repo`, `inv_repo`, `audit` |
| PrintService | `db` |
| ReportsService | `db` |
| SeriesService | `db`, `audit` |
| StafService | `db`, `repo`, `audit` |
| TreatmentService | `db`, `treatment_repo`, `kunjungan_repo`, `audit`, `inventory` |
| UpsellService | `db`, `kunjungan_repo`, `pemeriksaan_repo`, `staf_repo`, `audit` |

### Naming Convention Insight

**Service dengan repo nama "spesifik" (BUKAN `self.repo`):**
- PasienService → `pasien_repo`
- KunjunganService → `kunjungan_repo`
- PemeriksaanService → `pemeriksaan_repo`
- TreatmentService → `treatment_repo`
- AuthService → `staf_repo`
- InventoryService → `inv_repo`

**Service dengan repo nama generik `self.repo`:**
- ApotekService, KasirService, MasterProdukService, MasterTreatmentService,
  OpnameService, PemesananService, StafService

### Lessons Learned

1. **Naming convention belum konsisten** — half pakai spesifik, half pakai
   generik `self.repo`. Tidak masalah selama caller pakai nama yang benar.
2. **Audit clean = sustaining quality** — BUG-A tidak regresi sejak fix.
3. **Reference matrix ini bisa di-print di docs/internal** untuk staf baru
   yang join project nanti.

### Audit Tool Recipe (untuk reuse)

Script audit ada di chat history sesi ini. 3 scan pattern:
1. Direct `Service(db).attr` chain
2. Variable assignment `var = Service(db)` + later usage
3. Instance variable `self.xxx_svc = Service(db)` + later usage

Plus specific bug pattern `Service(db).repo` untuk services yang tidak punya `.repo`.


## Sprint 8 Juni 2026 Siang — REPORTS-COMPART + Komisi Foundation

### Closed in This Sprint

- ✅ **#324 REPORTS-COMPART** — Per-role compartmentalization Reports UI lengkap
  + 2 fix UX (breadcrumb omzet clickable, total_dibayar field name)
- ✅ **#360 + #361 (backend done)** — Komisi system foundation: 9 kolom baru
  (5 di master_treatment, 4 di master_produk) + 2 helper functions module-level
  dengan formula closed-form. Form UI pending sesi berikutnya.

### Finance Module Decision

- **TODO #366 Finance Module** — Design document komprehensif di
  `outputs/FINANCE_MODULE_DESIGN.md`. Status: **undecided**, butuh konsultasi
  finance consultant + 13 jawaban pertanyaan strategis. Bukan blocker launch.

### Insight Strategis dari dr. Hansen

1. **Komisi dari laba bersih, bukan harga jual** — lebih fair untuk klinik.
   Formula closed-form `(harga - BHP - pajak) / (1 + Pd + Pp)` menyelesaikan
   recursive dependency (HPP butuh komisi, komisi butuh laba, laba butuh HPP).
2. **Klinik akan jadi PT Non-PKP** — pakai PPh Final UMKM 0.5% di tahun-1,
   PKP nanti kalau omzet > Rp 4.8M.
3. **Mau bangun finance internal vs pakai 3rd party software** — perlu
   konsultan finance dulu. Saya saran tahun-1 software 3rd party
   (Accurate/Jurnal Mekari ~Rp 200-350k/bln), tahun-2 evaluate.

### Workflow Dependencies (Foundation → Future)

```
DEC-059 (Komisi Foundation)
    ├─→ #363 Apoteker reports + write-off
    ├─→ NEW: Report Perawat (tindakan + komisi)
    └─→ Refactor Kinerja Dokter (include komisi)

#360 + #361 (Backend Komisi DONE)
    └─→ #369 + #372 (Form UI — pending)

#366 Finance Module (undecided)
    └─→ Auto-journal Komisi sebagai Beban Operasional
```

### Pending Tasks Updated Status

| # | Task | Status |
|---|------|--------|
| #325 | FIN-REPORTS module | Mungkin merge ke #366 Finance Module |
| #326 | Master Staf Role Edit UI | Pending (optional) |
| #360 | Master Treatment komisi (backend) | ✅ Done. Form UI #369 pending |
| #361 | Master Produk komisi (backend) | ✅ Done. Form UI #372 pending |
| #362 | Master Membership privilege | Pending (kompleks, butuh design) |
| #363 | Apoteker reports + write-off | Pending |
| #364 | Void Pembayaran flow | Pending |
| #366 | Finance Module | Undecided, butuh konsultan |
| #84 | Sosial media pasien | Future |


---

## Sprint 8 Juni 2026 Sore — Komisi Refactor DEC-060

### ✅ Resolved
- **#360 + #361 Komisi System** — Refactor dari formula recursive ke akuntansi standar selesai. Lihat DEC-060.
- **#375 Hybrid Komisi Refactor** — Migration 012 ter-apply di production + test DB. 7 row treatment + 5 row produk verified.

### 🐛 Bug Notes — B-013 Recurrence Aggressive
**B-013 (Recurring File Truncation)** kambuh **3× berturut-turut** dalam 1 sesi refactor:
1. `app/db/models/treatment.py` kepotong di line 211 (mid `qty_per_iterasi: Mapped[`)
2. `app/db/models/produk.py` kepotong di line 90 (mid `func.current_ti`)
3. `app/services/master_produk_service.py` kepotong 2× di set_active method (mid `id_target=p` lalu mid `request=reque`)

**Pattern observed:**
- File yang relatively besar (>200 LOC) lebih rentan
- Edit `replace_all=false` saat context window panjang → risiko tinggi
- Auto-restore via `head -N + heredoc + AST verify` (workaround DEC-056) bekerja konsisten

**Mitigation untuk masa depan:**
- Pertimbangkan refaktor Edit besar pakai Write tool (full file replacement) untuk file critical
- Tetap jalankan AST parse + grep residual setelah setiap batch edit pada file > 200 LOC
- Backup project source code (bukan hanya DB) di future B1 enhancement

### ⏭ Pending Implementation (Foundation Layer Complete)
- **#369** Form UI Master Treatment — dropdown tipe komisi (PERSEN_HARGA / PERSEN_MARGIN / NOMINAL / NULL) + input value + preview kalkulasi
- **#372** Form UI Master Produk — sama tapi single dokter
- **#373** Verify smoke test end-to-end setelah UI ready

### 📋 Future Modul Yang Akan Terdampak DEC-060
- **Reports Kinerja Dokter** — query SUM(komisi) harus dipindah ke helper `hitung_komisi_treatment/produk` (tidak bisa SUM kolom langsung lagi karena hybrid mode)
- **Future Finance Module (#366)** — base data sekarang sesuai akuntansi standar: Revenue → COGS (BHP + komisi) → Gross → Tax → Net Income

---

## Sprint 8 Juni 2026 Malam — #369 Form UI Master Treatment + Bug Marathon

### ✅ Resolved
- **#369 Form UI Master Treatment** — Section "Biaya, Pajak & Komisi" lengkap: BHP, pajak %/nominal, komisi dokter (tipe + value), komisi perawat (tipe + value, independent), preview kalkulasi reactive JS
- **Schema mismatch produk** — Model `produk.py` di-rewrite clean dari scratch agar match exact 19 kolom DB. DB master_produk TIDAK punya `created_at`, `catatan`, `id_staf`. Hanya `updated_at`.
- **Service master_treatment** — Restore `tambah_komponen` + `hapus_komponen` + `set_active` yang ter-truncate oleh B-013

### 🐛 Bug-bug yang Fixed Hari Ini

| # | Bug | Root Cause | Fix |
|---|-----|------------|-----|
| 1 | Layout Master Treatment kacau (button melayang) | Duplikat `<div class="flex...">` saat restore | Hapus baris duplikat, div balance = 0 |
| 2 | SQL error `master_produk.catatan` | Salah inject Text + catatan saat restore produk.py | Hapus catatan + Text import |
| 3 | SQL error `master_produk.id_staf` | Salah ganti catatan → id_staf (asumsi salah) | Hapus id_staf |
| 4 | SQL error `master_produk.created_at` | Model punya field, DB tidak | Rewrite model exact match DB schema |
| 5 | Decimal not JSON serializable | Field hybrid baru tidak masuk `_NUM_FIELDS` | Tambah 5 field ke tuple |
| 6 | `tambah_komponen() missing 'qty' and 'satuan'` | Lupa pass kwargs ke service | Tambah qty + satuan |
| 7 | `hapus_komponen` RedirectResponse tanpa url | B-013 truncation | Restore full URL string |
| 8 | `add_komponen via service belum diimplementasi` | Stale .pyc cache + service truncated | Restore method implementation lengkap |

### 🚨 B-013 Recurrence Pattern — 7× dalam 1 Sesi

**Trend critical:** B-013 makin agresif seiring context window panjang. Per-file truncation pattern:

1. `app/db/models/treatment.py` — line 211 mid `qty_per_iterasi: Mapped[`
2. `app/db/models/produk.py` — line 90 mid `func.current_ti`
3. `app/services/master_produk_service.py` — 2× di set_active method
4. `app/db/models/produk.py` — null bytes appended
5. `app/web/templates/master_treatment_form.html` — line 207 mid button class
6. `app/web/routes/master.py` — line 798 mid `tambah_komponen(`
7. `app/web/routes/master.py` — line 843 mid string `?ok`
8. `app/services/master_treatment_service.py` — line 311 mid `self.db.ro`

**Workaround DEC-056** (head -N + heredoc + AST verify) bekerja konsisten, tapi friction tinggi. Kadang null bytes muncul di akhir file — `rstrip(b'\x00')` perlu.

**Lesson untuk sesi ke depan:**
- Edit file > 200 LOC dengan context > 50% window → very risky
- Pakai Write tool (full rewrite) lebih aman dari Edit replace untuk file critical
- Setelah setiap Edit chunk file besar, langsung jalankan AST verify
- Punya backup source code (bukan hanya DB) di backup ZIP — currently backup hanya berisi DB + uploads, source code TIDAK di-backup. Risk!

### ⏭ Pending Next Session
- **#372** Form UI Master Produk hybrid komisi (analog #369 tapi single dokter)
- **#373** Smoke test instruction end-to-end
- Pertimbangkan tambah source code ke `backup.py` script untuk mitigasi B-013 cascade

### 📌 Recovery Note
Bila B-013 terjadi lagi di file yang sama, urut prioritas restore:
1. AST/syntax verify dulu
2. Cek null bytes (`rstrip(b'\x00')`)
3. Cek struktur HTML div balance
4. Match exact field name dengan DB schema (lesson dari produk.py)

---

## Sprint 9 Juni 2026 Pagi — #372 Complete

### ✅ Resolved
- **#372 Form UI Master Produk** — Section hybrid komisi (HPP + pajak + komisi dokter single, NO perawat)
- **B-013 fallout `ProdukGenericResponse` missing** — Restored 2 schema class yang hilang saat restore tail sesi kemarin
- **DEC-061 Action Item 1 IMPLEMENTED** — `scripts/backup.py` sekarang include source code (app/, migrations_sql/, seed_data/, scripts/, Project_Memory/) per recovery best practice

### 🐛 B-013 Sesi Ini — Hanya 2×
Strategi defensif lebih efektif:
1. Pakai Write tool untuk full rewrite saat file > 200 LOC
2. AST verify after EVERY edit chunk
3. Small targeted Edit only, hindari edit di file critical besar dalam 1 chunk

### ⏭ Pending Next
- **#373** Smoke test end-to-end komisi system (manual instruction sambil Bapak run app)
- **Run backup baru dengan source bundle** untuk validasi backup script extension

---

## Sprint 10 Juni 2026 — #326 Role Edit + Dokter Dropdown Cleanup

### ✅ Resolved
- **#326 Master Staf Role Edit UI** — Card "Ubah Role" Owner-only di staf_detail. Service + Route + Template lengkap dengan 3 validasi (tier hierarchy, self-edit block, dokter antrian aktif block).
- **Owner removal dari dropdown dokter** — `get_dokter_aktif_list()` sekarang return DOKTER saja. 3 entry point auto-update (FO pendaftaran, antrian, search).
- **[BE-04] Bare except `_shared.py:413`** — diganti dengan `logging.warning()` untuk visibility.

### 🟢 Health Check Status: PERFECT
Final run (10 Juni 2026):
- 🔴 CRITICAL: 0
- 🟠 HIGH: 0
- 🟡 MEDIUM: 0
- 🟢 LOW: 0

Trend: improving dari MEDIUM 1 → 0 dalam 1 sesi.

### 🐛 B-013 Recurrence Sesi Ini
3× truncation:
1. `staf.py` mid-fstring
2. `staf_detail.html` mid-comment
3. `_shared.py` mid-`__all__`

Semua restored via heredoc. Pattern konsisten: B-013 hit saat Edit di file dengan context panjang. Workaround DEC-056 efektif.

### ⏭ Sprint Akhir Belum Selesai
- #325 FIN-REPORTS — blocked by #366
- #362 Master Membership — butuh design
- #363 Apoteker Reports
- #364 Void Pembayaran
- #366 Finance Module — undecided

---

## 📚 Sesi 10 Juni 2026 — Void Pembayaran (#364) — Marathon Bug History

Pattern bug yang ditemukan saat implement Void Pembayaran (#364), didokumentasikan
sebagai referensi historis. Beberapa bug ini sudah di-fix, sisanya catatan
untuk avoid re-introduction di feature lain.

### 🐛 B-013 Recurrence — 10+ kali sesi ini
File yang terkena truncation berulang:
- `app/db/models/_enums.py` × 2 (saat tambah VoidReasonEnum + VoidApprovalMethodEnum)
- `app/db/models/__init__.py` (duplicate row TransaksiPembayaran)
- `app/db/models/transaksi.py` (lost 2 classes — TransaksiDetailProduk + TransaksiPembayaran)
- `app/services/kasir_service.py` × 3 (CATASTROPHIC: lost entire file → restored from safepoint zip)
- `app/services/staf_service.py` (mid-string `f"...{role.value}` truncated)
- `app/services/print_service.py` (mid-dict-literal)
- `app/web/routes/kasir.py` × 2 (mid-statement truncate)
- `app/web/routes/master.py` (tail truncate mid-RedirectResponse)
- `app/web/templates/kasir_bayar_sukses.html` × 2 (mid-tag + body lost)
- `app/web/templates/kasir_tagihan.html` × 3 (76 null bytes appended, tail truncate)
- `app/web/templates/print/nota_a5.html` (truncate mid-block)
- `app/web/templates/print/nota_thermal.html` (truncate mid-content)
- `app/schemas/kasir.py` × 2 (`"Void` mid-string literal)

**Mitigation**:
- Safepoint backup zip dibuat di awal sesi (`safepoint_pre_void_*.zip`,
  `safepoint_pre_bugfix_*.zip`, `safepoint_pre_p4_*.zip`)
- Recovery pattern: `unzip safepoint -d /tmp/restore && python3 patch_script.py`
- Python script dengan AST.parse + Jinja.parse verify SEBELUM write
- Hindari Edit tool untuk file > 800 lines kalau ada banyak context window
- Defensive: cek null bytes count + brace balance setelah setiap edit

### 🐛 B-015 (NEW) — HTML Attribute Quote Collision di Jinja Render
**Pola**: `onclick="someFn({{ var|tojson }})"` di mana `var` adalah string.

Jinja `|tojson` output dengan literal double quotes (`"value"`). Ditaruh di dalam
`onclick="..."` (juga double quote) → HTML parser melihat:
```html
onclick="someFn("  ← attribute closes
value             ← invalid HTML
")"               ← garbage
```

Hasil: JavaScript dapat input malformed → `Uncaught SyntaxError: Unexpected end of input`.
Onclick tidak terdaftar dengan benar → tombol tidak respond saat diklik.

**Fix**: gunakan single quote di luar + `|forceescape` filter:
```html
onclick='someFn({{ var|tojson|forceescape }})'
```
Render jadi:
```html
onclick='someFn(2047, &#34;Nucral Sirup&#34;)'
```
Double quotes di-encode sebagai HTML entity `&#34;`. JS dapat string utuh saat decode.

**Lokasi awal**: `kasir_tagihan.html` line 142 — tombol Void per item.
**Lesson**: SEMUA atribut HTML yang embed JSON value harus pakai pattern ini.

### 🐛 B-016 (NEW) — Flash Banner Hilang di Halaman Sukses
**Pola**: Redirect setelah POST dengan `?err=...` di URL → halaman tidak render.

Saat void transaksi validation gagal di server-side, route catch HTTPException dan
`return RedirectResponse(url=f"/web/kasir/bayar/sukses/{id}?err={detail}")`.
Browser navigasi ke halaman bayar_sukses dengan query param `?err=...`.

Tapi template `kasir_bayar_sukses.html` tidak baca/render `request.query_params.get("err")`.
User lihat halaman tampak sama → mengira aksi tidak jalan, padahal sebenarnya server
sudah menolak dengan error message yang lengkap.

**Fix**: tambah flash banner block di atas page_content:
```html
{% set _err = request.query_params.get("err") %}
{% if _err %}
<div class="bg-red-50 ...">⚠ Aksi Gagal — {{ _err }}</div>
{% endif %}
```

**Defense in depth**: tambah client-side validation di JS sebelum submit, supaya tidak
perlu round-trip ke server untuk catch validation errors.

**Lesson**: SETIAP halaman yang bisa jadi target redirect dengan `?err=` atau `?ok=`
WAJIB render flash banner. Audit semua redirects di code base.

### 🐛 B-017 (NEW) — Allowlist Repository Silently Ignores Update
**Pola**: `repo.update(obj, {"field": value})` dengan allowlist field filter.

`StafRepository.update()` punya `ALLOWED = {"nama_staf", "role", "username"}`. Field
di luar set itu diabaikan tanpa error/warning. `StafService.set_active()` panggil
`self.repo.update(staf, {"is_active": is_active})` — `is_active` bukan di allowlist
→ silent skip → database tidak ke-update → tombol nonaktif staf tampak tidak respond.

**Fix**: ada method dedicated `repo.set_active(staf, is_active)` yang juga handle
force-logout. Service harus panggil method itu, bukan `repo.update()`.

**Lesson**: allowlist filter di repo HARUS log warning kalau ada field yang ditolak.
Better: pisahkan setter per kelompok field (basic info, security, status) supaya
maintainer code paham field mana dipakai dimana.

### 🐛 B-018 (NEW) — Route Tidak Return di Success Path
**Pola**: try/except handle error paths tapi success path tidak ada return statement.

`pasien_beli_produk_submit` di pasien.py:
```python
try:
    result = KunjunganService(db).beli_produk_lengkap(...)
except HTTPException as e:
    return RedirectResponse(...)
except Exception as e:
    return RedirectResponse(...)
# ← no return here on success
```

FastAPI default response: kalau function return `None`, serialize sebagai JSON `null`.
User lihat halaman literally bertuliskan `null`.

**Fix**: tambah RedirectResponse success setelah try/except block:
```python
return RedirectResponse(url=f"/web/kunjungan?ok=...", status_code=303)
```

**Lesson**: setiap route POST WAJIB explicit return di SEMUA cabang. Linter rule
mypy `--strict` would catch ini. Audit semua endpoint POST.

### 🐛 B-019 (NEW) — Void Cascade Tidak Lengkap (FLOW-V6)
**Pola**: state transition update parent tidak cascade ke child.

`void_transaksi()` update `transaksi_kasir.status_transaksi = VOID` tapi:
- Tidak update `kunjungan_resep.status_item` (tetap DIBAYAR)
- Tidak update `kunjungan.status_antrian` (tetap ANTRI_OBAT)

Akibatnya: apotek antrian tetap lihat pasien yang transaksinya void, masih bisa
klik Serahkan obat → konflik data.

**Backfill**: Trx #621 dan #622 sebelum fix tidak ke-cascade. Bapak putuskan
biarkan saja sebagai contoh historis. Trx baru yang di-void setelah fix akan
ke-cascade otomatis (resep DIBAYAR → BATAL, kunjungan → COMPLETED).

**Fix**: tambah helper `_cascade_void_kunjungan(id_kunjungan, actor, request)`
yang dipanggil setelah void berhasil. Audit log entries baru:
- `VOID_RESEP_CASCADE` per resep
- `VOID_KUNJUNGAN_FORWARD` kalau kunjungan move ke COMPLETED

**Lesson**: setiap state transition di parent table WAJIB di-evaluate dampaknya
ke child tables. Buat matrix `(parent_state, child_state) -> action` saat design.
Test scenario: bayar → lihat child state → void → konfirmasi child state ter-update.

---

## 🎯 Pattern Library — Untuk Re-Use di Feature Lain

1. **HTML attribute JSON embed**: SELALU pakai single quote luar + `|forceescape`
2. **Flash banner template**: WAJIB render `?err` dan `?ok` di semua halaman target redirect
3. **Repository update allowlist**: log warning kalau ada field ditolak, atau pisahkan setter per group
4. **Route POST return path**: explicit return di SEMUA cabang termasuk success
5. **State cascade**: design matrix parent→child sebelum implement, test cascade end-to-end
6. **B-013 mitigation**: safepoint zip di awal, AST/Jinja verify setelah edit, hindari Edit untuk file > 800 lines

---

## ⚠️ Test Coverage Status — Akhir Sesi 10 Juni 2026

**TESTING COMPREHENSIF BELUM DILAKUKAN UNTUK SESI INI.**

Hanya bagian Void Pembayaran (#364) yang Bapak test secara end-to-end:
- ✅ Void per item (kasir tagihan, sebelum bayar) — tested
- ✅ Void transaksi same-day (Pembayaran Berhasil) — tested
- ✅ Cetak nota dengan watermark VOID — tested
- ✅ Cascade resep BATAL + kunjungan COMPLETED — tested
- ✅ Force Past-Day Void (Owner) — UI tested, belum test submit aktual
- ⚠️ Force Past-Day Void via Cari Transaksi — UI rendered, belum test submit
- ⚠️ Force Void Day 0 (Admin override) — UI rendered, belum test submit
- ⚠️ Limit Admin 3 hari — belum test boundary
- ⚠️ Limit Owner 7 hari — belum test boundary

### Yang TERSENTUH Sesi Ini Tapi BELUM Di-Retest Manual

**Schema/Model**:
- `app/db/models/_enums.py` — restored multiple kali via heredoc. AST OK tapi belum tes enum value sama dengan DB
- `app/db/models/transaksi.py` — TransaksiKasir + TransaksiDetailProduk + TransaksiPembayaran restored
- `app/db/models/__init__.py` — import + __all__ restored

**Service Layer**:
- `app/services/kasir_service.py` — paling banyak ke-touch (1033 lines), recovered dari catastrophic overwrite via safepoint. Existing flow yang BELUM retest: `get_tagihan`, `proses_bayar`, `void_item_resep` (legacy PIN flow removed → self-acc), `rekap_shift`, `_compute_charge` (series pricing)
- `app/services/staf_service.py` — `set_active()` patched, belum retest aktif/nonaktif flow
- `app/services/print_service.py` — VOID info added, belum retest nota normal (non-void) rendering

**Routes**:
- `app/web/routes/kasir.py` — 3 route baru + 1 route get_tagihan patched dengan `user_role` param. Belum retest: bayar, void item, rekap, antrian
- `app/web/routes/pasien.py` — `pasien_beli_produk_submit` success redirect added, belum retest beli produk flow
- `app/web/routes/master.py` — tambah komponen kategori fix, belum retest CRUD treatment komponen
- `app/web/routes/staf.py` — touched untuk staf service, belum retest

**Templates**:
- `app/web/templates/kasir_tagihan.html` — 557 lines, banyak conditional baru. Belum retest: render normal (sudah_lunas=False), render lunas non-void, render lunas voided
- `app/web/templates/kasir_bayar_sukses.html` — modal void + flash banner + client validation. Belum retest scenario sukses bayar normal (tanpa void)
- `app/web/templates/print/nota_a5.html` + `nota_thermal.html` — belum retest nota normal (non-void) printing
- `app/web/menu.py` — MENU_KASIR_CARI_TRANSAKSI added. Belum retest menu rendering per role lain

### Last Comprehensive Test
**Test menyeluruh terakhir = sebelum Void Pembayaran implementation dimulai** (sebelum sesi 10 Juni 2026 sore).

### Rekomendasi Test Plan Sesi Berikutnya
Sebelum lanjut implement Phase 5-6 #364 atau feature baru, sebaiknya:

1. **Smoke test full role journey** (sample 1 pasien per role):
   - FO daftar pasien baru → assign dokter
   - Dokter SOAP → tindakan + resep
   - Perawat eksekusi tindakan
   - Kasir bayar tagihan (test scenario: normal + ada void per item)
   - Apoteker serahkan obat
   - Owner buka Reports + Cari Transaksi

2. **Regression test focal areas yang banyak ke-touch sesi ini**:
   - kasir_service.proses_bayar (DB transaction integrity)
   - kasir_service.get_tagihan (semua flow: belum lunas + sudah lunas + voided)
   - print_service untuk nota normal vs nota void

3. **Edge case yang belum dicover**:
   - Void transaksi yang mengandung tindakan series sesi 1 → cek apakah rencana sesi 2-N batal
   - Force void Day 0 sebagai Admin (bukan Owner) — limit 3 hari boundary
   - Bayar dengan diskon membership → void → kuota balik

4. **Cleanup data test #621, #622** (yang di-skip cascade backfill) — manual ubah DB atau biarkan sebagai contoh historis.

---

## 🐛 New Bug Patterns — Sesi Sambungan 11 Juni 2026

Smoke test full role journey + 4 bug fix tambahan. Patterns documented:

### 🐛 B-020 (NEW) — Jinja `dict.items` Shadowed by Builtin Method
**Pola**: Saat dict di-pass ke Jinja template dan dict punya key bernama `items`, `keys`, `values`, `get`, dll → Jinja resolve sebagai attribute access ke method built-in, BUKAN key lookup.

**Example**:
```python
data = response.model_dump()  # {"items": [...], "page": 1, ...}
return templates.TemplateResponse("page.html", {"data": data})
```

```jinja
{# Crash! Jinja resolve data.items → dict.items method #}
{{ data.items|length }}
{% for it in data.items %}...{% endfor %}
```

**Error**: `TypeError: object of type 'builtin_function_or_method' has no len()`

**Fix**: Pakai bracket syntax `data["items"]`:
```jinja
{{ data["items"]|length }}
{% for it in data["items"] %}...{% endfor %}
```

**Better practice**: Hindari nama key yang sama dengan dict builtin (`items`, `keys`, `values`, `get`, `update`, `pop`, `clear`, `copy`, `setdefault`).

**Lokasi awal**: `app/web/templates/reports_void.html` saat implement Phase 6 #364.

---

### 🐛 B-021 (NEW) — FastAPI Optional[int] Tolak Empty String dari Form
**Pola**: HTML form `<input type="number" optional>` submit empty string `""` saat field tidak diisi. FastAPI Pydantic validator untuk `Optional[int] = None` di route signature tolak parse `""` jadi int → 422 Validation Error.

**Example**:
```python
@router.get("/reports/void")
def reports_void(
    kasir_id: Optional[int] = None,  # ← submit empty "" → 422
    ...
):
```

**Error**: 
```
{"detail":[{"type":"int_parsing","loc":["query","kasir_id"],
"msg":"Input should be a valid integer, unable to parse string as an integer","input":""}]}
```

**Fix**: Terima sebagai str + parse manual:
```python
def _safe_int(v) -> Optional[int]:
    """Parse query param int dengan empty string gracefully → None."""
    if v is None: return None
    s = str(v).strip()
    if not s: return None
    try: return int(s)
    except (ValueError, TypeError): return None

@router.get("/reports/void")
def reports_void(
    kasir_id: Optional[str] = None,
    ...
):
    kasir_id = _safe_int(kasir_id)  # ← graceful
```

**Lokasi awal**: 3 endpoint Reports — `/reports/void`, `/reports/void/csv`, `/reports/audit-log` saat smoke test FO journey.

---

### 🐛 B-022 (NEW) — Cascade Filter Hide Items Setelah State Transition
**Pola**: Display query filter berdasarkan **status saat ini** padahal items pernah punya status lain. Kalau ada cascade yang ubah status (e.g. void cascade DIBAYAR → BATAL), items lama jadi tersembunyi dari display.

**Example #1 — Nota cetak**:
```python
# print_service: filter resep yang DIBAYAR untuk cetak nota
.where(KunjunganResep.status_item == StatusItemResepEnum.DIBAYAR)
```
Setelah void cascade FLOW-V6, semua resep → BATAL. Nota cetak ulang → items kosong.

**Example #2 — Detail Tagihan**:
```python
# kasir_service.get_tagihan: filter resep non-BATAL
.where(KunjunganResep.status_item != "BATAL")
```
Same problem: voided transaksi resep → BATAL → tidak tampil.

**Fix**: Conditional filter berdasarkan parent state:
```python
_is_voided = trx.status_transaksi == "VOID"
if _is_voided:
    # No filter atau include BATAL
    resep = query.where(status_item.in_([DIBAYAR, BATAL]))
else:
    # Filter normal
    resep = query.where(status_item != "BATAL")
```

**Pattern Library Entry**:
- SETIAP query yang filter berdasarkan child item status WAJIB cek apakah parent (transaksi) sudah state transition (VOID/CANCEL).
- Display query untuk voided/cancelled records harus tampil context historis (items asli) BUKAN current state filter.

**Lokasi awal**: `print_service.prepare_nota_context` + `kasir_service.get_tagihan` setelah cascade FLOW-V6 implementation.

---

### 🐛 B-023 (NEW) — Field Typo Across Related Tables
**Pola**: Developer ambil field name dari table salah saat join queries karena assumption tanpa schema verify.

**Example**:
```python
# Dashboard kasir stats — JOIN TransaksiKasir + TransaksiPembayaran
select(func.coalesce(func.sum(TransaksiPembayaran.nominal), 0))
.join(TransaksiKasir, ...)
.where(TransaksiPembayaran.waktu_bayar >= today_start)  # ← TYPO
.where(TransaksiPembayaran.waktu_bayar <= today_end)    # ← TYPO
```

`TransaksiPembayaran` tidak punya field `waktu_bayar`. Yang punya `TransaksiKasir` (already in JOIN).

**Error saat query exec**:
```
type object 'TransaksiPembayaran' has no attribute 'waktu_bayar'
```

**Fix**: Cek schema dulu, atau prefer columns dari table yang explicitly in JOIN:
```python
.where(TransaksiKasir.waktu_bayar >= today_start)  # ← correct
.where(TransaksiKasir.waktu_bayar <= today_end)    # ← correct
```

**Lokasi awal**: `dashboard_service.py:_kasir_stats` ditemukan saat smoke test login Kasir.

---

## 📚 Pattern Library Update — 10 Patterns Catalogued

Updated dari sesi 10 Juni + 11 Juni sambungan:

1. **HTML attribute JSON embed** → single quote luar + `|tojson|forceescape`
2. **Flash banner template** → render `?err`/`?ok` di semua halaman target redirect
3. **Repository allowlist** → log warning kalau field ditolak
4. **Route POST return path** → explicit return di SEMUA cabang
5. **State cascade design** → matrix parent→child, test cascade end-to-end
6. **B-013 mitigation** → safepoint zip + AST/Jinja verify
7. **🆕 Jinja dict.items shadowing** → bracket syntax `data["items"]`
8. **🆕 FastAPI form int parsing** → `_safe_int()` helper + accept str
9. **🆕 Cascade filter hide items** → conditional filter based on parent state
10. **🆕 Field typo across tables** → schema verify, prefer JOIN-table columns

---

## ✅ Smoke Test 11 Juni 2026 — Result Summary

Bapak run smoke test full role journey (Owner, FO, Dokter, Perawat, Kasir, Apoteker, Admin).

**Verdict**: ✅ **Tidak ditemukan bug kritis.** Yang ditemukan:
- **4 issue fixed live**: BUG-DASH-KASIR, UI-KASIR-1, BUG-NOTA-VOID, BUG-DT-VOID
- **5 enhancement queued**: TODO-NEW-1 sd TODO-NEW-5
- **#364 Void Pembayaran**: Konfirmasi PRODUCTION-READY end-to-end

**Sign-off**: Bapak confirm "saya tidak menemukan bug atau error di semua role/endpoint".

**Test Coverage Pasca Sambungan**: ✅ COMPREHENSIVE — semua role dijalankan, focal area #364 dan side fixes ter-validate.

---

## 🆕 Pattern: API Namespace Reservation (DEC-064, 11 Juni 2026)

**Pattern**: Saat tahu akan ada module baru terhubung via API (e.g. Finance Module),
**reserve namespace dulu** dengan skeleton endpoint yang return 501 Not Implemented.

**Benefits**:
- Frontend / external client tahu endpoint **akan ada** dan bisa develop UI/integration paralel
- Swagger UI documentation visible (dokumentasi self-explanatory)
- API versioning planning lebih awal (`/api/v1` vs `/api/v2`)
- Clear "implemented vs reserved" status

**Implementation Pattern**:
```python
from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/api/v1/finance", tags=["Finance Module API"])

def _not_yet_implemented(endpoint_name: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Endpoint '{endpoint_name}' belum diimplementasi. "
               f"Reserved untuk Phase X. Lihat Project_Memory/.../00_DESIGN.md."
    )

@router.get("/transaksi", summary="...")
def list_transaksi_for_finance(...):
    """[Full docstring dengan response schema sebagai kontrak referensi]"""
    raise _not_yet_implemented("list_transaksi_for_finance")
```

**Anti-pattern**: Jangan return 404 atau 200 placeholder — 501 jelas "ada tapi belum siap".

**Files**:
- Skeleton: `app/api/v1/finance.py` (285 lines, 10 endpoint placeholder)
- Spec: `Project_Memory/FinanceModule/00_DESIGN.md`
- Migration skeleton: `migrations_sql/017_finance_module_skeleton.sql`

---

## B-024 — B-013 STORM (Sesi 11 Juni Pagi)

### Pattern
Sesi 11 Juni 2026 (08:40-10:00) mengalami **10 B-013 truncation strike** dalam ~1.5 jam — record tertinggi sejauh ini.

### Files Affected
- `treatment_service.py` (saat #33)
- `master_produk_service.py` × 1 (saat #31)
- `master_produk_form.html` × 1 (saat #31)
- `master.py` × 3 (saat #31)
- `pasien_service.py` × 1 (saat #29A)
- `pasien.py` (schemas) × 1 (saat #29A)
- `pasien.py` (routes) × 2 (saat #29A enum fix)
- `dokter.py` × 1 (saat #29A enum fix)
- `dokter_soap_form.html` × 2 (saat #29A)
- `pasien_detail.html` × 1 (saat #29A)

### Hypothesis
B-013 lebih sering hit pada:
1. Files > 200 lines
2. Multiple Edit operations dalam quick succession (< 30 detik antar Edit)
3. Edit yang insert/replace di middle of file (push tail content past internal buffer?)

### Mitigation yang Bekerja
1. **Python heredoc + AST verify pattern** (DEC-056) — paling reliable
2. **Safepoint restoration** (`backups/safepoint_*.zip`) — fallback kalau Edit truncate
3. **File splitting** — refactor 1 large template jadi multiple partials + `{% include %}`
4. **Write tool** untuk new files (no truncation risk on creation)

### Anti-Pattern (Sebaiknya Hindari)
1. ❌ Multiple `Edit` calls in a row on same large file
2. ❌ Edit di middle of file > 300 lines
3. ❌ Edit yang menambah > 50 lines dalam 1 operation

### Recommendation untuk Sesi Berikutnya
- Untuk file > 200 lines: gunakan **Python heredoc + AST verify** SEKALIPUN Edit single line
- Untuk modifikasi service/route besar: SPLIT jadi append-at-end + helper function
- Take safepoint zip SETELAH setiap task complete

### Status
- 🔴 Bug pattern belum di-fix di Edit tool level (limitation tool)
- 🟢 Mitigation pattern proven (10/10 restored successfully sesi ini)
- 🟡 Recommendation: TODO baru untuk "DEC-066 — B-013 mitigation playbook" atau apply di 10_ai_collaboration_guide.md

---

## B-013 Update — Sesi 11 Juni Malam ZERO Strike

**Tanggal:** 11 Juni 2026 Malam

### Result
Setelah adopsi playbook (lihat DEC-066 di 11_decisions_log.md):
- **0 B-013 strikes** across 4 hours session
- 7 tasks delivered (#29B + #29C + 4 UX refinements + #50)
- ~12 file edits, all clean
- Compare: pagi 10 strikes dalam 1.5 jam

### Pattern Confirmed Working
- Python heredoc `python3 << PYEOF` dengan `ast.parse()` / Jinja verify
- Write tool untuk NEW files only
- Batch multi-step edits dalam 1 PYEOF block
- AVOID Edit tool pada file > 200 lines

### Status
- B-013 root cause tetap unfix-able dari sisi project (limitation tool)
- Mitigation pattern STABLE, adopt as standard for all future sessions
- Update di B-024 entry: "Mitigation playbook VALIDATED"

---

## Sesi 2026-06-12 Malam — B-013 Observation Update (5× strikes)

### Frequency Pattern
- **Sesi pagi (2026-06-12 pagi)**: 0 strikes
- **Sesi malam (2026-06-12 malam)**: 5 strikes

### Honest Assessment dari Claude

Bukan kekurangan memory di sisi user — file fisiknya memang ter-truncate di server side. Tiga faktor pengaruh terbesar:

#### 1. Cumulative Context (faktor TERBESAR)
Sesi panjang = banyak conversation turns + screenshot + skill files dimuat. Context "berat" → output streaming makin tidak reliable. Sesi pagi fresh; sesi malam sudah jam ke-4 → strike spike.

#### 2. File Size Growth
Selama sesi malam, target files membesar:
- `membership_service.py` 904 baris (target Edit untuk LOG-1)
- `print_service.py` 479 baris (target Edit untuk NOTA-C)
- `pemeriksaan_service.py` 654 baris
Edit di file besar = bigger output window = higher truncation risk.

#### 3. Edit Complexity
Edit sesi malam banyak nested structure (try/except + audit dict + multi-line tuple). Edit kompleks lebih rentan strike dari simple single-line replace.

#### 4. Server Load (sekunder)
Variabilitas infrastruktur Anthropic real tapi BUKAN penyebab utama.

### Mitigation untuk Sesi Berikutnya

**Pattern yang lebih robust:**
1. **Edit kecil 3-5 baris** — strike menurun drastis
2. **Bash heredoc untuk insert blok besar** — bypass streaming truncation (tidak pernah strike)
3. **Read sebelum Edit besar** — pastikan context fresh
4. **Safepoint setiap milestone** — recovery <30 detik kalau strike kena
5. **AST/Jinja verify setelah setiap Edit** — early detection

**Pattern yang berisiko TINGGI:**
1. Edit single block >40 baris di file >500 baris (sweet spot strike)
2. Multi-line nested structure (dict + try/except + tuple)
3. Sesi >3 jam tanpa break/context clear

### Recovery Track Record Sesi Ini
| Strike # | File | Lines after restore | Recovery method | Time |
|----------|------|---------------------|-----------------|------|
| 1 | `membership_service.py` | 904 | Python heredoc tail splice | ~30s |
| 2 | `pemeriksaan_service.py` | 654 | Safepoint splice | ~30s |
| 3 | `print_service.py` (truncate 1) | 475 | Safepoint splice | ~30s |
| 4 | `print_service.py` (truncate 2) | 479 | Safepoint splice | ~30s |
| 5 | `nota_a5.html` | 168 | Safepoint splice | ~20s |
| 6 | `nota_thermal.html` | 126 | Safepoint splice | ~20s |
| 7 | `membership_service.py` (truncate 2) | 908 | Python heredoc tail splice | ~30s |

Recovery rate: 100% (semua strike di-restore + AST verify + functional checks).


---

## Sesi 2026-06-12 Malam (Lanjutan) — Phase 3 Void Cascade

**Status:** 🟢 1 task selesai (DEC-068 Void Cascade Kuota Revert). Test14 PASS manual.

### B-013 Strike (1×)
- **Lokasi:** `app/services/kasir_service.py`, line 1253 — Edit tool memotong file mid-statement (`tabel_target` tanpa value) saat insert helper `_revert_kuota_per_tindakan`. Tail `force_past_day_void` (audit.log + commit + return + except + `__all__`) hilang.
- **Deteksi:** `ast.parse` → `SyntaxError: '(' was never closed` di line 1251. Konfirmasi via `tokenize` → `EOF in multi-line statement (1255,0)`. `wc -l` = 1253 (harusnya ~1288). Null bytes = 0 (kali ini truncation murni, bukan null injection).
- **Catatan penting:** Read tool sempat nunjukin versi **cached** (full content) padahal disk sudah truncate — jangan percaya Read saja, selalu verify via `wc -l` + `tail` di bash setelah edit file besar.
- **Recovery:** `head -n 1246 + heredoc` restore tail + sekalian wire `force_past_day_void`. Sisa wiring `void_transaksi` pakai Python patch script (anchor-replace `assert count==1`). AST + py_compile clean.

### Insight / Workflow Reinforcement
1. **Edit tool tetap risky di file >1200 baris** (kasir_service.py ~1250 baris). Untuk file besar: prefer bash heredoc (rewrite tail) atau Python patch script (targeted anchor-replace) daripada Edit tool.
2. **Verifikasi pasca-edit WAJIB lewat bash**, bukan Read tool — Read bisa stale/cached saat disk ter-truncate. Cek `wc -l` + `tail` + `ast.parse`/`py_compile`.
3. Python patch script dengan `assert s.count(anchor)==1` = aman: gagal-cepat kalau anchor tidak unik / sudah berubah, tidak silent-corrupt.

---

## Data Quality — Raw Data Export (cek 2026-06-12 malam, DEC-069)

Field kategori disimpan sebagai **teks bebas** (bukan enum integer). Anomali yang ditemukan saat review pipeline Data Analyst:

| Field | Anomali | Asal | Penanganan |
|-------|---------|------|------------|
| `metode_bayar` | kode angka `1/2/4` | data test awal (id_transaksi 1-7, 15-16 Apr 2026) | → UNKNOWN (cleanup DITUNDA per dr. Hansen) |
| `metode_bayar` | label `CASH` (dominan) | import historical Excel (`import_excel_historical.py:334`, ~569 faktur) | **Normalisasi → TUNAI** (DONE via SQL manual) |
| `sumber_pendaftaran` | kode angka `1` | baris legacy/test (kunjungan BATAL) | → UNKNOWN (cleanup DITUNDA) |

**Nilai kanonik live:** `metode_bayar` = TUNAI/QRIS/DEBIT/KREDIT/TRANSFER; `sumber_pendaftaran` = WALK_IN/MEMBERSHIP_ONLY.

**Penting (verified):** Tidak ada kode di `app/` yang branch pada literal `'CASH'`/`'TUNAI'` — kolom murni label display/group-by, jadi normalisasi data aman tidak merusak program.

**Outstanding (low priority):** cleanup kode angka → `UNKNOWN_LEGACY` (Section B di `seed_data/data_cleanup_metode_sumber_2026-06-12.sql`) belum dijalankan. Bisa di-filter di Data Analyst sementara.

---

## C2 RESOLVED — Rate Limiting Login (2026-06-26, DEC-070)

`/web/login` POST sekarang punya rate limit per-IP via `app/core/rate_limit.py` (in-memory, dependency-free). Hitung kegagalan saja (sukses reset), ambang 10 gagal/10 menit → cooldown 5 menit (429 ramah), **TANPA account lockout**. Tested live: attempt 11 → 429. Catatan: in-memory = per-worker; pindah Redis kalau multi-worker. API `/api/v1/auth/login` belum di-wire (bisa pakai modul sama).

---

## B-013 AKAR MASALAH DITEMUKAN (2026-06-26)

**Selama ini B-013 (truncation + null byte injection) misterius. Sekarang jelas:**
menulis file ke **`/mnt/c` (drive Windows) dari WSL/tooling menyuntik null byte / korupsi.**

**Bukti:** script `setup_self_host.sh` (step 3, Python `open(w).write()` di WSL) menulis ulang 6 template di /mnt/c → KESEMUANYA kena null byte (_app.html 87 nulls, base.html 8, 4 report 34 each). Akibatnya Tailwind content-scan tidak bisa baca class → app.css kosong utility → tampilan polos total.

**Implikasi:**
- B-013 yang berulang sepanjang proyek = gejala filesystem /mnt/c, BUKAN tool tertentu. Edit tool, Python write, dll semua rentan saat target /mnt/c.
- **Solusi permanen = migrasi proyek ke filesystem WSL-native (`~/`).** Quick-fix terus melawan filesystem.

**Mitigasi sementara:** untuk build Tailwind, scan template dari /tmp (Linux-native) via `deployment/build_tailwind.sh`. Template di-switch + dibersihkan dari sisi AI (write AI ke /mnt/c kali ini null-safe, beda dari Python WSL user).

**REKOMENDASI KUAT: jadwalkan migrasi WSL-native (DEC-071 sudah catat ini sebagai opsi).**

---

## B-013 — Eksperimen Terkontrol (2026-06-27, sesi Kasir-1)

**Tujuan:** karakterisasi akar B-013 secara empiris (bukan tebakan), menjawab
2 hipotesis dr. Hansen: (a) apakah karena Windows-drive vs WSL-native? (b) apakah null byte?

**Metode (probe reproducible):**
1. Tulis `_b013_probe.py` via bash = 601 baris, **40.849 byte**, sentinel
   `SENTINEL_AKHIR = "..."` di baris terakhir. Disk bersih (0 null byte).
2. `Read` file (prime file-tool view) → tampil lengkap.
3. `Edit` tool ubah HANYA baris 5 (menambah byte di ATAS file).
4. Cek kondisi disk via bash.

**Hasil (smoking gun):**
- Ukuran disk setelah Edit = **tetap 40.849 byte, persis sama**.
- Edit menambah byte di baris 5, tapi file TIDAK membesar → byte sejumlah
  itu **dipotong dari EKOR**: `...HARUS_U` (`TUH"` + newline hilang).
- **Null byte = 0.** Truncation murni, bukan injeksi null byte.
- `rm` di bash **DITOLAK** (`Operation not permitted`); truncate (tulis 0 byte)
  BOLEH; unlink hanya bisa via layer Cowork. = bukti dua lapisan FS berbeda.

**Kesimpulan (mengkonfirmasi diagnosa /mnt sebelumnya):**
- Akar = **jembatan sinkronisasi drive Windows (E:) ↔ mount Linux sandbox.**
  Tulisan dari tool editor yang MEMPERBESAR file tidak ter-propagate utuh;
  mount meng-cap file di ~panjang byte asli dan memotong sisanya di ekor
  (jatuh di tengah statement). Makin besar penambahan, makin panjang ekor hilang.
- BUKAN null byte (gejala sekunder yang kadang muncul), BUKAN bug Python/encoding.
- Jawaban hipotesis: (a) **YA** — lokus = Windows-drive-via-mount (sama dengan
  temuan /mnt/c, drive E: pun kena). (b) **TIDAK** — bukan null byte.

**Mitigasi operasional (dipakai untuk build Kasir-1):**
- Semua tulis file lewat **bash heredoc/python langsung ke mount** (path otoritatif
  untuk runtime), lalu verifikasi disk: `wc -c` + `tail` + `py_compile`/AST.
- Edit/Write tool aman HANYA untuk perubahan yang tidak memperbesar file / file kecil.
- Rekomendasi permanen tetap: **migrasi proyek ke filesystem WSL-native (~/)** —
  ref DEC-071, DEC-074.

---

## B-025 — __all__ Tak Konsisten Bikin `alembic` Gagal (`import *`) — FIXED (2026-06-27)

**Gejala:** Saat `alembic upgrade head` (apply migrasi `20260627_0900 kasir_closing`):
```
AttributeError: module 'app.db.models' has no attribute 'MasterMembershipBenefitDiscount'.
Did you mean: 'MasterMembershipBenefitTreatment'?
```
Migrasi gagal, tabel `kasir_closing` tidak terbuat → halaman Tutup Kasir 500
("Table 'db_sehati.kasir_closing' doesn't exist").

**Akar masalah:** `app/db/models/__init__.py` punya `__all__` dengan 2 nama class
membership yang **sudah tidak ada** di `membership.py` (kemungkinan sisa rename/hapus lama):
- `MasterMembershipBenefitDiscount` (tidak ada — yang ada `...BenefitTreatment`)
- `PasienMembershipKuotaTreatment` (tidak ada — yang ada `PasienMembershipKuota`)

`migrations/env.py` pakai `from app.db.models import *`. Python memvalidasi setiap
nama di `__all__` saat `import *`; nama yang tak terdefinisi → `AttributeError`.
**Penting:** app uvicorn normal pakai import EKSPLISIT (bukan `import *`), jadi app
tetap jalan — bug ini laten dan hanya muncul lewat `alembic` (atau `import *` lain).

**Fix:** ganti 2 nama salah di `__all__` dengan 2 class membership asli yang justru
belum di-export: `PasienMembershipHistory`, `PasienMembershipKuota`. Sekarang semua
nama `__all__` resolvable (diverifikasi via AST checker: 0 missing).

**Pelajaran / pencegahan:**
- Setelah edit `models/__init__.py`, jalankan AST consistency check: semua nama di
  `__all__` HARUS terdefinisi/ter-import di modul. (Script ada di catatan sesi.)
- Kemungkinan diperparah B-013 (truncation) saat edit `__init__.py` di sesi yang sama;
  rekonstruksi tail harus sekalian validasi `__all__` vs import.
- Catatan: `AuditLog` juga ter-import tapi tidak di `__all__` — dibiarkan (tidak
  breaking, app pakai import eksplisit). Bukan prioritas.

---

## B-026 — Live Selisih Salah 100× (data attribute Decimal) — FIXED (2026-06-27)

**Gejala (real-test Tutup Kasir dr. Hansen):** Expected TUNAI tampil 10.500.000, kasir isi
counted 10.500.000, tapi selisih live JS jadi −1.039.500.000 (≈ −1 miliar). Server pun
tolak dengan selisih raksasa.

**Akar:** template render `data-expected="{{ row.expected }}"` di mana `row.expected`
adalah `Decimal` → jadi string `"10500000.00"`. JS `parseNum` buang semua non-digit
(termasuk titik desimal) → `"1050000000"` = 1,05 miliar (100× lipat). Selisih = counted − 1,05M.

**Fix:** render integer — `data-expected="{{ row.expected|int }}"` dan
`data-total="{{ preview.total_expected|int }}"`. Diverifikasi: parseNum("10500000")=10.500.000,
selisih=0 saat cocok.

**Pelajaran:** untuk nilai uang yang dibaca JS via `data-*`, SELALU render integer
(`|int`), jangan Decimal mentah (yang bawa `.00`). Pola umum di template lain perlu dicek.

### UI/UX fixes sekalian (sesi sama)
- **Pemisah ribuan live** di semua input rupiah (modal + counted) — `data-rupiah` + JS group,
  server `_parse_rupiah` buang titik saat submit. Hilangkan kebingungan baca digit panjang.
- **Tombol Filter laporan tak terlihat:** class `bg-slate-800` TIDAK ter-compile di Tailwind
  self-host (DEC-073) — hanya class yang ke-scan template saat build yang ada. Ganti ke
  `bg-emerald-600` (sudah dipakai di tempat lain, pasti ter-compile). **Pelajaran:** hati-hati
  pakai class Tailwind baru/jarang di template baru tanpa rebuild/safelist.
- **Default tanggal laporan = hari ini** (sebelumnya kosong/dd-mm-yyyy). Sentinel `?tgl=all`
  untuk semua tanggal + indikator teks.

---

## B-027 — Pydantic model_dump() Buang kode_penyakit + UI fixes (2026-06-29)

**Gejala:** Penyakit kronis tersimpan (mis. "Hipertensi") tidak tercentang di checkbox panel,
bahkan tak muncul di "Lain-lain" — `kode_penyakit` tak sampai ke template.

**Akar:** `PasienService.get_detail()` mengembalikan `PasienDetailResponse` (Pydantic), field
`penyakit_kronis: list[PenyakitKronisResponse]`. Schema `PenyakitKronisResponse` TIDAK punya
`kode_penyakit`, jadi `model_dump()` membuang field itu meski dict sumber sudah memuatnya.

**Fix:** tambah `kode_penyakit: Optional[int] = None` ke `PenyakitKronisResponse` (app/schemas/pasien.py).
**Pelajaran:** kalau menambah kolom DB yang perlu tampil via response model_dump, WAJIB tambahkan
juga ke schema Pydantic response-nya — bukan cukup di dict.

**Catatan data lama:** baris lama `kode_penyakit=NULL` muncul sebagai "Lain-lain" (tak hilang),
tapi tak ter-map ke kode kanonik sampai `scripts/backfill_penyakit_kode.py --apply` dijalankan.

### UI fixes sekalian (sesi sama)
- **Dropdown "+ Antrian" terpotong** (pasien_search): flip-logic dulu pakai tinggi hardcoded 160px
  → salah saat menu tinggi. Fix: ukur tinggi AKTUAL (offsetHeight), flip ke sisi terluas, cap
  max-height + scroll. Tak pernah ke-clip lagi.
- **Guard konfirmasi hapus** penyakit kronis: kalau ada yang di-uncheck saat simpan, konfirmasi
  sebut persis yang akan dihilangkan (cegah hilang tak sengaja). Pre-check otomatis dari data aktif.
- **B-013 kambuh** saat Edit tool dipakai untuk JS dropdown (pasien_search.html ter-truncate) →
  ditulis ulang via bash. Workflow bash-write tetap wajib (DEC-074).

---

## B-028 — Tailwind ter-purge: class arbitrary/jarang diam-diam MATI (2026-07-01, modul Booking)

**Gejala:** halaman kalender Booking ambruk — grid 7 kolom jadi tumpukan 1 kolom vertikal; sel tanpa tinggi min;
teks ukuran salah. Tidak ada error apa pun (class-nya sekadar tak berlaku).

**Akar masalah:** `app/web/static/css/app.css` itu **build Tailwind yang sudah di-purge** (bukan Play CDN, walau
komentar di `base.html` menulis "via CDN"). Isinya hanya kelas yang terpakai di template lama. Cek nyata:
- `grep '\.grid-cols-' app.css` → **cuma `grid-cols-1/2/3`**. `grid-cols-7` TIDAK ADA (yang ada cuma varian
  responsif `md:grid-cols-7`/`lg:grid-cols-7` dari template lain).
- Nilai **kurung-siku arbitrary** (`min-h-[7.5rem]`, `text-[11px]`, `min-w-[11rem]`), `ring-inset`, `opacity-75`,
  `bg-purple-700`/`hover:bg-purple-700` → **tidak ada**.

**Fix:** komponen kalender ditulis pakai **CSS mandiri** (`<style>` di dalam template, kelas `.cal-*`, `.chip.*`) —
tak bergantung Tailwind. Untuk 2 kelas kecil yang hilang di halaman detail (`opacity-75`, purple hover) → inline
`style="..."`.

**Pelajaran (WAJIB untuk kerja template ke depan):**
1. **Jangan andaikan** sembarang kelas Tailwind tersedia. app.css statis & ter-purge — kelas baru yang belum pernah
   dipakai template lama **tidak akan ada**.
2. Sebelum pakai kelas non-standar (angka besar `grid-cols-7`, nilai `[...]`, warna langka, `ring-*`, `opacity-*`):
   `grep '\.<kelas>' app/web/static/css/app.css` untuk konfirmasi ADA.
3. Untuk komponen baru yang butuh layout khusus (grid kalender dst.), **paling aman pakai CSS mandiri** di `<style>`
   atau inline `style=""`. Warna/spacing standar (`bg-slate-*`, `text-*`, `px-*`, `grid-cols-2`) umumnya aman
   karena banyak dipakai.
4. Kalau nanti pipeline build Tailwind di-*rebuild* dari template, ingat template baru harus ikut ter-*scan* (content
   glob) supaya kelasnya masuk — kalau tidak, masalah ini berulang.

---

## B-029 — Halaman yang bangun shell-context MANUAL (bukan build_shell_context) (2026-07-02)

**Pelajaran:** sebagian besar halaman web pakai `build_shell_context()` (auto-inject `klinik_nama`,
`klinik_logo_path`, `klinik_mini_logo_path`, menu, dll). TAPI **`GET /web/dashboard`** (di `auth.py`) menyusun
context dict-nya **sendiri** — plus `login.html` (yang tak butuh topbar). Efek: saat menambah variabel branding
baru ke shell, dashboard TIDAK ikut otomatis → sempat 2× salah (dulu cuma dashboard yg tampil nama; lalu cuma
dashboard yg tampil huruf, bukan mini-logo).

**Aturan ke depan:** kalau menambah/mengubah variabel shell/topbar di `build_shell_context`, **CEK JUGA
`dashboard()` di `app/web/routes/auth.py`** (dan template `dashboard.html`) — samakan key-nya. Kandidat refactor
nanti: buat dashboard pakai `build_shell_context` juga (hati-hati: dashboard pass `user` sebagai dict, shell pakai
model — perlu sinkron dulu).

---

## B-030 — Dead-code register (sweep 2026-07-02)

Sweep otomatis: 17 metode/fungsi di `repositories/`+`services/` dengan **0 referensi** di seluruh repo
(app+tests+templates). Diperiksa satu-satu. **TIDAK dihapus buta** — mayoritas = scaffolding fitur aktif/rencana.

**KEEP (ada intent jelas / pola concurrency / fitur aktif-rencana):**
- `master_produk_repo.get_for_update` + `add_stok` — SELECT FOR UPDATE restock (anti race). Dipakai di template project.
- `pemesanan_repo.get_item_for_update` (dipakai) → `get_item_by_id` = sibling non-lock; `get_by_nomor_po` lookup PO.
- `kasir_repo.count_transaksi_for_kunjungan` — cap reopen FLOW-D.
- `master_produk_service.hitung_komisi_produk` + `master_treatment_service.hitung_komisi_treatment` — akuntansi komisi dokter (fitur riil, belum di-wire ke UI).
- `opname_repo.get_stok_sistem_produk` — stok RETAIL (opname RETAIL yg baru diaktifkan).
- `kunjungan_repo.list_antropometri_timeline` — timeline antropometri (dipakai konektor Antropometri nanti, §C).
- `auth_service.get_current_user_data` — bentuk UserResponse untuk endpoint /me.
- `export_service._redact` — helper redaksi PII (scaffolding privasi export).
- `pasien_repo.get_alergi_aktif` + `get_penyakit_kronis_aktif` — getter klinis aktif (area fitur aktif).

**REVIEW (kandidat hapus — kemungkinan leftover; tunggu konfirmasi dr. Hansen):**
- `kunjungan_repo.list_antrian_hari_ini` — tampak digantikan `kunjungan_service.lihat_antrian_hari_ini`.
- `pasien_service._create_pending_membership_history_if_needed` (private, #362D) — tampak digantikan alur create-billing.
- `opname_repo.get_by_nomor` — lookup opname by nomor (tak terpakai).
- `export_service.is_range_warning` — helper trivial (warning rentang tanggal) tak terpakai.

**Sebelumnya dihapus (DEC-084):** `pasien_repo.get_by_no_rm`.
**Prinsip:** hapus hanya REVIEW yg dikonfirmasi benar-benar ditinggalkan; KEEP tetap sampai fiturnya di-wire/dibuang eksplisit.

**Klarifikasi (2026-07-02) — kenapa `hitung_komisi_produk/treatment` "dead":**
Komisi = fitur separuh-jadi, BUKAN bug. Yang SUDAH jalan: rate komisi per produk/treatment (kolom
`komisi_dokter_tipe/value`, `komisi_perawat_*`) disimpan + diedit via master form; helper inti `_hitung_komisi_satu`
dipakai DI DALAM `hitung_komisi_produk/treatment`. Yang BELUM: konsumen-nya = endpoint payroll
`GET /api/v1/finance/komisi/staf` (agregasi komisi per periode untuk slip gaji) masih `501 Not Implemented`
(= modul Finance/A5 yang ditunda POST-PRODUCTION). Jadi 2 fungsi komisi itu = lapisan hitung yang menunggu
modul payroll dibangun. **KEEP** — akan tersambung saat payroll dibuat.

**Klarifikasi membership pending:** status "pending" = tier membership sudah dipilih tapi BELUM dibayar. Alur
AKTIF: tombol "Buat Tagihan Sekarang" → pasien masuk antrian kasir → saat lunas, membership aktif (ditangani
`kasir_service`, lihat referensi `nama_tier_pending`/`id_mship_pending`). Helper mati
`_create_pending_membership_history_if_needed` = jalur pembuatan pending versi lama yg digantikan alur billing ini.
Perlu cross-check UI (Chrome DevTools) di kemudian hari untuk pastikan transisi pending→aktif→expired lengkap.

### B-031 — BaseHTTPMiddleware membuang Set-Cookie CSRF (2026-07-03)
Menambah security headers via `@app.middleware("http")` (BaseHTTPMiddleware) MEMBUANG Set-Cookie yang
di-inject `CSRFMiddleware` (pure ASGI, set cookie di wrapper `send`) → semua form kena "Token Keamanan
Tidak Valid / Sesi CSRF tidak ditemukan". **Fix:** tulis middleware header sebagai PURE ASGI (append ke
`http.response.start` headers saja), JANGAN BaseHTTPMiddleware. Lihat DEC-093 + app/main.py SecurityHeadersMiddleware.
ATURAN: jangan pakai `@app.middleware("http")` di app ini — pola CSRF/cookie pure-ASGI tak kompatibel dengannya.

### B-013 (kambuh 2026-07-04) — truncation saat Edit `_app.html`
Edit tool memotong ekor file (`window.appConfirm`/`</body>`/`</html>` hilang) saat menambah nav-drawer.
Terdeteksi via anomali jumlah baris (221→217, seharusnya bertambah). Dipulihkan lewat splice bash
(python `replace`) + verifikasi 0 null-byte, marker ekor utuh, Jinja parse OK. **Pelajaran ulang:** untuk
template besar, sunting via bash/python `replace` + verifikasi baris/marker/null-byte, JANGAN andalkan Edit saja.

## B-ANTRO-1 — [RESOLVED 2026-07-06] Label "Diproses" vs "Menunggu approval" (SOAP + detail)
Ditemukan 2026-07-06 (dr. Hansen). Saat laporan modul MASIH diproses AI (status modul `processed`,
label modul "Diproses"), kolom-3 SOAP menampilkan "⏳ Draft menunggu approval" — SEHARUSNYA "sedang diproses".
Penyebab: di AntroReportService.laporan_by_rm, bucket `pending` menggabung status `waiting_approval` + `processed`;
template (dokter_soap_form.html kolom-3 & pasien_detail.html hint) melabeli semua `pending` = "menunggu approval".
JEBAKAN NAMA: status modul `processed` = SEDANG diproses (bukan "sudah diproses").
FIX (belum dikerjakan, atas permintaan user "catat dulu"):
 - laporan_by_rm: pisah bucket -> `processing` = [status=="processed"], `pending` = [status=="waiting_approval"].
 - dokter_soap_form.html kolom-3: tampilkan `processing` sbg "⏳ Sedang diproses" (TANPA link approve),
   `pending` sbg "Draft menunggu approval" (DENGAN link "Tinjau & approve ↗").
 - pasien_detail.html: hint pending juga pisahkan (opsional: "n sedang diproses" vs "n menunggu approval").
 - Update test_antro_laporan_display.py: assert a3 (processed) masuk `processing`, a2 (waiting_approval) masuk `pending`.
Dampak: kosmetik/label saja; tak ada data rusak. Alur fungsional benar.

RESOLVED 2026-07-06: laporan_by_rm pisah bucket processing (status=processed) vs pending (waiting_approval).
SOAP kolom-3: blok "⏳ Sedang diproses" (abu, tanpa link approve) TERPISAH dari "Draft menunggu approval"
(kuning, dgn link approve). Detail: hint "sedang diproses…" terpisah dari "menunggu persetujuan". Test
tests/test_antro_laporan_display.py diperbarui (a3 processed->processing, a2 waiting_approval->pending).

## B-ANTRO-3 — [RESOLVED 2026-07-06] Tombol "+Buat Laporan Antropometri" membuka laporan LAMA, bukan assessment baru
Ditemukan 2026-07-06 (dr. Hansen). Pasien yang sudah punya laporan → klik "Buat Laporan" (dokter/perawat)
langsung diarahkan ke VIEW laporan sebelumnya, bukan halaman assessment baru.
PENYEBAB (terkonfirmasi): modul /intake dedup by idempotency_key (web/connector.py find_idempotent →
balas url=/review/{existing}). Sehati kirim idempotency_key = f"sehati-antro-{encounter_id}" dengan
encounter_id = id_pasien (antro=None), jadi SAMA tiap klik untuk pasien yg sama.
FIX (belum): buat idempotency_key UNIK per klik, mis. f"sehati-antro-{id_pasien}-{unix_ts}" di
app/services/antro_connector_core.build_intake_payload / pemanggilan di pasien_antro_buat. (Retry-safety
tetap terjaga untuk 1 klik; klik baru = assessment baru.) Alternatif: modul balas url=/intake/{id} bukan
/review saat idempoten, tapi lebih tepat perbaiki di Sehati (aksi "Buat" memang niat assessment BARU).

KLARIFIKASI (dr. Hansen): tombol "Buka laporan" SUDAH benar; yang bermasalah tombol "+Buat Laporan
Antropometri" — ia membuka /review laporan lama, bukan form assessment baru.
RESOLVED 2026-07-06: idempotency_key kini UNIK per klik. antro_report_service.build_payload +param
idempotency_key; route pasien_antro_buat generate f"sehati-antro-{id_pasien}-{int(time.time())}". Modul:
intake baru balas url=/intake/{id} (form), hit idempoten balas /review — dgn key unik, tiap klik = intake
BARU. Resolusi detik = klik-ganda dlm 1 detik tetap idempoten (aman). Verified: key unik diteruskan ke
request_meta. Uji manual: klik +Buat -> form modul kosong/prefill identitas (BUKAN laporan lama).
+ (2026-07-06) Tombol +Buat kini target="_blank" (buka TAB BARU) di pasien_detail & dokter_soap_form -> halaman detail/SOAP tetap terjaga.

## B-ANTRO-4 — [RESOLVED 2026-07-06] Laporan PERAWAT & DOKTER (layar): path filesystem bocor + audit log
Ditemukan 2026-07-06 (dr. Hansen). KOREKSI lokasi: BUKAN di layar/laporan PASIEN, tapi di tampilan LAPORAN
PERAWAT & DOKTER (on-screen) di modul ai-antropometri. Audit log tampil di sana (dinilai kurang pas) dan
memuat path absolut "mnt/e/..." untuk file PDF. CATATAN: PDF hasil cetak BERSIH — audit log TIDAK ada di PDF,
hanya di tampilan layar. FIX (belum): jangan tampilkan path absolut di layar (tampilkan nama file saja /
sembunyikan); tinjau apakah audit log perlu tampil di laporan perawat/dokter (mungkin pindah ke area
admin/owner). File modul: render/html.py (render_doctor_html / render_review_html / _audit_field) +
web/app.py (review_html). PDF (render/pdf.py) sudah benar — jadikan acuan.

RESOLVED 2026-07-06: (1) render/html.py _short_detail() -> path filesystem di detail audit ditampilkan
NAMA FILE saja (retroaktif utk laporan lama). (2) Audit dibungkus <details> "Riwayat perubahan (audit)"
default tertutup di layar review dokter/perawat. (3) review/service.py export() simpan detail={"pdf_file":
basename} (bukan pdf_path absolut). PDF (render_patient_html) tak terpengaruh, tetap bersih. Test:
tests/test_review_audit_path.py (3, lulus). Uji manual: restart modul -> buka laporan dokter/perawat ->
audit terlipat, path = nama file saja.

## B-ANTRO-5 — [RESOLVED 2026-07-06] Opsi Reject terminal untuk laporan belum di-approve
Ditemukan 2026-07-06. Saat laporan belum diapprove, dokter hanya bisa Approve; tak ada "Reject" (atau
"Reject & Edit") bila laporan dinilai tidak sesuai. FIX (belum): tambah aksi reject di alur review modul.
Cek dulu apakah ReviewService (modul review.py) sudah punya state/rejected + edit — bila ada, cukup ekspos
di UI review; bila belum, tambah state rejected + form edit/koreksi. Modul: review.py + web/app.py + render.

RESOLVED 2026-07-06 (keputusan dr. Hansen: Reject TERMINAL, bukan kirim-ulang; Edit sudah ada -> dipertahankan
apa adanya). Modul: state.py +Status.rejected (terminal; transisi dari doctor_review_pending & doctor_edited);
review/service.reject(actor,reason); models.ReviewSession +reject_reason; jobs.display_status -> "rejected"
(SEBELUM approved/pending) + STATUS_LABEL "Ditolak"; controllers.reject; app.py POST /review/{id}/reject;
pages.review_actions +tombol "Tolak (reject)" merah + input alasan + confirm. Sehati: laporan rejected TIDAK
masuk bucket approved/pending/processing -> otomatis hilang dari tampilan (sesuai maksud). Edit tetap: viable
utk koreksi teks kecil (pilih field + isi nilai; angka read-only + cek guardrail). Test: tests/test_reject.py
(5) + verifikasi sandbox state/display_status. Uji manual: buka review draft -> Tolak -> status Ditolak,
tak muncul di Sehati.
