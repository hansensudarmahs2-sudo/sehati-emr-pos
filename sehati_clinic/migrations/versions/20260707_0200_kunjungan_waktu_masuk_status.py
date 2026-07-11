"""kunjungan.waktu_masuk_status — untuk warna wait per-tahap (WARNA_ANTRIAN_FO).

Defensif/idempoten: skip add bila kolom sudah ada. Backfill baris in-flight =
COALESCE(tgl_kunjungan, created_at, NOW()) (kira-kira; self-heal saat transisi berikutnya).

Revision ID: 20260707_0200
Revises: 20260707_0100
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa

revision = "20260707_0200"
down_revision = "20260707_0100"
branch_labels = None
depends_on = None

TABLE = "kunjungan"
COL = "waktu_masuk_status"


def _cols(insp):
    return {c["name"] for c in insp.get_columns(TABLE)}


def upgrade():
    insp = sa.inspect(op.get_bind())
    if COL not in _cols(insp):
        op.add_column(TABLE, sa.Column(COL, sa.DateTime(), nullable=True,
                                       server_default=sa.func.current_timestamp()))
        op.execute(
            "UPDATE kunjungan SET waktu_masuk_status = "
            "COALESCE(tgl_kunjungan, created_at, NOW()) WHERE waktu_masuk_status IS NULL"
        )


def downgrade():
    insp = sa.inspect(op.get_bind())
    if COL in _cols(insp):
        op.drop_column(TABLE, COL)
