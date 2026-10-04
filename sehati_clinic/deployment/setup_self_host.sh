#!/usr/bin/env bash
# =====================================================================
# B3.1 — Self-host Aset Frontend (HTMX + Tom Select + Chart.js + Tailwind)
# =====================================================================
# Tujuan: aplikasi 100% mandiri dari internet/CDN.
#
# JALANKAN DI LINGKUNGAN YANG ADA INTERNET + npm (WSL Bapak / server saat setup).
# Idempotent — aman dijalankan ulang.
#
# Pakai:  bash deployment/setup_self_host.sh
#         (dari folder sehati_clinic/)
#
# Prasyarat: curl, node, npm terpasang.
# =====================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"   # folder sehati_clinic/
cd "$ROOT"
echo "==> Root project: $ROOT"

# ⚠ DIPERBAIKI 2026-10-04. Dulu kedua path ini menunjuk app/web/static/ — folder
# yang TIDAK DILAYANI server. app/main.py memasang StaticFiles dari
# parent.parent/"static", dan skrip ini sendiri menambal template agar menunjuk
# "/static/vendor/..." dan "/static/css/app.css". Jadi ia mengunduh ke satu tempat
# lalu menyuruh template memuat dari tempat lain.
#
# Akibatnya folder kembar app/web/static/ lahir dan hidup berdampingan dengan
# static/ selama berbulan-bulan; cek_kelas_tailwind.py dan CLAUDE.md §4.2 ikut
# menunjuk ke salinan yang salah. Folder kembarnya sudah dihapus 2026-10-04.
# Kalau path di bawah dikembalikan ke app/web/static, folder itu lahir lagi.
VENDOR="static/vendor"
CSSDIR="static/css"
mkdir -p "$VENDOR" "$CSSDIR"

# ---------------------------------------------------------------------
# 1. Download library (pin versi sama dengan yang dipakai sekarang)
# ---------------------------------------------------------------------
echo "==> [1/4] Download HTMX, Tom Select, Chart.js ke $VENDOR ..."
curl -fsSL "https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js" \
     -o "$VENDOR/htmx.min.js"
curl -fsSL "https://cdn.jsdelivr.net/npm/tom-select@2.3.1/dist/js/tom-select.complete.min.js" \
     -o "$VENDOR/tom-select.complete.min.js"
curl -fsSL "https://cdn.jsdelivr.net/npm/tom-select@2.3.1/dist/css/tom-select.min.css" \
     -o "$VENDOR/tom-select.min.css"
curl -fsSL "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js" \
     -o "$VENDOR/chart.umd.min.js"
echo "    OK. File vendor:"
ls -la "$VENDOR"

# ---------------------------------------------------------------------
# 2. Build Tailwind jadi CSS statis (hanya class yang dipakai)
# ---------------------------------------------------------------------
echo "==> [2/4] Build Tailwind CSS statis ..."
# tailwind.config.js + input.css sudah disiapkan di repo (lihat file pendamping).
# Pakai npx supaya tidak perlu install global.
npx --yes tailwindcss@3 \
    -c ./tailwind.config.js \
    -i "$CSSDIR/input.css" \
    -o "$CSSDIR/app.css" \
    --minify
echo "    OK. Output: $CSSDIR/app.css ($(wc -c < "$CSSDIR/app.css") bytes)"

# ---------------------------------------------------------------------
# 3. Switch referensi CDN -> lokal di template (Python, robust)
# ---------------------------------------------------------------------
echo "==> [3/4] Ganti referensi CDN -> /static lokal di template ..."
python3 - <<'PYEOF'
import glob, re

REPLACEMENTS = {
    # Tailwind Play CDN -> CSS statis
    '<script src="https://cdn.tailwindcss.com"></script>':
        '<link rel="stylesheet" href="/static/css/app.css">',
    # HTMX (dua versi yang dipakai)
    '<script src="https://unpkg.com/htmx.org@1.9.12"></script>':
        '<script src="/static/vendor/htmx.min.js"></script>',
    '<script src="https://unpkg.com/htmx.org@1.9.10"></script>':
        '<script src="/static/vendor/htmx.min.js"></script>',
    # Tom Select
    '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/tom-select@2.3.1/dist/css/tom-select.min.css">':
        '<link rel="stylesheet" href="/static/vendor/tom-select.min.css">',
    '<script src="https://cdn.jsdelivr.net/npm/tom-select@2.3.1/dist/js/tom-select.complete.min.js"></script>':
        '<script src="/static/vendor/tom-select.complete.min.js"></script>',
    # Chart.js (4 report templates)
    '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>':
        '<script src="/static/vendor/chart.umd.min.js"></script>',
}

total = 0
for path in glob.glob('app/web/templates/**/*.html', recursive=True):
    s = open(path, encoding='utf-8').read()
    orig = s
    for old, new in REPLACEMENTS.items():
        if old in s:
            s = s.replace(old, new)
            total += 1
    if s != orig:
        open(path, 'w', encoding='utf-8').write(s)
        print(f"    patched: {path}")
print(f"    Total referensi diganti: {total}")
# sisa CDN?
import subprocess
leftover = subprocess.run(
    ['grep', '-rl', '-e', 'cdn.tailwindcss', '-e', 'unpkg.com', '-e', 'jsdelivr', 'app/web/templates/'],
    capture_output=True, text=True).stdout.strip()
print("    Sisa referensi CDN:", leftover if leftover else "(bersih)")
PYEOF

# ---------------------------------------------------------------------
# 4. Selesai — instruksi verifikasi
# ---------------------------------------------------------------------
echo "==> [4/4] SELESAI."
echo ""
echo "VERIFIKASI:"
echo "  1. Restart aplikasi (atau uvicorn --reload akan auto-reload template)."
echo "  2. Buka aplikasi, cek tampilan TETAP normal (Tailwind), dropdown searchable jalan (Tom Select), chart laporan muncul (Chart.js)."
echo "  3. PUTUS internet di komputer client, refresh -> harus tetap normal."
echo ""
echo "  Kalau ada style yang hilang setelah build Tailwind (class dinamis di JS"
echo "  yang tidak ke-scan), tambahkan class itu ke 'safelist' di tailwind.config.js,"
echo "  lalu jalankan ulang script ini."
