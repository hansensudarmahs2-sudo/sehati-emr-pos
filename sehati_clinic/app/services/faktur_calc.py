"""
Faktur — kalkulasi diskon TERBALIK (FK-L2). Murni Decimal, TANPA dependensi DB/model
(bisa diunit-test standalone). Ref FAKTUR_MODULE_DESIGN.md §10.

Diketahui: X = Σ harga_order×qty (pra-diskon, pra-PPN), t = PPN%, Y = total ditagih.
Diskon seragam sebelum PPN:  d = 1 − Y/(X·(1+t)).
Harga terima per unit = harga_order·(1−d), dibulatkan ke rupiah utuh.
extra_diskon = (Σ harga_terima×qty)·(1+t) − Y  → rekonsiliasi agar total = Y persis.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

_TWO = Decimal("0.01")
_RP = Decimal("1")


def _D(x) -> Decimal:
    if x is None or x == "":
        return Decimal(0)
    return Decimal(str(x))


def hitung_dari_total(items: list, ppn_persen, total_ditagih) -> dict:
    """items: list dict {harga_order, qty, ...}. Return hasil kalkulasi + per_item."""
    t = _D(ppn_persen) / Decimal(100)
    Y = _D(total_ditagih)
    X = sum((_D(it.get("harga_order")) * _D(it.get("qty")) for it in items), Decimal(0))
    if X <= 0:
        return {"ok": False, "error": "Harga order item belum lengkap (subtotal 0). Isi harga order dulu."}
    if Y <= 0:
        return {"ok": False, "error": "Total ditagih harus lebih dari 0."}

    gross = X * (Decimal(1) + t)
    d = Decimal(1) - (Y / gross)

    per_item = []
    S = Decimal(0)
    for it in items:
        order = _D(it.get("harga_order"))
        qty = _D(it.get("qty"))
        terima = (order * (Decimal(1) - d)).quantize(_RP, rounding=ROUND_HALF_UP)
        if terima < 0:
            terima = Decimal(0)
        per_item.append({
            **it,
            "harga_terima": terima,
            "subtotal_terima": (terima * qty).quantize(_TWO),
        })
        S += terima * qty

    total_tanpa_extra = (S * (Decimal(1) + t)).quantize(_TWO)
    extra = (total_tanpa_extra - Y).quantize(_TWO)
    return {
        "ok": True,
        "subtotal_order": X.quantize(_TWO),
        "diskon_persen": (d * Decimal(100)).quantize(_TWO),
        "subtotal_setelah_diskon": S.quantize(_TWO),
        "ppn_rupiah": (S * t).quantize(_TWO),
        "extra_diskon": extra,
        "total_ditagih": Y.quantize(_TWO),
        "per_item": per_item,
        "harga_naik": d < 0,
    }


def hitung_dari_diskon(items: list, ppn_persen, diskon_persen) -> dict:
    """Mode maju: input diskon% → hitung total ditagih (Y). extra_diskon = 0."""
    t = _D(ppn_persen) / Decimal(100)
    d = _D(diskon_persen) / Decimal(100)
    X = sum((_D(it.get("harga_order")) * _D(it.get("qty")) for it in items), Decimal(0))
    if X <= 0:
        return {"ok": False, "error": "Harga order item belum lengkap (subtotal 0)."}
    per_item = []
    S = Decimal(0)
    for it in items:
        order = _D(it.get("harga_order"))
        qty = _D(it.get("qty"))
        terima = (order * (Decimal(1) - d)).quantize(_RP, rounding=ROUND_HALF_UP)
        if terima < 0:
            terima = Decimal(0)
        per_item.append({**it, "harga_terima": terima, "subtotal_terima": (terima * qty).quantize(_TWO)})
        S += terima * qty
    total = (S * (Decimal(1) + t)).quantize(_TWO)
    return {
        "ok": True,
        "subtotal_order": X.quantize(_TWO),
        "diskon_persen": (d * Decimal(100)).quantize(_TWO),
        "subtotal_setelah_diskon": S.quantize(_TWO),
        "ppn_rupiah": (S * t).quantize(_TWO),
        "extra_diskon": Decimal("0.00"),
        "total_ditagih": total,
        "per_item": per_item,
        "harga_naik": d < 0,
    }


__all__ = ["hitung_dari_total", "hitung_dari_diskon"]
