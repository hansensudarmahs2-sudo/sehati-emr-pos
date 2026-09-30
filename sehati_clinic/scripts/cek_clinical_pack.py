"""Pemeriksa paket klinis — yang dijaga BUKAN "berkasnya terbentuk", tapi
"tidak ada identitas pasien yang lolos".

Bahaya yang dijaga, dari yang paling buruk:
  1. Nama / no_rm / NIK / alamat / telepon / tgl_lahir lolos ke paket. Paket ini
     keluar dari klinik. Kalau satu kolom saja lolos, penyamaran sia-sia.
  2. `pid` BERUBAH antar ekspor. Tidak ada error, berkas tetap terbentuk, angka
     tetap masuk akal — hanya seluruh analisis longitudinal jadi salah.
  3. Pasien yang digabungkan muncul sebagai DUA pid. Kasus berulangnya terpecah,
     drop case palsu.
  4. Draf SOAP (belum disetujui dokter) ikut keluar sebagai rekam medis.
  5. Paket ditulis POLOS karena age/BACKUP_RECIPIENT tidak ada.
  6. Folder drop berada di cloud/repo tersinkron.

MURNI BACA untuk berkas (tidak menulis ke folder drop sama sekali), tapi
MENULIS ke DB: `sinkron_pseudonim` membuat pid, dan bagian G membuat pasien uji
lalu menghapusnya.

Jalankan dari `sehati_clinic/`:  python -m scripts.cek_clinical_pack
"""
import logging
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.db.session import engine as _eng  # noqa: E402

_eng.echo = False
for _n in ("sqlalchemy.engine", "sqlalchemy.engine.Engine"):
    logging.getLogger(_n).setLevel(logging.WARNING)

from app.services import clinical_export_batch as batch  # noqa: E402
from app.services.clinical_export_service import (  # noqa: E402
    KOLOM_TERLARANG, ClinicalExportService, KolomTerlarangError, pagar_kolom,
)

PREFIKS_UJI = "ZZ UJI KLINIS"
_lulus, _gagal = 0, 0


def cek(label, ok, detail=""):
    global _lulus, _gagal
    if ok:
        _lulus += 1
        print(f"  ✓ {label}" + (f"\n      {detail}" if detail else ""))
    else:
        _gagal += 1
        print(f"  ✗ {label}" + (f"\n      {detail}" if detail else ""))


# ------------------------------------------------------------------ A. pagar
def bagian_a():
    print("A. Pagar kolom terlarang\n")
    cek("pagar_kolom melewatkan baris bersih",
        pagar_kolom("uji", [{"pid": "PX1", "anamnesa": "gatal"}]) is not None)

    # Nama STAF harus LOLOS — diminta dr. Hansen (dokter/perawat yang menindak)
    aman = [{"pid": "PX1", "nama_dokter": "dr. A", "nama_snapshot": "Akne",
             "nama_staf_pelaksana": "B", "nama_perawat_pelaksana": "C"}]
    lolos = True
    try:
        pagar_kolom("uji", aman)
    except KolomTerlarangError:
        lolos = False
    cek("Nama STAF & nama diagnosa TIDAK ikut diblokir", lolos,
        "kecocokan PERSIS, bukan substring — 'nama' dilarang, 'nama_dokter' tidak")

    for kolom in ("nama", "no_rm", "nomor_ktp", "alamat", "nomor_telepon",
                  "tgl_lahir", "id_pasien", "email_address", "peresep_luar_nama"):
        tertangkap = False
        try:
            pagar_kolom("uji", [{"pid": "PX1", kolom: "x"}])
        except KolomTerlarangError:
            tertangkap = True
        cek(f"'{kolom}' DITOLAK", tertangkap)

    # Kunci yang hanya muncul di baris KE-2 juga harus tertangkap
    tertangkap = False
    try:
        pagar_kolom("uji", [{"pid": "PX1"}, {"pid": "PX2", "no_rm": "J01"}])
    except KolomTerlarangError:
        tertangkap = True
    cek("Kolom yang muncul hanya di baris ke-2 tetap tertangkap", tertangkap,
        "memeriksa baris pertama saja tidak cukup")


# ---------------------------------------------------------------- B. drop
def bagian_b():
    print("\nB. Folder drop\n")
    for d, harus_tolak in (
        ("/mnt/e/SehatiExport/clinical_pack", False),
        ("/mnt/e/Claude/Projects/sehati-emr-pos/exports/clinical", True),
        ("/home/x/OneDrive/klinik", True),
        ("/home/x/Dropbox/klinik", True),
    ):
        ditolak = False
        try:
            batch.periksa_drop(d)
        except batch.DropTidakAmanError:
            ditolak = True
        cek(f"{'TOLAK' if harus_tolak else 'terima'}: {d}",
            ditolak == harus_tolak)


# ------------------------------------------------------- pasien uji
def _id_staf(db) -> int:
    sid = db.execute(text("SELECT id_staf FROM master_staf ORDER BY id_staf "
                          "LIMIT 1")).scalar()
    if sid is None:
        raise RuntimeError("master_staf kosong — seed dulu DB-nya.")
    return int(sid)


def _buat_pasien_uji(db, suffix: str, status_soap: str = "FINAL") -> int:
    """Pasien uji + kunjungan + SOAP + diagnosa terkode."""
    stamp = datetime.now().strftime("%H%M%S%f")[:10]
    sid = _id_staf(db)
    db.execute(text(
        "INSERT INTO pasien (no_rm, nama, jenis_kelamin, tgl_lahir, is_active) "
        "VALUES (:rm, :nama, 'L', :tgl, 1)"),
        {"rm": f"ZK{stamp}{suffix}"[:20], "nama": f"{PREFIKS_UJI} {suffix}",
         "tgl": date(1990, 5, 17)})
    pid = int(db.execute(text("SELECT LAST_INSERT_ID()")).scalar())

    db.execute(text(
        "INSERT INTO kunjungan (id_pasien, tgl_kunjungan, status_antrian, "
        " keluhan_utama) VALUES (:p, :t, 'COMPLETED', :kel)"),
        {"p": pid, "t": datetime.now(), "kel": "UJI keluhan"})
    kid = int(db.execute(text("SELECT LAST_INSERT_ID()")).scalar())

    db.execute(text(
        "INSERT INTO pemeriksaan_klinis (id_kunjungan, id_pasien, id_staf_dokter, "
        " anamnesa, diagnosa, status_soap) "
        "VALUES (:k, :p, :s, :an, 'UJI dx', :st)"),
        {"k": kid, "p": pid, "s": sid, "an": f"UJI anamnesa {suffix}",
         "st": status_soap})
    db.execute(text(
        "INSERT INTO kunjungan_diagnosa (id_kunjungan, sistem_snapshot, "
        " kode_snapshot, nama_snapshot, is_primer, urutan) "
        "VALUES (:k, 'ICD10', 'L70.0', 'Acne vulgaris (UJI)', 1, 1)"), {"k": kid})
    db.commit()
    return pid


def _bersihkan(db) -> int:
    ids = [int(r[0]) for r in db.execute(text(
        "SELECT id_pasien FROM pasien WHERE nama LIKE :p"),
        {"p": f"{PREFIKS_UJI}%"}).all()]
    if not ids:
        return 0
    marks = ",".join(str(i) for i in ids)
    kids = [int(r[0]) for r in db.execute(text(
        f"SELECT id_kunjungan FROM kunjungan WHERE id_pasien IN ({marks})")).all()]
    if kids:
        km = ",".join(str(k) for k in kids)
        db.execute(text(f"DELETE FROM kunjungan_diagnosa WHERE id_kunjungan IN ({km})"))
    db.execute(text(f"DELETE FROM pemeriksaan_klinis WHERE id_pasien IN ({marks})"))
    db.execute(text(f"DELETE FROM kunjungan WHERE id_pasien IN ({marks})"))
    db.execute(text(f"DELETE FROM pasien_pseudonim WHERE id_pasien IN ({marks})"))
    db.execute(text(f"DELETE FROM pasien WHERE id_pasien IN ({marks})"))
    db.commit()
    return len(ids)


# ------------------------------------------------------ C-G. dengan DB
def bagian_cdefg(db):
    svc = ClinicalExportService(db)

    print("\nC. Pseudonim\n")
    info = svc.sinkron_pseudonim()
    cek("Setiap pasien punya pid",
        info["total_pid"] >= info["total_pasien"],
        f"{info['total_pid']} pid / {info['total_pasien']} pasien "
        f"({info['dibuat']} baru)")

    peta1 = svc.peta_pid()
    contoh = sorted(peta1.values())[:2]
    cek("Format pid acak 'PX' + 10 hex",
        all(v.startswith("PX") and len(v) == 12 for v in peta1.values()),
        f"contoh: {contoh}")
    cek("pid TIDAK mencerminkan urutan id_pasien",
        sorted(peta1.items()) != sorted(peta1.items(), key=lambda kv: kv[1]),
        "kalau berurutan, pemegang paket bisa menebak tanpa tabel peta")

    info2 = svc.sinkron_pseudonim()
    peta2 = svc.peta_pid()
    cek("Jalan kedua TIDAK membuat pid baru", info2["dibuat"] == 0)
    cek("pid STABIL antar pemanggilan", peta1 == peta2,
        "kalau berubah, seluruh analisis longitudinal salah TANPA GEJALA")

    print("\nD. Dataset tidak memuat identitas\n")
    uji_final = _buat_pasien_uji(db, "OK", "FINAL")
    uji_draf = _buat_pasien_uji(db, "DRAF", "DRAFT")
    svc.sinkron_pseudonim()

    total = 0
    for entry in svc.REGISTRY:
        rows = getattr(svc, entry["method"])(None, None)   # pagar jalan di dalam
        total += len(rows)
        kunci = set()
        for r in rows:
            kunci |= set(r.keys())
        cek(f"{entry['name']:26} {len(rows):>5} baris, tanpa kolom identitas",
            not (kunci & KOLOM_TERLARANG),
            f"kolom: {sorted(kunci)}" if len(rows) == 0 else "")
    cek("Paket tidak kosong", total > 0, f"{total} baris total")

    print("\nE. Hanya SOAP FINAL yang keluar\n")
    peta = svc.peta_pid()
    pid_draf = peta.get(uji_draf)
    soap = svc.soap(None, None)
    ada_draf = any(r["pid"] == pid_draf for r in soap)
    cek("SOAP status DRAFT TIDAK ikut", not ada_draf,
        "draf belum disetujui dokter — bukan rekam medis")
    cek("SOAP status FINAL ikut",
        any(r["pid"] == peta.get(uji_final) for r in soap))
    cek("Semua baris soap berstatus FINAL",
        all(r["status_soap"] == "FINAL" for r in soap))

    print("\nF. Umur, bukan tanggal lahir\n")
    profil = svc.pasien_profil()
    pf = next((r for r in profil if r["pid"] == peta.get(uji_final)), None)
    cek("Profil memuat umur_tahun & kelompok_umur",
        pf is not None and pf.get("umur_tahun") is not None
        and pf.get("kelompok_umur"),
        f"umur={pf.get('umur_tahun') if pf else '?'} "
        f"kelompok={pf.get('kelompok_umur') if pf else '?'} (lahir 1990-05-17)")
    vis = svc.visits(None, None)
    vf = next((r for r in vis if r["pid"] == peta.get(uji_final)), None)
    cek("Kunjungan memuat umur SAAT kunjungan",
        vf is not None and vf.get("umur_tahun_saat_kunjungan") is not None,
        "umur saat kejadian, bukan umur hari ini — itu yang berarti klinis")

    print("\nG. Pasien yang digabungkan = SATU pid\n")
    from app.services.audit_pasien_service import AuditPasienService
    dup = _buat_pasien_uji(db, "GD", "FINAL")
    srv = _buat_pasien_uji(db, "GS", "FINAL")
    svc.sinkron_pseudonim()
    pid_dup_asli = svc.peta_pid()[dup]
    AuditPasienService(db).gabungkan(dup, srv, "uji cek_clinical_pack",
                                     actor_id_staf=_id_staf(db))
    peta_g = svc.peta_pid()
    cek("pid duplikat menunjuk pid pasien yang bertahan",
        peta_g.get(dup) == peta_g.get(srv),
        f"dup {pid_dup_asli} -> {peta_g.get(dup)}, bertahan {peta_g.get(srv)}")

    profil_g = svc.pasien_profil()
    n_pid = [r["pid"] for r in profil_g].count(peta_g.get(srv))
    cek("Profil tidak memuat baris kembar untuk pid yang sama", n_pid == 1,
        f"{n_pid} baris untuk pid {peta_g.get(srv)}")

    pg = svc.pid_gabung()
    ada = any(r["pid_lama"] == pid_dup_asli
              and r["pid_bertahan"] == peta_g.get(srv) for r in pg)
    cek("clinical_pid_gabung mencatat pid_lama -> pid_bertahan", ada,
        "tanpa berkas ini, analis melihat satu pasien hilang tanpa penjelasan")

    print("\nH. Enkripsi WAJIB\n")
    # Bukan sekadar menghapus dari os.environ: `envval` JATUH KEMBALI ke berkas
    # .env, jadi menghapus variabel saja tidak membuktikan apa pun kalau kuncinya
    # ada di .env. Yang ditumpulkan adalah envval-nya.
    asli = batch.envval
    batch.envval = lambda nama, default="": ("" if nama == "BACKUP_RECIPIENT"
                                             else asli(nama, default))
    gagal_benar = False
    try:
        batch._recipient()
    except batch.EnkripsiTidakTersediaError:
        gagal_benar = True
    finally:
        batch.envval = asli
    cek("Tanpa BACKUP_RECIPIENT, ekspor GAGAL (bukan menulis polos)",
        gagal_benar, "gagal terang-terangan > berhasil tanpa perlindungan")

    cek("envval() menemukan kunci lewat .env (bukan hanya environ)",
        bool(batch.envval("BACKUP_RECIPIENT")),
        "kunci terbaca" if batch.envval("BACKUP_RECIPIENT")
        else "BELUM ADA di environ maupun .env — tambahkan sebelum ekspor")


def main() -> int:
    bagian_a()
    bagian_b()
    db = SessionLocal()
    try:
        nama_db = db.execute(text("SELECT DATABASE()")).scalar() or ""
        n = db.execute(text("SELECT COUNT(*) FROM pasien")).scalar() or 0
        if not ("dev" in nama_db.lower() or "test" in nama_db.lower() or n <= 50):
            print(f"\n  ⛔ BERHENTI: DB '{nama_db}' punya {n} pasien dan namanya "
                  f"bukan dev/test. Bagian C-H membuat & MENGGABUNGKAN pasien uji "
                  f"(tak bisa dibatalkan).")
            print(f"\nHASIL SEBAGIAN: {_lulus} lulus, {_gagal} gagal")
            return 1 if _gagal else 0
        print(f"\n   DB '{nama_db}', {n} pasien -> aman untuk uji tulis")
        _bersihkan(db)
        try:
            bagian_cdefg(db)
        finally:
            print(f"\n   Bersih-bersih: {_bersihkan(db)} pasien uji dihapus.")
        print(f"\nHASIL: {_lulus} lulus, {_gagal} gagal")
        return 1 if _gagal else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
