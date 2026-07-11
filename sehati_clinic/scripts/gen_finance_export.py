"""
Generate export pack (CSV) dari db_sehati untuk uji kontrak ke Finance.

Menjalankan semua dataset di ExportService.DATASET_REGISTRY untuk rentang
2026-01-01..2026-06-30, menulis CSV ke exports/finance_pack/, dan mencetak
jumlah baris per dataset. Tidak mengubah DB.

USAGE (venv aktif, dari sehati_clinic/):
    python scripts/gen_finance_export.py
"""
import sys
import logging
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
for _lg in ("sqlalchemy.engine", "sqlalchemy.engine.Engine"):
    logging.getLogger(_lg).setLevel(logging.WARNING)

from app.db.session import SessionLocal  # noqa: E402
from app.db.session import engine as _eng  # noqa: E402
_eng.echo = False  # matikan echo SQL definitif
import logging as _l
for _n in ("sqlalchemy.engine","sqlalchemy.engine.Engine"):
    _l.getLogger(_n).setLevel(_l.WARNING)  # senyapkan echo (setelah engine dibuat)
from app.services.export_service import ExportService  # noqa: E402
from app.core.csv_writer import dict_list_to_csv_bytes  # noqa: E402

START, END = date(2026, 1, 1), date(2026, 6, 30)


def main():
    db = SessionLocal()
    svc = ExportService(db)
    outdir = ROOT / "exports" / "finance_pack"
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"[export] rentang {START} .. {END}  -> {outdir}")
    total = 0
    try:
        for i, entry in enumerate(svc.DATASET_REGISTRY, 1):
            try:
                rows = getattr(svc, entry["method"])(START, END, False)
            except Exception as e:
                print(f"  {entry['name']:34} ERROR: {str(e)[:70]}")
                continue
            data = dict_list_to_csv_bytes(rows, columns=entry.get("default_columns"))
            (outdir / f"{i:02d}_{entry['name']}.csv").write_bytes(data)
            total += len(rows)
            print(f"  {i:02d} {entry['name']:34} {len(rows):>6} baris")
    finally:
        db.close()
    print(f"[export] SELESAI. total {total} baris di {outdir}")


if __name__ == "__main__":
    main()
