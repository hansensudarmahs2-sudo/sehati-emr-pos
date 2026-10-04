"""Smoke test UI web — buka setiap halaman yang BISA DIKLIK, cari yang error.

Kenapa menelusuri tautan, bukan daftar route
--------------------------------------------
Introspeksi `app.routes` ternyata tidak dapat diandalkan di sini (route /web tidak
muncul walau requestnya berhasil). Menelusuri `href` justru lebih berguna: yang diuji
adalah apa yang benar-benar bisa diklik pengguna, termasuk tautan yang DIRAKIT dari
variabel template. Itulah yang menemukan `/web/kasir/tagihan/None` — transaksi
MEMBERSHIP tidak punya `id_kunjungan`, dan tautannya tetap dirender.

BUTUH kredensial uji di environment (di laptop sudah ada di `.env`):
    TEST_USERNAME, TEST_PASSWORD

⚠ Perannya menentukan apa yang terlihat. Akun Owner/Superadmin membuka paling banyak
halaman; akun berperan sempit akan melaporkan lebih sedikit halaman, BUKAN lebih sedikit
masalah. Jadi "0 bermasalah" dengan akun sempit tidak mengatakan banyak.

Jalankan dari `sehati_clinic/`:
    docker compose ... exec sehati-app python -m scripts.cek_smoke_web
"""
import os
import re
import sys

from fastapi.testclient import TestClient

from app.main import app

TAUTAN = re.compile(r'href="(/web[^"#?]*)"')

# Segmen URL yang jelas hasil variabel KOSONG. Dicari langsung di HTML, bukan dengan
# mengikuti tautannya, karena kode status tidak selalu membongkarnya: tautan rusak
# bisa saja membalas 200 sambil menampilkan rekam YANG SALAH. Lihat catatan di bawah.
SEGMEN_KOSONG = re.compile(r'href="(/web/[^"]*/(?:None|none|undefined|null|nan)(?:[/#?][^"]*)?)"')


def tautan_di(html: str) -> set[str]:
    return {h for h in TAUTAN.findall(html)
            if "{" not in h and not h.endswith("/logout")}


def segmen_kosong_di(html: str) -> set[str]:
    """Tautan yang memuat `None`/`undefined` sebagai segmen path.

    ⚠ KENAPA DICARI DI HTML, BUKAN DARI KODE STATUS. Versi pertama pemeriksa ini hanya
    melaporkan halaman yang membalas >=400. Itu menemukan `/web/kasir/tagihan/None`
    (422) — tapi MELEWATKAN bug yang jauh lebih serius di halaman membership: di sana
    `id_transaksi` dimasukkan ke URL ber-parameter `id_kunjungan`, dan karena nomornya
    kebetulan bertabrakan, halaman membership satu pasien membuka tagihan PASIEN LAIN
    dengan status **200**. Kode status tidak akan pernah membongkar itu.

    Pemeriksaan ini menangkap kelas yang pertama (variabel kosong) langsung dari HTML,
    jadi ia tetap melaporkan walau tautannya membalas 200. Kelas kedua — id yang salah
    JENIS tapi valid bentuknya — tidak bisa ditangkap crawler mana pun; itu hanya
    tertangkap dengan membaca template. Jangan percaya "0 bermasalah" sebagai bukti
    bahwa semua tautan menunjuk ke rekam yang BENAR.
    """
    return set(SEGMEN_KOSONG.findall(html))


def main() -> None:
    user, sandi = os.getenv("TEST_USERNAME"), os.getenv("TEST_PASSWORD")
    if not user or not sandi:
        sys.exit("DITOLAK: set TEST_USERNAME dan TEST_PASSWORD dulu (lihat .env laptop).")

    c = TestClient(app, follow_redirects=True)
    hal = c.get("/web/login")
    data = {"username": user, "password": sandi}
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', hal.text)
    if m:
        data["csrf_token"] = m.group(1)
    if c.post("/web/login", data=data).status_code >= 400:
        sys.exit("DITOLAK: login gagal — periksa TEST_USERNAME/TEST_PASSWORD.")

    dash = c.get("/web/dashboard")
    if dash.status_code >= 400:
        sys.exit(f"DITOLAK: dashboard {dash.status_code} — login sepertinya tidak nyangkut.")

    dikunjungi: set[str] = set()
    rusak: list[tuple[str, int, str]] = []
    kosong: dict[str, str] = {}      # tautan ber-segmen kosong -> halaman asalnya
    antre = tautan_di(dash.text)
    for t in segmen_kosong_di(dash.text):
        kosong.setdefault(t, "/web/dashboard")

    # Dua lapis: tautan di dashboard, lalu tautan di halaman-halaman itu.
    for lapis in range(2):
        berikut: set[str] = set()
        for p in sorted(antre - dikunjungi):
            dikunjungi.add(p)
            try:
                resp = c.get(p)
            except Exception as e:                      # noqa: BLE001
                rusak.append((p, 0, f"{type(e).__name__}: {e}"))
                continue
            if resp.status_code >= 400:
                rusak.append((p, resp.status_code, resp.text[:160]))
            for t in segmen_kosong_di(resp.text):
                kosong.setdefault(t, p)
            if lapis == 0:
                berikut |= tautan_di(resp.text)
        antre = berikut

    print(f"SMOKE UI WEB — akun {user!r}\n")
    print(f"  {len(dikunjungi)} halaman dibuka · "
          f"{len(dikunjungi) - len(rusak)} OK · {len(rusak)} BERMASALAH")
    for p, kode, pesan in rusak:
        print(f"\n  ✗ {kode or 'EXC'}  {p}")
        print(f"       {pesan.strip()[:160]}")

    if kosong:
        print(f"\n  ✗ {len(kosong)} tautan memuat segmen KOSONG "
              f"(dilaporkan walau balasannya 200):")
        for t, asal in sorted(kosong.items()):
            print(f"       {t}")
            print(f"         dirender di: {asal}")

    print(f"\nHASIL: {len(rusak)} halaman bermasalah, "
          f"{len(kosong)} tautan ber-segmen kosong, dari {len(dikunjungi)} halaman")


if __name__ == "__main__":
    main()
