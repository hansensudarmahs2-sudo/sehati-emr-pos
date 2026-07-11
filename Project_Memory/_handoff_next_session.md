═══════════════════════════════════════════════════════════
SESSION HANDOFF — Sehati Clinic eMR-POS WebApp
Ditulis: 2026-07-04  →  Untuk: sesi berikutnya (fresh agent)
═══════════════════════════════════════════════════════════

ROLE
Anda Claude, lead/senior programmer untuk Sehati Clinic eMR-POS WebApp.
User = dr. Hansen Sudarma, dokter PEMILIK klinik, BUKAN programmer.
Komunikasi: Bahasa Indonesia casual, RINGKAS & to-the-point (preferensi "concise").
Jelaskan keputusan teknis dgn bahasa awam. Selalu minta approval sebelum
bangun modul/keputusan arsitektural besar.

PROJECT
- Stack: FastAPI + SQLAlchemy 2.0 + Pydantic 2 + MySQL (pymysql) + Jinja2 + HTMX + Alembic
- Kode:   E:\Claude\Projects\sehati-emr-pos\sehati_clinic
- Memory: E:\Claude\Projects\sehati-emr-pos\Project_Memory
- Nama klinik contoh di data test: "Acnova".

CARA RUN (verifikasi dulu di awal sesi)
- `alembic upgrade head` — head TERAKHIR = 20260703_2400_retur_apoteker.
  (rantai 07-03: 1000 opname_item_lot → 1200 klinik_apoteker → 1400 po_termin_apoteker
   → 1600 lokasi_pengiriman → 1800 faktur_penerimaan → 2000 reorder_leadtime
   → 2200 retur_produk → 2400 retur_apoteker). Single-head linear.
  Kalau user lapor kolom hilang / 500, tersangka #1 = belum `alembic upgrade head`.
- `uvicorn app.main:app --reload --port 8000` (dari sehati_clinic/, venv aktif).
- Test: `pytest`.

═══════════════════════════════════════════════════════════
GOTCHAS PENTING (baca sebelum menyunting)
═══════════════════════════════════════════════════════════
- B-013 (truncation): Edit/Write tool bisa MEMOTONG ekor file .py/template besar di
  bridge E:↔WSL. WORKAROUND: sunting via bash heredoc / python `replace`; SELALU
  verifikasi: `py_compile` (py) / Jinja parse (template) + cek jumlah baris masuk akal
  + null-byte `python3 -c "print(open(f,'rb').read().count(b'\x00'))"` + marker ekor
  (`</body></html>`, dsb). Kalau baris BERKURANG padahal menambah → truncation, restore.
- B-028: Tailwind app.css TER-PURGE → kelas arbitrary & varian responsif (md:/sm:/lg:)
  DIAM-DIAM gagal. Untuk styling baru pakai `<style>` media-query manual / inline style.
- B-029: dashboard(auth.py) + login BANGUN context shell manual (bukan via _app.html base).
- B-031: middleware HARUS pure-ASGI. `@app.middleware("http")` BaseHTTPMiddleware
  MENGHAPUS Set-Cookie CSRF → semua form "Token Keamanan Tidak Valid". SecurityHeaders
  sudah pure-ASGI di main.py — jangan balik ke @app.middleware.
- Transaksi: service FLUSH, route COMMIT (kecuali proses_bayar/void_transaksi/receive_item/
  retur/opname yang commit internal). VOID dikecualikan dari semua agregasi uang.
- FEFO: tgl_ed ASC (NULL last) → tgl_masuk ASC → id_lot. VOID/retur potong/kembalikan lot
  MANUAL (dropdown) demi jejak QC, bukan FEFO otomatis. Uang: Decimal, float hanya di boundary.

═══════════════════════════════════════════════════════════
YANG SELESAI (kumulatif s/d 2026-07-04)
═══════════════════════════════════════════════════════════
Modul inti: EMR/SOAP, POS/kasir, tutup kasir + rekap, booking, komisi, apotek+FEFO+lot/ED,
opname per-batch, penyakit kronis, audit-log + akses-baca (log_view).
Pengadaan lengkap: Master Distributor, PO ideal (termin/validitas/apoteker+SIPA/No.SIA/ship-to),
Faktur penerimaan (reverse-discount, terima parsial per-baris, harga-terima editable, 2-cetak
finance/inventory di window baru), Master Lokasi Pengiriman.
Stok minimal DINAMIS: effective_min = MAX(manual, ROP). ROP = ceil((pakai_90h/90)×(lead+safety)).
Retur produk: form + pilih lot manual + approve(=potong lot) + Nota Retur (tukar→lot baru / refund→tutup),
apoteker PJ+SIPA+SIA di cetakan.
Master Klinik identity: kode_klinik, rm_prefix, no_sia, lead/safety di Profil Klinik + CRUD apoteker.

SESI 2026-07-04 (ini):
- B3 DEPLOYMENT: `deployment/B3_DEPLOYMENT_GUIDE.md` di-refresh + file config siap-pakai
  (`sehati-clinic.service`, `nginx_sehati.conf`, `.env.prod.example`). Target go-live pertama:
  1 klinik, Ubuntu native mini-PC, LAN, HTTP. (DEC-097)
- TEASER REMOTE: Lampiran A (WSL2 & teaser LAN) + Lampiran B (teaser remote: PC rumah diakses
  dari klinik via Tailscale [rekomendasi, privat] atau Cloudflare Tunnel [publik+gate]) +
  skrip `deployment/refresh-sehati-teaser.ps1` (auto-refresh portproxy Tailscale→WSL). Sudah
  DIUJI user: HP di seluler (bukan LAN rumah) akses lancar via Tailscale. (DEC-099)
- NAV DRAWER HP: `_app.html` (73 halaman) — sidebar jadi off-canvas drawer + hamburger di <768px,
  tablet/desktop tak berubah. (DEC-098)
- BERSIH TOMBOL DEV: hapus "Header Dokter (JSON)" di pasien_detail; "Swagger UI" di-gate Owner saja.
  ("Dictionary JSON" di export = fitur sah, dibiarkan.) (DEC-098)

═══════════════════════════════════════════════════════════
PENDING / BACKLOG (belum dikerjakan — lihat TODO_SEHATI.md)
═══════════════════════════════════════════════════════════
- B3 sisa = EKSEKUSI DI SERVER oleh dr.Hansen/teknisi (systemd, IP statis, MySQL tuning+grant,
  cron backup, setup data awal, smoke test fisik). Kode/guide sudah siap.
- P-L6c (DITUNDA): tindakan potong BHP → FEFO bahan (#62).
- MODUL FINANCE (kategori baru): status bayar/jatuh tempo faktur (AP/hutang), FK-L6. Design-only.
- Mobile-friendly ALUR FOTO perawat/dokter (patient quick-view + tombol intake DermAI + return_url).
  DITUNDA sampai DermAI ada; UI kamera = ranah DermAI (WAJIB masuk syarat kontrak DermAI: responsif HP).
- Rename master_klinik + stok per-cabang (tunggu cabang ke-2). Arsitektur di MASTER_KLINIK §9 (1 DB
  pusat + resolusi klinik via IP/subnet). Contingency: EMRPOS_MINI_CONTINGENCY_DESIGN.md (resync
  engine BELUM dibuat: emergency-prefix E-A-..., de-dup 4-field, validasi manual).
- +Antrian kontekstual (butuh design doc).
- Konektor: DermAI, Antropometri, Accurate (finance).
- Keamanan lanjutan: TLS/HSTS/CSP, enkripsi at-rest, 2FA, idle-timeout, pip-audit,
  audit-immutability (GRANT tanpa UPDATE/DELETE).

CARA MULAI SESI: baca file ini → `alembic upgrade head` + uvicorn jalan → tanya dr. Hansen
mau lanjut item mana. Jangan mulai modul besar tanpa approval.

═══════════════════════════════════════════════════════════
UPDATE 2026-07-05 — KONEKTOR ANTROPOMETRI + AI (sesi panjang)
═══════════════════════════════════════════════════════════
App modul: E:\Apps\body_composition_report_tool (FastAPI, run: run_web.bat -> http://127.0.0.1:8051/,
form /assess). Kontrak: Project_Memory/CONTRACT_SEHATI_ANTROPOMETRI_v1.md. Aturan medis:
body_composition_report_tool/docs/ANTROPO_DETERMINISTIC_RULES.md.

SELESAI:
- AN-L1: konektor handshake 2 sisi — modul web/connector.py (POST /intake Bearer A + GET /health) +
  connector_core.py (pure); Sehati app/services/antro_connector.py + antro_connector_core.py
  (build_intake_payload, skinfold_named, map_sex/role). INTAKE PARSIAL: antropometri OPSIONAL, wajib hanya
  schema_version+patient.sex (modul isi bila Sehati tak kirim).
- AN-AI-1: modul src/bodycomp/energy.py — BMR Mifflin-St Jeor, TDEE, energy_plan (target 5-10%/6bln, lantai
  kalori, laju aman), macro_targets, impact_tolerance (BMI>=30/ortopedi/usia>=65 -> LOW_IMPACT),
  needs_medical_clearance. Riset guideline (CDC/ACSM/WHO/NHLBI). tests/test_energy.py.
- AN-AI-2: payload.py enrich (energy/macro/exercise/context), models.py+forms.py+pages.py (+activity_level +
  teks opsional; exercise_habit DIHAPUS krn redundan), prompt_v2, client.py pakai prompt_v2. Nama obat TAK ke AI
  (hanya flag on_weight_med).
- AN-AI-3: multi-provider (settings.py + client.py). AI_PROVIDER=anthropic main -> OpenAI auto-fallback -> dummy.
  _AnthropicResponder pakai TOOL-USE (paksa schema) + normalisasi stringified-JSON (Haiku). Model default
  claude-sonnet-4-6. Loader .env FALLBACK bawaan (tanpa python-dotenv) + _bool tahan komentar-sebaris.
- Guardrail (validator.py) diperhalus: fokus konteks OBAT (dosis obat/resep obat/N mg non-lab) + NEGATION-AWARE
  (disclaimer "bukan diagnosis pasti" lolos). prompt_v2 LINGKUP TERTUTUP (jangan perkenalkan penyakit di luar
  input, jangan nilai lab, jangan tatalaksana).

CATATAN OPERASIONAL (mesin dr.Hansen):
- run_web.bat pakai .venv -> pip install harus KE .venv (bukan global). anthropic sudah terpasang.
- .env modul: AI_ENABLED=true, AI_PROVIDER=anthropic, ANTHROPIC_API_KEY=<valid>, ANTHROPIC_MODEL=claude-sonnet-4-6.
- Kredensial Anthropic dari console.anthropic.com (API terpisah dari langganan claude.ai).
- Cek hasil: logs/ai_usage.jsonl -> source harus "anthropic". Sonnet 1 laporan ~4.5k token out, ~60-90 detik.

BERIKUTNYA — AN-AI-4 (DESAIN SUDAH ADA: docs/ANTROPO_AI4_TEMPLATE_DESIGN.md):
Ciutkan AI ke interpretasi+personalisasi; skema kalori/olahraga/makan DETERMINISTIK. Meal-template dari
culinary_lab (E:\Claude Skills\culinary_lab, 99 resep, 93 halal non-babi) — SUBSET TERKURASI ke modul, filter
halal, MVP tag-based (energy.py=jangkar makro). Fase 4a kurasi -> 4b komposer+template olahraga -> 4c schema/
prompt ringkas -> 4d renderer+test. Tujuan: token turun ~4.5k->~1k, cepat, aman, konsisten, minim guardrail.
Belum mulai kode 4a.

--- UPDATE 2026-07-05 (lanjutan) — SMART TARGET ENGINE (AN-AI-5) ---
BUG KRITIS diperbaiki: energy_plan lama menyuruh pasien BMI-normal turun berat (65->58.5). Fix energy.py
sadar-goal + DIBANGUN mesin baru plan_engine.py (Asia-Pasifik + sub-band + target-rentang + kurva laju
bertingkat + band kalori). Keputusan terkunci: Asia-Pasifik, sub-band mid, laju .50/.45/.35/.25, band ±150.
BUILT & TESTED (9 check + tests/test_plan_engine.py): src/bodycomp/plan_engine.py.
BELUM DIWIRE ke laporan (payload masih pakai energy_plan lama). LANGKAH BERIKUT (AN-AI-5d - PENTING):
ganti pemakaian energy_plan di payload.py -> plan_engine.build_plan; update prompt_v2 narasi ikut
goal/target-rentang/band-kalori; renderer tampilkan band & target rentang. Lalu 5c olahraga per-tujuan
(fat_burn/muscle/joint_friendly) + 5e meal culinary_lab. Doc: docs/SMART_TARGET_ENGINE_DESIGN.md.

--- UPDATE 2026-07-05 (AN-AI-5d SELESAI) ---
plan_engine SUDAH DIWIRE ke laporan: payload.py pakai build_plan (bukan energy_plan lama); prompt_v2 TUJUAN
3-mode (pemeliharaan/penurunan/penambahan) + band kalori + target-rentang; render/html.py kartu "Rencana Kalori
(dihitung sistem)" deterministik di hal.1. Verifikasi 7 check. Bug BMI-normal-disuruh-turun TUNTAS di laporan.
SISA AN-AI-5: 5c olahraga per-tujuan (fat_burn/muscle/joint_friendly + DB), 5e meal culinary_lab (subset halal
terkurasi, tag-based). AN-AI-4 (ciutkan schema AI ke interpretasi saja) bisa digabung setelah 5c/5e.
Aksi dr.Hansen: restart run_web.bat, uji pasien BMI normal -> kartu "Pertahankan berat" + tak ada target turun.

--- UPDATE 2026-07-05 (AN-AI-5c SELESAI) ---
Olahraga per-tujuan: exercise_engine.py (fat_burn/muscle/joint_friendly + selector) + wire payload[exercise_plan]
+ kartu deterministik renderer hal.3 + prompt_v2 komponen D. Verifikasi 6+6 check. SISA AN-AI-5: hanya 5e (meal
template culinary_lab: subset halal terkurasi non-babi, MVP tag-based, komposer isi slot sarapan/siang/snack/malam
by kategori+kondisi[rendah garam utk HT], angka makro dari plan_engine/energy). culinary_lab=E:\Claude Skills\
culinary_lab (99 resep, 93 halal). Doc: docs/SMART_TARGET_ENGINE_DESIGN.md + ANTROPO_AI4_TEMPLATE_DESIGN.md.

--- UPDATE 2026-07-05 (AN-AI-5e SELESAI = SELURUH AN-AI-5 TUNTAS) ---
Meal: scripts/curate_meal_templates.py + data/reference/meal_templates.json (94 halal) + meal_engine.py
(compose slot harian, rotasi variasi, rendah-garam utk HT) + wire payload[meal_plan] + kartu "Contoh Menu"
renderer hal.2 + prompt_v2 C. Laporan kini 3 KARTU DETERMINISTIK (Rencana Kalori / Aktivitas Fisik / Contoh Menu)
+ narasi AI. Modul baru: plan_engine.py, exercise_engine.py, meal_engine.py (+ energy.py sadar-goal). Tests:
test_plan_engine, test_exercise_engine, test_meal_engine, test_energy. AKSI dr.Hansen: `pip`-tak-perlu; restart
run_web.bat + uji (BMI normal->pertahankan; obese->target rentang+band+laju landai; olahraga low-impact bila
LOW_IMPACT; contoh menu resep nyata). LANJUTAN OPSIONAL: dr.Hansen tambah underweight/overweight meal plan khusus;
AN-AI-4c ciutkan schema AI (token turun lagi); externalize reference json.

--- UPDATE 2026-07-05 (AN-AI-5e REVISI: meal AI-driven) ---
dr.Hansen prefer meal plan dari AI (jam+gram+varian+bahan generik, TANPA nama resep), selaras energy.calorie_band.
Kartu meal deterministik + wiring DIHAPUS (payload/render). prompt_v2 komponen C ditulis ulang (grams+times+variants
generik). meal_engine.py/curate_meal_templates.py/meal_templates.json(94 halal)/test_meal_engine.py = ASET DORMANT
(tak wired; bisa dipakai kelak utk lampiran resep). Kartu deterministik yang MASIH tampil: Rencana Kalori +
Aktivitas Fisik. Disclaimer standar wajib (_STD_DISCLAIMER) selalu ada. pytest 2 fix (AIPayload +Optional dict;
disclaimer standar).

--- UPDATE 2026-07-05 (ARSITEKTUR ANTROPO v1.1: fire-and-forget + pull) ---
dr.Hansen KUNCI: (1) penyakit kronis TAK ditulis balik (Sehati sumber kebenaran), (2) metrik komposisi tubuh
TINGGAL DI MODUL (Sehati pull/link, tak simpan), (3) modul ASINKRON (fire-and-forget). Sehati NOL endpoint
tulis-masuk (hanya panggilan keluar + GET pull) -> stabilitas maksimal. Kontrak diperbarui v1.1 (§4/§5 write-back
DIARSIP). RENCANA modul: body_composition_report_tool/docs/ANTROPO_ASYNC_REFACTOR_DESIGN.md. FASE: ASYNC-M1
(status+background), ASYNC-M2 (intake->assessment+return_url), ASYNC-M3 (pull /status,/reports,/regenerate).
Lalu AN-L2 Sehati (papan laporan+tombol+re-send). Belum mulai kode async.

--- UPDATE 2026-07-05 (ASYNC-M1 SELESAI) ---
Modul kini ASINKRON: web/jobs.py (JobStore) + AppService.create_assessment_async/_generate_bg/resend/job_status +
review_html tangani PROCESSING/FAILED + /assess async. Submit -> balik seketika -> AI di daemon thread -> DONE/
FAILED. tests/test_async_flow.py. SISA: ASYNC-M2 (intake->assessment pre-fill + redirect return_url seketika di
web/connector.py /intake, sekarang masih stub), ASYNC-M3 (endpoint pull GET /status/{id} + GET /reports?rm + POST
/regenerate + signed /view), lalu AN-L2 Sehati (menu papan laporan + tombol fire-and-forget + re-send; simpan hanya
assessment_id; NOL tulis-masuk). Doc: docs/ANTROPO_ASYNC_REFACTOR_DESIGN.md + CONTRACT v1.1.

--- UPDATE 2026-07-05 (ASYNC-M1b: status + clean-slate) ---
Status terpadu: processed|waiting_approval|approved|failed (jobs.display_status + STATUS_LABEL). Submit -> balik ke
FORM KOSONG (/?ok=1) + banner, TAK ada layar stuck. Data Tersimpan gabung job PROCESSING + review, tampil Status.
Status code siap utk pull Sehati. Storage modul = JSON files (reviews/patient_meta/jobs/exports/intake/reference),
keyed storage_id. SISA: ASYNC-M2 (intake pre-fill + redirect return_url = "tutup" modul saat dipanggil Sehati),
ASYNC-M3 (pull GET /status,/reports + /regenerate), AN-L2 Sehati (papan laporan pakai status code).

═══════════════════════════════════════════════════════════
RINGKASAN STATE AKHIR SESI — 2026-07-05 (untuk fresh agent)
═══════════════════════════════════════════════════════════
KONTEKS: Sesi panjang fokus MODUL ANTROPOMETRI (E:\Apps\body_composition_report_tool) + integrasinya ke Sehati.
Sehati sendiri TIDAK diubah struktural sesi ini (aman, stabil).

SUDAH SELESAI & TERUJI (modul antropo):
- Laporan AI end-to-end: energy.py + plan_engine.py (BMI Asia-Pasifik, sub-band mid, target rentang, kurva laju
  landai bertingkat, band kalori) + exercise_engine.py (fat_burn/muscle/joint_friendly) + prompt_v2 (meal AI:
  jam/gram/varian generik selaras band; TANPA nama resep) + provider Anthropic (sonnet-4-6, fallback openai->dummy).
  Renderer: 2 kartu deterministik (Rencana Kalori, Aktivitas Fisik) + disclaimer standar wajib.
- ASINKRON (fire-and-forget): web/jobs.py (JobStore) + AppService.create_assessment_async/_generate_bg/resend +
  status terpadu jobs.display_status (processed/waiting_approval/approved/failed). Submit -> FORM KOSONG (/?ok=1)
  + banner; Data Tersimpan gabung job PROCESSING + review + kolom Status. processing_page auto-refresh 5s.
- Tests: test_plan_engine, test_exercise_engine, test_meal_engine, test_energy, test_async_flow, test_connector_core.
  dr.Hansen konfirmasi PYTEST HIJAU (2 fix: AIPayload +Optional dict; disclaimer standar).

KEPUTUSAN ARSITEKTUR TERKUNCI (v1.1):
- Integrasi Sehati<->antropo = FIRE-AND-FORGET + PULL. Sehati NOL endpoint tulis-masuk (hanya panggilan keluar +
  GET pull). Penyakit kronis & metrik TIDAK ditulis balik (Sehati sumber kebenaran; metrik tinggal di modul).
  Kontrak: CONTRACT_SEHATI_ANTROPOMETRI_v1.md (§4/§5 write-back DIARSIP).
- Storage modul = JSON files (volume rendah); naik SQLite bila perlu; JANGAN share MySQL Sehati.

SISA (belum dikoding) — urut:
1. ASYNC-M2 (modul): /intake petakan payload -> assessment pre-fill + redirect return_url seketika (modul "tutup"
   balik ke Sehati). Sekarang /intake masih STUB (simpan mentah ke data/intake).
2. ASYNC-M3 (modul): endpoint PULL utk Sehati — GET /status/{id}, GET /reports?rm=, POST /regenerate/{id} (re-send).
3. AN-L2 (SEHATI): menu Antropometri = papan laporan (pull daftar+status code) + tombol "Buat Laporan" fire-and-forget
   (POST /intake) + re-send. Simpan hanya assessment_id. NOL tulis-masuk. Timeout pendek + gagal-anggun.
Docs rencana: body_composition_report_tool/docs/ANTROPO_ASYNC_REFACTOR_DESIGN.md + SMART_TARGET_ENGINE_DESIGN.md.

AKSI dr.Hansen di mesin: restart run_web.bat; .env modul (AI_PROVIDER=anthropic + ANTHROPIC_API_KEY + AI_ENABLED=true);
install anthropic KE .venv. Uji: submit->form kosong+banner; Data Tersimpan status berubah; laporan spesifik +
BMI-normal="pertahankan berat".

SISA LAIN (Sehati, non-antropo, lama): P-L6c BHP-FEFO; Modul Finance; +Antrian kontekstual; Absensi; deployment B3
eksekusi server; keamanan produksi (TLS/2FA/dll). Lihat TODO_SEHATI.md.

--- UPDATE 2026-07-05 (ASYNC-M2 SELESAI) ---
Intake pre-fill + return_url: connector_core.build_prefill; /intake balas url=/intake/{id}; GET /intake/{id} ->
form TERISI (index_page prefill JS + hidden return_url); /assess redirect return_url (balik ke Sehati) bila ada.
tests +build_prefill (test_connector_core). Alur intake Sehati->modul->balik SELESAI. SISA: ASYNC-M3 (endpoint pull
GET /status/{id}, GET /reports?rm, POST /regenerate/{id}) utk Sehati baca status; lalu AN-L2 Sehati (papan laporan+
tombol fire-and-forget POST /intake + buka url). Contract v1.1 + docs/ANTROPO_ASYNC_REFACTOR_DESIGN.md.

--- UPDATE 2026-07-05 (ASYNC-M3 SELESAI = SISI MODUL LENGKAP) ---
Pull endpoints (Bearer A): GET /status/{id}, GET /reports?rm, POST /regenerate/{id}. id konsisten (intake_id ->
storage_id; report keyed = assessment_id balasan /intake) + rm di meta. AppService.pull_status/pull_reports.
tests/test_async_flow.py +pull. SISI MODUL untuk integrasi = SELESAI (M1 async, M1b status+clean-slate, M2 intake
prefill+return_url, M3 pull). BERIKUTNYA hanya AN-L2 di SEHATI (sehati_clinic): menu Antropometri = papan laporan
(pull GET {antro}/reports?rm=<no_rm> + status code) + tombol "Buat Laporan Komposisi Tubuh" di Detail Pasien
(antro_connector.intake(build_intake_payload(...)) fire-and-forget -> buka url balasan) + re-send (POST /regenerate).
Sehati simpan HANYA assessment_id. NOL endpoint tulis-masuk. Konektor Sehati (antro_connector.py) sudah ada
health()/intake(); tambah status()/reports()/regenerate() GET/POST + UI. Contract v1.1.

--- UPDATE 2026-07-05 (AN-L2 a+b SELESAI; L2c = SISA TERAKHIR) ---
Sisi Sehati: antro_connector.py +status/reports/regenerate (pull, Bearer A). antro_report_service.py: build_payload
(dari pasien+kunjungan_antropometri; L->male; skinfold_named; antro None=parsial) + kirim/daftar/status/resend
(outbound+pull, NOL tulis-masuk). TAK perlu migrasi (pull-by-rm; assessment_id tak disimpan). tests/
test_antro_report_service.py. SISA = AN-L2c (route + template + tombol) — DETAIL spec di DEC "AN-L2 a+b DONE":
routes pasien.py (GET /pasien/{id}/antro papan; POST .../buat fire-and-forget; POST .../{aid}/resend), template
antro_laporan.html (extends _app.html, shell-context MANUAL spt B-029), tombol kecil di pasien_detail.html section
Antropometri (hati B-013). Gate AntroReportService.enabled(). Butuh uji-runtime (app kritis) -> kerjakan fokus.
Ini melengkapi SELURUH integrasi antropo (modul M1-M3 SELESAI + Sehati L2a/b SELESAI; tinggal L2c UI).

================================================================================
# HANDOFF 2026-07-06 (AN-L2c UI + AN-VITAL) — untuk sesi berikutnya
================================================================================

## SELESAI & TERUJI di mesin dr. Hansen sesi ini
- AN-L2c (UI Sehati alih ke modul antropo):
  * Step 1: pendaftaran_pasien buang Step 4 (antro+vital), TOTAL_STEPS 3, route stop simpan. [TERUJI]
  * Step 2: pasien_detail card "Antropometri (Laporan AI)" — pull approved dari modul + tombol Buat +
    data lama read-only. Panel edit dibuang.
  * Step 3: dokter_soap_form kolom-3 — draft belum-approve tampil dulu (badge) + tombol Buat.
  * Plumbing: AntroReportService.laporan_by_rm (pull aman, timeout 3s, degrade). Route POST
    /pasien/{id}/antro/buat (fire intake antro=None + return_url) & .../resend. Guard dokter/perawat/owner.
  * KEPUTUSAN: tanda vital DIHAPUS TOTAL dari Sehati; backend antro lama PENSIUN READ-ONLY.
- AN-VITAL (TD+nadi di MODUL antropo → batas intensitas olahraga + sinyal AI). [TERUJI: 139/80 nadi96→moderate;
  190/100→hold]. Kategori 2025 AHA/ACC. classify_bp per-komponen. Krisis=HOLD (tunda+rujuk). Modul saja.
- BONUS: jobs.py _write ATOMIK (mkstemp+os.replace) → race test_failed_then_resend beres + integritas job.

## LINGKUNGAN TEASER (penting!)
- Sehati jalan di WSL (uvicorn 8000). Modul antropo SEKARANG jalan di WSL juga (.venv-linux,
  PYTHONPATH=src uvicorn bodycomp.web.app:app --host 127.0.0.1 --port 8051) → loopback 127.0.0.1 nyambung.
  (Sebelumnya modul di Windows 127.0.0.1 → TAK terjangkau dari WSL; itu sebabnya pindah ke WSL.)
- .env Sehati: ANTRO_BASE_URL=http://127.0.0.1:8051, ANTRO_INTAKE_TOKEN=<sama dgn modul>.
- pytest: pakai `python -m pytest` di dalam venv (bukan `pytest` telanjang = python sistem, tanpa pydantic).

## OPEN ISSUES (semua DITUNDA, catat dulu — lihat 07_known_issues.md)
- B-ANTRO-1: label "Diproses" salah jadi "menunggu approval" (pisah bucket processing vs pending).
- B-ANTRO-3: "Buat Laporan" buka laporan LAMA → fix idempotency_key unik per klik
  (antro_connector_core.build_intake_payload / pemanggilan di pasien_antro_buat: tambah unix_ts).
- B-ANTRO-4: review modul bocorkan path mnt/e + audit log salah tempat (render_review_html/_audit_field).
- B-ANTRO-5: belum ada Reject / Reject+Edit utk laporan belum approve (cek ReviewService dulu).

## CATATAN TEKNIS
- Edit E:<->WSL: Edit/Read tool SEMPAT tak sinkron ke mount WSL → WAJIB edit via bash python + verifikasi
  grep di mount WSL (B-013 diperluas). Semua edit sesi ini via bash python.
- _dokter_antropometri_panel.html kini YATIM (dead, aman). Backend antro lama (model/service/REST/route ubah)
  sengaja DIBIARKAN (pensiun read-only), tak dihapus.

═══════════════════════════════════════════════════════════
SESI 2026-07-07 (append) — banyak fitur + fondasi
═══════════════════════════════════════════════════════════
Head migrasi TERAKHIR: 20260707_0200_kunjungan_waktu_masuk_status.
(rantai baru 07-06/07: inventory_cost → ppn_settle_refund → 0100 audit_log_indexes → 0200 waktu_masuk_status.)
Verifikasi awal sesi: `alembic upgrade head` + `python -m compileall app`.

SELESAI sesi ini:
- SMART EXPORT KE FINANCE: tombol UI owner/superadmin (/web/finance-export), cek fingerprint
  dulu (soft-warning kalau identik). FINGERPRINT_EXCLUDE={staff_activity_raw,medical_soap_raw}
  (audit/SOAP volatil → tak memicu "beda"). Core dipakai bersama CLI. Finance sisi ingest =
  FILE-DROP (scan folder, no live-pull), tabel ingest_batch diformalkan via Alembic.
- SECURITY QUICK-WINS: header Permissions-Policy; audit-baca (log_view) di perawat+apotek;
  dok KLASIFIKASI_DATA_V1.8.md; RUNBOOK_PIP_AUDIT.md (+scripts/security_pip_audit.sh).
- CACHE FONDASI: app/core/ttl_cache.py (TTL+LRU+single-flight+kill-switch SEHATI_CACHE_ENABLED).
  5 endpoint antrian di-render_cached (TTL 12s). Indeks audit_log (waktu,target). Terbukti live.
- WARNA WAIT ANTRIAN FO: kolom kunjungan.waktu_masuk_status (event-stamp saat status berubah).
  Kartu konsul/treatment/bayar berwarna + "Terlama: N mnt". Ambang: konsul/treatment (20,30),
  bayar (6,11) → >10mnt merah. Inline-style (B-028).
- NOMOR ANTRIAN (NA-PRINT): cetak thermal (print/antrian_thermal.html, PrintService
  .prepare_antrian_context, audit PRINT_ANTRIAN). Auto-print saat daftar (?print_antrian=id di _app.html)
  + tombol "🖨 Nomor" cetak-ulang. Counter reset harian 00:01 WIB (nomor_antrean per-hari).
  CATATAN: nomor DECOUPLED dari state EMR — skip/call/urutan = SOP OFFLINE, bukan software.
- BADGE PER-ROLE: badge merah di menu (Dokter=ANTRI_KONSULTASI, Tindakan=ANTRI_TREATMENT,
  Kasir=ANTRI_BAYAR, Apotek=ANTRI_OBAT). badge_counts di build_shell_context (cache 10s).
- #4 RIWAYAT SOAP: panel riwayat per-kunjungan di form SOAP (treatments+produk+diagnosa),
  layout revamp 60/40 (form kiri / history sticky kanan). NB: panel per-VISIT bukan SOAP-only
  (banyak pasien punya treatment tapi belum tentu SOAP).
- DATA ANALYST: pipeline `run` sekarang JSON-aware (prepare_input.py shim CSV←JSON) + toleran
  dataset kosong (empty required → warning, council_handoff selalu jadi). Modul movement
  (timelog_movement.py) rekonstruksi insiden merah dari transisi status. status_maps di-refresh.
  Export raw diperkaya (status_lama/status_baru transisi). Handoff md ditulis.
- INTERCOMPANY (design-only, finance-ai/26): prefix B2 pakai kuota beli B1 → B1 hutang ke B2.
- HOUSEKEEPING: 6 file usang dihapus (A7).

GOTCHA BARU:
- B-013 masih berlaku (Edit/Write truncate ekor di E:↔WSL) → sunting via bash+verify.
- MySQL CLI mesin ini: `mysql -u klinik_dev -p db_sehati` (root/sudo mysql GAGAL 1045).
  mysqldump juga `-u klinik_dev -p --no-tablespaces`. (disimpan di memory).
- WSL host commands pakai python3 (bukan python).

═══════════════════════════════════════════════════════════
MULAI DI SINI (next session) — #7 FOLLOW-UP REMINDER
═══════════════════════════════════════════════════════════
Design SUDAH FINAL & divalidasi → Project_Memory/FOLLOWUP_REMINDER_DESIGN.md.
Ringkas: follow-up PER-ITEM treatment (konsultasi=treatment juga → 1 pasien bisa banyak
follow-up di tanggal beda). Field min/max minggu (default_rentang_mulai/akhir_minggu) &
override dokter (Kunjungan.tgl_kontrol_selanjutnya) SUDAH ADA. Yang baru: tabel `followup` +
generation on-SOAP-save + halaman list weekly/daily + workflow 4-tombol (Confirm/Rescheduled/
No-answer/Cancelled) beraudit id_staf. Build per lapis G1–G6 (lihat design note §8).
Pola contek modul Booking. MINTA APPROVAL sebelum mulai, konfirmasi mulai dari G1.

═══════════════════════════════════════════════════════════
UPDATE 2026-07-08 — #7 FOLLOW-UP REMINDER: SHIPPED & LIVE ✅
═══════════════════════════════════════════════════════════
Head migrasi TERAKHIR sekarang: 20260707_0400_kunjungan_catatan_kontrol.
G1–G6 tuntas & diverifikasi live oleh dr. Hansen ("all clear").
Detail + build log: Project_Memory/FOLLOWUP_REMINDER_DESIGN.md.
File: models/followup.py, services/followup_service.py, routes/followup.py,
templates/followup_list.html, +kolom kunjungan.catatan_kontrol, input kontrol di form SOAP,
menu 🔔 Follow-up (Owner/Superadmin/Admin/Kasir/FO).
Caveat: item konsultasi dikenali via nama mengandung "konsul" (tak ada flag is_konsultasi);
sesuaikan _is_konsultasi_treatment() bila nama treatment konsultasi klinik berbeda.

NEXT: tidak ada task ter-prime. Pilih dari backlog (TODO_SEHATI.md §BACKLOG).
