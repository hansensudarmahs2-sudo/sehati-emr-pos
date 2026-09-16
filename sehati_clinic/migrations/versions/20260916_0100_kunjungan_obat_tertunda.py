"""kunjungan.tgl_janji_kirim + catatan_kirim — modul Obat Tertunda (P1-1).

Defensif/idempoten: skip add bila kolom sudah ada. Lihat OBAT_TERTUNDA_DESIGN.md.

Revision ID: 20260916_0100
Revises: 20260710_2200
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa

revision = "20260916_0100"
down_revision = "20260710_2200"
branch_labels = None
depends_on = None

TABLE = "kunjungan"
COLS = ("tgl_janji_kirim", "catatan_kirim")


def _cols(insp):
    return {c["name"] for c in insp.get_columns(TABLE)}


def upgrade():
    insp = sa.inspect(op.get_bind())
    have = _cols(insp)
    if "tgl_janji_kirim" not in have:
        op.add_column(TABLE, sa.Column("tgl_janji_kirim", sa.Date(), nullable=True))
    if "catatan_kirim" not in have:
        op.add_column(TABLE, sa.Column("catatan_kirim", sa.String(255), nullable=True))


def downgrade():
    insp = sa.inspect(op.get_bind())
    have = _cols(insp)
    for c in ("catatan_kirim", "tgl_janji_kirim"):
        if c in have:
            op.drop_column(TABLE, c)
