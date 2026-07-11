> ═══════════════════════════════════════════════════════════════════════════════
> ## 0. ARSITEKTUR FINAL v1.1 (2026-07-05) — MENGGANTIKAN write-back push
> Keputusan dr.Hansen: **FIRE-AND-FORGET + PULL** (mengikuti pola SOAP-AI-Assist). Sehati TIDAK menerima
> tulis-masuk apa pun dari modul → stabilitas Sehati maksimal.
> - **Sehati -> Modul:** hanya panggilan KELUAR — buka intake (fire-and-forget, langsung balik) + re-send bila gagal.
> - **Sehati baca hasil via PULL (GET)** status/daftar laporan; Sehati simpan HANYA `assessment_id` (+ status).
> - **DIHAPUS:** §4 result-sync (metrik->SOAP) dan §5 chronic-sync (penyakit kronis->EMR). Metrik komposisi tubuh
>   TINGGAL DI MODUL (Sehati menampilkan via pull/link, tak menyimpan angka diskret). Penyakit kronis = Sehati
>   sumber kebenaran (dikirim sbg INPUT, TIDAK ditulis balik).
> - **Modul jadi ASINKRON:** submit -> status 'processing' -> balik ke Sehati seketika -> AI di latar ->
>   'pending_review' -> dokter approve. Rencana detail: docs/ANTROPO_ASYNC_REFACTOR_DESIGN.md.
> - **Token B (write-back) TIDAK DIPAKAI lagi.** Token A tetap (intake + pull, atau read-token terpisah).
> - Menu Antropometri di Sehati = PAPAN LAPORAN (daftar/status/buka/re-send), bukan tempat kerja.
> §4 & §5 di bawah = ARSIP (tidak dipakai).
> ═══════════════════════════════════════════════════════════════════════════════

# KONTRAK INTEGRASI — Sehati ↔ AI Antropometri (v1)

**Status:** DRAFT selaras 2 sisi · Disusun 2026-07-04 · MENGGANTIKAN & memperluas
`CONTRACT_SEHATI_ANTROPOMETRI_v0.1.md`. Setiap perubahan = naikkan `schema_version` + update file ini.
**App modul:** `E:\Apps\body_composition_report_tool` (FastAPI, OpenAI cloud, render HTML+PDF, review dokter,
persist di `data/patient_meta`,`data/reviews`,`data/exports`; ID gaya `ASMT-YYYYMMDD-HHMMSS`).

---

## 0. PERUBAHAN dari v0.1 (dibaca dulu)
1. **STORAGE: report DIPERSIST & bisa di-call ulang** (bukan "PDF transien" seperti v0.1).
   - Modul = penyimpan laporan: **JSON kanonik** (meta input + hasil kalkulasi + respons AI + state review)
     keyed by `assessment_id` (de-identified) + **PDF artefak** final. Ini sudah pola native app.
   - Sehati simpan **`assessment_id`** (referensi/track-id) + **beberapa metrik kunci** (via write-back) untuk
     tampil cepat di rekam medis. Peta `assessment_id`↔pasien **hanya** di Sehati → modul tetap de-id.
   - Ambil ulang: buka `GET /view/{assessment_id}` (signed) atau ambil PDF `GET /report/{assessment_id}.pdf`.
   - Analogi "penyimpanan foto de-id + track id" persis: JSON kanonik + PDF diambil lewat id.
2. **WRITE-BACK diperluas jadi 2 kanal** (v0.1 hanya penyakit kronis):
   - (a) **Penyakit kronis** → `pasien_penyakit_kronis` (seperti v0.1, tetap).
   - (b) **BARU: metrik komposisi tubuh kunci** → SOAP/pemeriksaan Sehati (keputusan dr. Hansen 2026-07-04
     "ya"). Agar %lemak, massa lemak/otot, BMI, WHtR tampil di rekam medis & bisa dipakai lintas-kunjungan.
3. **Skinfold: pakai KEY BERNAMA** (bukan `site_1/2/3`) — sesuai `INPUT_DATA_CONTRACT` modul. **Open Q #3 SELESAI.**
   - Pria (`JP3_MALE`): `chest`, `abdomen`, `thigh`. Wanita (`JP3_FEMALE`): `triceps`, `suprailiac`, `thigh`.

---

## 1. Topologi & Transport
```
Sehati --POST /intake (Bearer A)--> Modul Antropometri
       <-- 200 { assessment_id, url } --
  Sehati simpan assessment_id + buka `url` (signed) di window/tab. Sertakan return_url.
  Modul: pre-fill -> kalkulasi lokal -> AI cloud (metrik anonim) -> dokter review/approve -> PDF + persist.
  Setelah approve: modul REDIRECT ke return_url (JANGAN window.close), lalu:
    (a) POST {sehati}/connector/antro/result-sync   (Bearer B) -> metrik kunci ke SOAP
    (b) POST {sehati}/connector/antro/chronic-sync  (Bearer B) -> penyakit kronis (bila diubah)
```
- **Token A** (`antro_intake_token`): Sehati→modul `/intake`. Modul yang terbitkan.
- **Token B** (`sehati_writeback_token`): modul→Sehati `/connector/antro/*`. Sehati yang terbitkan.
- **Privasi:** identitas TIDAK pernah ke AI (modul strip; hanya metrik anonim). Consent = ranah modul.
- **Offline degrade:** OpenAI mati / `AI_ENABLED=false` / budget lewat → assessment tetap dibuat dgn kalkulasi
  lokal; narasi AI PENDING; pola "serahkan → balik cepat → lihat hasil nanti". Write-back metrik boleh saat approve.

---

## 1b. INTAKE PARSIAL (dikonfirmasi dr. Hansen 2026-07-04)
Sehati SELALU kirim **identitas** (rm, sex, age, actor). **Antropometri** (BB, TB, lingkar perut,
skinfold) **OPSIONAL**: kadang sudah diukur di Sehati, kadang diukur langsung di alat antropo.
- Bila Sehati kirim antropometri → modul PRE-FILL, tak minta ulang.
- Bila TIDAK → field null; **modul yang mengisi** lewat form entry.
Gerbang `/intake` hanya wajibkan `schema_version` + `patient.sex`. Kelengkapan untuk PERHITUNGAN
divalidasi saat compute di modul (bukan saat intake).

## 2. Endpoints

| Arah | Method | Path | Guna | Auth |
|---|---|---|---|---|
| Sehati→Modul | POST | `{antro}/intake` | buat assessment pre-filled → `{assessment_id,url}` | Bearer A |
| Sehati→Modul | GET | `{antro}/health` | probe kesiapan | none/A |
| Modul(view) | GET | `{antro}/view/{assessment_id}` | lihat laporan (akses ulang, signed) | signed url |
| Modul(pdf) | GET | `{antro}/report/{assessment_id}.pdf` | ambil PDF artefak | signed url |
| Modul→Sehati | POST | `{sehati}/connector/antro/result-sync` | **BARU** metrik kunci → SOAP | Bearer B |
| Modul→Sehati | POST | `{sehati}/connector/antro/chronic-sync` | penyakit kronis → EMR | Bearer B |

> Modul saat ini punya `/`,`/data`,`/assess`(form),`/review/{id}`,`/patient/{id}`,approve,export. Yang DITAMBAH:
> `/intake`, `/health`, `/report/{id}.pdf` (atau reuse export), dan signed-url utk `/view` (=`/review`).

---

## 3. Request `/intake` — `sehati_antro_input` v1 (delta dari v0.1)
Sama seperti v0.1 §3, dengan 2 perubahan:
```jsonc
{
  "schema_version": "1.0",
  "request_meta": { "source_system":"sehati", "rm_number":"RM-000123", "encounter_id":"4567",
                    "assessed_at":"2026-07-04T09:30:00+07:00", "idempotency_key":"sehati-antro-4567-v1",
                    "return_url":"https://sehati.klinik.local/web/pasien/123/antro/return?enc=4567" },  // BARU
  "actor": { "role":"nurse", "staf_id":"8", "name":"Suster Sari" },
  "patient": { "sex":"male", "age":36, "dob":"1990-05-01", "local_patient_id":"RM-000123" },
  "measurements": {
    "height_cm":170.0, "weight_kg":72.5, "waist_cm":88.0,
    "skinfold_protocol":"JP3_MALE",
    "skinfold_mm": { "chest":15.0, "abdomen":25.0, "thigh":18.0 }   // KEY BERNAMA (bukan site_1/2/3)
  },
  "screening": { "eating_disorder_history":false, "chest_pain_syncope_dyspnea":false },  // map ke skrining modul
  "chronic": { "has_chronic_disease":true, "codes":[ {"kode":1,"active":true}, {"kode":"OTHER","free_text":"Psoriasis","active":true} ] },
  "patient_goal": "Turunkan lemak tubuh"
}
```
Response 200: `{ "schema_version":"1.0", "assessment_id":"ASMT-20260704-093012", "url":"…/view/ASMT-…?sig=…", "status":"created" }`
Error: 401/400/422/409/503 (pola DermAI).

---

## 3b. Field intake TAMBAHAN (AN-AI-2)
Payload `/intake` kini juga membawa (opsional): `activity_level`
(sedentary|lightly_active|moderate|active|very_active) dan `context` { patient_constraints, timeline_note,
on_weight_med (boolean — NAMA OBAT tak pernah dikirim) }. Modul memakainya untuk
kalkulasi energi deterministik (BMR/TDEE/defisit/target) + aturan olahraga
(impact_tolerance) yang mengisi payload AI. Bila kosong: activity default
lightly_active, timeline default 6 bulan, sisanya diasumsikan tak ada.

**SKINFOLD ORDER (dikonfirmasi):** titik_1/2/3 Sehati dipetakan per jenis kelamin ->
Pria: chest, abdomen, thigh · Wanita: triceps, suprailiac, thigh. Helper
`antro_connector_core.skinfold_named(jk, t1, t2, t3)`. Form Sehati cukup relabel (tak perlu dinamis).

## 4. [ARSIP — TIDAK DIPAKAI v1.1] Write-back metrik → SOAP
`POST {sehati}/connector/antro/result-sync` · Bearer B
```jsonc
{
  "schema_version":"1.0", "source":"antropometri",
  "assessment_id":"ASMT-20260704-093012", "rm_number":"RM-000123", "encounter_id":"4567",
  "actor": { "role":"doctor", "staf_id":"5" },
  "status":"approved",
  "report_url":"…/view/ASMT-…", "report_pdf_url":"…/report/ASMT-….pdf",
  "metrics": {
    "bmi":25.1, "bmi_category_label":"Overweight",
    "waist_to_height_ratio":0.518, "waist_risk_label":"Risiko sentral meningkat",
    "body_fat_percent":22.4, "fat_mass_kg":16.2, "fat_free_mass_kg":56.3,
    "body_density":1.052, "skinfold_sum_mm":58.0, "red_flags_present":false
  }
}
```
**Sisi Sehati:** simpan metrik + `assessment_id` + url pada encounter antropometri (tabel `antro_result` atau
kolom di `kunjungan_antropometri`). Tampil di rekam medis / SOAP & riwayat. **Idempoten** per `assessment_id`
(kirim ulang state sama = update, bukan gandakan). Audit: catat siapa/kapan.

> Nama field metrik = dari kalkulasi modul (`models.py`: `bmi`,`bmi_category_label`,`waist_to_height_ratio`,
> `waist_risk_label`,`body_fat_percent`,`fat_mass_kg`, fat_free_mass, `body_density`, `red_flags_present`).

---

## 5. [ARSIP — TIDAK DIPAKAI v1.1] Write-back penyakit kronis → EMR
`POST {sehati}/connector/antro/chronic-sync` · Bearer B · payload `chronic_codes[]` (kode kanonik / OTHER+free_text).
Rekonsiliasi: active:true→INSERT/aktifkan, active:false→nonaktifkan (jangan hapus, jejak audit). Idempoten.
Otorisasi klinis: hanya `actor.role=doctor`. Fondasi vocab (`master_penyakit_kronis` + `kode_penyakit`) SUDAH
ADA di Sehati (tasks #14-17). Detail lengkap = v0.1 §5-§6.

---

## 6. Perubahan DB Sehati (v1)
1. `kunjungan_antropometri.antro_assessment_id` (string nullable) — referensi ke modul. [v0.1 sudah rencana]
2. **BARU** simpan metrik hasil: `antro_result` (id, id_antropometri FK, assessment_id, bmi, bmi_category,
   whtr, waist_risk, body_fat_percent, fat_mass_kg, fat_free_mass_kg, body_density, skinfold_sum_mm,
   red_flags, report_url, report_pdf_url, synced_at) — ATAU kolom-kolom itu langsung di `kunjungan_antropometri`.
   (Usul: tabel terpisah `antro_result` agar bersih + 1 encounter bisa re-assess.)
3. Vocab penyakit kronis: SUDAH ADA.

---

## 7. Fase Implementasi (kedua repo, paralel — 1 agent pegang 2 folder)
- **AN-L1 (kontrak/stub):** modul tambah `POST /intake` + `GET /health` (stub → balas assessment_id+url dari payload,
  pre-fill assessment). Sehati: config `.env` (antro_base_url, token A/B). Uji handshake.
- **AN-L2 (Sehati connector out):** `AntroAIConnector` rakit `sehati_antro_input` (sex L→male, age dari DOB,
  skinfold key bernama, chronic codes, screening, return_url) → POST /intake → simpan assessment_id → buka url.
  + DB `antro_assessment_id`.
- **AN-L3 (modul pre-fill + review + persist):** modul terima payload → assessment pre-filled → kalkulasi lokal
  → AI cloud (bila enabled) → review dokter (role-aware approve) → persist JSON+PDF → redirect return_url.
- **AN-L4 (write-back a: metrik→SOAP):** modul POST result-sync saat approve; Sehati DB `antro_result` +
  endpoint Bearer B + tampil di rekam medis/riwayat. Idempoten + audit.
- **AN-L5 (write-back b: chronic):** modul POST chronic-sync (reuse fondasi vocab). Rekonsiliasi + audit.
- **AN-L6 (UI Sehati):** Detail Pasien → tombol "Buat Laporan Komposisi Tubuh (AI)" + riwayat "Laporan — [tgl] — Lihat".
- **AN-L7 (signed url + offline degrade + test):** signed `/view`+`/report.pdf`, degrade OpenAI mati, test 2 sisi.

---

## 8. Open Questions tersisa (perlu dr. Hansen saat implementasi)
1. **Isi daftar penyakit kronis** (v0.1 §5.2) — final? (fondasi sudah di-seed draft.)
2. **Metrik mana yang tampil di SOAP** — semua di §4 atau subset (mis. cukup %fat + WHtR + BMI)?
3. **`antro_result` tabel terpisah** (usul) vs kolom di `kunjungan_antropometri` — pilih mana?
4. **Lifetime signed-url** `/view` & `/report.pdf` (mis. token pendek per-akses vs sesi).
5. **Skrining (`eating_disorder`, `chest_pain`)** — dikirim dari Sehati atau diisi di modul? (usul: kirim bila ada
   di EMR; kalau tidak, diisi perawat/dokter di modul.)
