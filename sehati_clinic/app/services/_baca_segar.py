"""Tutup transaksi BACA sebelum mengunci — SATU tempat untuk pola Audit T4-1/T4-2/T4-5/T4-6.

Kenapa ada: MySQL REPEATABLE-READ. SELECT biasa membaca POTRET yang dibuat pada pembacaan
konsisten PERTAMA transaksi — di route itu `get_user_from_cookie`, jauh sebelum kunci baris
didapat. Permintaan kedua yang menunggu kunci (bayar ganda, retur ganda, void vs refund) lalu
memutuskan dari potret lama: "belum dibayar", "belum diretur", "belum ada refund". Kunci saja
TIDAK cukup. Dengan menutup transaksi lebih dulu, potret baru dibuat oleh SELECT biasa pertama
SESUDAH kunci (SELECT … FOR UPDATE bukan pembacaan konsisten, tidak membuat potret).

⚠ KONTRAK — fungsi ini MEN-COMMIT pekerjaan pemanggil yang sudah di-flush. Panggil HANYA di
awal operasi tulis yang dipanggil langsung dari route, sebelum apa pun ditulis. Terbukti
2026-10-16: sebuah test yang mengubah kunjungan lalu memanggil `tutup_kasir` dengan sesi
ber-commit SUNGGUHAN membuat perubahan test itu permanen di DB dev. Perubahan yang belum
di-flush ditolak di sini (RuntimeError); yang SUDAH di-flush tidak bisa dideteksi — jangan
panggil operasi-operasi ini di tengah transaksi lain.

⚠ Sesudahnya: jangan sisipkan SELECT biasa sebelum kunci pertama — SELECT itu akan membuat
potret baru yang lagi-lagi mendahului kunci.

Pemakai: `KasirService.proses_bayar`, `KasirService._kunci_untuk_void` (kedua jalur void),
`KasirService.refund_item_tertunda`, `ReturPasienService.buat_retur`,
`KasirClosingService.tutup_kasir`.
"""
from sqlalchemy.orm import Session


def mulai_baca_segar(db: Session) -> None:
    if db.new or db.dirty or db.deleted:
        raise RuntimeError(
            "mulai_baca_segar: sesi masih punya perubahan yang belum ditulis — operasi ini "
            "men-commit di awal dan tidak boleh dipanggil di tengah transaksi lain.")
    db.commit()
    # Sesi memakai expire_on_commit=False: objek yang sudah dimuat harus dibaca ulang.
    db.expire_all()
