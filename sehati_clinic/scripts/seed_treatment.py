"""
Seed master_treatment dari CSV FINAL (JoDerma).

Aturan (keputusan dr. Hansen):
  - BHP per pakai       = 20% x harga jual
  - Komisi dokter       = 45% dari MARGIN (PERSEN_MARGIN, value=45)
  - Komisi perawat      = kosong (set per-tindakan nanti)
  - Pajak               = 0%
  - durasi_menit        = 30 (placeholder, edit di Master Treatment)
  - role_pelaksana      = Perawat untuk 'Facial & Basic Skin Care' + Hair Removal/IPL/IPL Adv;
                          selain itu Dokter
  - butuh_otorisasi     = False (halus-kan nanti utk botox/filler/laser/surgery)

Kategori CSV TIDAK disimpan (master_treatment tak punya kolom kategori) — hanya referensi.

Jalankan dari folder sehati_clinic:
  .venv/bin/python scripts/seed_treatment.py --csv '../seed_data/LIST TINDAKAN - joderma FINAL.csv'
  (tambah --force untuk tetap jalan walau tabel sudah terisi)
"""
from __future__ import annotations

import argparse
import csv
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.db.models.treatment import MasterTreatment

PERAWAT_NAMES = {"Hair Removal", "IPL", "IPL Adv"}
KATEGORI_PERAWAT = {"Facial & Basic Skin Care"}


def role_for(kategori: str, nama: str) -> str:
    if kategori.strip() in KATEGORI_PERAWAT or nama.strip() in PERAWAT_NAMES:
        return "Perawat"
    return "Dokter"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--force", action="store_true", help="lanjut walau master_treatment tak kosong")
    a = ap.parse_args()

    path = Path(a.csv)
    if not path.exists():
        sys.exit(f"CSV tidak ditemukan: {path}")

    rows = list(csv.reader(path.open(encoding="utf-8-sig")))[1:]
    items = []
    for r in rows:
        if len(r) < 3 or not r[1].strip():
            continue
        harga_s = r[2].strip().replace(".", "")
        if not harga_s.isdigit():
            sys.exit(f"Harga tak valid di baris: {r}")
        items.append((r[0].strip(), r[1].strip()[:100], Decimal(harga_s)))

    if not items:
        sys.exit("CSV kosong / tak ada baris valid.")

    db = SessionLocal()
    try:
        existing = db.scalar(select(func.count()).select_from(MasterTreatment))
        if existing and not a.force:
            sys.exit(f"ABORT: master_treatment sudah berisi {existing} baris. "
                     f"Pakai --force kalau memang mau menambah.")

        n_dok = n_per = 0
        for kategori, nama, harga in items:
            bhp = (harga * Decimal("0.20")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            role = role_for(kategori, nama)
            n_per += role == "Perawat"
            n_dok += role == "Dokter"
            db.add(MasterTreatment(
                nama_treatment=nama,
                role_pelaksana=role,
                durasi_menit=30,
                harga=harga,
                bhp_per_pakai_nominal=bhp,
                komisi_dokter_tipe="PERSEN_MARGIN",
                komisi_dokter_value=Decimal("45"),
                komisi_perawat_tipe=None,
                komisi_perawat_value=0,
                pajak_persen=0,
                is_active=True,
                butuh_otorisasi=False,
            ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"✅ Seed {len(items)} tindakan.")
    print(f"   Role: Dokter={n_dok}, Perawat={n_per}")
    print(f"   BHP=20% harga, komisi dokter 45% margin, pajak 0, durasi 30 mnt (placeholder)")


if __name__ == "__main__":
    main()
