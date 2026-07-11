"""
P-L3 — sanity test StokLot (buat lot produk + verifikasi field). Non-destruktif (rollback).
Run: .venv/bin/pytest tests/integration/test_stok_lot.py -v
"""
import random
import time as _t
from datetime import date

import pytest

from app.db.session import SessionLocal
from app.db.models import StokLot, MasterProduk


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def test_buat_lot_produk(db):
    p = db.query(MasterProduk).first()
    assert p is not None, "butuh minimal 1 produk seed"
    lot = StokLot(
        tipe_item="PRODUK", id_produk=p.id_produk, lokasi="RETAIL",
        batch_no=f"BATCH-{random.randint(1000,9999)}", tgl_ed=date(2027, 1, 1),
        qty_masuk=10, qty_sisa=10, harga_terima=25000, status="AKTIF",
    )
    db.add(lot)
    db.flush()
    got = db.get(StokLot, lot.id_lot)
    assert got.qty_sisa == 10
    assert got.tipe_item == "PRODUK"
    assert got.lokasi == "RETAIL"
    assert got.status == "AKTIF"


def test_lot_batch_ed_boleh_null(db):
    """Batch pembuka / kasus khusus: batch_no & tgl_ed NULL didukung."""
    p = db.query(MasterProduk).first()
    lot = StokLot(
        tipe_item="PRODUK", id_produk=p.id_produk, lokasi="RETAIL",
        batch_no=None, tgl_ed=None, qty_masuk=5, qty_sisa=5, status="AKTIF",
    )
    db.add(lot)
    db.flush()
    got = db.get(StokLot, lot.id_lot)
    assert got.batch_no is None and got.tgl_ed is None and got.qty_sisa == 5
