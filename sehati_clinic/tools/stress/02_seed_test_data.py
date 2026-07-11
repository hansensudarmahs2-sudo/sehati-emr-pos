"""
Stress Test — Seed dummy data ke db_sehati_test.

USAGE:
    # Pastikan db_sehati_test sudah ada + schema imported (lihat README.md Step 1)
    source .venv/bin/activate
    python tools/stress/02_seed_test_data.py

    # Reset (truncate semua data, re-seed):
    python tools/stress/02_seed_test_data.py --reset

SAFETY:
- Script INI selalu force DB_NAME=db_sehati_test (hardcoded override).
- Tidak akan pernah nyentuh db_sehati production.
- Idempotent: aman di-rerun kalau ada error di tengah.
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path

# Force test DB BEFORE app imports (pydantic-settings honor env var)
os.environ["DB_NAME"] = "db_sehati_test"

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.db.models import (  # noqa: E402
    GenderEnum,
    MasterKlinikConfig,
    MasterMembership,
    MasterProduk,
    MasterStaf,
    MasterTreatment,
    MembershipTierEnum,
    Pasien,
    StafRoleEnum,
    TipeProdukEnum,
    VerifikasiEnum,
)


# =============================================================================
# Configuration
# =============================================================================
TEST_DB_NAME = "db_sehati_test"

STAF_SEEDS = [
    # (username, password, nama, role)
    ("superadmin", "admin123", "Owner Test Klinik", StafRoleEnum.OWNER),
    ("dokter_a", "dokter123", "Dr. Andi (Test)", StafRoleEnum.DOKTER),
    ("dokter_b", "dokter123", "Dr. Budi (Test)", StafRoleEnum.DOKTER),
    ("fo_test", "fo123", "Frontdesk Test", StafRoleEnum.FO),
    ("kasir_test", "kasir123", "Kasir Test", StafRoleEnum.KASIR),
    ("perawat_test", "perawat123", "Perawat Test", StafRoleEnum.PERAWAT),
]

# 10 single treatment + 5 series treatment
TREATMENT_SEEDS = [
    # Single (harga, harga_paket=NULL)
    ("Konsultasi Dokter", "Dokter", 30, 150_000, None),
    ("Facial Acne", "Perawat", 60, 350_000, None),
    ("Facial Whitening", "Perawat", 60, 450_000, None),
    ("Chemical Peeling", "Perawat", 45, 500_000, None),
    ("Microdermabrasi", "Perawat", 45, 450_000, None),
    ("Suntik Vitamin C", "Perawat", 15, 250_000, None),
    ("Cek Laboratorium", "Perawat", 30, 200_000, None),
    ("IV Drip Hydration", "Perawat", 60, 400_000, None),
    ("Pijat Refleksi", "Perawat", 60, 200_000, None),
    ("Konsultasi Gizi", "Dokter", 30, 200_000, None),
    # Series (harga single + harga_paket per-sesi)
    ("Series Laser Hair Removal", "Perawat", 60, 800_000, 600_000),
    ("Series Photo Facial", "Perawat", 45, 700_000, 500_000),
    ("Series Treatment Acne", "Perawat", 60, 600_000, 450_000),
    ("Series Slimming", "Perawat", 90, 1_000_000, 750_000),
    ("Series Whitening Body", "Perawat", 60, 850_000, 650_000),
]

# 25 obat (RETAIL=apotek) + 25 retail produk
def _make_produk_seeds():
    seeds = []
    obat_names = [
        ("OBT001", "Paracetamol 500mg", "tablet", 2_500),
        ("OBT002", "Amoxicillin 500mg", "kapsul", 3_500),
        ("OBT003", "Cetirizine 10mg", "tablet", 4_500),
        ("OBT004", "Vitamin C 500mg", "tablet", 2_000),
        ("OBT005", "Asam Mefenamat 500mg", "tablet", 3_000),
        ("OBT006", "Loperamide 2mg", "tablet", 3_500),
        ("OBT007", "Ranitidine 150mg", "tablet", 4_000),
        ("OBT008", "Cefadroxil 500mg", "kapsul", 5_500),
        ("OBT009", "Ibuprofen 400mg", "tablet", 3_000),
        ("OBT010", "Salep Mata Gentamicin", "tube", 35_000),
        ("OBT011", "Salep Hidrokortison", "tube", 28_000),
        ("OBT012", "Salep Mupirocin", "tube", 65_000),
        ("OBT013", "Sirup Ambroxol 60ml", "botol", 25_000),
        ("OBT014", "Sirup Loratadine 60ml", "botol", 30_000),
        ("OBT015", "Sirup OBH Combi 100ml", "botol", 18_000),
        ("OBT016", "Tablet ISDN 5mg", "tablet", 6_000),
        ("OBT017", "Kapsul Omeprazole 20mg", "kapsul", 5_000),
        ("OBT018", "Salep Bioplacenton", "tube", 45_000),
        ("OBT019", "Tablet Allopurinol 100mg", "tablet", 3_500),
        ("OBT020", "Tablet Simvastatin 10mg", "tablet", 4_500),
        ("OBT021", "Kapsul Antasida DOEN", "kapsul", 2_000),
        ("OBT022", "Tablet Glibenklamid 5mg", "tablet", 3_500),
        ("OBT023", "Tablet Metformin 500mg", "tablet", 3_000),
        ("OBT024", "Salep Ketoconazole", "tube", 35_000),
        ("OBT025", "Tablet Domperidone 10mg", "tablet", 4_000),
    ]
    retail_names = [
        ("RET001", "Sunscreen SPF 50+", "tube", 150_000),
        ("RET002", "Moisturizer Hyaluronic Acid", "botol", 250_000),
        ("RET003", "Serum Vitamin C 20%", "botol", 350_000),
        ("RET004", "Cleanser Glow Boost", "botol", 180_000),
        ("RET005", "Toner Niacinamide", "botol", 200_000),
        ("RET006", "Eye Cream Anti Aging", "tube", 320_000),
        ("RET007", "Lip Balm SPF 30", "stick", 75_000),
        ("RET008", "Body Lotion Whitening", "botol", 165_000),
        ("RET009", "Hand Cream Vitamin E", "tube", 95_000),
        ("RET010", "Sheet Mask Brightening (pack 5)", "pcs", 100_000),
        ("RET011", "Acne Patch (pack 12)", "pcs", 65_000),
        ("RET012", "Micellar Water 250ml", "botol", 145_000),
        ("RET013", "Exfoliator AHA BHA", "botol", 280_000),
        ("RET014", "Retinol Serum 0.5%", "botol", 380_000),
        ("RET015", "Collagen Drink (box 14)", "box", 350_000),
        ("RET016", "Vitamin Hair Supplement", "botol", 220_000),
        ("RET017", "Anti Aging Cream Night", "jar", 420_000),
        ("RET018", "Toner Acne Care", "botol", 175_000),
        ("RET019", "Lip Plumper Gloss", "stick", 95_000),
        ("RET020", "Body Scrub Coffee", "jar", 120_000),
        ("RET021", "Foot Cream Healing", "tube", 85_000),
        ("RET022", "Eye Patch Hydrogel (pack 10)", "pcs", 130_000),
        ("RET023", "Face Mist Rose", "botol", 110_000),
        ("RET024", "Bath Salt Lavender 500g", "pcs", 90_000),
        ("RET025", "Hair Mask Keratin 250ml", "botol", 195_000),
    ]
    for k, n, s, h in obat_names:
        seeds.append((k, n, TipeProdukEnum.CABIN, s, h, 100))
    for k, n, s, h in retail_names:
        seeds.append((k, n, TipeProdukEnum.RETAIL, s, h, 50))
    return seeds


MEMBERSHIP_SEEDS = [
    # (nama_tier, harga_aktivasi, durasi_bulan, free_konsul, diskon_treatment%, diskon_produk%)
    ("Bronze", 200_000, 12, False, 5.0, 5.0),
    ("Silver", 500_000, 12, True, 10.0, 10.0),
    ("Gold", 1_000_000, 12, True, 15.0, 15.0),
    ("Platinum", 2_500_000, 12, True, 20.0, 20.0),
]


# 100 nama pasien dummy — variasi gender + tier
def _make_pasien_seeds():
    nama_pria = [
        "Andi", "Budi", "Cahya", "Dedi", "Eko", "Fajar", "Gilang", "Hadi", "Iwan", "Joko",
        "Kurnia", "Lukman", "Made", "Nanda", "Oscar", "Putra", "Qodir", "Rizki", "Surya", "Toni",
        "Umar", "Vino", "Wira", "Xavier", "Yusuf",
    ]
    nama_wanita = [
        "Anita", "Bunga", "Citra", "Dewi", "Eka", "Fani", "Gita", "Hana", "Indah", "Juli",
        "Kania", "Lala", "Maya", "Nila", "Olga", "Putri", "Qori", "Rina", "Sari", "Tania",
        "Ulfa", "Vera", "Wati", "Xena", "Yuli",
    ]
    nama_belakang = [
        "Pratama", "Wijaya", "Santoso", "Susanto", "Hartono", "Tanjung", "Wibowo", "Setiawan",
        "Wiratama", "Kurniawan", "Sudarma", "Halim", "Halim", "Lim", "Tjokrodirdjo",
    ]
    seeds = []
    rm_counter = 1001
    import random
    random.seed(42)  # reproducible
    today = date.today()
    for i in range(50):
        nama_depan = random.choice(nama_pria)
        nama = f"{nama_depan} {random.choice(nama_belakang)}"
        seeds.append((
            f"RM-{rm_counter:05d}",
            nama,
            GenderEnum.LAKI_LAKI if hasattr(GenderEnum, 'LAKI_LAKI') else GenderEnum("L"),
            today - timedelta(days=random.randint(7300, 25550)),  # 20-70 tahun
            f"08{random.randint(1000000000, 9999999999)}",
        ))
        rm_counter += 1
    for i in range(50):
        nama_depan = random.choice(nama_wanita)
        nama = f"{nama_depan} {random.choice(nama_belakang)}"
        seeds.append((
            f"RM-{rm_counter:05d}",
            nama,
            GenderEnum.PEREMPUAN if hasattr(GenderEnum, 'PEREMPUAN') else GenderEnum("P"),
            today - timedelta(days=random.randint(7300, 25550)),
            f"08{random.randint(1000000000, 9999999999)}",
        ))
        rm_counter += 1
    return seeds


# =============================================================================
# Seed runners
# =============================================================================
def safety_check():
    """Ensure we're connected to test DB, not production."""
    if "test" not in settings.db_name.lower():
        raise RuntimeError(
            f"SAFETY ABORT — db_name='{settings.db_name}' bukan test DB. "
            f"Script ini HANYA boleh dijalankan untuk db_sehati_test. "
            f"Cek env var DB_NAME."
        )
    print(f"[seed] Target DB: {settings.db_name} ✓")


def reset_data(db: Session):
    """Truncate semua data (untuk --reset)."""
    print("[reset] Truncating semua tabel data...")
    db.execute(text("SET FOREIGN_KEY_CHECKS=0"))
    # Order matters: child tables first
    tables_in_order = [
        "audit_log",
        "transaksi_kasir_detail",
        "transaksi_kasir",
        "kunjungan_resep",
        "kunjungan_tindakan",
        "kunjungan_antropometri",
        "kunjungan_foto",
        "pemeriksaan_klinis",
        "pasien_rencana_treatment",
        "pasien_membership_kuota",
        "pasien_membership_history",
        "pasien_alergi",
        "pasien_penyakit_kronis",
        "kunjungan",
        "inventory_history",
        "treatment_komponen",
        "master_produk",
        "master_treatment",
        "inventory_stok",
        "master_membership_benefit_treatment",
        "master_membership",
        "pasien",
        "master_staf",
        "master_klinik_config",
    ]
    for t in tables_in_order:
        try:
            db.execute(text(f"TRUNCATE TABLE {t}"))
        except Exception as e:
            print(f"  [warn] {t}: {e}")
    db.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    db.commit()
    print("[reset] Done.")


def seed_klinik_config(db: Session):
    existing = db.query(MasterKlinikConfig).filter_by(id_config=1).first()
    if existing:
        print("[seed] master_klinik_config: already exists, skip")
        return
    cfg = MasterKlinikConfig(
        id_config=1,
        nama_klinik="Sehati Clinic Test",
        alamat_baris1="Jl. Test Stress No. 1",
        alamat_baris2="Jakarta Selatan",
        no_telepon="021-12345678",
        email="test@sehati.clinic",
        default_paper_nota="a5",
        default_paper_soap="a5",
    )
    db.add(cfg)
    db.commit()
    print("[seed] master_klinik_config: 1 row ✓")


def seed_staf(db: Session):
    existing_count = db.query(MasterStaf).count()
    if existing_count >= len(STAF_SEEDS):
        print(f"[seed] master_staf: {existing_count} exist, skip")
        return
    for username, password, nama, role in STAF_SEEDS:
        if db.query(MasterStaf).filter_by(username=username).first():
            continue
        staf = MasterStaf(
            username=username,
            password_hash=hash_password(password),
            nama_staf=nama,
            role=role,
            is_active=True,
            is_logged_in=False,
        )
        db.add(staf)
    db.commit()
    print(f"[seed] master_staf: {len(STAF_SEEDS)} rows ✓")


def seed_membership(db: Session):
    existing_count = db.query(MasterMembership).count()
    if existing_count >= len(MEMBERSHIP_SEEDS):
        print(f"[seed] master_membership: {existing_count} exist, skip")
        return
    for i, (nama, harga, durasi, free_konsul, dt, dp) in enumerate(MEMBERSHIP_SEEDS):
        if db.query(MasterMembership).filter_by(nama_tier=nama).first():
            continue
        m = MasterMembership(
            nama_tier=nama,
            harga_aktivasi=harga,
            durasi_bulan=durasi,
            free_konsultasi_dokter=free_konsul,
            diskon_treatment_persen=dt,
            diskon_produk_persen=dp,
            is_active=True,
            urutan_tampilan=i,
        )
        db.add(m)
    db.commit()
    print(f"[seed] master_membership: {len(MEMBERSHIP_SEEDS)} rows ✓")


def seed_treatment(db: Session):
    existing_count = db.query(MasterTreatment).count()
    if existing_count >= len(TREATMENT_SEEDS):
        print(f"[seed] master_treatment: {existing_count} exist, skip")
        return
    for nama, role_pel, durasi, harga, harga_paket in TREATMENT_SEEDS:
        if db.query(MasterTreatment).filter_by(nama_treatment=nama).first():
            continue
        t = MasterTreatment(
            nama_treatment=nama,
            role_pelaksana=role_pel,
            durasi_menit=durasi,
            harga=harga,
            harga_paket=harga_paket,
            is_active=True,
        )
        db.add(t)
    db.commit()
    print(f"[seed] master_treatment: {len(TREATMENT_SEEDS)} rows ✓")


def seed_produk(db: Session):
    seeds = _make_produk_seeds()
    existing_count = db.query(MasterProduk).count()
    if existing_count >= len(seeds):
        print(f"[seed] master_produk: {existing_count} exist, skip")
        return
    for kode, nama, tipe, satuan, harga, stok in seeds:
        if db.query(MasterProduk).filter_by(kode_produk=kode).first():
            continue
        p = MasterProduk(
            kode_produk=kode,
            nama_produk=nama,
            tipe_produk=tipe,
            satuan=satuan,
            harga_jual=harga,
            stok_terkini=stok,
            stok_minimal=10,
            eligible_member_discount=True,
        )
        db.add(p)
    db.commit()
    print(f"[seed] master_produk: {len(seeds)} rows ✓")


def seed_pasien(db: Session):
    seeds = _make_pasien_seeds()
    existing_count = db.query(Pasien).count()
    if existing_count >= len(seeds):
        print(f"[seed] pasien: {existing_count} exist, skip")
        return
    # Get owner staf as creator
    owner = db.query(MasterStaf).filter_by(role=StafRoleEnum.OWNER).first()
    owner_id = owner.id_staf if owner else None
    for no_rm, nama, gender, tgl_lahir, telp in seeds:
        if db.query(Pasien).filter_by(no_rm=no_rm).first():
            continue
        p = Pasien(
            no_rm=no_rm,
            nama=nama,
            jenis_kelamin=gender,
            tgl_lahir=tgl_lahir,
            nomor_telepon=telp,
            tipe_membership=MembershipTierEnum.REGULAR,
            status_verifikasi=VerifikasiEnum.VERIFIED,
            id_staf=owner_id,
        )
        db.add(p)
    db.commit()
    print(f"[seed] pasien: {len(seeds)} rows ✓")


def main():
    import time
    t0 = time.time()
    print(f"[seed] Connecting to {settings.database_url.split('@')[-1]}...")
    safety_check()

    db = SessionLocal()
    try:
        if "--reset" in sys.argv:
            reset_data(db)

        seed_klinik_config(db)
        seed_staf(db)
        seed_membership(db)
        seed_treatment(db)
        seed_produk(db)
        seed_pasien(db)
    finally:
        db.close()

    elapsed = time.time() - t0
    print(f"\n[seed] DONE in {elapsed:.1f}s")
    print(f"[seed] Login test: superadmin / admin123")


if __name__ == "__main__":
    main()
