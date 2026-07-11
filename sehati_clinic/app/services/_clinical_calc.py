"""
Helper kalkulasi klinis — BMI, body fat Pollock, kategori BMI, usia.

Pertahankan formula dari kode lama dokter (`main_api.py` line 841-866):
- BMI = berat_kg / (tinggi_m^2)
- Body fat % via Jackson-Pollock 3-site + Siri equation

WHO BMI categories (Asia-Pacific cutoff Bapak boleh tweak nanti).
"""

from datetime import date
from typing import Optional


def hitung_usia(tgl_lahir: Optional[date]) -> int:
    """Usia dalam tahun. Return 0 kalau tgl_lahir None."""
    if not tgl_lahir:
        return 0
    today = date.today()
    return (
        today.year
        - tgl_lahir.year
        - ((today.month, today.day) < (tgl_lahir.month, tgl_lahir.day))
    )


def hitung_bmi(berat_kg: Optional[float], tinggi_cm: Optional[float]) -> float:
    """BMI = kg / m². Return 0.0 kalau data kurang."""
    if not berat_kg or not tinggi_cm or tinggi_cm == 0:
        return 0.0
    tinggi_m = tinggi_cm / 100.0
    return round(berat_kg / (tinggi_m ** 2), 1)


def kategori_bmi(bmi: float) -> str:
    """
    Kategori BMI berdasarkan klasifikasi WHO standar.

    Catatan: dr. Hansen bisa ganti ke Asia-Pacific cutoff (overweight ≥ 23, obese ≥ 25)
    kalau preferensi. Untuk Phase 1 kita pakai WHO standar.
    """
    if bmi <= 0:
        return "tidak_tersedia"
    if bmi < 18.5:
        return "underweight"
    if bmi < 25.0:
        return "normal"
    if bmi < 30.0:
        return "overweight"
    return "obese"


def hitung_body_fat_pollock(
    jenis_kelamin: str,
    usia: int,
    sum_skinfold_mm: float,
) -> float:
    """
    Body fat % via Jackson-Pollock 3-site + Siri equation.

    Pertahankan formula dari kode dokter lama:
    - Pria (L): BD = 1.10938 − (0.0008267 × ΣSF) + (0.0000016 × ΣSF²) − (0.0002574 × usia)
    - Wanita (P): BD = 1.0994921 − (0.0009929 × ΣSF) + (0.0000023 × ΣSF²) − (0.0001392 × usia)
    - Body fat % = (495 / BD) − 450 (Siri)

    Return 0.0 kalau data tidak lengkap (sum_sf ≤ 0 atau usia ≤ 0).
    """
    if sum_skinfold_mm <= 0 or usia <= 0:
        return 0.0

    jk_upper = (jenis_kelamin or "").upper()
    if jk_upper == "L":
        body_density = (
            1.10938
            - (0.0008267 * sum_skinfold_mm)
            + (0.0000016 * (sum_skinfold_mm ** 2))
            - (0.0002574 * usia)
        )
    else:  # P / fallback ke formula wanita
        body_density = (
            1.0994921
            - (0.0009929 * sum_skinfold_mm)
            + (0.0000023 * (sum_skinfold_mm ** 2))
            - (0.0001392 * usia)
        )

    if body_density <= 0:
        return 0.0

    body_fat_pct = (495.0 / body_density) - 450.0
    return round(max(0.0, body_fat_pct), 1)


def hitung_lean_pct(body_fat_pct: float) -> float:
    """Lean mass % = 100 − body fat %."""
    if body_fat_pct <= 0:
        return 0.0
    return round(100.0 - body_fat_pct, 1)


def sum_skinfold(s1: Optional[float], s2: Optional[float], s3: Optional[float]) -> float:
    """Total skinfold 3-site (mm). Nilai None dianggap 0."""
    return (s1 or 0.0) + (s2 or 0.0) + (s3 or 0.0)


__all__ = [
    "hitung_usia",
    "hitung_bmi",
    "kategori_bmi",
    "hitung_body_fat_pollock",
    "hitung_lean_pct",
    "sum_skinfold",
]
