"""
P-L6b — void mengembalikan qty ke LOT pilihan operator (batch fisik yang diretur),
dengan fallback lot 'VOID-RETURN'. Plus pagar Temuan 30.
Non-destruktif (rollback; _reverse_stok_per_item FLUSH bukan commit).
Run: .venv/bin/pytest tests/integration/test_void_return_lot.py -v

⚠ Dirombak 2026-10-04 (Temuan 30). Sebelumnya fixture menyetel resep `DISERAHKAN`
TANPA jejak `kunjungan_lot_terpakai`, lalu menuntut void mengembalikan qty-nya ke lot
pilihan / lot retur baru. Bentuk itu TIDAK BISA dihasilkan alur nyata untuk data baru:
`serahkan_obat` selalu menulis jejak untuk setiap lot yang benar-benar dipotong. Yang
diuji dulu justru penyerahan FANTOM — `DISERAHKAN` tanpa satu lot pun keluar — dan
mengembalikannya MENCIPTAKAN barang yang tak pernah ada.

Jadi kedua test lot-pilihan/fallback dipindahkan ke bentuk **data LAMA**, satu-satunya
tempat `lot_map` masih berlaku: kunjungan yang sudah punya jejak untuk produk LAIN
(sehingga `_mode_per_item` → False) tapi produk yang di-void ini tidak punya jejak.
Dua test baru menjaga perilaku per-item yang benar.
"""
import random
from datetime import date

import pytest

from app.db.session import SessionLocal
from app.db.models import (
    StokLot, MasterProduk, MasterStaf, TransaksiKasir, TransaksiDetailProduk, Kunjungan,
    KunjunganLotTerpakai,
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


def _produk(db, stok=0):
    p = MasterProduk(
        kode_produk=f"VR{random.randint(10000,99999)}", nama_produk="Void Return Test",
        tipe_produk=TipeProdukEnum.RETAIL, satuan="pcs", default_iterasi=1,
        eligible_member_discount=False, stok_terkini=stok,
    )
    db.add(p); db.flush()
    return p


def _lot(db, p, qty, status, batch="BATCH-X"):
    lot = StokLot(tipe_item="PRODUK", id_produk=p.id_produk, lokasi="RETAIL",
                  batch_no=batch, tgl_ed=date(2027, 1, 1), qty_masuk=max(qty, 3),
                  qty_sisa=qty, status=status, tgl_masuk=date(2026, 1, 1))
    db.add(lot); db.flush()
    return lot


def _setup(db, lot_status="HABIS", lot_qty=0, *, gaya_lama, jejak_qty=0):
    """Siapkan satu transaksi berisi 3 unit satu produk, siap di-void.

    `gaya_lama=True`  → bentuk data LAMA: itemnya masih `DIBAYAR` (status `DISERAHKAN`
                        belum ada saat itu) dan kunjungan punya jejak untuk produk LAIN,
                        sehingga `_mode_per_item` menjawab False dan penilaian jatuh ke
                        `_produk_stok_sudah_dipotong` (kunjungan COMPLETED).
    `gaya_lama=False` → skema per-item: resepnya `DISERAHKAN`. `jejak_qty` = berapa unit
                        yang benar-benar keluar dari lot saat serah.
    """
    staf = db.query(MasterStaf).first()
    kunjungan_apa_pun = db.query(Kunjungan).first()
    if staf is None or kunjungan_apa_pun is None:
        pytest.skip("Butuh minimal 1 baris master_staf dan 1 baris kunjungan di DB test.")
    # Kunjungan SENDIRI, bukan menumpang baris pertama di DB.
    # Dulu fixture ini memakai `db.query(Kunjungan).first()`, dan kunjungan itu di DB
    # seed ternyata SUDAH punya baris resep `DISERAHKAN` milik produk lain. Akibatnya
    # `_mode_per_item` selalu menjawab True dan bentuk "data lama" tidak pernah benar-
    # benar teruji — hasil testnya bergantung pada data seed, bukan pada kodenya.
    kunjungan = Kunjungan(id_pasien=kunjungan_apa_pun.id_pasien, status_antrian="COMPLETED")
    db.add(kunjungan); db.flush()

    p = _produk(db)
    trx = TransaksiKasir(id_kunjungan=kunjungan.id_kunjungan, id_staf_kasir=staf.id_staf,
                         rincian_tagihan="t", total_tagihan=100000, status_transaksi="BAYAR")
    db.add(trx); db.flush()
    detail = TransaksiDetailProduk(id_transaksi=trx.id_transaksi, id_produk=p.id_produk,
                                   qty=3, harga_satuan=10000, subtotal=30000)
    db.add(detail); db.flush()
    lot = _lot(db, p, lot_qty, lot_status)

    resep = KunjunganResep(
        id_kunjungan=kunjungan.id_kunjungan, id_produk=p.id_produk, qty=3,
        aturan_pakai="-", id_staf_input=staf.id_staf,
        status_item=(StatusItemResepEnum.DIBAYAR if gaya_lama
                     else StatusItemResepEnum.DISERAHKAN),
    )
    db.add(resep); db.flush()

    if gaya_lama:
        # Jejak milik produk LAIN di kunjungan yang sama — cukup untuk membuat
        # `_mode_per_item` menjawab False tanpa memberi jejak ke produk yang di-void.
        p_lain = _produk(db, stok=5)
        lot_lain = _lot(db, p_lain, 5, "AKTIF", batch="BATCH-LAIN")
        db.add(KunjunganLotTerpakai(
            id_kunjungan=kunjungan.id_kunjungan, id_produk=p_lain.id_produk,
            id_lot=lot_lain.id_lot, qty=1,  # gaya lama: id_resep & id_racikan NULL
        ))
        db.flush()
    elif jejak_qty:
        db.add(KunjunganLotTerpakai(
            id_kunjungan=kunjungan.id_kunjungan, id_produk=p.id_produk,
            id_lot=lot.id_lot, qty=jejak_qty, id_resep=resep.id_resep,
        ))
        db.flush()

    return staf, p, trx, detail, lot


# ---------------------------------------------------------------------------
# P-L6b — hanya berlaku untuk data LAMA (lihat docstring modul)
# ---------------------------------------------------------------------------
def test_void_return_ke_lot_pilihan(db):
    staf, p, trx, detail, lot = _setup(db, lot_status="HABIS", lot_qty=0, gaya_lama=True)
    KasirService(db)._reverse_stok_per_item(
        trx, [detail.id_detail], staf.id_staf, None, lot_map={detail.id_detail: lot.id_lot})
    db.refresh(lot); db.refresh(p)
    assert lot.qty_sisa == 3            # qty balik ke lot batch-X
    assert lot.status == "AKTIF"        # lot HABIS diaktifkan lagi
    assert float(p.stok_terkini) == 3   # cache ikut naik


def test_void_fallback_lot_retur_baru(db):
    staf, p, trx, detail, lot = _setup(db, lot_status="AKTIF", lot_qty=1, gaya_lama=True)
    KasirService(db)._reverse_stok_per_item(
        trx, [detail.id_detail], staf.id_staf, None, lot_map={})  # tak pilih batch
    # lot lama tak berubah; ada lot VOID-RETURN baru dengan qty 3
    db.refresh(lot)
    assert lot.qty_sisa == 1
    retur = db.query(StokLot).filter(StokLot.id_produk == p.id_produk,
                                     StokLot.batch_no == "VOID-RETURN").all()
    assert len(retur) == 1 and retur[0].qty_sisa == 3


# ---------------------------------------------------------------------------
# Temuan 30 — skema per-item
# ---------------------------------------------------------------------------
def test_per_item_dengan_jejak_pulih_ke_lot_asli(db):
    """Serah yang sah: jejaknya ada, jadi qty kembali ke lot ASLI (ED terjaga)."""
    staf, p, trx, detail, lot = _setup(db, lot_status="HABIS", lot_qty=0,
                                       gaya_lama=False, jejak_qty=3)
    KasirService(db)._reverse_stok_per_item(
        trx, [detail.id_detail], staf.id_staf, None, lot_map={})
    db.refresh(lot); db.refresh(p)
    assert lot.qty_sisa == 3, "qty harus pulih ke lot asli, bukan lot baru"
    assert lot.batch_no == "BATCH-X" and lot.tgl_ed == date(2027, 1, 1)
    assert float(p.stok_terkini) == 3
    assert db.query(StokLot).filter(StokLot.id_produk == p.id_produk,
                                    StokLot.batch_no == "VOID-RETURN").count() == 0


def test_per_item_tanpa_jejak_tidak_menciptakan_lot(db):
    """TEMUAN 30 — penyerahan FANTOM: `DISERAHKAN` tanpa satu lot pun keluar.

    Terjadi kalau stok kurang saat serah; serah TIDAK diblokir (stok minus sengaja
    diizinkan). Void-nya tidak boleh menciptakan barang: tidak ada lot baru, dan lot
    pilihan operator pun tidak boleh diisi — lot aslinya memang tidak pernah keluar.
    `stok_terkini` tetap dikembalikan penuh karena serah juga memotongnya penuh.
    """
    staf, p, trx, detail, lot = _setup(db, lot_status="AKTIF", lot_qty=0,
                                       gaya_lama=False, jejak_qty=0)
    KasirService(db)._reverse_stok_per_item(
        trx, [detail.id_detail], staf.id_staf, None,
        lot_map={detail.id_detail: lot.id_lot})   # operator pilih batch — harus DIABAIKAN
    db.refresh(lot); db.refresh(p)
    assert lot.qty_sisa == 0, "lot tidak boleh bertambah — barangnya tak pernah keluar"
    assert db.query(StokLot).filter(StokLot.id_produk == p.id_produk,
                                    StokLot.batch_no == "VOID-RETURN").count() == 0, \
        "tidak boleh ada lot VOID-RETURN: itu barang fantom yang akan dibagikan FEFO"
    assert float(p.stok_terkini) == 3, "cache dikembalikan penuh, mencerminkan potongan serah"


def test_per_item_jejak_sebagian_hanya_pulih_sebanyak_yang_keluar(db):
    """Serah 3 unit tapi lot hanya mampu 2 → void memulihkan 2 ke lot, bukan 3."""
    staf, p, trx, detail, lot = _setup(db, lot_status="AKTIF", lot_qty=0,
                                       gaya_lama=False, jejak_qty=2)
    KasirService(db)._reverse_stok_per_item(
        trx, [detail.id_detail], staf.id_staf, None, lot_map={})
    db.refresh(lot)
    assert lot.qty_sisa == 2, "hanya 2 unit yang pernah keluar, jadi hanya 2 yang pulih"
    assert db.query(StokLot).filter(StokLot.id_produk == p.id_produk,
                                    StokLot.batch_no == "VOID-RETURN").count() == 0
