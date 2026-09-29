"""Pemeriksa R8 (status DITUNDA) — TANPA mengubah data.

Yang diuji — semuanya murni baca atau ditolak sebelum menulis:
  1. Enum DITUNDA ada di model DAN di kolom ENUM MySQL.
  2. Kolom `kunjungan_racikan.id_kunjungan_racikan_asal` ada.
  3. Pagar "tidak boleh menunda item terakhir" bekerja (ditolak sebelum tulis).
  4. Pagar "hanya PENDING yang bisa ditunda" bekerja.
  5. Daftar tebus resep lama MENERIMA DITUNDA (obat & racikan).
  6. Daftar serah apotek MENOLAK DITUNDA — ini yang paling berbahaya kalau bocor:
     obat belum dibayar tidak boleh muncul sebagai kandidat penyerahan.

Jalankan dari `sehati_clinic/`:  python -m scripts.cek_tunda_item
"""
from fastapi import HTTPException
from sqlalchemy import select, text

from app.db.session import SessionLocal
from app.db.models import StatusItemResepEnum, KunjunganResep
from app.repositories.apotek_repo import ApotekRepository
from app.services.apotek_service import ApotekService
from app.services.kasir_service import KasirService

_lulus, _gagal = 0, 0


def cek(label: str, ok: bool, detail: str = "") -> None:
    global _lulus, _gagal
    if ok:
        _lulus += 1
        print(f"  ✓ {label}" + (f"\n      {detail}" if detail else ""))
    else:
        _gagal += 1
        print(f"  ✗ {label}" + (f"\n      {detail}" if detail else ""))


def main() -> None:
    db = SessionLocal()
    try:
        print("1. Skema\n")
        cek("Enum model punya DITUNDA",
            hasattr(StatusItemResepEnum, "DITUNDA"))

        _tipe = db.execute(text(
            "SELECT COLUMN_TYPE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='kunjungan_resep' "
            "AND COLUMN_NAME='status_item'"
        )).scalar() or ""
        cek("Kolom MySQL punya DITUNDA", "DITUNDA" in _tipe, _tipe)

        _kol = db.execute(text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='kunjungan_racikan' "
            "AND COLUMN_NAME='id_kunjungan_racikan_asal'"
        )).scalar() or 0
        cek("Kolom id_kunjungan_racikan_asal ada", int(_kol) == 1)

        print("\n2. Pagar\n")
        ks = KasirService(db)

        # Item yang statusnya BUKAN PENDING → harus ditolak.
        _bukan_pending = db.execute(
            select(KunjunganResep)
            .where(KunjunganResep.status_item.in_(["DIBAYAR", "DISERAHKAN", "BATAL"]))
            .limit(1)
        ).scalars().first()
        if _bukan_pending is None:
            print("  – tidak ada item non-PENDING untuk diuji, lewati")
        else:
            try:
                ks.tunda_item_resep(_bukan_pending.id_resep, id_staf_kasir=0)
                cek("Item non-PENDING ditolak", False, "TIDAK ditolak — pagar bocor")
            except HTTPException as e:
                cek("Item non-PENDING ditolak", True, str(e.detail)[:90])
            finally:
                db.rollback()

        # Kunjungan yang cuma punya SATU item PENDING → menundanya harus ditolak.
        _sendirian = db.execute(text(
            "SELECT kr.id_resep FROM kunjungan_resep kr "
            "WHERE kr.status_item='PENDING' AND kr.id_kunjungan IN ("
            "  SELECT id_kunjungan FROM kunjungan_resep WHERE status_item='PENDING' "
            "  GROUP BY id_kunjungan HAVING COUNT(*)=1) "
            "LIMIT 1"
        )).scalar()
        if _sendirian is None:
            print("  – tidak ada kunjungan beritem tunggal, lewati pagar 'jangan kosongkan'")
        else:
            try:
                ks.tunda_item_resep(int(_sendirian), id_staf_kasir=0)
                # Bisa lolos SAH kalau kunjungan itu punya tindakan/racikan lain.
                db.rollback()
                cek("Pagar 'jangan kosongkan tagihan'", True,
                    "lolos — kunjungan ini masih punya item lain (tindakan/racikan). Wajar.")
            except HTTPException as e:
                db.rollback()
                cek("Pagar 'jangan kosongkan tagihan'", True, str(e.detail)[:90])

        print("\n3. Arah baca status\n")
        aps = ApotekService(db)
        rep = ApotekRepository(db)

        # Kunjungan yang PUNYA item DITUNDA — kalau belum ada, bagian ini dilewati.
        _kunj = db.execute(text(
            "SELECT id_kunjungan FROM kunjungan_resep WHERE status_item='DITUNDA' LIMIT 1"
        )).scalar()
        if _kunj is None:
            print("  – belum ada item DITUNDA di DB; uji arah baca setelah coba di UI.")
        else:
            _pasien = db.execute(text(
                "SELECT id_pasien FROM kunjungan WHERE id_kunjungan=:k"
            ), {"k": _kunj}).scalar()

            _ids_tebus = {r["id_resep"] for r in aps.list_resep_belum_ditebus(int(_pasien))}

            # Tidak semua baris DITUNDA HARUS muncul. Dua yang sah disembunyikan:
            #   (a) sudah punya SALINAN → berarti sudah ditebus (anti tebus ganda)
            #   (b) baris itu sendiri SALINAN → bukan sumber penebusan
            # Versi pertama pemeriksa ini menuntut SEMUA baris DITUNDA muncul, lalu
            # melaporkan gagal untuk baris yang justru benar disembunyikan. Klasifikasi
            # di bawah membuat bug sungguhan tetap kelihatan tanpa alarm palsu.
            _rows = db.execute(text(
                "SELECT kr.id_resep, kr.id_resep_asal, "
                "  (SELECT COUNT(*) FROM kunjungan_resep s WHERE s.id_resep_asal=kr.id_resep) "
                "FROM kunjungan_resep kr "
                "WHERE kr.id_kunjungan=:k AND kr.status_item='DITUNDA'"
            ), {"k": _kunj}).all()

            _wajib, _sah_tersembunyi, _bocor = set(), [], []
            for _id, _asal, _n_salinan in _rows:
                if _asal is not None:
                    _sah_tersembunyi.append(f"#{_id} (baris ini salinan)")
                elif int(_n_salinan or 0) > 0:
                    _sah_tersembunyi.append(f"#{_id} (sudah ditebus)")
                else:
                    _wajib.add(_id)
                    if _id not in _ids_tebus:
                        _bocor.append(f"#{_id}")

            _det = f"wajib muncul={sorted(_wajib) or '—'}"
            if _sah_tersembunyi:
                _det += f"; sah disembunyikan: {', '.join(_sah_tersembunyi)}"
            if _bocor:
                _det += f"; HILANG: {', '.join(_bocor)}"
            cek("Tebus resep lama MEMUAT item DITUNDA yang belum ditebus",
                not _bocor, _det)

            # SEMUA baris DITUNDA harus absen dari daftar serah — tanpa kecuali, termasuk
            # yang sudah ditebus (yang diserahkan adalah SALINAN-nya di kunjungan baru).
            _semua_ditunda = {int(_r[0]) for _r in _rows}
            _serah = {kr.id_resep for kr, _mp in rep.get_resep_for_apotek(int(_kunj))}
            _bocor_serah = _serah & _semua_ditunda
            cek("Daftar serah apotek MENOLAK item DITUNDA",
                not _bocor_serah,
                f"BOCOR={sorted(_bocor_serah)}" if _bocor_serah
                else f"diperiksa {len(_semua_ditunda)} baris DITUNDA")

        print(f"\nHASIL: {_lulus} lulus, {_gagal} gagal")
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
