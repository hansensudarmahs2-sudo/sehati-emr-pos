"""
RT-L4 — test retur: approve potong lot + nota tukar (lot pengganti) + refund (tutup).
create_retur/approve/input_nota commit internal → persist (jalankan di DB dev).
Run: .venv/bin/pytest tests/integration/test_retur.py -v
"""
import random
from datetime import date

import pytest
from decimal import Decimal

from app.db.session import SessionLocal
from app.db.models import StokLot, MasterProduk, MasterStaf, ReturProduk
from app.db.models._enums import TipeProdukEnum
from app.services.retur_service import ReturService


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _mk(db, stok):
    p = MasterProduk(
        kode_produk=f"RTR{random.randint(10000,99999)}", nama_produk="Retur Test",
        tipe_produk=TipeProdukEnum.RETAIL, satuan="pcs", default_iterasi=1,
        eligible_member_discount=False, stok_terkini=stok,
    )
    db.add(p); db.flush()
    lot = StokLot(tipe_item="PRODUK", id_produk=p.id_produk, lokasi="RETAIL",
                  batch_no="RT1", tgl_ed=date(2026, 3, 1), qty_masuk=stok, qty_sisa=stok,
                  status="AKTIF", tgl_masuk=date(2026, 1, 1))
    db.add(lot); db.commit()
    return p, lot


def test_approve_potong_lot_lalu_tukar(db):
    staf = db.query(MasterStaf).first()
    p, lot = _mk(db, 10)
    svc = ReturService(db)
    r = svc.create_retur(None, "mendekati ED", [{"id_lot": lot.id_lot, "qty": 3}], staf)
    svc.approve_retur(r.id_retur, staf)
    db.refresh(lot); db.refresh(p)
    assert lot.qty_sisa == 7
    assert float(p.stok_terkini) == 7

    svc.input_nota_tukar(r.id_retur, "NOTA-T", date.today(),
                         [{"id_produk": p.id_produk, "batch": "FRESH", "ed": date(2028, 1, 1),
                           "qty": 3, "harga": Decimal("10000")}], staf)
    db.refresh(p)
    new_lot = (db.query(StokLot)
               .filter(StokLot.id_produk == p.id_produk, StokLot.batch_no == "FRESH").first())
    assert new_lot is not None and new_lot.qty_sisa == 3
    assert float(p.stok_terkini) == 10  # 7 + 3 pengganti
    r2 = db.get(ReturProduk, r.id_retur)
    assert r2.status == "SELESAI" and r2.jenis_penyelesaian == "TUKAR_BARANG"


def test_approve_lalu_refund(db):
    staf = db.query(MasterStaf).first()
    p, lot = _mk(db, 8)
    svc = ReturService(db)
    r = svc.create_retur(None, "ED", [{"id_lot": lot.id_lot, "qty": 5}], staf)
    svc.approve_retur(r.id_retur, staf)
    db.refresh(lot); db.refresh(p)
    assert lot.qty_sisa == 3 and float(p.stok_terkini) == 3

    svc.input_nota_refund(r.id_retur, "NOTA-R", date.today(), Decimal("250000"), "refund penuh", staf)
    db.refresh(p)
    assert float(p.stok_terkini) == 3  # refund tak ubah stok
    r2 = db.get(ReturProduk, r.id_retur)
    assert r2.status == "SELESAI" and r2.jenis_penyelesaian == "REFUND"
    assert r2.total_nilai == Decimal("250000.00")
