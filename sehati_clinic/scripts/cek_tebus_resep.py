"""Pemeriksa cepat R2–R4 (apotek kanal penebusan resep) — TANPA membuat data.

Yang diuji:
  1. Pagar validasi `beli_produk_lengkap` untuk tiap jenis — semuanya melempar
     HTTPException SEBELUM ada tulisan ke DB, jadi aman dijalankan kapan saja.
  2. `ApotekService.list_resep_belum_ditebus` — murni baca.

Jalankan dari `sehati_clinic/`:  python -m scripts.cek_tebus_resep
"""
from fastapi import HTTPException

from app.db.session import SessionLocal
from app.services.apotek_service import ApotekService
from app.services.kunjungan_service import KunjunganService


def _harus_ditolak(label, fn):
    try:
        fn()
    except HTTPException as e:
        print(f"  ✓ {label}\n      ditolak: {e.detail}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ {label}\n      error TAK TERDUGA: {type(e).__name__}: {e}")
        return False
    print(f"  ✗ {label}\n      TIDAK ditolak — pagar tidak bekerja")
    return False


def main() -> None:
    db = SessionLocal()
    try:
        ks = KunjunganService(db)
        aps = ApotekService(db)

        # Pasien mana pun yang ada, cuma untuk melewati validasi pertama.
        from app.db.models import Pasien
        from sqlalchemy import select
        pasien = db.execute(
            select(Pasien).where(Pasien.is_active.is_(True)).limit(1)
        ).scalars().first()
        if pasien is None:
            print("Tidak ada pasien aktif — lewati.")
            return
        print(f"Pasien uji: {pasien.nama} ({pasien.no_rm}) id={pasien.id_pasien}\n")

        produk_dummy = [{"id_produk": 1, "qty": 1}]
        ok = []

        print("PAGAR VALIDASI (tidak menulis apa pun ke DB):")
        ok.append(_harus_ditolak(
            "RESEP_LUAR tanpa nama peresep",
            lambda: ks.beli_produk_lengkap(
                id_pasien=pasien.id_pasien, produk_list=produk_dummy, id_staf_fo=1,
                jenis_kunjungan="RESEP_LUAR")))
        ok.append(_harus_ditolak(
            "RESEP_ONLINE tanpa dokter internal",
            lambda: ks.beli_produk_lengkap(
                id_pasien=pasien.id_pasien, produk_list=produk_dummy, id_staf_fo=1,
                jenis_kunjungan="RESEP_ONLINE")))
        ok.append(_harus_ditolak(
            "TEBUS_LANJUT tanpa kunjungan asal",
            lambda: ks.beli_produk_lengkap(
                id_pasien=pasien.id_pasien, produk_list=produk_dummy, id_staf_fo=1,
                jenis_kunjungan="TEBUS_LANJUT")))
        ok.append(_harus_ditolak(
            "TEBUS_LANJUT dengan kunjungan asal milik orang lain / tidak ada",
            lambda: ks.beli_produk_lengkap(
                id_pasien=pasien.id_pasien, produk_list=produk_dummy, id_staf_fo=1,
                jenis_kunjungan="TEBUS_LANJUT", id_kunjungan_asal=999999)))
        ok.append(_harus_ditolak(
            "jenis_kunjungan ngawur",
            lambda: ks.beli_produk_lengkap(
                id_pasien=pasien.id_pasien, produk_list=produk_dummy, id_staf_fo=1,
                jenis_kunjungan="NGAWUR")))

        print("\nRESEP BELUM DITEBUS (murni baca):")
        total = 0
        for p in db.execute(select(Pasien).where(Pasien.is_active.is_(True))).scalars().all():
            daftar = aps.list_resep_belum_ditebus(p.id_pasien)
            if not daftar:
                continue
            total += len(daftar)
            print(f"  {p.nama} ({p.no_rm}):")
            for d in daftar:
                tanda = " ⚠ KEDALUWARSA" if d["kedaluwarsa"] else ""
                print(f"    - resep#{d['id_resep']} {d['nama_produk']} x{d['qty']:g} "
                      f"· kunjungan#{d['id_kunjungan']} · {d['umur_hari']} hari"
                      f"{tanda} · stok {d['stok_terkini']:g}")
        if total == 0:
            print("  (tidak ada resep PENDING yang menggantung — wajar kalau semua "
                  "kunjungan uji sudah dibayar)")

        print(f"\nHASIL PAGAR: {sum(ok)}/{len(ok)} benar")
    finally:
        db.close()


if __name__ == "__main__":
    main()
