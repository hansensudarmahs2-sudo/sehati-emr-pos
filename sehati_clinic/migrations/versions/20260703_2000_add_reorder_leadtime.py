"""DYN-L1: lead_time_hari + safety_hari di master_klinik_config (stok minimal dinamis)

Revision ID: 20260703_2000
Revises: 20260703_1800
Create Date: 2026-07-03 20:00:00

Aditif. Setting global untuk reorder point dinamis: ambang = MAX(stok_minimal manual, ROP dinamis)
di mana ROP = rata2 pemakaian harian (90 hari) × (lead_time + safety). Ref diskusi 2026-07-03.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260703_2000"
down_revision = "20260703_1800"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("master_klinik_config",
                  sa.Column("lead_time_hari", sa.Integer(), server_default="14", nullable=False))
    op.add_column("master_klinik_config",
                  sa.Column("safety_hari", sa.Integer(), server_default="7", nullable=False))


def downgrade() -> None:
    op.drop_column("master_klinik_config", "safety_hari")
    op.drop_column("master_klinik_config", "lead_time_hari")
