# HANDOFF PENUTUP — Sehati eMR-POS × Modul AI-Antropometri
**Tanggal:** 2026-07-06 · **Untuk:** sesi/engineer berikutnya · **Status modul antropo:** SELESAI (fungsional). Deployment = TO-DO.

---

## 1. Gambaran Project Sehati eMR-POS (ringkas)
Sistem eMR + POS untuk klinik dr. Hansen. FastAPI + SQLAlchemy 2.0 + Pydantic 2 + MySQL, Jinja2/HTMX,
uvicorn :8000. Modul yang SUDAH jadi: Pendaftaran & Rekam Medis pasien, SOAP dokter, Antrian/Booking,
Kasir + Tutup Kasir (Z-report) + Rekap Harian, Komisi dokter (ledger), Pembelian/PO + Faktur + FEFO
(stok per-lot/ED) + Retur, Master (distributor, lokasi kirim, apoteker, membership), Penyakit Kronis
(master kanonik + kosakata bersama), Audit akses rekam medis, Hardening keamanan (CSRF, JWT guard,
password policy), Nav drawer HP. Deployment Sehati: file systemd/nginx/.env.prod sudah dimaterialisasi
(B3_DEPLOYMENT_GUIDE). Backlog non-antropo: P-L6c (BHP→FEFO), modul Finance, Antrian kontekstual,
Absensi, keamanan produksi (TLS/2FA).

---

## 2. Antropometri = MODUL EKSTENSI Sehati (bukan bagian internal)
Modul "Body Composition & Skinfold AI Report" (folder `E:\Apps\body_composition_report_tool`) adalah
aplikasi TERPISAH: proses sendiri, port sendiri (uvicorn :8051), storage sendiri (file JSON di `data/`),
venv sendiri. Ia BUKAN bagian dari codebase Sehati dan TIDAK berbagi database MySQL Sehati.

**Prinsip integrasi (dikunci, "fire-and-forget + PULL"):**
- Sehati hanya melakukan panggilan KELUAR (POST /intake) + baca (GET pull). Sehati **NOL endpoint tulis-masuk**.
- Sehati **TIDAK menyimpan** metrik/laporan antropometri. Modul yang memegang; Sehati menampilkan via pull by No.RM.
- Konektor gagal/modul mati → halaman Sehati tetap jalan (degrade anggun, timeout 3 detik).
- Isolasi ini melindungi stabilitas Sehati: modul boleh mati/restart tanpa mempengaruhi eMR-POS.
- Karena pull-by-rm, **Sehati TIDAK perlu migrasi DB** (tak ada kolom assessment_id disimpan).

**Kenapa modul terpisah:** volume rendah, butuh GPU/AI berbeda, siklus rilis beda, dan menjaga eMR inti tetap ramping & stabil.

---

## 3. Kontrak Data (Sehati → Modul)
Dokumen kanonik: `Project_Memory/CONTRACT_SEHATI_ANTROPOMETRI_v1.md`. `schema_version = "1.0"`.

**Autentikasi:** Bearer **Token A** = `ANTRO_INTAKE_TOKEN` (nilai SAMA di `.env` Sehati dan `.env` modul).
**Alamat modul:** `ANTRO_BASE_URL` di `.env` Sehati (teaser: `http://127.0.0.1:8051`).

**Payload `sehati_antro_input`** (dibangun `app/services/antro_connector_core.build_intake_payload`):
`request_meta` (source_system, rm_number, encounter_id, assessed_at, idempotency_key, return_url) ·
`actor` (role→doctor/nurse/fo, staf_id, name) · `patient` (sex L→male/P→female, age, dob, local_patient_id=No.RM) ·
`measurements` (height/weight/waist/skinfold — OPSIONAL; modul yang mengisi bila kosong) · `screening` ·
`chronic` (kode kosakata bersama) · `activity_level` · `context` · `patient_goal`.
De-identifikasi: hanya No.RM sebagai id lokal; nama TIDAK dikirim ke AI.

**Endpoint modul yang dipakai Sehati:**
`POST /intake` (kirim, balas {assessment_id, url}) · `GET /health` · `GET /status/{id}` ·
`GET /reports?rm={norm}` (papan laporan) · `POST /regenerate/{id}` (re-send bila gagal).
Status terpadu (pull): `processed` (sedang diproses) · `waiting_approval` · `approved` · `rejected` · `failed`.

**Alur end-to-end:** Sehati (dokter/perawat) klik "+Buat Laporan" → POST /intake (identitas + de-id, ukuran kosong)
→ modul balas url form → browser buka **tab baru** ke form modul (identitas pre-fill) → user isi ukuran + TD/nadi
→ submit → modul generate di latar (async) → dokter tinjau di modul (Approve / Reject) → Sehati menampilkan
laporan **approved** via pull di card pasien. return_url membawa balik ke halaman Sehati.

---

## 4. Yang BERUBAH di SEHATI selama pengerjaan antropo
Semua aditif/aman; tak menyentuh keuangan/rekam medis inti.
- **Registrasi pasien** (`pendaftaran_pasien.html` + `routes/pendaftaran.py`): **buang Step 4** (antropometri +
  tanda vital). Wizard jadi 3 langkah. Route stop menyimpan BB/TB/TD/suhu/skinfold.
- **Tanda vital DIHAPUS TOTAL dari Sehati** (keputusan dr. Hansen). Bila perlu, dokter catat di Objective SOAP.
- **Backend antropometri lama = PENSIUN READ-ONLY**: tabel `kunjungan_antropometri`, `antropometri_service`,
  REST `/api/v1/antropometri`, route `.../antropometri/ubah` DIBIARKAN (tak dihapus) tapi tak dipakai UI;
  panel edit inline `_dokter_antropometri_panel.html` kini YATIM. Data historis tetap terbaca (read-only).
- **Detail pasien** (`pasien_detail.html`): card "Antropometri (Laporan AI)" — tarik laporan **approved** dari
  modul + tombol "+Buat Laporan" (tab baru) + hint sedang-diproses/menunggu-approval + data lama di `<details>`.
- **SOAP dokter** (`dokter_soap_form.html`): kolom-3 tampilkan status modul (draft menunggu approval dulu) + tombol Buat.
- **BARU (konektor sisi Sehati):** `app/services/antro_connector.py` (network/urllib), `antro_connector_core.py`
  (payload pure/testable), `antro_report_service.py` (build_payload, kirim, daftar/status/resend, laporan_by_rm).
- **Config:** `app/config.py` + `.env` → `ANTRO_BASE_URL`, `ANTRO_INTAKE_TOKEN`.
- **Route baru:** `POST /web/pasien/{id}/antro/buat` (fire-and-forget + tab baru), `.../antro/{aid}/resend`.
- **Test:** `tests/test_antro_report_service.py`, `tests/test_antro_laporan_display.py`.

---

## 5. Yang DIBANGUN/BERUBAH di MODUL antropo (ringkas)
- **Mesin deterministik:** `plan_engine.py` (BMI Asia-Pasifik, sub-band, target rentang, laju landai per-BMI,
  band kalori), `exercise_engine.py` (olahraga per-tujuan + **tanda vital TD/nadi → intensity_cap**:
  Normal/Elevated/Stage1/Stage2/Krisis 2025 AHA/ACC + nadi; krisis=HOLD tunda+rujuk), `energy.py`.
- **AI:** `prompts_v2.py` (6 komponen, scope-locked, patuh intensity_cap), provider abstraction
  (Anthropic utama + fallback OpenAI + dummy), validator guardrail.
- **Async & data:** `web/jobs.py` (status PROCESSING/DONE/FAILED, tulis file **ATOMIK** mkstemp+os.replace),
  intake pre-fill + return_url, endpoint pull, `data/` = JSON files (SQLite = future).
- **Review dokter:** **Approve** + **Reject terminal (+alasan)**. **TIDAK ADA fitur Edit** (keputusan final;
  edit_field + status doctor_edited dipensiunkan). Audit log dilipat + path filesystem disembunyikan (nama file saja).
- **Test:** test_plan_engine, test_exercise_engine, test_vitals_exercise, test_vitals_pipeline, test_reject,
  test_async_flow, test_connector_core, dll.

---

## 6. DEPLOYMENT MODUL ANTROPO — **TO-DO** (belum dikerjakan)
Saat ini modul jalan sebagai **teaser di WSL** (bersama Sehati) supaya loopback `127.0.0.1:8051` tersambung.
Untuk PRODUKSI di server Ubuntu:
- [ ] Jalankan modul sebagai **systemd service** — file sudah ada: `deployment/antropo.service`
      (uvicorn `bodycomp.web.app:app` host 0.0.0.0:8051, baca `.env` dari WorkingDirectory). Ref `deployment/DEPLOY_ANTROPO.md`.
- [ ] Set `ANTRO_BASE_URL` di `.env` Sehati ke alamat modul produksi (LAN/loopback server, mis. `http://127.0.0.1:8051`
      bila 1 host, atau IP LAN bila beda host). `ANTRO_INTAKE_TOKEN` sama di kedua sisi.
- [ ] **Backup** folder `data/` modul (berisi intake + laporan + job status). Jadwalkan backup rutin.
- [ ] (Opsional) Pasang **WeasyPrint** di server untuk export PDF asli; tanpa itu export → HTML siap-cetak (Ctrl+P).
- [ ] Pastikan aset self-host (tanpa CDN) untuk lingkungan offline klinik.
- **Catatan lingkungan:** di produksi Sehati + modul di **satu host Linux** → loopback `127.0.0.1` bekerja
  langsung (tak ada masalah WSL↔Windows seperti di teaser). systemd auto-restart = tahan mati.

---

## 7. Status known-issues antropo
Semua RESOLVED 2026-07-06: **B-ANTRO-1** (label Diproses vs Menunggu approval), **B-ANTRO-3** (+Buat buka
laporan lama → idempotency_key unik per klik + tab baru), **B-ANTRO-4** (path filesystem bocor + audit log →
nama file saja + dilipat), **B-ANTRO-5** (Reject terminal). Tak ada bug antropo terbuka.

## 8. Catatan usang untuk dibersihkan (opsional)
Item lama di `TODO_SEHATI.md` C-series (kolom `antro_assessment_id`, write-back result-sync/chronic-sync)
kini **USANG** — arsitektur pull-by-rm tak butuh Sehati menyimpan apa pun dari modul. Resep meal-templates
(94 halal) sengaja DORMAN (meal plan pakai AI). Bukan task; hanya opsi bila kelak dipakai.
