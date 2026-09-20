"""produk: kekuatan sediaan + isi kemasan (dasar hitung racikan)

kekuatan_nilai/satuan → mode MG (tablet): butir = dosis×N ÷ kekuatan, bulat KE ATAS.
isi_kemasan/satuan_isi → mode GRAM (krim): harga per gram = harga_jual ÷ isi_kemasan (pro-rata).

Revision ID: 20260920_0300
Revises: 20260920_0200
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa


revision = "20260920_0300"
down_revision = "20260920_0200"
branch_labels = None
depends_on = None

_COLS = [
    ("kekuatan_nilai", sa.DECIMAL(10, 3)),
    ("kekuatan_satuan", sa.String(10)),
    ("isi_kemasan", sa.DECIMAL(10, 3)),
    ("satuan_isi", sa.String(10)),
]


def _existing(bind):
    return {c["name"] for c in sa.inspect(bind).get_columns("master_produk")}


def upgrade() -> None:
    bind = op.get_bind()
    cols = _existing(bind)
    for name, tipe in _COLS:
        if name not in cols:
            op.add_column("master_produk", sa.Column(name, tipe, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    cols = _existing(bind)
    for name, _ in reversed(_COLS):
        if name in cols:
            op.drop_column("master_produk", name)
