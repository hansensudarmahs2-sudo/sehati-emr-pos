"""
Konversi 4 produk RACIKAN flat (Tab SR, SR 2, SRO, STR) menjadi Formula Racikan.

Kenapa: produk flat menyimpan HARGA MATI dan — yang lebih serius — terjual TANPA
memotong stok bahan (Stenirol/Rydian/Metcor). Formula menyimpan KOMPOSISI; harga
dihitung dari harga bahan terkini + ongkos racik flat.

Idempoten: formula yang sudah ada tidak diduplikasi; bahan hanya diisi bila masih kosong.

Jalankan dari folder sehati_clinic:
  .venv/bin/python scripts/convert_racikan_templates.py
  .venv/bin/python scripts/convert_racikan_templates.py --nonaktifkan-produk-flat
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.db.session import SessionLocal
from app.db.models.produk import MasterProduk
from app.db.models.racikan import MasterRacikan, MasterRacikanBahan
from app.services.racikan_service import RacikanService

# Komposisi dibaca dari kolom `kandungan` produk flat lama.
# (nama formula, jenis, default unit, [(kode_produk, dosis_mg), ...], kode produk flat asal)
TEMPLATES = [
    ("Tab SR", "KAPSUL", 15,
     [("OBM-024", 8), ("OBM-019", 7), ("OBM-075", 2)], "OBM-068"),
    ("Tab SR 2", "KAPSUL", 15,
     [("OBM-024", 4), ("OBM-019", 5), ("OBM-075", 2)], "OBM-069"),
    ("Tab SRO", "KAPSUL", 15,
     [("OBM-024", 8), ("OBM-019", 7), ("OBM-075", 2), ("OBM-018", 15)], "OBM-070"),
    ("Tab STR", "KAPSUL", 15,
     [("OBM-024", 6), ("OBM-026", 2), ("OBM-019", 7)], "OBM-071"),
]
# OBM-018 Oxtin 30mg → "½ tab" = 15 mg. OBM-075 Metcor 8mg (disamakan Stenirol).


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nonaktifkan-produk-flat", action="store_true",
                    help="Set is_active=0 untuk 4 produk RACIKAN flat setelah dikonversi.")
    a = ap.parse_args()

    db = SessionLocal()
    svc = RacikanService(db)
    dibuat = dilewati = bahan_ditambah = 0
    try:
        for nama, jenis, unit, bahan, kode_flat in TEMPLATES:
            formula = db.scalar(select(MasterRacikan).where(MasterRacikan.nama == nama))
            if formula is None:
                formula = svc.create_formula(
                    nama=nama, jenis_racik=jenis, default_jumlah_unit=unit,
                    catatan=f"Konversi dari produk flat {kode_flat}.",
                )
                dibuat += 1
                print(f"✅ Formula dibuat: {nama}")
            else:
                dilewati += 1
                print(f"↷  Formula sudah ada: {nama}")

            if svc.list_bahan(formula.id_racikan):
                print(f"   ↷ bahan sudah terisi, dilewati")
                continue

            for urut, (kode, dosis) in enumerate(bahan, start=1):
                produk = db.scalar(select(MasterProduk).where(MasterProduk.kode_produk == kode))
                if produk is None:
                    print(f"   ⚠ produk {kode} TIDAK DITEMUKAN — bahan dilewati")
                    continue
                if not produk.kekuatan_nilai:
                    print(f"   ⚠ {produk.nama_produk} belum punya kekuatan — bahan dilewati")
                    continue
                db.add(MasterRacikanBahan(
                    id_racikan=formula.id_racikan, id_produk=produk.id_produk,
                    dosis_per_unit=dosis, satuan_dosis="mg", urutan=urut,
                ))
                bahan_ditambah += 1
                print(f"   + {produk.nama_produk}: {dosis} mg/unit")
            db.commit()

        if a.nonaktifkan_produk_flat:
            print("\n-- Menonaktifkan produk RACIKAN flat --")
            for _, _, _, _, kode_flat in TEMPLATES:
                p = db.scalar(select(MasterProduk).where(MasterProduk.kode_produk == kode_flat))
                if p is not None and p.is_active:
                    p.is_active = False
                    print(f"   ⛔ {p.kode_produk} {p.nama_produk} → nonaktif")
            db.commit()

        print(f"\nRingkas: {dibuat} formula baru, {dilewati} sudah ada, {bahan_ditambah} bahan ditambahkan.")
        print("\n-- Pratinjau harga (jumlah unit default) --")
        for nama, _, unit, _, _ in TEMPLATES:
            f = db.scalar(select(MasterRacikan).where(MasterRacikan.nama == nama))
            if not f:
                continue
            h = svc.hitung(f.id_racikan, unit)
            print(f"  {nama:10s} {h['jumlah_unit']:>3} unit | bahan {h['subtotal_bahan']:>10,.0f} "
                  f"+ racik {h['biaya_racik']:>7,.0f} = {h['total']:>10,.0f}  (per unit {h['per_unit']:,.0f})")
            for m in h["masalah"]:
                print(f"      ⚠ {m}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
