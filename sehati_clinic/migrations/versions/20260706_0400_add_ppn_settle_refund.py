"""M-FIN-4 (Tier 3): PPN jual (dormant) + tgl_settle + tabel refund

Kontrak v2 gap G11-jual (PPN penjualan, dormant non-PKP), G12 (settlement EDC), G9 (refund).
Aditif & aman: kolom NULLable/default; tabel refund baru.

Revision ID: 20260706_0400
Revises: 20260706_0300
Create Date: 2026-07-06 04:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "20260706_0400"
down_revision = "20260706_0300"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transaksi_kasir", sa.Column("dpp", sa.DECIMAL(precision=14, scale=2), nullable=True))
    op.add_column("transaksi_kasir", sa.Column("ppn", sa.DECIMAL(precision=14, scale=2), server_default="0.00", nullable=True))
    op.add_column("transaksi_kasir", sa.Column("is_kena_ppn", sa.Boolean(), server_default="0", nullable=True))
    op.add_column("transaksi_pembayaran", sa.Column("tgl_settle", sa.Date(), nullable=True))
    op.create_table(
        "transaksi_refund",
        sa.Column("id_refund", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id_transaksi", sa.Integer(), nullable=False),
        sa.Column("doc_number_refund", sa.String(length=30), nullable=True),
        sa.Column("tgl_refund", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("nilai_refund", sa.DECIMAL(precision=12, scale=2), nullable=False),
        sa.Column("metode_refund", sa.String(length=50), nullable=True),
        sa.Column("alasan", sa.Text(), nullable=True),
        sa.Column("id_staf_refund", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["id_transaksi"], ["transaksi_kasir.id_transaksi"], name="fk_refund_transaksi"),
        sa.ForeignKeyConstraint(["id_staf_refund"], ["master_staf.id_staf"], name="fk_refund_staf"),
        sa.PrimaryKeyConstraint("id_refund"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_refund_transaksi", "transaksi_refund", ["id_transaksi"])


def downgrade() -> None:
    op.drop_index("ix_refund_transaksi", table_name="transaksi_refund")
    op.drop_table("transaksi_refund")
    op.drop_column("transaksi_pembayaran", "tgl_settle")
    op.drop_column("transaksi_kasir", "is_kena_ppn")
    op.drop_column("transaksi_kasir", "ppn")
    op.drop_column("transaksi_kasir", "dpp")
