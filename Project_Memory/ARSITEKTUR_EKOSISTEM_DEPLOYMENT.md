# ARSITEKTUR EKOSISTEM & DEPLOYMENT — Sehati + DermAI + Antropometri

**Disusun:** 2026-06-29 · diskusi dr. Hansen · companion untuk CONTRACT_SEHATI_DERMAI_v0.2.md & CONTRACT_SEHATI_ANTROPOMETRI_v0.1.md
**Sifat:** Catatan arsitektur (bukan kode). Pegangan saat implementasi konektor + deployment.

---

## 1. Topologi

**Target (produksi): 2 host di LAN klinik.**
- **PC-A (klinik):** Sehati (FastAPI) + MySQL + **Antropometri** (numpang, ringan).
- **PC-B (klinik):** **DermAI** sendiri — GPU + Qdrant + storage. Berat (YOLO lokal + klien cloud + async).
- **Klien:** HP / PC / laptop → **browser** via **WiFi klinik**. Tidak ada app native (itu Phase 4).
  HP justru plus untuk DermAI (kamera browser).

**Live/stress test awal: 1 PC** menjalankan ketiganya (lihat §6 Migrasi 1→2 PC). Sah & disengaja
sebagai skenario beban terberat (semua + GPU + MySQL menumpuk). PC test tunggal sebaiknya ber-GPU.

---

## 2. Jaringan & Offline

- **Operasi inti = LAN saja, TIDAK butuh internet:** Sehati EMR/POS, intake, buka UI modul, simpan,
  **YOLO lokal (GPU)**, kalkulasi antropometri lokal. Klien WiFi klinik → server internal langsung.
- **Butuh internet HANYA: langkah cloud-AI di dalam modul** (DermAI analisa cloud, Antropometri
  laporan AI). Internet putus → foto/case/metrik tetap aman, **verdict AI tertunda**. Modul WAJIB
  degrade gracefully (antri + retry saat internet balik), BUKAN crash. Sejalan dgn "run in background
  sampai output cloud diterima".
- **Data keluar klinik = hanya JSON de-identified** (hasil YOLO / metrik antropometri). **Tidak ada
  ID, tidak ada gambar.** Hasil cloud ditangkap modul masing-masing. Sehati lepas total dari cloud/gambar.
- **SYARAT offline-UI:** ketiga app **WAJIB self-host aset frontend** (no CDN). Sehati sudah (DEC-073);
  DermAI & Antropometri harus mengikuti, kalau tidak internet mati = UI rusak.
- **HP di luar WiFi klinik:** tidak relevan sekarang (HP hanya di WiFi klinik). Kalau nanti perlu akses
  dari luar → Tailscale/Cloudflare Tunnel. Tanpa itu, LAN sudah cukup.

---

## 3. Integrasi (ringkas; detail di kontrak)

- Sehati `POST /intake` (Bearer) → modul balas `{id, url}`. Sehati simpan id, buka `url` di window/tab.
- **`return_url` (refinement baru):** Sehati sertakan `return_url` di payload intake. Setelah
  **Simpan** / **Simpan & Analisa**, modul **REDIRECT browser balik ke `return_url`** — JANGAN pakai
  `window.close()` (rapuh, sering gagal di browser HP & hanya jalan utk window hasil `window.open`).
  - **Simpan & Analisa:** modul **balik cepat ke Sehati**, analisa cloud lanjut di background; hasil
    dilihat belakangan via link `case_id` yang Sehati simpan. Pola: **serahkan → balik cepat → lihat hasil nanti.**
- **`url` membawa signed token (kedaluwarsa singkat)** → buka di perangkat apa pun tanpa login ulang.
- **`url` & `base_url` WAJIB alamat LAN yang terjangkau klien** (mis. `http://pc-a.local:PORT`),
  **JANGAN `localhost`** — kalau localhost, hanya bisa dibuka di PC itu sendiri, klien lain gagal
  (berlaku bahkan saat masih 1 PC).

> TODO kontrak: tambahkan `request_meta.return_url` ke schema v0.2/v0.1 saat kontrak difinalkan.

---

## 4. Keputusan Docker

**Docker ≠ pengganti kontrak HTTP.** Beda lapisan: kontrak = bahasa antar-app (wajib); Docker = cara
membungkus/menjalankan tiap app (opsional). Di dalam container pun mereka tetap saling panggil via HTTP.

- **DermAI → dockerize (disarankan).** Multi-komponen (app + engine + Qdrant + GPU). `docker compose up`
  di PC-B menyalakan semua sekaligus, reproducible, `restart: always` menjaga background service tetap
  hidup (penting utk async cloud). GPU via NVIDIA container toolkit (WSL2).
- **Sehati + Antropometri → native dulu** (sudah jalan: uvicorn + MySQL). Dockerisasi menyusul, opsional.

---

## 5. Rencana Port (hindari tabrakan di 1 PC)

| Service | Port |
|---|---|
| Sehati (FastAPI) | 8000 |
| Antropometri (FastAPI) | 8051 |
| **DermAI app** | **8100** ⚠️ (default-nya 8000, WAJIB diubah agar tak tabrakan dgn Sehati) |
| DermAI engine | 9000 |
| Qdrant | 6333 |
| MySQL | 3306 |

---

## 6. Migrasi 1 PC → 2 PC (tanpa rewrite)

Bisa mulai 1 PC lalu pisah 2 PC **hanya dengan ubah config**, ASALKAN sejak awal:
1. **base_url tiap modul = config (.env)**, bukan hardcode. Sehati: `dermai_base_url`, `antro_base_url`.
2. **Port tak tabrakan** (lihat §5) — terutama Sehati vs DermAI (dua-duanya default 8000).
3. **`url` balikan modul = alamat LAN**, bukan localhost (§3).
4. **GPU**: 1-PC test sebaiknya mesin GPU; saat split, GPU ikut ke PC-B.

**Aksi split:** ganti `dermai_base_url` dari `http://localhost:8100` → `http://pc-b.local:8100`. Selesai.
Tidak ada perubahan kode. Stress test 1 PC = beban terberat; kalau lolos, split hanya menambah headroom.

---

## 7. Prinsip Pengikat

- **Tiga app tetap mandiri** (DB sendiri-sendiri), disambung **hanya via kontrak HTTP** — bukan share DB.
- **Sehati = master/otak**; modul menyesuaikan.
- **Privasi:** gambar & ID tak pernah ke Sehati maupun ke cloud; YOLO lokal; cloud hanya JSON de-identified.
