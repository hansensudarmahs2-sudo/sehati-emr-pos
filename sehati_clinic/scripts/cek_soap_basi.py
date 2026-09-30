"""Pemeriksa #51 — halaman SOAP basi tidak boleh menghapus data yang lahir sesudahnya.

Menguji `RacikanService.save_kunjungan_racikan` LANGSUNG di DB dalam transaksi yang
SELALU di-rollback di akhir. Tidak ada data yang tersisa.

Skenario yang diuji (racikan):
  1. Tab A menambah racikan baru → tersimpan
  2. Tab B (dimuat SEBELUM racikan tab A ada) menyimpan → racikan tab A HARUS SELAMAT
     dan dilaporkan lewat `dipertahankan`
  3. Dokter menghapus kartu di layarnya → baris itu BENAR-BENAR terhapus
     (jangan sampai perbaikan ini membuat penghapusan yang sah jadi mustahil)
  4. Simpan dua kali tanpa perubahan → ID racikan TIDAK berubah
  5. Baris DIBAYAR / DITUNDA tidak tersentuh
  6. Pemanggil tanpa `loaded_ids` (layar apotek) tetap berperilaku lama

Jalankan dari `sehati_clinic/`:  python -m scripts.cek_soap_basi
"""
from sqlalchemy import select, text

from app.db.session import SessionLocal
from app.db.models import Kunjungan
from app.db.models.racikan import KunjunganRacikan
from app.services.racikan_service import RacikanService

_lulus, _gagal = 0, 0


def cek(label, ok, detail=""):
    global _lulus, _gagal
    if ok:
        _lulus += 1
        print(f"  ✓ {label}" + (f"\n      {detail}" if detail else ""))
    else:
        _gagal += 1
        print(f"  ✗ {label}" + (f"\n      {detail}" if detail else ""))


def _kartu(nama, bahan_id, id_kr=None, unit=10):
    return {
        "id_kunjungan_racikan": id_kr,
        "id_racikan": None,
        "nama": nama,
        "jenis_racik": "KAPSUL",
        "jumlah_unit": unit,
        "aturan_pakai": "uji",
        "bahan": [{"id_produk": bahan_id, "dosis": 10, "satuan": "mg"}],
    }


def _pending(db, id_kunjungan):
    return sorted(db.execute(
        select(KunjunganRacikan.id_kunjungan_racikan).where(
            KunjunganRacikan.id_kunjungan == id_kunjungan,
            KunjunganRacikan.status_item == "PENDING",
        )
    ).scalars().all())


def main() -> None:
    db = SessionLocal()
    try:
        svc = RacikanService(db)

        kunj = db.execute(select(Kunjungan).order_by(Kunjungan.id_kunjungan.desc())
                          .limit(1)).scalars().first()
        if kunj is None:
            print("Tidak ada kunjungan — lewati.")
            return
        idk = kunj.id_kunjungan

        # Bahan uji: produk mana pun yang punya harga & kekuatan supaya hitung_spec jalan.
        pid = db.execute(text(
            "SELECT id_produk FROM master_produk "
            "WHERE is_active=1 AND harga_jual>0 AND kekuatan_nilai IS NOT NULL LIMIT 1"
        )).scalar()
        if pid is None:
            print("Tidak ada produk yang cocok untuk uji — lewati.")
            return
        print(f"Kunjungan uji #{idk}, bahan id_produk={pid}\n")

        awal = _pending(db, idk)
        print(f"PENDING sebelum uji: {awal or '—'}\n")

        print("1-2. Halaman basi TIDAK menghapus racikan yang lahir sesudahnya\n")
        # Tab B memuat halaman SEKARANG → melihat `awal`
        loaded_tab_b = list(awal)

        # Tab A menambah racikan baru (loaded_ids = awal juga, tapi ia mengirim kartu baru)
        svc.save_kunjungan_racikan(idk, [_kartu("UJI-TAB-A", pid)], loaded_ids=list(awal))
        setelah_a = _pending(db, idk)
        baru_a = [i for i in setelah_a if i not in awal]
        cek("Tab A berhasil menambah racikan", len(baru_a) == 1, f"id baru={baru_a}")

        # Tab B menyimpan — ia TIDAK tahu racikan tab A. Kartu di layarnya: kosong.
        hasil_b = svc.save_kunjungan_racikan(idk, [], loaded_ids=loaded_tab_b)
        setelah_b = _pending(db, idk)
        cek("Racikan tab A SELAMAT dari simpan tab B",
            all(i in setelah_b for i in baru_a),
            f"pending sekarang={setelah_b}")
        cek("Tab B DIBERI TAHU ada baris yang dipertahankan",
            sorted(hasil_b.get("dipertahankan") or []) == sorted(baru_a),
            f"dipertahankan={hasil_b.get('dipertahankan')}")

        print("\n3. Penghapusan yang SAH tetap bekerja\n")
        # Sekarang tab A menyimpan lagi, melihat baris miliknya, dan membuang kartunya.
        hasil_c = svc.save_kunjungan_racikan(idk, [], loaded_ids=list(baru_a))
        setelah_c = _pending(db, idk)
        cek("Kartu yang dibuang dokter BENAR-BENAR terhapus",
            not any(i in setelah_c for i in baru_a),
            f"dihapus={hasil_c.get('dihapus')} pending={setelah_c}")

        print("\n4. ID stabil — tidak berubah tiap simpan\n")
        svc.save_kunjungan_racikan(idk, [_kartu("UJI-STABIL", pid)], loaded_ids=_pending(db, idk))
        p1 = [i for i in _pending(db, idk) if i not in awal]
        # Simpan ULANG kartu yang sama, membawa identitasnya
        svc.save_kunjungan_racikan(
            idk, [_kartu("UJI-STABIL", pid, id_kr=p1[0])], loaded_ids=_pending(db, idk))
        p2 = [i for i in _pending(db, idk) if i not in awal]
        cek("ID racikan TIDAK berubah setelah simpan ulang", p1 == p2, f"{p1} -> {p2}")

        print("\n5. Baris terkunci tidak tersentuh\n")
        terkunci = db.execute(text(
            "SELECT COUNT(*) FROM kunjungan_racikan "
            "WHERE id_kunjungan=:k AND status_item IN ('DIBAYAR','BATAL','DITUNDA')"
        ), {"k": idk}).scalar() or 0
        svc.save_kunjungan_racikan(idk, [], loaded_ids=_pending(db, idk))
        terkunci2 = db.execute(text(
            "SELECT COUNT(*) FROM kunjungan_racikan "
            "WHERE id_kunjungan=:k AND status_item IN ('DIBAYAR','BATAL','DITUNDA')"
        ), {"k": idk}).scalar() or 0
        cek("Jumlah baris DIBAYAR/BATAL/DITUNDA tetap", terkunci == terkunci2,
            f"{terkunci} -> {terkunci2}")

        print("\n6. Pemanggil tanpa loaded_ids (layar apotek) berperilaku lama\n")
        svc.save_kunjungan_racikan(idk, [_kartu("UJI-LAMA", pid)])
        sisa = _pending(db, idk)
        hasil_f = svc.save_kunjungan_racikan(idk, [])      # tanpa loaded_ids
        cek("Tanpa loaded_ids: semua PENDING diganti (perilaku lama)",
            _pending(db, idk) == [] and hasil_f.get("dihapus") == len(sisa),
            f"dihapus={hasil_f.get('dihapus')} dari {len(sisa)}")

        # ------------------------------------------------------------- DIAGNOSA
        print("\n7. Diagnosa — halaman basi tidak menghapus yang lahir sesudahnya\n")
        from app.db.models.diagnosa import KunjunganDiagnosa
        from app.services.diagnosa_service import DiagnosaService

        def _dx(db, idk):
            return sorted(db.execute(
                select(KunjunganDiagnosa.id_kunjungan_diagnosa)
                .where(KunjunganDiagnosa.id_kunjungan == idk)
            ).scalars().all())

        def _chip(nama, id_kd=None):
            return {"id_kunjungan_diagnosa": id_kd, "id_diagnosa": None,
                    "sistem": None, "kode": None, "nama": nama, "is_primer": False}

        dsvc = DiagnosaService(db)
        dx_awal = _dx(db, idk)
        dx_loaded_tab_b = list(dx_awal)

        # Tab A menambah diagnosa baru
        dsvc.save_kunjungan_diagnosa(
            idk, [_chip(f"UJI-DX-A-{idk}")], loaded_ids=list(dx_awal))
        dx_setelah_a = _dx(db, idk)
        dx_baru = [i for i in dx_setelah_a if i not in dx_awal]
        cek("Tab A berhasil menambah diagnosa", len(dx_baru) == 1, f"id baru={dx_baru}")

        # Tab B menyimpan tanpa tahu diagnosa tab A
        dsvc.save_kunjungan_diagnosa(idk, [], loaded_ids=dx_loaded_tab_b)
        cek("Diagnosa tab A SELAMAT dari simpan tab B",
            all(i in _dx(db, idk) for i in dx_baru),
            f"dipertahankan={dsvc.dipertahankan}")

        # Chip yang membawa id → DIPERBARUI, bukan digandakan
        _n_sebelum = len(_dx(db, idk))
        dsvc.save_kunjungan_diagnosa(
            idk, [_chip("UJI-DX-DIUBAH", id_kd=dx_baru[0])], loaded_ids=_dx(db, idk))
        _sesudah = _dx(db, idk)
        _nama_baru = db.get(KunjunganDiagnosa, dx_baru[0]).nama_snapshot
        cek("Chip ber-id DIPERBARUI, bukan digandakan",
            dx_baru[0] in _sesudah and len(_sesudah) <= _n_sebelum
            and _nama_baru == "UJI-DX-DIUBAH",
            f"jumlah {_n_sebelum}->{len(_sesudah)}, nama={_nama_baru!r}")

        # Penghapusan yang sah tetap jalan
        dsvc.save_kunjungan_diagnosa(idk, [], loaded_ids=list(dx_baru))
        cek("Diagnosa yang dibuang dokter BENAR-BENAR terhapus",
            not any(i in _dx(db, idk) for i in dx_baru), f"sisa={_dx(db, idk)}")

        print(f"\nHASIL: {_lulus} lulus, {_gagal} gagal")
        print("(semua perubahan di-ROLLBACK — tidak ada data yang tersisa)")
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
