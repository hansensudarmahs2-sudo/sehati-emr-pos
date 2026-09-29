"""R8 — "sisakan untuk nanti" di kasir: status DITUNDA + penanda asal racikan

Masalah yang ditutup: kasir menagih SEMUA item PENDING sekaligus, dan satu-satunya
tindakan per item adalah void → BATAL yang PERMANEN. Jadi untuk pasien yang mau dua dari
lima obat, kasir cuma punya dua pilihan dan keduanya salah: menagih semuanya, atau
membatalkan sisanya selamanya.

DITUNDA = dikeluarkan dari tagihan hari ini TAPI tidak dibatalkan, sehingga otomatis
muncul di daftar "Tebus resep lama" yang sudah ada.

⚠ PERINGATAN UNTUK KODE BARU: sejak migrasi ini ada DUA status yang berarti "belum
dibayar" — PENDING dan DITUNDA. Setiap query yang menulis `!= 'BATAL'` untuk memaksudkan
"masih berlaku" kini ikut menarik baris DITUNDA. Daftar 9 titik yang sudah disisir ada di
`Project_Memory/DESAIN_RESEP_LUAR_APOTEK.md` §11b.

`kunjungan_racikan.status_item` TIDAK diubah di sini: kolomnya sengaja String(20), bukan
ENUM, sejak penambahan DISERAHKAN — menambah nilai baru tidak butuh ALTER.

`id_kunjungan_racikan_asal` mengikuti pola `kunjungan_resep.id_resep_asal`: keberadaan
SALINAN-lah yang menandai baris asal sudah ditebus. Tidak ada kolom "sudah ditebus"
terpisah yang bisa berselisih dengan kenyataan.

Revision ID: 20260927_0100
Revises: 20260925_0100
Create Date: 2026-09-27
"""
from alembic import op

revision = "20260927_0100"
down_revision = "20260925_0100"
branch_labels = None
depends_on = None

# MySQL ENUM: tidak ada "ADD VALUE" — harus MODIFY dengan DAFTAR LENGKAP. Kalau ada nilai
# yang lupa ditulis, baris yang memakainya jadi '' tanpa peringatan.
_ENUM_BARU = "ENUM('PENDING','BATAL','DIBAYAR','DISERAHKAN','DITUNDA')"
_ENUM_LAMA = "ENUM('PENDING','BATAL','DIBAYAR','DISERAHKAN')"


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE kunjungan_resep "
        f"MODIFY COLUMN status_item {_ENUM_BARU} NOT NULL DEFAULT 'PENDING'"
    )
    op.execute(
        "ALTER TABLE kunjungan_racikan "
        "ADD COLUMN id_kunjungan_racikan_asal INT NULL "
        "COMMENT 'R8: racikan asal yang ditebus belakangan (anti tebus ganda)'"
    )
    op.execute(
        "ALTER TABLE kunjungan_racikan "
        "ADD CONSTRAINT fk_kracikan_asal FOREIGN KEY (id_kunjungan_racikan_asal) "
        "REFERENCES kunjungan_racikan(id_kunjungan_racikan)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE kunjungan_racikan DROP FOREIGN KEY fk_kracikan_asal")
    op.execute("ALTER TABLE kunjungan_racikan DROP COLUMN id_kunjungan_racikan_asal")
    # Baris DITUNDA dikembalikan ke PENDING dulu — kalau tidak, MODIFY akan
    # mengosongkannya diam-diam.
    op.execute("UPDATE kunjungan_resep SET status_item='PENDING' WHERE status_item='DITUNDA'")
    op.execute("UPDATE kunjungan_racikan SET status_item='PENDING' WHERE status_item='DITUNDA'")
    op.execute(
        f"ALTER TABLE kunjungan_resep "
        f"MODIFY COLUMN status_item {_ENUM_LAMA} NOT NULL DEFAULT 'PENDING'"
    )
