# Sehati eMR-POS — image produksi (mini PC klinik, Docker).
# Build context = folder sehati_clinic/ (lihat docker-compose.sehati.yml).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Jakarta

WORKDIR /app

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
