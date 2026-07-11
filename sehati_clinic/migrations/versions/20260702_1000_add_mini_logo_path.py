"""add mini_logo_path ke master_klinik_config (ikon topbar mini)

Revision ID: 20260702_1000
Revises: 20260629_0900
Create Date: 2026-07-02 10:00:00

Mini-logo = versi kecil logo untuk kotak ikon di kiri-atas (topbar). Opsional:
kalau kosong, topbar pakai huruf pertama nama klinik. Terpisah dari logo_path
(logo penuh untuk nota/dokumen) karena logo penuh sering tak pas di kotak 32px.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260702_1000"
down_revision = "20260629_0900"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "master_klinik_config",
        sa.Column("mini_logo_path", sa.String(length=200), nullable=True,
                  comment="Path relatif ke mini-logo (ikon topbar). Kosong = huruf pertama nama klinik."),
    )


def downgrade() -> None:
    op.drop_column("master_klinik_config", "mini_logo_path")
