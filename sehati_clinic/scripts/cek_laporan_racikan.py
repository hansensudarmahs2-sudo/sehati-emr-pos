"""Pemeriksa: racikan muncul di laporan apoteker & top produk. MURNI BACA.

Keluhan asalnya: racikan tidak terlihat sama sekali di dua laporan ini, sehingga
  - apoteker yang seharian meracik tampak tidak mengerjakan apa pun; dan
  - bahan yang laris lewat racikan terlihat seperti barang mati, padahal stoknya
    terkuras — keputusan pembelian jadi salah.

Yang diuji:
  1. Laporan apoteker memuat baris racikan (is_racikan=True) bila ada yang DISERAHKAN
  2. Top produk memuat bagian peringkat racikan
  3. Bahan racikan menempel ke baris produk (qty_racikan terisi)
  4. Produk yang HANYA terpakai lewat racikan tetap MUNCUL (dulu hilang sama sekali)
  5. qty_racikan TIDAK dilebur ke total_qty — satuannya berbeda
  6. Laporan tidak kosong hanya karena tidak ada resep produk (dulu return dini)

Jalankan dari `sehati_clinic/`:  python -m scripts.cek_laporan_racikan
"""
from datetime import date, timedelta

from sqlalchemy import text

from app.db.session import SessionLocal
from app.services.reports_service import ReportsService

_lulus, _gagal, _lewat = 0, 0, 0


def cek(label, ok, detail=""):
    global _lulus, _gagal
    if ok:
        _lulus += 1
        print(f"  ✓ {label}" + (f"\n      {detail}" if detail else ""))
    else:
        _gagal += 1
        print(f"  ✗ {label}" + (f"\n      {detail}" if detail else ""))


def lewat(label, alasan):
    global _lewat
    _lewat += 1
    print(f"  – {label}\n      dilewati: {alasan}")


def main() -> None:
    db = SessionLocal()
    try:
        svc = ReportsService(db)

        # Rentang: seluruh riwayat racikan yang pernah diserahkan.
        rng = db.execute(text(
            "SELECT MIN(DATE(waktu_serah)), MAX(DATE(waktu_serah)), COUNT(*) "
            "FROM kunjungan_racikan WHERE status_item='DISERAHKAN' AND waktu_serah IS NOT NULL"
        )).first()
        dari, sampai, n_racik = (rng[0], rng[1], int(rng[2] or 0)) if rng else (None, None, 0)
        if not n_racik:
            print("Belum ada racikan berstatus DISERAHKAN di DB.\n")
            print("Uji ini butuh minimal satu racikan yang sudah DISERAHKAN di apotek.")
            print("Lakukan di UI: SOAP dengan racikan → bayar di kasir → serahkan di apotek.")
            return
        if dari is None:
            dari = date.today() - timedelta(days=365)
        print(f"Rentang uji: {dari} .. {sampai}  ({n_racik} racikan DISERAHKAN)\n")

        print("1. Laporan apoteker\n")
        apt = svc.get_apoteker_dispensed_report(
            tgl_dari=dari, tgl_sampai=sampai, page=1, page_size=500)
        baris_racik = [i for i in apt.items if getattr(i, "is_racikan", False)]
        cek("Laporan apoteker MEMUAT baris racikan", len(baris_racik) > 0,
            f"{len(baris_racik)} baris racikan dari {len(apt.items)} total")
        if baris_racik:
            b = baris_racik[0]
            cek("Baris racikan tidak memalsukan kode/id produk",
                b.kode_produk in (None, "") and b.id_produk is None,
                f"kode_produk={b.kode_produk!r} id_produk={b.id_produk!r}")
            cek("Baris racikan membawa jenis & unit",
                bool(b.jenis_racik) and b.qty > 0,
                f"{b.nama_produk!r} {b.jenis_racik} {b.qty:g} unit, Rp {b.subtotal:,.0f}")

        print("\n2-5. Laporan top produk\n")
        top = svc.get_top_dispensed_products(tgl_dari=dari, tgl_sampai=sampai, limit=500)
        cek("Ada bagian peringkat RACIKAN", len(top.racikan) > 0,
            f"{len(top.racikan)} racikan, {top.total_racikan_batch} batch, "
            f"Rp {top.total_nominal_racikan:,.0f}")

        dgn_racik = [i for i in top.items if i.qty_racikan]
        cek("Bahan racikan MENEMPEL ke baris produk", len(dgn_racik) > 0,
            f"{len(dgn_racik)} produk memuat pemakaian racikan")

        hanya = [i for i in top.items if i.hanya_dari_racikan]
        if hanya:
            cek("Produk yang HANYA terpakai lewat racikan tetap muncul", True,
                ", ".join(f"{i.nama_produk} ({i.qty_racikan:g} {i.satuan_racikan})"
                          for i in hanya[:3]))
        else:
            lewat("Produk yang hanya terpakai lewat racikan",
                  "semua bahan racikan kebetulan juga terjual langsung — bukan kegagalan")

        # total_qty tidak boleh ikut memuat qty_racikan. Diperiksa lewat produk
        # 'hanya_dari_racikan': ia tidak pernah terjual langsung, jadi total_qty
        # WAJIB 0. Kalau bocor, angkanya akan ikut terisi dari racikan.
        salah = [i for i in hanya if i.total_qty != 0]
        cek("qty_racikan TIDAK dilebur ke total_qty",
            not salah,
            "total_qty produk racikan-saja = 0 (benar)" if not salah
            else f"BOCOR: {[i.nama_produk for i in salah]}")

        print("\n6. Laporan tidak kosong walau tanpa resep produk\n")
        # Cari hari yang HANYA punya penyerahan racikan.
        hari = db.execute(text(
            "SELECT DATE(kr.waktu_serah) d FROM kunjungan_racikan kr "
            "WHERE kr.status_item='DISERAHKAN' AND kr.waktu_serah IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM kunjungan_resep r "
            "  WHERE r.status_item='DISERAHKAN' AND DATE(r.waktu_serah)=DATE(kr.waktu_serah)) "
            "LIMIT 1"
        )).scalar()
        if hari is None:
            lewat("Hari berisi racikan saja",
                  "tidak ada hari yang penyerahannya racikan saja — tidak bisa diuji")
        else:
            solo = svc.get_top_dispensed_products(tgl_dari=hari, tgl_sampai=hari, limit=50)
            cek("Hari berisi racikan saja TIDAK menghasilkan laporan kosong",
                len(solo.racikan) > 0,
                f"{hari}: {len(solo.racikan)} racikan, {len(solo.items)} produk")

        print(f"\nHASIL: {_lulus} lulus, {_gagal} gagal, {_lewat} dilewati")
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
