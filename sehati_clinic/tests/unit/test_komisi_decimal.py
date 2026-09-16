"""P2-1 regresi: math komisi pakai Decimal (bebas galat biner) + quantize 2dp.

Menargetkan _hitung_komisi_satu di kedua service (nilai yang disimpan ke
komisi_nominal DECIMAL(12,2)). Kasus 15% dari 333 = 49.95 mengekspos galat float.
"""
from app.services.master_produk_service import (
    _hitung_komisi_satu as komisi_produk,
    KOMISI_TIPE_PERSEN_HARGA, KOMISI_TIPE_PERSEN_MARGIN, KOMISI_TIPE_NOMINAL,
)
from app.services.master_treatment_service import (
    _hitung_komisi_satu as komisi_treat,
)


def test_persen_harga_exact_2dp():
    # 15% × 333 = 49.95 (float mentah = 49.949999999999996)
    assert komisi_produk(KOMISI_TIPE_PERSEN_HARGA, 15, 333, 0) == 49.95
    assert komisi_treat(KOMISI_TIPE_PERSEN_HARGA, 15, 333, 0) == 49.95


def test_persen_margin_clamp_nonnegatif():
    # margin negatif (hpp>harga) → komisi 0, bukan negatif
    assert komisi_produk(KOMISI_TIPE_PERSEN_MARGIN, 10, 100, 250) == 0.0
    # margin normal: 10% × (10000-4000) = 600
    assert komisi_treat(KOMISI_TIPE_PERSEN_MARGIN, 10, 10000, 4000) == 600.0


def test_nominal_dan_nol():
    assert komisi_produk(KOMISI_TIPE_NOMINAL, 25000, 999999, 0) == 25000.0
    assert komisi_produk(None, 10, 500, 0) == 0.0
    assert komisi_treat(KOMISI_TIPE_PERSEN_HARGA, 0, 500, 0) == 0.0
