"""
P0-1 (AUDIT_SEHATI_2026-07-10) — Void "reverse stok" hanya boleh untuk barang yang
BENAR-BENAR sudah keluar dari stok (sudah diserahkan). Kalau belum diserahkan,
stok tak pernah dipotong, jadi reverse HARUS no-op (bukan menambah = overstate).

Fakta alur (terverifikasi baca kode):
- `proses_bayar` TIDAK memotong `stok_terkini`.
- Stok produk HANYA dipotong saat serah obat (`ApotekService.serahkan_obat`), yang
  men-transisi kunjungan `ANTRI_OBAT -> COMPLETED`. Jadi:
    kunjungan COMPLETED  => obat sudah diserah => stok SUDAH dipotong => reverse SAH.
    belum COMPLETED (mis. ANTRI_OBAT) / tanpa kunjungan => stok BELUM dipotong => reverse = no-op.

Interim guard (tanpa migrasi): `_reverse_stok_per_item` men-skip reverse kalau
kunjungan transaksi belum COMPLETED.

Sifat test: NON-DESTRUKTIF (fixture `db` rollback; hanya flush). Memakai satu
kunjungan yang sudah ada di DB lalu mengubah statusnya HANYA di dalam sesi test
(ikut ter-rollback), supaya tak perlu membangun graf FK kunjungan dari nol.

Run:
  .venv/bin/pytest tests/integration/test_repro_P0_1_void_stock_inflation.py -v
"""
import random

import pytest

from app.db.session import SessionLocal
from app.db.models import (
    Kunjungan, MasterProduk, MasterStaf, TransaksiKasir, TransaksiDetailProduk,
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


def _setup(db, status_kunjungan, stok_terkini, qty_beli=3):
    """Produk + transaksi BAYAR yang terikat ke kunjungan dgn status tertentu.

    status_kunjungan="ANTRI_OBAT" => obat BELUM diserah (stok belum dipotong).
    status_kunjungan="COMPLETED"  => obat SUDAH diserah (stok sudah dipotong).
    """
    staf = db.query(MasterStaf).first()
    kunjungan = db.query(Kunjungan).first()
    if staf is None or kunjungan is None:
        pytest.skip("Butuh minimal 1 baris master_staf dan 1 baris kunjungan di DB test.")

    kunjungan.status_antrian = status_kunjungan  # hanya di sesi ini; rollback di teardown
    db.flush()

    produk = MasterProduk(
        kode_produk=f"P01{random.randint(10000, 99999)}",
        nama_produk="Repro P0-1", tipe_produk=TipeProdukEnum.RETAIL, satuan="pcs",
        default_iterasi=1, eligible_member_discount=False, stok_terkini=stok_terkini,
    )
    db.add(produk); db.flush()

    trx = TransaksiKasir(
        id_kunjungan=kunjungan.id_kunjungan, id_staf_kasir=staf.id_staf,
        rincian_tagihan="repro P0-1", total_tagihan=qty_beli * 10000,
        status_transaksi="BAYAR",
    )
    db.add(trx); db.flush()

    detail = TransaksiDetailProduk(
        id_transaksi=trx.id_transaksi, id_produk=produk.id_produk,
        qty=qty_beli, harga_satuan=10000, subtotal=qty_beli * 10000,
    )
    db.add(detail); db.flush()
    return staf, produk, trx, detail


def test_void_reverse_pada_obat_belum_diserah_tidak_menambah_stok(db):
    """Obat BELUM diserah (kunjungan ANTRI_OBAT) → stok tak pernah dipotong →
    void reverse HARUS no-op. Stok tetap 10 (bukan 13)."""
    stok_awal, qty = 10, 3
    staf, produk, trx, detail = _setup(db, "ANTRI_OBAT", stok_awal, qty)

    KasirService(db)._reverse_stok_per_item(
        trx, [detail.id_detail], staf.id_staf, None, lot_map={},
    )

    db.refresh(produk)
    assert float(produk.stok_terkini) == stok_awal, (
        f"OVERSTATE: stok jadi {float(produk.stok_terkini)} (harusnya {stok_awal}); "
        f"void me-reverse {qty} unit yang tak pernah dipotong dari stok."
    )


def test_void_reverse_pada_obat_sudah_diserah_mengembalikan_stok(db):
    """Obat SUDAH diserah (kunjungan COMPLETED, stok sudah dipotong jadi 7) →
    void reverse SAH mengembalikan 7 → 10. (Kontras: fix tak boleh merusak ini.)"""
    stok_awal, qty = 10, 3
    staf, produk, trx, detail = _setup(db, "COMPLETED", stok_awal - qty, qty)  # stok 7

    KasirService(db)._reverse_stok_per_item(
        trx, [detail.id_detail], staf.id_staf, None, lot_map={},
    )

    db.refresh(produk)
    assert float(produk.stok_terkini) == stok_awal, (
        "Untuk obat yang sudah diserah, reverse mengembalikan stok ke semula — benar."
    )
