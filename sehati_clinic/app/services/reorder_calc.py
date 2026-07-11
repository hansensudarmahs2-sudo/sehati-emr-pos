"""
Reorder point dinamis (DYN) — fungsi murni, tanpa dependensi DB (bisa diunit-test standalone).

Ambang stok efektif = MAX(stok_minimal manual, ROP dinamis).
ROP dinamis = ceil( rata pemakaian harian × (lead_time + safety) ),
di mana rata pemakaian harian = qty terjual 90 hari / 90.

Manual = LANTAI pengaman (untuk item kritis). Dinamis MENAIKKAN ambang bila pemakaian tinggi,
sehingga produk laris tidak kehabisan sebelum barang datang. Ref DEC-094.
"""
import math


def rop_dinamis(qty_terjual_90d: float, lead_time_hari: int, safety_hari: int) -> int:
    """Reorder point dinamis (unit stok). 0 kalau tak ada pemakaian."""
    q = float(qty_terjual_90d or 0)
    if q <= 0:
        return 0
    rata_harian = q / 90.0
    cover = max(0, int(lead_time_hari or 0)) + max(0, int(safety_hari or 0))
    return int(math.ceil(rata_harian * cover))


def effective_min(stok_minimal_manual, qty_terjual_90d: float,
                  lead_time_hari: int, safety_hari: int) -> float:
    """Ambang efektif = MAX(manual, ROP dinamis)."""
    manual = float(stok_minimal_manual or 0)
    return max(manual, float(rop_dinamis(qty_terjual_90d, lead_time_hari, safety_hari)))


__all__ = ["rop_dinamis", "effective_min"]
