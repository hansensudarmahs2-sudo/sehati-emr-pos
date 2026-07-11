#!/usr/bin/env bash
# Scan dependensi Python untuk kerentanan yang diketahui (ASVS V14.5.2).
# Aman dijalankan manual ATAU terjadwal (cron/systemd) — auto-detect .venv,
# jadi TIDAK perlu 'source activate'.
#
# Manual (WSL, dari sehati_clinic/):
#   bash scripts/security_pip_audit.sh
#
# Output: tabel ke logs/pip_audit/cron.log + JSON bertanggal + latest.json.
# Exit: 0 = aman, 2 = ADA kerentanan (memudahkan alert/monitoring), 1 = error.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"

# Interpreter: pakai venv bila ada (biar cron/systemd tak perlu activate)
if [ -x "$ROOT/.venv/bin/python" ]; then PY="$ROOT/.venv/bin/python"; else PY="$(command -v python3)"; fi

OUTDIR="logs/pip_audit"; mkdir -p "$OUTDIR"
STAMP="$(date +%Y%m%dT%H%M)"
JSON="$OUTDIR/pip_audit_$STAMP.json"
LOG="$OUTDIR/cron.log"
RETENTION="${PIP_AUDIT_RETENTION:-12}"   # simpan N JSON mingguan terakhir

log(){ echo "[$(date -Is)] $*" | tee -a "$LOG"; }

# Pastikan pip-audit terpasang di interpreter terpilih
"$PY" -m pip show pip-audit >/dev/null 2>&1 || {
  log "pip-audit belum ada, memasang..."; "$PY" -m pip install pip-audit >>"$LOG" 2>&1 || { log "GAGAL pasang pip-audit"; exit 1; }
}

log "pip-audit scan mulai (py=$PY)"
"$PY" -m pip_audit -f json -o "$JSON" || true      # nonzero saat ada vuln — diabaikan, dihitung dari JSON
"$PY" -m pip_audit >>"$LOG" 2>&1 || true            # tabel readable ke log

# Hitung jumlah temuan dari JSON (dukung format list & {"dependencies":[...]})
COUNT="$("$PY" - "$JSON" <<'PYEOF'
import json,sys
try: d=json.load(open(sys.argv[1]))
except Exception: print("-1"); sys.exit(0)
deps = d.get("dependencies", []) if isinstance(d, dict) else d
n=0
if isinstance(deps, list):
    for p in deps:
        if isinstance(p, dict): n += len(p.get("vulns", []) or [])
print(n)
PYEOF
)"

cp -f "$JSON" "$OUTDIR/latest.json" 2>/dev/null || true

FINAL_RC=0
if [ "${COUNT:-0}" -gt 0 ] 2>/dev/null; then
  log "TEMUAN: $COUNT kerentanan — lihat $JSON (dan RUNBOOK untuk tindak lanjut)."
  echo "$COUNT vuln @ $STAMP" > "$OUTDIR/VULN_FOUND"
  FINAL_RC=2
else
  log "Aman: 0 kerentanan pada snapshot ini."
  rm -f "$OUTDIR/VULN_FOUND" 2>/dev/null || true
fi

# Retensi: sisakan N JSON terbaru (latest.json tidak ikut terhapus)
ls -1t "$OUTDIR"/pip_audit_*.json 2>/dev/null | tail -n +"$((RETENTION+1))" | xargs -r rm -f

log "selesai (rc=$FINAL_RC)"
exit "$FINAL_RC"
