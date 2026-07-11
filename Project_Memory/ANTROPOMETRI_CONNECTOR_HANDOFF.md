═══════════════════════════════════════════════════════════
SESSION HANDOFF — Konektor Sehati ↔ AI Antropometri (Phase 0)
Disusun: 2026-06-26 · untuk sesi berikutnya (kepala segar)
═══════════════════════════════════════════════════════════

## ROLE
Claude = lead programmer Sehati eMR-POS + **master designer ekosistem klinik dr. Hansen**.
Sehati = **otak utama**; modul AI Antropometri (Body Composition Report Tool) =
modul yang **menyesuaikan ke Sehati**. dr. Hansen = dokter pemilik (non-programmer),
Bahasa Indonesia casual. Tujuan modul: **meringankan Sehati** (offload AI/kalkulasi/PDF),
BUKAN membebani.

## DUA PROYEK (ke-mount di Cowork)
- **Sehati** (master): `E:\Claude\Projects\sehati-emr-pos\sehati_clinic`
  FastAPI + SQLAlchemy 2.0 + MySQL + Jinja2 + HTMX.
- **AI Antropometri** (modul): `E:\Apps\body_composition_report_tool`
  - FastAPI web app (port 8051) — web layer, kalkulasi lokal, OpenAI Structured Outputs,
    doctor review (state machine), PDF export — **SEMUA SELESAI**.
  - Privacy-conscious: **identitas pasien TIDAK dikirim ke AI** (hanya metrik anonim).
  - Kode: `src/bodycomp/` (web/, ai/, review/). Docs: `docs/` (INPUT_DATA_CONTRACT,
    AI_PAYLOAD_CONTRACT, DATA_FLOW, DOCTOR_REVIEW_WORKFLOW, SECURITY_PRIVACY, dll).
  - Run: `run_web.py` → http://127.0.0.1:8051/.

## BACA DULU (URUT)
1. Modul kontrak: `docs/INPUT_DATA_CONTRACT.md`, `docs/AI_PAYLOAD_CONTRACT.md`,
   `docs/DATA_FLOW.md`, `docs/DOCTOR_REVIEW_WORKFLOW.md`, `docs/SECURITY_PRIVACY.md`.
2. Modul rute aktual: `src/bodycomp/web/app.py` (sekarang: `/`, `/data`, POST `/assess`,
   `/review/{id}` + edit/approve/export). **Belum ada endpoint intake ber-token utk Sehati.**
3. Sehati: model `app/db/models/kunjungan.py` (KunjunganAntropometri) +
   `app/db/models/pasien.py` (PasienPenyakitKronis), `antropometri_service.py`, halaman
   Antropometri di Detail Pasien, `app/config.py`.

═══════════════════════════════════════════════════════════
## KEPUTUSAN ARSITEKTUR (sudah dikunci dr. Hansen)
═══════════════════════════════════════════════════════════
1. **Tidak rombak Sehati.** Skrining penyakit (ginjal/jantung/diabetes/hipertensi/eating
   disorder/ortopedik/nyeri dada) di-input di **MODUL** (checkbox sudah ada), pre-filled dari
   kontrak Sehati. Ini red-flag keselamatan → sengaja jadi input sadar dokter.
2. **Semua role bisa jalankan + LIHAT hasil** (FO/perawat/dokter). Yang dikunci cuma **tombol
   APPROVE** → hanya aktif kalau role = dokter. Non-dokter → approve disabled → PDF tak bisa
   dibuat → pasien tak dapat laporan. Modul terima `actor.role` dari Sehati + enforce.
3. **Approve di MODUL** (reuse review workflow yang sudah ada), BUKAN di SOAP Sehati (hindari
   membebani Sehati). Dokter bisa approve kapan saja (modul tahan draft) — termasuk dari
   riwayat via link yang Sehati simpan.
4. **Storage = Opsi A (Sehati simpan REFERENSI saja).** Modul simpan + tampilkan laporan
   (punya SQLite sendiri). Sehati simpan `assessment_id` (1 string) di antropometri/kunjungan.
   Riwayat pasien Sehati tampilkan baris "Laporan Komposisi Tubuh — [tgl] — [Lihat]" → buka
   jendela view modul. **TIDAK ada renderer di Sehati (Phase 0).**
5. **TIDAK ADA PDF DI DATABASE — di mana pun.** PDF transien: dibuat saat dibutuhkan
   (cetak/beri pasien), tidak dipersist. Sumber kebenaran = JSON di modul.
6. **Consent ringan** (lebih ringan dari DermAI): identitas TIDAK pernah ke AI (cuma metrik
   anonim). Cukup consent ringan, bukan gerbang seketat DermAI.

> Opsi B (Sehati simpan JSON + renderer untuk tampil terintegrasi/resilient saat modul mati)
> = DITUNDA ke Phase 1 kalau memang dibutuhkan.

═══════════════════════════════════════════════════════════
## ALUR (satu arah)
═══════════════════════════════════════════════════════════
```
Sehati (halaman Antropometri) --POST intake (token)--> Modul Antropometri
  bangun kontrak dari KunjunganAntropometri + pasien    pre-fill form
                                                        siapa pun lengkapi skrining + jalankan
                                                        → kalkulasi lokal + AI → laporan
                                                        → DOKTER approve (role-gated) → PDF (transien) ke pasien
Sehati simpan assessment_id; "Lihat" → buka view modul.
```

═══════════════════════════════════════════════════════════
## PEMETAAN DATA (Sehati → INPUT_DATA_CONTRACT modul)
═══════════════════════════════════════════════════════════
| Modul field | Sumber Sehati |
|---|---|
| `assessment_id` | id antropometri/kunjungan (internal, anonim) |
| `assessed_at` | timestamp antropometri / tgl_kunjungan |
| `sex` (male/female) | jenis_kelamin (**L→male, P→female**) |
| `age` | hitung dari tgl_lahir |
| `height_cm` | tinggi_badan |
| `weight_kg` | berat_badan |
| `waist_cm` | lingkar_perut |
| `skinfold_protocol` | JP3_MALE (L) / JP3_FEMALE (P) |
| `skinfold_mm` | map skinfold_titik_1/2/3 → situs JP3 (**KONFIRMASI urutan**: pria dada/perut/paha; wanita trisep/suprailiaka/paha) |
| `has_chronic_disease` | ada PasienPenyakitKronis? |
| screening booleans lain | pre-fill via name-match (diabetes/hipertensi); sisanya **dokter konfirmasi di modul** |
| nama/RM | display-only / local_patient_id — **TIDAK ke AI** (modul yang strip) |
| `patient_goal` | opsional |

═══════════════════════════════════════════════════════════
## PHASE 0 — PEKERJAAN SISI SEHATI
═══════════════════════════════════════════════════════════
1. **Service `AntroAIConnector`:** bangun kontrak INPUT_DATA dari KunjunganAntropometri + pasien
   + actor.role → POST intake (token) → terima `{assessment_id, url}` → simpan assessment_id →
   buka jendela. Config `base_url` + `token` di `.env`/klinik_config.
2. **DB kecil:** `antro_assessment_id` (string, nullable) di tabel antropometri/kunjungan.
3. **Tombol** di halaman Antropometri (Detail Pasien): "Buat Laporan Komposisi Tubuh (AI)".
   Kirim role aktor. Semua role boleh klik.
4. **Riwayat:** baris "Laporan Komposisi Tubuh — [tgl] — [Lihat]" → buka view modul.
5. Map gender L→male/P→female; hitung age dari DOB; pre-fill has_chronic_disease.

═══════════════════════════════════════════════════════════
## PHASE 0 — TO-DO PERBAIKAN MODUL (agar molding ke Sehati)
═══════════════════════════════════════════════════════════
> Modul SUDAH lengkap (web, kalkulasi, AI, review, PDF). Ini **penyesuaian** integrasi.
> Verifikasi vs `src/bodycomp/web/app.py` + INPUT_DATA_CONTRACT sebelum eksekusi.

1. **Endpoint intake ber-token untuk Sehati.** Sekarang baru web form `/assess`. Tambah
   `POST /intake` (Bearer token) → terima kontrak data dari Sehati → buat assessment (pre-filled)
   → balas `{assessment_id, url}`. (Pola DermAI /intake.)
2. **Role-aware APPROVE gating.** Terima `actor.role` dari Sehati. Kalau bukan dokter → tombol
   approve disabled (UI) + endpoint `/review/{id}/approve` TOLAK (server-side enforce). Export
   PDF tetap hanya saat `approved` (sudah ada).
3. **Pre-fill dari kontrak Sehati** (sex/age/measurements/skinfold/has_chronic_disease) + dokter
   lengkapi sisa skrining. Jangan minta ketik ulang data yang Sehati sudah kirim.
4. **Konfirmasi pemetaan skinfold** (Sehati 1/2/3 ↔ situs JP3). Selaraskan urutan.
5. **PDF transien** — pastikan tidak ada persist PDF (sudah sesuai: export on-demand).
6. **Deployment ikut topologi Sehati** (base_url klinik LAN, token dibagikan ke Sehati,
   HTTPS bila Sehati pakai; LAN HTTP juga oke). Kalau identitas dikirim utk display, pastikan
   tetap TIDAK masuk payload AI (sudah by-design).

═══════════════════════════════════════════════════════════
## OUT OF SCOPE PHASE 0 (parkir)
═══════════════════════════════════════════════════════════
- **Opsi B** (Sehati simpan JSON + renderer pretty di Sehati) → Phase 1 kalau perlu history
  terintegrasi / resilient saat modul mati.
- Write-back laporan ke rekam medis Sehati (selain assessment_id) → ditunda.
- Tracking tren komposisi tubuh lintas-kunjungan (grafik progress) → Phase 1.

═══════════════════════════════════════════════════════════
## START SEQUENCE
═══════════════════════════════════════════════════════════
1. Baca kontrak modul (INPUT_DATA_CONTRACT, DATA_FLOW, review workflow) + rute aktual +
   antropometri Sehati.
2. Kunci pemetaan skinfold + token/base_url.
3. Rancang skeleton `AntroAIConnector` + tombol + field assessment_id. Breakdown → approval.
4. Implement sisi Sehati (patch-script/heredoc, verify via bash).
5. Susun to-do perbaikan modul sebagai workplan terpisah di proyek modul.
6. Uji bareng.

Mulai dengan baca kontrak dua sisi, lalu breakdown + tunggu approval dr. Hansen sebelum coding.
═══════════════════════════════════════════════════════════
