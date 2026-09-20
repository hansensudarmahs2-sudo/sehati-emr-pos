"""produk: tambah kolom golongan (untuk obat minum)

Revision ID: 20260920_0200
Revises: 20260920_0100
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa


revision = "20260920_0200"
down_revision = "20260920_0100"
branch_labels = None
depends_on = None


def _cols(bind):
    return {c["name"] for c in sa.inspect(bind).get_columns("master_produk")}


def upgrade() -> None:
    bind = op.get_bind()
    if "golongan" not in _cols(bind):
        op.add_column("master_produk", sa.Column("golongan", sa.String(50), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if "golongan" in _cols(bind):
        op.drop_column("master_produk", "golongan")
