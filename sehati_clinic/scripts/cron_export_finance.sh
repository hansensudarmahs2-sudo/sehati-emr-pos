#!/usr/bin/env bash
# Export batch Finance ke folder file-drop (DEC-066-R2).
# Portabel: Windows+WSL (via Task Scheduler->wsl) ATAU Linux murni (via cron).
# Override opsional: SEHATI_FINANCE_DROP (folder tujuan), LOGDIR.
set -e
HERE="$(cd "$(dirname "$0")/.." && pwd)"          # = sehati_clinic/
DROP="${SEHATI_FINANCE_DROP:-$HERE/../SehatiExport/finance_pack}"
LOGDIR="${LOGDIR:-$(dirname "$DROP")}"
mkdir -p "$DROP" "$LOGDIR"
cd "$HERE"
# venv: pakai bila ada (dev); di prod bisa langsung python3 sistem
[ -f .venv/bin/activate ] && source .venv/bin/activate
python3 scripts/export_finance_batch.py --out "$DROP" --keep 30 >> "$LOGDIR/export.log" 2>&1
echo "[$(date '+%F %T')] export selesai -> $DROP" >> "$LOGDIR/export.log"
