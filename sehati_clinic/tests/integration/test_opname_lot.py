"""
P-L9 — test opname per-batch (PRODUK/RETAIL): selisih diterapkan ke LOT spesifik,
cache stok_terkini = Σ qty_sisa lot AKTIF, dan "batch baru ditemukan" membuat lot baru.
CATATAN: create_opname & approve commit internal → data persist (jalankan di DB dev).
Run: .venv/bin/pytest tests/integration/test_opname_lot.py -v
"""
import random
from datetime import date

import pytest

from app.db.session import SessionLocal
from app.db.models import StokLot, MasterProduk, MasterStaf, LokasiOpnameEnum
from app.db.models._enums import TipeProdukEnum
from app.schemas.pengadaan import StockOpnameCreateRequest, StockOpnameItemInput
from app.services.opname_service import OpnameService


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _mk_produk(db, stok):
    p = MasterProduk(
        kode_produk=f"OPN{random.randint(10000,99999)}", nama_produk="Opname Lot Test",
        tipe_produk=TipeProdukEnum.RETAIL, satuan="pcs", default_iterasi=1,
        eligible_member_discount=False, stok_terkini=stok,
    )
    db.add(p)
    db.flush()
    return p


def test_opname_selisih_ke_lot_spesifik(db):
    staf = db.query(MasterStaf).first()
    assert staf is not None
    p = _mk_produk(db, 10)
    lot_a = StokLot(tipe_item="PRODUK", id_produk=p.id_produk, lokasi="RETAIL",
                    batch_no="A", tgl_ed=date(2027, 1, 1), qty_masuk=4, qty_sisa=4,
                    status="AKTIF", tgl_masuk=date(2026, 1, 1))
    lot_b = StokLot(tipe_item="PRODUK", id_produk=p.id_produk, lokasi="RETAIL",
                    batch_no="B", tgl_ed=date(2028, 1, 1), qty_masuk=6, qty_sisa=6,
                    status="AKTIF", tgl_masuk=date(2026, 1, 1))
    db.add_all([lot_a, lot_b])
    db.commit()

    # Opname: lot A fisik 3 (selisih -1), lot B fisik 6 (match)
    payload = StockOpnameCreateRequest(
        lokasi=LokasiOpnameEnum.RETAIL, catatan="test lot",
        items=[
            StockOpnameItemInput(tipe_item="PRODUK", id_produk=p.id_produk,
                                 id_lot=lot_a.id_lot, qty_fisik=3),
            StockOpnameItemInput(tipe_item="PRODUK", id_produk=p.id_produk,
                                 id_lot=lot_b.id_lot, qty_fisik=6),
        ],
    )
    opname = OpnameService(db).create_opname(payload=payload, actor=staf)
    OpnameService(db).approve(opname.id_opname, actor=staf)

    db.refresh(lot_a); db.refresh(lot_b); db.refresh(p)
    assert lot_a.qty_sisa == 3          # selisih -1 ke lot A saja
    assert lot_b.qty_sisa == 6          # lot B tak berubah
    assert float(p.stok_terkini) == 9   # cache = Σ qty_sisa (3+6)


def test_opname_batch_baru_buat_lot(db):
    staf = db.query(MasterStaf).first()
    p = _mk_produk(db, 5)
    lot_a = StokLot(tipe_item="PRODUK", id_produk=p.id_produk, lokasi="RETAIL",
                    batch_no="A", tgl_ed=date(2027, 6, 1), qty_masuk=5, qty_sisa=5,
                    status="AKTIF", tgl_masuk=date(2026, 1, 1))
    db.add(lot_a)
    db.commit()

    # Batch baru ditemukan: fisik 8, ED 2029
    payload = StockOpnameCreateRequest(
        lokasi=LokasiOpnameEnum.RETAIL, catatan="batch baru",
        items=[
            StockOpnameItemInput(tipe_item="PRODUK", id_produk=p.id_produk,
                                 id_lot=None, batch_no="NEWBATCH",
                                 tgl_ed=date(2029, 1, 1), qty_fisik=8),
        ],
    )
    opname = OpnameService(db).create_opname(payload=payload, actor=staf)
    OpnameService(db).approve(opname.id_opname, actor=staf)

    db.refresh(p)
    new_lot = (db.query(StokLot)
               .filter(StokLot.id_produk == p.id_produk, StokLot.batch_no == "NEWBATCH")
               .first())
    assert new_lot is not None
    assert new_lot.qty_sisa == 8
    assert new_lot.tgl_ed == date(2029, 1, 1)
    assert float(p.stok_terkini) == 13   # 5 (lot A) + 8 (lot baru)
