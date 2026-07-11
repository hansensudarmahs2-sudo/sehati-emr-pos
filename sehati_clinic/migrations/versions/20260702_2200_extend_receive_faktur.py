"""extend pemesanan_receive (batch/ED/harga_terima/distributor) — P-L4 faktur

Revision ID: 20260702_2200
Revises: 20260702_2000
Create Date: 2026-07-02 22:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "20260702_2200"
down_revision = "20260702_2000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pemesanan_receive", sa.Column("batch_no", sa.String(length=50), nullable=True))
    op.add_column("pemesanan_receive", sa.Column("tgl_ed", sa.Date(), nullable=True))
    op.add_column("pemesanan_receive", sa.Column("harga_terima", sa.DECIMAL(precision=12, scale=2), nullable=True))
    op.add_column("pemesanan_receive", sa.Column("id_distributor", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_receive_distributor", "pemesanan_receive",
                          "master_distributor", ["id_distributor"], ["id_distributor"])


def downgrade() -> None:
    op.drop_constraint("fk_receive_distributor", "pemesanan_receive", type_="foreignkey")
    op.drop_column("pemesanan_receive", "id_distributor")
    op.drop_column("pemesanan_receive", "harga_terima")
    op.drop_column("pemesanan_receive", "tgl_ed")
    op.drop_column("pemesanan_receive", "batch_no")
