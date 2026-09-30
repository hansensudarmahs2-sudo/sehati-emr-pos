"""Pemeriksa laporan Kasus Terbanyak — menguji ANGKANYA, bukan tampilannya.

Laporan agregat berbahaya justru karena ia selalu terlihat masuk akal: kolom
terisi, urutan rapi, persentase berjumlah 100. Salah hitung tidak menimbulkan
error apa pun — hanya kesimpulan klinis yang keliru.

Yang diuji:
  A. Bedanya jumlah_pasien vs jumlah_kunjungan BENAR-BENAR terjadi
     (dibuktikan dengan pasien uji yang kontrol 3x untuk diagnosa yang sama)
  B. jumlah_pasien menghitung ORANG, bukan baris; kunjungan_per_pasien benar
  C. Slicer ICD10/ESTETIK memilah dengan benar & jumlahnya konsisten
  D. `hanya_primer` menyaring, dan jumlahnya tidak pernah melebihi total
  E. Pasien yang DIGABUNGKAN terhitung SATU orang, bukan dua
  F. Rentang tanggal benar-benar memotong
  G. Urutan STABIL (dua panggilan berturut memberi urutan sama)
  H. Laporan tidak memuat identitas pasien

⚠ MENULIS ke DB: membuat pasien uji "ZZ UJI DX" lalu menghapusnya. Bagian E
  MENGGABUNGKAN dua pasien uji (tak bisa dibatalkan) — karena itu menolak jalan
  di DB yang bukan dev/test.

Jalankan dari `sehati_clinic/`:  python -m scripts.cek_top_diagnosa
"""
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.db.session import engine as _eng  # noqa: E402

_eng.echo = False
for _n in ("sqlalchemy.engine", "sqlalchemy.engine.Engine"):
    logging.getLogger(_n).setLevel(logging.WARNING)

from app.services.reports_service import ReportsService  # noqa: E402

PREFIKS = "ZZ UJI DX"
KODE_A = "ZZ-A1"     # ICD10, dipakai 1 pasien x 3 kunjungan
KODE_B = "ZZ-B2"     # ESTETIK, dipakai 3 pasien x 1 kunjungan
_lulus, _gagal = 0, 0


def cek(label, ok, detail=""):
    global _lulus, _gagal
    if ok:
        _lulus += 1
        print(f"  ✓ {label}" + (f"\n      {detail}" if detail else ""))
    else:
        _gagal += 1
        print(f"  ✗ {label}" + (f"\n      {detail}" if detail else ""))


def _id_staf(db) -> int:
    sid = db.execute(text("SELECT id_staf FROM master_staf ORDER BY id_staf "
                          "LIMIT 1")).scalar()
    if sid is None:
        raise RuntimeError("master_staf kosong.")
    return int(sid)


def _pasien(db, suffix) -> int:
    stamp = datetime.now().strftime("%H%M%S%f")[:10]
    db.execute(text(
        "INSERT INTO pasien (no_rm, nama, jenis_kelamin, tgl_lahir, is_active) "
        "VALUES (:rm, :nm, 'L', '1990-01-01', 1)"),
        {"rm": f"ZD{stamp}{suffix}"[:20], "nm": f"{PREFIKS} {suffix}"})
    return int(db.execute(text("SELECT LAST_INSERT_ID()")).scalar())


def _kunjungan_dx(db, id_pasien, tgl, sistem, kode, nama, primer=True) -> int:
    db.execute(text(
        "INSERT INTO kunjungan (id_pasien, tgl_kunjungan, status_antrian) "
        "VALUES (:p, :t, 'COMPLETED')"), {"p": id_pasien, "t": tgl})
    kid = int(db.execute(text("SELECT LAST_INSERT_ID()")).scalar())
    db.execute(text(
        "INSERT INTO kunjungan_diagnosa (id_kunjungan, sistem_snapshot, "
        " kode_snapshot, nama_snapshot, is_primer, urutan) "
        "VALUES (:k, :s, :kd, :nm, :pr, 1)"),
        {"k": kid, "s": sistem, "kd": kode, "nm": nama,
         "pr": 1 if primer else 0})
    return kid


def _bersihkan(db) -> int:
    ids = [int(r[0]) for r in db.execute(text(
        "SELECT id_pasien FROM pasien WHERE nama LIKE :p"),
        {"p": f"{PREFIKS}%"}).all()]
    if not ids:
        return 0
    m = ",".join(str(i) for i in ids)
    kids = [int(r[0]) for r in db.execute(text(
        f"SELECT id_kunjungan FROM kunjungan WHERE id_pasien IN ({m})")).all()]
    if kids:
        km = ",".join(str(k) for k in kids)
        db.execute(text(f"DELETE FROM kunjungan_diagnosa WHERE id_kunjungan IN ({km})"))
    for t in ("pemeriksaan_klinis", "transaksi_kasir", "kunjungan",
              "pasien_pseudonim"):
        db.execute(text(f"DELETE FROM {t} WHERE id_pasien IN ({m})"))
    db.execute(text(f"DELETE FROM pasien WHERE id_pasien IN ({m})"))
    db.commit()
    return len(ids)


def _cari(data, kode):
    return next((i for i in data["items"]
             if i["kode_diagnosa"] == kode), None)


def main() -> int:
    db = SessionLocal()
    try:
        nama_db = db.execute(text("SELECT DATABASE()")).scalar() or ""
        n = db.execute(text("SELECT COUNT(*) FROM pasien")).scalar() or 0
        if not ("dev" in nama_db.lower() or "test" in nama_db.lower() or n <= 50):
            print(f"  ⛔ BERHENTI: DB '{nama_db}' ({n} pasien) bukan dev/test. "
                  f"Pemeriksa ini membuat & MENGGABUNGKAN pasien uji.")
            return 1
        print(f"DB '{nama_db}', {n} pasien -> aman untuk uji tulis\n")
        _bersihkan(db)

        svc = ReportsService(db)
        hari_ini = date.today()
        lama = hari_ini - timedelta(days=400)     # DI LUAR jendela default 365h

        # KODE_A: SATU pasien, TIGA kunjungan  -> pasien=1, kunjungan=3
        pa = _pasien(db, "A")
        for d in (0, 10, 20):
            _kunjungan_dx(db, pa, datetime.combine(hari_ini - timedelta(days=d),
                                                   datetime.min.time()),
                          "ICD10", KODE_A, "Uji A (medis)")
        # KODE_B: TIGA pasien, SATU kunjungan  -> pasien=3, kunjungan=3
        pb = []
        for s in ("B1", "B2", "B3"):
            p = _pasien(db, s)
            pb.append(p)
            _kunjungan_dx(db, p, datetime.combine(hari_ini, datetime.min.time()),
                          "ESTETIK", KODE_B, "Uji B (estetik)")
        # diagnosa sekunder, supaya `hanya_primer` bisa diuji
        _kunjungan_dx(db, pa, datetime.combine(hari_ini, datetime.min.time()),
                      "ICD10", "ZZ-SEK", "Uji sekunder", primer=False)
        # kunjungan LAMA, di luar jendela default
        _kunjungan_dx(db, pa, datetime.combine(lama, datetime.min.time()),
                      "ICD10", "ZZ-LAMA", "Uji lama")
        db.commit()

        dari, sampai = hari_ini - timedelta(days=364), hari_ini
        data = svc.get_top_diagnosa(dari, sampai)

        print("A. Pasien vs kunjungan BENAR-BENAR berbeda\n")
        a, b = _cari(data, KODE_A), _cari(data, KODE_B)
        cek("Diagnosa A (1 pasien, 3 kunjungan) terbaca benar",
            a and a["jumlah_pasien"] == 1 and a["jumlah_kunjungan"] == 3,
            f"pasien={a['jumlah_pasien'] if a else '?'} "
            f"kunjungan={a['jumlah_kunjungan'] if a else '?'}")
        cek("Diagnosa B (3 pasien, 3 kunjungan) terbaca benar",
            b and b["jumlah_pasien"] == 3 and b["jumlah_kunjungan"] == 3,
            f"pasien={b['jumlah_pasien'] if b else '?'} "
            f"kunjungan={b['jumlah_kunjungan'] if b else '?'}")
        cek("Kedua diagnosa punya jumlah KUNJUNGAN sama tapi PASIEN beda",
            a and b and a["jumlah_kunjungan"] == b["jumlah_kunjungan"]
            and a["jumlah_pasien"] != b["jumlah_pasien"],
            "inilah alasan dua kolom itu tidak boleh digabung jadi satu")

        print("\nB. Rasio kunjungan per pasien\n")
        cek("A (kontrol berulang) = 3.0", a and a["kunjungan_per_pasien"] == 3.0,
            f"{a['kunjungan_per_pasien'] if a else '?'}")
        cek("B (sekali datang) = 1.0", b and b["kunjungan_per_pasien"] == 1.0,
            f"{b['kunjungan_per_pasien'] if b else '?'}")

        print("\nC. Slicer medis vs estetik\n")
        d_icd = svc.get_top_diagnosa(dari, sampai, sistem="ICD10")
        d_est = svc.get_top_diagnosa(dari, sampai, sistem="ESTETIK")
        cek("Filter ICD10 memuat A, tidak memuat B",
            _cari(d_icd, KODE_A) and not _cari(d_icd, KODE_B))
        cek("Filter ESTETIK memuat B, tidak memuat A",
            _cari(d_est, KODE_B) and not _cari(d_est, KODE_A))
        cek("Semua baris hasil filter memang bersistem itu",
            all(i["sistem"] == "ICD10" for i in d_icd["items"])
            and all(i["sistem"] == "ESTETIK" for i in d_est["items"]))
        cek("ICD10 + ESTETIK = SEMUA (jumlah kunjungan)",
            d_icd["total_kunjungan"] + d_est["total_kunjungan"]
            == data["total_kunjungan"],
            f"{d_icd['total_kunjungan']} + {d_est['total_kunjungan']} "
            f"= {data['total_kunjungan']}")

        print("\nD. Diagnosa primer saja\n")
        d_pri = svc.get_top_diagnosa(dari, sampai, hanya_primer=True)
        cek("Diagnosa sekunder TIDAK muncul", not _cari(d_pri, "ZZ-SEK"))
        cek("Total primer <= total semua",
            d_pri["total_kunjungan"] <= data["total_kunjungan"],
            f"{d_pri['total_kunjungan']} <= {data['total_kunjungan']}")

        print("\nE. Pasien digabung = SATU orang\n")
        from app.services.audit_pasien_service import AuditPasienService
        # dua pasien uji baru, KEDUANYA punya diagnosa yang sama
        g1, g2 = _pasien(db, "G1"), _pasien(db, "G2")
        for p in (g1, g2):
            _kunjungan_dx(db, p, datetime.combine(hari_ini, datetime.min.time()),
                          "ICD10", "ZZ-GAB", "Uji gabung")
        db.commit()
        sebelum = _cari(svc.get_top_diagnosa(dari, sampai), "ZZ-GAB")
        AuditPasienService(db).gabungkan(g1, g2, "uji cek_top_diagnosa",
                                         actor_id_staf=_id_staf(db))
        sesudah = _cari(svc.get_top_diagnosa(dari, sampai), "ZZ-GAB")
        cek("Sebelum digabung: 2 pasien",
            sebelum and sebelum["jumlah_pasien"] == 2,
            f"{sebelum['jumlah_pasien'] if sebelum else '?'}")
        cek("Sesudah digabung: 1 pasien, kunjungan TETAP 2",
            sesudah and sesudah["jumlah_pasien"] == 1
            and sesudah["jumlah_kunjungan"] == 2,
            f"pasien={sesudah['jumlah_pasien'] if sesudah else '?'} "
            f"kunjungan={sesudah['jumlah_kunjungan'] if sesudah else '?'} "
            "— riwayat tidak hilang, hanya menyatu")

        print("\nF. Rentang tanggal memotong\n")
        cek("Kunjungan 400 hari lalu TIDAK masuk jendela 365 hari",
            not _cari(data, "ZZ-LAMA"))
        luas = svc.get_top_diagnosa(hari_ini - timedelta(days=500), hari_ini)
        cek("Ia MUNCUL saat jendela diperlebar ke 500 hari",
            bool(_cari(luas, "ZZ-LAMA")),
            "membuktikan ia memang ada, bukan sekadar tidak tersimpan")

        print("\nG. Urutan stabil\n")
        u1 = [i["kode_diagnosa"] for i in svc.get_top_diagnosa(dari, sampai)["items"]]
        u2 = [i["kode_diagnosa"] for i in svc.get_top_diagnosa(dari, sampai)["items"]]
        cek("Dua panggilan berturut memberi urutan sama", u1 == u2,
            "tanpa kunci pengurut kedua, baris berskor sama bisa bertukar dan "
            "terlihat seperti data berubah")

        print("\nH. Tidak ada identitas pasien di laporan\n")
        kunci = set()
        for i in data["items"]:
            kunci |= set(i.keys())
        haram = kunci & {"id_pasien", "nama", "no_rm", "nama_pasien",
                         "nomor_ktp", "tgl_lahir"}
        cek("Tidak ada kolom identitas", not haram,
            f"kolom: {sorted(kunci)}" if not haram else f"BOCOR: {haram}")

        print(f"\nHASIL: {_lulus} lulus, {_gagal} gagal")
        return 1 if _gagal else 0
    finally:
        try:
            print(f"   Bersih-bersih: {_bersihkan(db)} pasien uji dihapus.")
        finally:
            db.close()


if __name__ == "__main__":
    sys.exit(main())
