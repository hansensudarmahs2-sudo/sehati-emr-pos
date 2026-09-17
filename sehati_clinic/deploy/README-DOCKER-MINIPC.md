# Runbook Deploy Sehati (Docker) — mini PC klinik

Stack berdiri sendiri, terpisah dari Photodex. Akses via Tailscale serve.
Notasi: `[desktop]` = mesin kerja, `[minipc]` = mini PC (SSH/monitor).

## 1. Kirim kode ke mini PC  [desktop]
Repo di-rsync ke `/srv/sehati` TANPA .env/backups/.venv/*.sql (lihat langkah 2 chat).

## 2. Persiapan sekali  [minipc]
```bash
sudo mkdir -p /srv/sehati && sudo chown -R "$USER":"$USER" /srv/sehati
cd /srv/sehati
docker compose version    # pastikan compose v2 ada
```

## 3. Buat .env produksi  [minipc]  (rahasia digenerate DI SINI)
```bash
cd /srv/sehati
cp deploy/.env.sehati.example .env
python3 -c "import secrets; print('DB_PASSWORD='      + secrets.token_urlsafe(24))"
python3 -c "import secrets; print('DB_ROOT_PASSWORD=' + secrets.token_urlsafe(24))"
python3 -c "import secrets; print('JWT_SECRET_KEY='   + secrets.token_urlsafe(48))"
nano .env    # tempel 3 nilai di atas; pastikan APP_DEBUG=false, COOKIE_SECURE=true
grep -c $'\r' .env || true   # harus 0 (tidak ada CRLF)
```

## 4. Cek mesin  [minipc]
```bash
free -h                              # RAM cukup (Postgres+MySQL+app)
sudo ss -ltnp | grep -E ':8001|:3306' || echo "8001 & 3306 bebas"
```

## 5. Jalankan  [minipc]
```bash
cd /srv/sehati
docker compose up -d --build         # build pertama beberapa menit
docker compose ps                    # sehati-db healthy, sehati-app Up
docker compose logs -f sehati-app    # lihat: DB siap -> alembic upgrade -> uvicorn
curl -s http://127.0.0.1:8001/health # {"status":"ok",...}
```
Kalau `sehati-app` restart terus: `docker compose logs sehati-app` — biasanya .env
(password DB tak cocok, atau JWT_SECRET_KEY < 32 char, atau APP_DEBUG=true).

## 6. Akun awal  [minipc]
(ditentukan di langkah chat — via seed / CLI. Jangan seed-demo di produksi.)

## 7. Buka HTTPS via Tailscale  [minipc]
```bash
sudo tailscale serve --bg --https=8443 http://127.0.0.1:8001
tailscale serve status
```
Akses: `https://joderma-jemur.tail730d69.ts.net:8443` (dari perangkat di tailnet).
Persisten lintas reboot. Monitor mini PC sendiri cukup `http://localhost:8001`.

## 8. Update kode berikutnya  [desktop]
rsync ulang -> `[minipc] cd /srv/sehati && docker compose up -d --build`
(volume `sehati_db_data` & `sehati_uploads` TIDAK tersentuh; migrasi jalan otomatis).
JANGAN `docker compose down -v` (–v menghapus database!).

## Batalkan / bersihkan (kalau perlu)
```bash
docker compose down                  # stop, DATA AMAN (volume tetap)
sudo tailscale serve --https=8443 off
```
