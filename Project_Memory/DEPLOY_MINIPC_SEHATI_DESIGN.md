# Deploy Sehati eMR-POS ke mini PC klinik — Rencana Desain

Status: **RENCANA (belum dieksekusi)**. Disusun 16 Sep 2026 setelah mempelajari
stack Photodex (`E:\Claude\Projects\Clinic-photo`) yang sudah jalan di mesin yang
sama. Prinsip utama: **aditif & reversibel** — Photodex tidak boleh tersentuh.

## 0. Mesin target
- ASUS NUC 14 (N355), RAM 16GB (invoice; catatan Photodex sebut 8GB — cek `free -h`), NVMe 512 GB.
- Ubuntu Desktop, hostname & user `joderma-jemur`. SSH + Tailscale + Docker sudah ada.
- Menjalankan Photodex (Docker): `db` (postgres, internal), `backend` (127.0.0.1:8000), `web` (127.0.0.1:8080), `web-tls` (nginx di 192.168.1.10:80/443, `photodex.joderma.id`).
- **Akses Photodex nyata:** LAN → `photodex.joderma.id` (nginx). LUAR klinik → `joderma-jemur.tail730d69.ts.net` (Tailscale serve → 127.0.0.1:8080). Domain `.joderma.id` praktis hanya jalan di LAN.
- Port host terpakai: 8080, 8000, 5000, 8731, 5432 (+ 80/443 nginx). **8000 dipakai Photodex → Sehati pakai 8001.**

## 1. KEPUTUSAN AKSES (2026-09-16, direvisi): TAILSCALE SERVE
dr. Hansen: **lupakan subdomain-nginx dulu, pakai Tailscale saja.**
- Sehati diekspos via **`tailscale serve --bg --https=8443 http://127.0.0.1:8001`**.
- URL akses: **`https://joderma-jemur.tail730d69.ts.net:8443`** (port 8443; 443 dipakai Photodex).
- Sertifikat `.ts.net` diterminasi Tailscale → HTTPS sah → `COOKIE_SECURE=true` aman.
- **TANPA** DNS record, **TANPA** acme cert, **TANPA** sentuh nginx, **TANPA** gabung network Photodex. Sehati = stack Docker berdiri sendiri.
- Skenario pakai: (1) monitor mini PC → `http://localhost:8001`; (2) staff/HP dalam & luar klinik → Tailscale `:8443`.
- Subdomain-nginx = DITUNDA (opsional, hanya kalau perlu nama pendek di LAN nanti).

## 2. Arsitektur target Sehati
Stack terpisah (`/srv/sehati`), 2 container, jaringan internal sendiri:
- **sehati-db** — MySQL 8 / MariaDB. DB `db_sehati`, user `klinik_dev`. TIDAK dibuka ke host. Volume `sehati_db_data`.
- **sehati-app** — FastAPI/uvicorn (build dari repo). Publish **`127.0.0.1:8001:8000`** (loopback; Tailscale serve yang membukanya ke tailnet). Migrasi Alembic jalan otomatis saat start.

### Setting produksi wajib di `.env` Sehati (dibuat DI mini PC, tak ikut git)
- `SESSION_COOKIE_SECURE=true`
- `TRUSTED_PROXIES=127.0.0.1,::1` — Tailscale serve meneruskan dari loopback + set `X-Forwarded-For`/`X-Forwarded-Proto`; cocok dgn fix P1-3. (Default kita memang 127.0.0.1,::1 → mungkin tak perlu diubah.)
- DB password baru (kuat), beda dari dev: `db_user=klinik_dev`, `db_name=db_sehati`.
- `secret_key` sesi baru (random 48 byte). `APP_DEBUG=false`.

## 3. Langkah bertahap (dipandu satu-satu; approval tiap langkah yang menyentuh mini PC)
1. **Siapkan artefak deploy di repo** (desktop, aman — belum menyentuh mini PC): Dockerfile Sehati, `docker-compose.yml` (root; app+mysql), entrypoint (alembic upgrade → uvicorn), `.env.example`, `.dockerignore`. Verifikasi build lokal.
2. **Kirim ke mini PC** (rsync via SSH Tailscale; TANPA .env/backups/.venv/PHI).
3. **Buat `.env` produksi di mini PC** (rahasia digenerate di sana).
4. **Cek mesin**: `free -h`, port 8001 & 3306 bebas, `docker compose version`.
5. **`docker compose up -d --build`** → cek `sehati-db` healthy, `sehati-app` Up, migrasi jalan, `curl 127.0.0.1:8001/`.
6. **Buat akun awal** (CLI/seed minimal).
7. **`tailscale serve --bg --https=8443 http://127.0.0.1:8001`** → uji `https://joderma-jemur.tail730d69.ts.net:8443` dari HP di tailnet.
8. **Backup** DB Sehati (mysqldump terjadwal + enkripsi age, pola BACKUP.md Photodex).
9. **Smoke test** lengkap di HTTPS: login, kasir, apotek, membership, obat tertunda.

## 4. Ditunda (catatan celah, bukan penghambat)
- Subdomain-nginx (nama pendek LAN) — opsional.
- Enkripsi disk (LUKS); backup off-site; multi-branch P2-6 (saat cabang #2 nyata).
- Pantau resource: Postgres+MySQL+2 app berbagi RAM → `docker stats`, cek `free -h` dulu.

## 5. Aturan keamanan yang berlaku
- JANGAN commit/sync `.env`, `backup*.sql`, folder `backups/`, atau PHI klinik lain (`Medis Backup.sql`).
- `.env` produksi hanya hidup di mini PC.
- Photodex compose, container, & nginx TIDAK diubah sama sekali (jalur Tailscale terpisah total).

## 6. Progres eksekusi
- **Langkah 1 SELESAI (16 Sep 2026):** artefak Docker dibuat di `sehati_clinic/` — `docker-compose.yml`, `deploy/Dockerfile`, `deploy/entrypoint.sh` (wait-DB → alembic upgrade → uvicorn --no-proxy-headers), `deploy/requirements.txt`, `deploy/.env.sehati.example`, `deploy/README-DOCKER-MINIPC.md`, `.dockerignore`. Verifikasi offline lolos (YAML valid, bash/py syntax OK, 1 head Alembic 20260916_0200, app+migrations compile bersih). Build Docker sungguhan dilakukan di mini PC (sandbox tak ada Docker). BELUM menyentuh mini PC.
