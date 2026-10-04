# S1 — CSP + HSTS: keadaan sebenarnya, dan apa yang tersisa

**Diperiksa 2026-10-04 di laptop.** Dokumen ini menggantikan baris "S1 — CSP + HSTS"
di CLAUDE.md §8 dan `BACKLOG_KONSOLIDASI_2026-09-30.md` §4, yang keduanya menyebut S1
**belum dikerjakan**. Itu tidak benar.

---

## 1. Yang ternyata SUDAH ada

Commit `adb0459` ("security(headers): CSP + HSTS config-driven (S1)") sudah memasang
keduanya di `app/main.py` → `SecurityHeadersMiddleware` (pure-ASGI, sesuai B-031).

| Header | Status | Catatan |
|---|---|---|
| `X-Content-Type-Options: nosniff` | selalu | tanpa tombol |
| `X-Frame-Options: DENY` | selalu | tanpa tombol |
| `Referrer-Policy: strict-origin-when-cross-origin` | selalu | tanpa tombol |
| `Permissions-Policy: geolocation=(), microphone=(), camera=()` | selalu | tanpa tombol |
| **CSP** | **AKTIF & MENEGAKKAN** | default `security_csp_enabled=True`, `report_only=False` |
| **HSTS** | **ADA tapi MATI** | default `security_hsts_enabled=False` |

Kebijakan CSP yang sedang berjalan:

```
default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none';
form-action 'self'; img-src 'self' data:; font-src 'self' data:;
style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'
```

---

## 2. CSP tidak merusak apa pun — diverifikasi, bukan diasumsikan

CSP sedang **menegakkan** di klinik. Kalau ia memblokir sesuatu, fiturnya mati tanpa
error yang terlihat pengguna. Empat hal diperiksa:

| Yang diperiksa | Hasil |
|---|---|
| Sumber eksternal (`src`/`href`/`action` ke `http(s)://`) di 127 template | **nol** — aplikasi 100% self-host (DEC-073) |
| `fetch`/`axios`/`XHR` ke origin luar (dibatasi `connect-src 'self'`) | **nol** |
| `eval()` / `new Function` / `setTimeout("string")` di template | **nol** — penting, karena `'unsafe-inline'` **tidak** mengizinkan eval |
| Fitur HTMX yang butuh eval: `hx-vals="js:…"`, `hx-headers="js:…"`, kondisi `hx-trigger="[…]"`, `hx-on` | **nol dipakai** — htmx.min.js memang memuat `new Function`, tapi hanya di jalur fitur itu |
| Konsol browser di halaman login | **nol pesan** |

Kesimpulan: kebijakan sekarang aman dipertahankan apa adanya.

---

## 3. HSTS — terbukti jalan, tinggal dinyalakan di mini PC

Diuji di laptop (dinyalakan, diverifikasi, dimatikan lagi):

```
strict-transport-security: max-age=31536000
```

**SENGAJA tanpa `includeSubDomains`** — agar tidak memaksa HTTPS ke
`photodex.joderma.id` yang LAN-nya HTTP. Jangan ditambahkan tanpa memeriksa itu dulu.

### ⚠ HSTS itu lengket — jangan langsung 1 tahun

Begitu browser menerima HSTS, ia **menolak HTTP ke host itu** selama `max-age`, walau
HTTPS-nya rusak. Kalau Tailscale serve bermasalah, mini PC jadi tak terjangkau dari
browser yang terlanjur menyimpannya — dan menurunkan `max-age` butuh waktu menyebar ke
tiap browser yang pernah berkunjung.

**Rencana aman:** mulai `SECURITY_HSTS_MAX_AGE=86400` (1 hari), amati beberapa minggu,
baru naikkan ke `31536000`. Default di `.env.example` sudah diubah ke 86400.

**Yang harus dikerjakan di mini PC** (bukan dari laptop — deploy hanya dari desktop):

```bash
# di /srv/sehati/.env
SECURITY_HSTS_ENABLED=true
SECURITY_HSTS_MAX_AGE=86400
# lalu: docker compose up -d   (DI LUAR jam operasional klinik — CLAUDE.md §1.4)
```

Verifikasi sesudahnya:
`curl -sI https://joderma-jemur.tail730d69.ts.net:8443/web/login | grep -i strict`

---

## 4. Celah yang ditemukan: tombolnya tidak terdokumentasi

`SECURITY_CSP_*` dan `SECURITY_HSTS_*` **tidak ada di `.env.example`**. Setelan yang
hanya hidup sebagai default di `app/config.py` praktis tidak terlihat oleh siapa pun
yang menyiapkan `.env` produksi — ia akan menyalin `.env.example` dan tidak pernah tahu
tombol itu ada. Sudah ditambahkan (2026-10-04) berikut peringatan lengketnya HSTS.

---

## 5. Yang TERSISA dari S1 — dan kenapa tidak dikerjakan hari ini

Kebijakan sekarang memakai `'unsafe-inline'` di **`script-src`** dan **`style-src`**.
Itu melemahkan justru bagian CSP yang melindungi dari XSS: penyerang yang berhasil
menyuntikkan `<script>` ke halaman tetap dijalankan browser.

Menghapusnya bukan perubahan satu baris. Ukurannya (dari 127 template):

| Penghalang | Jumlah | Template | Nonce menolong? |
|---|---|---|---|
| Blok `<script>` inline | 52 | 40 | **Ya** — tinggal tambah `nonce` |
| **Handler inline** (`onclick`, `onsubmit`, `onchange`, `onkeydown`) | **89** | 37 | **TIDAK** — CSP memblokir semua handler inline apa pun noncenya. Harus diubah ke `addEventListener` |
| Blok `<style>` | 9 | — | **Ya** |
| **Atribut `style="…"`** | **275** | 33 | **TIDAK** — harus dipindah jadi kelas |

Jadi `script-src` bersih menuntut **89 handler diubah di 37 template**, dan `style-src`
bersih menuntut **275 atribut dipindah di 33 template**. Keduanya menyentuh perilaku UI
yang tidak punya test otomatis — risikonya bukan teoretis.

**Rekomendasi bertahap:**

1. **Nonce untuk blok `<script>` dan `<style>` lebih dulu** (61 titik, mekanis). Belum
   bisa menghapus `'unsafe-inline'`, tapi menyiapkan jalannya.
2. **Refactor 89 handler inline** per modul, bukan sekaligus — setiap modul diuji di UI
   laptop sebelum lanjut.
3. **Baru hapus `'unsafe-inline'` dari `script-src`**, pakai
   `SECURITY_CSP_REPORT_ONLY=true` dulu untuk mengumpulkan pelanggaran tanpa merusak.
4. `style-src` **terakhir** — 275 titik, dampak keamanannya paling kecil dari ketiganya.

⚠ Kebijakan CSP sekarang **tidak punya `report-uri`/`report-to`**, jadi pelanggaran
tidak terlihat oleh siapa pun. Sebelum langkah 3, itu perlu diputuskan: tanpa kanal
laporan, mode report-only tidak mengumpulkan apa-apa kecuali ada yang membuka konsol
browser.

**Butuh persetujuan dr. Hansen sebelum dimulai** — ini menyentuh 37+33 template.

---

## 6. Ringkas: status S1

| Bagian | Status |
|---|---|
| Header dasar (nosniff, frame, referrer, permissions) | ✅ selesai, selalu aktif |
| CSP terpasang & menegakkan | ✅ selesai, diverifikasi tidak merusak |
| CSP didokumentasikan di `.env.example` | ✅ 2026-10-04 |
| HSTS terpasang & terbukti jalan | ✅ 2026-10-04 |
| HSTS **dinyalakan di mini PC** | ⬜ menunggu — §3 |
| CSP tanpa `'unsafe-inline'` | ⬜ menunggu keputusan — §5 |
