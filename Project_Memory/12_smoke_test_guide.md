# Smoke Test Swagger UI — Panduan WSL

> Untuk dr. Hansen. App runtime di WSL, code source di drive E: (mount /mnt/e/).
> **Last updated:** 27 Mei 2026 (revisi: pivot ke WSL setelah Windows native blocked)

## Arsitektur
- Code: Windows `E:\Claude\Projects\sehati-emr-pos\sehati_clinic` (di-akses dari WSL via `/mnt/e/Claude/Projects/sehati-emr-pos/...`)
- App runtime: WSL Python + uvicorn
- MySQL: WSL native, user `klinik_dev`
- Akses Swagger: browser Windows → `http://localhost:8000/docs` (auto-forward WSL2)

## Step 0 — Reset sudo password (kalau lupa)
**PowerShell Windows:**
```powershell
wsl -u root
ls /home
passwd <username>
exit
```

## Step 1 — Cek Python di WSL
**WSL terminal:**
```bash
python3 --version
```
- ≥ 3.11 → lompat ke Step 3
- < 3.11 atau tidak ada → Step 2

## Step 2 — Install Python 3.11 (deadsnakes PPA)
```bash
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev
python3.11 --version
```

## Step 3 — Verify MySQL
```bash
mysql -u klinik_dev -p
# di prompt mysql:
USE db_sehati;
SELECT COUNT(*) FROM master_staf;
SELECT id_staf, username, role FROM master_staf LIMIT 5;
EXIT;
```
Catat username staf yang akan dipakai login.

## Step 4 — Navigate ke project
```bash
cd "/mnt/e/Claude/Projects/sehati-emr-pos/sehati_clinic"
```

## Step 5 — Venv & install
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

## Step 6 — Setup .env
```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(64))"  # catat outputnya
nano .env
# Edit:
#   DB_HOST=127.0.0.1
#   DB_USER=klinik_dev
#   DB_PASSWORD=<password klinik_dev>
#   DB_NAME=db_sehati
#   JWT_SECRET_KEY=<paste hasil generate>
# Save: Ctrl+O, Enter, Ctrl+X
```

## Step 7 — Test config
```bash
python -c "from app.config import settings; print('OK:', settings.db_host, settings.db_name)"
```

## Step 8 — Hash passwords
```bash
python ../tools/migrate_passwords.py
```

## Step 9 — Run server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Biarkan terbuka. Buka terminal WSL kedua kalau perlu kerja lain.

## Step 10 — Buka Swagger UI di browser Windows
`http://localhost:8000/docs`

## Step 11 — Test workflow
- `GET /health/db` → cek koneksi DB
- `POST /api/v1/auth/login` → dapat JWT
- Klik 🔓 Authorize → paste token
- `GET /auth/me` → verify profil
- `GET /pasien/cari?keyword=<nama>` → cari pasien
- `POST /kunjungan/lama` → daftar kunjungan baru
- `PATCH /kunjungan/{id}/status` → KONSULTASI
- `GET /dokter/pasien/{id}/header` → grid dashboard
- `POST /dokter/input-medis` → submit SOAP

## Common Errors

### "Address already in use" saat uvicorn
Port 8000 dipakai. Cek & kill:
```bash
sudo lsof -i :8000
kill -9 <PID>
```

### "Can't connect to MySQL server"
Cek MySQL jalan: `sudo service mysql status`
Cek port: `sudo netstat -tlnp | grep 3306` (harus muncul 127.0.0.1:3306)

### "ModuleNotFoundError: No module named 'app'"
Belum aktivasi venv. Run: `source .venv/bin/activate`

### Swagger UI tidak load dari browser Windows
- Pastikan uvicorn pakai `--host 0.0.0.0` (bukan 127.0.0.1)
- Pastikan WSL2 (bukan WSL1) — `wsl -l -v` harus VERSION = 2
- Restart WSL: dari PowerShell `wsl --shutdown`, lalu buka WSL lagi

## Endpoint Inventory (32 routes)
[Lihat file 08_roadmap.md untuk detail lengkap]
