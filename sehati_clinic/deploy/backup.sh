#!/usr/bin/env bash
# Backup Sehati (Docker) — dump MySQL (via container) + uploads volume.
# Enkripsi age OPSIONAL: aktif bila BACKUP_RECIPIENT (age public key) ada di .env.
# Jalankan dari /srv/sehati:  bash deploy/backup.sh
set -euo pipefail
cd "$(dirname "$0")/.."                      # -> /srv/sehati
BK="backups"; mkdir -p "$BK"
STAMP="$(date +%Y%m%d_%H%M%S)"

# Baca 1 nilai dari .env; kosong bila tak ada (|| true supaya set -e tak berhenti).
envval() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d "\"'" || true; }
RECIPIENT="$(envval BACKUP_RECIPIENT)"
KEEP="$(envval BACKUP_KEEP_DAILY)"; KEEP="${KEEP:-14}"

DBFILE="$BK/sehati_db_${STAMP}.sql.gz"
echo "[backup] dump database -> $DBFILE"
docker compose exec -T sehati-db sh -c \
  'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --triggers --events --default-character-set=utf8mb4 --add-drop-table db_sehati' \
  | gzip -c > "${DBFILE}.tmp"
mv "${DBFILE}.tmp" "$DBFILE"
echo "[backup]   ukuran: $(du -h "$DBFILE" | cut -f1)"

UPFILE="$BK/sehati_uploads_${STAMP}.tar.gz"
echo "[backup] arsip uploads -> $UPFILE"
if docker compose exec -T sehati-app sh -c 'tar czf - -C /app/static uploads' > "${UPFILE}.tmp" 2>/dev/null; then
  mv "${UPFILE}.tmp" "$UPFILE"; echo "[backup]   ukuran: $(du -h "$UPFILE" | cut -f1)"
else
  rm -f "${UPFILE}.tmp"; echo "[backup]   (uploads kosong/skip)"
fi

if [ -n "$RECIPIENT" ]; then
  if command -v age >/dev/null 2>&1; then
    echo "[backup] enkripsi (age -> $RECIPIENT)"
    age -r "$RECIPIENT" -o "${DBFILE}.age" "$DBFILE" && rm -f "$DBFILE"
    [ -f "$UPFILE" ] && age -r "$RECIPIENT" -o "${UPFILE}.age" "$UPFILE" && rm -f "$UPFILE"
  else
    echo "[backup] PERINGATAN: BACKUP_RECIPIENT diisi tapi 'age' tidak terpasang -> simpan TANPA enkripsi!"
  fi
else
  echo "[backup] catatan: BACKUP_RECIPIENT kosong -> backup TIDAK dienkripsi (ok untuk uji; WAJIB diisi sebelum ada data pasien)."
fi

echo "[backup] retensi: simpan $KEEP terbaru per jenis"
ls -1t "$BK"/sehati_db_*.sql.gz*     2>/dev/null | tail -n +$((KEEP+1)) | xargs -r rm -f || true
ls -1t "$BK"/sehati_uploads_*.tar.gz* 2>/dev/null | tail -n +$((KEEP+1)) | xargs -r rm -f || true
echo "[backup] SELESAI. Isi $BK/:"; ls -lh "$BK"
