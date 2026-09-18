"""produk: tambah kolom kandungan + nama_dagang (topikal)

nama_produk = kode sediaan (yang tampil). kandungan boleh ditampilkan.
nama_dagang = merk asli (internal, untuk PO — tidak tampil ke pasien).

Revision ID: 20260918_0100
Revises: 20260917_0300
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa


revision = "20260918_0100"
down_revision = "20260917_0300"
branch_labels = None
depends_on = None


def _cols(bind):
    return {c["name"] for c in sa.inspect(bind).get_columns("master_produk")}


def upgrade() -> None:
    bind = op.get_bind()
    cols = _cols(bind)
    if "kandungan" not in cols:
        op.add_column("master_produk", sa.Column("kandungan", sa.String(255), nullable=True))
    if "nama_dagang" not in cols:
        op.add_column("master_produk", sa.Column("nama_dagang", sa.String(100), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    cols = _cols(bind)
    if "nama_dagang" in cols:
        op.drop_column("master_produk", "nama_dagang")
    if "kandungan" in cols:
        op.drop_column("master_produk", "kandungan")
