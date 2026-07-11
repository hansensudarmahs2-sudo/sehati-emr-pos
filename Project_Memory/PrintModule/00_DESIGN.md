# Sehati Clinic — Print Module Design

**Status:** 🟡 DESIGN — pending dr. Hansen final approval
**Owner:** dr. Hansen Sudarma
**Konteks:** Wajib untuk soft launch — kasir butuh cetak nota pembayaran, dokter butuh cetak resume medis (SOAP). User caught hal ini tepat sebelum mulai Phase B.
**Date:** 5 Juni 2026

---

## 0. Tujuan

Sediakan **2 jenis dokumen ready-to-print** untuk Sehati Clinic:
1. **Nota Kasir** — bukti pembayaran transaksi (rincian item + total + metode bayar)
2. **Resume Medis SOAP** — ringkasan konsul dokter (anamnesa + pemeriksaan + diagnosa + saran)

Dengan format yang **editable oleh Owner** (logo, nama klinik, alamat, no HP), **support 2 paper size** (thermal 80mm untuk kasir + A5 standar untuk MR), dan **audit-tracked** setiap kali dicetak.

---

## 1. Prinsip

1. **Browser-side HTML print** — pakai `window.print()` + CSS `@media print`, no PDF library
2. **Owner editable** — form sederhana untuk klinik info + logo upload
3. **Audit setiap cetak** — `aksi="PRINT_NOTA"` atau `aksi="PRINT_SOAP"` di audit_log
4. **Role gate ketat** — Nota: Kasir/Owner/Admin/Superadmin; SOAP: Dokter/Owner/Admin/Superadmin
5. **Always re-render** — tidak simpan HTML snapshot, regen dari current klinik config
6. **2 paper format** — thermal 80mm + A5 reguler, owner pilih default per dokumen
7. **Jangan ubah business logic existing** — print = read-only operation di atas data yang sudah ada
8. **Tidak install library tambahan** — pakai built-in browser print + Jinja2 templates

---

## 2. 7 Keputusan Locked (5 Juni 2026)

| # | Topic | Decision |
|---|-------|----------|
| 1 | Print strategy | **Path A — Browser HTML print** (`window.print()` + CSS @media print) |
| 2 | Scope MVP | **Nota Kasir + Resume Medis SOAP** (2 jenis dokumen) |
| 3 | Format editor | **Form fields sederhana** (no WYSIWYG / no template editor raw) |
| 4 | Role gate | **Standard**: Nota = Kasir+Owner+Admin+Superadmin; SOAP = Dokter+Owner+Admin+Superadmin |
| 5 | Paper size | **Kedua format** — thermal 80mm + A5 reguler. Owner pilih default per dokumen di Settings. |
| 6 | Logo upload | **File ke disk** — `sehati_clinic/static/uploads/logo.{png,jpg}`. Max 500KB. |
| 7 | Snapshot policy | **Always re-render** dari current `master_klinik_config`. No snapshot column. |

---

## 3. Arsitektur

```
Browser (Kasir/Dokter/Owner/Admin)
    ↓ GET /web/kasir/transaksi/{id}/cetak-nota?paper=a5
    ↓ atau GET /web/dokter/soap/{id_pemeriksaan}/cetak?paper=a5
    ↓
Server:
    1. Auth check (role gate)
    2. Fetch transaksi/SOAP data
    3. Fetch master_klinik_config (logo + alamat + dll)
    4. Render Jinja2 template (nota_{a5|thermal}.html atau soap_{a5|thermal}.html)
    5. Audit log entry (PRINT_NOTA atau PRINT_SOAP)
    6. Return HTML response dengan CSS @media print
    ↓
Browser:
    7. Page load auto-trigger window.print() (after a small delay)
    8. User pilih printer di OS dialog → cetak
    9. Optional: user pakai Ctrl+P untuk re-cetak tanpa reload
```

### Modul structure

```
sehati_clinic/
├── app/
│   ├── db/
│   │   └── models/
│   │       └── klinik_config.py             ← MasterKlinikConfig (singleton row)
│   ├── services/
│   │   ├── klinik_config_service.py         ← get_or_create + update_with_audit
│   │   └── print_service.py                 ← prepare_nota_context() + prepare_soap_context()
│   ├── web/
│   │   ├── routes/
│   │   │   ├── settings.py                  ← /web/settings/klinik (Owner only)
│   │   │   ├── kasir.py                     ← extend dengan /transaksi/{id}/cetak-nota
│   │   │   └── dokter.py                    ← extend dengan /soap/{id}/cetak
│   │   └── templates/
│   │       ├── settings_klinik.html         ← form edit klinik config (Owner)
│   │       ├── print/
│   │       │   ├── nota_a5.html             ← layout A5 (full-page)
│   │       │   ├── nota_thermal.html        ← layout 80mm (single column)
│   │       │   ├── soap_a5.html             ← layout A5 (full-page MR)
│   │       │   ├── soap_thermal.html        ← layout 80mm (compact)
│   │       │   └── _print_base.html         ← shared CSS + auto-print JS
└── migrations/sql/
    └── 007_klinik_config.sql                ← CREATE TABLE master_klinik_config
```

---

## 4. Schema Database

### `master_klinik_config` (singleton — selalu 1 row dengan id_config=1)

| Kolom | Tipe | Default | Description |
|-------|------|---------|-------------|
| id_config | INT PK | 1 | Hardcoded 1 (singleton enforcement) |
| nama_klinik | VARCHAR(100) | "Sehati Clinic" | Nama klinik untuk header nota/SOAP |
| alamat_baris1 | VARCHAR(150) | NULL | Alamat line 1 |
| alamat_baris2 | VARCHAR(150) | NULL | Alamat line 2 |
| alamat_baris3 | VARCHAR(150) | NULL | Alamat line 3 (kelurahan/kecamatan) |
| no_telepon | VARCHAR(50) | NULL | Nomor telepon klinik (kontak) |
| no_whatsapp | VARCHAR(50) | NULL | Nomor WhatsApp (opsional) |
| email | VARCHAR(100) | NULL | Email klinik |
| website | VARCHAR(200) | NULL | URL website (opsional) |
| logo_path | VARCHAR(200) | NULL | Path relatif ke logo (e.g., `uploads/logo.png`) |
| footer_text | TEXT | NULL | Pesan footer ("Terima kasih, semoga lekas sembuh") |
| default_paper_nota | VARCHAR(20) | "a5" | "a5" atau "thermal" — default paper untuk nota |
| default_paper_soap | VARCHAR(20) | "a5" | "a5" atau "thermal" — default paper untuk SOAP |
| ttd_dokter_text | VARCHAR(100) | NULL | Optional sign-off untuk SOAP ("Dokter Pemeriksa,") |
| created_at | TIMESTAMP | NOW() | |
| updated_at | TIMESTAMP | NOW() ON UPDATE NOW() | |
| id_staf_last_edit | INT FK master_staf | NULL | Audit: siapa terakhir edit |

**Migration:** `migrations/sql/007_klinik_config.sql`
- CREATE TABLE + INSERT row default (id_config=1, nama_klinik="Sehati Clinic")
- CHECK constraint: id_config = 1 (force singleton)

### Tidak ada perubahan ke tabel existing

`transaksi_kasir` + `pemeriksaan_klinis` tetap apa adanya. Print = read-only.

---

## 5. Endpoints

### Settings (Owner-only)

| URL | Method | Role | Action |
|-----|--------|------|--------|
| `/web/settings/klinik` | GET | Owner+Superadmin | Render form edit klinik config |
| `/web/settings/klinik` | POST | Owner+Superadmin | Submit form → update + audit |
| `/web/settings/klinik/logo` | POST | Owner+Superadmin | Upload logo file (PNG/JPG) → save to disk |

### Print Nota (Kasir scope)

| URL | Method | Role | Action |
|-----|--------|------|--------|
| `/web/kasir/transaksi/{id}/cetak-nota` | GET | KASIR_ROLES | Render nota HTML auto-print |

Query params:
- `?paper=a5` atau `?paper=thermal` (default: dari `master_klinik_config.default_paper_nota`)
- `?autoprint=false` opt-out dari auto window.print() (untuk preview)

### Print SOAP (Dokter scope)

| URL | Method | Role | Action |
|-----|--------|------|--------|
| `/web/dokter/soap/{id_pemeriksaan}/cetak` | GET | DOKTER_ANTRIAN_ROLES | Render SOAP HTML auto-print |

Query params sama dengan nota.

---

## 6. Template Design

### `_print_base.html` (shared CSS + JS)

```css
@media print {
    body { margin: 0; }
    .no-print { display: none; }
    @page { size: A5; margin: 10mm; }     /* A5 default */
    @page :thermal { size: 80mm auto; margin: 2mm; }  /* thermal */
}
```

JS auto-print:
```js
window.addEventListener('load', function() {
    if (new URLSearchParams(location.search).get('autoprint') !== 'false') {
        setTimeout(() => window.print(), 500);  // delay supaya CSS loaded
    }
});
```

### Nota A5 layout (full-page)

```
┌──────────────────────────────────────┐
│  [LOGO]   Sehati Clinic               │
│           Jl. Sudirman No. 123        │
│           Jakarta Selatan             │
│           Telp: 021-xxx               │
├──────────────────────────────────────┤
│  NOTA PEMBAYARAN                     │
│  No. Transaksi: #1234                 │
│  Tanggal: 5 Juni 2026 15:30           │
│  Kasir: Hansen                        │
│  Pasien: Megita (J06296)              │
├──────────────────────────────────────┤
│  ITEM                    QTY   HARGA  │
│  Konsultasi Kulit         1   150.000 │
│  Doxicor                 20   180.000 │
│  Cream N                  1   150.000 │
├──────────────────────────────────────┤
│                  Subtotal:    480.000 │
│                  Diskon:        0.000 │
│                  TOTAL:       480.000 │
├──────────────────────────────────────┤
│  Pembayaran: CASH                     │
│  Diterima:  500.000                   │
│  Kembali:    20.000                   │
├──────────────────────────────────────┤
│  Terima kasih, semoga lekas sembuh    │
│  [footer text dari config]            │
└──────────────────────────────────────┘
```

### Nota Thermal 80mm layout (single column monospace)

```
================================
       SEHATI CLINIC
   Jl. Sudirman No. 123
     Jakarta Selatan
       021-xxx
================================
NOTA #1234
5 Jun 2026 15:30
Kasir: Hansen
Pasien: Megita (J06296)
--------------------------------
Konsultasi Kulit
  1 x 150.000        150.000
Doxicor
 20 x   9.000        180.000
Cream N
  1 x 150.000        150.000
--------------------------------
Subtotal:           480.000
Diskon:                   0
TOTAL:              480.000
--------------------------------
CASH:               500.000
Kembali:             20.000
================================
Terima kasih
================================
```

### SOAP A5 layout

```
┌────────────────────────────────────────┐
│  [LOGO]   Sehati Clinic                │
│           Alamat...                    │
├────────────────────────────────────────┤
│  RESUME MEDIS                          │
│  No. RM: J06296                        │
│  Nama Pasien: Megita Pramanda Putri    │
│  Tgl Lahir / Usia: ... / ...           │
│  Tgl Kunjungan: 5 Juni 2026            │
│  Dokter: dr. Hansen Sudarma            │
├────────────────────────────────────────┤
│  KELUHAN UTAMA                         │
│  Jerawat parah di wajah ...            │
├────────────────────────────────────────┤
│  ANAMNESA (S)                          │
│  ...                                   │
├────────────────────────────────────────┤
│  PEMERIKSAAN FISIK (O)                 │
│  ...                                   │
├────────────────────────────────────────┤
│  DIAGNOSA (A)                          │
│  ...                                   │
├────────────────────────────────────────┤
│  TINDAKAN YANG DILAKUKAN               │
│  - Basic Treatment                     │
│  - Konsultasi Kulit                    │
├────────────────────────────────────────┤
│  RESEP                                 │
│  - Doxicor 20 tablet                   │
│  - Cream N 1 pcs                       │
├────────────────────────────────────────┤
│  SARAN                                 │
│  ...                                   │
├────────────────────────────────────────┤
│                                        │
│                  Dokter Pemeriksa,     │
│                                        │
│                  dr. Hansen Sudarma    │
└────────────────────────────────────────┘
```

### SOAP Thermal layout

Compact single-column version dengan section divider `--------`. Practical untuk patient handout kasar tapi readable.

---

## 7. UI Flow

### Owner: Setup Klinik Info

1. Login Owner → menu **Settings → Profil Klinik**
2. Form fields: nama klinik, alamat (3 line), telp, WA, email, website, footer text
3. Upload logo (PNG/JPG max 500KB)
4. Pilih default paper untuk nota + SOAP (radio: A5 / Thermal)
5. Klik **Simpan** → update + audit + flash "Konfigurasi diperbarui"

### Kasir: Cetak Nota setelah Bayar

1. Login Kasir → halaman detail tagihan setelah pembayaran sukses
2. Tampil button **🖨 Cetak Nota** (di samping button Selesai/Back)
3. Klik → buka tab baru `/web/kasir/transaksi/{id}/cetak-nota`
4. Page load → CSS @media print apply → setTimeout(window.print, 500)
5. Print dialog OS muncul → pilih printer → cetak
6. Optional: button kecil "🖨 Print Ulang" di pojok atas page (kalau user batal cetak)

### Dokter: Cetak Resume Medis dari SOAP

1. Login Dokter → halaman SOAP (input atau view)
2. Setelah SOAP saved, tampil button **🖨 Cetak Resume**
3. Klik → buka tab baru `/web/dokter/soap/{id_pemeriksaan}/cetak`
4. Page auto-print dialog seperti nota

### Owner / Admin override

Owner + Admin + Superadmin bisa juga akses URL print langsung (untuk reprint atau backup print). Tidak perlu button khusus di UI kalau Bapak biasanya pakai role spesifik.

---

## 8. Implementation Roadmap

**Phase P1.1 — Schema + KlinikConfig service** (~1 sesi, 1.5 jam):
- Migration `007_klinik_config.sql`
- Model `MasterKlinikConfig`
- `KlinikConfigService.get()` + `update_with_audit()`
- Helper untuk logo upload + validation

**Phase P1.2 — Settings UI** (~1 sesi, 1.5 jam):
- Route `/web/settings/klinik` GET + POST
- Template `settings_klinik.html` dengan form fields + upload + preview logo
- Menu group "Settings" baru di sidebar (Owner+Superadmin only)
- Test create → edit → reload, persist OK

**Phase P1.3 — Nota templates + Kasir route** (~1 sesi, 1.5 jam):
- `_print_base.html` shared CSS + auto-print JS
- `nota_a5.html` + `nota_thermal.html` templates
- Route `/web/kasir/transaksi/{id}/cetak-nota` dengan `paper` param
- `PrintService.prepare_nota_context()` (fetch transaksi + items + config)
- Button "🖨 Cetak Nota" di Kasir detail tagihan page
- Audit log `PRINT_NOTA` entry
- Test cetak di Chrome A5 + thermal (jika ada printer test)

**Phase P1.4 — SOAP templates + Dokter route** (~1 sesi, 1.5 jam):
- `soap_a5.html` + `soap_thermal.html` templates
- Route `/web/dokter/soap/{id_pemeriksaan}/cetak`
- `PrintService.prepare_soap_context()` (fetch SOAP + tindakan + resep + config)
- Button "🖨 Cetak Resume" di SOAP view page
- Audit log `PRINT_SOAP` entry
- Test cetak

**Phase P1.5 — Verify + housekeeping** (~30-45 menit):
- Health check post-deploy
- DEC-047 entry di decisions log
- Update 00_README dengan magic command "cetak nota" / "cetak resume"
- Update roadmap → Print Module complete

**Total estimasi: 4-5 sesi (~6-7 jam)**

---

## 9. Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Print preview tidak match actual print | MEDIUM | Test di Chrome/Edge dengan A5 + thermal. CSS pakai standar @page rule, support 95%+ browser modern. |
| Logo file rusak / hilang | LOW | Validation upload: check magic bytes PNG/JPG, max 500KB. Kalau file hilang, render placeholder text "Logo not found". |
| Owner edit format saat ada transaksi aktif | LOW | Always re-render = nota baru pakai info baru. Acceptable karena tidak ada legal/audit constraint. |
| Tidak punya printer thermal | LOW | Default A5. Owner bisa pilih thermal kapan saja kalau beli printer thermal di future. |
| Print dialog auto-trigger annoying untuk preview | LOW | Support `?autoprint=false` query param untuk preview tanpa dialog. |
| Network printer setup di Windows complex | LOW | Bukan tanggung jawab app — user install via OS. App cuma trigger window.print(). |

---

## 10. Approved Decisions (dr. Hansen — 5 Juni 2026)

7 keputusan utama sudah locked (Section 2). Final check sebelum implement:

| # | Topic | Locked Value |
|---|-------|--------------|
| 1 | Print strategy | Path A — Browser HTML print |
| 2 | Scope MVP | Nota Kasir + Resume Medis SOAP |
| 3 | Editor | Form fields sederhana |
| 4 | Role gate | Standard (per dokumen) |
| 5 | Paper size | Kedua format (thermal + A5) |
| 6 | Logo upload | File ke disk |
| 7 | Snapshot | Always re-render |

---

## 11. Trigger Kalimat untuk Mulai

Saat dr. Hansen ketik salah satu kalimat ini di sesi berikutnya:

- **"mulai print module"** atau **"lanjut print P1.1"** → AI mulai Phase P1.1 (schema + service)
- **"mulai semua print module"** → AI mulai sekuensial P1.1 → P1.5 (4-5 sesi)
- **"tunda print module, lanjut B"** → defer print, switch ke Soft Launch Prep
- **"lihat design print"** → AI baca `PrintModule/00_DESIGN.md`

---

## 12. Revision Log

- **2026-06-05** — Initial design draft. 7 keputusan locked. Ready for P1.1 implementation.
