"""baseline: existing schema dari manual SQL migrations (001-004)

Revision ID: 0000_baseline
Revises:
Create Date: 2026-05-03 18:30:00

Baseline ini di-stamp ke DB yang sudah punya skema lengkap hasil
migrasi manual SQL (file 001_fix_kritis.sql sampai 004_audit_log.sql
plus seed master_membership).

upgrade()/downgrade() sengaja kosong — fungsinya hanya marker.
Revision berikutnya (saat ORM models dibuat di Minggu 2) akan punya
down_revision yang point ke baseline ini.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = "0000_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op. Skema sudah ada via manual SQL migration."""
    pass


def downgrade() -> None:
    """No-op. Tidak boleh rollback baseline."""
    pass
