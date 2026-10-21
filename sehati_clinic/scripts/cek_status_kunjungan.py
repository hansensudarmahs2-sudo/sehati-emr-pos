"""Pemeriksa "bayar dulu" tahap 1 — label `kunjungan.status_antrian` vs isi kunjungan.

HANYA MEMBACA. Tidak menulis, tidak commit (Ruling 11, bayar dulu T1-8).

Kenapa ini perlu ada
--------------------
Sejak tahap 1, status kunjungan adalah RINGKASAN dari isinya (tindakan, tagihan, obat),
dihitung satu fungsi: `app/services/_status_kunjungan.py`. Antrian perawat/kasir/apotek
membaca ISI, bukan label — jadi label yang basi tidak menyembunyikan pasien dari meja
mana pun, tapi ia tetap dibaca laporan, dashboard FO, dan penjaga tutup kasir. Label basi
hanya mungkin lahir dari (a) baris lama sebelum tahap 1 yang tak pernah mengalami
kejadian penghitung-ulang, atau (b) penulis status baru yang menulis `status_antrian`
langsung tanpa memanggil `hitung_ulang_status` (pemindai kode di
`tests/integration/test_bayar_dulu_tahap1.py` menjaga yang ini).

Yang dibandingkan
-----------------
Untuk setiap kunjungan pada tanggal itu yang bukan BATAL: `status_antrian` tersimpan vs
`status_seharusnya()`. Kunjungan yang `status_seharusnya`-nya None (belum berisi apa pun /
pra-SOAP) sengaja dilewati — memang tidak disentuh penghitung.

Perbaikan label basi TIDAK dilakukan di sini; dr. Hansen memutuskan saat deploy
berdasarkan keluaran ini.

Jalankan dari `sehati_clinic/`:  python3 -m scripts.cek_status_kunjungan [--tanggal YYYY-MM-DD] [--hari N]
Di laptop:  docker compose ... exec sehati-app python -m scripts.cek_status_kunjungan
Kode keluar 1 bila ada selisih.
"""
import argparse
import sys
from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from app.db.models import Kunjungan
from app.db.session import SessionLocal
from app.services._status_kunjungan import status_seharusnya


def periksa(db, tanggal: date) -> list:
    """Selisih (id_kunjungan, status_tersimpan, status_seharusnya) untuk kunjungan
    bukan-BATAL pada `tanggal`. Hanya membaca."""
    baris = db.execute(
        select(Kunjungan.id_kunjungan, Kunjungan.status_antrian)
        .where(func.date(Kunjungan.tgl_kunjungan) == tanggal)
        .where(Kunjungan.status_antrian != "BATAL")
        .order_by(Kunjungan.id_kunjungan)
    ).all()
    selisih = []
    for id_kunjungan, status in baris:
        tersimpan = getattr(status, "value", status)
        seharusnya = status_seharusnya(db, id_kunjungan)
        if seharusnya is not None and seharusnya != tersimpan:
            selisih.append((id_kunjungan, tersimpan, seharusnya))
    return selisih


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tanggal", help="YYYY-MM-DD (default: hari ini)")
    # Review akhir tahap 1 (M7): sebelum deploy, label basi dari hari-hari sebelumnya yang
    # perlu dilihat — satu tanggal saja tidak cukup. Tetap HANYA membaca.
    ap.add_argument("--hari", type=int, default=1,
                    help="periksa N hari terakhir sampai --tanggal (default 1 = tanggal itu saja)")
    args = ap.parse_args()
    akhir = (datetime.strptime(args.tanggal, "%Y-%m-%d").date()
             if args.tanggal else date.today())
    n_hari = max(1, args.hari)
    daftar_tanggal = [akhir - timedelta(days=i) for i in range(n_hari - 1, -1, -1)]

    db = SessionLocal()
    try:
        rentang = (f"{daftar_tanggal[0]} s/d {akhir}" if n_hari > 1 else f"{akhir}")
        print(f"PEMERIKSA: status kunjungan vs isi — {rentang}\n")
        total = 0
        for tanggal in daftar_tanggal:
            selisih = periksa(db, tanggal)
            for id_k, tersimpan, seharusnya in selisih:
                print(f"  ✗ {tanggal} kunjungan #{id_k}: tersimpan {tersimpan} · "
                      f"seharusnya {seharusnya}")
            total += len(selisih)
        print(f"\nHASIL: {total} selisih")
        return 1 if total else 0
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    sys.exit(main())
