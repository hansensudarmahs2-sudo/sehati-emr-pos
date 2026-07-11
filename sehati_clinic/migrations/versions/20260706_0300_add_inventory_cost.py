"""M-FIN-3 (Tier 2): nilai stok — inventory_history + inventory_stok cost

Kontrak v2 gap G7 (mutasi bernilai) + G8-bahan (cost bahan). Aditif, NULLable.

Revision ID: 20260706_0300
Revises: 20260706_0200
Create Date: 2026-07-06 03:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "20260706_0300"
down_revision = "20260706_0200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inventory_stok", sa.Column("harga_modal", sa.DECIMAL(precision=12, scale=2), nullable=True))
    op.add_column("inventory_history", sa.Column("hpp_satuan", sa.DECIMAL(precision=12, scale=2), nullable=True))
    op.add_column("inventory_history", sa.Column("nilai_mutasi", sa.DECIMAL(precision=14, scale=2), nullable=True))


def downgrade() -> None:
    op.drop_column("inventory_history", "nilai_mutasi")
    op.drop_column("inventory_history", "hpp_satuan")
    op.drop_column("inventory_stok", "harga_modal")
