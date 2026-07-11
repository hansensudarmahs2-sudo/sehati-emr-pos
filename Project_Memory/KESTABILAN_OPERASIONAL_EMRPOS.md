# Design Note — Kestabilan & Ketahanan Operasional eMR-POS + Roadmap Antrian

**Status:** 🟠 DESIGN / DISKUSI (belum kode). **Dibuat:** 2026-07-07 · diskusi dr. Hansen.
**Konteks deployment:** 1 PC server (Ubuntu mini-PC), klinik utama via LAN + cabang remote via Cloudflare.
**Terkait:** `raw_idea_070726.md` (ide antrian), `EMRPOS_MINI_CONTINGENCY_DESIGN.md` (SPOF/degraded), `deployment/B3_DEPLOYMENT_GUIDE.md`, `AUDIT_ASVS_*`.

> Dokumen ini jadi **syarat masuk (entry checklist)** sebelum fitur ber-polling apa pun (raw_idea #1–#7) dibangun.

---

## 1. Prinsip pemandu

**Jalur kritis operasional — pendaftaran, SOAP, kasir, serah obat — tidak boleh pernah melambat karena fitur "enak-punya"** (warna antrian, badge, tracking publik, laporan). Semua ide di `raw_idea_070726.md` adalah enak-punya; tak satu pun boleh menyandera kasir/SOAP.

---

## 2. Kondisi nyata sekarang (terverifikasi di kode, 2026-07-07)

- **Sudah polling tiap 10 detik di 5 layar antrian**: `apotek/dokter/kasir/kunjungan/perawat_antrian` (`hx-trigger="load, every 10s"`). Baseline beban BUKAN nol.
- **1 worker uvicorn** (systemd `ExecStart` tanpa `--workers`). Route sync (`def`) → jalan di threadpool (~40 thread default).
- **Pool DB**: `pool_size=10 + max_overflow=20` = maksimum 30 koneksi (`pool_pre_ping=True`, `pool_recycle=280`).
- **Belum ada cache sisi server** untuk endpoint yang di-poll → tiap poll = query DB baru.
- **`audit_log` belum ada indeks eksplisit** di `waktu`/`id_pasien` (tumbuh makin cepat setelah audit-baca dipasang).

Ilustrasi: 6 station buka layar antrian @10s = ~36 query antrian/menit terus-menerus, memukul DB langsung, lewat satu proses.

---

## 3. Ancaman utama

**Akar kopling bukan "query tercampur", tapi SUMBER DAYA BERSAMA** (satu pool + satu worker). Rantai kegagalan paling realistis:

> Banyak poller (atau 1 laporan berat saat jam sibuk) → koneksi/thread tertahan → **pool 30 habis** → request baru termasuk *kasir* antre/timeout → **kasir seolah hang** padahal DB sehat.

Ancaman lain:
- **SPOF**: PC/listrik/disk-penuh/MySQL-crash → sistem berhenti (diterima; mitigasi = eMR-POS Mini + ops di §6).
- **Landing page publik (raw_idea #2)**: tak-terautentikasi, dipoll banyak HP, lewat Cloudflare → kandidat #1 spike/DoS tak sengaja. **DITUNDA** (lihat §7).
- **`audit_log` membengkak** → query lambat + disk penuh.

---

## 4. Interval polling vs Cache (analisis)

**Interval dan cache menyelesaikan masalah berbeda:**

Tanpa cache, beban ~ linear dengan (jumlah client × frekuensi). Contoh 6 station:
| Interval | Req/menit per client | Total query/menit |
|---|---|---|
| 5 detik | 12 | 72 |
| 10 detik | 6 | 36 |
| 40 detik | 1,5 | 9 |

→ 40s ≈ 4× lebih ringan dari 10s, 8× dari 5s — **tapi hanya berlaku tanpa cache.**

**Dengan cache sisi server (TTL):**
- **Beban DB** ditentukan **TTL**, bukan interval. Cache TTL 10s → DB dihit ~1×/10s **berapa pun jumlah client/kecepatan poll**. Jadi 5s+cache10s ≈ beban DB 40s.
- **Beban web/CPU/jaringan** tetap dipengaruhi interval (tiap request makan slot thread + serialisasi + bandwidth, walau murah).

**Trade-off sesungguhnya = kesegaran vs beban.** Interval 40s = data bisa basi 40s. Jangan pakai interval panjang **sebagai pengganti cache** — itu mengorbankan kesegaran dan tetap boros bila client polling barengan.

**Pola yang disarankan (pakai keduanya, disetel terpisah):**
- Interval per layar sesuai kebutuhan kesegaran: **FO ~15s**, **dokter/perawat ~30s atau manual**, layar non-kritis **40–60s**.
- **Cache sisi server TTL pendek (mis. 10s)** untuk membatasi beban DB apa pun jumlah client.
- **Pause polling saat tab tidak aktif** (Page Visibility API) — station ditinggal semalaman berhenti memukul server.
- **ETag / 304 Not Modified** — data tak berubah → balas 304 mungil, tanpa render ulang.

---

## 5. Mitigasi (urut ROI tertinggi)

1. **Cache sisi server untuk semua endpoint yang di-poll** (list antrian, badge, kelak landing). Simpan hasil 5–10s per (layar+filter). Dampak: 50 poller = 1 query DB/interval. Meringankan sistem yang SEDANG berjalan + membuat semua fitur antrian aman. **Prioritas #1.**
2. **Batasi blast-radius laporan berat**: jalankan off-peak atau pasang `statement_timeout` MySQL, agar 1 laporan tak menyandera pool saat jam klinik.
3. **Worker sizing hati-hati**: 2–4 worker agar 1 request lambat tak memblokir semua — tapi worker × pool_size = total koneksi → sesuaikan `max_connections` MySQL. Keputusan tuning, bukan asal tambah.
4. **Higiene polling**: pause tab-hidden, backoff saat error, interval sesuai §4.
5. **Indeks `audit_log`** (`waktu`, `id_pasien`, `id_staf`) + rencana retensi/arsip bulanan sebelum membengkak.
6. **Cetak thermal non-blocking**: printer macet/habis kertas tak boleh menghentikan pendaftaran.

---

## 6. Ops / SPOF (menuju & pasca go-live)

UPS · backup harian yang **diuji restore** · monitor disk penuh · health-check + auto-restart systemd · jendela maintenance untuk migrasi Alembic (restart menjatuhkan request in-flight) · eMR-POS Mini sebagai degraded-mode cabang remote.

---

## 7. Keputusan roadmap antrian (dr. Hansen, 2026-07-07)

- **raw_idea #2 dipecah:**
  - **Fase awal (internal, aman):** generate **nomor antrian** (booking diselipkan sesuai jam janji, bukan FIFO murni) + **cetak thermal**. Tanpa landing publik → QR belum menunjuk ke mana-mana; cukup cetak nomor (boleh sisakan field token di data untuk nanti).
  - **Fase publik (DITUNDA ≥6 bulan setelah live-run):** landing page + QR tracking pasien di gadget. Dibangun dengan cache + rate-limit + isolasi. Ditunda karena permukaan publik = risiko kestabilan tertinggi; 6 bulan live memberi data beban riil untuk kalibrasi.
- **Cetak thermal wajib non-blocking.**

**Roadmap fase awal (semua low-risk dgn cache):**
1. Fondasi **cache endpoint polled + indeks `audit_log`** (menguntungkan sistem sekarang, de-risk semua fitur antrian).
2. Nomor antrian internal + thermal.
3. History SOAP panel kanan-bawah (fetch sekali + lazy-load; indeks `pemeriksaan(id_pasien, waktu)`).
4. Badge notifikasi per role (1 endpoint gabungan, ikut poll antrian yang ada + cache per-role).
5. Skip/lewati (setelah nomor antrian solid).
6. Monitoring antri bayar (laporan periodik dari audit log; bukan real-time).
7. Reminder follow-up (batch semalam / saat dashboard dibuka; indeks query "due").

**Fase publik (≥6 bulan live):** landing page + QR tracking.

---

## 8. Entry checklist (WAJIB lolos sebelum fitur ber-polling di-merge)

- [ ] Endpoint terpisah & **ringan** (tidak menyentuh query dashboard/laporan berat).
- [ ] **Cache sisi server** dgn TTL wajar; DB tak dihit per-request.
- [ ] Interval polling **disetel sesuai kebutuhan kesegaran** layar (bukan default 10s buta).
- [ ] **Pause saat tab hidden** + backoff saat error.
- [ ] Tidak menambah query per-request ke jalur kritis (kasir/SOAP/serah).
- [ ] Payload minimal (khusus publik nanti: tanpa PHI, token acak, rate-limit, kedaluwarsa).
- [ ] Ada indeks pendukung untuk query barunya.

---

## 9. Aturan & Batasan Cache (regulasi wajib)

> Kekhawatiran valid: cache yang tidak diregulasi bisa mengganggu sistem sendiri — bahayanya HALUS (diam-diam menampilkan data keliru), berbeda dari sistem lambat yang kelihatan. Bagian ini = pagar resmi sebelum cache dibangun.

**Risiko yang diwaspadai:**
- **Data basi (stale):** cache menyajikan data lama setelah aslinya berubah (mis. kasir tandai LUNAS tapi layar masih "antri bayar").
- **Bocor antar-user/role:** response terfilter (mis. "Antrian Saya" dr. A) tersaji ke user lain karena kunci cache kurang lengkap. Salah data + privasi.
- **Memori membengkak:** cache tanpa batas → OOM → proses mati.
- **Inkoherensi multi-worker:** cache in-memory = per-worker; "buang cache" di satu worker tak sampai ke lainnya. Sadari sebelum menambah worker.
- **Thundering herd:** entri populer kedaluwarsa → banyak miss serentak memukul DB.

**Aturan wajib (setiap cache HARUS mematuhi):**
1. **Hanya tampilan read-heavy non-otoritatif** (daftar antrian, badge). **DILARANG** cache data untuk keputusan/tulis — saldo, stok, status bayar di jalur keputusan **selalu baca langsung ke DB**. Ini garis pemisah terpenting.
2. **TTL pendek (5–10 detik) = basi terbatas + sembuh sendiri.** Untuk v1 utamakan TTL-waktu (bodoh tapi terprediksi) di atas invalidasi-berbasis-event yang rawan bug.
3. **Kunci cache lengkap:** sertakan role, id_staf, filter, klinik (semua dimensi yang mengubah isi). Ragu → jangan cache data terpersonalisasi.
4. **Batasi ukuran** (LRU + jumlah entri maks). TTL pendek juga otomatis membuang yang lama.
5. **Ruang lingkup kecil:** segelintir endpoint panas, bukan "cache semuanya".
6. **Kill-switch + observability:** satu flag untuk mematikan cache seketika bila berulah + log hit/miss.
7. **Jangan cache error/empty** sebagai hasil sah (hindari negative-cache tak sengaja).

**Kenapa rencana cache antrian tetap aman:** layar antrian SUDAH refresh tiap 10 detik → datanya memang sudah "basi hingga 10 detik" secara desain. Cache 10 detik di belakangnya = kebasian **tetap sama**, beban DB turun drastis. Keringanan tanpa mengorbankan apa pun yang belum dikorbankan. Cache ini display-only; kasir/SOAP/serah tetap baca DB langsung.

---

## 10. Status implementasi (2026-07-07) — Fondasi cache + indeks

**SUDAH dibangun (perlu smoke-test live di WSL):**
- **Util cache** `app/core/ttl_cache.py`: TTL, LRU terbatas, single-flight, kill-switch, metrics. Unit-test hijau (7 skenario).
- **Helper** `render_cached()` di `app/web/routes/_shared.py`: cache BYTES fragment hasil render; auth dicek di luar cache.
- **Diterapkan ke 4 endpoint antrian form-free** (TTL default 12s):
  - shared key: `/apotek/list` (`antrian:apotek`), `/kasir/antrian/list` (`antrian:kasir`).
  - per-user key: `/dokter/antrian/list` (`antrian:dokter:{id_staf}`), `/ruang-tindakan/antrian/list` (`antrian:perawat:{id_staf}`).
- **`/kunjungan/list` SENGAJA TIDAK di-cache** — fragment-nya (`_antrian_content.html`) mengandung form+CSRF; caching shared bisa membocorkan token antar-user. Ditunda (butuh per-user keying atau refactor fragment).
- **Indeks `audit_log`** via migrasi defensif `20260707_0100_audit_log_indexes` (`ix_audit_log_waktu`, `ix_audit_log_target`).

**Kill-switch (rollback instan tanpa ubah kode):** set env `SEHATI_CACHE_ENABLED=false` lalu restart → semua endpoint kembali baca DB langsung. TTL bisa disetel via `SEHATI_ANTRIAN_CACHE_TTL` (detik).

**Belum diuji:** boot FastAPI + klik layar antrian aktual + `alembic upgrade head`. Wajib dijalankan user di WSL/venv.

---

*Living document — status: DESIGN-ONLY, tidak ada perubahan kode dari dokumen ini. Perbarui saat sizing worker/pool difinalkan atau saat fase publik dibuka.*
