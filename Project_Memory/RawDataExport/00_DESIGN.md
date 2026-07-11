# Sehati Clinic — Owner Raw Data Export Plan (C2) — REVISED

**Status:** ✅ APPROVED — ready for Phase C2.1 implementation (5 Juni 2026)
**Owner:** dr. Hansen Sudarma (Owner role only — bukan Superadmin/Admin)
**Konteks:** Feeder ke modul Data Analyst (proyek terpisah) → Council AI (proyek Codex)
**Date:** 5 Juni 2026 (Revisi 1)
**Reference:** OpenAI prompt + dr. Hansen revision feedback 5 Juni 2026

---

## 0. Apa yang berubah dari Revisi 0

| Perubahan | Sebelumnya | Sekarang |
|-----------|------------|----------|
| Role gate | Owner + Superadmin | **Owner ONLY** (MVP, lebih ketat) |
| Main UX | 11 dataset cards, click satu-satu | **Export Pack one-click** (Weekly / Monthly / Custom → ZIP) |
| Per-dataset endpoint | Main flow | **Advanced/internal helper** (optional, untuk debugging atau pull spesifik) |
| Tier 3 (SOAP + audit) | Double-confirm modal | **No modal** — Owner-only sudah cukup gate |
| Tier 3 di pack | Modal warning per dataset | **Auto-include di pack** (no friction untuk Owner) |
| mask_pii UI | Tier-specific warning | **Single checkbox global** di main flow |
| Hard cap | Strict 100K/dataset | **Adaptive** — kalau over, suggest split range (tidak block) |
| Data dictionary | Separate access | **Auto-include di setiap ZIP pack** (self-contained) |

---

## 1. Prinsip (Refined)

1. **eMR-POS = source of truth** — operational data, bukan AI insight
2. **Export raw/semi-raw**, bukan opini atau analisis
3. **One-click experience** — Owner workflow priority: Weekly / Monthly export. Klik 1 tombol, dapat ZIP berisi semua dataset.
4. **CSV + JSON keduanya** — Owner pilih format saat klik export (CSV default)
5. **Data dictionary self-contained** — ter-bundle di setiap ZIP pack supaya Council AI tidak perlu fetch separate
6. **Audit trail wajib** — 1 entry per Pack Export event (bukan per dataset)
7. **Owner-only di MVP** — Admin/Superadmin extension defer ke Phase berikutnya
8. **mask_pii opt-in** — default OFF (Owner pakai sendiri). Checkbox aktif kalau export untuk AI/3rd party.
9. **Adaptive hard cap** — soft warning kalau range besar, tidak block. Future: chunking auto-split.
10. **Jangan ganggu Owner dengan modal** — Tier 3 (clinical/audit) tetap include di pack tanpa friction. Audit log catat sensitivitas.

---

## 2. Arsitektur Revisi

```
Browser (Owner)
    ↓ GET /web/export                        ← landing dengan 3 BIG buttons
    ↓ klik "Weekly Pack" atau "Monthly Pack" atau "Custom..."
    ↓
    [Weekly/Monthly: instant download dengan default range]
    [Custom: form pendek (tgl_dari, tgl_sampai, mask_pii) → submit → download]
    ↓
    ↓ GET /web/export/pack/{period}.zip?format=csv&mask_pii=false
    ↓ StreamingResponse (ZIP file generated server-side)
    ↓ Browser save: sehati_pack_{period}_{tgl_dari}_to_{tgl_sampai}_{ts}.zip
```

**ZIP contents:**
```
sehati_pack_weekly_2026-05-29_to_2026-06-05_20260605T1430.zip
├── README.txt                              ← human-readable header (filter, generated, row counts)
├── DATA_DICTIONARY.md                       ← copy dari Project_Memory (self-contained)
├── 01_daily_operational_summary.csv
├── 02_visits_raw.csv
├── 03_medical_soap_raw.csv                  ← Tier 3, include di MVP owner-only
├── 04_treatments_raw.csv
├── 05_products_prescription_sales_raw.csv
├── 06_transactions_header_raw.csv
├── 07_transactions_detail_raw.csv
├── 08_inventory_movements_raw.csv
├── 09_purchasing_orders_header_raw.csv
├── 10_purchasing_orders_item_raw.csv
├── 11_purchasing_orders_receive_raw.csv
├── 12_staff_activity_raw.csv                ← Tier 3 Mode A (no data snapshots di pack)
└── 13_membership_raw.csv
```

**13 file** total (11 dataset, PO di-split 3, semua include).
Format file = pilihan format di main flow (.csv atau .json).

**Module structure:**
```
app/
├── services/
│   └── export_service.py             ← ExportService:
│                                         - 11 dataset method (internal, reusable)
│                                         - generate_pack(period, ..., format, mask_pii)
│                                         - audit hook _audit_export_pack(actor, period, range, file_count, row_total)
├── web/
│   ├── routes/
│   │   └── export.py                 ← Routes:
│   │                                     - GET /web/export (landing)
│   │                                     - GET /web/export/pack/weekly.zip
│   │                                     - GET /web/export/pack/monthly.zip
│   │                                     - GET /web/export/pack/custom.zip
│   │                                     - GET /web/export/dictionary.{json,md}
│   │                                     - [advanced] GET /web/export/{dataset}/download.{csv,json}
│   └── templates/
│       └── export_landing.html        ← Simple: 3 big buttons + format + mask_pii
└── core/
    ├── csv_writer.py                  ← dict_list_to_csv_bytes()
    ├── json_writer.py                 ← dict_list_to_json_bytes()
    └── zip_packer.py                  ← ZipPacker class — stream-append file ke ZIP
```

**Audit integration (revised):**
- 1 entry per pack export: `aksi="EXPORT_PACK"`, `keterangan=f"period={period}, range={Y}..{Z}, format={fmt}, files={N}, total_rows={M}, mask_pii={bool}"`
- Per-dataset advanced endpoint masih log: `aksi="EXPORT_DATASET"` (untuk audit forensic kalau Owner pull dataset spesifik di luar pack)
- Tidak include actual exported data ke audit (size + PII)

---

## 3. Privacy Tiers (Simplified)

Karena role gate = Owner-only, privacy concern lebih relax untuk in-clinic export. Tetap tracked supaya kalau future expand ke Admin, mudah enable per-tier.

| Tier | Datasets | Tier 3 Special? |
|------|----------|-----------------|
| 🟢 Tier 1 Aggregate | daily_operational_summary | No |
| 🟡 Tier 2 Operational | visits, treatments, products, transactions header/detail, inventory, PO header/item/receive, membership | No |
| 🔴 Tier 3 Sensitive | medical_soap_raw, staff_activity_raw | Auto-include di pack tanpa modal (Owner-only sudah cukup gate) |

**Mode B (data_lama/data_baru di staff_activity_raw):**
- **TIDAK di pack** default (avoid PII spillover ke setiap weekly export)
- **Available via advanced endpoint** dengan flag: `GET /web/export/staff-activity-raw/download.csv?include_snapshots=true`
- No modal, Owner-only juga sudah cukup gate
- Audit log catat flag `WITH_SNAPSHOT` di keterangan

**Pseudonymization (mask_pii):**
- Checkbox di main flow (default OFF)
- Affects: `nama_pasien`, `nomor_ktp`, `alamat`, `nomor_hp` → hash atau `(redacted)`
- Tidak affect: `id_pasien` (perlu untuk JOIN antar dataset)
- Hint text di UI: *"Centang kalau ZIP akan dikirim ke AI atau pihak luar"*

---

## 4. UI Design (Simplified)

### Main flow — `GET /web/export`

```
┌──────────────────────────────────────────────────────────┐
│ 📥 Owner Raw Data Export                                 │
│ Generate paket lengkap untuk modul Data Analyst /        │
│ Council AI.                                              │
│                                                          │
│ Format:  ⦿ CSV ZIP    ○ JSON ZIP                        │
│ ☐ Mask PII (centang kalau ZIP dikirim ke AI/3rd party)   │
│                                                          │
│ ┌──────────────────────────────────────────────────┐    │
│ │ 📊 Weekly Pack (7 hari)                          │    │
│ │ Akhir periode: [2026-06-05]  ← default today     │    │
│ │ Preview range: 2026-05-29 → 2026-06-05           │    │
│ │ [↓ Download .zip]                                │    │
│ └──────────────────────────────────────────────────┘    │
│                                                          │
│ ┌──────────────────────────────────────────────────┐    │
│ │ 📅 Monthly Pack (30 hari)                        │    │
│ │ Akhir periode: [2026-06-05]  ← default today     │    │
│ │ Preview range: 2026-05-06 → 2026-06-05           │    │
│ │ [↓ Download .zip]                                │    │
│ └──────────────────────────────────────────────────┘    │
│                                                          │
│ ┌──────────────────────────────────────────────────┐    │
│ │ 🛠 Custom Range                                  │    │
│ │ Dari: [_______]   Sampai: [_______]              │    │
│ │ [↓ Download .zip]                                │    │
│ └──────────────────────────────────────────────────┘    │
│                                                          │
│ ── ADVANCED (per-dataset, internal) ──                  │
│ <details>                                                │
│ Klik untuk akses per-dataset endpoint (debug/spesifik).  │
│ [collapsed list 11 dataset link dengan filter masing]    │
│ </details>                                               │
└──────────────────────────────────────────────────────────┘
```

**Anchor date behavior:**
- Setiap card Weekly/Monthly punya 1 field `Akhir periode` (default = today)
- JS auto-update "Preview range" saat field berubah → owner langsung lihat rentang yang akan di-export
- Klik Download = submit dengan `ending_date` param + N hari subtraksi di server
- Contoh use case: Bapak klik 5 Juni mau export "Weekly minggu lalu" → ubah field ke `2026-05-29` → preview update jadi `2026-05-23 → 2026-05-29` → klik Download
- Contoh use case: Bapak akhir bulan mau "Monthly April" → ubah ke `2026-04-30` → preview `2026-04-01 → 2026-04-30` → klik Download

**Custom range:**
- Form full freedom untuk arbitrary range (lebih dari 30 hari, atau range non-rolling)
- Sama behavior dengan Weekly/Monthly setelah submit

Kalau range > 90 hari, tampilkan **warning soft** (tidak block):
> ⚠ Range > 90 hari (estimasi total rows ~XXX). Generate akan lambat (~30s) dan file ZIP besar. Lanjut?

Owner pilih "Lanjut" atau "Cancel dan split range".

### Endpoint

| URL | Action |
|-----|--------|
| `GET /web/export` | Render landing |
| `GET /web/export/pack/weekly.zip?ending_date=YYYY-MM-DD&format=csv&mask_pii=false` | Weekly ZIP. `ending_date` optional (default today). Range = ending_date - 7 sampai ending_date |
| `GET /web/export/pack/monthly.zip?ending_date=YYYY-MM-DD&format=csv&mask_pii=false` | Monthly ZIP. Sama pattern dengan weekly tapi - 30 hari |
| `GET /web/export/pack/custom.zip?tgl_dari=...&tgl_sampai=...&format=csv&mask_pii=false` | Custom range ZIP (full freedom) |
| `GET /web/export/dictionary.md` | Render data dictionary HTML |
| `GET /web/export/dictionary.json` | Programmatic access untuk Council AI |
| `GET /web/export/{dataset_name}/download.{csv\|json}?filters...` | **Advanced** — single dataset |

**Filename convention:**
- Pack: `sehati_pack_{period}_{tgl_dari}_to_{tgl_sampai}_{ts}.zip`
- Single: `sehati_{dataset}_{tgl_dari}_to_{tgl_sampai}_{ts}.{csv,json}`

---

## 5. Per-Dataset Spec

(11 dataset, 13 file di pack karena PO split 3)

> Spec detail per dataset tetap sama dengan Revisi 0 (Section 5 di doc lama).
> Yang berubah: semua dataset auto-include di pack tanpa user pilih.
> Per-dataset endpoint masih ada sebagai advanced/internal — tidak hilang.

| # | Dataset | Privacy | Difficulty | Di Pack | Advanced endpoint |
|---|---------|---------|------------|---------|-------------------|
| 01 | daily_operational_summary | 🟢 Tier 1 | MEDIUM | ✅ | ✅ |
| 02 | visits_raw | 🟡 Tier 2 | EASY | ✅ | ✅ |
| 03 | medical_soap_raw | 🔴 Tier 3 | EASY | ✅ (no modal) | ✅ |
| 04 | treatments_raw | 🟡 Tier 2 | EASY | ✅ | ✅ |
| 05 | products_prescription_sales_raw | 🟡 Tier 2 | EASY | ✅ | ✅ |
| 06 | transactions_header_raw | 🟡 Tier 2 | EASY | ✅ | ✅ |
| 07 | transactions_detail_raw | 🟡 Tier 2 | EASY | ✅ | ✅ |
| 08 | inventory_movements_raw | 🟡 Tier 2 | MEDIUM | ✅ | ✅ |
| 09 | purchasing_orders_header_raw | 🟡 Tier 2 | MEDIUM | ✅ | ✅ |
| 10 | purchasing_orders_item_raw | 🟡 Tier 2 | MEDIUM | ✅ | ✅ |
| 11 | purchasing_orders_receive_raw | 🟡 Tier 2 | MEDIUM | ✅ | ✅ |
| 12 | staff_activity_raw (Mode A) | 🔴 Tier 3 | EASY | ✅ (no snapshot) | ✅ + `?include_snapshots=true` Mode B |
| 13 | membership_raw | 🟡 Tier 2 | EASY | ✅ | ✅ |

**Detail kolom + filter per dataset:** lihat lampiran Section 5 Revisi 0 (atau pindah ke `01_DATA_DICTIONARY.md` saat C2.4).

---

## 6. Implementation Roadmap (Revised)

**C2.1 Foundation** (1 sesi, ~2 jam)
- Folder + design doc Revisi 1 (✅ ini)
- `app/core/csv_writer.py` — `dict_list_to_csv_bytes(items, columns)`
- `app/core/json_writer.py` — `dict_list_to_json_bytes(items)`
- `app/core/zip_packer.py` — `ZipPacker` class:
  - `add_file(filename, bytes)` — append ke in-memory ZIP
  - `add_readme(metadata)` — auto README.txt
  - `add_data_dictionary()` — copy DATA_DICTIONARY.md
  - `finalize() -> bytes`
- `app/services/export_service.py` skeleton dengan placeholder method
- `app/web/routes/export.py`:
  - GET /web/export landing
  - GET /web/export/dictionary.{md,json} stub
- `export_landing.html` template (3 big buttons)
- `MENU_EXPORT` baru → gate `require_owner_only`
- Helper `require_owner_only(user)` di `_shared.py`
- Verify health check

**C2.2 Tier 1+2 datasets (11 datasets in service)** — 2-3 sesi
- 11 dataset method di `ExportService` (semua tier, satu per satu)
- Urutan simple-to-complex: daily_summary → visits → treatments → products → trx_header → trx_detail → inventory → PO 3-way → membership → soap → audit
- Per-dataset advanced endpoint untuk testing
- Audit log entry per dataset endpoint (untuk advanced flow)

**C2.3 Pack endpoint (Weekly/Monthly/Custom)** — 1 sesi
- `ExportService.generate_pack(period, ..., format, mask_pii)`
- 3 endpoint pack: weekly, monthly, custom
- ZIP generation dengan ZipPacker
- README.txt auto-generate dengan metadata + row counts
- Audit hook `_audit_export_pack`
- Soft warning untuk range > 90 hari (return HTML preview dulu kalau range besar, lalu owner confirm)

**C2.4 Data Dictionary** — 1 sesi
- `Project_Memory/RawDataExport/01_DATA_DICTIONARY.md` — full schema per dataset
- Sample row JSON per dataset
- Endpoint `GET /web/export/dictionary.json` — return parsed dict (Council AI auto-discovery)
- Bundle DATA_DICTIONARY.md ke setiap ZIP pack

**C2.5 Verify + housekeeping** — 1 sesi
- Manual test 3 pack types (weekly, monthly, custom)
- Open ZIP, validate CSV/JSON parse-able
- Validate README + DATA_DICTIONARY included
- Health check post-deploy
- DEC-046 (Export Pack module)
- Update roadmap + Project Memory README magic command words ("export weekly", "export monthly", "export custom dari X sampai Y")

**Total estimasi:** 5-6 sesi (~12 jam)

---

## 7. Risks & Mitigations (Revised)

| Risk | Severity | Mitigation |
|------|----------|-----------|
| ZIP generation OOM untuk pack besar | HIGH | StreamingResponse + in-memory ZIP cap di RAM. Kalau row total > 200K, suggest split range |
| PII leak ke Council AI external | CRITICAL | mask_pii checkbox prominent di UI. Hint text wajib. Default OFF karena owner-self default. |
| Pack default include Tier 3 (SOAP + audit) | (intended) | Owner-only gate sudah cukup. Audit log catat. |
| File CSV parse error (newline in TEXT) | MEDIUM | `csv.QUOTE_ALL` + escape proper |
| Pack download takes too long → browser timeout | MEDIUM | StreamingResponse keep connection alive. Untuk pack besar, owner pakai Custom dengan range lebih kecil. |
| ZIP file size > 100MB | MEDIUM | Soft warning di UI kalau row total prediksi tinggi. Suggest split. |
| Data dictionary out-of-sync dengan schema | MEDIUM | Health check tambah BE-09: cek schema vs dictionary alignment (Phase berikutnya) |

---

## 8. Estimated Effort

| Phase | Effort | Output |
|-------|--------|--------|
| C2.1 Foundation | 1 sesi (~2 jam) | Skeleton + CSV/JSON/ZIP helpers + landing UI |
| C2.2 11 Datasets | 2-3 sesi (~6 jam) | 11 dataset method + advanced per-dataset endpoint |
| C2.3 Pack endpoint | 1 sesi (~2 jam) | Weekly/Monthly/Custom pack + ZIP gen + audit |
| C2.4 Data Dictionary | 1 sesi (~2 jam) | MD + JSON endpoint + auto-bundle |
| C2.5 Verify + housekeeping | 1 sesi (~1 jam) | Health check + DEC + Project Memory |
| **Total** | **5-6 sesi (~13 jam)** | **Production-ready Owner Export Pack** |

(Total sama dengan Revisi 0 — UX disederhanakan tapi tetap ada 11 dataset + advanced endpoint untuk forward-compat.)

---

## 9. Approved Decisions (dr. Hansen — 5 Juni 2026, Revisi 1)

| # | Topic | Decision |
|---|-------|----------|
| 1 | Role gate | **Owner ONLY** (MVP). Superadmin/Admin defer ke Phase berikutnya. |
| 2 | `mask_pii` default | **OFF + checkbox global**. Hint text di UI: "Centang kalau ZIP dikirim ke AI/3rd party". |
| 3 | Format export | **CSV + JSON** keduanya. Owner toggle di main flow. |
| 4 | Main UX | **Export Pack one-click**: Weekly / Monthly / Custom → ZIP. |
| 5 | Tier 3 (SOAP + audit) | **Auto-include di pack tanpa modal**. Owner-only gate cukup. |
| 6 | Audit Mode B | Tidak di pack default. **Tersedia via advanced endpoint** dengan `?include_snapshots=true`. No modal. |
| 7 | Per-dataset endpoint | **Advanced/internal**, tetap ada tapi bukan main flow. Untuk debugging atau pull spesifik. |
| 8 | PO dataset | **Split 3 file** (header/item/receive) di dalam pack. |
| 9 | Hard cap | **Adaptive** — soft warning untuk range > 90 hari, tidak block. Future: chunking. |
| 10 | Data Dictionary | **Auto-include di setiap ZIP pack** (self-contained untuk Council AI). |
| 11 | Implementation order | Simple-to-complex (sesuai usulan): daily_summary → ... → soap → audit. |
| 12 | Weekly pack range | **7 hari terakhir rolling** (today - 7 sampai today). Konsisten klik kapanpun. |
| 13 | Monthly pack range | **30 hari terakhir rolling** (today - 30 sampai today). Symmetric dengan Weekly. |
| 14 | Soft warning threshold | **> 90 hari** range → tampil warning soft (tidak block). Balance untuk quarterly pack. |
| 15 | Weekly/Monthly anchor date | **Optional `ending_date` field** di setiap card (default today). Owner override untuk historical export. JS preview range auto-update. |

---

## 10. Final Validated — Ready for C2.1

Semua 14 keputusan (Section 9) sudah locked oleh dr. Hansen pada 5 Juni 2026.

**Scope freeze:**
- Tidak ada implementasi tanpa notifikasi perubahan scope explisit
- DEC-046 akan dibuat saat C2.5 housekeeping
- Project_Memory/00_README.md akan di-update dengan magic command words baru saat C2.5

**Trigger kalimat dari dr. Hansen untuk mulai:**
- "mulai C2.1" atau "lanjut C2 foundation" → AI mulai Phase C2.1 Foundation
- "mulai semua C2" → AI mulai sekuensial C2.1 → C2.5 (lebih panjang, 5-6 sesi)
- "tunda C2, mulai B" → defer C2, switch ke Soft Launch Prep

**Next checkpoint:** Phase C2.1 selesai = skeleton + landing UI + ZIP helper jalan, smoke test pass, belum ada dataset live. Bapak verify struktur sebelum lanjut C2.2.

---

## 11. Revision Log

- **2026-06-05 Revisi 0** — Initial design draft (Hansen + Claude). 11 dataset cards. Owner+Superadmin.
- **2026-06-05 Revisi 1** — User feedback restructure: Owner ONLY, Export Pack one-click main flow, per-dataset jadi advanced, hapus modal Tier 3.
- **2026-06-05 Revisi 1 FINAL APPROVED** — 14 keputusan locked. Weekly/Monthly = 7/30 hari rolling. Warning threshold = > 90 hari.
- **2026-06-05 Revisi 1.1 FINAL APPROVED** — Tambah keputusan #15: anchor date selector di Weekly/Monthly card untuk historical export. Ready for C2.1.
