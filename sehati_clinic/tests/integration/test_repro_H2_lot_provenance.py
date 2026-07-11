"""
H2 / P0-1 lot-provenance (AUDIT_SEHATI_2026-07-10) — void mengembalikan qty ke LOT ASLI.

Sebelum fix: `_reverse_stok_per_item` membuat lot 'VOID-RETURN' tgl_ed=NULL (ED hilang,
tenggelam di belakang antrean FEFO). Sesudah fix: kalau ada jejak `kunjungan_lot_terpakai`
(diisi saat serah obat), reverse mengembalikan qty ke lot ASLI (ED asli terjaga) dan menandai
jejak `reversed_at`.

Sifat test: NON-DESTRUKTIF (fixture `db` rollback; helper FLUSH bukan commit).
Run: .venv/bin/pytest tests/integration/test_repro_H2_lot_provenance.py -v
"""
import random
from datetime import date

import pytest

from app.db.session import SessionLocal
from app.db.models import (
    Kunjungan, MasterProduk, MasterStaf, StokLot, KunjunganLotTerpakai,
    TransaksiKasir, TransaksiDetailProduk,
)
from app.db.models._enums import TipeProdukEnum
from app.services.kasir_service import KasirService


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _setup_dispensed_from_lot(db, qty=3):
    """Kunjungan COMPLETED + lot ASLI (ED nyata) yang sudah HABIS karena serah,
    + jejak kunjungan_lot_terpakai. Stok cache = 0 (sudah dipotong saat serah)."""
    staf = db.query(MasterStaf).first()
    kunjungan = db.query(Kunjungan).first()
    if staf is None or kunjungan is None:
        pytest.skip("Butuh minimal 1 baris master_staf dan 1 baris kunjungan di DB test.")
    kunjungan.status_antrian = "COMPLETED"
    db.flush()

    produk = MasterProduk(
        kode_produk=f"H2{random.randint(10000, 99999)}", nama_produk="Repro H2",
        tipe_produk=TipeProdukEnum.RETAIL, satuan="pcs", default_iterasi=1,
        eligible_member_discount=False, stok_terkini=0,
    )
    db.add(produk); db.flush()

    # Lot ASLI: ED nyata, sudah HABIS karena serah memotongnya.
    lot = StokLot(
        tipe_item="PRODUK", id_produk=produk.id_produk, lokasi="RETAIL",
        batch_no="BATCH-ASLI", tgl_ed=date(2027, 6, 30), qty_masuk=qty, qty_sisa=0,
        status="HABIS", tgl_masuk=date(2026, 1, 1),
    )
    db.add(lot); db.flush()

    trx = TransaksiKasir(
        id_kunjungan=kunjungan.id_kunjungan, id_staf_kasir=staf.id_staf,
        rincian_tagihan="repro H2", total_tagihan=qty * 10000, status_transaksi="BAYAR",
    )
    db.add(trx); db.flush()
    detail = TransaksiDetailProduk(
        id_transaksi=trx.id_transaksi, id_produk=produk.id_produk,
        qty=qty, harga_satuan=10000, subtotal=qty * 10000,
    )
    db.add(detail); db.flush()

    # Jejak lot terpakai (seperti yang ditulis serahkan_obat).
    jejak = KunjunganLotTerpakai(
        id_kunjungan=kunjungan.id_kunjungan, id_produk=produk.id_produk,
        id_lot=lot.id_lot, qty=qty,
    )
    db.add(jejak); db.flush()
    return staf, produk, lot, trx, detail, jejak


def test_void_reverse_ke_lot_asli_bukan_void_return(db):
    qty = 3
    staf, produk, lot, trx, detail, jejak = _setup_dispensed_from_lot(db, qty)

    KasirService(db)._reverse_stok_per_item(
        trx, [detail.id_detail], staf.id_staf, None, lot_map={},
    )

    db.refresh(lot); db.refresh(produk); db.refresh(jejak)
    # Lot ASLI dipulihkan (ED asli terjaga), status AKTIF lagi.
    assert float(lot.qty_sisa) == qty, f"Lot asli harus pulih ke {qty}, dapat {lot.qty_sisa}."
    assert lot.status == "AKTIF"
    assert lot.tgl_ed == date(2027, 6, 30)
    # TIDAK ada lot VOID-RETURN baru.
    void_return = db.query(StokLot).filter(
        StokLot.id_produk == produk.id_produk, StokLot.batch_no == "VOID-RETURN"
    ).count()
    assert void_return == 0, "Tidak boleh ada lot VOID-RETURN bila jejak lot asli tersedia."
    # Jejak ditandai reversed → cegah double-restore.
    assert jejak.reversed_at is not None
    # Cache stok naik sesuai qty.
    assert float(produk.stok_terkini) == qty


def test_serah_menulis_jejak_lot_terpakai(db):
    """Sisi tulis: serahkan_obat merekam lot FEFO yang dikonsumsi (writer helper)."""
    from app.services.apotek_service import ApotekService

    staf = db.query(MasterStaf).first()
    kunjungan = db.query(Kunjungan).first()
    if staf is None or kunjungan is None:
        pytest.skip("Butuh master_staf + kunjungan.")
    produk = MasterProduk(
        kode_produk=f"H2W{random.randint(10000, 99999)}", nama_produk="Repro H2 writer",
        tipe_produk=TipeProdukEnum.RETAIL, satuan="pcs", default_iterasi=1,
        eligible_member_discount=False, stok_terkini=0,
    )
    db.add(produk); db.flush()
    lot = StokLot(
        tipe_item="PRODUK", id_produk=produk.id_produk, lokasi="RETAIL",
        batch_no="B-W", tgl_ed=date(2028, 1, 1), qty_masuk=5, qty_sisa=3,
        status="AKTIF", tgl_masuk=date(2026, 1, 1),
    )
    db.add(lot); db.flush()

    consumed = [{"id_lot": lot.id_lot, "qty": 2.0, "batch_no": "B-W", "tgl_ed": lot.tgl_ed}]
    ApotekService(db)._simpan_lot_terpakai(kunjungan.id_kunjungan, produk.id_produk, consumed)

    rows = db.query(KunjunganLotTerpakai).filter(
        KunjunganLotTerpakai.id_kunjungan == kunjungan.id_kunjungan,
        KunjunganLotTerpakai.id_produk == produk.id_produk,
    ).all()
    assert len(rows) == 1
    assert rows[0].id_lot == lot.id_lot and float(rows[0].qty) == 2.0
    assert rows[0].reversed_at is None
