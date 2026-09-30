"""Pemeriksa: normalisasi NIK + gerbang "tidak ada jalur tulis yang melewatinya".

Bahaya yang dijaga:
  `pasien.nomor_ktp` punya UNIQUE INDEX. MySQL memperbolehkan banyak NULL, tapi
  '0' adalah nilai biasa. Kalau satu saja jalur menyimpan '0' alih-alih NULL,
  pasien KEDUA tanpa KTP ditolak dengan pesan "NIK sudah terdaftar atas pasien
  lain" — gejala yang sama sekali tidak menunjuk ke penyebabnya.

Yang diuji:
  A. normalisasi_nik() berperilaku benar (tabel kasus)
  B. AST: setiap penugasan ke `.nomor_ktp` di app/ melewati normalisasi_nik()
     ATAU ada di daftar pengecualian yang dijelaskan alasannya
  C. Keadaan DB: tidak ada '' dan tidak ada penanda kosong tersimpan; unique
     index terpasang

Jalankan dari `sehati_clinic/`:  python -m scripts.cek_nik
"""
import ast
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Senyapkan gema SQL — hasil pemeriksaan harus bisa dibaca sekilas.
for _n in ("sqlalchemy.engine", "sqlalchemy.engine.Engine"):
    logging.getLogger(_n).setLevel(logging.WARNING)

from app.core.nik import normalisasi_nik  # noqa: E402

# Jalur yang SENGAJA tidak menormalkan, beserta alasannya. Kalau menambah di
# sini, tulis alasannya — bukan sekadar membungkam pemeriksa.
PENGECUALIAN = {
    ("app/services/audit_pasien_service.py", "nomor_ktp_lama"):
        "menyimpan NIK lama apa adanya untuk jejak; bukan kolom ber-unique index",
    ("app/services/audit_pasien_service.py", "nomor_ktp"):
        "melepas NIK (set None) saat nonaktif; .strip() disengaja agar '0' lama "
        "ikut terbebaskan — lihat komentar di sana",
}

_lulus, _gagal = 0, 0


def cek(label, ok, detail=""):
    global _lulus, _gagal
    if ok:
        _lulus += 1
        print(f"  ✓ {label}" + (f"\n      {detail}" if detail else ""))
    else:
        _gagal += 1
        print(f"  ✗ {label}" + (f"\n      {detail}" if detail else ""))


# ----------------------------------------------------------------- A. perilaku
KASUS_NONE = ["", "   ", "0", "00", "000", "0000", "-", "--", "0-0-0", " - ",
              "x", "XX", None, "\t", " 0 "]
KASUS_TETAP = {
    "3578123456789012": "3578123456789012",
    " 3578-1234 5678 9012 ": "3578123456789012",
    "3578.1234.5678.9012": "3578123456789012",
    "A1": "A1",
    "01": "01",          # awalan nol yang SAH — jangan ikut dibuang
    "1": "1",            # satu digit bukan nol: bukan penanda kosong
}


def bagian_a():
    print("A. Perilaku normalisasi_nik()\n")
    salah = [repr(k) for k in KASUS_NONE if normalisasi_nik(k) is not None]
    cek("Semua penanda kosong -> None", not salah,
        f"{len(KASUS_NONE)} kasus diuji" if not salah else f"GAGAL: {salah}")

    salah2 = {k: normalisasi_nik(k) for k, v in KASUS_TETAP.items()
              if normalisasi_nik(k) != v}
    cek("NIK sah dipertahankan (pemisah dibuang, awalan nol aman)", not salah2,
        f"{len(KASUS_TETAP)} kasus diuji" if not salah2 else f"GAGAL: {salah2}")

    cek("'01' TIDAK dianggap kosong", normalisasi_nik("01") == "01",
        "kalau ini gagal, NIK berawalan nol akan hilang")


# ---------------------------------------------------------------------- B. AST
KOLOM = ("nomor_ktp", "nomor_ktp_lama")

# Hanya panggilan yang benar-benar MENULIS ke baris DB yang diperiksa. Route
# yang menyusun payload schema (PasienBaruRequest, PasienUpdateRequest) TIDAK
# diperiksa — nilainya masih lewat service, dan di sanalah normalisasi terjadi.
# Memeriksa keduanya hanya menghasilkan kebisingan yang bikin gerbang diabaikan.
PENULIS_DB = {"Pasien", "values", "update"}


class Pemindai(ast.NodeVisitor):
    """Cari penulisan NIK yang SAMPAI KE DB tanpa melewati normalisasi_nik().

    Dua bentuk yang diperiksa:
      1. `<apa pun>.nomor_ktp = <nilai>`           (penugasan atribut ORM)
      2. `Pasien(nomor_ktp=<nilai>)` / `.values(nomor_ktp=...)`

    Nilai dianggap ternormalisasi bila (a) memanggil normalisasi_nik() langsung,
    atau (b) berupa variabel yang di fungsi yang sama diisi dari normalisasi_nik()
    — pola `_new_nik = normalisasi_nik(x)` lalu `pasien.nomor_ktp = _new_nik`.
    """

    def __init__(self, rel):
        self.rel = rel
        self.temuan = []          # (lineno, kolom, ternormalisasi: bool)
        self._aman = set()        # nama variabel hasil normalisasi_nik()

    # -- bantu ------------------------------------------------------------
    @staticmethod
    def _memanggil_normalisasi(node) -> bool:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                nama = getattr(sub.func, "id", None) or getattr(sub.func, "attr", None)
                if nama == "normalisasi_nik":
                    return True
        return False

    def _ternormalisasi(self, nilai) -> bool:
        if self._memanggil_normalisasi(nilai):
            return True
        # variabel yang sudah dinormalisasi sebelumnya di lingkup ini
        if isinstance(nilai, ast.Name) and nilai.id in self._aman:
            return True
        if isinstance(nilai, ast.BoolOp):   # `x or None`
            return all(self._ternormalisasi(v) for v in nilai.values
                       if not isinstance(v, ast.Constant))
        return False

    @staticmethod
    def _nama_fungsi(call) -> str:
        return getattr(call.func, "id", None) or getattr(call.func, "attr", "") or ""

    # -- lingkup fungsi: variabel aman tidak bocor antar fungsi -----------
    def visit_FunctionDef(self, node):
        simpan = self._aman
        self._aman = set()
        self.generic_visit(node)
        self._aman = simpan

    visit_AsyncFunctionDef = visit_FunctionDef

    # -- bentuk yang diperiksa --------------------------------------------
    def visit_Assign(self, node):
        # catat dulu variabel hasil normalisasi (urutan baca = urutan tulis)
        if self._memanggil_normalisasi(node.value):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    self._aman.add(t.id)
        for t in node.targets:
            if isinstance(t, ast.Attribute) and t.attr in KOLOM:
                self.temuan.append(
                    (node.lineno, t.attr, self._ternormalisasi(node.value)))
        self.generic_visit(node)

    def visit_Call(self, node):
        if self._nama_fungsi(node) in PENULIS_DB:
            for kw in node.keywords:
                if kw.arg in KOLOM:
                    self.temuan.append(
                        (node.lineno, kw.arg, self._ternormalisasi(kw.value)))
        self.generic_visit(node)


def bagian_b():
    print("\nB. Gerbang: semua jalur tulis NIK melewati normalisasi_nik()\n")
    pelanggar = []
    diperiksa = 0
    for p in sorted((ROOT / "app").rglob("*.py")):
        rel = p.relative_to(ROOT).as_posix()
        try:
            pohon = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError as e:
            pelanggar.append(f"{rel}: TIDAK BISA DI-PARSE ({e})")
            continue
        pem = Pemindai(rel)
        pem.visit(pohon)
        for lineno, kolom, ternormal in pem.temuan:
            diperiksa += 1
            if ternormal:
                continue
            if (rel, kolom) in PENGECUALIAN:
                continue
            pelanggar.append(f"{rel}:{lineno}  {kolom}=  (tanpa normalisasi_nik)")

    cek(f"Tidak ada jalur tulis NIK yang melewati normalisasi ({diperiksa} penugasan dipindai)",
        not pelanggar,
        "semua bersih" if not pelanggar else "PELANGGAR:\n      " + "\n      ".join(pelanggar))

    print("\n   Pengecualian terdaftar (disengaja):")
    for (f, k), alasan in PENGECUALIAN.items():
        print(f"      {f} :: {k}\n         -> {alasan}")


# ----------------------------------------------------------------------- C. DB
def bagian_c():
    print("\nC. Keadaan DB\n")
    from sqlalchemy import text
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        r = db.execute(text(
            "SELECT COUNT(*) total, SUM(nomor_ktp IS NULL) nul, "
            "SUM(nomor_ktp = '') kosong FROM pasien")).one()
        total, nul, kosong = r[0], int(r[1] or 0), int(r[2] or 0)
        cek("Tidak ada nomor_ktp = '' (harus NULL)", kosong == 0,
            f"total {total} pasien, {nul} NULL, {kosong} string kosong")

        # Penanda kosong yang tersimpan sebagai nilai -> menempati slot unique
        baris = db.execute(text(
            "SELECT id_pasien, no_rm, nomor_ktp FROM pasien "
            "WHERE nomor_ktp IS NOT NULL")).all()
        nakal = [(b[0], b[1], b[2]) for b in baris if normalisasi_nik(b[2]) is None]
        cek("Tidak ada penanda kosong ('0','-',dst) tersimpan sebagai NIK",
            not nakal,
            "bersih" if not nakal else
            "SLOT TERKUNCI oleh: " + ", ".join(
                f"id={i} RM={rm} nik={v!r}" for i, rm, v in nakal))

        ix = db.execute(text(
            "SELECT INDEX_NAME, NON_UNIQUE FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'pasien' "
            "AND COLUMN_NAME = 'nomor_ktp'")).all()
        unik = [n for n, nonuniq in ix if int(nonuniq) == 0]
        cek("UNIQUE INDEX pada nomor_ktp terpasang", bool(unik),
            f"index: {unik}" if unik else
            "TIDAK ADA — migrasi 20260917_0100 mungkin melewatinya karena ada NIK kembar")

        # NIK kembar setelah normalisasi (pemisah beda gaya lolos unique index)
        dari_normal = {}
        for b in baris:
            n = normalisasi_nik(b[2])
            if n:
                dari_normal.setdefault(n, []).append(b[1])
        kembar = {k: v for k, v in dari_normal.items() if len(v) > 1}
        cek("Tidak ada NIK kembar setelah normalisasi", not kembar,
            "bersih" if not kembar else
            "KEMBAR (lolos unique index karena gaya penulisan beda): "
            + ", ".join(f"{k} -> RM {v}" for k, v in kembar.items()))
    finally:
        db.close()


def main():
    bagian_a()
    bagian_b()
    bagian_c()
    print(f"\nHASIL: {_lulus} lulus, {_gagal} gagal")
    return 1 if _gagal else 0


if __name__ == "__main__":
    sys.exit(main())
