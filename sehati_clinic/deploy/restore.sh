#!/usr/bin/env bash
# PEMULIHAN BENCANA (DESTRUKTIF): restore backup ke DB LIVE db_sehati.
# Membuat safety-backup dulu, lalu minta konfirmasi ketik 'RESTORE'.
# HANYA dipakai saat benar-benar perlu memulihkan. Jalankan dari /srv/sehati:
#   bash deploy/restore.sh backups/sehati_db_XXXX.sql.gz
set -euo pipefail
cd "$(dirname "$0")/.."
SRC="${1:-}"; [ -z "$SRC" ] && { echo "Usage: bash deploy/restore.sh <file.sql.gz>"; exit 1; }
[ -f "$SRC" ] || { echo "File tak ada: $SRC"; exit 1; }
echo "PERHATIAN: ini akan MENIMPA database live db_sehati dengan isi: $SRC"
echo "Safety-backup dibuat dulu."
bash deploy/backup.sh
read -r -p "Ketik 'RESTORE' untuk lanjut: " ans
[ "$ans" = "RESTORE" ] || { echo "Dibatalkan."; exit 1; }
echo "[restore] menimpa db_sehati ..."
docker compose exec -T sehati-db sh -c "exec mysql -uroot -p\"\$MYSQL_ROOT_PASSWORD\" -e 'DROP DATABASE IF EXISTS db_sehati; CREATE DATABASE db_sehati CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;'"
gzip -dc "$SRC" | docker compose exec -T sehati-db sh -c "exec mysql -uroot -p\"\$MYSQL_ROOT_PASSWORD\" db_sehati"
echo "[restore] selesai. Restart app untuk sinkron migrasi:"
echo "  docker compose restart sehati-app"
