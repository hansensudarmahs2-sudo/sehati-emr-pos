"""
CSV writer helper untuk Owner Raw Data Export module.

Pattern: convert list of dict → bytes CSV (UTF-8, header included).
Pakai csv.QUOTE_ALL untuk safety (escape newline/koma dalam TEXT fields).
"""

import csv
import io
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable


# P1-5 (AUDIT_SEHATI_2026-07-10): karakter pemicu rumus spreadsheet. Nilai TEKS yang
# diawali salah satunya dieksekusi Excel/Sheets sebagai rumus saat file dibuka.
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def _neutralize_formula(s: str) -> str:
    """Cegah CSV formula injection: prefix teks yang diawali pemicu rumus dengan '.

    Hanya untuk STRING (teks bebas yang bisa diisi user — nama, keluhan, catatan).
    Angka (Decimal/int/float) TIDAK lewat sini, jadi nilai negatif tetap utuh.
    """
    if s and s[0] in _FORMULA_TRIGGERS:
        return "'" + s
    return s


def _to_csv_safe(value: Any) -> str:
    """Convert value ke string CSV-safe.

    None → "" (empty), datetime → ISO string, Decimal → str, teks → anti-formula-injection.
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (dict, list)):
        # JSON struktur (e.g., dari audit_log.data_lama) → flatten ke JSON string
        import json
        return json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, str):
        return _neutralize_formula(value)
    return str(value)


def dict_list_to_csv_bytes(
    items: Iterable[dict],
    columns: list[str] | None = None,
) -> bytes:
    """
    Convert list of dict ke CSV bytes (UTF-8 with BOM untuk Excel compat).

    Args:
        items: iterable of dict (semua dict harus punya kolom yang sama)
        columns: optional explicit column order. Kalau None, auto-detect dari item pertama.

    Returns:
        bytes UTF-8 BOM-prefixed CSV.
    """
    buf = io.StringIO()

    # Materialize iter ke list (perlu peek item pertama untuk column auto-detect)
    items_list = list(items) if not isinstance(items, list) else items

    if not items_list:
        # Empty dataset — return CSV dengan header saja (kalau columns provided), else just empty
        if columns:
            writer = csv.DictWriter(buf, fieldnames=columns, quoting=csv.QUOTE_ALL, lineterminator="\n")
            writer.writeheader()
        return ("﻿" + buf.getvalue()).encode("utf-8")

    if columns is None:
        columns = list(items_list[0].keys())

    writer = csv.DictWriter(buf, fieldnames=columns, quoting=csv.QUOTE_ALL, lineterminator="\n")
    writer.writeheader()
    for row in items_list:
        # Sanitize semua values dulu sebelum write
        clean_row = {col: _to_csv_safe(row.get(col)) for col in columns}
        writer.writerow(clean_row)

    # Prefix BOM (﻿) supaya Excel buka dengan UTF-8 encoding benar
    return ("﻿" + buf.getvalue()).encode("utf-8")


__all__ = ["dict_list_to_csv_bytes"]
