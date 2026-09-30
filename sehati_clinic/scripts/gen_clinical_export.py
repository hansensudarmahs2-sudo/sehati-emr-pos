"""Jalankan ekspor paket KLINIS (ber-pseudonim, terenkripsi age).

    python -m scripts.gen_clinical_export                  # sejak awal data
    python -m scripts.gen_clinical_export 2026-01-01 2026-06-30
    python -m scripts.gen_clinical_export --force          # walau isinya sama

⚠ MENULIS KE DB: membuat baris `pasien_pseudonim` untuk pasien yang belum punya
  `pid` (get-or-create). Tidak menyentuh data klinis apa pun.

⚠ Paket ditulis TERENKRIPSI age ke `SEHATI_CLINICAL_DROP`
  (default /mnt/e/SehatiExport/clinical_pack). Kalau `age` atau
  `BACKUP_RECIPIENT` tidak ada, ekspor GAGAL — tidak pernah menulis polos.
"""
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

from app.services import clinical_export_batch as batch  # noqa: E402


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    dari = date.fromisoformat(args[0]) if len(args) > 0 else None
    sampai = date.fromisoformat(args[1]) if len(args) > 1 else None

    print(f"[klinis] rentang: {dari or 'awal data'} .. {sampai or 'kini'}")
    print(f"[klinis] drop   : {batch.DEFAULT_DROP}")

    db = SessionLocal()
    try:
        res = batch.smart_export(db, tgl_dari=dari, tgl_sampai=sampai,
                                 force=force, triggered_by="cli")
    except Exception as e:
        print(f"\n[klinis] GAGAL: {type(e).__name__}: {e}")
        return 1
    finally:
        db.close()

    p = res.get("pseudonim") or {}
    print(f"[klinis] pid: {p.get('total_pid')} total "
          f"({p.get('dibuat')} baru dibuat)")
    for d in res.get("datasets", []):
        print(f"   {d['name']:28} {d['rows']:>6} baris")

    if res["status"] == "no_change":
        print(f"\n[klinis] TIDAK ADA PERUBAHAN sejak "
              f"{(res.get('last') or {}).get('exported_at')}.")
        print("[klinis] Tambahkan --force kalau tetap ingin menulis paket baru.")
        return 0

    print(f"\n[klinis] SELESAI -> {res['path']}")
    print(f"[klinis] {res['total_rows']} baris, terenkripsi age.")
    print("[klinis] PSEUDONIM, BUKAN ANONIM — teks bebas bisa memuat nama/telepon "
          "di dalam kalimat. Perlakukan sebagai data rahasia.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
