"""M-FIN-2 (Tier 1b, Opsi A): transaksi_detail_tindakan — link treatment ke transaksi

Kontrak Data v2 gap G3-treatment. Simetris dengan transaksi_detail_produk.
Snapshot harga/diskon/BHP per treatment yang ditagih ke satu transaksi kasir.

Revision ID: 20260706_0200
Revises: 20260706_0100
Create Date: 2026-07-06 02:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "20260706_0200"
down_revision = "20260706_0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transaksi_detail_tindakan",
        sa.Column("id_detail_tindakan", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id_transaksi", sa.Integer(), nullable=False),
        sa.Column("id_kunjungan_tindakan", sa.Integer(), nullable=True),
        sa.Column("id_treatment", sa.Integer(), nullable=False),
        sa.Column("qty", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("harga_satuan", sa.DECIMAL(precision=12, scale=2), nullable=False),
        sa.Column("diskon_item", sa.DECIMAL(precision=12, scale=2), server_default="0.00", nullable=True),
        sa.Column("subtotal", sa.DECIMAL(precision=12, scale=2), nullable=False),
        sa.Column("bhp_satuan", sa.DECIMAL(precision=12, scale=2), nullable=True),
        sa.ForeignKeyConstraint(["id_transaksi"], ["transaksi_kasir.id_transaksi"], name="fk_tdt_transaksi"),
        sa.ForeignKeyConstraint(["id_kunjungan_tindakan"], ["kunjungan_tindakan.id_kunjungan_tindakan"], name="fk_tdt_kunjungan_tindakan"),
        sa.ForeignKeyConstraint(["id_treatment"], ["master_treatment.id_treatment"], name="fk_tdt_treatment"),
        sa.PrimaryKeyConstraint("id_detail_tindakan"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_tdt_transaksi", "transaksi_detail_tindakan", ["id_transaksi"])


def downgrade() -> None:
    op.drop_index("ix_tdt_transaksi", table_name="transaksi_detail_tindakan")
    op.drop_table("transaksi_detail_tindakan")
