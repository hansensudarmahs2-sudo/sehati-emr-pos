"""
Seed Clean-Slate (Finance-complete) — Sehati eMR-POS.

Mengisi ulang db_sehati dengan data SINTETIS lengkap yang mengisi SEMUA field
yang dibutuhkan Finance Module (Kontrak Data v2): hpp/BHP, doc_number, diskon per
item, mutasi stok bernilai, dll. Dipakai untuk menguji kontrak Sehati -> Finance.

FASE:
  S1 (file ini) : masters + pasien (finance-complete).
  S2            : stream operasional 6 bulan (kunjungan/transaksi/pembayaran/item/stok/void/refund/membership).
  S3            : pembelian (PO/faktur bernilai).

USAGE (WSL, venv aktif, dari sehati_clinic/):
    python scripts/seed_finance_cleanslate.py --phase masters            # seed masters+pasien (tanpa wipe)
    python scripts/seed_finance_cleanslate.py --phase masters --wipe     # WIPE dulu (minta konfirmasi), lalu seed
    python scripts/seed_finance_cleanslate.py --phase masters --wipe --yes  # tanpa prompt (hati-hati)

SAFETY:
- Target DB = dari .env (settings.db_name). Tampilkan nama DB sebelum jalan.
- --wipe TRUNCATE seluruh tabel data (butuh konfirmasi ketik nama DB, kecuali --yes).
- PASTIKAN backup sudah dibuat (backup_all.py). Clean-slate = destruktif.
"""

import argparse
import random
import sys
from datetime import date, datetime, time as dtime, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import logging  # noqa: E402
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
for _lg in ("sqlalchemy.engine", "sqlalchemy.engine.Engine"):
    logging.getLogger(_lg).setLevel(logging.WARNING)  # senyapkan echo SQL

from app.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.db.session import engine as _eng  # noqa: E402
_eng.echo = False  # matikan echo SQL definitif
import logging as _l
for _n in ("sqlalchemy.engine","sqlalchemy.engine.Engine"):
    _l.getLogger(_n).setLevel(_l.WARNING)  # senyapkan echo (setelah engine dibuat)
from app.db.models import (  # noqa: E402
    GenderEnum,
    MasterDistributor,
    MasterKlinikConfig,
    MasterMembership,
    MasterProduk,
    MasterStaf,
    MasterTreatment,
    MembershipTierEnum,
    InventoryStok,
    Pasien,
    StafRoleEnum,
    TipeProdukEnum,
    VerifikasiEnum,
)

SEED = 42

# Tabel data untuk di-TRUNCATE saat --wipe (alembic_version DIKECUALIKAN).
RESET_TABLES = [
    "audit_log", "komisi_ledger",
    "transaksi_refund", "transaksi_pembayaran",
    "transaksi_detail_tindakan", "transaksi_detail_produk", "transaksi_kasir",
    "kasir_closing",
    "kunjungan_resep", "kunjungan_tindakan", "kunjungan_antropometri",
    "kunjungan_foto", "pemeriksaan_klinis",
    "pasien_rencana_treatment", "pasien_resep_iterasi",
    "pasien_membership_kuota", "pasien_membership_history",
    "pasien_alergi", "pasien_penyakit_kronis", "kunjungan",
    "retur_produk_item", "retur_produk",
    "faktur_penerimaan", "pemesanan_receive", "pemesanan_item", "pemesanan",
    "stock_opname_item", "stock_opname",
    "inventory_history", "stok_lot",
    "treatment_komponen",
    "master_membership_benefit_treatment", "master_membership",
    "master_produk", "master_treatment", "inventory_stok",
    "master_distributor", "klinik_apoteker", "lokasi_pengiriman",
    "master_penyakit_kronis",
    "jadwal_booking",
    "pasien", "master_staf", "master_klinik_config",
]

STAF_SEEDS = [
    # (username, password, nama, role)
    ("owner", "owner123", "dr. Hansen Sudarma", StafRoleEnum.OWNER),
    ("dokter_a", "dokter123", "dr. Andi Wijaya", StafRoleEnum.DOKTER),
    ("dokter_b", "dokter123", "dr. Bella Santoso", StafRoleEnum.DOKTER),
    ("perawat_a", "perawat123", "Ns. Citra", StafRoleEnum.PERAWAT),
    ("perawat_b", "perawat123", "Ns. Dewi", StafRoleEnum.PERAWAT),
    ("perawat_c", "perawat123", "Ns. Eka", StafRoleEnum.PERAWAT),
    ("perawat_d", "perawat123", "Ns. Fani", StafRoleEnum.PERAWAT),
    ("apoteker_a", "apoteker123", "Apt. Gita", StafRoleEnum.APOTEKER),
    ("fo_a", "fo123", "Frontdesk Hana", StafRoleEnum.FO),
    ("kasir_a", "kasir123", "Kasir Indah", StafRoleEnum.KASIR),
]

# (nama, role_pelaksana, durasi, harga, harga_paket, bhp_nominal)
TREATMENT_SEEDS = [
    ("Konsultasi Dokter", "Dokter", 30, 150_000, None, 5_000),
    ("Facial Acne", "Perawat", 60, 350_000, None, 80_000),
    ("Facial Whitening", "Perawat", 60, 450_000, None, 110_000),
    ("Chemical Peeling", "Perawat", 45, 500_000, None, 140_000),
    ("Microdermabrasi", "Perawat", 45, 450_000, None, 100_000),
    ("Suntik Vitamin C", "Perawat", 15, 250_000, None, 90_000),
    ("IV Drip Hydration", "Perawat", 60, 400_000, None, 160_000),
    ("Konsultasi Gizi", "Dokter", 30, 200_000, None, 5_000),
    ("Series Laser Hair Removal", "Perawat", 60, 800_000, 600_000, 180_000),
    ("Series Photo Facial", "Perawat", 45, 700_000, 500_000, 150_000),
    ("Series Treatment Acne", "Perawat", 60, 600_000, 450_000, 130_000),
    ("Series Slimming", "Perawat", 90, 1_000_000, 750_000, 220_000),
]

MEMBERSHIP_SEEDS = [
    # (nama_tier, harga_aktivasi, durasi_bulan, free_konsul, diskon_treatment%, diskon_produk%)
    ("Silver", 500_000, 12, True, 10.0, 10.0),
    ("Gold", 1_000_000, 12, True, 15.0, 15.0),
    ("Platinum", 2_500_000, 12, True, 20.0, 20.0),
]

# (nama_bahan, satuan, satuan_beli, rasio, harga_modal, stok_gudang, stok_kabin)
BAHAN_SEEDS = [
    ("Serum Vitamin C (vial)", "ml", "botol", 30, 8_000, 300, 50),
    ("Larutan Peeling TCA", "ml", "botol", 50, 12_000, 200, 40),
    ("Masker Algae", "gr", "pack", 500, 500, 2000, 300),
    ("Jarum Mesotherapy", "pcs", "box", 100, 1_500, 500, 100),
    ("Cairan Infus NaCl", "ml", "botol", 500, 20, 5000, 500),
    ("Vitamin C Injeksi (amp)", "amp", "box", 30, 15_000, 150, 30),
    ("Kapas Steril", "gr", "pack", 500, 100, 3000, 400),
    ("Sarung Tangan Latex", "pcs", "box", 100, 800, 800, 200),
    ("Gel Ultrasound", "ml", "botol", 250, 60, 2000, 300),
    ("Alkohol Swab", "pcs", "box", 100, 300, 1000, 250),
    ("Hyaluronic Serum (vial)", "ml", "botol", 30, 18_000, 120, 25),
    ("Krim Anestesi Topikal", "gr", "tube", 30, 6_000, 200, 40),
]

DISTRIBUTOR_SEEDS = [
    ("Kimia Farma Trading", "Jl. Veteran No. 9, Jakarta", "021-5551001", "Bpk. Rudi"),
    ("Anugerah Pharmindo", "Jl. Industri No. 21, Bekasi", "021-5551002", "Ibu Sinta"),
    ("Enseval Putera", "Jl. Pulo Gadung No. 5, Jakarta", "021-5551003", "Bpk. Toni"),
    ("Merapi Utama Pharma", "Jl. Raya Bogor No. 88, Depok", "021-5551004", "Ibu Wulan"),
    ("Distributor Kosmetik Prima", "Jl. Sudirman No. 12, Jakarta", "021-5551005", "Bpk. Yoga"),
]

NAMA_PRIA = ["Andi", "Budi", "Cahya", "Dedi", "Eko", "Fajar", "Gilang", "Hadi", "Iwan", "Joko",
             "Kurnia", "Lukman", "Made", "Nanda", "Oscar", "Putra", "Rizki", "Surya", "Toni", "Umar"]
NAMA_WANITA = ["Anita", "Bunga", "Citra", "Dewi", "Eka", "Fani", "Gita", "Hana", "Indah", "Juli",
               "Kania", "Maya", "Nila", "Olga", "Putri", "Rina", "Sari", "Tania", "Ulfa", "Vera"]
NAMA_BELAKANG = ["Pratama", "Wijaya", "Santoso", "Susanto", "Hartono", "Wibowo", "Setiawan",
                 "Kurniawan", "Halim", "Nugroho", "Permata", "Anggraini"]


def _obat_retail():
    obat = [
        ("OBT001", "Paracetamol 500mg", "tablet", 2_500), ("OBT002", "Amoxicillin 500mg", "kapsul", 3_500),
        ("OBT003", "Cetirizine 10mg", "tablet", 4_500), ("OBT004", "Vitamin C 500mg", "tablet", 2_000),
        ("OBT005", "Asam Mefenamat 500mg", "tablet", 3_000), ("OBT006", "Salep Mata Gentamicin", "tube", 35_000),
        ("OBT007", "Salep Hidrokortison", "tube", 28_000), ("OBT008", "Salep Mupirocin", "tube", 65_000),
        ("OBT009", "Kapsul Omeprazole 20mg", "kapsul", 5_000), ("OBT010", "Salep Bioplacenton", "tube", 45_000),
        ("OBT011", "Salep Ketoconazole", "tube", 35_000), ("OBT012", "Tablet Domperidone 10mg", "tablet", 4_000),
    ]
    retail = [
        ("RET001", "Sunscreen SPF 50+", "tube", 150_000), ("RET002", "Moisturizer Hyaluronic", "botol", 250_000),
        ("RET003", "Serum Vitamin C 20%", "botol", 350_000), ("RET004", "Cleanser Glow Boost", "botol", 180_000),
        ("RET005", "Toner Niacinamide", "botol", 200_000), ("RET006", "Eye Cream Anti Aging", "tube", 320_000),
        ("RET007", "Body Lotion Whitening", "botol", 165_000), ("RET008", "Sheet Mask (pack 5)", "pcs", 100_000),
        ("RET009", "Acne Patch (pack 12)", "pcs", 65_000), ("RET010", "Exfoliator AHA BHA", "botol", 280_000),
        ("RET011", "Retinol Serum 0.5%", "botol", 380_000), ("RET012", "Collagen Drink (box 14)", "box", 350_000),
    ]
    return obat, retail


# ---------------------------------------------------------------------------
def safety_print():
    print(f"[seed] Target DB : {settings.db_name}  (host={settings.database_url.split('@')[-1]})")


def confirm_wipe(auto_yes: bool):
    if auto_yes:
        return True
    print("\n  ⚠  --wipe akan TRUNCATE SELURUH data di DB di atas (clean-slate).")
    print("     Pastikan backup sudah dibuat (backup_all.py).")
    ans = input(f"     Ketik nama DB '{settings.db_name}' untuk konfirmasi: ").strip()
    return ans == settings.db_name


def reset_all(db: Session):
    print("[reset] TRUNCATE semua tabel data...")
    db.execute(text("SET FOREIGN_KEY_CHECKS=0"))
    n_ok = 0
    for t in RESET_TABLES:
        try:
            db.execute(text(f"TRUNCATE TABLE {t}"))
            n_ok += 1
        except Exception as e:
            print(f"  [warn] {t}: {str(e)[:80]}")
    db.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    db.commit()
    print(f"[reset] Done ({n_ok}/{len(RESET_TABLES)} tabel).")


def seed_klinik(db: Session):
    if db.query(MasterKlinikConfig).filter_by(id_config=1).first():
        print("[seed] klinik_config: skip (ada)"); return
    db.add(MasterKlinikConfig(
        id_config=1, nama_klinik="Klinik JoDerma", kode_klinik="KLN", rm_prefix="J",
        alamat_baris1="Jl. Kesehatan No. 1", alamat_baris2="Jakarta Selatan",
        no_telepon="021-7000123", email="info@joderma.clinic",
        default_paper_nota="a5", default_paper_soap="a5",
    ))
    db.commit(); print("[seed] klinik_config: 1 ✓")


def seed_staf(db: Session):
    if db.query(MasterStaf).count() >= len(STAF_SEEDS):
        print("[seed] staf: skip (ada)"); return
    for u, p, n, r in STAF_SEEDS:
        if db.query(MasterStaf).filter_by(username=u).first():
            continue
        db.add(MasterStaf(username=u, password_hash=hash_password(p), nama_staf=n,
                          role=r, is_active=True, is_logged_in=False))
    db.commit(); print(f"[seed] staf: {len(STAF_SEEDS)} ✓")


def seed_membership(db: Session):
    if db.query(MasterMembership).count() >= len(MEMBERSHIP_SEEDS):
        print("[seed] membership: skip (ada)"); return
    for i, (nama, harga, durasi, fk, dt, dp) in enumerate(MEMBERSHIP_SEEDS):
        db.add(MasterMembership(nama_tier=nama, harga_aktivasi=harga, durasi_bulan=durasi,
                                free_konsultasi_dokter=fk, diskon_treatment_persen=dt,
                                diskon_produk_persen=dp, is_active=True, urutan_tampilan=i))
    db.commit(); print(f"[seed] membership: {len(MEMBERSHIP_SEEDS)} ✓")


def seed_treatment(db: Session):
    if db.query(MasterTreatment).count() >= len(TREATMENT_SEEDS):
        print("[seed] treatment: skip (ada)"); return
    for nama, role, durasi, harga, paket, bhp in TREATMENT_SEEDS:
        is_dokter = role == "Dokter"
        db.add(MasterTreatment(
            nama_treatment=nama, role_pelaksana=role, durasi_menit=durasi,
            harga=harga, harga_paket=paket,
            bhp_per_pakai_nominal=bhp,
            komisi_dokter_tipe="PERSEN_HARGA" if is_dokter else None,
            komisi_dokter_value=Decimal("10.0") if is_dokter else Decimal("0"),
            komisi_perawat_tipe=None if is_dokter else "PERSEN_HARGA",
            komisi_perawat_value=Decimal("0") if is_dokter else Decimal("2.5"),
            pajak_persen=Decimal("0"), is_active=True,
        ))
    db.commit(); print(f"[seed] treatment: {len(TREATMENT_SEEDS)} ✓ (with BHP+komisi)")


def seed_produk(db: Session):
    obat, retail = _obat_retail()
    total = len(obat) + len(retail)
    if db.query(MasterProduk).count() >= total:
        print("[seed] produk: skip (ada)"); return
    for k, n, s, h in obat:  # CABIN (apotek), hpp ~60%
        db.add(MasterProduk(kode_produk=k, nama_produk=n, tipe_produk=TipeProdukEnum.CABIN,
                            satuan=s, harga_jual=h, hpp_per_unit=round(h * 0.60),
                            stok_terkini=200, stok_minimal=20, eligible_member_discount=True))
    for k, n, s, h in retail:  # RETAIL, hpp ~45%
        db.add(MasterProduk(kode_produk=k, nama_produk=n, tipe_produk=TipeProdukEnum.RETAIL,
                            satuan=s, harga_jual=h, hpp_per_unit=round(h * 0.45),
                            stok_terkini=100, stok_minimal=15, eligible_member_discount=True))
    db.commit(); print(f"[seed] produk: {total} ✓ (with hpp_per_unit)")


def seed_bahan(db: Session):
    if db.query(InventoryStok).count() >= len(BAHAN_SEEDS):
        print("[seed] bahan: skip (ada)"); return
    for nama, sat, sat_beli, rasio, hm, sg, sk in BAHAN_SEEDS:
        db.add(InventoryStok(nama_bahan=nama, satuan=sat, satuan_pembelian=sat_beli,
                             rasio_konversi=rasio, harga_modal=hm,
                             stok_gudang_utama=sg, stok_kabin=sk))
    db.commit(); print(f"[seed] bahan (inventory_stok): {len(BAHAN_SEEDS)} ✓ (with harga_modal)")


def seed_distributor(db: Session):
    if db.query(MasterDistributor).count() >= len(DISTRIBUTOR_SEEDS):
        print("[seed] distributor: skip (ada)"); return
    for nama, alamat, telp, pic in DISTRIBUTOR_SEEDS:
        db.add(MasterDistributor(nama=nama, alamat=alamat, telepon=telp,
                                 kontak_person=pic, is_active=True))
    db.commit(); print(f"[seed] distributor: {len(DISTRIBUTOR_SEEDS)} ✓")


def seed_pasien(db: Session, n=100):
    if db.query(Pasien).count() >= n:
        print("[seed] pasien: skip (ada)"); return
    rng = random.Random(SEED)
    owner = db.query(MasterStaf).filter_by(role=StafRoleEnum.OWNER).first()
    owner_id = owner.id_staf if owner else None
    today = date.today()
    for i in range(n):
        pria = i % 2 == 0
        depan = rng.choice(NAMA_PRIA if pria else NAMA_WANITA)
        nama = f"{depan} {rng.choice(NAMA_BELAKANG)}"
        db.add(Pasien(
            no_rm=f"J{1001 + i:05d}", nama=nama,
            jenis_kelamin=GenderEnum.LAKI_LAKI if pria else GenderEnum.PEREMPUAN,
            tgl_lahir=today - timedelta(days=rng.randint(7300, 25550)),
            nomor_telepon=f"08{rng.randint(1000000000, 9999999999)}",
            tipe_membership=MembershipTierEnum.REGULAR,
            status_verifikasi=VerifikasiEnum.VERIFIED, id_staf=owner_id,
            created_at=datetime.combine(PERIOD_START + timedelta(days=rng.randint(0, 175)), dtime(9, 0)),
        ))
    db.commit(); print(f"[seed] pasien: {n} ✓")


def phase_masters(db: Session):
    seed_klinik(db); seed_staf(db); seed_membership(db)
    seed_treatment(db); seed_produk(db); seed_bahan(db)
    seed_distributor(db); seed_pasien(db)



# =============================================================================
# FASE S2 — Stream operasional 6 bulan (Jan-Jun 2026)
# =============================================================================
PERIOD_START = date(2026, 1, 1)
PERIOD_END = date(2026, 6, 30)
METODE_WEIGHTED = (["TUNAI"] * 40 + ["QRIS"] * 30 + ["DEBIT"] * 15 + ["TRANSFER"] * 10 + ["KREDIT"] * 5)


def _q2(x):
    return Decimal(str(round(float(x), 2)))


def phase_ops(db: Session):
    from app.db.models import (
        Kunjungan, KunjunganTindakan, KunjunganResep,
        TransaksiKasir, TransaksiDetailProduk, TransaksiDetailTindakan,
        TransaksiPembayaran, TransaksiRefund, InventoryHistory,
        PasienMembershipHistory, JenisMutasiEnum, StatusTindakanEnum,
        StatusItemResepEnum,
    )
    rng = random.Random(SEED + 7)

    produk = db.query(MasterProduk).all()
    treatments = db.query(MasterTreatment).all()
    bahan = db.query(InventoryStok).all()
    pasien = db.query(Pasien).all()
    memberships = db.query(MasterMembership).all()
    kasir = db.query(MasterStaf).filter(MasterStaf.role.in_([StafRoleEnum.KASIR, StafRoleEnum.OWNER])).all()
    dokter = db.query(MasterStaf).filter_by(role=StafRoleEnum.DOKTER).all()
    perawat = db.query(MasterStaf).filter_by(role=StafRoleEnum.PERAWAT).all()
    if not (produk and treatments and pasien and kasir and dokter and perawat):
        print("[ops] ABORT: master/pasien belum ada. Jalankan --phase masters dulu."); return

    prod_stock = {pr.id_produk: 9999 for pr in produk}
    bahan_stock = {b.id_bahan: 99999 for b in bahan}
    doc_counter = {}
    n_txn = n_void = n_refund = n_memb = 0
    bayar_txn_ids = []

    def next_doc(dt):
        key = dt.strftime("%Y-%m")
        doc_counter[key] = doc_counter.get(key, 0) + 1
        return f"TRX-{key}-{doc_counter[key]:06d}"

    cur = PERIOD_START
    while cur <= PERIOD_END:
        if cur.weekday() == 6:  # Minggu tutup
            cur += timedelta(days=1); continue
        n_today = rng.randint(3, 7)
        for _ in range(n_today):
            pas = rng.choice(pasien)
            jam = rng.randint(9, 19); menit = rng.choice([0, 15, 30, 45])
            waktu = datetime.combine(cur, dtime(jam, menit))

            mode = rng.random()
            n_t = n_p = 0
            if mode < 0.35: n_p = rng.randint(1, 3)
            elif mode < 0.70: n_t = rng.randint(1, 2)
            else: n_t = rng.randint(1, 2); n_p = rng.randint(1, 2)
            pick_t = [rng.choice(treatments) for _ in range(n_t)]
            pick_p = [rng.choice(produk) for _ in range(n_p)]
            if not pick_t and not pick_p: pick_p = [rng.choice(produk)]

            # kunjungan
            kj = Kunjungan(id_pasien=pas.id_pasien, tgl_kunjungan=waktu,
                           status_antrian="COMPLETED", sumber_pendaftaran="WALK_IN",
                           id_staf_fo=None)
            db.add(kj); db.flush()

            # transaksi header (angka diisi setelah item)
            trx = TransaksiKasir(
                id_kunjungan=kj.id_kunjungan, id_staf_kasir=rng.choice(kasir).id_staf,
                rincian_tagihan="{}", subtotal=Decimal("0"), nominal_diskon=Decimal("0"),
                total_tagihan=Decimal("0"), waktu_bayar=waktu, status_transaksi="BAYAR",
                dpp=None, ppn=Decimal("0"), is_kena_ppn=False,
            )
            db.add(trx); db.flush()
            trx.doc_number = next_doc(cur)

            line_items = []  # (jenis, obj_detail, subtotal_pre)
            subtotal = Decimal("0")

            for t in pick_t:
                harga = Decimal(str(t.harga)); sub = harga
                subtotal += sub
                kt = KunjunganTindakan(id_kunjungan=kj.id_kunjungan, id_treatment=t.id_treatment,
                                       status_tindakan=StatusTindakanEnum.SELESAI,
                                       id_dokter_pelaksana=rng.choice(dokter).id_staf,
                                       id_perawat_pelaksana=rng.choice(perawat).id_staf,
                                       waktu_mulai=waktu, waktu_selesai=waktu + timedelta(minutes=t.durasi_menit))
                db.add(kt); db.flush()
                dt_row = TransaksiDetailTindakan(
                    id_transaksi=trx.id_transaksi, id_kunjungan_tindakan=kt.id_kunjungan_tindakan,
                    id_treatment=t.id_treatment, qty=1, harga_satuan=harga,
                    diskon_item=Decimal("0"), subtotal=sub,
                    bhp_satuan=Decimal(str(t.bhp_per_pakai_nominal or 0)))
                db.add(dt_row)
                line_items.append(("T", dt_row, sub))
                # bahan terpakai (valued TINDAKAN)
                if bahan:
                    b = rng.choice(bahan); qb = rng.randint(1, 5)
                    bahan_stock[b.id_bahan] -= qb
                    hm = Decimal(str(b.harga_modal or 0))
                    db.add(InventoryHistory(tipe_item="BAHAN", id_bahan=b.id_bahan,
                        id_staf=rng.choice(perawat).id_staf, jenis_mutasi=JenisMutasiEnum.TINDAKAN,
                        qty_perubahan=-qb, stok_akhir=bahan_stock[b.id_bahan],
                        hpp_satuan=hm, nilai_mutasi=_q2(qb) * hm,
                        referensi=f"Tindakan {t.nama_treatment}", waktu_mutasi=waktu))

            for pr in pick_p:
                qp = rng.randint(1, 3); harga = Decimal(str(pr.harga_jual)); sub = harga * qp
                subtotal += sub
                db.add(KunjunganResep(id_kunjungan=kj.id_kunjungan, id_produk=pr.id_produk, qty=qp,
                                      status_item=StatusItemResepEnum.DIBAYAR,
                                      id_staf_input=rng.choice(dokter).id_staf))
                hpp = Decimal(str(pr.hpp_per_unit or 0))
                dp_row = TransaksiDetailProduk(id_transaksi=trx.id_transaksi, id_produk=pr.id_produk,
                    qty=qp, harga_satuan=harga, subtotal=sub, diskon_item=Decimal("0"), hpp_satuan=hpp)
                db.add(dp_row)
                line_items.append(("P", dp_row, sub))
                prod_stock[pr.id_produk] -= qp
                db.add(InventoryHistory(tipe_item="PRODUK", id_produk=pr.id_produk,
                    id_staf=trx.id_staf_kasir, jenis_mutasi=JenisMutasiEnum.PENJUALAN,
                    qty_perubahan=-qp, stok_akhir=prod_stock[pr.id_produk],
                    hpp_satuan=hpp, nilai_mutasi=_q2(qp) * hpp,
                    referensi=trx.doc_number, waktu_mutasi=waktu))

            # diskon (30% transaksi)
            diskon = Decimal("0"); promo = None
            if rng.random() < 0.30 and subtotal > 0:
                pct = rng.choice([Decimal("0.05"), Decimal("0.10"), Decimal("0.15")])
                diskon = (subtotal * pct).quantize(Decimal("1"))
                promo = f"Diskon {int(pct*100)}%"
            total = subtotal - diskon

            # alokasi diskon per item (pro-rata)
            if diskon > 0 and subtotal > 0:
                sisa = diskon
                for i, (_, row, sub) in enumerate(line_items):
                    if i == len(line_items) - 1:
                        row.diskon_item = sisa
                    else:
                        d = (diskon * sub / subtotal).quantize(Decimal("1"))
                        row.diskon_item = d; sisa -= d

            trx.subtotal = subtotal; trx.nominal_diskon = diskon
            trx.total_tagihan = total; trx.keterangan_promo = promo
            trx.rincian_tagihan = f'{{"items": {len(line_items)}, "total": {total}}}'

            # pembayaran (split kadang)
            settle = None
            metode1 = rng.choice(METODE_WEIGHTED)
            if metode1 != "TUNAI":
                settle = cur + timedelta(days=1)
            if rng.random() < 0.20 and total > 20000:
                part = (total / 2).quantize(Decimal("1"))
                db.add(TransaksiPembayaran(id_transaksi=trx.id_transaksi, metode_bayar="TUNAI",
                                           nominal=part, tgl_settle=None))
                db.add(TransaksiPembayaran(id_transaksi=trx.id_transaksi, metode_bayar="QRIS",
                                           nominal=total - part, tgl_settle=cur + timedelta(days=1)))
            else:
                db.add(TransaksiPembayaran(id_transaksi=trx.id_transaksi, metode_bayar=metode1,
                                           nominal=total, tgl_settle=settle))

            # VOID ~2.5%
            if rng.random() < 0.025:
                trx.status_transaksi = "VOID"
                trx.void_at = waktu + timedelta(hours=1)
                trx.void_by_id_staf = trx.id_staf_kasir
                trx.void_reason_code = "SALAH_INPUT"
                n_void += 1
            else:
                bayar_txn_ids.append((trx.id_transaksi, total, waktu, metode1))
            n_txn += 1

        # commit harian
        db.commit()
        cur += timedelta(days=1)

    # MEMBERSHIP ~15 aktivasi
    for _ in range(15):
        pas = rng.choice(pasien); tier = rng.choice(memberships)
        d = PERIOD_START + timedelta(days=rng.randint(0, 175))
        waktu = datetime.combine(d, dtime(rng.randint(9, 18), 0))
        harga = Decimal(str(tier.harga_aktivasi))
        trx = TransaksiKasir(id_kunjungan=None, id_staf_kasir=rng.choice(kasir).id_staf,
            rincian_tagihan='{"membership":1}', subtotal=harga, nominal_diskon=Decimal("0"),
            total_tagihan=harga, waktu_bayar=waktu, status_transaksi="BAYAR",
            id_membership_aktivasi=tier.id_membership, nominal_aktivasi_membership=harga,
            ppn=Decimal("0"), is_kena_ppn=False)
        db.add(trx); db.flush(); trx.doc_number = next_doc(d)
        db.add(TransaksiPembayaran(id_transaksi=trx.id_transaksi, metode_bayar="TRANSFER",
                                   nominal=harga, tgl_settle=d + timedelta(days=1)))
        db.add(PasienMembershipHistory(id_pasien=pas.id_pasien, id_membership=tier.id_membership,
            tgl_aktif=d, tgl_expired=d + timedelta(days=365), harga_bayar=harga,
            id_transaksi_aktivasi=trx.id_transaksi, id_staf_aktivasi=trx.id_staf_kasir,
            created_at=waktu))
        n_memb += 1
    db.commit()

    # REFUND ~1% dari transaksi BAYAR
    n_ref_target = max(3, len(bayar_txn_ids) // 100)
    for tid, total, waktu, metode in rng.sample(bayar_txn_ids, min(n_ref_target, len(bayar_txn_ids))):
        nilai = (total if rng.random() < 0.4 else (total / 2).quantize(Decimal("1")))
        db.add(TransaksiRefund(id_transaksi=tid, nilai_refund=nilai,
            tgl_refund=waktu + timedelta(days=rng.randint(1, 5)), metode_refund=metode,
            alasan=rng.choice(["Produk rusak", "Salah beli", "Reaksi alergi", "Batal treatment"]),
            id_staf_refund=rng.choice(kasir).id_staf))
        n_refund += 1
    db.commit()

    print(f"[ops] transaksi: {n_txn} (VOID {n_void}) | membership {n_memb} | refund {n_refund}")
    print("[ops] SELESAI.")



# =============================================================================
# FASE S3 — Pembelian (PO -> item -> receive -> faktur bernilai + RESTOCK)
# =============================================================================
def phase_purchasing(db: Session):
    from app.db.models import (
        Pemesanan, PemesananItem, PemesananReceive, FakturPenerimaan,
        StatusPemesananEnum, InventoryHistory, JenisMutasiEnum,
    )
    rng = random.Random(SEED + 13)
    produk = db.query(MasterProduk).all()
    bahan = db.query(InventoryStok).all()
    distributors = db.query(MasterDistributor).all()
    apoteker = (db.query(MasterStaf).filter_by(role=StafRoleEnum.APOTEKER).first()
                or db.query(MasterStaf).filter_by(role=StafRoleEnum.OWNER).first())
    if not (produk and distributors and apoteker):
        print("[buy] ABORT: master belum ada. Jalankan --phase masters dulu."); return

    po_day, fb_month = {}, {}
    prod_stock = {pr.id_produk: int(pr.stok_terkini or 0) for pr in produk}
    bahan_stock = {b.id_bahan: int((b.stok_gudang_utama or 0) + (b.stok_kabin or 0)) for b in bahan}
    n_po = n_recv = n_faktur = 0

    d = PERIOD_START
    while d <= PERIOD_END:
        if d.weekday() < 6 and rng.random() < 0.28:
            dist = rng.choice(distributors)
            po_day[d] = po_day.get(d, 0) + 1
            nomor_po = f"PO-{d.strftime('%y%m%d')}-{po_day[d]:03d}"
            tgl = datetime.combine(d, dtime(10, 0))
            po = Pemesanan(nomor_po=nomor_po, tgl_pemesanan=tgl, supplier_nama=dist.nama,
                           termin_hari=14, id_staf_pemesan=apoteker.id_staf,
                           status=StatusPemesananEnum.SUBMITTED, created_at=tgl)
            db.add(po); db.flush()

            items = []
            for _ in range(rng.randint(2, 5)):
                if bahan and rng.random() < 0.4:
                    b = rng.choice(bahan); qty = rng.randint(5, 30)
                    cost = _q2(Decimal(str(b.harga_modal or 0)) * Decimal(str(int(b.rasio_konversi or 1))))
                    it = PemesananItem(id_pemesanan=po.id_pemesanan, tipe_item="BAHAN",
                        id_bahan=b.id_bahan, nama_snapshot=b.nama_bahan,
                        satuan_snapshot=b.satuan_pembelian, qty_dipesan=qty, qty_diterima=0,
                        harga_satuan=cost, subtotal=cost * qty)
                    db.add(it); db.flush(); items.append(("BAHAN", b, it, qty, cost))
                else:
                    pr = rng.choice(produk); qty = rng.randint(20, 100)
                    cost = _q2(pr.hpp_per_unit or 0)
                    it = PemesananItem(id_pemesanan=po.id_pemesanan, tipe_item="PRODUK",
                        id_produk=pr.id_produk, nama_snapshot=pr.nama_produk,
                        satuan_snapshot=pr.satuan, qty_dipesan=qty, qty_diterima=0,
                        harga_satuan=cost, subtotal=cost * qty)
                    db.add(it); db.flush(); items.append(("PRODUK", pr, it, qty, cost))
            po.total_estimasi_biaya = sum((i[4] * i[3] for i in items), Decimal("0"))
            n_po += 1

            r = rng.random()
            if r < 0.05:
                po.status = StatusPemesananEnum.CANCELLED
                db.commit(); d += timedelta(days=1); continue
            partial = r < 0.20
            tgl_terima = tgl + timedelta(days=rng.randint(2, 10))
            diskon_persen = Decimal(str(rng.choice([0, 0, 2, 5])))
            ppn_persen = Decimal("11") if rng.random() < 0.6 else Decimal("0")

            fbkey = tgl_terima.strftime("%Y-%m"); fb_month[fbkey] = fb_month.get(fbkey, 0) + 1
            nomor_faktur = f"FB-{fbkey}-{fb_month[fbkey]:03d}"
            fak = FakturPenerimaan(id_pemesanan=po.id_pemesanan, nomor_faktur=nomor_faktur,
                id_distributor=dist.id_distributor, tgl_faktur=tgl_terima.date(),
                tgl_terima=tgl_terima, ppn_persen=ppn_persen, diskon_persen=diskon_persen,
                id_staf_penerima=apoteker.id_staf)
            db.add(fak); db.flush(); n_faktur += 1

            sub_order = Decimal("0")
            for tipe, obj, it, qty, cost in items:
                qrecv = qty if not partial else max(1, int(qty * rng.choice([0.3, 0.5, 0.7])))
                harga_terima = _q2(cost * (Decimal("1") - diskon_persen / 100))
                sub_order += cost * qrecv
                it.qty_diterima = qrecv
                db.add(PemesananReceive(id_pemesanan=po.id_pemesanan, id_pemesanan_item=it.id_item,
                    qty_diterima=qrecv, tgl_terima=tgl_terima, id_staf_penerima=apoteker.id_staf,
                    nomor_faktur=nomor_faktur, harga_terima=harga_terima,
                    id_distributor=dist.id_distributor, id_faktur=fak.id_faktur))
                n_recv += 1
                if tipe == "PRODUK":
                    prod_stock[obj.id_produk] = prod_stock.get(obj.id_produk, 0) + qrecv
                    db.add(InventoryHistory(tipe_item="PRODUK", id_produk=obj.id_produk,
                        id_staf=apoteker.id_staf, jenis_mutasi=JenisMutasiEnum.RESTOCK,
                        qty_perubahan=qrecv, stok_akhir=prod_stock[obj.id_produk],
                        hpp_satuan=harga_terima, nilai_mutasi=_q2(harga_terima * qrecv),
                        referensi=nomor_po, waktu_mutasi=tgl_terima))
                else:
                    rasio = int(obj.rasio_konversi or 1)
                    qty_pakai = qrecv * rasio
                    bahan_stock[obj.id_bahan] = bahan_stock.get(obj.id_bahan, 0) + qty_pakai
                    hpp_pakai = _q2(harga_terima / Decimal(str(rasio)))
                    db.add(InventoryHistory(tipe_item="BAHAN", id_bahan=obj.id_bahan,
                        id_staf=apoteker.id_staf, jenis_mutasi=JenisMutasiEnum.RESTOCK,
                        qty_perubahan=qty_pakai, stok_akhir=bahan_stock[obj.id_bahan],
                        hpp_satuan=hpp_pakai, nilai_mutasi=_q2(harga_terima * qrecv),
                        referensi=nomor_po, waktu_mutasi=tgl_terima))

            po.status = StatusPemesananEnum.PARTIAL_RECEIVED if partial else StatusPemesananEnum.RECEIVED
            sub_setelah = _q2(sub_order * (Decimal("1") - diskon_persen / 100))
            ppn_val = _q2(sub_setelah * ppn_persen / 100)
            fak.subtotal_order = _q2(sub_order)
            fak.subtotal_setelah_diskon = sub_setelah
            fak.total_ditagih = _q2(sub_setelah + ppn_val)
            db.commit()
        d += timedelta(days=1)

    print(f"[buy] PO: {n_po} | faktur: {n_faktur} | receive events: {n_recv}")
    print("[buy] SELESAI.")


def main():
    ap = argparse.ArgumentParser(description="Seed clean-slate finance-complete (Sehati).")
    ap.add_argument("--phase", choices=["masters", "ops", "purchasing", "all"], default="masters",
                    help="masters (S1) | ops (S2) | purchasing (S3) | all.")
    ap.add_argument("--wipe", action="store_true", help="TRUNCATE semua data dulu (clean-slate).")
    ap.add_argument("--yes", action="store_true", help="Skip prompt konfirmasi wipe.")
    args = ap.parse_args()

    safety_print()
    db = SessionLocal()
    try:
        if args.wipe:
            if not confirm_wipe(args.yes):
                print("[abort] Konfirmasi wipe gagal. Batal."); return 1
            reset_all(db)
        if args.phase in ("masters", "all"):
            phase_masters(db)
        if args.phase in ("ops", "all"):
            phase_ops(db)
        if args.phase in ("purchasing", "all"):
            phase_purchasing(db)
    finally:
        db.close()
    print("[seed] SELESAI.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
