# Work Plan — 8 Minggu Menuju MVP Production

> Disusun oleh: Claude (lead programmer)
> Setelah review: skema DB, dokumentasi alur klinik, usulan GPT, dan kode `main_api.py` (1.892 baris)
> Strategi: **Strangler Pattern** (refactor bertahap, kode lama tetap jalan sampai diganti)

---

## Asumsi awal

- **Mulai:** Senin, 4 Mei 2026 (minggu depan setelah dokter approve plan ini)
- **Selesai MVP usable:** Sabtu, 27 Juni 2026 (8 minggu)
- **Dokter punya waktu rata-rata 1-2 jam/hari** untuk testing & feedback
- **Database `db_sehati` sudah ada di server klinik** — tidak akan saya recreate, hanya migrate (alter)
- **Saya** bekerja sebagai full-time programmer untuk project ini

Kalau salah satu asumsi berubah, timeline harus disesuaikan — kasih tahu saya secepatnya.

---

## Format kerja per minggu

Tiap minggu punya:
- **Goal:** Apa yang harus jalan akhir minggu
- **Deliverable:** File/fitur yang dihasilkan
- **Dokter punya tugas:** Apa yang dokter harus siapkan/test/jawab
- **Demo Sabtu:** Saya tunjukkan progress, dokter coba di laptop sendiri, kasih feedback

Kalau ada minggu deliverable tidak tercapai — kita stop, evaluasi, geser jadwal. Tidak boleh tumpuk-tumpuk hutang ke minggu berikut.

---

## 🗓️ MINGGU 1 (4-10 Mei) — Fondasi

### Goal
Project structure siap, database konsisten, dependency terinstall, dokter bisa run server di laptop dokter sendiri.

### Yang saya kerjakan
1. **Setup project struktur folder** sesuai `02_STRUKTUR_PROGRAM.md`
2. **Inisiasi Git repository** (lokal dulu, GitHub/GitLab di minggu 8)
3. **Install dependency** via `uv` (Python venv + libraries)
4. **Buat file `.env.example`** untuk semua secret config
5. **DB Migration #1 — perbaikan kritis** (lihat `01_ANALISA_DATABASE.md`):
   - Add missing FKs
   - Add `id_treatment` di `pasien_rencana_treatment`, `id_produk` di `pasien_resep_iterasi`
   - Ubah tipe data kolom uang di `transaksi_kasir` jadi DECIMAL
   - Add tabel `master_membership`
   - Add tabel `audit_log`
   - Add index untuk query laporan
6. **DB Migration #2 — security fix:**
   - Hash semua password di `master_staf` (bcrypt)
   - Hash semua PIN di `master_staf`
   - Script bantu `tools/migrate_passwords.py`
7. **Setup Alembic** untuk migrasi versioned ke depannya
8. **README.md untuk developer** (cara run, cara test, cara migrate)

### Deliverable
- Folder project siap (kosong tapi terstruktur)
- File `pyproject.toml` + `uv.lock`
- File `migrations/sql/001_kritis_fix.sql` (untuk dijalankan manual sebelum app start)
- File `migrations/sql/002_hash_passwords.sql` + `tools/migrate_passwords.py`
- README setup
- Server FastAPI bisa start (pun tanpa endpoint)

### Dokter punya tugas
- Backup database `db_sehati` SEBELUM migrasi dijalankan (saya kirim panduan).
- Jawab pertanyaan kritis dari `01_ANALISA_DATABASE.md` (poin Q1-Q7) dan `04_REVIEW_KODE_SAAT_INI.md` (Q11-Q15) — minimal yang berkaitan dengan inventory & membership.
- Tentukan diskon awal: REGULAR 0%, VIP %, VVIP %.
- Daftar treatment yang `butuh_otorisasi=1` (mau di-seed minggu 2).

### Demo Sabtu (10 Mei)
Saya tunjukkan: folder project terstruktur, server FastAPI start, dokter login ke DB sehati di laptop dokter dan lihat tabel baru sudah ada.

---

## 🗓️ MINGGU 2 (11-17 Mei) — Models, Repositories, Auth

### Goal
Layer data sudah lengkap. Login/logout sudah pakai JWT yang aman. Dokter bisa login via Swagger UI dan dapat token.

### Yang saya kerjakan
1. **SQLAlchemy models** untuk SEMUA 21 tabel + tabel baru (`master_membership`, `audit_log`).
   - 1 file per domain di `app/db/models/`
   - Definisi relationship lengkap (back_populates)
2. **Repository layer** — CRUD + query custom untuk tiap tabel. Belum ada business logic.
3. **Pydantic schemas** untuk input/output (Create, Update, Read variants).
4. **Auth module:**
   - `app/services/auth_service.py` — login dengan bcrypt, generate JWT
   - `app/core/security.py` — encode/decode JWT, dependency `get_current_user`
   - `app/core/deps.py` — dependency `role_required(["FO","Dokter",...])`
   - `app/api/v1/auth.py` — endpoint `/login`, `/logout`, `/me`
5. **Audit service skeleton** — siap dipakai di minggu 3+ untuk log semua aksi sensitif.
6. **Pertahankan logika anchor shift** dokter — pindahkan ke `auth_service.login()`.
7. **Unit test pertama** — test login success, login fail, token decode, role check.

### Deliverable
- `app/db/models/*.py` — 9 file models lengkap
- `app/repositories/*.py` — 9 file repos lengkap
- `app/schemas/*.py` — 9 file Pydantic
- `app/services/auth_service.py` lengkap
- `app/api/v1/auth.py` — login/logout/me endpoint
- 5+ unit test pass
- Swagger UI di `/docs` bisa coba login dan dapat token

### Dokter punya tugas
- Setelah migrate password, login pakai password lama dari Swagger UI — pastikan jalan.
- Test edge case: salah password, akun non-active, token expired.
- Kasih daftar role mapping ulang kalau ada role yang berubah (`Owner`, `Dokter`, `Perawat`, `Apoteker`, `Kasir`, `FO`, `Admin`, `Superadmin`).

### Demo Sabtu (17 Mei)
Login via Swagger → dapat token → pakai token untuk request `/me` → return data staf. Logout → token tidak bisa dipakai lagi (di blacklist atau cek `is_logged_in`).

---

## 🗓️ MINGGU 3 (18-24 Mei) — Modul FO + Pasien

### Goal
Semua endpoint FO dan management pasien sudah pindah ke service layer. JWT-protected. Logika dokter dipertahankan.

### Yang saya kerjakan
1. **`pasien_service.py`:**
   - `register_pasien_baru(payload)` — pertahankan logika dokter (insert pasien + alergi + penyakit + kunjungan + antropometri dalam 1 transaksi).
   - `cari_pasien(keyword)` — search by nama/RM/HP.
   - `riwayat_pasien(id)` — agregat treatment + produk.
   - `get_header_pasien(id)` — pertahankan kalkulasi BMI + Pollock.
   - `get_summary_pasien(id)` — 4 cardbox.
2. **`booking_service.py`:**
   - CRUD booking.
   - `check_in(id_booking)` — convert booking → kunjungan.
   - `cancel_booking(id, alasan)` — hanya FO yang bisa.
3. **`kunjungan_service.py`:**
   - `kunjungan_lama(id_pasien, ...)` — pertahankan logika dokter.
   - `dapatkan_antrian_hari_ini()` — pertahankan logika dokter.
   - `lihat_antrian_hari_ini()` — list semua antrian.
   - `ubah_status_antrian(id, status)`.
4. **`alergi_service.py` & `penyakit_kronis_service.py`:**
   - Add, soft delete, list.
   - RBAC: tambah boleh FO/Perawat/Dokter, hapus hanya Dokter (sesuai dok dokter).
5. **`audit_service.py` integrasi** — semua aksi mutating ditulis ke `audit_log`.
6. **Endpoint FO:**
   - `POST /api/v1/fo/pasien` (register baru)
   - `POST /api/v1/fo/kunjungan` (kunjungan lama)
   - `GET /api/v1/fo/antrian` (lihat antrian hari ini)
   - `PATCH /api/v1/fo/kunjungan/{id}/status`
   - `GET /api/v1/pasien/search?q=...`
   - `GET /api/v1/pasien/{id}` (detail + riwayat)
7. **Integration test:**
   - Test alur: login FO → daftar pasien baru → cari pasien → input kunjungan lama → batal kunjungan.

### Deliverable
- 5 service modules lengkap
- 12+ endpoint API jalan dengan JWT + RBAC
- 10+ integration test pass
- Endpoint LAMA di `main_api.py` masih jalan (belum dibuang)

### Dokter punya tugas
- Test alur FO lengkap di Swagger atau Insomnia.
- Kasih feedback edge case yang biasa terjadi di klinik (misal: pasien lupa bawa KTP, no telepon kosong, antropometri di-skip, dll).

### Demo Sabtu (24 Mei)
Saya simulasikan alur FO real: pasien baru datang → daftar lengkap → pulang. Pasien lama datang → cari → check-in. Pasien batal → FO ubah status. Semua via API + audit log tercatat.

---

## 🗓️ MINGGU 4 (25-31 Mei) — Modul Dokter + Perawat

### Goal
Dokter bisa input SOAP + treatment plan + resep. Perawat bisa start/end treatment. Stok terpotong otomatis. Upsell dengan PIN otorisasi jalan.

### Yang saya kerjakan
1. **`pemeriksaan_service.py`:**
   - `submit_input_medis(payload)` — pertahankan logika dokter complex (SOAP + tindakan single/series + resep).
   - Update status kunjungan otomatis (ANTRI_TREATMENT / ANTRI_BAYAR / ANTRI_OBAT).
2. **`treatment_service.py`:**
   - `create_series(pasien_id, plan)` — generate `pasien_rencana_treatment` rows.
   - `start_treatment(id_kunjungan_tindakan, id_staf)` — pertahankan logika.
   - `end_treatment(id_kunjungan_tindakan)` — **versi yang ada potong stok BHP** (yang line 1470, bukan line 1347).
   - Smart trigger: cek sisa tindakan, lempar ke ANTRI_BAYAR otomatis.
3. **`upsell_service.py`:**
   - `submit_upsell(...)` — pertahankan logika dengan PIN otorisasi.
4. **`antropometri_service.py`:**
   - Insert/update dengan kalkulasi BMI + Pollock.
5. **`inventory_service.py` (skeleton untuk minggu ini):**
   - `potong_stok_bahan(id_bahan, qty, jenis_mutasi, referensi, id_staf)` — reusable, dipakai oleh `end_treatment`.
   - `cek_stok_sebelum_potong()` — return warning kalau bakal minus.
6. **Endpoint Dokter & Perawat:**
   - `GET /api/v1/dokter/pasien/{id}/header`
   - `GET /api/v1/dokter/pasien/{id}/summary`
   - `POST /api/v1/dokter/input-medis`
   - `POST /api/v1/dokter/alergi`
   - `DELETE /api/v1/dokter/alergi/{id}`
   - `POST /api/v1/dokter/antropometri`
   - `GET /api/v1/ruang-tindakan/antrian`
   - `GET /api/v1/ruang-tindakan/kunjungan/{id}/detail`
   - `POST /api/v1/ruang-tindakan/{id}/start`
   - `POST /api/v1/ruang-tindakan/{id}/end`
   - `POST /api/v1/ruang-tindakan/upsell`

### Deliverable
- 5 service modules
- 12+ endpoint
- Test alur end-to-end: dokter input SOAP → tindakan single → perawat start → end → stok terpotong → kasir bisa lihat tagihan.

### Dokter punya tugas
- Test SOAP form dengan kasus rumit: pasien dengan series 5 sesi, ada 2 tindakan single hari ini, 3 produk di resep.
- Test upsell perawat: produk biasa (boleh) vs treatment butuh otorisasi (harus PIN).
- Verifikasi auto-potong stok sesuai harapan.

### Demo Sabtu (31 Mei)
Simulasi 1 hari klinik mini: 3 pasien dengan kombinasi treatment + produk. Lihat stok berkurang, audit log lengkap, status pasien bergerak FO → dokter → perawat → kasir.

---

## 🗓️ MINGGU 5 (1-7 Juni) — Modul Kasir + Apotek

### Goal
Pasien bisa dibayar (split payment), struk bisa dicetak, apotek serah obat dengan auto-potong stok, suggested order bisa dipakai apoteker.

### Yang saya kerjakan
1. **`kasir_service.py`:**
   - `get_tagihan(nomor_antrean)` — pertahankan bulletproof check sudah lunas + fix `harga_satuan=0` issue (insert dengan harga real).
   - `bayar(payload)` — split payment. Update status kunjungan ke AMBIL_PRODUK / ANTRI_OBAT.
   - `void_item(id_resep, manager_credentials)` — pertahankan logika.
   - `rekap_shift(id_staf)` — clean up duplicate return statement bug, pertahankan logika.
2. **`membership_service.py`:**
   - `get_diskon(tier)` baca dari `master_membership` (bukan hardcode).
   - `cek_eligibilitas_member(id_pasien)` — untuk validasi.
3. **`apotek_service.py`:**
   - `get_antrian()` — pertahankan logika.
   - `get_detail_resep(id_kunjungan)` — pertahankan + fix asumsi id_produk=id_bahan (pakai mapping eksplisit).
   - `serahkan_obat(id_kunjungan, id_apoteker)` — auto potong stok + history log. Set kunjungan COMPLETED.
   - `write_off(id_bahan, qty, jenis, alasan)` — pertahankan logika.
   - `suggested_order()` — pertahankan logika AMC + UoM.
4. **`shift_kasir` table & service** (poin #10 di analisa DB):
   - Tabel baru: `shift_kasir(id, id_staf, mulai, selesai, kas_awal, kas_akhir, total_omzet)`.
   - Endpoint `POST /api/v1/kasir/shift/buka` & `POST /api/v1/kasir/shift/tutup`.
5. **Generate struk PDF** sederhana — dipakai untuk reprint nanti.
6. **Endpoint:**
   - `GET /api/v1/kasir/antrian-bayar`
   - `GET /api/v1/kasir/tagihan/{nomor_antrean}`
   - `POST /api/v1/kasir/bayar`
   - `POST /api/v1/kasir/void-item`
   - `GET /api/v1/kasir/rekap-shift`
   - `POST /api/v1/kasir/shift/buka` & `tutup`
   - `GET /api/v1/apotek/antrian`
   - `GET /api/v1/apotek/kunjungan/{id}/detail`
   - `POST /api/v1/apotek/serahkan-obat`
   - `POST /api/v1/apotek/write-off`
   - `GET /api/v1/apotek/suggested-order`

### Deliverable
- 4 service modules + 1 PDF generator
- 11+ endpoint
- Test alur lengkap dari registrasi sampai serah obat.

### Dokter punya tugas
- Verifikasi diskon membership setelah pakai `master_membership` — angkanya benar.
- Test split payment: 2x metode (tunai 50k + QRIS 30k untuk total 80k).
- Test void item dengan password manager sembarangan vs benar.
- Test write-off — apakah audit log sesuai harapan.

### Demo Sabtu (7 Juni)
Simulasi 1 hari penuh: 5 pasien dengan kombinasi pembayaran, 1 void item, 1 kunjungan tanpa resep (langsung dari kasir ke pulang). Tutup shift kasir, lihat rekap.

---

## 🗓️ MINGGU 6 (8-14 Juni) — Modul Admin + Master + Owner Dashboard

### Goal
Admin bisa CRUD master (produk, treatment, staf, membership). Owner punya dashboard ringkas. Iterasi resep berfungsi (untuk pasien beli produk tanpa konsul).

### Yang saya kerjakan
1. **`master_service.py` (umbrella for all CRUD master):**
   - `master_produk` CRUD
   - `master_treatment` + `treatment_komponen` CRUD
   - `master_staf` CRUD (admin/superadmin only)
   - `master_membership` CRUD
   - `inventory_stok` CRUD (apoteker)
2. **`iterasi_service.py`:**
   - `create_iterasi(id_pasien, id_produk, kuota, dokter)`.
   - `ambil_iterasi(id_pasien, id_produk)` — cek kuota, decrement.
   - Endpoint untuk FO: pasien daftar untuk ambil iterasi tanpa konsultasi → langsung ANTRI_BAYAR.
3. **`booking_service` lanjutan:**
   - Booking via API (untuk persiapan kiosk Phase 2).
   - Reschedule.
4. **`laporan_service.py`:**
   - Laporan harian: omzet kotor/diskon/netto, jumlah pasien, jumlah tindakan per kategori.
   - Laporan bulanan: trend, top treatment, top produk.
   - Laporan stok: minimum, expired (placeholder, expiry tracking belum di skema).
   - Laporan staff: per dokter (kunjungan), per perawat (treatment selesai), per kasir (omzet shift).
5. **Endpoint:**
   - `/api/v1/master/produk`, `treatment`, `staf`, `membership`, `bahan` (CRUD)
   - `/api/v1/iterasi` CRUD
   - `/api/v1/laporan/harian`, `/bulanan`, `/staff`
   - `/api/v1/owner/dashboard` (summary)

### Deliverable
- 3 service modules (master, iterasi, laporan)
- 20+ endpoint
- All endpoint tested

### Dokter punya tugas
- Tambah 5-10 produk dummy via admin endpoint. Hapus 1, edit 1.
- Setup membership tier dengan diskon final.
- Test iterasi: dokter assign pasien iterasi 3 obat, FO daftar pasien untuk ambil → kasir bayar → apotek serah → kuota turun.

### Demo Sabtu (14 Juni)
Owner dashboard lihat omzet 7 hari, top 5 treatment, top 5 produk, perlu order 5 bahan, 2 staff aktif sekarang.

---

## 🗓️ MINGGU 7 (15-21 Juni) — Frontend (HTMX + Jinja + Tailwind)

### Goal
Setiap role punya halaman web yang bisa dipakai. Login → home role → fungsionalitas inti.

### Yang saya kerjakan
1. **Setup Tailwind CSS** + base template + komponen reusable (table, form, modal, toast).
2. **Halaman per role:**
   - **Login page** — form sederhana, post ke `/login` simpan JWT di httpOnly cookie.
   - **FO home:** dashboard antrian hari ini + tombol "Daftar Pasien Baru" + search bar.
   - **FO form pasien baru** — multi-step (biodata → alergi → penyakit kronis → antropometri opsional).
   - **FO form kunjungan lama** — pilih pasien → input keluhan → set status antrian.
   - **Dokter home:** list pasien antri konsultasi + 4-cardbox summary saat klik.
   - **Dokter form SOAP** — anamnesa, PF, diagnosa + keranjang tindakan (single/series toggle) + keranjang resep.
   - **Perawat home (ruang tindakan):** list pasien ANTRI_TREATMENT + tombol start/end.
   - **Perawat form upsell** — pilih item, kalau perlu otorisasi muncul popup PIN dokter.
   - **Apoteker home:** antrian obat + tombol serahkan + tab write-off + tab suggested order.
   - **Kasir home:** antrian bayar + form pembayaran (split) + tombol void + rekap shift.
   - **Owner dashboard:** chart sederhana omzet harian + summary card.
   - **Admin master CRUD** — table + form add/edit untuk semua master.
3. **HTMX patterns:**
   - Auto-refresh antrian setiap 5 detik (hx-trigger="every 5s").
   - Modal pop-up untuk form tanpa pindah halaman.
   - Toast notification (sukses/error) di pojok kanan atas.
   - Inline edit untuk field-field tertentu.

### Deliverable
- ~30 file template Jinja2
- 1 file CSS Tailwind compiled
- Static asset (favicon, logo placeholder)
- Web UI bisa dipakai di laptop dan tablet/iPad (responsive)

### Dokter punya tugas
- **Ini minggu paling penting untuk dokter test UI/UX.**
- Coba semua role: login as FO, sebagai Dokter, sebagai Perawat, dst.
- Catat semua bagian yang membingungkan — saya benerin di minggu 8.
- Coba di iPad (untuk perawat di ruang tindakan) — apakah font cukup besar, button cukup mudah ditekan.
- Bandingkan flow vs cara klinik beroperasi sekarang.

### Demo Sabtu (21 Juni)
Saya pinjam laptop dokter, install demo. Dokter coba sebagai semua role selama 2 jam. Saya catat 30+ feedback UX untuk minggu 8.

---

## 🗓️ MINGGU 8 (22-27 Juni) — Polish, Testing Real, Deployment

### Goal
Bug minggu 7 fixed. Backup harian aktif. Klinik dokter Hansen pakai sistem ini di hari real (paralel dengan sistem lama untuk safety).

### Yang saya kerjakan
1. **Fix semua feedback UX** dari minggu 7.
2. **Performance check:**
   - Query optimization (slow query log).
   - Index tambahan kalau perlu.
   - Connection pool tuning.
3. **Backup automation:**
   - Cron `mysqldump` harian → simpan ke folder backup + (opsional) upload ke cloud.
   - Test restore di server staging.
4. **Production deployment:**
   - Pakai Docker compose: nginx (reverse proxy + HTTPS) + FastAPI (gunicorn workers) + MySQL.
   - SSL cert via Let's Encrypt (kalau cloud) atau self-signed (kalau LAN).
   - Setup `.env` production dengan secret kuat.
5. **Dokumentasi user:**
   - Manual user pendek per role (PDF/print) — 2-3 halaman per role.
   - Video tutorial pendek (opsional, kalau ada waktu).
6. **Soft launch:**
   - Hari Senin (22 Juni) staf training 1 jam.
   - Hari Selasa-Kamis (23-25 Juni) **paralel run** — staf input data ke sistem baru DAN sistem lama.
   - Hari Jumat-Sabtu (26-27 Juni) **switch** ke sistem baru. Sistem lama jadi backup.
7. **Hypercare Sabtu siang-malam:** saya standby remote, support kalau ada bug saat klinik berjalan.

### Deliverable
- Sistem production-ready, jalan di server klinik
- Backup harian otomatis
- Dokumen manual user
- Sistem dipakai real di klinik

### Dokter punya tugas
- Brief staf tentang sistem baru.
- Pastikan koneksi internet/LAN klinik stabil.
- Pertama-tama dokter pakai sendiri seharian sebelum staf, untuk sanity check.

### Demo final Sabtu (27 Juni)
Sistem berjalan satu hari penuh di klinik. Tutup shift kasir akhir hari, lihat rekap, dokter happy.

---

## Backlog (di luar 8 minggu — Phase 2 dan seterusnya)

Saya catat di sini supaya tidak hilang, tapi **tidak akan dikerjakan dalam 2 bulan ini**:

| Fitur | Phase | Estimasi |
|-------|-------|----------|
| Modul `kunjungan_foto` (upload before/after) | 2 | 1 minggu |
| Booking online (web pasien) | 2 | 2 minggu |
| Kiosk registrasi mandiri | 2 | 1 minggu |
| Delivery products to doorstep | 2 | 1 minggu |
| Skin analysis (Gemini AI) | 3 | 2 minggu |
| USG kulit AI interpretation | 3 | 2 minggu |
| SOAP smart assist (Gemini) | 3 | 1 minggu |
| Chat AI member dengan context | 3 | 3 minggu |
| Mobile app native (React Native/Flutter) | 4 | 6 minggu |
| Multi-cabang (multi-tenant) | 5 | TBD |

---

## Risiko & mitigasi

| Risiko | Mitigasi |
|--------|----------|
| Dokter terlalu sibuk untuk test mingguan | Demo Sabtu minimum 2 jam reserved. Kalau skip 2x, timeline geser 1 minggu. |
| Database production rusak saat migrasi | Backup wajib sebelum tiap migrasi. Test migrate di copy DB dulu. |
| Staf nolak pakai sistem baru | Training 1 jam + paralel run 3 hari. Sistem lama jadi backup. |
| Bug fatal saat klinik berjalan | Saya standby di hari soft launch. Sistem lama tetap available untuk fallback. |
| Timeline meleset karena fitur tambahan | Kontrol scope ketat: "ini di backlog Phase 2 atau memang harus minggu ini?" |
| Internet klinik tidak stabil | Pakai deployment LAN-only sebagai fallback. Sistem cloud bisa belakangan. |

---

## Komitmen saya

- **Setiap Senin pagi:** Saya kasih ringkasan plan minggu itu (5-10 menit baca).
- **Setiap Sabtu siang:** Demo + dokter test + log feedback.
- **Real-time:** Kalau ada bug kritis di production, saya respond <2 jam.
- **Transparan:** Kalau saya stuck atau melenceng dari plan, saya bilang minggu yang sama, bukan tutup-tutup.

## Komitmen yang saya minta dari dokter

- **Min. 1 jam/hari weekday** untuk review/test (cukup di malam hari).
- **2-3 jam Sabtu** untuk demo & feedback.
- **Jawaban cepat (<24 jam)** untuk pertanyaan blocking.
- **Keputusan business clear** — kalau ragu, kasih tahu saya, jangan suruh saya tebak.

---

## Action item untuk minggu depan

Sebelum kita mulai minggu 1:

1. ✅ Dokter baca semua 4 dokumen (`00_README.md`, `01_ANALISA_DATABASE.md`, `02_STRUKTUR_PROGRAM.md`, `03_WORK_PLAN.md`, `04_REVIEW_KODE_SAAT_INI.md`).
2. ⏳ Dokter approve atau revisi tech stack di `02_STRUKTUR_PROGRAM.md`.
3. ⏳ Dokter jawab minimal pertanyaan kritis (Q1-Q7 di analisa DB, Q11-Q15 di review kode).
4. ⏳ Dokter siapkan akses ke server klinik (SSH atau remote desktop) untuk minggu 8.
5. ⏳ Backup `db_sehati` sebelum minggu 1 dimulai.

Kalau semua OK, **Senin 4 Mei 2026 kita mulai minggu 1**. 🚀
