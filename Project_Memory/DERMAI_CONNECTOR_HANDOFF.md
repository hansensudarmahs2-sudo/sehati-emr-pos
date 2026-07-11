═══════════════════════════════════════════════════════════
SESSION HANDOFF — Konektor Sehati ↔ DermAI (Phase 0)
Disusun: 2026-06-26 · untuk sesi berikutnya (kepala segar)
═══════════════════════════════════════════════════════════

## ROLE
Anda adalah Claude, **lead programmer Sehati eMR-POS + master designer ekosistem klinik
dr. Hansen**. Sehati = **otak utama** ekosistem; DermAI = modul AI dermatologi yang
**menyesuaikan diri ke Sehati**. dr. Hansen = dokter pemilik (BUKAN programmer); Bahasa
Indonesia casual. Karena Sehati adalah master, Anda berwenang **menentukan kontrak integrasi
dari sudut Sehati** dan menetapkan perbaikan yang DermAI perlu lakukan agar pas.

## DUA PROYEK (dua-duanya ke-mount di Cowork)
- **Sehati** (master): `E:\Claude\Projects\sehati-emr-pos\sehati_clinic`
  Stack: FastAPI + SQLAlchemy 2.0 + Pydantic 2 + MySQL + Jinja2 + HTMX. App jalan port 8000.
- **DermAI** (modul): `E:\AI_PROJECTS\derma-ai`
  - `dermai_app/` = web app Part 1 (FastAPI, port 8000, auth, SQLite, HTTPS certs) — **SELESAI (stub)**.
  - `dermai_engine/` = embedding/analyzer (port 9000). `qdrant_data/` = Qdrant (6333).
  - `dermai-pipeline/` = dokumen 01-24. `schemas/`, `templates/`.
  - Cara jalan: `derma-ai/RUN.md`.

## BACA DULU (URUT)
1. DermAI kontrak: `dermai-pipeline/15_SEHATI_INTEGRATION_GUIDE.md`, `07_SEHATI_INTERFACE.md`,
   `schemas/sehati_soap_input.schema.json`, `templates/sehati_soap_example.json`.
2. DermAI status & rute: `17_PART1_NOTES.md` (Part 1 selesai), `14_PART1_ROUTES.md`,
   `dermai_app/app/main.py` + routers (cek route /intake, /cases, /capture aktual).
3. Sehati: SOAP route `app/web/routes/dokter.py` + `pemeriksaan_service.py` + template
   `dokter_soap_form.html`; Ruang Tindakan `ruang-tindakan`; `app/config.py` (.env settings).

═══════════════════════════════════════════════════════════
## KONTRAK INTEGRASI (v0.1 — terkunci, SATU ARAH)
═══════════════════════════════════════════════════════════
```
Sehati (SOAP/Tindakan) --POST /intake (HTTPS + Bearer token)--> DermAI
                       <-- 200 {case_id, url} --
Sehati buka browser/WebView ke `url`. Sisanya (foto, AI, review) di jendela DermAI.
```
- Sehati simpan **2 hal**: `base_url` + `intake_token`. Tidak ada write-back ke eMR (kecuali
  Sehati menyimpan `case_id` sebagai referensi foto).
- DermAI yang melakukan **de-id + foto + AI + review**. Sehati TIDAK kirim foto.
- **Payload** = `sehati_soap_input` (schema v0.1). Wajib: `schema_version`, `request_meta`
  (rm_number, encounter_id, visit_datetime, examining_doctor_id), `consent`
  (cloud_processing_consent), `patient` (sex), `soap` (subjective + objective),
  `clinical_context`.
- **PENTING:** isi `objective` (GAGS, lesi, fitzpatrick) **OPSIONAL** — Sehati boleh kirim
  `objective` hanya berisi `exam_free_text`. **GAGS digrading di DermAI, bukan di Sehati.**
- Consent gerbang: `cloud_processing_consent=true` baru boleh ke cloud.

═══════════════════════════════════════════════════════════
## 4 KEPUTUSAN KONTRAK BARU (v0.2 — koordinasi 2 sisi)
═══════════════════════════════════════════════════════════
1. **Routing acne/non-acne** (`is_acne` + `acne_severity`): acne → DermAI jalankan pipeline
   penuh; non-acne → DermAI cuma tag + simpan foto + balikkan `case_id`, TANPA AI.
2. **Peran aktor** (`actor.role` = dokter/perawat): dokter = akses penuh (lihat analisa/laporan/
   saran AI); perawat = foto saja, TIDAK lihat hasil AI.
3. **Mode "lihat foto"** (mis. `/view`): perawat saat tindakan + dokter akses ulang riwayat.
4. **DermAI konsumsi SOAP Sehati tanpa tanya ulang** (anti-duplikasi): mode intake pakai SOAP
   dari payload (read-only), tidak menampilkan form input dokter standalone lagi.

═══════════════════════════════════════════════════════════
## PRINSIP PENGIKAT (mencegah edge-case sticky-diagnosis)
═══════════════════════════════════════════════════════════
**"Analisa AI selalu terikat konsultasi dokter yang SEGAR. Foto boleh diambil kapan saja
(konsul/tindakan), tapi AI hanya jalan atas diagnosa yang dokter buat saat konsultasi."**
→ Karena perawat & sesi series TIDAK menjalankan AI (cuma simpan foto), severity basi tidak
pernah masuk ke AI. Masalah series (kunjungan-1 severe, series-3 harusnya mild) jadi tidak
berbahaya di Phase 0.

═══════════════════════════════════════════════════════════
## PHASE 0 — PEKERJAAN SISI SEHATI
═══════════════════════════════════════════════════════════
1. **Form SOAP — diagnosa jadi terstruktur ringan:** toggle **Acne / Non-acne**.
   - Non-acne → teks bebas (seperti sekarang).
   - Acne → dropdown **mild / moderate / severe / mix** (+ teks bebas opsional).
2. **DB kecil** (migrasi minimal): `is_acne` (bool), `acne_severity` (enum/string),
   `dermai_case_id` (string, nullable) di tabel pemeriksaan/kunjungan.
3. **Field consent BARU:** `cloud_processing_consent` per pasien (Sehati belum punya — perlu
   capture + simpan). Ini gerbang wajib kontrak.
4. **Service `DermAIConnector`:** bangun `sehati_soap_input` dari kunjungan+SOAP → POST `/intake`
   (Bearer) → handle `{case_id, url}` + error (401/400/422/409) → simpan case_id → buka jendela.
   Config `base_url` + `intake_token` di `.env`/klinik_config.
5. **Pemetaan field:** rm_number←no_rm, encounter_id←id_kunjungan, visit_datetime←tgl_kunjungan,
   examining_doctor_id←id_staf_dokter, sex←jenis_kelamin (**peta L→M, P→F**), dob←tgl_lahir,
   subjective←anamnesa, objective.exam_free_text←pemeriksaan fisik.
6. **Tombol UI:** SOAP Dokter = "Analisa Foto (DermAI)" akses penuh (kirim is_acne + role=dokter);
   Ruang Tindakan = "Foto DermAI" akses terbatas (role=perawat, foto saja).
7. Gerbang consent sebelum kirim; kalau consent false → boleh tetap simpan foto (non-cloud).

═══════════════════════════════════════════════════════════
## PHASE 0 — TO-DO PERBAIKAN DERMAI (agar molding ke Sehati)
═══════════════════════════════════════════════════════════
> DermAI Part 1 SUDAH ada (auth, DB, intake, capture, review, audit, HTTPS, RBAC 2-tier).
> Jadi ini **penyesuaian**, bukan bangun dari nol. Verifikasi tiap poin vs `14_PART1_ROUTES.md`
> + `dermai_app/app/` sebelum eksekusi.

1. **Role "perawat" + gating AI.** RBAC sekarang 2-tier (owner/dokter). Tambah peran perawat:
   boleh buka case + ambil/lihat foto, TAPI sembunyikan analisa/laporan/saran AI. Terima
   `actor.role` di /intake + enforce di template/route.
2. **Routing non-acne.** Tambah `is_acne` di intake. Kalau false → lewati engine+cloud, cukup
   tag + simpan foto + balikkan case_id. Schema sekarang acne-only.
3. **Mode `/view` (lihat foto).** Untuk perawat + akses ulang dokter. Sekarang baru `/capture`.
4. **Intake = konsumsi SOAP, jangan tanya ulang.** Form "Kasus baru in-app" (input dokter
   standalone) hanya untuk mode non-integrasi. Saat dari Sehati intake → SOAP read-only
   pre-filled; dokter cukup grading GAGS + foto. Hilangkan duplikasi entri.
5. **Toleransi objective minimal.** Terima payload di mana objective cuma `exam_free_text`
   (tanpa GAGS) → prompt dokter grading GAGS di jendela DermAI. Jangan error kalau GAGS kosong.
6. **case_id sebagai referensi foto** — pastikan persist + return (konfirmasi sudah ada).
7. **schema_version → 0.2** dengan field baru (actor.role, is_acne, view). Koordinasi 2 tim +
   update `schemas/sehati_soap_input.schema.json`.
8. **Stub /intake publik** untuk Sehati uji paralel (cek apakah sudah ada).
9. **Deployment ikut topologi Sehati:** base_url klinik, **HTTPS cert dipercaya** (mkcert/CA
   internal, bukan self-signed manual), token intake dibagikan ke Sehati. (Catatan di 17.)

═══════════════════════════════════════════════════════════
## OUT OF SCOPE PHASE 0 (parkir — JANGAN dikerjakan)
═══════════════════════════════════════════════════════════
- **Series severity re-assessment** (foto before/after sepanjang series + re-grading) → Phase 1.
- **Dokter re-run AI dari riwayat** → Phase 1.
- **Kunjungan palsu untuk SOAP baru** → DITOLAK PERMANEN (mengacau audit log). Solusi sah =
  entri "penilaian ulang" saat pasien series HADIR (desain Phase 1).
- **Write-back hasil AI ke eMR Sehati** → ditunda (one-way + simpan case_id saja).

═══════════════════════════════════════════════════════════
## START SEQUENCE
═══════════════════════════════════════════════════════════
1. Baca kontrak + status DermAI (15, 07, schema, 17, 14, main.py) + SOAP Sehati.
2. Kunci 4 keputusan kontrak v0.2 bareng dr. Hansen.
3. Rancang skeleton: `DermAIConnector` service + perubahan form SOAP (toggle acne) + field DB +
   tombol SOAP/Tindakan. Tunjukkan breakdown → minta approval.
4. Implement sisi Sehati (pakai patch-script/heredoc — bukan Edit tool untuk file besar; B-013
   sudah hilang di E: tapi tetap hati-hati). Verify via bash (py_compile, jinja, null-byte).
5. Susun daftar perbaikan DermAI sebagai workplan terpisah di proyek DermAI.
6. Uji bareng pakai stub /intake.

Mulai dengan baca kontrak dua sisi, lalu breakdown + tunggu approval dr. Hansen sebelum coding.
═══════════════════════════════════════════════════════════
