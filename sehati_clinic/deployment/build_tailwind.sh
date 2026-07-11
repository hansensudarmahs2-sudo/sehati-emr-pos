#!/usr/bin/env bash
# =====================================================================
# B3.1 (fix) — BUILD-ONLY Tailwind CSS, robust untuk WSL + /mnt/c.
# =====================================================================
# CATATAN PENTING:
#  - Folder static yang DILAYANI server = sehati_clinic/static/ (lihat
#    app/main.py: parent.parent/"static"). BUKAN app/web/static.
#  - Template + vendor SUDAH disiapkan oleh Claude (jangan ditulis ulang
#    dari WSL → /mnt/c menyuntik null byte = B-013).
#  - Script ini HANYA build app.css ke static/css/. Tidak menyentuh template.
#  - Scan template dari /tmp (Linux-native) supaya glob Tailwind tidak gagal
#    di filesystem /mnt/c.
#
# Pakai (dari folder sehati_clinic/, di WSL dengan Node Linux):
#   bash deployment/build_tailwind.sh
# =====================================================================
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "==> Root: $ROOT"

# Pastikan pakai Node LINUX, bukan Windows
NODE_BIN="$(command -v node || true)"
echo "==> node: $NODE_BIN ($(node --version 2>/dev/null || echo '??'))"
case "$NODE_BIN" in
  /mnt/c/*) echo "!! Ini Node WINDOWS. Install Node Linux dulu (NodeSource), lalu ulangi."; exit 1;;
esac

mkdir -p static/css

# Copy template ke /tmp (Linux-native) supaya glob Tailwind handal
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp -r app/web/templates "$TMP/templates"
echo "==> Template disalin ke $TMP ($(find "$TMP/templates" -name '*.html' | wc -l) file html)"

echo "==> Build Tailwind → static/css/app.css ..."
npx --yes tailwindcss@3 \
    -i static/css/input.css \
    -o static/css/app.css \
    --content "$TMP/templates/**/*.html" \
    --minify

# Verifikasi hasil
BYTES=$(wc -c < static/css/app.css)
UTILS=$(grep -oE '\.(flex|grid|bg-|text-|px-|py-|rounded|w-|h-|border)' static/css/app.css | wc -l)
NULLS=$(tr -cd '\000' < static/css/app.css | wc -c)
echo ""
echo "==> HASIL: static/css/app.css = ${BYTES} bytes | utility hits = ${UTILS} | null bytes = ${NULLS}"
if [ "$UTILS" -lt 100 ]; then
  echo "!! GAGAL: utility class masih sedikit (<100). Scan template bermasalah."
  echo "   Kirim output ini ke Claude. Kemungkinan saatnya migrasi WSL-native."
  exit 1
fi
if [ "$NULLS" -ne 0 ]; then
  echo "!! app.css kena null byte (masalah /mnt/c). Saatnya migrasi WSL-native."
  exit 1
fi

echo ""
echo "✅ SUKSES. Refresh aplikasi (Ctrl+Shift+R untuk hard-refresh) → Tailwind normal."
echo "   Test pamungkas: putus internet → aplikasi tetap tampil sempurna."
