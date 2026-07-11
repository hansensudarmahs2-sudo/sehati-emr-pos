"""add master_distributor (P-L1)

Revision ID: 20260702_1800
Revises: 20260702_1600
Create Date: 2026-07-02 18:00:00

Master distributor/pemasok untuk pengadaan (PO + faktur penerimaan).
Ref INVENTORY_LOT_ED_MODULE_DESIGN.md.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260702_1800"
down_revision = "20260702_1600"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "master_distributor",
        sa.Column("id_distributor", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nama", sa.String(length=100), nullable=False),
        sa.Column("alamat", sa.Text(), nullable=True),
        sa.Column("telepon", sa.String(length=30), nullable=True),
        sa.Column("email", sa.String(length=100), nullable=True),
        sa.Column("kontak_person", sa.String(length=100), nullable=True, comment="PIC / narahubung"),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id_distributor"),
    )


def downgrade() -> None:
    op.drop_table("master_distributor")
