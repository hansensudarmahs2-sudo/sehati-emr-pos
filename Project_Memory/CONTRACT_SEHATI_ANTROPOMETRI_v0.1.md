> ⚠️ **DIGANTIKAN oleh `CONTRACT_SEHATI_ANTROPOMETRI_v1.md` (2026-07-04).** v1 mengubah storage jadi
> persist+retrievable (JSON kanonik+PDF) & menambah write-back metrik→SOAP. Baca v1 untuk implementasi.

# KONTRAK DATA — Sehati ↔ AI Antropometri (v0.1)

**Status:** DRAFT untuk disepakati 2 sisi · Disusun 2026-06-27 · ref ANTROPOMETRI_CONNECTOR_HANDOFF.md
**Sifat:** Intake satu arah (Sehati → modul) + **write-back penyakit kronis** (modul → Sehati).
**Tujuan:** Satu sumber kebenaran agar sisi Sehati & sisi modul Antropometri bisa dikerjakan paralel.
Setiap perubahan kontrak = naikkan `schema_version` + update file ini.

---

## 1. Topologi & Transport

```
Sehati (halaman Antropometri) --HTTPS POST /intake (Bearer A)--> Modul Antropometri
                              <-- 200 { assessment_id, url } --
  Sehati simpan assessment_id + buka jendela modul.
  Modul: pre-fill -> kalkulasi lokal + AI (metrik anonim) -> dokter approve -> PDF transien.

  Saat dokter ubah/konfirmasi penyakit kronis di modul:
Modul --HTTPS POST {sehati}/connector/antro/chronic-sync (Bearer B)--> Sehati
                              <-- 200 { synced } --
  Sehati update pasien_penyakit_kronis (pakai KODE kanonik).
```

- **Auth dua arah:**
  - **Token A** (`antro_intake_token`): Sehati → modul `/intake`. Modul yang terbitkan.
  - **Token B** (`sehati_writeback_token`): modul → Sehati `/connector/antro/chronic-sync`. **Sehati** yang terbitkan.
- **Privacy:** identitas pasien TIDAK pernah dikirim ke AI (modul strip; hanya metrik anonim ke AI).
- **Consent:** ringan. Identitas tak ke AI, jadi tak perlu gerbang seketat DermAI. **Penanganan consent = ranah modul** (konsisten keputusan DermAI: consent cloud milik modul).
- **Storage = Opsi A:** Sehati simpan REFERENSI (`assessment_id`) saja; modul simpan laporan (SQLite sendiri). PDF transien (tak dipersist di mana pun).

---

## 2. Endpoints

| Arah | Method | Path | Guna | Auth |
|---|---|---|---|---|
| Sehati→Modul | POST | `{antro_base_url}/intake` | kirim data antropometri → buat assessment, balas url | Bearer A |
| Sehati→Modul | GET | `{antro_base_url}/health` | probe kesiapan (uji paralel) | Bearer A/none |
| Modul→Sehati | POST | `{sehati_base_url}/connector/antro/chronic-sync` | write-back penyakit kronis | Bearer B |
| (Modul internal) | GET | `{antro_base_url}/view/{assessment_id}` | lihat laporan (akses ulang) | sesi modul |

---

## 3. Request `/intake` — `sehati_antro_input` v0.1

```json
{
  "schema_version": "0.1",
  "request_meta": {
    "source_system": "sehati",
    "rm_number": "RM-000123",
    "encounter_id": "4567",
    "assessed_at": "2026-06-27T09:30:00+07:00",
    "idempotency_key": "sehati-antro-4567-v1"
  },
  "actor": { "role": "nurse", "staf_id": "8", "name": "Suster Sari" },
  "patient": {
    "sex": "male",
    "age": 36,
    "dob": "1990-05-01",
    "local_patient_id": "RM-000123"
  },
  "measurements": {
    "height_cm": 170.0,
    "weight_kg": 72.5,
    "waist_cm": 88.0,
    "skinfold_protocol": "JP3_MALE",
    "skinfold_mm": { "site_1": 12.0, "site_2": 18.0, "site_3": 10.0 }
  },
  "chronic": {
    "has_chronic_disease": true,
    "codes": [
      { "kode": 1, "active": true },
      { "kode": 2, "active": true },
      { "kode": "OTHER", "free_text": "Psoriasis", "active": true }
    ]
  },
  "patient_goal": "Turunkan lemak tubuh"
}
```

### 3.1 Field — wajib/opsional

| Field | Tipe | Wajib | Aturan |
|---|---|---|---|
| `schema_version` | string | ✅ | `"0.1"`. |
| `request_meta.rm_number` | string | ✅ | display/link, tidak ke AI. |
| `request_meta.encounter_id` | string | ✅ | id kunjungan/antropometri Sehati. |
| `request_meta.assessed_at` | string ISO8601 | ✅ | offset +07:00. |
| `request_meta.idempotency_key` | string | ⭕ disarankan | retry sama → assessment sama. |
| `actor.role` | enum | ✅ | `doctor`\|`nurse`\|`fo`. **APPROVE hanya `doctor`** (gating di modul). |
| `actor.staf_id` | string | ✅ | id staf. |
| `patient.sex` | enum | ✅ | `male`\|`female`. |
| `patient.age` | int | ✅ | dihitung dari `dob`. |
| `patient.dob` | string date | ⭕ | `YYYY-MM-DD`. |
| `patient.local_patient_id` | string | ⭕ | = rm_number; display only, **tidak ke AI**. |
| `measurements.height_cm` | number | ✅ | cm. |
| `measurements.weight_kg` | number | ✅ | kg. |
| `measurements.waist_cm` | number | ⭕ | cm. |
| `measurements.skinfold_protocol` | enum | ⭕ | `JP3_MALE` (L) / `JP3_FEMALE` (P). |
| `measurements.skinfold_mm.site_1/2/3` | number | ⭕ | **urutan situs perlu dikonfirmasi** (lihat §7 & Open Q). |
| `chronic.has_chronic_disease` | bool | ✅ | ringkasan cepat. |
| `chronic.codes[]` | array | ⭕ | kode kanonik penyakit kronis (lihat §5). Pre-centang checkbox di modul. |
| `patient_goal` | string | ⭕ | tujuan pasien. |

### 3.2 Response `/intake` — 200
```json
{ "schema_version": "0.1", "assessment_id": "asmt_abc123", "url": "https://antro.klinik.local/review/asmt_abc123?...", "status": "created" }
```
Error: pola sama dgn DermAI — 401 `unauthorized`, 400 `bad_request`, 422 `validation_error`, 409 `conflict`, 503 `engine_unavailable`.

---

## 4. Pemetaan Field (Sehati → kontrak) — KOLOM ASLI

| Kontrak | Sumber Sehati | Transform |
|---|---|---|
| `request_meta.rm_number` | `pasien.no_rm` | str |
| `request_meta.encounter_id` | `kunjungan_antropometri.id_antropometri` (atau `id_kunjungan`) | int→str |
| `request_meta.assessed_at` | `kunjungan_antropometri.created_at` / `kunjungan.tgl_kunjungan` | ISO8601 +07:00 |
| `actor.role` | `master_staf.role` | `Dokter/Owner/Admin/Superadmin→doctor`, `Perawat→nurse`, `FO→fo` |
| `patient.sex` | `pasien.jenis_kelamin` (L/P) | **L→male, P→female** |
| `patient.age` | dihitung dari `pasien.tgl_lahir` | tahun |
| `patient.dob` | `pasien.tgl_lahir` | `YYYY-MM-DD` |
| `measurements.height_cm` | `kunjungan_antropometri.tinggi_badan` | float |
| `measurements.weight_kg` | `kunjungan_antropometri.berat_badan` | float |
| `measurements.waist_cm` | `kunjungan_antropometri.lingkar_perut` | float |
| `measurements.skinfold_protocol` | dari sex | L→`JP3_MALE`, P→`JP3_FEMALE` |
| `measurements.skinfold_mm.site_1/2/3` | `kunjungan_antropometri.skinfold_titik_1/2/3` | map sesuai protokol (Open Q) |
| `chronic.codes[]` | `pasien_penyakit_kronis` (via KODE kanonik, lihat §5) | map nama→kode; non-match → `OTHER`+free_text |
| `chronic.has_chronic_disease` | ada `pasien_penyakit_kronis` aktif? | bool |

---

## 5. ⭐ KOSAKATA BERSAMA PENYAKIT KRONIS (shared vocabulary)

**Masalah:** penyakit kronis ada di DUA sisi (Sehati EMR + checkbox modul). Tanpa kode bersama → divergen.
**Solusi (keputusan dr. Hansen):** satu daftar KODE kanonik dipakai kedua modul; slot terakhir `OTHER` = free text.

### 5.1 Sumber kebenaran
- Tabel master BARU di **Sehati**: `master_penyakit_kronis (id, kode, nama, is_active)`. Sehati = master.
- Modul Antropometri **mirror** daftar kode yang sama (sinkron manual/diekspor saat rilis).
- `kode` **stabil** (jangan diubah/dipakai ulang). Tambah penyakit baru = kode baru. `OTHER` selalu kode khusus (lihat di bawah).

### 5.2 Draft daftar (⚠️ dr. Hansen koreksi/tambah/kurangi)
| kode | nama |
|---|---|
| 1 | Diabetes Mellitus |
| 2 | Hipertensi |
| 3 | Penyakit Jantung |
| 4 | Penyakit Ginjal Kronik |
| 5 | Penyakit Hati (Liver) |
| 6 | Asma / PPOK |
| 7 | Gangguan Tiroid |
| 8 | Stroke / Serebrovaskular |
| 9 | Gangguan Makan (Eating Disorder) |
| 10 | Masalah Ortopedik / Sendi |
| **99** | **Lain-lain (free text)** ← slot "id ke-11" |

> Catatan: `OTHER` dipakukan ke **kode 99** (bukan "11") supaya menambah penyakit baru (11, 12, …)
> tidak menggeser slot free-text. Nilai free text disimpan di `free_text`.
> **Open Q:** apakah skrining keselamatan non-penyakit (mis. "nyeri dada") masuk daftar ini atau
> tetap internal modul? (default: hanya penyakit kronis sejati di daftar bersama.)

### 5.3 Perubahan DB Sehati untuk vocab
- Tabel baru `master_penyakit_kronis`.
- `pasien_penyakit_kronis` tambah kolom `kode_penyakit` (int, FK ke master, nullable untuk data lama).
  - `nama_penyakit` (existing) tetap dipakai untuk display & untuk isi `OTHER`.
  - Migrasi data lama: best-effort match nama→kode; tak match → `kode=99` (OTHER), nama tetap.

---

## 6. Write-back Penyakit Kronis (modul → Sehati)

### 6.1 Endpoint Sehati
`POST {sehati_base_url}/connector/antro/chronic-sync` · Header `Authorization: Bearer <sehati_writeback_token>`

```json
{
  "schema_version": "0.1",
  "source": "antropometri",
  "rm_number": "RM-000123",
  "encounter_id": "4567",
  "actor": { "role": "doctor", "staf_id": "5" },
  "chronic_codes": [
    { "kode": 1, "active": true },
    { "kode": 2, "active": false },
    { "kode": "OTHER", "free_text": "Psoriasis", "active": true }
  ]
}
```

### 6.2 Aturan rekonsiliasi (sisi Sehati)
- Identifikasi pasien via `rm_number` (atau `encounter_id`).
- Untuk tiap `kode` (non-OTHER):
  - `active:true` & belum ada baris aktif kode itu → INSERT `pasien_penyakit_kronis(kode_penyakit=kode, nama=master.nama, is_active=1)`.
  - `active:false` → set baris kode itu `is_active=0` (jangan hapus — jejak audit).
- `OTHER`: match by `free_text` (case-insensitive). `active:true` & belum ada → INSERT (`kode=99`, `nama=free_text`). `active:false` → nonaktifkan baris free_text yang cocok.
- **Idempoten:** kirim ulang state yang sama tidak menggandakan.
- **Otorisasi klinis:** write-back hanya diproses bila `actor.role=doctor` (penyakit kronis = data klinis). Non-dokter → 403 (atau diabaikan, simpan ke pending).
- Audit: catat tiap perubahan (siapa, kode, active) di audit log Sehati.

### 6.3 Response
`200 { "synced": true, "applied": <n>, "skipped": <n> }` · error 401/403/422 sesuai pola.

---

## 7. Pemetaan Skinfold (perlu dikonfirmasi 2 sisi)
- Protokol JP3 (3 situs). Urutan situs Sehati `skinfold_titik_1/2/3` harus dipetakan ke situs protokol modul.
- Asumsi handoff: **Pria** dada/perut/paha; **Wanita** trisep/suprailiaka/paha.
- **WAJIB konfirmasi** urutan persis dengan INPUT_DATA_CONTRACT modul sebelum kirim produksi.

---

## 8. Checklist — SISI SEHATI

1. **DB:** tabel `master_penyakit_kronis` (id, kode, nama, is_active) + seed draft §5.2.
2. **DB:** `pasien_penyakit_kronis.kode_penyakit` (int nullable, FK master) + migrasi data lama (match/OTHER).
3. **DB:** `antro_assessment_id` (string nullable) di antropometri/kunjungan.
4. **Service `AntroAIConnector`:** rakit `sehati_antro_input` (sex L→male/P→female, age dari DOB,
   chronic.codes dari pasien_penyakit_kronis) → POST `/intake` (Bearer A) → simpan assessment_id → buka url.
5. **Endpoint write-back** `POST /connector/antro/chronic-sync` (Bearer B) + rekonsiliasi §6.2 + audit.
6. **Config:** `antro_base_url`, `antro_intake_token` (A), `sehati_writeback_token` (B) di `.env`.
7. **UI:** halaman Antropometri (Detail Pasien) form penyakit kronis pakai **checkbox dari master** (bukan free text murni) + "Lain-lain" free text. Tombol "Buat Laporan Komposisi Tubuh (AI)" (kirim role aktor; semua role boleh klik).
8. **Riwayat:** baris "Laporan Komposisi Tubuh — [tgl] — [Lihat]" → buka view modul.

## 9. Checklist — SISI MODUL ANTROPOMETRI

1. **Endpoint `/intake` ber-token** (Bearer A): terima `sehati_antro_input` → buat assessment pre-filled → balas `{assessment_id, url}`. (Pola DermAI.)
2. **Mirror daftar kode penyakit kronis** (§5.2) + pre-centang checkbox dari `chronic.codes`. `OTHER` → tampung sebagai input free text.
3. **Role-aware APPROVE:** terima `actor.role`; non-dokter → tombol approve disabled + endpoint approve TOLAK server-side. Export PDF hanya saat approved.
4. **Pre-fill** sex/age/measurements/skinfold/chronic dari payload; jangan minta ketik ulang.
5. **Write-back chronic:** saat dokter approve/ubah penyakit kronis → POST ke `{sehati}/connector/antro/chronic-sync` (Bearer B) dgn `chronic_codes` final. Kirim hanya saat ada perubahan.
6. **Konfirmasi pemetaan skinfold** (§7) selaras INPUT_DATA_CONTRACT.
7. **PDF transien** (sudah on-demand). **Identitas tak ke AI** (sudah by-design).
8. **Stub `/intake` + `/health`** untuk uji paralel.
9. **Deployment** ikut topologi Sehati (base_url LAN, token A/B dibagikan).

---

## 10. Contoh Write-back (modul → Sehati)
(lihat §6.1) — `OTHER` membawa free_text; `active:false` menonaktifkan, bukan hapus.

---

## 11. Open Questions (perlu disepakati 2 sisi)
1. **Isi daftar penyakit kronis** (§5.2) — dr. Hansen finalisasi (tambah/kurangi/ubah nama).
2. **Skrining non-penyakit** (nyeri dada, dll) — masuk daftar bersama atau internal modul? (default: internal modul).
3. **Urutan skinfold** Sehati titik_1/2/3 ↔ situs JP3 (§7).
4. **Identifikasi write-back:** pakai `rm_number` atau `encounter_id` sebagai kunci utama?
5. **Otorisasi write-back non-dokter:** tolak (403) atau simpan pending? (default: tolak).
6. **`url` lifetime / auth** untuk WebView mulus (sama seperti DermAI Open Q).

---
*Perubahan kontrak dicatat di sini + decisions_log Sehati. Naikkan schema_version untuk perubahan breaking.*
