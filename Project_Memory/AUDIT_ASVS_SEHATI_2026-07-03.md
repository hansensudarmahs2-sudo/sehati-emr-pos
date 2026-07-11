# Laporan Audit Keamanan Sehati eMR-POS — Berbasis OWASP ASVS 4.0.3

**Tanggal:** 3 Juli 2026
**Metode:** Audit kode sumber langsung (`sehati_clinic/app`, ~36.000 baris) + review Project_Memory.
**Target level:** ASVS Level 2 (aplikasi menangani data pasien = data sensitif).
**Sifat:** Self-assessment, bukan sertifikasi. Read-only — tidak ada kode yang diubah.

---

## 1. Ringkasan Eksekutif

Postur keamanan Sehati **kuat untuk sebuah MVP klinik** dan jauh di atas rata-rata aplikasi buatan sendiri. Fondasi auth benar secara arsitektural: **role di-fetch dari DB tiap request** (bukan percaya klaim token klien), **semua query ter-parameterisasi** (SQLAlchemy `select()`), **password bcrypt cost 12**, **CSRF penuh** di jalur web, **rate-limit login bertingkat**, dan **guard boot produksi** menolak JWT secret lemah.

Dari 6 item prioritas tertinggi di checklist (SQLi, IDOR, hashing, audit trail, headers, biometrik), **4 sudah aman**. Yang benar-benar bolong tinggal **2 kategori**:

1. **Audit trail hanya mencatat perubahan (CREATE/UPDATE/DELETE), belum mencatat AKSES-BACA rekam medis** (siapa membuka data pasien siapa). Ini kewajiban akuntabilitas khas EMR — gap paling penting yang tersisa.
2. **Security headers HTTP tidak ada** (CSP, HSTS, X-Frame-Options, X-Content-Type-Options) dan **deployment berjalan plain-HTTP di LAN tanpa TLS**.

Sisanya adalah *hardening* bertahap: kebijakan password minimal masih 6 karakter, tidak ada idle-timeout sesi, tidak ada enkripsi at-rest, dan belum ada pemindaian dependensi (CVE) otomatis.

**Tidak ditemukan temuan P0 (kritis-eksploitabel) di jalur auth/akses.** Kesimpulan ini konsisten dengan audit internal 2026-06-29.

**Skor kasar kesiapan ASVS L2:** ~68% terpenuhi, ~18% sebagian, ~14% belum. Cukup untuk operasi klinik terkontrol di LAN; **belum cukup** jika sistem dibuka ke jaringan tak-tepercaya / cloud tanpa perbaikan V9 & V14.4.

---

## 2. Status Per Kontrol

Legenda: ✅ Sudah · ⚠️ Sebagian · ❌ Belum · N/A

### V1 — Arsitektur & Threat Modeling

| # | Kontrol | Status | Temuan di kode |
|---|---------|:---:|----------------|
| 1.1 | Dokumen arsitektur & trust boundary | ✅ | `Project_Memory/02_architecture.md` + `ARSITEKTUR_*` lengkap. Diagram trust-boundary tunggal masih bisa diformalkan. |
| 1.2 | Akun layanan privilege minimal | ⚠️ | `.env` dev pakai user `klinik_dev` dgn password template `Klinik123!`. GRANT MySQL tidak tervalidasi di kode — **perlu cek: apakah user app `ALL PRIVILEGES` atau dibatasi?** |
| 1.4 | Trust boundary ditegakkan | ✅ | Connector satu-arah + pemisahan entitas terdokumentasi. |
| 1.5 | Validasi I/O lintas boundary | ⚠️ | Pydantic memvalidasi input API. Validasi schema di sisi penerima connector cloud→on-prem masih Phase 2. |
| 1.8 | Klasifikasi data sensitif | ⚠️ | Kesadaran ada (`export_service` punya PII-masking `PASIEN_HASH`), tapi **belum ada tabel klasifikasi formal** PII vs pseudonim vs operasional. |
| 1.11 | Logika bisnis kritikal tidak bisa di-bypass | ✅ | RBAC via `role_required` ditegakkan server-side; alur transaksi atomik. |

### V2 — Autentikasi

| # | Kontrol | Status | Temuan |
|---|---------|:---:|--------|
| 2.1.1 | Password min. 12 karakter | ❌ | Minimum saat ini **6 karakter / PIN 4** — lemah secara kebijakan (walau di-bcrypt). |
| 2.1.7 | Cek password bocor | ❌ | Tidak ada. Murah untuk on-prem (list statis). |
| 2.2.1 | Anti-brute-force | ✅ | `rate_limit.py`: cooldown bertingkat per-IP, hanya hitung gagal. |
| 2.4.1 | Hashing kuat | ✅ | `bcrypt.gensalt(rounds=12)` di `security.py`. Bukan MD5/SHA1. |
| 2.5.4 | Tidak ada credential default aktif | ⚠️ | Cek `seed_data/`: apakah admin awal dipaksa ganti password saat pertama login. `.env` template masih `Klinik123!`. |
| 2.7.x | 2FA untuk akun berhak-tinggi | ❌ | Belum ada. Owner/Superadmin/Dokter akses PII penuh tanpa faktor kedua. |
| 2.8.1 | Biometrik ≠ satu-satunya faktor auth | ✅/N/A | Auth aplikasi = username+password. Fingerprint (AT-series) terpisah sbg *presence*, tidak dijadikan secret auth. **Pertahankan pemisahan ini.** |

### V3 — Manajemen Sesi

| # | Kontrol | Status | Temuan |
|---|---------|:---:|--------|
| 3.2.1 | Token server-side, entropi cukup | ✅ | JWT HS256, secret 86 karakter; sesi diverifikasi via `is_logged_in` di DB tiap request. |
| 3.2.3 | Cookie `HttpOnly`/`Secure`/`SameSite` | ✅ | `web/routes/auth.py`: `httponly=True, samesite="lax", secure=COOKIE_SECURE`. ⚠️ `Secure` hanya aktif saat `COOKIE_SECURE=true` (wajib di produksi). |
| 3.3.1 | Logout invalidate sesi server-side | ✅ | `mark_logged_out` + cek `is_logged_in` di `get_current_user` (bukan sekadar hapus cookie). |
| 3.3.2 | Idle timeout | ❌ | Hanya expiry absolut 6 jam. **Tidak ada idle-timeout** — workstation klinik ditinggal = PII terbuka sampai 6 jam. |
| 3.5.x | Token tidak di URL | ✅ | Bearer header / cookie. Tidak ada token/ID di query string. |

### V4 — Kontrol Akses (RBAC)

| # | Kontrol | Status | Temuan |
|---|---------|:---:|--------|
| 4.1.1 | Ditegakkan server-side | ✅ | `deps.role_required()` di API + cek cookie/role di web routes. UI-hiding bukan satu-satunya proteksi. |
| 4.1.2 | Role tidak bisa dimanipulasi user | ✅ | Role dibaca dari `MasterStaf` di DB tiap request, bukan dari payload token. |
| 4.1.3 | Least privilege | ✅ | Role matrix terdefinisi (`04_api_rules.md`). |
| 4.2.1 | Proteksi IDOR | ✅ | Aman **by design**: model akses klinis (semua role klinis boleh lihat semua pasien dalam 1 klinik), bukan multi-tenant. Endpoint di-gate role. ⚠️ Kompensasi yang hilang: akses-baca tidak di-audit (lihat 7.2.1). |
| 4.3.1 | Fungsi admin otorisasi terpisah | ✅ | Role Owner/Superadmin terpisah dari user biasa. |

### V5 — Validasi Input & Encoding

| # | Kontrol | Status | Temuan |
|---|---------|:---:|--------|
| 5.1.1 | Anti mass-assignment | ✅ | Pydantic schema + whitelist `allowed_fields` (mis. `klinik_config_service`). |
| 5.2.x | Sanitasi input teks bebas | ⚠️ | Jinja2 autoescape aktif (encode saat output). Input SOAP/catatan disimpan mentah tapi di-encode saat render → XSS-tersimpan tercegah selama autoescape tidak dimatikan. |
| 5.3.4 | Parameterized query | ✅ | **Seluruh repo pakai `select()`/statement objek.** Satu-satunya `text()` (`pasien_repo`) pakai bound param `:prefix`. Tidak ada f-string SQL. Non-negotiable → lulus. |
| 5.3.3 | Output encoding | ✅ | Jinja2 autoescape. |
| 5.5.x | Deserialisasi aman | ✅ | JSON only, tidak ada `pickle`. |

### V7 — Logging & Audit

| # | Kontrol | Status | Temuan |
|---|---------|:---:|--------|
| 7.1.1 | Log tidak simpan data sensitif | ⚠️ | Log login catat username (bukan password) — ok. Tapi `audit_log.data_lama/data_baru` menyimpan snapshot JSON yang **bisa berisi PII**. Perlu kebijakan retensi & akses ke tabel audit. |
| 7.1.3 | Event keamanan dicatat | ✅ | Login gagal, logout, VOID, dll via `AuditService`. |
| 7.2.1 | **Akses rekam medis dicatat** | ❌ | **GAP UTAMA.** `AuditService` hanya punya shortcut mutasi (CREATE/UPDATE/DELETE/LOGIN/VOID). **Tidak ada `log_view`/pencatatan siapa MEMBUKA data pasien.** Untuk EMR ini kewajiban akuntabilitas, bukan opsional. |
| 7.3.1 | Log tahan-ubah | ⚠️ | "Append-only" hanya **konvensi** (komentar kode). Tidak ada mekanisme yang mencegah UPDATE/DELETE row `audit_log` oleh user DB. |

### V8 — Perlindungan Data

| # | Kontrol | Status | Temuan |
|---|---------|:---:|--------|
| 8.1.1 | Tidak di-cache di tempat tak aman | ❌ | Tidak ada header `Cache-Control: no-store` di halaman berisi PII. |
| 8.2.2 | Tidak simpan sensitif di client | ✅ | JWT di cookie `HttpOnly`, bukan localStorage. |
| 8.3.4 | Perlindungan sesuai klasifikasi | ⚠️ | Parsial — masking PII di export ada; belum menyeluruh. |
| 8.1.6 `[L3]` | Enkripsi at-rest | ❌ | Tidak ada enkripsi DB/disk. Untuk klaim data-sovereignty penuh: minimal disk-level (LUKS/BitLocker). |

### V9 — Komunikasi

| # | Kontrol | Status | Temuan |
|---|---------|:---:|--------|
| 9.1.1 | Semua komunikasi TLS | ❌ | Deployment guide menjalankan **plain HTTP :80** di LAN. app↔MySQL tanpa TLS. `COOKIE_SECURE=false`. LAN bukan alasan skip TLS. |
| 9.1.2 | Konfigurasi TLS kuat | ❌ | Belum ada TLS untuk dikonfigurasi. |
| 9.2.1 | Verifikasi sertifikat ke sistem eksternal | N/A | Connector cloud Phase 2. Catat: jangan `verify=False` saat diimplementasi. |

### V10 — Kode Berbahaya & Integritas

| # | Kontrol | Status | Temuan |
|---|---------|:---:|--------|
| 10.2.1 | Tidak ada backdoor | ⚠️ | Kode AI-generated; sudah melalui beberapa audit internal. Wajar, lanjutkan review berkala. |
| 10.3.2 | Update diverifikasi integritasnya | ❌ | Belum ada mekanisme delivery update on-prem yang ter-sign/terverifikasi. |

### V11 — Logika Bisnis

| # | Kontrol | Status | Temuan |
|---|---------|:---:|--------|
| 11.1.1 | Alur berurutan tidak bisa di-skip | ✅ | Transaksi atomik + gating status. |
| 11.1.4 | Anti-automation fungsi kritikal | ⚠️ | Rate-limit hanya di login. |

### V12 — File & Resource

| # | Kontrol | Status | Temuan |
|---|---------|:---:|--------|
| 12.1.1 | Upload dibatasi ukuran & tipe | ✅ | Logo: max 500KB, ext png/jpg + **cek magic bytes** (anti-spoof) di `klinik_config_service`. |
| 12.3.1 | Nama file tidak dipakai langsung (path traversal) | ✅ | Basename dinormalisasi ke nama tetap. |
| 12.4.1 | File di luar webroot / tidak dieksekusi | ⚠️ | Saat ini hanya logo (publik ok). **Foto pasien Phase 2 WAJIB auth-gated**, jangan di `/static` publik. |

### V13 — API & Web Service

| # | Kontrol | Status | Temuan |
|---|---------|:---:|--------|
| 13.1.1 | API = kontrol akses UI | ✅ | Keduanya pakai `role_required`/cek role. |
| 13.2.1 | Method HTTP dibatasi | ⚠️ | `finance.py` (viewer read-only) masih `501 Not Implemented`. **P1-5: 11 endpoint finance belum pasang guard auth** — sekarang tak bocor (501), tapi WAJIB tambah `dependencies=[Depends(role_required(...))]` SEBELUM diimplementasi. |
| 13.2.3 | Proteksi CSRF | ✅ | `CSRFMiddleware` double-submit, constant-time compare, coverage penuh `/web/*`. API bearer immune. |

### V14 — Konfigurasi

| # | Kontrol | Status | Temuan |
|---|---------|:---:|--------|
| 14.1.x | Tanpa file dev/debug di produksi | ⚠️ | `.env`: `APP_DEBUG=true`, `APP_ENV=development`. Boot-guard hanya cek JWT secret, **belum menolak `debug=true` di produksi**. File nyasar di root: `1`, `exit`, `debug_kunjungan.py`. `.env` sudah di `.gitignore`. |
| 14.3.2 | Error tidak bocorkan detail | ⚠️ | `/health/db` sudah diperbaiki. Tapi `debug=app_debug` → traceback bocor jika debug menyala di produksi. |
| 14.4.1 | Security headers aktif | ❌ | **Tidak ada CSP, HSTS, X-Frame-Options, X-Content-Type-Options.** Tidak ada middleware header maupun di conf nginx. |
| 14.5.2 | Scan dependensi (CVE) | ❌ | Tidak ada `pip-audit`/Dependabot/CI. |

---

## 3. Analisa

**Kekuatan (yang membedakan Sehati dari EMR buatan-sendiri biasa).** Tiga kesalahan paling mematikan di EMR — SQL injection, IDOR vertikal, dan penyimpanan password lemah — **semuanya sudah tertutup di level kode**, bukan sekadar diklaim. Pola auth-nya benar secara arsitektural: karena role selalu dibaca ulang dari DB, seorang penyerang tidak bisa "menaikkan" dirinya jadi Owner dengan mengedit token. CSRF dan rate-limit yang sering dilupakan aplikasi internal, di sini justru ada dan matang. Ini menunjukkan disiplin keamanan yang konsisten sepanjang basis kode.

**Sifat gap yang tersisa.** Hampir semua kelemahan bukan "lubang eksploitasi" melainkan **kontrol akuntabilitas & pengerasan yang hilang**:

- Gap **V7.2.1 (audit akses-baca)** unik karena bukan soal mencegah serangan, melainkan soal **membuktikan** siapa melihat rekam medis siapa. Saat ada sengketa pasien atau tuduhan kebocoran internal, sistem saat ini tidak bisa menjawab "siapa membuka data Ibu X tanggal sekian". Untuk EMR, ini risiko hukum/etik, bukan sekadar teknis.
- Gap **V9 (TLS) + V14.4.1 (headers)** saat ini diredam oleh fakta deployment di **LAN terisolasi**. Selama sistem tidak menyentuh jaringan tak-tepercaya, risikonya rendah. Tapi begitu ada Wi-Fi klinik yang dipakai bersama, kunjungan Phase 2 ke cloud, atau laptop tamu di jaringan yang sama, plain-HTTP berarti kredensial & PII bisa disadap dengan tool sepele (mis. sniffing ARP).
- Gap **V2.1.1 (password 6 char), V3.3.2 (idle timeout), V2.7 (2FA)** adalah kelemahan *policy* yang murah diperbaiki dan berdampak besar di konteks klinik (workstation bersama, staf datang-pergi).

**Konsistensi dengan audit sebelumnya.** Temuan ini selaras dengan `AUDIT_SEHATI_2026-06-29.md`. Beberapa item P2/P3 di sana sudah diperbaiki (boot-guard JWT, `/health/db`, exclude VOID). Yang belum tersentuh dan naik prioritas di lensa ASVS: **audit akses-baca, security headers, TLS produksi, idle-timeout.**

---

## 4. Saran Perbaikan (Berurut Impact-per-Effort)

**Quick win (jam-an, dampak tinggi):**

1. **Security headers (V14.4.1)** — tambah satu middleware yang set `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Content-Security-Policy` dasar, dan `Cache-Control: no-store` untuk halaman PII. ~30 menit, menutup beberapa kontrol sekaligus (14.4.1 + 8.1.1).
2. **Guard auth finance (V13.2.1 / P1-5)** — pasang `dependencies=[Depends(role_required(OWNER, ADMIN, SUPERADMIN))]` di router `finance.py` **sekarang**, sebelum ada data nyata.
3. **Idle timeout sesi (V3.3.2)** — tambah `last_activity` + auto-logout 15–30 menit. Lindungi PII di layar workstation yang ditinggal.
4. **Kebijakan password (V2.1.1)** — naikkan minimum ke 12 karakter untuk password (PIN tetap sesuai UX), tambah cek list password umum statis (V2.1.7).

**Menengah (menjelang produksi):**

5. **Audit akses-baca rekam medis (V7.2.1)** — tambah `AuditService.log_view(...)` dan panggil di endpoint detail/riwayat pasien & SOAP. Ini gap akuntabilitas terpenting. Pertimbangkan tabel/partisi terpisah agar volume tidak membebani `audit_log` utama.
6. **TLS produksi (V9)** — terminasi TLS di nginx (self-signed untuk LAN atau internal CA), set `COOKIE_SECURE=true`, aktifkan HSTS. Idealnya TLS juga untuk app↔MySQL.
7. **Hardening konfigurasi (V14.1/14.3.2)** — perluas boot-guard: tolak `APP_DEBUG=true` saat `APP_ENV=production`. Hapus file nyasar (`1`, `exit`, `debug_*.py`).
8. **Scan dependensi (V14.5.2)** — jadwalkan `pip-audit` (mingguan) via scheduled task atau CI.

**Lanjutan (data-sovereignty & skala):**

9. **Enkripsi at-rest (V8.1.6 L3)** — LUKS/BitLocker disk-level minimal; pertimbangkan enkripsi kolom untuk field paling sensitif.
10. **Immutability audit (V7.3.1)** — GRANT MySQL: user app hanya `INSERT/SELECT` di `audit_log`, tanpa `UPDATE/DELETE`. Sekaligus tuntaskan V1.2 (least-privilege DB grant).
11. **2FA (TOTP) untuk Owner/Superadmin/Dokter (V2.7)** — on-prem tetap bisa via TOTP.
12. **Klasifikasi data formal (V1.8)** — tabel klasifikasi PII/pseudonim/operasional sebagai fondasi kontrol lain.

---

## 5. Keuntungan vs Kerugian — Dengan atau Tanpa Perbaikan

### Jika DIPERBAIKI

**Keuntungan:**
- **Akuntabilitas hukum/etik terpenuhi** — audit akses-baca membuat Sehati bisa mempertanggungjawabkan setiap akses rekam medis; krusial saat sengketa atau audit regulator.
- **Aman dibuka ke jaringan lebih luas** — dengan TLS + headers, sistem siap untuk Wi-Fi bersama, multi-cabang, dan langkah cloud Phase 2 tanpa risiko penyadapan.
- **Klaim "data sovereignty" jadi kredibel** — enkripsi at-rest + audit immutable mengubah klaim pemasaran jadi kontrol nyata yang bisa ditunjukkan.
- **Permukaan serangan mengecil di titik yang tepat** — idle-timeout & password policy menutup jalur paling realistis di klinik (workstation bersama, shoulder-surfing).

**Kerugian/biaya:**
- Waktu engineering: quick-win ~1 hari; paket menengah ~3–5 hari; lanjutan bertahap.
- Sedikit gesekan operasional: idle-timeout & password 12-char butuh sosialisasi ke 8 staf.
- TLS self-signed di LAN memunculkan warning browser (sekali setup trust / internal CA).

### Jika TIDAK DIPERBAIKI

**Keuntungan (jangka sangat pendek):**
- Tidak ada biaya waktu sekarang; fokus tetap ke fitur (booking, inventory, komisi).
- Selama **murni LAN terisolasi & staf tepercaya**, risiko harian tetap rendah — fondasi sudah aman dari serangan klasik.

**Kerugian/risiko:**
- **Tidak bisa membuktikan siapa mengakses rekam medis** — bila ada kebocoran internal atau tuduhan, tidak ada jejak. Ini risiko terbesar & tidak bisa direkonstruksi surut (data akses yang tak dicatat hilang selamanya).
- **PII & kredensial bisa disadap** begitu jaringan tidak lagi sepenuhnya terisolasi (tamu, Wi-Fi bersama, cloud Phase 2).
- **Workstation ditinggal = rekam medis terbuka** hingga 6 jam.
- **Utang keamanan menumpuk** — makin banyak modul (finance, cloud) dibangun di atas fondasi tanpa TLS/audit-baca, makin mahal retrofit-nya nanti.
- **Klaim data-sovereignty jadi lemah** jika diuji: tanpa enkripsi at-rest & audit immutable, klaim sulit dipertahankan.

### Rekomendasi

Kerjakan **quick-win (1–4) sekarang** — biayanya jam-an, menutup gap dengan dampak paling nyata di konteks klinik. **Paket menengah (5–8) jadikan gerbang wajib sebelum**: (a) sistem menyentuh jaringan non-LAN-terisolasi, atau (b) modul finance/cloud Phase 2 di-*go-live*. **Paket lanjutan (9–12)** dijadwalkan seiring klaim data-sovereignty diformalkan dan skala bertambah. Fondasi sudah kokoh; yang tersisa adalah mengubah "aman dari serangan" menjadi juga "akuntabel & tahan saat konteks berubah".

---

*Berbasis OWASP ASVS 4.0.3 Level 2. Alat self-assessment, bukan sertifikasi resmi. Audit read-only — tidak ada kode aplikasi yang diubah.*
