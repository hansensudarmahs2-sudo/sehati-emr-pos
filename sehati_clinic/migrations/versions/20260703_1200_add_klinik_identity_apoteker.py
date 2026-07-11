"""MK-L1: field identitas klinik (no_sia/rm_prefix/kode_klinik/is_default/is_active) + tabel klinik_apoteker

Revision ID: 20260703_1200
Revises: 20260703_1000
Create Date: 2026-07-03 12:00:00

Aditif & aman (tak rename tabel, tak sentuh CHECK singleton). Fondasi PO ideal:
- master_klinik_config: kode_klinik, rm_prefix, no_sia, is_default, is_active.
- klinik_apoteker: daftar apoteker + SIPA per klinik (dropdown saat buat PO).
Ref MASTER_KLINIK_MODULE_DESIGN.md. Rename fisik -> master_klinik ditunda sampai cabang ke-2.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260703_1200"
down_revision = "20260703_1000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("master_klinik_config", sa.Column("kode_klinik", sa.String(length=10), nullable=True))
    op.add_column("master_klinik_config", sa.Column("rm_prefix", sa.String(length=5), nullable=True))
    op.add_column("master_klinik_config", sa.Column("no_sia", sa.String(length=60), nullable=True))
    op.add_column("master_klinik_config",
                  sa.Column("is_default", sa.Boolean(), server_default="1", nullable=False))
    op.add_column("master_klinik_config",
                  sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False))

    # Set baris singleton (id_config=1) jadi klinik default; rm_prefix default 'A' (samakan env lama).
    op.execute(
        "UPDATE master_klinik_config "
        "SET is_default=1, is_active=1, "
        "rm_prefix=COALESCE(rm_prefix,'A'), kode_klinik=COALESCE(kode_klinik,'A') "
        "WHERE id_config=1"
    )

    op.create_table(
        "klinik_apoteker",
        sa.Column("id_apoteker", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id_klinik", sa.Integer(), nullable=False),
        sa.Column("nama_apoteker", sa.String(length=100), nullable=False),
        sa.Column("no_sipa", sa.String(length=60), nullable=True),
        sa.Column("masa_berlaku", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id_apoteker"),
        sa.ForeignKeyConstraint(["id_klinik"], ["master_klinik_config.id_config"],
                                name="fk_apoteker_klinik"),
    )


def downgrade() -> None:
    op.drop_table("klinik_apoteker")
    op.drop_column("master_klinik_config", "is_active")
    op.drop_column("master_klinik_config", "is_default")
    op.drop_column("master_klinik_config", "no_sia")
    op.drop_column("master_klinik_config", "rm_prefix")
    op.drop_column("master_klinik_config", "kode_klinik")
