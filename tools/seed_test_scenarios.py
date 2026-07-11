"""
seed_test_scenarios.py — dummy data untuk smoke testing & integration tests.

USAGE:
    cd sehati_clinic && source .venv/bin/activate
    python ../tools/seed_test_scenarios.py

CLEANUP (kalau perlu hapus semua data SEED-*):
    python ../tools/seed_test_scenarios.py --cleanup

NOTES:
    - Idempotent: cek `no_rm` dengan prefix 'SEED-' dulu, skip kalau sudah ada
    - Pakai prefix 'SEED-' di no_rm + nama supaya mudah identifikasi & cleanup
    - Master treatment & produk yang dipakai: dipilih dari yang sudah ada di DB
      (ambil yang pertama is_active=1). Kalau master kosong, script complain.

SKENARIO:
    SEED-001 (Andi Pratama)   : Single treatment, kunjungan kemarin COMPLETED + bayar
    SEED-002 (Sari Dewi)      : Series 6 sesi, 3 sudah eksekusi, 3 pending
    SEED-003 (Budi Santoso)   : VVIP, kunjungan hari ini ANTRI_BAYAR (ready test kasir)
"""

import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

try:
    from sqlalchemy import select, text
    from app.db.session import SessionLocal
    from app.db.models import (
        Kunjungan, KunjunganAntropometri, KunjunganResep, KunjunganTindakan,
        MasterProduk, MasterStaf, MasterTreatment, Pasien, PasienAlergi,
        PasienPenyakitKronis, PasienRencanaTreatment, PemeriksaanKlinis,
        TransaksiDetailProduk, TransaksiKasir, TransaksiPembayaran,
        GenderEnum, MembershipTierEnum, StatusItemResepEnum,
        StatusRencanaTreatmentEnum, StatusTindakanEnum,
        TingkatKeparahanAlergiEnum,
    )
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Pastikan venv aktif & dependencies ter-install.")
    sys.exit(1)


SEED_PREFIX = "SEED-"


# ============================================================================
# HELPERS — pick master records yang aktif
# ============================================================================
def pick_treatment(db, prefer_butuh_otorisasi: bool = False) -> MasterTreatment | None:
    """Ambil 1 master_treatment aktif. Optionally prefer butuh_otorisasi."""
    stmt = select(MasterTreatment).where(MasterTreatment.is_active.is_(True))
    if prefer_butuh_otorisasi:
        stmt = stmt.where(MasterTreatment.butuh_otorisasi.is_(True))
    stmt = stmt.limit(1)
    return db.execute(stmt).scalar_one_or_none()


def pick_produk(db) -> MasterProduk | None:
    stmt = select(MasterProduk).limit(1)
    return db.execute(stmt).scalar_one_or_none()


def pick_staf(db, role: str) -> MasterStaf | None:
    stmt = select(MasterStaf).where(MasterStaf.role == role).where(MasterStaf.is_active.is_(True)).limit(1)
    return db.execute(stmt).scalar_one_or_none()


# ============================================================================
# CLEANUP
# ============================================================================
def cleanup_seed_data(db):
    """Hapus semua data dengan no_rm LIKE 'SEED-%'. Cascade via FK + manual."""
    print("🧹 Cleanup seed data...")
    pasien_ids = [
        row[0] for row in db.execute(
            text("SELECT id_pasien FROM pasien WHERE no_rm LIKE 'SEED-%'")
        ).all()
    ]
    if not pasien_ids:
        print("   Tidak ada data SEED untuk dihapus.")
        return

    placeholders = ",".join([f":id{i}" for i in range(len(pasien_ids))])
    params = {f"id{i}": v for i, v in enumerate(pasien_ids)}

    # Order penting: child first
    queries = [
        f"DELETE FROM kunjungan_antropometri WHERE id_kunjungan IN (SELECT id_kunjungan FROM kunjungan WHERE id_pasien IN ({placeholders}))",
        f"DELETE FROM kunjungan_tindakan WHERE id_kunjungan IN (SELECT id_kunjungan FROM kunjungan WHERE id_pasien IN ({placeholders}))",
        f"DELETE FROM kunjungan_resep WHERE id_kunjungan IN (SELECT id_kunjungan FROM kunjungan WHERE id_pasien IN ({placeholders}))",
        f"DELETE FROM pemeriksaan_klinis WHERE id_pasien IN ({placeholders})",
        f"DELETE FROM transaksi_detail_produk WHERE id_transaksi IN (SELECT id_transaksi FROM transaksi_kasir WHERE id_kunjungan IN (SELECT id_kunjungan FROM kunjungan WHERE id_pasien IN ({placeholders})))",
        f"DELETE FROM transaksi_pembayaran WHERE id_transaksi IN (SELECT id_transaksi FROM transaksi_kasir WHERE id_kunjungan IN (SELECT id_kunjungan FROM kunjungan WHERE id_pasien IN ({placeholders})))",
        f"DELETE FROM transaksi_kasir WHERE id_kunjungan IN (SELECT id_kunjungan FROM kunjungan WHERE id_pasien IN ({placeholders}))",
        f"DELETE FROM kunjungan WHERE id_pasien IN ({placeholders})",
        f"DELETE FROM pasien_alergi WHERE id_pasien IN ({placeholders})",
        f"DELETE FROM pasien_penyakit_kronis WHERE id_pasien IN ({placeholders})",
        f"DELETE FROM pasien_rencana_treatment WHERE id_pasien IN ({placeholders})",
        f"DELETE FROM pasien WHERE id_pasien IN ({placeholders})",
    ]
    for q in queries:
        db.execute(text(q), params)
    db.commit()
    print(f"   ✅ Deleted {len(pasien_ids)} pasien + related data.")


# ============================================================================
# SCENARIO 1 — SEED-001 Andi Pratama: single treatment COMPLETED kemarin
# ============================================================================
def seed_andi(db, treatment: MasterTreatment, dokter: MasterStaf, fo: MasterStaf):
    no_rm = "SEED-001"
    existing = db.execute(select(Pasien).where(Pasien.no_rm == no_rm)).scalar_one_or_none()
    if existing:
        print(f"   ↪ {no_rm} (Andi) sudah ada — id_pasien={existing.id_pasien}, skip")
        return existing

    # 1. Pasien
    pasien = Pasien(
        no_rm=no_rm,
        nama="SEED Andi Pratama",
        jenis_kelamin=GenderEnum.LAKI_LAKI,
        tgl_lahir=date(1990, 5, 15),
        nomor_telepon="081299900001",
        alamat="Jl. Test SEED-001 No. 1",
        tipe_membership=MembershipTierEnum.REGULAR,
        id_staf=fo.id_staf,
    )
    db.add(pasien)
    db.flush()

    # 2. Alergi
    db.add(PasienAlergi(
        id_pasien=pasien.id_pasien,
        alergen="Paracetamol",
        gejala="Ruam kulit",
        tingkat_keparahan=TingkatKeparahanAlergiEnum.SEDANG,
        id_staf=fo.id_staf,
    ))

    # 3. Kunjungan kemarin
    kemarin = datetime.now() - timedelta(days=1)
    kunjungan = Kunjungan(
        id_pasien=pasien.id_pasien,
        id_staf_fo=fo.id_staf,
        tgl_kunjungan=kemarin,
        nomor_antrean=1,
        status_antrian="COMPLETED",
        sumber_pendaftaran="WALK_IN",
        keluhan_utama="Demam ringan, ingin konsultasi",
    )
    db.add(kunjungan)
    db.flush()

    # 4. Antropometri
    db.add(KunjunganAntropometri(
        id_kunjungan=kunjungan.id_kunjungan,
        id_staf=fo.id_staf,
        berat_badan=70.0,
        tinggi_badan=170.0,
        tekanan_darah="120/80",
        suhu_tubuh=37.2,
        skinfold_titik_1=12.0,
        skinfold_titik_2=15.0,
        skinfold_titik_3=18.0,
        lingkar_perut=85.0,
    ))

    # 5. SOAP
    db.add(PemeriksaanKlinis(
        id_kunjungan=kunjungan.id_kunjungan,
        id_pasien=pasien.id_pasien,
        id_staf_dokter=dokter.id_staf,
        anamnesa="Pasien datang dengan keluhan demam ringan sejak 2 hari. Tidak ada riwayat traveling.",
        pemeriksaan_fisik="Suhu 37.2°C. TTV stabil. Tenggorokan tidak ada radang.",
        diagnosa="ISPA ringan (J00)",
    ))

    # 6. Tindakan (SELESAI)
    db.add(KunjunganTindakan(
        id_kunjungan=kunjungan.id_kunjungan,
        id_treatment=treatment.id_treatment,
        id_staf_pelaksana=dokter.id_staf,
        status_tindakan=StatusTindakanEnum.SELESAI,
        waktu_mulai=kemarin + timedelta(minutes=10),
        waktu_selesai=kemarin + timedelta(minutes=30),
    ))

    # 7. Transaksi
    trx = TransaksiKasir(
        id_kunjungan=kunjungan.id_kunjungan,
        id_staf_kasir=fo.id_staf,
        rincian_tagihan=f"{treatment.nama_treatment} Rp {treatment.harga}",
        subtotal=Decimal(str(treatment.harga)),
        total_tagihan=Decimal(str(treatment.harga)),
        waktu_bayar=kemarin + timedelta(minutes=35),
    )
    db.add(trx)
    db.flush()

    db.add(TransaksiPembayaran(
        id_transaksi=trx.id_transaksi,
        metode_bayar="TUNAI",
        nominal=Decimal(str(treatment.harga)),
    ))

    db.commit()
    print(f"   ✅ {no_rm} (Andi) created — id_pasien={pasien.id_pasien}, id_kunjungan={kunjungan.id_kunjungan}")
    return pasien


# ============================================================================
# SCENARIO 2 — SEED-002 Sari Dewi: Series 6 sesi, 3 sudah eksekusi
# ============================================================================
def seed_sari(db, treatment: MasterTreatment, dokter: MasterStaf, fo: MasterStaf):
    no_rm = "SEED-002"
    existing = db.execute(select(Pasien).where(Pasien.no_rm == no_rm)).scalar_one_or_none()
    if existing:
        print(f"   ↪ {no_rm} (Sari) sudah ada — id_pasien={existing.id_pasien}, skip")
        return existing

    pasien = Pasien(
        no_rm=no_rm,
        nama="SEED Sari Dewi",
        jenis_kelamin=GenderEnum.PEREMPUAN,
        tgl_lahir=date(1996, 3, 10),
        nomor_telepon="081299900002",
        alamat="Jl. Test SEED-002 No. 2",
        tipe_membership=MembershipTierEnum.VIP,
        id_staf=fo.id_staf,
    )
    db.add(pasien)
    db.flush()

    # Series rencana — 6 sesi
    sesi_offsets = [21, 14, 7, 0, -7, -14]  # days ago (negatif = future plan)
    for i, days_ago in enumerate(sesi_offsets, start=1):
        is_executed = days_ago > 0
        rencana = PasienRencanaTreatment(
            id_pasien=pasien.id_pasien,
            id_treatment=treatment.id_treatment,
            urutan_sesi=i,
            nama_tindakan=treatment.nama_treatment,
            status=StatusRencanaTreatmentEnum.DONE if is_executed else StatusRencanaTreatmentEnum.PENDING,
            tgl_eksekusi=(datetime.now() - timedelta(days=days_ago)) if is_executed else None,
            catatan_dokter=f"Sesi ke-{i} series acne treatment",
        )
        db.add(rencana)

    # 3 kunjungan history (sesi 1-3)
    bb_track = [65.0, 64.2, 63.5]  # penurunan progressive
    for i, (days_ago, bb) in enumerate(zip([21, 14, 7], bb_track), start=1):
        tgl = datetime.now() - timedelta(days=days_ago)
        kunjungan = Kunjungan(
            id_pasien=pasien.id_pasien,
            id_staf_fo=fo.id_staf,
            tgl_kunjungan=tgl,
            nomor_antrean=10 + i,
            status_antrian="COMPLETED",
            sumber_pendaftaran="WALK_IN",
            keluhan_utama=f"Sesi ke-{i} acne treatment",
        )
        db.add(kunjungan)
        db.flush()

        db.add(KunjunganAntropometri(
            id_kunjungan=kunjungan.id_kunjungan,
            id_staf=fo.id_staf,
            berat_badan=bb,
            tinggi_badan=160.0,
            tekanan_darah="110/75",
            suhu_tubuh=36.5,
            lingkar_perut=78.0 - i * 0.5,
        ))

        db.add(PemeriksaanKlinis(
            id_kunjungan=kunjungan.id_kunjungan,
            id_pasien=pasien.id_pasien,
            id_staf_dokter=dokter.id_staf,
            anamnesa=f"Kontrol sesi {i}/6 acne treatment. Respons terapi baik.",
            diagnosa="L70.0 — Acne vulgaris",
            saran_treatment="Lanjutkan ke sesi berikut, interval 1 minggu.",
        ))

        db.add(KunjunganTindakan(
            id_kunjungan=kunjungan.id_kunjungan,
            id_treatment=treatment.id_treatment,
            id_staf_pelaksana=dokter.id_staf,
            status_tindakan=StatusTindakanEnum.SELESAI,
            waktu_mulai=tgl + timedelta(minutes=15),
            waktu_selesai=tgl + timedelta(minutes=60),
        ))

        # Transaksi
        harga = Decimal(str(treatment.harga))
        trx = TransaksiKasir(
            id_kunjungan=kunjungan.id_kunjungan,
            id_staf_kasir=fo.id_staf,
            rincian_tagihan=f"{treatment.nama_treatment} sesi {i}",
            subtotal=harga,
            total_tagihan=harga,
            waktu_bayar=tgl + timedelta(minutes=70),
        )
        db.add(trx)
        db.flush()
        db.add(TransaksiPembayaran(
            id_transaksi=trx.id_transaksi,
            metode_bayar="QRIS",
            nominal=harga,
        ))

    db.commit()
    print(f"   ✅ {no_rm} (Sari) created — id_pasien={pasien.id_pasien}, 6 sesi series, 3 executed")
    return pasien


# ============================================================================
# SCENARIO 3 — SEED-003 Budi Santoso: VVIP, hari ini ANTRI_BAYAR
# ============================================================================
def seed_budi(db, treatment: MasterTreatment, produk: MasterProduk, dokter: MasterStaf, fo: MasterStaf):
    no_rm = "SEED-003"
    existing = db.execute(select(Pasien).where(Pasien.no_rm == no_rm)).scalar_one_or_none()
    if existing:
        print(f"   ↪ {no_rm} (Budi) sudah ada — id_pasien={existing.id_pasien}, skip")
        return existing

    pasien = Pasien(
        no_rm=no_rm,
        nama="SEED Budi Santoso",
        jenis_kelamin=GenderEnum.LAKI_LAKI,
        tgl_lahir=date(1980, 12, 1),
        nomor_telepon="081299900003",
        alamat="Jl. Test SEED-003 No. 3",
        tipe_membership=MembershipTierEnum.VVIP,
        id_staf=fo.id_staf,
    )
    db.add(pasien)
    db.flush()

    db.add(PasienAlergi(
        id_pasien=pasien.id_pasien,
        alergen="Penisilin",
        gejala="Anafilaksis",
        tingkat_keparahan=TingkatKeparahanAlergiEnum.BERAT,
        id_staf=fo.id_staf,
    ))
    db.add(PasienPenyakitKronis(
        id_pasien=pasien.id_pasien,
        nama_penyakit="Hipertensi",
        catatan="Terkontrol dengan amlodipine 10mg",
    ))

    # Kunjungan hari ini, status ANTRI_BAYAR
    sekarang = datetime.now()
    kunjungan = Kunjungan(
        id_pasien=pasien.id_pasien,
        id_staf_fo=fo.id_staf,
        tgl_kunjungan=sekarang.replace(hour=9, minute=0, second=0, microsecond=0),
        nomor_antrean=1,
        status_antrian="ANTRI_BAYAR",
        sumber_pendaftaran="WALK_IN",
        keluhan_utama="Kontrol rutin + medical check-up",
    )
    db.add(kunjungan)
    db.flush()

    db.add(KunjunganAntropometri(
        id_kunjungan=kunjungan.id_kunjungan,
        id_staf=fo.id_staf,
        berat_badan=75.0,
        tinggi_badan=175.0,
        tekanan_darah="135/85",
        suhu_tubuh=36.7,
        skinfold_titik_1=18.0,
        skinfold_titik_2=22.0,
        skinfold_titik_3=24.0,
        lingkar_perut=92.0,
    ))

    db.add(PemeriksaanKlinis(
        id_kunjungan=kunjungan.id_kunjungan,
        id_pasien=pasien.id_pasien,
        id_staf_dokter=dokter.id_staf,
        anamnesa="MCU rutin. Hipertensi terkontrol. Tidak ada keluhan baru.",
        pemeriksaan_fisik="TD 135/85. BB stabil. Tidak ada lesi.",
        diagnosa="Z00.0 Medical check-up; I10 Hipertensi esensial (terkontrol)",
        saran_produk="Lanjutkan amlodipine. Tambah Krim retinoid malam hari (3 bulan).",
    ))

    db.add(KunjunganTindakan(
        id_kunjungan=kunjungan.id_kunjungan,
        id_treatment=treatment.id_treatment,
        id_staf_pelaksana=dokter.id_staf,
        status_tindakan=StatusTindakanEnum.SELESAI,
        waktu_mulai=sekarang.replace(hour=9, minute=15),
        waktu_selesai=sekarang.replace(hour=9, minute=45),
    ))

    if produk:
        db.add(KunjunganResep(
            id_kunjungan=kunjungan.id_kunjungan,
            id_produk=produk.id_produk,
            qty=1,
            aturan_pakai="Oleskan tipis pada wajah malam hari",
            id_staf_input=dokter.id_staf,
            status_item=StatusItemResepEnum.PENDING,
        ))

    db.commit()
    print(f"   ✅ {no_rm} (Budi) created — id_pasien={pasien.id_pasien}, kunjungan ANTRI_BAYAR untuk test kasir")
    return pasien


# ============================================================================
# MAIN
# ============================================================================
def main():
    cleanup_mode = "--cleanup" in sys.argv

    print("🌱 Sehati Clinic — Seed Test Scenarios")
    print("=" * 60)

    with SessionLocal() as db:
        if cleanup_mode:
            cleanup_seed_data(db)
            return

        # Pick master records
        treatment = pick_treatment(db)
        if treatment is None:
            print("❌ Tidak ada master_treatment aktif di DB. Seed master dulu.")
            sys.exit(1)
        produk = pick_produk(db)
        dokter = pick_staf(db, "Dokter")
        fo = pick_staf(db, "FO") or pick_staf(db, "Admin") or pick_staf(db, "Owner")
        if not dokter:
            print("❌ Tidak ada staf dengan role Dokter aktif.")
            sys.exit(1)
        if not fo:
            print("❌ Tidak ada staf FO/Admin/Owner aktif.")
            sys.exit(1)

        print(f"📋 Master treatment: '{treatment.nama_treatment}' (id={treatment.id_treatment}, harga={treatment.harga})")
        produk_label = f"'{produk.nama_produk}'" if produk else "(none — skip resep)"
        print(f"📋 Master produk:    {produk_label}")
        print(f"👤 Dokter (test):    {dokter.username} (id={dokter.id_staf})")
        print(f"👤 FO/Admin (test):  {fo.username} (id={fo.id_staf})")
        print("=" * 60)

        seed_andi(db, treatment, dokter, fo)
        seed_sari(db, treatment, dokter, fo)
        seed_budi(db, treatment, produk, dokter, fo)

        print("=" * 60)
        print("✅ Seed selesai.")
        print()
        print("Untuk test di Swagger UI, cari pasien dengan keyword 'SEED'.")
        print("Untuk cleanup: python ../tools/seed_test_scenarios.py --cleanup")


if __name__ == "__main__":
    main()
