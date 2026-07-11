# AUDIT SEHATI eMR-POS — 2026-06-29 (read-only, tanpa perubahan kode)

Audit menyeluruh 3 dimensi (keamanan, integritas data, hygiene/konsistensi) via 3 agen paralel.
Disusun bersama dr. Hansen. **Tidak ada file aplikasi yang diubah.** Ini daftar temuan + prioritas.

## Ringkasan eksekutif
Postur Sehati **solid untuk MVP**: model auth benar (role di-fetch dari DB tiap request, bukan
percaya klaim klien), CSRF full coverage, SQL ter-parameterisasi, password/PIN bcrypt, rate-limit
login ada, rantai migrasi linear, `__all__` bersih (B-025 tidak kambuh). **Tidak ada P0 di jalur auth.**
**Temuan terpenting (P0): transaksi VOID belum di-exclude dari omzet & laporan & export** — omzet dan
jumlah transaksi **overstated** di banyak tempat. Plus beberapa P1 di integritas data & test coverage.

Status TODO lama dikonfirmasi: **#29, #31, #33 SUDAH selesai** (sejak ~11 Juni) — roadmap-nya yang usang.

---

## 🔴 P0 — Wajib dibenahi sebelum andalkan angka uang

**P0-1. ✅ FIXED 2026-06-29 (DEC-079) — VOID tidak di-exclude dari agregasi omzet/laporan/export → omzet & count overstated.**
Akar: saat void, `status_transaksi='VOID'` tapi `waktu_bayar` TETAP terisi (`transaksi.py:69`).
Semua agregasi yang filter rentang `waktu_bayar` tanpa `status_transaksi='BAYAR'` ikut menghitung void.
Lokasi (belum exclude VOID):
- `reports_service.py` — `omzet_harian` (59-104), `omzet_bulanan` (150-197), `rekap_kasir_shift` (642-651)
- `dashboard_service.py` — KPI omzet hari ini (278-281), transaksi today (406-408), kasir stats (186-197)
- `export_service.py` — export omzet (231-238), export transaksi (435-453, bahkan tak select status), pembayaran (486-495)
- `kasir_repo.py` — `list_transaksi_shift` (255) + `aggregate_pembayaran_shift` (272) → dipakai `rekap_shift` (kasir_service.py:824)

Fix: tambah `.where(TransaksiKasir.status_transaksi == "BAYAR")` di semua titik; export tambah kolom
status + marker VOID. Idealnya bikin 1 helper bersama supaya tak terulang. **Yang sudah benar (exclude VOID):**
`rekap_harian_service`, `kasir_closing_service`, void-report, dashboard void-stats.

---

## 🟠 P1 — Tinggi (korektnitas / keandalan)

**P1-1. `rekap_shift` (rekap kasir aktif) ikut hitung VOID** — bagian dari P0-1 (kasir_repo 255/272). Sama kelasnya.

**P1-2. Rollback di tengah transaksi belum commit (membership kuota lazy-create).**
`membership_service.py:668` `db.rollback()` dipanggil di dalam blok besar `pemeriksaan_service.py` (try 234 → commit 415).
Rollback ini membuang tulisan sebelumnya (tindakan/series) lalu kode lanjut commit transaksi parsial; `except`
menelan error secara senyap. Fix: pakai `begin_nested()`/savepoint atau biarkan exception naik — jangan rollback session bersama di helper.

**P1-3. ✅ FIXED 2026-06-29 (DEC-080) — Skew timezone di Tutup Kasir.** `kasir_closing_service` set `shift_mulai = datetime.utcnow()` (UTC) lalu
dibandingkan dengan `waktu_bayar` (DB current_timestamp = WIB) → window expected bisa meleset ~7 jam.
CATATAN: ini **mengikuti pola lama** `rekap_shift` (anchor `waktu_mulai_shift` juga utcnow) — jadi isu
konvensi sistemik, bukan unik modul baru. Fix: samakan basis (pakai `datetime.now()`/WIB sesuai DEC-052).

**P1-4. Jalur uang/POS nyaris tanpa test.** Ada `tests/` (~70 test, auth+klinis tercover), tapi **tidak ada**
test untuk kasir/kasir_closing/rekap/void/pembayaran. Justru area paling berisiko (uang). Tambah integration test:
(a) bayar → rekap_shift exclude VOID, (b) preview tutup kasir vs rekap konsisten, (c) void balikkan stok+pembayaran.

**P1-5 (potensial). Finance API tanpa auth.** `app/api/v1/finance.py` ~11 endpoint tanpa dependency auth.
Sekarang semua `501 Not Implemented` (tak ada data bocor), tapi WAJIB pasang guard router SEBELUM diimplementasi.

---

## 🟡 P2 — Sedang (hardening / maintainability)

- **P2-1.** Startup guard: tolak boot di produksi kalau `jwt_secret_key` = default/`<32 char` (config.py).
- **P2-2.** Hapus file duplikat usang: `app/web/routes/master.py.bak_restored`, `app/api/v1/kunjungan.py.new`
  (tidak di-import, tapi rawan ke-edit salah).
- **P2-3.** Boilerplate guard auth (redirect login + 403 HTML) di-copy ~50 tempat → bikin dependency/helper bersama.
- **P2-4.** Math uang pakai float di sebagian agregasi report (reports_service 914-915, 1218-1219, 1065-1068) →
  pertahankan Decimal sampai serialisasi.
- **P2-5.** Bentuk respons 403 tidak konsisten (full-page vs partial vs kosong) — standarkan 2 helper.
- **P2-6.** Basis waktu void tidak konsisten: `void_at` WIB vs `resep.waktu_void` UTC (kasir_service 1118 vs 1012).

## 🟢 P3 — Rendah (kebersihan)
- `/health/db` bocorkan versi MySQL + error mentah (tanpa auth). 
- `GET /web/logout` state-changing tanpa CSRF (risiko rendah, SameSite=Lax meredam).
- Min panjang password 6 / PIN 4 — lemah (tapi bcrypt).
- Rate-limit login in-memory per-process (kurang efektif multi-worker).
- ~16 fungsi repo/service dead (mis. `pasien_repo.get_by_no_rm`, `kasir_repo.count_transaksi_for_kunjungan`,
  `master_produk_repo.get_for_update`/`add_stok` — yang terakhir cek dulu, mungkin niatnya concurrency-safe).
- File nyasar di root: `1`, `exit`, `debug_kunjungan.py`, `fix_timezone_tindakan.py`; pastikan `backups/` + `*.sql` di .gitignore.
- `AuditLog` ter-import tapi tak di `__all__` (harmless).
- Dua sistem migrasi (Alembic + migrations_sql) — kasih README "Alembic canonical".
- Roadmap TODO-queue usang: #29/#31/#33 sudah done tapi masih "pending".

---

## Yang sudah BENAR (lulus audit)
Auth (role dari DB), CSRF (33 form ber-csrf), SQL parameterized, bcrypt cost 12, rate-limit login (C2),
cookie_secure config-driven (C5 tinggal set prod), atomicity proses_bayar/void/dispense/opname, migrasi linear
(head 20260627_1200), `__all__` bersih, kode_penyakit defensif, IDOR aman (model akses klinis bukan multi-tenant).

## Rekomendasi urutan tindak lanjut
1. **P0-1 + P1-1** (exclude VOID di semua agregasi) — paling berdampak, sebelum angka uang dipercaya. Sekalian P1-4 (test).
2. **P1-2** (rollback membership) + **P1-3** (timezone tutup kasir).
3. **P2** hardening saat menuju deployment (P2-1, P2-2, P2-3).
4. **P3** kebersihan kapan saja.
