"""Bersihkan penanda kosong di pasien.nomor_ktp ('0', '-', dst) -> NULL.

LATAR BELAKANG
--------------
`nomor_ktp` punya UNIQUE INDEX `ux_pasien_nomor_ktp` (migrasi 20260917_0100).
MySQL memperbolehkan BANYAK NULL di unique index, tapi '0' adalah nilai biasa.
Kolom ini tidak punya validasi bentuk, jadi petugas bisa mengetik '0' sebagai
penanda "tidak ada KTP" — dan itu MEMANG sudah terjadi (ditemukan 1 baris di
DB dev, 2026-09-30).

Akibatnya: pasien PERTAMA tanpa KTP tersimpan '0', pasien KEDUA ditolak dengan
"NIK sudah terdaftar atas pasien lain". Gejalanya tidak menunjuk ke penyebabnya
sama sekali — petugas merasa tidak mengisi apa pun.

Anak belum tentu punya KTP; lansia yang tidak membawa KTP tetap dilayani. Jadi
ini bukan kasus tepi, ini rutin.

APA YANG DILAKUKAN MIGRASI INI
------------------------------
1. '' -> NULL (jaring pengaman; 20260917_0100 sudah melakukannya, tapi baris
   baru bisa muncul di antaranya)
2. Penanda kosong ('0', '00', '000', '-', '--', 'x', dst — setelah spasi dan
   pemisah dibuang) -> NULL
3. Pasang UNIQUE INDEX kalau 20260917_0100 dulu MELEWATINYA (ia memang sengaja
   skip bila saat itu ada NIK kembar)

⚠ INI MENGHAPUS DATA — tapi data yang dihapus adalah penanda semu, bukan NIK.
   Tidak ada NIK sah yang berbentuk '0' atau '-'. Baris yang diubah dicetak ke
   log alembic sebelum diubah, supaya ada jejaknya.

Pencegahan ke depan: `app/core/nik.py` (normalisasi_nik) dipakai di semua jalur
tulis, dijaga oleh `scripts/cek_nik.py`.

Revision ID: 20260930_0100
Revises: 20260927_0100
Create Date: 2026-09-30
"""
import sqlalchemy as sa
from alembic import op

revision = "20260930_0100"
down_revision = "20260927_0100"
branch_labels = None
depends_on = None

INDEX = "ux_pasien_nomor_ktp"
TABLE = "pasien"

# Penanda kosong SETELAH spasi & pemisah dibuang dan huruf dikecilkan.
# Harus sinkron dengan app/core/nik.py::_PENANDA_KOSONG — cek_nik.py menguji
# perilakunya, bukan kesamaan daftar ini, jadi jaga manual.
_PENANDA = ("", "0", "00", "000", "0000", "-", "x", "xx", "xxx", "n", "na")

# Bersihkan spasi + pemisah agar '0-0-0' dan ' - ' ikut tertangkap.
_BERSIH = (
    "LOWER(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE("
    "TRIM(nomor_ktp), ' ', ''), '.', ''), '-', ''), '_', ''), '/', ''), CHAR(9), ''))"
)


def upgrade():
    bind = op.get_bind()
    daftar = ", ".join(f"'{p}'" for p in _PENANDA)
    kondisi = f"nomor_ktp IS NOT NULL AND {_BERSIH} IN ({daftar})"

    # 1+2. Cetak dulu APA yang akan diubah — supaya ada jejak di log deploy.
    baris = bind.execute(sa.text(
        f"SELECT id_pasien, no_rm, nomor_ktp FROM {TABLE} WHERE {kondisi}")).all()
    if baris:
        print(f"[migrasi {revision}] {len(baris)} baris NIK penanda-kosong -> NULL:")
        for b in baris:
            print(f"    id_pasien={b[0]}  no_rm={b[1]}  nomor_ktp={b[2]!r}")
    else:
        print(f"[migrasi {revision}] tidak ada NIK penanda-kosong. Bersih.")

    bind.execute(sa.text(f"UPDATE {TABLE} SET nomor_ktp = NULL WHERE {kondisi}"))

    # 3. Pasang unique index kalau 20260917_0100 dulu melewatinya.
    insp = sa.inspect(bind)
    if INDEX in {ix["name"] for ix in insp.get_indexes(TABLE)}:
        print(f"[migrasi {revision}] {INDEX} sudah ada. Lewati.")
        return

    kembar = bind.execute(sa.text(
        f"SELECT nomor_ktp, COUNT(*) c FROM {TABLE} "
        "WHERE nomor_ktp IS NOT NULL GROUP BY nomor_ktp HAVING c > 1")).all()
    if kembar:
        print(f"[migrasi {revision}] LEWATI {INDEX}: masih ada NIK kembar "
              f"({', '.join(str(k[0]) for k in kembar)}). Perlindungan aplikasi "
              f"tetap aktif. Bereskan kembar lalu pasang manual: "
              f"CREATE UNIQUE INDEX {INDEX} ON {TABLE}(nomor_ktp);")
        return
    op.create_index(INDEX, TABLE, ["nomor_ktp"], unique=True)
    print(f"[migrasi {revision}] {INDEX} dipasang.")


def downgrade():
    # Tidak ada jalan pulang: nilai '0'/'-' yang dihapus tidak menyimpan
    # informasi apa pun, jadi memulihkannya tidak bermakna — dan justru
    # mengembalikan bug "pasien kedua tanpa KTP ditolak".
    pass
