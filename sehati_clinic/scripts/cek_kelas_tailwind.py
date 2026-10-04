"""Pemeriksa: kelas Tailwind di template ADA di app.css hasil kompilasi.

MASALAH YANG DIJAGA
-------------------
Tailwind di proyek ini DIKOMPILASI LEBIH DULU (`static/css/app.css`).
Kelas yang tidak muncul di template mana pun saat kompilasi TIDAK ADA di CSS —
dan kegagalannya SENYAP: tidak ada error, tidak ada warning, elemennya tetap
dirender, hanya tampilannya salah.

Terjadi 2026-09-30 pada tombol "Tulis paket klinis": `bg-slate-800
hover:bg-slate-900` keduanya nol di app.css, jadi latar tombol hilang dan teks
putihnya menjadi TAK TERLIHAT. Yang tersisa di layar hanya emoji. Ditemukan
lewat mata dr. Hansen, bukan lewat uji apa pun.

CARA MEMBACA HASILNYA
---------------------
Ini pemeriksa PERINGATAN, bukan gerbang keras: beberapa kelas wajar hilang
(dipakai di cabang Jinja yang tidak pernah aktif, atau ditulis lewat JS).
Yang perlu diperiksa manusia adalah kelas WARNA & LATAR — itu yang membuat
elemen jadi tak terlihat.

Jalankan dari `sehati_clinic/`:  python -m scripts.cek_kelas_tailwind
                                 python -m scripts.cek_kelas_tailwind nama.html
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# ⚠ BERKAS YANG DILAYANI = sehati_clinic/static/css/app.css.
# app/main.py memasang StaticFiles dari parent.parent/"static", dan
# deployment/build_tailwind.sh menulis ke sana. Ada salinan kembar usang di
# app/web/static/css/app.css yang TIDAK dilayani dan TIDAK ikut di-build.
# Pemeriksa ini dulu membaca salinan itu: selama keduanya kebetulan identik
# hasilnya benar, tapi build pertama yang mengubah salah satunya membuat
# pemeriksa melaporkan keadaan berkas yang salah — persis jebakan "satu hal,
# dua penulis" di CLAUDE.md §4.1.
# Salinan kembarnya sudah DIHAPUS 2026-10-04 dan deployment/setup_self_host.sh
# (yang melahirkannya) sudah diarahkan ke static/. Jangan hidupkan lagi.
CSS = ROOT / "static" / "css" / "app.css"
TPL = ROOT / "app" / "web" / "templates"

# Kelas yang paling berbahaya kalau hilang: elemen jadi tak terlihat / tak terbaca.
POLA_KRITIS = re.compile(r"^(hover:)?(bg|text|border|ring|from|to|via)-")

# Sisa potongan dari kelas yang DIRAKIT SAAT RENDER, mis. `bg-{{ st.color }}-50/30`.
# Setelah bagian Jinja dibuang yang tersisa hanya `bg-` — itu bukan kelas yang
# hilang, melainkan tanda bahwa template itu merakit kelas secara dinamis.
# Dilaporkan terpisah: yang perlu dipastikan adalah kelas jadinya ada di
# `safelist` pada tailwind.config.js, bukan dicari-cari di app.css.
POLA_DINAMIS = re.compile(r"-$|-/")

# Bukan kelas Tailwind — jangan dilaporkan.
BUKAN_TAILWIND = re.compile(
    r"^(htmx-|js-|tom-|ts-|is-|has-|no-|active$|open$|hidden$|group$|peer$)")


def kelas_di_css(css: str) -> set[str]:
    """Semua selektor kelas di app.css, sudah di-unescape."""
    out = set()
    for m in re.finditer(r"\.((?:[A-Za-z0-9_-]|\\.)+)", css):
        out.add(m.group(1).replace("\\", ""))
    return out


def kelas_di_template(teks: str) -> set[str]:
    """Kelas statis di atribut class=. Bagian Jinja ({{...}}/{%...%}) dibuang.

    Kelas yang dirakit dinamis memang tidak bisa diperiksa — dan justru itu
    alasan proyek ini melarangnya.
    """
    out = set()
    for m in re.finditer(r'class="([^"]*)"', teks):
        isi = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", " ", m.group(1), flags=re.S)
        for tok in isi.split():
            if tok and not BUKAN_TAILWIND.match(tok):
                out.add(tok)
    return out


def main() -> int:
    if not CSS.is_file():
        print(f"  ⛔ {CSS} tidak ada.")
        return 1
    ada = kelas_di_css(CSS.read_text(encoding="utf-8", errors="replace"))
    print(f"app.css: {len(ada):,} kelas terkompilasi\n")

    target = sys.argv[1:] or None
    berkas = ([TPL / t for t in target] if target
              else sorted(TPL.rglob("*.html")))

    kritis_total, lain_total, dinamis_total, n_file = 0, 0, 0, 0
    for p in berkas:
        if not p.is_file():
            print(f"  ? {p} tidak ada")
            continue
        dipakai = kelas_di_template(p.read_text(encoding="utf-8", errors="replace"))
        hilang = sorted(k for k in dipakai if k not in ada)
        if not hilang:
            continue
        dinamis = [k for k in hilang if POLA_DINAMIS.search(k)]
        sisa = [k for k in hilang if k not in dinamis]
        kritis = [k for k in sisa if POLA_KRITIS.match(k)]
        lain = [k for k in sisa if not POLA_KRITIS.match(k)]
        n_file += 1
        kritis_total += len(kritis)
        lain_total += len(lain)
        dinamis_total += len(dinamis)
        print(f"  {p.relative_to(TPL)}")
        if kritis:
            print(f"      ⚠ WARNA/LATAR hilang -> elemen bisa TAK TERLIHAT:")
            for k in kritis:
                print(f"          {k}")
        if dinamis:
            print(f"      ↻ dirakit saat render (pastikan ada di safelist): "
                  f"{', '.join(dinamis)}")
        if lain:
            print(f"      (lain: {', '.join(lain[:12])}"
                  f"{' …' if len(lain) > 12 else ''})")

    print(f"\nRINGKASAN: {n_file} template punya kelas yang tidak ada di app.css")
    print(f"           {kritis_total} kelas WARNA/LATAR  ·  {lain_total} lainnya"
          f"  ·  {dinamis_total} dirakit saat render")
    if kritis_total:
        print("\n⚠ Kelas warna/latar yang hilang membuat elemen tak terlihat TANPA "
              "error apa pun.\n  Perbaiki dengan memakai kelas yang SUDAH dipakai "
              "template lain, atau kompilasi ulang Tailwind.")
    return 0   # peringatan, bukan gerbang keras


if __name__ == "__main__":
    sys.exit(main())
