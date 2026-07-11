"""kunjungan.catatan_kontrol — catatan rencana kontrol dokter (modul #7 follow-up).

Defensif/idempoten: skip add bila kolom sudah ada.

Revision ID: 20260707_0400
Revises: 20260707_0300
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa

revision = "20260707_0400"
down_revision = "20260707_0300"
branch_labels = None
depends_on = None

TABLE = "kunjungan"
COL = "catatan_kontrol"


def _cols(insp):
    return {c["name"] for c in insp.get_columns(TABLE)}


def upgrade():
    insp = sa.inspect(op.get_bind())
    if COL not in _cols(insp):
        op.add_column(TABLE, sa.Column(COL, sa.String(255), nullable=True))


def downgrade():
    insp = sa.inspect(op.get_bind())
    if COL in _cols(insp):
        op.drop_column(TABLE, COL)
