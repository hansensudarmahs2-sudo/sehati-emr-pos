"""DYN-L4 — unit test reorder point dinamis (pure, no DB)."""
from app.services.reorder_calc import rop_dinamis, effective_min


def test_rop_dari_pemakaian():
    # 90 unit / 90 hari = 1/hari; cover 14+7=21 → ROP 21
    assert rop_dinamis(90, 14, 7) == 21


def test_no_pemakaian_rop_nol():
    assert rop_dinamis(0, 14, 7) == 0


def test_manual_jadi_lantai():
    # pemakaian rendah → ROP kecil, tapi manual 50 jadi lantai
    assert effective_min(50, 9, 14, 7) == 50.0  # ROP=ceil(0.1*21)=3 → max(50,3)=50


def test_dinamis_menaikkan_di_atas_manual():
    # fast mover: 900/90=10/hari, cover 21 → ROP 210 > manual 5
    assert effective_min(5, 900, 14, 7) == 210.0


def test_pembulatan_ke_atas():
    # 100/90=1.111/hari × 21 = 23.33 → ceil 24
    assert rop_dinamis(100, 14, 7) == 24
