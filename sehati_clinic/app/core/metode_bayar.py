"""Metode bayar & refund yang SAH — SATU daftar (Audit T4-8, 2026-10-16).

Tutup kasir hanya menghitung metode di daftar ini. Dulu server menerima teks apa pun
(route hanya `.upper()`): POST rakitan `metode_bayar=GRATIS` atau `TUKAR` membuat transaksi
BAYAR yang masuk omzet tapi tidak diharapkan laci mana pun — uangnya bisa hilang tanpa
selisih tutup kasir; refund ber-metode aneh mengurangi omzet tanpa mengurangi laci.

`TUKAR` BUKAN metode yang boleh dipilih orang: ia hanya ditulis langsung oleh
`retur_pasien_service` (kredit tukar yang saling meniadakan), tidak pernah lewat form.

Menambah metode baru: tambahkan di sini, lalu periksa layar tutup kasir & laporan per metode.
"""

METODE_KANONIK = ["TUNAI", "QRIS", "DEBIT", "KREDIT", "TRANSFER"]


def metode_sah(metode) -> str:
    """Normalisasi (spasi, huruf besar) lalu pastikan ada di daftar → nama metode.

    ValueError bila tidak dikenal — pemanggil menerjemahkannya ke pesan yang sesuai.
    """
    m = (metode or "").strip().upper()
    if m not in METODE_KANONIK:
        raise ValueError(
            f"Metode '{metode}' tidak dikenal — pilih salah satu: {', '.join(METODE_KANONIK)}.")
    return m
