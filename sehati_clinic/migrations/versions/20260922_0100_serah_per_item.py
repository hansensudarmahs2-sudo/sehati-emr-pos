"""serah per item (#54): status DISERAHKAN + jejak serah + jejak lot per item

Tiga perubahan, semuanya prasyarat penyerahan obat PER ITEM di apotek:

1. `kunjungan_resep.status_item` menerima nilai baru **DISERAHKAN**. Sebelum ini
   "stok item sudah dipotong" ditebak dari `kunjungan.status_antrian == COMPLETED`.
   Begitu penyerahan boleh sebagian, tebakan itu salah dan void bisa mengembalikan
   stok yang tidak pernah keluar. Status per item menggantikan tebakan.

2. `kunjungan_resep` + `kunjungan_racikan` dapat `waktu_serah` & `id_staf_serah`.
   Satu kunjungan bisa diserahkan beberapa kali oleh apoteker berbeda; laporan harus
   memberi kredit per item, bukan per kunjungan.

3. `kunjungan_lot_terpakai` dapat `id_resep` & `id_kunjungan_racikan` (nullable).
   Tabel jejak lot hanya menyimpan `id_produk`, jadi satu produk yang muncul di DUA
   baris resep tidak bisa dibedakan saat reverse per item. Baris lama tetap NULL dan
   dibaca dengan cara lama (per produk).

`kunjungan_racikan.status_item` sudah String(20) → cukup dipakai, tanpa ALTER tipe.

Revision ID: 20260922_0100
Revises: 20260921_0300
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa


revision = "20260922_0100"
down_revision = "20260921_0300"
branch_labels = None
depends_on = None

# Nilai enum SETELAH penambahan. MySQL tidak punya "ALTER TYPE ADD VALUE" seperti
# Postgres — satu-satunya cara adalah MODIFY kolom dengan daftar lengkap.
_ENUM_BARU = "ENUM('PENDING','BATAL','DIBAYAR','DISERAHKAN')"
_ENUM_LAMA = "ENUM('PENDING','BATAL','DIBAYAR')"


def _cols(insp, table):
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    # --- 1 & 2. kunjungan_resep -------------------------------------------------
    if "kunjungan_resep" in tables:
        op.execute(
            f"ALTER TABLE kunjungan_resep MODIFY COLUMN status_item {_ENUM_BARU} "
            "NULL DEFAULT 'PENDING'"
        )
        cols = _cols(insp, "kunjungan_resep")
        if "waktu_serah" not in cols:
            op.add_column("kunjungan_resep", sa.Column("waktu_serah", sa.TIMESTAMP, nullable=True))
        if "id_staf_serah" not in cols:
            op.add_column("kunjungan_resep", sa.Column("id_staf_serah", sa.Integer, nullable=True))
            op.create_foreign_key(
                "fk_resep_staf_serah", "kunjungan_resep", "master_staf",
                ["id_staf_serah"], ["id_staf"],
            )

    # --- 2. kunjungan_racikan (status_item sudah String → tak perlu ALTER) ------
    if "kunjungan_racikan" in tables:
        cols = _cols(insp, "kunjungan_racikan")
        if "waktu_serah" not in cols:
            op.add_column("kunjungan_racikan", sa.Column("waktu_serah", sa.TIMESTAMP, nullable=True))
        if "id_staf_serah" not in cols:
            op.add_column("kunjungan_racikan", sa.Column("id_staf_serah", sa.Integer, nullable=True))
            op.create_foreign_key(
                "fk_kunjracik_staf_serah", "kunjungan_racikan", "master_staf",
                ["id_staf_serah"], ["id_staf"],
            )

    # --- 3. kunjungan_lot_terpakai: asal potongan per ITEM ----------------------
    if "kunjungan_lot_terpakai" in tables:
        cols = _cols(insp, "kunjungan_lot_terpakai")
        if "id_resep" not in cols:
            op.add_column("kunjungan_lot_terpakai", sa.Column("id_resep", sa.Integer, nullable=True))
            op.create_foreign_key(
                "fk_lotterpakai_resep", "kunjungan_lot_terpakai", "kunjungan_resep",
                ["id_resep"], ["id_resep"],
            )
        if "id_kunjungan_racikan" not in cols:
            op.add_column(
                "kunjungan_lot_terpakai",
                sa.Column("id_kunjungan_racikan", sa.Integer, nullable=True),
            )
            op.create_foreign_key(
                "fk_lotterpakai_kunjracik", "kunjungan_lot_terpakai", "kunjungan_racikan",
                ["id_kunjungan_racikan"], ["id_kunjungan_racikan"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "kunjungan_lot_terpakai" in tables:
        cols = _cols(insp, "kunjungan_lot_terpakai")
        if "id_kunjungan_racikan" in cols:
            try:
                op.drop_constraint("fk_lotterpakai_kunjracik", "kunjungan_lot_terpakai",
                                   type_="foreignkey")
            except Exception:
                pass
            op.drop_column("kunjungan_lot_terpakai", "id_kunjungan_racikan")
        if "id_resep" in cols:
            try:
                op.drop_constraint("fk_lotterpakai_resep", "kunjungan_lot_terpakai",
                                   type_="foreignkey")
            except Exception:
                pass
            op.drop_column("kunjungan_lot_terpakai", "id_resep")

    if "kunjungan_racikan" in tables:
        cols = _cols(insp, "kunjungan_racikan")
        # Turunkan dulu nilainya, kalau tidak baris DISERAHKAN jadi status tak dikenal.
        op.execute("UPDATE kunjungan_racikan SET status_item='DIBAYAR' "
                   "WHERE status_item='DISERAHKAN'")
        if "id_staf_serah" in cols:
            try:
                op.drop_constraint("fk_kunjracik_staf_serah", "kunjungan_racikan",
                                   type_="foreignkey")
            except Exception:
                pass
            op.drop_column("kunjungan_racikan", "id_staf_serah")
        if "waktu_serah" in cols:
            op.drop_column("kunjungan_racikan", "waktu_serah")

    if "kunjungan_resep" in tables:
        cols = _cols(insp, "kunjungan_resep")
        # WAJIB sebelum mempersempit ENUM — MySQL akan mengosongkan nilai di luar daftar.
        op.execute("UPDATE kunjungan_resep SET status_item='DIBAYAR' "
                   "WHERE status_item='DISERAHKAN'")
        if "id_staf_serah" in cols:
            try:
                op.drop_constraint("fk_resep_staf_serah", "kunjungan_resep", type_="foreignkey")
            except Exception:
                pass
            op.drop_column("kunjungan_resep", "id_staf_serah")
        if "waktu_serah" in cols:
            op.drop_column("kunjungan_resep", "waktu_serah")
        op.execute(
            f"ALTER TABLE kunjungan_resep MODIFY COLUMN status_item {_ENUM_LAMA} "
            "NULL DEFAULT 'PENDING'"
        )
