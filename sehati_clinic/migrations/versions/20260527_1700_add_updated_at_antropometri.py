"""add updated_at to kunjungan_antropometri

Revision ID: 20260527_1700
Revises: 0000_baseline
Create Date: 2026-05-27 17:00:00

Konteks (per smoke test Week 4):
- Endpoint `GET /antropometri/pasien/{id}/terakhir` sebelumnya pakai
  ORDER BY created_at DESC. Akibatnya kalau dokter EDIT antropometri row
  lama (created_at lebih kecil), `/terakhir` tetap return row yang LAST
  INSERTED (created_at lebih besar), bukan yang last edited.

Fix (Issue 2 Opsi A per dr. Hansen):
- Tambah kolom `updated_at` dengan ON UPDATE CURRENT_TIMESTAMP.
- Backfill existing rows: updated_at = created_at.
- Repo query ganti ORDER BY updated_at DESC (di code, bukan migrasi).
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260527_1700"
down_revision = "0000_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Tambah kolom updated_at dengan default & on-update CURRENT_TIMESTAMP
    op.add_column(
        "kunjungan_antropometri",
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
            nullable=True,
        ),
    )
    # 2. Backfill — untuk row lama, set updated_at = created_at
    op.execute(
        "UPDATE kunjungan_antropometri "
        "SET updated_at = created_at "
        "WHERE updated_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("kunjungan_antropometri", "updated_at")
