"""
WIPE dev DB dari 0 + seed admin/config/tier + 80 produk topikal.

DESTRUKTIF: mengosongkan SEMUA tabel (kecuali alembic_version), lalu:
  1. Buat 1 admin (Superadmin)
  2. Buat 1 master_klinik_config (identitas klinik)
  3. Seed tier membership VIP + VVIP (placeholder harga — edit di Settings)
  4. Seed 80 produk topikal dari CSV (harga jual + HPP + eligible diskon member)

Treatment SENGAJA dikosongkan (di-seed menyusul terpisah).

Jalankan dari folder sehati_clinic dengan venv:
  .venv/bin/python scripts/wipe_and_seed_topikal.py \
      --yes WIPE \
      --admin-user hansen --admin-pass 'RAHASIA' --admin-name 'dr. Hansen Sudarma' \
      --admin-pin 123456 \
      --nama-klinik 'JoDerma' \
      --csv '../seed_data/LIST PRODUK TOPIKAL - Produk Topikal.csv'

Tanpa --yes WIPE skrip berhenti (dry sanity print saja).
"""
from __future__ import annotations

import argparse
import csv
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

from app.db.session import SessionLocal
from app.core.security import hash_password
from app.db.models._enums import StafRoleEnum, TipeProdukEnum
from app.db.models.staf import MasterStaf
from app.db.models.klinik_config import MasterKlinikConfig
from app.db.models.membership import MasterMembership
from app.db.models.produk import MasterProduk
from app.config import settings


def parse_rp(s: str):
    """'150.000' -> Decimal(150000). '' -> None. Ada koma (desimal aneh) -> None."""
    s = (s or "").strip()
    if not s:
        return None
    if "," in s:            # HPP aneh spt '50,54' — lewati, jangan salah simpan
        return None
    digits = s.replace(".", "").replace(" ", "")
    return Decimal(digits) if digits.isdigit() else None


def parse_products(csv_path: Path):
    rows = list(csv.reader(csv_path.open(encoding="utf-8")))
    out, cur_gol = [], ""
    for r in rows[2:]:                       # 2 baris header
        if len(r) < 8:
            continue
        if r[1].strip():
            cur_gol = r[1].strip()
        nama = r[3].strip()
        if not nama:                          # baris lanjutan kandungan
            continue
        out.append({
            "golongan": cur_gol,
            "nama": nama[:100],
            "satuan": (r[5].strip() or "unit")[:20],
            "harga": parse_rp(r[6]),
            "hpp": parse_rp(r[7]),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", default="", help="ketik WIPE untuk konfirmasi destruktif")
    ap.add_argument("--admin-user", required=True)
    ap.add_argument("--admin-pass", required=True)
    ap.add_argument("--admin-name", required=True)
    ap.add_argument("--admin-pin", default="")
    ap.add_argument("--nama-klinik", default="JoDerma")
    ap.add_argument("--csv", required=True)
    a = ap.parse_args()

    csv_path = Path(a.csv)
    if not csv_path.exists():
        sys.exit(f"CSV tidak ditemukan: {csv_path}")

    prods = parse_products(csv_path)
    print(f"DB target : {settings.db_host}:{settings.db_port}/{settings.db_name}")
    print(f"Produk terbaca dari CSV: {len(prods)}")
    tanpa_hpp = [p["nama"] for p in prods if p["hpp"] is None]
    if tanpa_hpp:
        print(f"  (HPP kosong/di-skip {len(tanpa_hpp)}: {', '.join(tanpa_hpp)})")
    if not prods or any(p["harga"] is None for p in prods):
        sys.exit("ABORT: ada produk tanpa harga jual — cek CSV.")

    if a.yes != "WIPE":
        print("\nDRY: tambahkan `--yes WIPE` untuk benar-benar menghapus & seed. Berhenti.")
        return

    db = SessionLocal()
    try:
        conn = db.connection()
        # daftar tabel (kecuali alembic_version)
        tables = [row[0] for row in conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = :db AND table_type='BASE TABLE'"
        ), {"db": settings.db_name})]
        tables = [t for t in tables if t != "alembic_version"]

        print(f"\nTRUNCATE {len(tables)} tabel ...")
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for t in tables:
            conn.execute(text(f"TRUNCATE TABLE `{t}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))

        # 1. Admin
        db.add(MasterStaf(
            username=a.admin_user,
            password_hash=hash_password(a.admin_pass),
            pin=hash_password(a.admin_pin) if a.admin_pin else None,
            role=StafRoleEnum.SUPERADMIN,
            nama_staf=a.admin_name,
            is_active=True,
        ))

        # 2. Config klinik (id_config=1 setelah truncate)
        db.add(MasterKlinikConfig(
            kode_klinik="JD",
            rm_prefix=(settings.rm_clinic_prefix or "A"),
            nama_klinik=a.nama_klinik,
            is_default=True,
            is_active=True,
        ))

        # 3. Tier membership (placeholder harga — edit di Settings)
        db.add_all([
            MasterMembership(
                nama_tier="VIP", harga_aktivasi=Decimal("5000000.00"), durasi_bulan=12,
                free_konsultasi_dokter=True, diskon_treatment_persen=Decimal("10.00"),
                diskon_produk_persen=Decimal("3.00"), is_active=True, urutan_tampilan=1,
                catatan="Placeholder — konfirmasi harga & benefit.",
            ),
            MasterMembership(
                nama_tier="VVIP", harga_aktivasi=Decimal("10000000.00"), durasi_bulan=12,
                free_konsultasi_dokter=True, diskon_treatment_persen=Decimal("20.00"),
                diskon_produk_persen=Decimal("3.00"), is_active=True, urutan_tampilan=2,
                catatan="Placeholder — konfirmasi harga & benefit.",
            ),
        ])

        # 4. Produk topikal
        for i, p in enumerate(prods, start=1):
            db.add(MasterProduk(
                kode_produk=f"TPK-{i:03d}",
                nama_produk=p["nama"],
                tipe_produk=TipeProdukEnum.RETAIL,
                satuan=p["satuan"],
                harga_jual=p["harga"],
                hpp_per_unit=p["hpp"],
                stok_terkini=0,
                stok_minimal=5,
                eligible_member_discount=True,
                is_active=True,
                pajak_persen=0,
            ))

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print("\n✅ SELESAI.")
    print(f"  Admin      : {a.admin_user} (Superadmin)")
    print(f"  Klinik     : {a.nama_klinik} (rm_prefix={settings.rm_clinic_prefix or 'A'})")
    print(f"  Tier       : VIP, VVIP (placeholder harga)")
    print(f"  Produk     : {len(prods)} topikal (TPK-001..TPK-{len(prods):03d}), eligible diskon member")
    print(f"  Treatment  : KOSONG (seed menyusul)")


if __name__ == "__main__":
    main()
