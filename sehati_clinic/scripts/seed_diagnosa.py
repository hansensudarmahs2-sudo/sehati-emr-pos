"""
Seed ref_diagnosa dari CSV (ICD-10 WHO subset derma/estetik + estetik JD-xxx).

Idempoten: upsert per (sistem, kode) — aman dijalankan berulang.
Paket (diagnosa_paket_item) TIDAK di-seed di sini; diisi via Master Diagnosa (Fase B).

CSV kolom: sistem,kode,nama,nama_en,kategori,default_kontrol_hari

Jalankan dari folder sehati_clinic:
  .venv/bin/python scripts/seed_diagnosa.py --csv '../seed_data/ref_diagnosa_seed.csv'
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.db.models.diagnosa import RefDiagnosa
from app.db.models._enums import SistemDiagnosaEnum

VALID_SISTEM = {e.value for e in SistemDiagnosaEnum}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    a = ap.parse_args()

    path = Path(a.csv)
    if not path.exists():
        sys.exit(f"CSV tidak ditemukan: {path}")

    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    if not rows:
        sys.exit("CSV kosong.")

    db = SessionLocal()
    n_ins = n_upd = 0
    try:
        for r in rows:
            sistem = (r.get("sistem") or "").strip()
            kode = (r.get("kode") or "").strip()
            nama = (r.get("nama") or "").strip()
            if not sistem or not kode or not nama:
                continue
            if sistem not in VALID_SISTEM:
                sys.exit(f"sistem tidak valid '{sistem}' di baris: {r}")

            nama_en = (r.get("nama_en") or "").strip() or None
            kategori = (r.get("kategori") or "").strip() or None
            kontrol_s = (r.get("default_kontrol_hari") or "").strip()
            kontrol = int(kontrol_s) if kontrol_s.isdigit() else (14 if sistem == "ESTETIK" else 7)

            existing = db.scalar(
                select(RefDiagnosa).where(
                    RefDiagnosa.sistem == SistemDiagnosaEnum(sistem),
                    RefDiagnosa.kode == kode,
                )
            )
            if existing is None:
                db.add(RefDiagnosa(
                    sistem=SistemDiagnosaEnum(sistem),
                    kode=kode,
                    nama=nama,
                    nama_en=nama_en,
                    kategori=kategori,
                    default_kontrol_hari=kontrol,
                    is_active=True,
                ))
                n_ins += 1
            else:
                existing.nama = nama
                existing.nama_en = nama_en
                existing.kategori = kategori
                existing.default_kontrol_hari = kontrol
                n_upd += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"✅ Seed ref_diagnosa: {n_ins} baru, {n_upd} diperbarui (total baris CSV valid diproses).")


if __name__ == "__main__":
    main()
