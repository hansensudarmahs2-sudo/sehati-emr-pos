"""
P-L6b — test void mengembalikan qty ke LOT pilihan (batch fisik diretur) + fallback lot retur.
Non-destruktif (rollback; _reverse_stok_per_item FLUSH bukan commit).
Run: .venv/bin/pytest tests/integration/test_void_return_lot.py -v
"""
import random
from datetime import date

import pytest

from app.db.session import SessionLocal
from app.db.models import (
    StokLot, MasterProduk, MasterStaf, TransaksiKasir, TransaksiDetailProduk, Kunjungan,
)
from app.db.models._enums import TipeProdukEnum
from app.db.models import KunjunganResep, StatusItemResepEnum
from app.services.kasir_service import KasirService


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _setup(db, lot_status="HABIS", lot_qty=0):
    staf = db.query(MasterStaf).first()
    kunjungan = db.query(Kunjungan).first()
    if staf is None or kunjungan is None:
        import pytest as _pytest
        _pytest.skip("Butuh minimal 1 baris master_staf dan 1 baris kunjungan di DB test.")
    # P0-1: reverse stok hanya jalan kalau obat sudah diserah (kunjungan COMPLETED).
    kunjungan.status_antrian = "COMPLETED"
    db.flush()
    p = MasterProduk(
        kode_produk=f"VR{random.randint(10000,99999)}", nama_produk="Void Return Test",
        tipe_produk=TipeProdukEnum.RETAIL, satuan="pcs", default_iterasi=1,
        eligible_member_discount=False, stok_terkini=0,
    )
    db.add(p); db.flush()
    trx = TransaksiKasir(id_kunjungan=kunjungan.id_kunjungan, id_staf_kasir=staf.id_staf, rincian_tagihan="t", total_tagihan=100000, status_transaksi="BAYAR")
    db.add(trx); db.flush()
    detail = TransaksiDetailProduk(id_transaksi=trx.id_transaksi, id_produk=p.id_produk,
                                   qty=3, harga_satuan=10000, subtotal=30000)
    db.add(detail); db.flush()
    lot = StokLot(tipe_item="PRODUK", id_produk=p.id_produk, lokasi="RETAIL",
                  batch_no="BATCH-X", tgl_ed=date(2027, 1, 1), qty_masuk=3, qty_sisa=lot_qty,
                  status=lot_status, tgl_masuk=date(2026, 1, 1))
    db.add(lot); db.flush()
    # Task #54 (2026-09-22) — BUKTI PENYERAHAN PER ITEM.
    # Fixture ini dulu hanya menyetel kunjungan COMPLETED, mengikuti tebakan lama
    # "COMPLETED = obat sudah diserah". Tebakan itu DICABUT oleh #54 karena sejak
    # serah-per-item sebuah kunjungan bisa COMPLETED sementara itemnya belum
    # diserahkan sama sekali — dan memakainya akan "mengembalikan stok yang tidak
    # pernah keluar" (lihat docstring _produk_stok_sudah_dipotong).
    # Penilaiannya kini lewat _mode_per_item, yang menuntut jejak nyata: resep
    # berstatus DISERAHKAN. Tanpa baris di bawah, _reverse_stok_per_item menjawab 0
    # — dan itu JAWABAN YANG BENAR, karena memang tidak ada yang pernah diserahkan.
    db.add(KunjunganResep(
        id_kunjungan=kunjungan.id_kunjungan, id_produk=p.id_produk, qty=3,
        aturan_pakai="-", status_item=StatusItemResepEnum.DISERAHKAN,
        id_staf_input=staf.id_staf,
    ))
    db.flush()
    return staf, p, trx, detail, lot


def test_void_return_ke_lot_pilihan(db):
    staf, p, trx, detail, lot = _setup(db, lot_status="HABIS", lot_qty=0)
    KasirService(db)._reverse_stok_per_item(
        trx, [detail.id_detail], staf.id_staf, None, lot_map={detail.id_detail: lot.id_lot})
    db.refresh(lot); db.refresh(p)
    assert lot.qty_sisa == 3            # qty balik ke lot batch-X
    assert lot.status == "AKTIF"        # lot HABIS diaktifkan lagi
    assert float(p.stok_terkini) == 3   # cache ikut naik


def test_void_fallback_lot_retur_baru(db):
    staf, p, trx, detail, lot = _setup(db, lot_status="AKTIF", lot_qty=1)
    KasirService(db)._reverse_stok_per_item(
        trx, [detail.id_detail], staf.id_staf, None, lot_map={})  # tak pilih batch
    # lot lama tak berubah; ada lot VOID-RETURN baru dengan qty 3
    db.refresh(lot)
    assert lot.qty_sisa == 1
    retur = db.query(StokLot).filter(StokLot.id_produk == p.id_produk,
                                     StokLot.batch_no == "VOID-RETURN").all()
    assert len(retur) == 1 and retur[0].qty_sisa == 3
