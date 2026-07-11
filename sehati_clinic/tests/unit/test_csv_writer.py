"""
P1-5 (AUDIT_SEHATI_2026-07-10) — CSV formula injection.

Nilai teks yang diawali `= + - @` (atau tab/CR) dieksekusi Excel/Sheets sebagai RUMUS
saat file dibuka. `_to_csv_safe` harus menetralkannya dengan prefix `'` — TAPI hanya
untuk STRING (teks yang bisa diisi user), BUKAN angka (Decimal/int/float boleh negatif).
"""
from decimal import Decimal

from app.core.csv_writer import _to_csv_safe, dict_list_to_csv_bytes


def test_string_diawali_pemicu_rumus_dinetralkan():
    for danger in ("=cmd()", "+1+2", "-1+2", "@SUM(A1)", "\t=x", "\r=y"):
        out = _to_csv_safe(danger)
        assert out.startswith("'"), f"{danger!r} harus di-prefix ' → dapat {out!r}"
        assert out[1:] == danger


def test_string_normal_tidak_diubah():
    for safe in ("Budi Santoso", "obat 500mg", "a=b+c", "", "RM-260710-001"):
        assert _to_csv_safe(safe) == safe


def test_angka_negatif_tidak_ikut_diprefix():
    # Angka bukan teks-injeksi user; jangan rusak jadi teks.
    assert _to_csv_safe(Decimal("-5000")) == "-5000"
    assert _to_csv_safe(-5) == "-5"
    assert _to_csv_safe(-3.5) == "-3.5"


def test_output_csv_menetralkan_rumus_di_field_bebas():
    payload = [{"nama_pasien": "Budi", "keluhan": '=HYPERLINK("http://jahat")'}]
    text = dict_list_to_csv_bytes(payload, columns=["nama_pasien", "keluhan"]).decode("utf-8-sig")
    assert "'=HYPERLINK" in text, "Nilai rumus harus dinetralkan (prefix ') di output CSV."
    assert "Budi" in text
