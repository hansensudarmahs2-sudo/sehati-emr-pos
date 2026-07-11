#!/usr/bin/env python3
"""
Import Historical Excel Data — Sehati Clinic
================================================

Import data klinik bulanan (Mar/Apr/Mei 2026) dari file Excel format
"RINCIAN KOMISI" ke database Sehati Clinic sebagai dummy/historical data.

USAGE:
    cd sehati_clinic/
    python ../seed_data/import_excel_historical.py [options]

OPTIONS:
    --dry-run             Preview tanpa write ke DB (recommended pertama kali)
    --files PATH [PATH..] Override default folder (seed_data/historical_excel/*.xlsx)
    --yes                 Skip confirmation prompt (untuk automation)
    --limit-faktur N      Hanya import N faktur pertama (untuk testing)

DESIGN DECISIONS (locked 2026-06-05):
    1. Auto-create master_treatment + master_produk dari distinct items
    2. Stok awal produk = 1000 unit (safe untuk testing)
    3. Konsultasi Kulit → pemeriksaan_klinis (SOAP) saja, no kunjungan_tindakan
    4. Status: kunjungan=COMPLETED, transaksi LUNAS implisit, pembayaran=CASH
    5. Dokter mapping: pakai existing user OWNER (asumsi dr. Hansen = Owner)
    6. Idempotent: track imported faktur via keterangan field di kunjungan
"""

import argparse
import sys
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

import openpyxl


# =========================================================================
# Config
# =========================================================================
DEFAULT_FOLDER = Path(__file__).parent / "historical_excel"
STOK_AWAL_DEFAULT = 1000
KONSULTASI_NAMES = {"Konsultasi Kulit"}  # → SOAP, bukan treatment
IDEMPOTENT_KEY_PREFIX = "[LEGACY-IMPORT]"  # prefix di keterangan kunjungan


# =========================================================================
# Excel Parser
# =========================================================================
def parse_excel_file(path: Path) -> list[dict]:
    """Parse 1 file Excel ke list of dict (1 row data per dict)."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Data Export"]
    headers_raw = ["tanggal_str", "faktur", "layanan", "no_id", "pasien",
                   "id_tm", "tm_nama", "poliklinik", "asistensi", "asuransi",
                   "jenis", "kode", "nama_item", "jlh", "gross",
                   "diskon", "nilai_jual", "tarif_komisi", "bayar",
                   "pembayar", "total_komisi"]
    rows = []
    for row in ws.iter_rows(min_row=4, max_row=ws.max_row, values_only=True):
        # Skip footer & legend
        if row[0] is None and row[12] is None:
            continue
        if row[12] == "TOTAL":
            continue
        if isinstance(row[0], str) and ("RJ:" in row[0] or "Pembayar" in row[0]):
            continue
        if row[3] is None or row[1] is None:
            continue
        d = dict(zip(headers_raw, row))
        rows.append(d)
    return rows


def parse_tanggal(s: str) -> date:
    """'02/03/2026' → date(2026, 3, 2)"""
    parts = s.split("/")
    return date(int(parts[2]), int(parts[1]), int(parts[0]))


# =========================================================================
# Builders — distinct masters dari data
# =========================================================================
def build_distinct_pasien(rows: list[dict]) -> dict[str, str]:
    """no_rm → nama"""
    return {r["no_id"]: r["pasien"] for r in rows}


def build_distinct_treatments(rows: list[dict]) -> dict[str, Decimal]:
    """JENIS=P non-Konsul → {nama: harga_referensi}. Skip Konsultasi Kulit."""
    treatments = {}
    for r in rows:
        if r["jenis"] != "P":
            continue
        if r["nama_item"] in KONSULTASI_NAMES:
            continue
        if r["nama_item"] not in treatments:
            treatments[r["nama_item"]] = Decimal(str(r["gross"] or 0))
    return treatments


def build_distinct_produk(rows: list[dict]) -> dict[str, dict]:
    """JENIS=D → {nama: {kode, harga, satuan}}"""
    produk = {}
    for r in rows:
        if r["jenis"] != "D":
            continue
        nama = r["nama_item"]
        if nama in produk:
            continue
        kode = str(r["kode"]) if r["kode"] not in (None, "-", "") else f"AUTO-{len(produk)+1:04d}"
        produk[nama] = {
            "kode_produk": kode[:30],
            "harga": Decimal(str(r["gross"] or 0)) / Decimal(str(r["jlh"] or 1)),
        }
    return produk


def group_by_faktur(rows: list[dict]) -> dict:
    """Group all rows by faktur number → ordered dict-like."""
    faktur_map = {}
    for r in rows:
        f = r["faktur"]
        faktur_map.setdefault(f, []).append(r)
    return faktur_map


# =========================================================================
# DB Operations
# =========================================================================
def get_owner_staf(db):
    """Get existing user with role OWNER."""
    from app.db.models import MasterStaf, StafRoleEnum
    from sqlalchemy import select
    stmt = select(MasterStaf).where(MasterStaf.role == StafRoleEnum.OWNER).limit(1)
    return db.execute(stmt).scalars().first()


def upsert_pasien(db, no_rm: str, nama: str, owner_id: int) -> int:
    """Get-or-create pasien. Return id_pasien."""
    from app.db.models import Pasien
    from sqlalchemy import select
    existing = db.execute(select(Pasien).where(Pasien.no_rm == no_rm)).scalars().first()
    if existing:
        return existing.id_pasien
    p = Pasien(
        no_rm=no_rm,
        nama=nama,
        id_staf=owner_id,
        sumber_referensi="(legacy import)",
    )
    db.add(p)
    db.flush()
    return p.id_pasien


def upsert_treatment(db, nama: str, harga: Decimal, owner_id: int) -> int:
    """Get-or-create master_treatment. Return id_treatment."""
    from app.db.models import MasterTreatment
    from sqlalchemy import select
    existing = db.execute(
        select(MasterTreatment).where(MasterTreatment.nama_treatment == nama)
    ).scalars().first()
    if existing:
        return existing.id_treatment
    t = MasterTreatment(
        nama_treatment=nama[:100],
        role_pelaksana="Dokter",
        durasi_menit=30,
        harga=float(harga),
        is_active=True,
        id_staf=owner_id,
    )
    db.add(t)
    db.flush()
    return t.id_treatment


def upsert_produk(db, nama: str, kode: str, harga: Decimal,
                   stok_awal: int, owner_id: int) -> int:
    """Get-or-create master_produk. Return id_produk."""
    from app.db.models import MasterProduk, TipeProdukEnum
    from sqlalchemy import select
    existing = db.execute(
        select(MasterProduk).where(MasterProduk.nama_produk == nama)
    ).scalars().first()
    if existing:
        return existing.id_produk
    # Pastikan kode unique
    base_kode = kode
    suffix = 0
    while True:
        check = db.execute(
            select(MasterProduk).where(MasterProduk.kode_produk == kode)
        ).scalars().first()
        if not check:
            break
        suffix += 1
        kode = f"{base_kode}-{suffix}"
    p = MasterProduk(
        kode_produk=kode[:30],
        nama_produk=nama[:100],
        tipe_produk=TipeProdukEnum.RETAIL,
        harga_jual=float(harga),
        stok_terkini=float(stok_awal),
        stok_minimal=10.0,
        satuan="pcs",
        is_active=True,
    )
    db.add(p)
    db.flush()
    return p.id_produk


def faktur_already_imported(db, faktur: int) -> bool:
    """Cek apakah faktur sudah pernah di-import (via keterangan field)."""
    from app.db.models import Kunjungan
    from sqlalchemy import select
    marker = f"{IDEMPOTENT_KEY_PREFIX} #{faktur}"
    existing = db.execute(
        select(Kunjungan).where(Kunjungan.keluhan_utama.contains(marker))
    ).scalars().first()
    return existing is not None


def create_kunjungan_for_faktur(
    db, faktur: int, faktur_rows: list[dict],
    id_pasien: int, owner_id: int,
    treatment_map: dict, produk_map: dict,
) -> dict:
    """
    Create 1 kunjungan + child entities untuk 1 faktur.
    Returns stats: {kunjungan: 1, soap: N, tindakan: N, resep: N, transaksi: 1, omzet: Rp}.
    """
    from app.db.models import (
        Kunjungan, PemeriksaanKlinis, KunjunganTindakan,
        KunjunganResep, TransaksiKasir, TransaksiPembayaran,
        StatusTindakanEnum, StatusItemResepEnum,
    )

    # Build snapshot tanggal dari row pertama
    tgl = parse_tanggal(faktur_rows[0]["tanggal_str"])
    tgl_dt = datetime.combine(tgl, time(10, 0))  # default jam 10:00

    # Build keterangan dengan idempotent marker
    keluhan = f"{IDEMPOTENT_KEY_PREFIX} #{faktur} (Konsultasi Kulit & Kelamin)"

    k = Kunjungan(
        id_pasien=id_pasien,
        id_staf_fo=owner_id,
        tgl_kunjungan=tgl_dt,
        status_antrian="COMPLETED",
        sumber_pendaftaran="WALK_IN",
        keluhan_utama=keluhan,
    )
    db.add(k)
    db.flush()
    id_kunjungan = k.id_kunjungan

    stats = {"soap": 0, "tindakan": 0, "resep": 0, "omzet": Decimal("0")}
    rincian_lines = []

    for r in faktur_rows:
        nilai = Decimal(str(r["nilai_jual"] or 0))
        diskon = Decimal(str(r["diskon"] or 0))
        gross = Decimal(str(r["gross"] or 0))
        qty = Decimal(str(r["jlh"] or 1))
        nama_item = r["nama_item"]
        jenis = r["jenis"]

        if jenis == "P" and nama_item in KONSULTASI_NAMES:
            # SOAP
            soap = PemeriksaanKlinis(
                id_kunjungan=id_kunjungan,
                id_pasien=id_pasien,
                id_staf_dokter=owner_id,
                anamnesa="(legacy import — imported from 2026 historical export)",
                pemeriksaan_fisik="(legacy import)",
                diagnosa="(legacy import — diagnosa tidak ter-record di sumber data)",
            )
            db.add(soap)
            stats["soap"] += 1
            rincian_lines.append(f"KON: {nama_item} = Rp {nilai}")
        elif jenis == "P":
            # Treatment
            id_treatment = treatment_map.get(nama_item)
            if id_treatment is None:
                continue
            tindakan = KunjunganTindakan(
                id_kunjungan=id_kunjungan,
                id_treatment=id_treatment,
                status_tindakan=StatusTindakanEnum.SELESAI,
                id_staf_pelaksana=owner_id,
                waktu_mulai=tgl_dt,
                waktu_selesai=datetime.combine(tgl, time(10, 30)),
            )
            db.add(tindakan)
            stats["tindakan"] += 1
            rincian_lines.append(f"TND: {nama_item} = Rp {nilai}")
        elif jenis == "D":
            # Resep
            id_produk = produk_map.get(nama_item)
            if id_produk is None:
                continue
            harga_satuan = (gross / qty) if qty > 0 else Decimal("0")
            resep = KunjunganResep(
                id_kunjungan=id_kunjungan,
                id_produk=id_produk,
                qty=float(qty),
                status_item=StatusItemResepEnum.DIBAYAR,
                id_staf_input=owner_id,
            )
            db.add(resep)
            stats["resep"] += 1
            rincian_lines.append(f"OBT: {nama_item} ×{qty} = Rp {nilai}")

        stats["omzet"] += nilai

    # Transaksi kasir + pembayaran
    total = stats["omzet"]
    trx = TransaksiKasir(
        id_kunjungan=id_kunjungan,
        id_staf_kasir=owner_id,
        rincian_tagihan="\n".join(rincian_lines),
        subtotal=float(total),
        nominal_diskon=0.0,
        total_tagihan=float(total),
        waktu_bayar=datetime.combine(tgl, time(11, 0)),
    )
    db.add(trx)
    db.flush()

    pembayaran = TransaksiPembayaran(
        id_transaksi=trx.id_transaksi,
        metode_bayar="CASH",
        nominal=float(total),
    )
    db.add(pembayaran)

    return stats


# =========================================================================
# Main
# =========================================================================
def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Preview tanpa write ke DB")
    parser.add_argument("--files", nargs="+", help="Override default Excel files")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--limit-faktur", type=int, help="Limit jumlah faktur (testing)")
    args = parser.parse_args()

    # Resolve file list
    if args.files:
        files = [Path(f) for f in args.files]
    else:
        files = sorted(DEFAULT_FOLDER.glob("*.xlsx"))
    if not files:
        print(f"❌ Tidak ada file Excel ditemukan di {DEFAULT_FOLDER}")
        sys.exit(1)

    print(f"\n📥 Sehati Clinic — Excel Historical Import")
    print(f"   Mode: {'DRY-RUN (no write)' if args.dry_run else 'WRITE'}")
    print(f"   Files: {[f.name for f in files]}")

    # Parse all rows
    print("\n[Phase 1] Reading Excel files...")
    all_rows = []
    for f in files:
        rows = parse_excel_file(f)
        print(f"   {f.name}: {len(rows)} data rows")
        all_rows.extend(rows)
    print(f"   TOTAL: {len(all_rows)} rows")

    # Pre-analysis
    distinct_pasien = build_distinct_pasien(all_rows)
    distinct_treatments = build_distinct_treatments(all_rows)
    distinct_produk = build_distinct_produk(all_rows)
    faktur_groups = group_by_faktur(all_rows)
    if args.limit_faktur:
        # Take first N fakturs
        limited = dict(list(faktur_groups.items())[:args.limit_faktur])
        faktur_groups = limited
        print(f"\n⚠ Limiting to first {args.limit_faktur} faktur (testing mode)")

    print(f"\n[Phase 2] Analysis:")
    print(f"   Unique pasien:     {len(distinct_pasien)}")
    print(f"   Unique treatments: {len(distinct_treatments)} (non-Konsul)")
    print(f"   Unique produk:     {len(distinct_produk)}")
    print(f"   Unique faktur:     {len(faktur_groups)}")

    # Confirmation
    if not args.dry_run and not args.yes:
        ans = input(f"\n⚠ Akan import ke DB. Lanjut? [y/N] ").strip().lower()
        if ans != "y":
            print("Cancelled.")
            sys.exit(0)

    if args.dry_run:
        print("\n✅ Dry-run selesai. Preview only — tidak ada DB write.")
        print("\nSample 3 faktur pertama:")
        for i, (fak, rows) in enumerate(list(faktur_groups.items())[:3]):
            tgl = rows[0]["tanggal_str"]
            pas = rows[0]["pasien"]
            total = sum(Decimal(str(r["nilai_jual"] or 0)) for r in rows)
            print(f"\n   Faktur #{fak} ({tgl}) — {pas} — Rp {total}")
            for r in rows:
                marker = "🩺" if r["jenis"] == "P" and r["nama_item"] in KONSULTASI_NAMES else \
                         "💉" if r["jenis"] == "P" else "💊"
                print(f"     {marker} {r['jenis']}: {r['nama_item']} ×{r['jlh']} = Rp {r['nilai_jual']}")
        return

    # ===== ACTUAL WRITE =====
    print("\n[Phase 3] Connecting to DB...")
    sys.path.insert(0, str(Path(__file__).parent.parent / "sehati_clinic"))
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        owner = get_owner_staf(db)
        if owner is None:
            print("❌ Tidak ada user dengan role OWNER. Buat user OWNER dulu.")
            sys.exit(1)
        owner_id = owner.id_staf
        print(f"   Owner: {owner.nama_staf} (id_staf={owner_id})")

        # Pass A: Build masters
        print("\n[Phase 4] Building master_treatment + master_produk...")
        treatment_map = {}
        for nama, harga in distinct_treatments.items():
            treatment_map[nama] = upsert_treatment(db, nama, harga, owner_id)
        produk_map = {}
        for nama, info in distinct_produk.items():
            produk_map[nama] = upsert_produk(
                db, nama, info["kode_produk"], info["harga"],
                STOK_AWAL_DEFAULT, owner_id,
            )
        db.commit()
        print(f"   ✓ Treatments: {len(treatment_map)} ready")
        print(f"   ✓ Produk:     {len(produk_map)} ready (stok awal {STOK_AWAL_DEFAULT})")

        # Pass B: Per-faktur
        print("\n[Phase 5] Importing kunjungan per faktur...")
        totals = {"pasien_new": 0, "kunjungan": 0, "soap": 0,
                  "tindakan": 0, "resep": 0, "transaksi": 0,
                  "omzet": Decimal("0"), "skipped": 0}

        # Track pasien yang sudah di-create supaya bisa count "new"
        pasien_map = {}  # no_rm → id_pasien
        existing_count = 0
        from app.db.models import Pasien
        from sqlalchemy import select
        for no_rm in distinct_pasien:
            check = db.execute(select(Pasien).where(Pasien.no_rm == no_rm)).scalars().first()
            if check:
                pasien_map[no_rm] = check.id_pasien
                existing_count += 1

        for idx, (faktur, rows) in enumerate(faktur_groups.items(), 1):
            if idx % 50 == 0:
                print(f"   ... processed {idx}/{len(faktur_groups)} fakturs")

            if faktur_already_imported(db, faktur):
                totals["skipped"] += 1
                continue

            no_rm = rows[0]["no_id"]
            nama_pasien = rows[0]["pasien"]
            if no_rm in pasien_map:
                id_pasien = pasien_map[no_rm]
            else:
                id_pasien = upsert_pasien(db, no_rm, nama_pasien, owner_id)
                pasien_map[no_rm] = id_pasien
                totals["pasien_new"] += 1

            stats = create_kunjungan_for_faktur(
                db, faktur, rows, id_pasien, owner_id,
                treatment_map, produk_map,
            )
            totals["kunjungan"] += 1
            totals["transaksi"] += 1
            for k in ("soap", "tindakan", "resep"):
                totals[k] += stats[k]
            totals["omzet"] += stats["omzet"]

            # Commit per 25 faktur untuk safety
            if idx % 25 == 0:
                db.commit()

        db.commit()

        # Final report
        print("\n" + "=" * 60)
        print("✅ IMPORT SELESAI")
        print("=" * 60)
        print(f"   Pasien baru:        {totals['pasien_new']} (existing: {existing_count})")
        print(f"   Treatment baru:     {len(treatment_map)} unique")
        print(f"   Produk baru:        {len(produk_map)} unique")
        print(f"   Kunjungan dibuat:   {totals['kunjungan']}")
        print(f"   SOAP dibuat:        {totals['soap']}")
        print(f"   Tindakan dibuat:    {totals['tindakan']}")
        print(f"   Resep dibuat:       {totals['resep']}")
        print(f"   Transaksi dibuat:   {totals['transaksi']}")
        print(f"   Faktur di-skip:     {totals['skipped']} (sudah diimport sebelumnya)")
        print(f"   Total omzet:        Rp {totals['omzet']:,}".replace(",", "."))
        print("=" * 60)

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error: {e!r}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
