"""
P-L5 — test InventoryLotService.consume_fefo (urutan ED, null-ED terakhir, shortfall). Non-destruktif.
Run: .venv/bin/pytest tests/integration/test_fefo.py -v
"""
import random
from datetime import date

import pytest

from app.db.session import SessionLocal
from app.db.models import StokLot, MasterProduk
from app.db.models._enums import TipeProdukEnum
from app.services.inventory_lot_service import InventoryLotService


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _produk(db):
    p = MasterProduk(
        kode_produk=f"FEFO{random.randint(10000,99999)}", nama_produk="FEFO Test",
        tipe_produk=TipeProdukEnum.RETAIL, satuan="pcs", default_iterasi=1,
        eligible_member_discount=False, stok_terkini=0,
    )
    db.add(p)
    db.flush()
    return p


def _lot(db, p, batch, ed, qty, masuk):
    lot = StokLot(tipe_item="PRODUK", id_produk=p.id_produk, lokasi="RETAIL",
                  batch_no=batch, tgl_ed=ed, qty_masuk=qty, qty_sisa=qty,
                  status="AKTIF", tgl_masuk=masuk)
    db.add(lot)
    db.flush()
    return lot


def test_fefo_order_dan_null_terakhir(db):
    p = _produk(db)
    l_null = _lot(db, p, "NULL-ED", None, 5, date(2026, 1, 1))
    l_late = _lot(db, p, "LATE", date(2027, 12, 1), 5, date(2026, 2, 1))
    l_early = _lot(db, p, "EARLY", date(2027, 1, 1), 5, date(2026, 3, 1))

    svc = InventoryLotService(db)
    res = svc.consume_fefo(tipe_item="PRODUK", lokasi="RETAIL", qty=7, id_produk=p.id_produk)
    assert res["shortfall"] == 0
    batches = [c["batch_no"] for c in res["consumed"]]
    assert batches[0] == "EARLY"   # ED terdekat duluan
    assert batches[1] == "LATE"
    db.refresh(l_early); db.refresh(l_late); db.refresh(l_null)
    assert l_early.qty_sisa == 0 and l_early.status == "HABIS"
    assert l_late.qty_sisa == 3
    assert l_null.qty_sisa == 5    # lot ED-NULL belum tersentuh (paling akhir)


def test_shortfall_kalau_lot_kurang(db):
    p = _produk(db)
    _lot(db, p, "A", date(2027, 1, 1), 3, date(2026, 1, 1))
    svc = InventoryLotService(db)
    res = svc.consume_fefo(tipe_item="PRODUK", lokasi="RETAIL", qty=10, id_produk=p.id_produk)
    assert sum(c["qty"] for c in res["consumed"]) == 3
    assert res["shortfall"] == 7


def test_peek_tidak_mengubah(db):
    p = _produk(db)
    lot = _lot(db, p, "A", date(2027, 1, 1), 5, date(2026, 1, 1))
    svc = InventoryLotService(db)
    peek = svc.peek_fefo(tipe_item="PRODUK", lokasi="RETAIL", qty=3, id_produk=p.id_produk)
    assert peek[0]["batch_no"] == "A" and peek[0]["qty"] == 3
    db.refresh(lot)
    assert lot.qty_sisa == 5  # peek tidak memotong
