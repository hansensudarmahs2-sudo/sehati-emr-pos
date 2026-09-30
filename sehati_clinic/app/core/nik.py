"""Normalisasi NIK (nomor KTP) — SATU sumber kebenaran.

LATAR BELAKANG (2026-09-30)
---------------------------
`pasien.nomor_ktp` punya `UNIQUE INDEX ux_pasien_nomor_ktp` (migrasi
20260917_0100). MySQL memperbolehkan BANYAK baris ber-NULL di unique index —
itulah sebabnya NIK kosong WAJIB disimpan NULL, bukan string.

Tapi kolom ini menerima teks bebas sampai 30 karakter tanpa validasi apa pun.
Saat diperiksa, DB dev sudah memuat satu pasien ber-`nomor_ktp = '0'` — hasil
ketikan manual, bukan data seed. `'0'` adalah nilai BIASA di mata unique index:
pasien pertama tanpa KTP tersimpan `'0'`, **pasien kedua langsung ditolak**
dengan pesan "NIK sudah terdaftar atas pasien lain" — padahal petugas merasa
tidak mengisi apa pun. Gejalanya menyesatkan, penyebabnya tak terlihat.

Ini nyata di klinik: anak belum tentu punya KTP, dan lansia yang tidak membawa
KTP tetap dilayani.

KEPUTUSAN dr. Hansen (2026-09-30): normalisasi LUNAK.
  - Penanda kosong ('0', '000', '-', '--', spasi, kosong) -> None (NULL)
  - Selain itu diterima APA ADANYA, hanya dirapikan spasi/pemisah
  - TIDAK ADA validasi panjang. Tidak ada pendaftaran yang gagal karena bentuk
    NIK. Kalau petugas terbiasa mengetik '0', sistem yang membereskan.

Dipakai di SEMUA jalur tulis & banding NIK:
  - pasien_service.register_pasien_baru      (daftar baru)
  - pasien_service.update_pasien             (edit)
  - pasien_service.find_duplicate_candidates (banding saat daftar)
  - audit_pasien_service.scan                (kunci blocking duplikat)

⚠ Kalau menambah jalur tulis baru ke `nomor_ktp`, LEWATKAN lewat sini.
   `scripts/cek_nik.py` memeriksa hal itu dan akan GAGAL kalau ada yang lewat.
"""
from typing import Optional

# Karakter pemisah yang biasa diketik petugas di dalam NIK: "3578-1234 5678 9012"
_BUANG = " .-_/–—\t"

# Bentuk yang BUKAN NIK — hanya penanda "tidak ada / tidak dibawa".
# Dibandingkan SETELAH pemisah dibuang, jadi '0-0-0' dan '- -' ikut tertangkap.
_PENANDA_KOSONG = {"", "0", "00", "000", "0000", "-", "x", "xx", "xxx", "n", "na"}


def normalisasi_nik(raw) -> Optional[str]:
    """Kembalikan NIK bersih, atau None kalau nilainya berarti 'tidak ada'.

    >>> normalisasi_nik("")            is None
    True
    >>> normalisasi_nik("   ")         is None
    True
    >>> normalisasi_nik("0")           is None
    True
    >>> normalisasi_nik("000")         is None
    True
    >>> normalisasi_nik("-")           is None
    True
    >>> normalisasi_nik("0-0-0")       is None
    True
    >>> normalisasi_nik(None)          is None
    True
    >>> normalisasi_nik("3578123456789012")
    '3578123456789012'
    >>> normalisasi_nik(" 3578-1234 5678 9012 ")
    '3578123456789012'
    >>> normalisasi_nik("A1")
    'A1'

    Catatan: '0' tunggal dianggap penanda kosong. Tidak ada NIK sah yang
    terdiri dari satu angka nol, jadi tidak ada data benar yang hilang.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    # Buang pemisah agar "3578-1234 5678 9012" == "3578123456789012" —
    # tanpa ini, NIK yang sama diketik dua gaya lolos dari unique index.
    for ch in _BUANG:
        s = s.replace(ch, "")
    if s.lower() in _PENANDA_KOSONG:
        return None
    return s
