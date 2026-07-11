"""
K-L2 — test KomisiService: tulis komisi saat bayar + void. Non-destruktif (rollback teardown).
Run: .venv/bin/pytest tests/integration/test_komisi_ledger.py -v
"""
import random
import time as _t
from types import SimpleNamespace

import pytest

from app.db.session import SessionLocal
from app.db.models import (
    Pasien, Kunjungan, KunjunganTindakan, MasterTreatment, MasterStaf,
    KomisiLedger, TransaksiKasir,
)
from app.db.models._enums import StatusTindakanEnum
from app.services.komisi_service import KomisiService


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _staf(db):
    return db.query(MasterStaf).limit(2).all()


def _mk_treatment(db, kd, kp):
    t = MasterTreatment(
        nama_treatment=f"Facial Test {random.randint(1000, 9999)}",
        role_pelaksana="PERAWAT", durasi_menit=30, harga=500000,
        komisi_dokter_tipe=("NOMINAL" if kd else None), komisi_dokter_value=kd,
        komisi_perawat_tipe=("NOMINAL" if kp else None), komisi_perawat_value=kp,
    )
    db.add(t)
    db.flush()
    return t


def _mk_tindakan(db, dr, per, kd, kp):
    p = Pasien(no_rm=f"KOM-{int(_t.time())}-{random.randint(100,999)}", nama="Komisi Test")
    db.add(p)
    db.flush()
    t = _mk_treatment(db, kd, kp)
    kj = Kunjungan(id_pasien=p.id_pasien, id_staf_dokter_assigned=dr)
    db.add(kj)
    db.flush()
    kt = KunjunganTindakan(
        id_kunjungan=kj.id_kunjungan, id_treatment=t.id_treatment,
        status_tindakan=StatusTindakanEnum.SELESAI,
        id_dokter_pelaksana=dr, id_perawat_pelaksana=per,
    )
    db.add(kt)
    db.flush()
    return p, kj, kt


def test_komisi_tindakan_dokter_dan_perawat(db):
    staf = _staf(db)
    assert staf, "butuh minimal 1 staf seed"
    dr = staf[0].id_staf
    per = staf[1].id_staf if len(staf) > 1 else staf[0].id_staf
    p, kj, kt = _mk_tindakan(db, dr, per, 75000, 25000)
    n = KomisiService(db).catat_komisi_transaksi(
        id_transaksi=None, id_kunjungan=kj.id_kunjungan, id_pasien=p.id_pasien,
        id_dokter_assigned=dr, rincian_produk=[],
    )
    assert n == 2
    rows = db.query(KomisiLedger).filter(KomisiLedger.id_kunjungan == kj.id_kunjungan).all()
    by_role = {r.role_snapshot: r for r in rows}
    assert float(by_role["DOKTER"].komisi_nominal) == 75000
    assert float(by_role["PERAWAT"].komisi_nominal) == 25000
    assert by_role["DOKTER"].id_staf == dr
    assert by_role["PERAWAT"].id_staf == per
    assert by_role["DOKTER"].sumber == "TINDAKAN"


def test_komisi_hanya_dokter_kalau_perawat_nol(db):
    staf = _staf(db)
    dr = staf[0].id_staf
    p, kj, kt = _mk_tindakan(db, dr, dr, 50000, 0)  # pico: perawat 0
    n = KomisiService(db).catat_komisi_transaksi(
        id_transaksi=None, id_kunjungan=kj.id_kunjungan, id_pasien=p.id_pasien,
        id_dokter_assigned=dr, rincian_produk=[],
    )
    assert n == 1
    rows = db.query(KomisiLedger).filter(KomisiLedger.id_kunjungan == kj.id_kunjungan).all()
    assert len(rows) == 1 and rows[0].role_snapshot == "DOKTER"


def test_void_komisi(db):
    staf = _staf(db)
    dr = staf[0].id_staf
    trx = TransaksiKasir(id_staf_kasir=dr, rincian_tagihan="test", total_tagihan=500000, status_transaksi="BAYAR")
    db.add(trx)
    db.flush()
    p, kj, kt = _mk_tindakan(db, dr, dr, 75000, 25000)
    KomisiService(db).catat_komisi_transaksi(
        id_transaksi=trx.id_transaksi, id_kunjungan=kj.id_kunjungan, id_pasien=p.id_pasien,
        id_dokter_assigned=dr, rincian_produk=[],
    )
    voided = KomisiService(db).void_komisi_transaksi(id_transaksi=trx.id_transaksi)
    assert voided == 2
    rows = db.query(KomisiLedger).filter(KomisiLedger.id_transaksi == trx.id_transaksi).all()
    assert rows and all(r.status == "VOID" for r in rows)


def test_produk_beli_tanpa_konsul_tanpa_komisi(db):
    # id_dokter_assigned None (beli tanpa konsul) → blok produk dilewati → 0 baris
    n = KomisiService(db).catat_komisi_transaksi(
        id_transaksi=None, id_kunjungan=None, id_pasien=None, id_dokter_assigned=None,
        rincian_produk=[SimpleNamespace(id_produk=999999, id_resep=1, qty=2, harga_satuan=100000, nama_produk="x")],
    )
    assert n == 0


def test_anti_dobel_komisi(db):
    """Opsi A: panggil catat 2× (mis. split/reopen) → tindakan tidak dobel komisi."""
    staf = _staf(db)
    dr = staf[0].id_staf
    p, kj, kt = _mk_tindakan(db, dr, dr, 75000, 25000)
    svc = KomisiService(db)
    n1 = svc.catat_komisi_transaksi(id_transaksi=None, id_kunjungan=kj.id_kunjungan,
                                    id_pasien=p.id_pasien, id_dokter_assigned=dr, rincian_produk=[])
    n2 = svc.catat_komisi_transaksi(id_transaksi=None, id_kunjungan=kj.id_kunjungan,
                                    id_pasien=p.id_pasien, id_dokter_assigned=dr, rincian_produk=[])
    assert n1 == 2 and n2 == 0
    rows = db.query(KomisiLedger).filter(KomisiLedger.id_kunjungan == kj.id_kunjungan).all()
    assert len(rows) == 2
