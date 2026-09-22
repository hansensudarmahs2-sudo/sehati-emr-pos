"""refund per item (#54-F): transaksi_refund dapat kolom item

`transaksi_refund` sudah ada sejak 20260706_0400 tapi belum pernah ditulis siapa pun,
dan ekspor Finance `15_refunds_raw.csv` sudah membacanya. Refund per item menulis ke
tabel itu — bukan tabel baru — supaya laporan Finance langsung hidup.

Yang ditambahkan hanya penautan ke ITEM-nya, karena tabel aslinya hanya mengenal
transaksi:
- `jenis_refund` ('ITEM' / 'TRANSAKSI'), default 'ITEM'
- `id_resep` (null) → refund satu baris resep
- `id_kunjungan_racikan` (null) → refund satu racikan (all-or-nothing)

TEPAT SATU dari dua kolom item terisi saat jenis_refund='ITEM'.

Tidak ada kolom baru di `transaksi_kasir`: keputusan dr. Hansen adalah **mengurangi
`total_tagihan` yang sudah ada** saat refund, supaya 12 titik agregasi uang di 8 file
otomatis benar tanpa satu pun query disentuh (alternatifnya menyisakan celah senyap).

Revision ID: 20260922_0200
Revises: 20260922_0100
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa


revision = "20260922_0200"
down_revision = "20260922_0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "transaksi_refund" not in set(insp.get_table_names()):
        return  # tabel belum ada (instalasi sangat lama) — tidak ada yang bisa ditambah

    cols = {c["name"] for c in insp.get_columns("transaksi_refund")}

    if "jenis_refund" not in cols:
        op.add_column(
            "transaksi_refund",
            sa.Column("jenis_refund", sa.String(20), nullable=False,
                      server_default="ITEM",
                      comment="ITEM = refund satu baris resep/racikan; "
                              "TRANSAKSI = seluruh transaksi."),
        )
    if "id_resep" not in cols:
        op.add_column("transaksi_refund", sa.Column("id_resep", sa.Integer, nullable=True))
        op.create_foreign_key(
            "fk_refund_resep", "transaksi_refund", "kunjungan_resep",
            ["id_resep"], ["id_resep"],
        )
        op.create_index("ix_refund_resep", "transaksi_refund", ["id_resep"])
    if "id_kunjungan_racikan" not in cols:
        op.add_column(
            "transaksi_refund",
            sa.Column("id_kunjungan_racikan", sa.Integer, nullable=True),
        )
        op.create_foreign_key(
            "fk_refund_kunjracik", "transaksi_refund", "kunjungan_racikan",
            ["id_kunjungan_racikan"], ["id_kunjungan_racikan"],
        )
        op.create_index("ix_refund_kunjracik", "transaksi_refund",
                        ["id_kunjungan_racikan"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "transaksi_refund" not in set(insp.get_table_names()):
        return
    cols = {c["name"] for c in insp.get_columns("transaksi_refund")}

    if "id_kunjungan_racikan" in cols:
        for drop, kind in (("ix_refund_kunjracik", "index"),
                           ("fk_refund_kunjracik", "foreignkey")):
            try:
                if kind == "index":
                    op.drop_index(drop, table_name="transaksi_refund")
                else:
                    op.drop_constraint(drop, "transaksi_refund", type_="foreignkey")
            except Exception:
                pass
        op.drop_column("transaksi_refund", "id_kunjungan_racikan")
    if "id_resep" in cols:
        for drop, kind in (("ix_refund_resep", "index"),
                           ("fk_refund_resep", "foreignkey")):
            try:
                if kind == "index":
                    op.drop_index(drop, table_name="transaksi_refund")
                else:
                    op.drop_constraint(drop, "transaksi_refund", type_="foreignkey")
            except Exception:
                pass
        op.drop_column("transaksi_refund", "id_resep")
    if "jenis_refund" in cols:
        op.drop_column("transaksi_refund", "jenis_refund")
