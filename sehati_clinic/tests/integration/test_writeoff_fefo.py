"""
P-L6a — test write-off produk memotong lot FEFO (ED terdekat/expired duluan).
CATATAN: write_off_produk commit internal → data test persist (jalankan di DB dev).
Run: .venv/bin/pytest tests/integration/test_writeoff_fefo.py -v
"""
import random
from datetime import date

import pytest

from app.db.session import SessionLocal
from app.db.models import StokLot, MasterProduk, MasterStaf
from app.db.models._enums import TipeProdukEnum
from app.schemas.apotek import WriteOffProdukRequest
from app.services.apotek_service import ApotekService


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def test_writeoff_potong_lot_fefo(db):
    staf = db.query(MasterStaf).first()
    assert staf is not None
    p = MasterProduk(
        kode_produk=f"WO{random.randint(10000,99999)}", nama_produk="WriteOff Test",
        tipe_produk=TipeProdukEnum.RETAIL, satuan="pcs", default_iterasi=1,
        eligible_member_discount=False, stok_terkini=10,
    )
    db.add(p)
    db.flush()
    l_early = StokLot(tipe_item="PRODUK", id_produk=p.id_produk, lokasi="RETAIL",
                      batch_no="EARLY", tgl_ed=date(2026, 1, 1), qty_masuk=4, qty_sisa=4,
                      status="AKTIF", tgl_masuk=date(2025, 12, 1))
    l_late = StokLot(tipe_item="PRODUK", id_produk=p.id_produk, lokasi="RETAIL",
                     batch_no="LATE", tgl_ed=date(2028, 1, 1), qty_masuk=6, qty_sisa=6,
                     status="AKTIF", tgl_masuk=date(2026, 1, 1))
    db.add_all([l_early, l_late])
    db.flush()

    payload = WriteOffProdukRequest(id_produk=p.id_produk, qty_dibuang=5,
                                    jenis_mutasi="EXPIRED", keterangan="test expired")
    ApotekService(db).write_off_produk(payload=payload, id_staf_apoteker=staf.id_staf)

    db.refresh(l_early); db.refresh(l_late); db.refresh(p)
    assert l_early.qty_sisa == 0 and l_early.status == "HABIS"   # ED terdekat/expired diambil dulu
    assert l_late.qty_sisa == 5                                   # 1 dari lot late
    assert float(p.stok_terkini) == 5                            # cache ikut turun
