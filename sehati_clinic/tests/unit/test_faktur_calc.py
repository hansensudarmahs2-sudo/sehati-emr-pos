"""FK-L2 — unit test kalkulasi diskon terbalik (pure Decimal, no DB)."""
from decimal import Decimal

from app.services.faktur_calc import hitung_dari_total, hitung_dari_diskon


def test_contoh_dr_hansen_2item():
    items = [{"harga_order": 750000, "qty": 1}, {"harga_order": 250000, "qty": 1}]
    r = hitung_dari_total(items, ppn_persen=11, total_ditagih=888000)
    assert r["ok"]
    assert r["diskon_persen"] == Decimal("20.00")
    assert r["per_item"][0]["harga_terima"] == Decimal("600000")
    assert r["per_item"][1]["harga_terima"] == Decimal("200000")
    assert r["extra_diskon"] == Decimal("0.00")
    assert r["total_ditagih"] == Decimal("888000.00")


def test_rekonsiliasi_pembulatan():
    # Y yang tak jatuh ke % bersih → extra_diskon menyerap sisa; final tetap = Y
    items = [{"harga_order": 333333, "qty": 3}]
    r = hitung_dari_total(items, ppn_persen=11, total_ditagih=888000)
    assert r["ok"]
    final = (r["subtotal_setelah_diskon"] * Decimal("1.11")).quantize(Decimal("0.01")) - r["extra_diskon"]
    assert final == r["total_ditagih"]


def test_guard_x_nol():
    r = hitung_dari_total([{"harga_order": 0, "qty": 5}], ppn_persen=11, total_ditagih=100000)
    assert not r["ok"]


def test_harga_naik_flag():
    # Y lebih besar dari harga list + PPN → diskon negatif (harga naik)
    items = [{"harga_order": 100000, "qty": 1}]
    r = hitung_dari_total(items, ppn_persen=11, total_ditagih=133200)  # > 111000
    assert r["ok"] and r["harga_naik"] is True


def test_maju_dari_diskon():
    items = [{"harga_order": 750000, "qty": 1}, {"harga_order": 250000, "qty": 1}]
    r = hitung_dari_diskon(items, ppn_persen=11, diskon_persen=20)
    assert r["total_ditagih"] == Decimal("888000.00")
