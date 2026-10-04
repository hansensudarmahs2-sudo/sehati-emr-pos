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
from app.services.clinical_export_service import (  # noqa: F401
    KOLOM_UANG,  # noqa: E402
    KOLOM_TERLARANG, ClinicalExportService, KolomTerlarangError, pagar_kolom,
)

PREFIKS_UJI = "ZZ UJI KLINIS"
_lulus, _gagal = 0, 0


def _faktorial(n: int) -> int:
    h = 1
    for i in range(2, n + 1):
        h *= i
    return h


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
    # ⚠ Uji ini TIDAK BERARTI kalau pasiennya sedikit, dan dulu ia berteriak
    # serigala. Untuk n pasien, peluang permutasi acak kebetulan sama dengan
    # urutan id adalah 1/n! — jadi n=1 SELALU "gagal", n=2 gagal separuh waktu,
    # n=3 sepertiga. Di DB dev yang hanya berisi beberapa pasien uji, ia melaporkan
    # kebocoran privasi yang tidak ada (terbukti 2026-10-04: 2 pasien, pid memang
    # dari `secrets`, kebetulan terurut). Pemeriksa privasi yang sering salah
    # melatih orang mengabaikannya — persis yang tidak boleh terjadi di berkas ini.
    #
    # Ambang 8 dipilih supaya peluang salah-alarm < 1/40320.
    n = len(peta1)
    if n < 8:
        print(f"  ~ pid TIDAK mencerminkan urutan id_pasien — TIDAK DAPAT DIUJI"
              f"\n      hanya {n} pasien; peluang kebetulan terurut 1/{_faktorial(n)}."
              f" Butuh >= 8 pasien agar berarti.")
    else:
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



# ------------------------------------------------------ I. Tahap B
def bagian_i(db):
    """Tahap B — tindakan, resep, racikan (+bahan), followup.

    Fokusnya BUKAN mengulang pagar identitas (sudah diuji di A/D), melainkan
    keputusan yang khusus milik Tahap B: paket klinis TIDAK BOLEH memuat angka
    uang. Kolom harga di `kunjungan_racikan*` duduk tepat di sebelah kolom dosis,
    jadi menambahkannya ke SELECT hanya butuh satu kata dan tidak akan terlihat
    salah saat ditulis.
    """
    from app.services.clinical_export_service import KolomUangError

    print("\nI. Tahap B — tindakan / resep / racikan / followup\n")
    svc = ClinicalExportService(db)
    svc.sinkron_pseudonim()

    TAHAP_B = ("clinical_tindakan", "clinical_resep", "clinical_racikan",
               "clinical_racikan_bahan", "clinical_followup")
    terdaftar = {e["name"] for e in svc.REGISTRY}
    cek("5 dataset Tahap B terdaftar di REGISTRY",
        set(TAHAP_B) <= terdaftar,
        f"kurang: {sorted(set(TAHAP_B) - terdaftar)}" if not set(TAHAP_B) <= terdaftar
        else "tindakan, resep, racikan, racikan_bahan, followup")

    rusak = []
    for e in svc.REGISTRY:
        try:
            getattr(svc, e["method"])(None, None)
        except Exception as ex:
            rusak.append(f"{e['name']}: {type(ex).__name__}")
    cek("Semua dataset (A+B) bisa dijalankan tanpa error",
        not rusak, "; ".join(rusak) if rusak else f"{len(svc.REGISTRY)} dataset")

    # --- pagar uang, DUA ARAH ---
    bersih = [{"pid": "PX1", "nama_snapshot": "Tretinoin", "dosis_per_unit": 0.025}]
    try:
        pagar_kolom("uji_b", bersih)
        lolos_bersih = True
    except Exception:
        lolos_bersih = False
    cek("Baris klinis tanpa uang LOLOS pagar", lolos_bersih,
        "pagar tidak boleh menjegal dosis/satuan")

    ditolak = []
    for k in ("harga_satuan", "subtotal", "biaya_racik", "total", "hpp_satuan"):
        try:
            pagar_kolom("uji_b", [{"pid": "PX1", k: 50000}])
        except KolomUangError:
            ditolak.append(k)
    cek("Kolom uang DITOLAK pagar (5 nama diuji)",
        len(ditolak) == 5,
        f"ditolak: {ditolak}" if len(ditolak) == 5
        else f"BOCOR, hanya ditolak: {ditolak}")

    # --- followup: sinyal drop case harus bisa terbaca ---
    rows_fu = svc.followup(None, None)
    kolom_fu = set(rows_fu[0].keys()) if rows_fu else set()
    cek("followup memuat `status` (sinyal drop case)",
        not rows_fu or "status" in kolom_fu,
        "NO_ANSWER / CANCELLED = pasien hilang tanpa kontrol; tanpa kolom ini "
        "analis tak bisa bedakan sembuh dari menghilang")
    cek("followup memakai pid, BUKAN id_pasien",
        not rows_fu or ("pid" in kolom_fu and "id_pasien" not in kolom_fu),
        f"kolom: {sorted(kolom_fu)}" if rows_fu else "tidak ada baris followup")

    # --- racikan_bahan: dosis ikut, harga tidak ---
    rows_b = svc.racikan_bahan(None, None)
    if rows_b:
        kb = set(rows_b[0].keys())
        cek("racikan_bahan memuat dosis & kekuatan",
            {"dosis_per_unit", "satuan_dosis", "kekuatan_snapshot"} <= kb)
        cek("racikan_bahan TIDAK memuat harga", not (kb & KOLOM_UANG),
            f"kolom: {sorted(kb)}")
    else:
        print("  ~ racikan_bahan tidak diuji — tidak ada baris di DB ini")


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
            bagian_i(db)
        finally:
            print(f"\n   Bersih-bersih: {_bersihkan(db)} pasien uji dihapus.")
        print(f"\nHASIL: {_lulus} lulus, {_gagal} gagal")
        return 1 if _gagal else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
