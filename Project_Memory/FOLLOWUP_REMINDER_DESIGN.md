# FOLLOW-UP REMINDER — Design Note

Status: DESAIN (belum dibuild). Divalidasi dr. Hansen 2026-07-07.
Analogi: "seperti modul Booking, tapi versi reminder follow-up." Booking = kalender; follow-up = **list weekly/daily**.

---

## 1. Konsep inti

Follow-up dihitung **per-item treatment**, BUKAN per-kunjungan.
Konsultasi sendiri adalah salah satu master treatment — jadi satu kunjungan yang berisi
"konsultasi + facial" menghasilkan **2 follow-up di 2 tanggal berbeda**.

Contoh (hari ini 7/7/26):
- Pasien X, konsultasi -> due 14/7/26 (default 1 minggu)
- Pasien X, facial -> due 21/7/26 (2 minggu dari treatment)
=> di halaman follow-up: tanggal 14/7 muncul Pasien X (konsultasi), tanggal 21/7 muncul lagi Pasien X (facial).

Satu pasien bisa muncul beberapa kali, di tanggal berbeda, satu baris per item.

---

## 2. Field yang SUDAH ADA (reuse, tidak perlu bikin baru)

- `MasterTreatment.default_rentang_mulai_minggu` = **min minggu** (jadi due-date default).
- `MasterTreatment.default_rentang_akhir_minggu` = **max minggu** (batas atas window; dipakai untuk warna "overdue"/telat).
- `Kunjungan.tgl_kontrol_selanjutnya` (Date, nullable) = override dokter — SUDAH ADA, tapi **belum ada input di form SOAP** (perlu di-wire).

---

## 3. Cara hitung due-date (precedence)

Per item treatment di kunjungan:
- **Treatment biasa:** due = tanggal_kunjungan + `default_rentang_mulai_minggu` minggu.
- **Konsultasi:** due = **override dokter** (`tgl_kontrol_selanjutnya`) bila diisi; kalau tidak, default **1 minggu**.
- Override dokter selalu menang untuk item yang dia atur (via form SOAP + catatan).

Catatan: 1 tanggal + 1 catatan opsional per follow-up (keputusan #2 terkunci).

---

## 4. Workflow (4-state + audit) — bagian yang benar-benar BARU

State: `PENDING` -> salah satu dari `CONFIRMED` / `RESCHEDULED` / `NO_ANSWER` / `CANCELLED`.
- **Confirm** — pasien konfirmasi datang.
- **Rescheduled** — set **due_date baru** (butuh input tanggal).
- **No answer** — tak terhubung (bisa di-retry, tetap PENDING/ditandai).
- **Cancelled** — pasien batal / tak jadi kontrol.

Setiap aksi mencatat `id_staf_handler` + `waktu_handle` + `catatan` => **audit trail** untuk
menganalisa kinerja tim follow-up FO (feed ke Data Analyst, seperti analisis kongesti).

Kapan tim FO menelepon (timing reminder) = **SOP offline**, bukan diatur software (keputusan #3).

---

## 5. UI

Halaman **Follow-up** berbentuk **LIST**, default tampilan **mingguan** (atau harian), BUKAN kalender.
- "Due" = `due_date <= hari ini` (atau dalam window depan) DAN status `PENDING`.
- Kolom: tanggal, pasien (No.RM + nama), jenis (konsultasi/treatment + nama), no. HP, catatan, tombol aksi (4).
- Warna telat: kalau lewat `default_rentang_akhir_minggu` (max) => merah/overdue.

---

## 6. Skema data (baru)

Tabel `followup`:
- id (PK)
- id_pasien
- id_kunjungan (sumber)
- jenis: KONSULTASI | TREATMENT
- id_treatment (nullable; null utk konsultasi generik)
- due_date (Date)
- status: PENDING | CONFIRMED | RESCHEDULED | NO_ANSWER | CANCELLED (default PENDING)
- id_staf_handler (nullable) — siapa yang meng-handle
- waktu_handle (DateTime, nullable)
- catatan (Text, nullable)
- created_at / updated_at

Index: (due_date, status), (id_pasien).

---

## 7. Generation

Saat **SOAP disimpan** -> buat record follow-up:
- 1 per item treatment yang direncanakan/dilakukan (due dari min-minggu treatment).
- 1 untuk konsultasi (due dari `tgl_kontrol_selanjutnya` override, atau +1 minggu default).
Idempotent: jangan dobel kalau SOAP disimpan ulang (upsert by id_kunjungan + jenis + id_treatment).

---

## 8. Rencana build (per lapis, pola Booking)

- G1. Model `followup` + migrasi Alembic (defensif/idempotent).
- G2. Wire input `tgl_kontrol_selanjutnya` + catatan di form SOAP.
- G3. Generation on SOAP-save (service, idempotent).
- G4. Service: list due (weekly/daily) + handle 4 aksi + audit id_staf.
- G5. Routes + template halaman Follow-up (list, 4 tombol, filter minggu/hari).
- G6. Menu entry (FO/Kasir/Owner) + verifikasi py_compile/jinja + smoke.

Estimasi: modul kecil-menengah, 1 sesi tersendiri.

---

## Keputusan terkunci
1. Follow-up per-item treatment (konsultasi = treatment juga). Multi follow-up per pasien. ✅
2. 1 tanggal + 1 catatan. ✅
3. Timing reminder tim FO = SOP offline. ✅
4. UI list weekly/daily (bukan kalender). ✅

---

## BUILD LOG — 2026-07-08 (G1–G6 selesai, pending smoke live)

Keputusan tambahan (AskUserQuestion 2026-07-08):
- Konsultasi = **salah satu item treatment** (ada baris kunjungan_tindakan).
- Follow-up KONSULTASI **selalu** dibuat tiap SOAP disimpan (default 1 minggu, kecuali override).

Rekonsiliasi: generation di-hook di **SOAP-save** (= tiap dokter konsultasi), jadi:
- SELALU 1 follow-up KONSULTASI/kunjungan (id_treatment=NULL; due = tgl_kontrol_selanjutnya override, atau tgl_kunjungan+1mgg; catatan = catatan_kontrol).
- Tiap item treatment (kunjungan_tindakan) → TREATMENT (due = tgl+min-minggu), KECUALI item konsultasi.
- **Caveat:** item konsultasi dikenali via **nama mengandung "konsul"** (tak ada flag `is_konsultasi` di master_treatment). Kalau nama konsultasi klinik beda, sesuaikan `_is_konsultasi_treatment()` di followup_service.py (atau tambah kolom flag kelak).

Yang dibangun:
- Migrasi `20260707_0300_followup` (tabel) + `20260707_0400_kunjungan_catatan_kontrol` (kolom baru; head).
- `app/db/models/followup.py` + enum `JenisFollowupEnum`/`StatusFollowupEnum`.
- `kunjungan.catatan_kontrol` (String255) untuk simpan catatan rencana kontrol dokter.
- Form SOAP: input tanggal kontrol + catatan (prefill dari ORM). Handler: persist + generate (satu commit atomik).
- `app/services/followup_service.py`: generate_for_kunjungan + list_due/counts_open + confirm/no_answer/cancel/reschedule (audit id_staf_handler + waktu_handle).
- `app/web/routes/followup.py` + template `followup_list.html` (worklist mingguan/harian, 4 tombol, baris merah=telat). Terdaftar di router. Menu untuk Owner/Superadmin/Admin/Kasir/FO.

Status "open" (muncul di worklist) = PENDING, NO_ANSWER, RESCHEDULED. Confirm/Cancel = tutup.
Worklist menampilkan semua open due <= akhir periode (termasuk telat).

SMOKE LIVE (WSL, belum dijalankan): alembic upgrade head → restart → simpan 1 SOAP (isi/ kosongkan tgl kontrol) → cek baris `followup` → buka /web/followup → uji 4 tombol.
