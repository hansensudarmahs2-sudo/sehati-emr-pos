#!/usr/bin/env bash
# Entrypoint Sehati: tunggu DB siap -> migrasi Alembic -> jalankan uvicorn.
set -euo pipefail

echo "[entrypoint] Menunggu database ${DB_HOST:-sehati-db}:${DB_PORT:-3306} ..."
python - <<'PY'
import os, time, sys
import pymysql
host = os.getenv("DB_HOST", "sehati-db")
port = int(os.getenv("DB_PORT", "3306"))
user = os.getenv("DB_USER", "klinik_dev")
pw   = os.getenv("DB_PASSWORD", "")
db   = os.getenv("DB_NAME", "db_sehati")
for i in range(60):
    try:
        pymysql.connect(host=host, port=port, user=user, password=pw, database=db,
                        connect_timeout=3).close()
        print(f"[entrypoint] DB siap (percobaan {i+1}).")
        sys.exit(0)
    except Exception as e:
        print(f"[entrypoint] DB belum siap ({i+1}/60): {e}")
        time.sleep(2)
print("[entrypoint] DB tidak siap setelah 120 dtk — batal.", file=sys.stderr)
sys.exit(1)
PY

echo "[entrypoint] Menjalankan migrasi Alembic (upgrade head) ..."
alembic upgrade head

echo "[entrypoint] Start uvicorn di 0.0.0.0:8000 ..."
# --no-proxy-headers: uvicorn TIDAK menulis ulang request.client; logika XFF
# ditangani app (get_client_ip + TRUSTED_PROXIES, fix P1-3) supaya deterministik.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers
