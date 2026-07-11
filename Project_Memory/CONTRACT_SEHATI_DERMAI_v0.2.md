# KONTRAK DATA — Sehati ↔ DermAI (v0.2)

**Status:** DRAFT untuk disepakati 2 sisi · Disusun 2026-06-27 · ref DERMAI_CONNECTOR_HANDOFF.md
**Sifat:** Satu arah (Sehati = master pemanggil; DermAI = modul penerima).
**Revisi:** v0.2.1 (2026-06-27) — consent cloud = ranah DermAI (bukan Sehati); role Owner/Admin/Superadmin→doctor dikonfirmasi.
**Tujuan dokumen:** Satu sumber kebenaran agar sisi Sehati dan sisi DermAI bisa
dikerjakan paralel tanpa saling tunggu. Setiap perubahan kontrak = naikkan `schema_version` + update file ini.

---

## 1. Topologi & Transport

```
Sehati (SOAP/Tindakan)  --HTTPS POST /intake (Bearer token)-->  DermAI
                        <-- 200 { case_id, url, status } --
Sehati simpan case_id (referensi) + buka browser/WebView ke `url`.
Semua foto/AI/review terjadi di jendela DermAI. Sehati TIDAK kirim foto, TIDAK terima hasil AI.
```

- **Protocol:** HTTPS (LAN klinik). Cert dipercaya (mkcert/CA internal), bukan self-signed manual.
- **Auth:** Header `Authorization: Bearer <intake_token>`. Token statis dibagikan DermAI → Sehati.
- **Content-Type:** `application/json; charset=utf-8`.
- **Yang Sehati simpan:** `dermai_base_url`, `dermai_intake_token` (config), dan `dermai_case_id` (per pemeriksaan) sebagai referensi. Tidak ada write-back hasil AI ke eMR.

---

## 2. Endpoints

| Method | Path | Guna | Auth |
|---|---|---|---|
| POST | `{base_url}/intake` | Kirim SOAP → buat/lanjut case, balas url | Bearer |
| GET  | `{base_url}/health` | Probe kesiapan (untuk uji paralel Sehati) | Bearer/none |
| GET  | `{base_url}/view/{case_id}` | (opsional) buka foto/riwayat; biasanya cukup pakai `url` dari /intake | sesi DermAI |

> `url` yang dibalas /intake sudah membawa konteks (case + mode + role). Sehati cukup membukanya.

---

## 3. Request — `sehati_soap_input` v0.2

### 3.1 Struktur (JSON)

```json
{
  "schema_version": "0.2",
  "request_meta": {
    "source_system": "sehati",
    "rm_number": "RM-000123",
    "encounter_id": "4567",
    "visit_datetime": "2026-06-27T09:30:00+07:00",
    "examining_doctor_id": "5",
    "idempotency_key": "sehati-enc-4567-v1"
  },
  "actor": {
    "role": "doctor",
    "staf_id": "5",
    "name": "dr. Hansen"
  },
  "consent": {
    "cloud_processing_consent": true
  },
  "patient": {
    "sex": "M",
    "dob": "1990-05-01",
    "local_patient_id": "RM-000123"
  },
  "soap": {
    "subjective": "Jerawat meradang di pipi sejak 3 minggu...",
    "objective": {
      "exam_free_text": "Papula & pustula multipel regio bukal bilateral..."
    }
  },
  "clinical_context": {
    "is_acne": true,
    "acne_severity": "moderate",
    "assessment_free_text": "Acne vulgaris moderate",
    "plan_free_text": "Topikal retinoid malam; kontrol 2 minggu"
  },
  "options": {
    "mode": "analyze"
  }
}
```

### 3.2 Field — wajib/opsional & aturan

| Field | Tipe | Wajib | Aturan |
|---|---|---|---|
| `schema_version` | string | ✅ | Harus `"0.2"`. Mismatch → 422. |
| `request_meta.source_system` | string | ✅ | Selalu `"sehati"`. |
| `request_meta.rm_number` | string | ✅ | Nomor RM (display/link, bukan ke AI). |
| `request_meta.encounter_id` | string | ✅ | id_kunjungan Sehati (string-kan). |
| `request_meta.visit_datetime` | string ISO8601 | ✅ | Sertakan offset `+07:00`. |
| `request_meta.examining_doctor_id` | string | ✅ | id dokter pemeriksa. |
| `request_meta.idempotency_key` | string | ⭕ disarankan | Sama untuk retry encounter yang sama → DermAI balas case yang sama (status `existing`). |
| `actor.role` | enum | ✅ | `doctor` \| `nurse`. Gating AI di DermAI. |
| `actor.staf_id` | string | ✅ | id staf yang menekan tombol. |
| `actor.name` | string | ⭕ | Display. |
| `consent` (block) | object | ⭕ | **Opsional / informational.** Consent cloud DITANGKAP & DITEGAKKAN oleh DermAI di jendelanya (lihat §7). Sehati boleh mengirim status yang diketahui, tapi BUKAN sumber kebenaran. |
| `patient.sex` | enum | ✅ | `M` \| `F`. |
| `patient.dob` | string date | ⭕ | `YYYY-MM-DD`. |
| `patient.local_patient_id` | string | ⭕ | = rm_number; display only, **tidak ke AI**. |
| `soap.subjective` | string | ✅ | Anamnesa. |
| `soap.objective` | object | ⭕ | Boleh hanya `{ "exam_free_text": "..." }`. |
| `soap.objective.exam_free_text` | string | ⭕ | Pemeriksaan fisik bebas. |
| `soap.objective.gags` / `lesions` / `fitzpatrick` | (lihat schema DermAI) | ⭕ | **Digrading di DermAI**, Sehati boleh kosongkan. |
| `clinical_context.is_acne` | bool | ✅ | Routing: `true` → pipeline AI penuh; `false` → tag + simpan foto + balas case_id, TANPA AI. |
| `clinical_context.acne_severity` | enum\|null | bersyarat | Wajib bila `is_acne=true`: `mild`\|`moderate`\|`severe`\|`mix`. `null` bila non-acne. |
| `clinical_context.assessment_free_text` | string | ⭕ | Diagnosa dokter. |
| `clinical_context.plan_free_text` | string | ⭕ | Rencana/plan. |
| `options.mode` | enum | ⭕ | `analyze` (default, dokter) \| `photo_only` (perawat ambil foto) \| `view` (lihat ulang). |

---

## 4. Response

### 4.1 Sukses — 200

```json
{ "schema_version": "0.2", "case_id": "case_abc123", "url": "https://dermai.klinik.local/case/case_abc123?...", "status": "created" }
```

| Field | Tipe | Catatan |
|---|---|---|
| `case_id` | string | Sehati simpan ke `pemeriksaan_klinis.dermai_case_id`. |
| `url` | string (absolute) | Sehati buka di browser/WebView. |
| `status` | enum | `created` (baru) \| `existing` (idempotency hit). |

### 4.2 Error (semua JSON `{ "error_code", "message", "details?" }`)

| HTTP | error_code | Kapan | Aksi Sehati |
|---|---|---|---|
| 401 | `unauthorized` | Token salah/hilang | Cek config token; tampilkan "konektor DermAI belum siap". |
| 400 | `bad_request` | JSON rusak/Content-Type salah | Bug Sehati; log. |
| 422 | `validation_error` | Schema/enum/consitency salah (mis. is_acne true tapi severity null; schema_version mismatch) | Tampilkan detail field; jangan retry tanpa perbaikan. |
| 409 | `conflict` | encounter konflik (idempotency beda payload) | Tampilkan; minta dokter cek. |
| 503 | `engine_unavailable` | DermAI/engine down | "DermAI sementara tak tersedia"; boleh tetap simpan foto lokal (lihat consent false path). |

---

## 5. Pemetaan Field (Sehati → Kontrak) — KOLOM ASLI

| Kontrak | Sumber Sehati (tabel.kolom) | Transform |
|---|---|---|
| `request_meta.rm_number` | `pasien.no_rm` | str |
| `request_meta.encounter_id` | `kunjungan.id_kunjungan` | int→str |
| `request_meta.visit_datetime` | `kunjungan.tgl_kunjungan` | → ISO8601 +07:00 |
| `request_meta.examining_doctor_id` | `pemeriksaan_klinis.id_staf_dokter` (fallback `kunjungan.id_staf_dokter_assigned`) | int→str |
| `actor.role` | role user login (`master_staf.role`) | `Dokter`→`doctor`; `Perawat`→`nurse`; `Owner/Admin/Superadmin`→`doctor` (akses penuh); lainnya → tolak tombol |
| `actor.staf_id` | user.id_staf | int→str |
| `consent` | — (tidak ada field Sehati) | **Ditangani DermAI**; Sehati tidak menyimpan consent cloud |
| `patient.sex` | `pasien.jenis_kelamin` (GenderEnum L/P) | **L→M, P→F** |
| `patient.dob` | `pasien.tgl_lahir` | date `YYYY-MM-DD` |
| `patient.local_patient_id` | `pasien.no_rm` | str (display only) |
| `soap.subjective` | `pemeriksaan_klinis.anamnesa` | str |
| `soap.objective.exam_free_text` | `pemeriksaan_klinis.pemeriksaan_fisik` | str |
| `clinical_context.is_acne` | **BARU** `pemeriksaan_klinis.is_acne` | bool |
| `clinical_context.acne_severity` | **BARU** `pemeriksaan_klinis.acne_severity` | enum/null |
| `clinical_context.assessment_free_text` | `pemeriksaan_klinis.diagnosa` | str |
| `clinical_context.plan_free_text` | `pemeriksaan_klinis.saran_treatment` (+ `saran_produk`) | gabung str |

### Enum map ringkas
- **sex:** `L → M`, `P → F`.
- **actor.role:** `Dokter/Owner/Admin/Superadmin → doctor`, `Perawat → nurse`.
- **acne_severity:** `mild | moderate | severe | mix` (cocok dropdown SOAP Sehati).

---

## 6. Versioning
- `schema_version` di setiap payload. v0.2 = penambahan `actor`, `is_acne/acne_severity`, `options.mode`.
- Perubahan breaking → naikkan minor (`0.3`), update file ini + `schemas/sehati_soap_input.schema.json` di DermAI bersamaan.
- DermAI WAJIB tolak (422) versi yang tak didukung, sebut versi yang didukung di `details`.

---

## 7. Consent (gerbang) — RANAH DERMAI
**Keputusan (dr. Hansen, 2026-06-27):** cloud processing consent adalah tanggung jawab **DermAI**,
bukan Sehati. Alasannya: DermAI yang melakukan proses cloud/AI, dan pasien ada di jendela DermAI
saat foto diambil. Maka:
- **DermAI** menangkap + menegakkan persetujuan proses cloud SEBELUM mengirim ke AI. Consent
  `true` → proses cloud; `false`/belum → tahan (boleh "foto lokal saja").
- **Sehati TIDAK** menambah field/tabel consent dan TIDAK jadi gerbang. Block `consent` di payload
  bersifat opsional/informational saja.

---

## 8. Checklist — SISI SEHATI (yang saya/kamu kerjakan di repo Sehati)

1. **DB migrasi kecil** di `pemeriksaan_klinis`: `is_acne` (bool), `acne_severity` (string/enum nullable), `dermai_case_id` (string nullable). **Tidak ada** field consent di Sehati (ranah DermAI, §7).
2. **Form SOAP** (`dokter_soap_form.html` + service): toggle **Acne/Non-acne**; bila Acne → dropdown `mild/moderate/severe/mix`. Non-acne → teks bebas seperti sekarang.
3. **(Consent cloud = ranah DermAI)** — Sehati tidak menangkap/menyimpan consent cloud; cukup serahkan ke DermAI.
4. **Service `DermAIConnector`**: rakit payload v0.2 dari kunjungan+SOAP+pasien+actor → `POST /intake` (Bearer) → handle 200/401/400/422/409/503 → simpan `dermai_case_id` → balas `url` ke UI untuk dibuka.
5. **Config**: `dermai_base_url` + `dermai_intake_token` di `app/config.py` (.env) — saat ini BELUM ada.
6. **Tombol UI**: SOAP Dokter = "Analisa Foto (DermAI)" (mode=analyze, role=doctor, kirim is_acne); Ruang Tindakan = "Foto DermAI" (mode=photo_only, role=nurse).
7. **Riwayat**: tampilkan link buka case (pakai `url`/case_id) untuk akses ulang.
8. Tidak ada gerbang consent di Sehati. Mode (`analyze`/`photo_only`) menentukan alur; consent cloud ditegakkan DermAI.

## 9. Checklist — SISI DERMAI (kamu kerjakan di repo derma-ai)

1. **Terima v0.2**: tambah `actor.role`, `is_acne`/`acne_severity`, `options.mode` di `/intake` + `schemas/sehati_soap_input.schema.json`.
2. **Role gating**: `nurse` → boleh buka case + ambil/lihat foto, TAPI sembunyikan analisa/laporan/saran AI. `doctor` → akses penuh.
3. **Routing non-acne**: `is_acne=false` → skip engine+cloud, cukup tag + simpan foto + balas `case_id`.
4. **Konsumsi SOAP read-only** (anti-duplikasi): saat intake dari Sehati, SOAP pre-filled read-only; dokter cukup grading GAGS + foto. Form input standalone hanya untuk mode non-integrasi.
5. **Toleransi objective minimal**: terima payload yang `objective` hanya `exam_free_text` (GAGS kosong) → prompt grading di DermAI, jangan error.
6. **Mode `/view`** (lihat foto) untuk perawat + akses ulang dokter.
7. **Idempotency**: `idempotency_key` sama → balas case yang sama (`status: existing`).
8. **`case_id` persist + return** (konfirmasi sudah ada).
9. **Stub `/intake` + `/health`** publik untuk uji paralel Sehati.
10. **Deployment**: base_url klinik, HTTPS cert dipercaya, token dibagikan ke Sehati.
11. **Consent cloud (system of record):** DermAI menangkap + menegakkan persetujuan proses cloud di jendelanya sebelum kirim ke AI. Sehati bukan sumber consent.

---

## 10. Contoh Payload

### 10.1 Acne (mode analyze, dokter)
```json
{ "schema_version":"0.2",
  "request_meta":{"source_system":"sehati","rm_number":"RM-000123","encounter_id":"4567","visit_datetime":"2026-06-27T09:30:00+07:00","examining_doctor_id":"5","idempotency_key":"sehati-enc-4567-v1"},
  "actor":{"role":"doctor","staf_id":"5","name":"dr. Hansen"},
  "consent":{"cloud_processing_consent":true},
  "patient":{"sex":"M","dob":"1990-05-01","local_patient_id":"RM-000123"},
  "soap":{"subjective":"Jerawat meradang 3 minggu","objective":{"exam_free_text":"Papula & pustula regio bukal"}},
  "clinical_context":{"is_acne":true,"acne_severity":"moderate","assessment_free_text":"Acne vulgaris moderate","plan_free_text":"Topikal retinoid; kontrol 2 minggu"},
  "options":{"mode":"analyze"} }
```

### 10.2 Non-acne (mode photo_only, perawat)
```json
{ "schema_version":"0.2",
  "request_meta":{"source_system":"sehati","rm_number":"RM-000200","encounter_id":"4570","visit_datetime":"2026-06-27T10:00:00+07:00","examining_doctor_id":"5"},
  "actor":{"role":"nurse","staf_id":"8"},
  "consent":{"cloud_processing_consent":false},
  "patient":{"sex":"F","local_patient_id":"RM-000200"},
  "soap":{"subjective":"Bercak hiperpigmentasi","objective":{"exam_free_text":"Makula hiperpigmentasi regio zygomatik"}},
  "clinical_context":{"is_acne":false,"acne_severity":null,"assessment_free_text":"Melasma (DD)"},
  "options":{"mode":"photo_only"} }
```

---

## 11. Rencana Uji Bersama (paralel, pakai stub)
1. DermAI sediakan stub `/health` + `/intake` yang echo `{case_id, url}` tanpa AI.
2. Sehati panggil dengan §10.1 & §10.2 → verifikasi: 200, case_id tersimpan, url terbuka.
3. Uji error: token salah → 401; is_acne true + severity null → 422; consent false → case non-cloud.
4. Setelah kontrak stabil, DermAI nyalakan pipeline penuh; Sehati tidak perlu berubah.

---

## 12. Open Questions (perlu disepakati 2 sisi)
1. ~~Consent granularity~~ → **RESOLVED**: consent cloud = ranah DermAI (§7).
2. ~~actor.role Owner/Admin~~ → **RESOLVED**: `Owner/Admin/Superadmin → doctor` (akses penuh).
3. **`url` lifetime / auth:** apakah `url` mengandung token sesi sementara, atau butuh login DermAI? (untuk WebView mulus).
4. **examining_doctor_id sumber:** `pemeriksaan_klinis.id_staf_dokter` vs `kunjungan.id_staf_dokter_assigned` saat berbeda.
5. **`view` endpoint:** bentuk final (`/view/{case_id}` vs `url` ber-mode) — konfirmasi DermAI.
6. **acne_severity "mix":** pastikan DermAI mengenali nilai ini.

---
*Versi & perubahan kontrak dicatat di sini + decisions_log Sehati. Naikkan schema_version untuk perubahan breaking.*
