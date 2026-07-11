"""
Export batch Finance (DEC-066-R2, file-drop) — Sehati -> folder bersama.

Menghasilkan SATU ZIP (15 CSV + manifest.json) ditulis ATOMIK (.tmp -> rename) ke
folder file-drop. Memakai core BERSAMA app/services/finance_export_batch.py, sehingga
cron & tombol UI Sehati berbagi satu jalur kode + satu export_log.jsonl.

USAGE (WSL, venv aktif, dari sehati_clinic/):
    python3 scripts/export_finance_batch.py                         # periode default (awal bulan..hari ini)
    python3 scripts/export_finance_batch.py --from 2026-01-01 --to 2026-06-30
    python3 scripts/export_finance_batch.py --smart                 # skip bila data identik dgn batch terakhir
    python3 scripts/export_finance_batch.py --smart --force         # tetap export walau identik
    python3 scripts/export_finance_batch.py --out /mnt/e/SehatiExport/finance_pack --keep 30

Mode:
- Default (cron): SELALU tulis batch harian (baseline/heartbeat) + catat ke export_log.jsonl.
- --smart       : cek fingerprint dulu; bila identik dgn export terakhir periode+entity yang
                  sama -> BATAL dgn soft-warning (kecuali --force). Cocok utk export manual CLI.
"""
import argparse
import logging
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.db.session import engine as _eng  # noqa: E402
_eng.echo = False
for _n in ("sqlalchemy.engine", "sqlalchemy.engine.Engine"):
    logging.getLogger(_n).setLevel(logging.WARNING)

from app.services import finance_export_batch as core  # noqa: E402


def _run_plain(db, d0, d1, out, entity, keep):
    ds, dm, total, fp = core.compute_datasets(db, d0, d1)
    res = core.write_batch(out, entity, d0, d1, ds, dm, total, fp,
                           triggered_by="cron", mode="auto", keep=keep)
    print(f"[export] {res['path']}  ({total} baris, batch {res['batch_id']})")


def _run_smart(db, d0, d1, out, entity, keep, force):
    res = core.smart_export(db, out, entity, d0, d1, force=force,
                            triggered_by="cli", mode="manual", keep=keep)
    if res["status"] == "no_change":
        last = res["last"]
        print("[smart] TIDAK ADA PERUBAHAN — data identik dengan batch terakhir:")
        print(f"        batch {last.get('batch_id')} @ {last.get('exported_at')} "
              f"({last.get('total_rows')} baris)")
        print(f"        fingerprint {res['content_fingerprint'][:16]}…")
        print("        Belum perlu export. Ulangi dengan --force untuk tetap export.")
        return 0
    changed = res.get("changed") or []
    if res.get("forced_identical"):
        print("[smart] DIPAKSA (data identik) — export tetap dibuat.")
    elif changed:
        print("[smart] ADA PERUBAHAN:")
        for c in changed:
            print(f"        - {c['name']}: {c['status']} ({c['delta_rows']:+d} baris)")
    else:
        print("[smart] Periode baru / belum pernah diexport.")
    print(f"[export] {res['path']}  ({res['total_rows']} baris, batch {res['batch_id']})")
    return 0


def main():
    today = date.today()
    ap = argparse.ArgumentParser(description="Export batch Finance (file-drop, DEC-066-R2).")
    ap.add_argument("--from", dest="dari", default=today.replace(day=1).isoformat(),
                    help="Tanggal mulai (ISO). Default: awal bulan berjalan.")
    ap.add_argument("--to", dest="sampai", default=today.isoformat(),
                    help="Tanggal akhir (ISO). Default: hari ini.")
    ap.add_argument("--out", default=core.DEFAULT_DROP, help="Folder file-drop tujuan.")
    ap.add_argument("--entity", default="KLN")
    ap.add_argument("--keep", type=int, default=30, help="Retensi: simpan N zip terbaru.")
    ap.add_argument("--smart", action="store_true",
                    help="Cek fingerprint; skip bila identik dgn batch terakhir.")
    ap.add_argument("--force", action="store_true",
                    help="(dengan --smart) tetap export walau data identik.")
    args = ap.parse_args()
    d0 = date.fromisoformat(args.dari)
    d1 = date.fromisoformat(args.sampai)

    db = SessionLocal()
    try:
        if args.smart:
            _run_smart(db, d0, d1, args.out, args.entity, args.keep, args.force)
        else:
            _run_plain(db, d0, d1, args.out, args.entity, args.keep)
    finally:
        db.close()
    print("[export] SELESAI.")


if __name__ == "__main__":
    main()
