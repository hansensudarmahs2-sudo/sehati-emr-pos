"""Audit paket klinis yang BENAR-BENAR KELUAR — bukan kodenya, tapi berkasnya.

    python -m scripts.cek_paket_klinis_keluar                      # paket terbaru
    python -m scripts.cek_paket_klinis_keluar /path/ke/paket.age
    python -m scripts.cek_paket_klinis_keluar --kunci ~/kunci.key

KENAPA PEMERIKSA INI ADA, TERPISAH DARI cek_clinical_pack
---------------------------------------------------------
`cek_clinical_pack` menguji KODE: pagar kolom, pid stabil, SOAP draf tidak ikut.
Itu memeriksa niat. Pemeriksa INI membuka ZIP yang sudah tertulis ke folder drop
dan membaca byte-nya — satu-satunya cara memastikan yang keluar dari klinik
memang yang kita maksud. Kode benar tapi berkas salah adalah kemungkinan nyata
(nomor berkas bergeser, dataset lama tertinggal, dsb).

YANG DIUJI, dari yang paling penting:
  1. Paket bisa didekripsi dengan kunci privat yang ada — kalau tidak, paketnya
     tidak berguna dan kita baru tahu saat dibutuhkan.
  2. Tidak ada KOLOM identitas di header CSV mana pun.
  3. ⚠ Nama & no_rm pasien NYATA tidak muncul DI DALAM TEKS BEBAS. Ini risiko
     sisa yang tidak bisa dihilangkan penyamaran kolom: anamnesa sering memuat
     "diantar suaminya Pak Budi". Yang dicetak hanya JUMLAH, tidak pernah nama
     atau kutipan teksnya.
  4. manifest.json memuat peringatan "PSEUDONIM, BUKAN ANONIM".
  5. Tidak ada `pid` di paket yang tidak dikenal peta (paket nyasar / basi).
  6. Tidak ada ZIP POLOS yang tertinggal di folder drop.

Berkas hasil dekripsi ditulis ke direktori sementara dan DIHAPUS di akhir,
apa pun yang terjadi.
"""
import csv
import io
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
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
from app.services.clinical_export_service import KOLOM_TERLARANG  # noqa: E402

KUNCI_DEFAULT = os.path.expanduser("~/sehati-backup.key")
_lulus, _gagal = 0, 0


def cek(label, ok, detail=""):
    global _lulus, _gagal
    if ok:
        _lulus += 1
        print(f"  ✓ {label}" + (f"\n      {detail}" if detail else ""))
    else:
        _gagal += 1
        print(f"  ✗ {label}" + (f"\n      {detail}" if detail else ""))


def paket_terbaru(drop: str):
    if not os.path.isdir(drop):
        return None
    kandidat = sorted((f for f in os.listdir(drop)
                       if f.startswith("sehati_clinical_") and f.endswith(".age")),
                      reverse=True)
    return os.path.join(drop, kandidat[0]) if kandidat else None


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    kunci = KUNCI_DEFAULT
    if "--kunci" in sys.argv:
        kunci = os.path.expanduser(sys.argv[sys.argv.index("--kunci") + 1])

    drop = batch.DEFAULT_DROP
    paket = args[0] if args else paket_terbaru(drop)
    if not paket or not os.path.isfile(paket):
        print(f"  ⛔ Tidak ada paket .age di {drop}. Jalankan "
              f"`python -m scripts.gen_clinical_export` dulu.")
        return 1
    if shutil.which("age") is None:
        print("  ⛔ Program `age` tidak ada.")
        return 1
    if not os.path.isfile(kunci):
        print(f"  ⛔ Kunci privat tidak ada di {kunci}. Beri lewat --kunci.")
        return 1

    print(f"Paket : {os.path.basename(paket)}")
    print(f"Ukuran: {os.path.getsize(paket):,} byte\n")

    tmp = tempfile.mkdtemp(prefix="cek_klinis_")
    try:
        print("1. Dekripsi\n")
        zpath = os.path.join(tmp, "paket.zip")
        hasil = subprocess.run(["age", "-d", "-i", kunci, "-o", zpath, paket],
                               capture_output=True)
        cek("Paket bisa didekripsi dengan kunci privat yang ada",
            hasil.returncode == 0 and os.path.isfile(zpath),
            "kunci cocok" if hasil.returncode == 0
            else hasil.stderr.decode()[:160])
        if hasil.returncode != 0:
            return 1

        with zipfile.ZipFile(zpath) as z:
            isi = z.namelist()
            berkas = {n: z.read(n) for n in isi}

        print(f"\n2. Isi paket ({len(isi)} berkas)\n")
        for n in sorted(isi):
            print(f"      {n:34} {len(berkas[n]):>9,} byte")
        cek("manifest.json ada", "manifest.json" in isi)

        print("\n3. Header CSV — tidak ada kolom identitas\n")
        header_map = {}
        for n in sorted(x for x in isi if x.endswith(".csv")):
            teks = berkas[n].decode("utf-8-sig", errors="replace")
            baris1 = teks.splitlines()[0] if teks.splitlines() else ""
            kol = next(csv.reader(io.StringIO(baris1)), [])
            header_map[n] = kol
            haram = sorted(set(kol) & KOLOM_TERLARANG)
            cek(f"{n:34} {len(kol)} kolom",
                not haram,
                f"kolom: {kol}" if not haram else f"⚠ KOLOM IDENTITAS: {haram}")

        print("\n4. ⚠ Nama & no_rm pasien NYATA di dalam TEKS BEBAS\n")
        print("      (yang dicetak hanya JUMLAH — nama pasien tidak pernah "
              "ditampilkan di sini)\n")
        db = SessionLocal()
        try:
            pasien = db.execute(text(
                "SELECT nama, no_rm FROM pasien")).all()
        finally:
            db.close()
        # ⚠ HANYA kolom TEKS BEBAS. Versi pertama pemeriksa ini menyisir SELURUH
        #   isi CSV dan langsung memberi alarm palsu: ia menemukan nama pasien di
        #   kolom `nama_dokter`, karena di klinik ada staf yang JUGA terdaftar
        #   sebagai pasien. Kolom nama staf memang SENGAJA ikut (diminta dr.
        #   Hansen: dokter peresep, yang menindak, perawat yang menindak) — jadi
        #   mencocokkannya dengan daftar nama pasien mengukur hal yang salah.
        #   Yang dijaga di sini adalah identitas yang terselip DI DALAM KALIMAT.
        KOLOM_TEKS_BEBAS = {
            "anamnesa", "pemeriksaan_fisik", "diagnosa", "saran_treatment",
            "saran_produk", "keluhan_utama", "catatan_kontrol", "catatan",
            "aturan_pakai",
        }
        potong = []
        for n in (x for x in isi if x.endswith(".csv")):
            teks = berkas[n].decode("utf-8-sig", errors="replace")
            for row in csv.DictReader(io.StringIO(teks)):
                for kol, val in row.items():
                    if kol in KOLOM_TEKS_BEBAS and val:
                        potong.append(str(val))
        gabung_isi = "\n".join(potong).lower()
        print(f"      kolom teks bebas yang disisir: "
              f"{sorted(KOLOM_TEKS_BEBAS & set().union(*header_map.values()))}\n")

        # Nama pendek (<4 huruf) dilewati: "Ani" muncul di kata biasa dan hanya
        # menghasilkan alarm palsu yang membuat pemeriksa ini berhenti dibaca.
        nama_kena = [nm.strip() for nm, _ in pasien
                     if nm and len(nm.strip()) >= 4
                     and nm.strip().lower() in gabung_isi]
        kena_nama = len(nama_kena)
        kena_rm = sum(1 for _, rm in pasien
                      if rm and len(rm.strip()) >= 4
                      and rm.strip().lower() in gabung_isi)

        # --rinci: sebutkan BERKAS, KOLOM dan pid tempat nama itu muncul, supaya
        # bisa ditelusuri di Sehati — TANPA pernah mencetak namanya di sini.
        # Nama disamarkan jadi 'S****h (8 huruf, 2 kata)'; itu cukup untuk
        # mengenali baris yang dimaksud lewat pid, tidak cukup untuk membocorkan.
        if nama_kena and "--rinci" in sys.argv:
            print("\n      RINCI — lokasi kemunculan (nama disamarkan):")
            for nm in nama_kena:
                low = nm.lower()
                samar = (f"{nm[0]}{'*' * max(len(nm) - 2, 1)}{nm[-1]} "
                         f"({len(nm)} huruf, {len(nm.split())} kata)")
                print(f"        {samar}")
                for n in sorted(x for x in isi if x.endswith(".csv")):
                    teks = berkas[n].decode("utf-8-sig", errors="replace")
                    rdr = csv.DictReader(io.StringIO(teks))
                    for row in rdr:
                        for kol, val in row.items():
                            # sama seperti di atas: hanya kolom teks bebas
                            if (kol in KOLOM_TEKS_BEBAS and val
                                    and low in str(val).lower()):
                                print(f"          {n} · kolom '{kol}' · "
                                      f"pid={row.get('pid', '?')}")
        elif nama_kena:
            print("      (jalankan dengan --rinci untuk melihat berkas/kolom/pid-nya)")
        cek("Tidak ada nama pasien di dalam isi paket", kena_nama == 0,
            f"{len(pasien)} pasien diperiksa, 0 ditemukan" if kena_nama == 0
            else f"⚠ {kena_nama} nama pasien DITEMUKAN di teks bebas. Ini BUKAN "
                 f"bug kode — penyamaran kolom memang tidak menyentuh isi "
                 f"kalimat. Putuskan: tetap kirim (paket rahasia) atau saring.")
        cek("Tidak ada no_rm di dalam isi paket", kena_rm == 0,
            f"{len(pasien)} no_rm diperiksa, 0 ditemukan" if kena_rm == 0
            else f"⚠ {kena_rm} no_rm DITEMUKAN — petugas mungkin menulis nomor RM "
                 f"di dalam anamnesa/catatan.")

        print("\n5. Manifest\n")
        import json
        man = json.loads(berkas.get("manifest.json", b"{}").decode("utf-8"))
        cek("Manifest memuat peringatan PSEUDONIM-BUKAN-ANONIM",
            "PSEUDONIM" in str(man.get("PERINGATAN", "")).upper(),
            "penerima tidak akan pernah menyangka ini data anonim")
        cek("Manifest mencatat sidik jari isi",
            bool(man.get("content_fingerprint")),
            f"fp: {str(man.get('content_fingerprint'))[:16]}…")
        cek("Jumlah dataset di manifest cocok dengan CSV di ZIP",
            man.get("dataset_count") == len([x for x in isi if x.endswith(".csv")]),
            f"manifest {man.get('dataset_count')}, "
            f"CSV {len([x for x in isi if x.endswith('.csv')])}")

        print("\n6. pid dikenal peta\n")
        db = SessionLocal()
        try:
            pid_sah = {str(r[0]) for r in db.execute(text(
                "SELECT pid FROM pasien_pseudonim")).all()}
        finally:
            db.close()
        pid_paket = set()
        for n in isi:
            if not n.endswith(".csv"):
                continue
            teks = berkas[n].decode("utf-8-sig", errors="replace")
            rdr = csv.DictReader(io.StringIO(teks))
            for row in rdr:
                for k in ("pid", "pid_lama", "pid_bertahan"):
                    if row.get(k):
                        pid_paket.add(row[k])
        asing = sorted(pid_paket - pid_sah)
        cek("Semua pid di paket dikenal peta pseudonim", not asing,
            f"{len(pid_paket)} pid di paket, semuanya dikenal" if not asing
            else f"⚠ pid tidak dikenal (paket basi / nyasar): {asing[:5]}")

        print("\n7. Folder drop bersih\n")
        polos = [f for f in os.listdir(drop)
                 if f.startswith("sehati_clinical_")
                 and (f.endswith(".zip") or f.endswith(".tmp"))]
        cek("Tidak ada ZIP polos / .tmp yatim di folder drop", not polos,
            "bersih" if not polos else f"⚠ TERTINGGAL TANPA ENKRIPSI: {polos}")

        print(f"\nHASIL: {_lulus} lulus, {_gagal} gagal")
        return 1 if _gagal else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"   (hasil dekripsi sementara dihapus: {tmp})")


if __name__ == "__main__":
    sys.exit(main())
