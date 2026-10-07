"""Nomor RM Omnicare (sistem lama) — SATU sumber kebenaran bentuknya.

LATAR BELAKANG (dr. Hansen 2026-10-07)
--------------------------------------
Klinik masih menginput pasien DUA KALI: di Sehati (emr.joderma.id) dan di
Omnicare. Nomor RM di Omnicare diketik manual, dan Sehati dijadikan SUMBER
nomornya: staf melihat nomor tertinggi di Cari Pasien, mendaftarkan pasien di
Sehati dengan nomor berikutnya, lalu menyalin datanya ke Omnicare. Kolom ini juga
persiapan migrasi data lama.

Bentuk: `JJ-` (cabang Jemur) atau `JC-` (Citraland) + angka. Hari ini 4 digit
(Jemur 81xx, Citraland 20xx), sebentar lagi 5 digit.

KEPUTUSAN BENTUK
----------------
- Disimpan TANPA nol di depan (`JJ-08123` -> `JJ-8123`). Tanpa itu, nomor yang
  sama diketik dua gaya lolos dari unique index — pelajaran NIK (app/core/nik.py).
- "Tertinggi" WAJIB dibandingkan sebagai ANGKA (`angka()`), bukan teks: sebagai
  teks `JJ-8199` > `JJ-10000`, jadi tepat saat nomor menyentuh 5 digit Sehati
  akan menunjuk nomor yang salah dan staf membagikan nomor ganda.
- Kosong / '-' / '0' -> None (NULL). MySQL mengizinkan banyak NULL di unique
  index; string kosong tidak.
- Bentuk lain DITOLAK (beda dengan NIK yang normalisasinya lunak): nomor ini
  dipakai untuk mencocokkan dua sistem, jadi nomor yang salah bentuk lebih
  berbahaya daripada nomor yang kosong.

Kolomnya bernama `no_rm_omnicare`, BUKAN `no_rm_lama`: tabel pasien sudah punya
`nomor_ktp_lama` yang berarti "NIK yang dilepas saat nonaktif". Satu kata, dua
arti di tabel yang sama = jebakan CLAUDE.md §4.1.
"""
import re
from typing import Optional

PREFIX = ("JJ", "JC")
LABEL_CABANG = {"JJ": "Jemur", "JC": "Citraland"}

# Spasi & tanda hubung boleh di mana saja; angka 1–6 digit (setelah nol depan dibuang).
_POLA = re.compile(r"^(JJ|JC)-?(\d{1,7})$")
_PENANDA_KOSONG = {"", "-", "--", "0", "JJ-", "JC-", "JJ", "JC"}


class NoRmOmnicareTidakSah(ValueError):
    """Bentuk nomor tidak dikenali — pesan siap ditampilkan ke staf."""


def normalisasi_no_rm_omnicare(raw) -> Optional[str]:
    """Kembalikan bentuk baku (`JJ-8123`) atau None bila kosong.

    >>> normalisasi_no_rm_omnicare(" jj-8123 ")
    'JJ-8123'
    >>> normalisasi_no_rm_omnicare("JJ-08123")
    'JJ-8123'
    >>> normalisasi_no_rm_omnicare("jc 2010")
    'JC-2010'
    >>> normalisasi_no_rm_omnicare("JJ10234")
    'JJ-10234'
    >>> normalisasi_no_rm_omnicare("") is None
    True
    >>> normalisasi_no_rm_omnicare("-") is None
    True
    """
    if raw is None:
        return None
    s = re.sub(r"\s+", "", str(raw)).upper()
    if s in _PENANDA_KOSONG:
        return None
    m = _POLA.match(s)
    if not m:
        raise NoRmOmnicareTidakSah(
            f"No. RM Omnicare '{raw}' tidak dikenali. Bentuknya JJ-angka (Jemur) "
            f"atau JC-angka (Citraland), mis. JJ-8123.")
    nomor = int(m.group(2))
    if nomor < 1 or nomor > 999999:
        raise NoRmOmnicareTidakSah(
            f"No. RM Omnicare '{raw}': angkanya harus 1 sampai 999999.")
    return f"{m.group(1)}-{nomor}"


CABANG_DEFAULT = "JJ"   # klinik ini cabang Jemur (dr. Hansen 2026-10-07)


def gabung_isian(cabang, angka_diketik) -> str:
    """Isian form: tombol cabang (JJ/JC) + kotak ANGKA saja → teks mentah untuk
    `normalisasi_no_rm_omnicare` (dr. Hansen 2026-10-07: prefix otomatis, staf hanya
    mengetik angka).

    - Angka kosong → "" (tidak ada nomor; di form edit artinya HAPUS).
    - Kalau staf menempel nomor LENGKAP (ada huruf, mis. "JC-2010"), itu yang dipakai —
      prefix yang diketik eksplisit menang atas tombol, supaya salin-tempel dari
      Omnicare tidak diam-diam berpindah cabang.
    - Penggabungan dilakukan di SERVER; JavaScript di layar hanya menampilkan prefix.

    >>> gabung_isian("JJ", "8124")
    'JJ-8124'
    >>> gabung_isian("JC", " 2010 ")
    'JC-2010'
    >>> gabung_isian(None, "8124")
    'JJ-8124'
    >>> gabung_isian("JJ", "JC-2010")
    'JC-2010'
    >>> gabung_isian("JJ", "")
    ''
    """
    a = re.sub(r"\s+", "", str(angka_diketik or ""))
    if not a:
        return ""
    if re.search(r"[A-Za-z]", a):
        return a
    c = str(cabang or CABANG_DEFAULT).strip().upper()
    if c not in PREFIX:
        raise NoRmOmnicareTidakSah(f"Cabang '{cabang}' tidak dikenal — pilih Jemur atau Citraland.")
    return f"{c}-{a.lstrip('-')}"


def angka(no_rm_omnicare: str) -> int:
    """Bagian angka dari nomor BAKU — untuk membandingkan sebagai angka."""
    return int(no_rm_omnicare.split("-", 1)[1])
