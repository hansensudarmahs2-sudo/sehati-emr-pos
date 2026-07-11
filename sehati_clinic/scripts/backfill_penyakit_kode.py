"""
Backfill kode_penyakit untuk data penyakit kronis lama (free-text, kode NULL).

Maps nama_penyakit -> kode kanonik (master + sinonim). Tak cocok -> kode 99 (Lain-lain).
Aman: dry-run default. Jalankan dengan --apply untuk commit.

Pakai:
    .venv/bin/python -m scripts.backfill_penyakit_kode          # dry-run (lihat hasil)
    .venv/bin/python -m scripts.backfill_penyakit_kode --apply  # eksekusi
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.services.penyakit_kronis_service import PenyakitKronisService


def main():
    apply = "--apply" in sys.argv
    db = SessionLocal()
    try:
        rep = PenyakitKronisService(db).backfill_kode(dry_run=not apply)
    finally:
        db.close()
    print(f"Total baris kode NULL : {rep['total']}")
    print(f"  Cocok ke kode master: {rep['matched']}")
    print(f"  Jadi Lain-lain (99) : {rep['other']}")
    print(f"  Mode                : {'APPLY (commit)' if apply else 'DRY-RUN (tidak diubah)'}")
    if rep["sample"]:
        print("\nContoh pemetaan (maks 20):")
        for s in rep["sample"]:
            print(f"  - {s['nama']!r:40} -> kode {s['kode']}")
    if not apply and rep["total"] > 0:
        print("\nKalau sudah cocok, jalankan ulang dengan --apply untuk menyimpan.")


if __name__ == "__main__":
    main()
