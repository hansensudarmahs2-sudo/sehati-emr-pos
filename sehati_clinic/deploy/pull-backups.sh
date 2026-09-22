#!/usr/bin/env bash
# TARIK cadangan Sehati dari mini PC ke DESKTOP (salinan di luar mesin).
#
# Dijalankan DI DESKTOP, bukan di mini PC. Arah TARIK dipilih dengan sengaja:
# mini PC tidak perlu diberi kunci SSH ke desktop, jadi kalau mini PC disusupi,
# penyerang tidak mendapat jalan masuk ke mesin pemegang kunci `age`.
#
# Yang ditarik HANYA file `*.age` (sudah terenkripsi). Kalau suatu saat
# `backup.sh` gagal mengenkripsi dan menghasilkan `.sql.gz` mentah, file itu
# TIDAK akan ikut tersalin — lebih baik cadangan tidak bertambah daripada
# plaintext rekam medis berpindah mesin tanpa disadari.
#
# Kunci privat `age` TIDAK pernah ikut berpindah. Ia tetap hanya di desktop.
#
# Pemakaian:  bash deploy/pull-backups.sh
# Cron harian (desktop, sesudah jadwal backup mini PC 23:59):
#   30 0 * * * bash /mnt/e/Claude/Projects/sehati-emr-pos/sehati_clinic/deploy/pull-backups.sh >> ~/sehati-pull.log 2>&1
set -euo pipefail

REMOTE="${SEHATI_REMOTE:-joderma-jemur@joderma-jemur}"
REMOTE_DIR="${SEHATI_REMOTE_DIR:-/srv/sehati/backups}"
DEST="${SEHATI_BACKUP_DEST:-/mnt/e/Claude/Backups/sehati}"
KEEP="${SEHATI_KEEP:-60}"          # desktop = arsip lebih panjang dari mini PC (14)
MAX_UMUR_JAM="${SEHATI_MAX_UMUR_JAM:-30}"  # ambang "cadangan basi"

mkdir -p "$DEST"
echo "[pull] $(date '+%F %T') dari $REMOTE:$REMOTE_DIR -> $DEST"

# --include/--exclude: hanya *.age. Tanpa --delete: penghapusan di mini PC
# (retensi 14 hari) TIDAK boleh menghapus arsip panjang di desktop.
rsync -az --prune-empty-dirs \
  --include '*/' --include '*.age' --exclude '*' \
  "$REMOTE:$REMOTE_DIR/" "$DEST/"

N_DB=$(ls -1 "$DEST"/sehati_db_*.age 2>/dev/null | wc -l | tr -d ' ')
N_UP=$(ls -1 "$DEST"/sehati_uploads_*.age 2>/dev/null | wc -l | tr -d ' ')
echo "[pull] tersimpan: $N_DB dump database, $N_UP arsip uploads"

# --- Deteksi cadangan BASI -------------------------------------------------
# Ini bagian yang benar-benar menyelamatkan: cron backup yang mati diam-diam
# tidak menimbulkan gejala apa pun sampai hari kamu membutuhkan cadangannya.
BARU=$(ls -1t "$DEST"/sehati_db_*.age 2>/dev/null | head -1 || true)
if [ -z "${BARU:-}" ]; then
  echo "[pull] ⚠ GAWAT: tidak ada satu pun dump database di $DEST"
  exit 1
fi
UMUR_JAM=$(( ( $(date +%s) - $(stat -c %Y "$BARU") ) / 3600 ))
echo "[pull] terbaru: $(basename "$BARU") — umur ${UMUR_JAM} jam"
if [ "$UMUR_JAM" -gt "$MAX_UMUR_JAM" ]; then
  echo "[pull] ⚠ PERINGATAN: cadangan terbaru lebih tua dari ${MAX_UMUR_JAM} jam."
  echo "[pull]   Kemungkinan cron backup di mini PC berhenti. Periksa:"
  echo "[pull]   ssh $REMOTE 'tail -20 /srv/sehati/backups/backup_cron.log'"
fi

# --- Retensi desktop -------------------------------------------------------
for pola in "sehati_db_*.age" "sehati_uploads_*.age"; do
  # shellcheck disable=SC2086
  ls -1t $DEST/$pola 2>/dev/null | tail -n +$((KEEP+1)) | xargs -r rm -f || true
done

echo "[pull] SELESAI. Total: $(du -sh "$DEST" | cut -f1)"
