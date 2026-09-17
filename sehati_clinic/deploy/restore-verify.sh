#!/usr/bin/env bash
# UJI restore NON-DESTRUKTIF: restore backup TERBARU ke database scratch
# (db_sehati_verify), bandingkan jumlah tabel & baris (staf, produk) dgn DB live,
# lalu hapus scratch. DB live (db_sehati) TIDAK disentuh.
# Jalankan dari /srv/sehati:  bash deploy/restore-verify.sh [file.sql.gz]
set -euo pipefail
cd "$(dirname "$0")/.."
BK="backups"; SCRATCH="db_sehati_verify"
SRC="${1:-$(ls -1t "$BK"/sehati_db_*.sql.gz 2>/dev/null | head -1 || true)}"
[ -z "${SRC:-}" ] && { echo "Tak ada backup .sql.gz. (Kalau .age, dekripsi dulu.)"; exit 1; }
echo "[verify] sumber: $SRC"

# Kirim SQL lewat STDIN (hindari masalah kutip di argumen). -N -B = tanpa header/border.
run_sql() { docker compose exec -T sehati-db sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -B "$@"' _ "$@"; }

echo "[verify] buat scratch $SCRATCH ..."
printf 'DROP DATABASE IF EXISTS %s; CREATE DATABASE %s CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n' "$SCRATCH" "$SCRATCH" | run_sql 2>/dev/null

echo "[verify] restore ke $SCRATCH ..."
gzip -dc "$SRC" | run_sql "$SCRATCH" 2>/dev/null

q() { printf '%s\n' "$1" | run_sql 2>/dev/null; }
LT=$(q "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='db_sehati';")
ST=$(q "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$SCRATCH';")
LS=$(q "SELECT COUNT(*) FROM db_sehati.master_staf;")
SS=$(q "SELECT COUNT(*) FROM $SCRATCH.master_staf;")
LP=$(q "SELECT COUNT(*) FROM db_sehati.master_produk;")
SP=$(q "SELECT COUNT(*) FROM $SCRATCH.master_produk;")
echo "[verify] LIVE vs SCRATCH:"
printf "  tabel         live=%s  scratch=%s\n" "$LT" "$ST"
printf "  master_staf   live=%s  scratch=%s\n" "$LS" "$SS"
printf "  master_produk live=%s  scratch=%s\n" "$LP" "$SP"

echo "[verify] hapus scratch ..."
printf 'DROP DATABASE %s;\n' "$SCRATCH" | run_sql 2>/dev/null

if [ "$LT" = "$ST" ] && [ "$LS" = "$SS" ] && [ "$LP" = "$SP" ] && [ -n "$LT" ]; then
  echo "[verify] LULUS ✅ — backup valid & bisa di-restore (angka cocok)."
else
  echo "[verify] ⚠ ANGKA TIDAK COCOK / kosong — periksa backup."
fi
