# Sehati eMR-POS — image produksi (mini PC klinik, Docker).
# Build context = folder sehati_clinic/ (lihat docker-compose.sehati.yml).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Jakarta

WORKDIR /app

# `age` — WAJIB untuk Export Paket Klinis (paket berisi SOAP tidak boleh ditulis
# polos; lihat app/services/clinical_export_batch.py).
#
# ⚠ KENAPA INI PERLU, padahal backup terenkripsi sudah jalan sejak 2026-09-17:
#   `deploy/backup.sh` dijalankan di HOST mini PC, jadi ia memakai `age` milik
#   host. Ekspor klinis dijalankan dari TOMBOL UI, yaitu DI DALAM container —
#   dan image ini `python:3.11-slim` tanpa apt-get apa pun. Tanpa baris di bawah,
#   tombolnya menolak jalan di klinik dengan "Program `age` tidak terpasang".
#
# `age --version` di akhir DISENGAJA: kalau paketnya tidak ada di repositori,
# build GAGAL di sini — bukan menghasilkan image yang fiturnya mati diam-diam.
# Kalau suatu saat gagal, alternatifnya unduh biner resmi dari
# github.com/FiloSottile/age/releases lalu salin ke /usr/local/bin/age.
RUN apt-get update \
    && apt-get install -y --no-install-recommends age \
    && rm -rf /var/lib/apt/lists/* \
    && age --version

# Deps dulu (layer cache): hanya requirements → tidak rebuild saat kode berubah.
COPY deploy/requirements.txt /app/deploy/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/deploy/requirements.txt

# Kode aplikasi + yang dibutuhkan runtime (migrasi, alembic.ini, static).
COPY app/ /app/app/
COPY migrations/ /app/migrations/
COPY alembic.ini /app/alembic.ini
COPY static/ /app/static/
COPY deploy/entrypoint.sh /app/deploy/entrypoint.sh
RUN chmod +x /app/deploy/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
