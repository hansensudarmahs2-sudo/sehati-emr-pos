"""
K-L3 — test KomisiReportService (agregasi + rincian). Non-destruktif (rollback).
Pakai tanggal terisolasi (2099-01-15) supaya tidak tercampur data riil.
Run: .venv/bin/pytest tests/integration/test_komisi_report.py -v
"""
import random
import time as _t
from datetime import date

import pytest

from app.db.session import SessionLocal
from app.db.models import KomisiLedger, MasterStaf, Pasien
from app.services.komisi_report_service import KomisiReportService

TGL = date(2099, 1, 15)  # terisolasi


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _row(db, id_staf, sumber, role, nominal, tanggal=TGL, status="AKTIF", id_pasien=None, nama="Facial"):
    db.add(KomisiLedger(
        tanggal=tanggal, id_staf=id_staf, role_snapshot=role, sumber=sumber,
        nama_item=nama, harga_jual=500000, komisi_tipe="NOMINAL", komisi_value=nominal,
        komisi_nominal=nominal, status=status, id_pasien=id_pasien,
    ))


def test_ringkasan_dan_rincian(db):
    staf = db.query(MasterStaf).limit(2).all()
    dr = staf[0].id_staf
    per = staf[1].id_staf if len(staf) > 1 else staf[0].id_staf
    p = Pasien(no_rm=f"KOMR-{int(_t.time())}-{random.randint(100,999)}", nama="Pasien Komisi")
    db.add(p)
    db.flush()

    _row(db, dr, "TINDAKAN", "DOKTER", 75000, id_pasien=p.id_pasien)
    _row(db, per, "TINDAKAN", "PERAWAT", 25000, id_pasien=p.id_pasien)
    _row(db, dr, "PRODUK", "DOKTER", 20000, id_pasien=p.id_pasien, nama="Serum")
    _row(db, dr, "TINDAKAN", "DOKTER", 999999, status="VOID")          # VOID → dikecualikan
    _row(db, dr, "TINDAKAN", "DOKTER", 888888, tanggal=date(2099, 2, 1))  # di luar rentang
    db.flush()

    rep = KomisiReportService(db).laporan(TGL, TGL)
    assert rep["ringkasan"]["total_tindakan"] == 100000
    assert rep["ringkasan"]["total_produk"] == 20000
    assert rep["ringkasan"]["total_semua"] == 120000
    assert rep["ringkasan"]["jumlah_baris"] == 3
    # rincian punya kolom yang diminta
    r0 = rep["rincian"][0]
    for key in ("tanggal", "no_rm", "nama_pasien", "nama_item", "harga_jual", "komisi", "role"):
        assert key in r0


def test_filter_per_staf(db):
    staf = db.query(MasterStaf).limit(2).all()
    if len(staf) < 2:
        pytest.skip("butuh >=2 staf untuk tes filter")
    dr, per = staf[0].id_staf, staf[1].id_staf
    _row(db, dr, "TINDAKAN", "DOKTER", 50000)
    _row(db, per, "TINDAKAN", "PERAWAT", 30000)
    db.flush()

    rep_dr = KomisiReportService(db).laporan(TGL, TGL, id_staf=dr)
    assert rep_dr["ringkasan"]["total_semua"] == 50000
    assert all(r["role"] == "DOKTER" for r in rep_dr["rincian"])
