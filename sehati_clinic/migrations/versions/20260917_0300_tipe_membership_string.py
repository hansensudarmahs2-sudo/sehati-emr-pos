"""pasien.tipe_membership: ENUM(REGULAR/VIP/VVIP) -> VARCHAR(20) (tier bebas).

Mendukung nama tier custom (mis. Platinum) dari master_membership. Nilai lama
(REGULAR/VIP/VVIP) tetap valid. Sumber kebenaran benefit = history ACTIVE.

Revision ID: 20260917_0300
Revises: 20260917_0200
Create Date: 2026-09-17
"""
from alembic import op
import sqlalchemy as sa

revision = "20260917_0300"
down_revision = "20260917_0200"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE pasien MODIFY COLUMN tipe_membership VARCHAR(20) "
        "NULL DEFAULT 'REGULAR'"
    )


def downgrade():
    op.execute(
        "ALTER TABLE pasien MODIFY COLUMN tipe_membership "
        "ENUM('REGULAR','VIP','VVIP') NULL DEFAULT 'REGULAR'"
    )
