"""FK-L1: tabel faktur_penerimaan + kolom id_faktur di pemesanan_receive

Revision ID: 20260703_1800
Revises: 20260703_1600
Create Date: 2026-07-03 18:00:00

Aditif. 1 faktur = 1 pengiriman. PPN + diskon seragam + extra_diskon (rekonsiliasi).
Ref FAKTUR_MODULE_DESIGN.md §3/§10. Status bayar/AP = fase 2 (belum).
"""
from alembic import op
import sqlalchemy as sa

revision = "20260703_1800"
down_revision = "20260703_1600"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "faktur_penerimaan",
        sa.Column("id_faktur", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id_pemesanan", sa.Integer(), nullable=False),
        sa.Column("nomor_faktur", sa.String(length=100), nullable=True),
        sa.Column("nomor_pengiriman", sa.String(length=50), nullable=True),
        sa.Column("id_distributor", sa.Integer(), nullable=True),
        sa.Column("tgl_faktur", sa.Date(), nullable=True),
        sa.Column("tgl_terima", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("ppn_persen", sa.DECIMAL(precision=5, scale=2), nullable=True),
        sa.Column("diskon_persen", sa.DECIMAL(precision=5, scale=2), nullable=True),
        sa.Column("extra_diskon", sa.DECIMAL(precision=14, scale=2), nullable=True),
        sa.Column("subtotal_order", sa.DECIMAL(precision=14, scale=2), nullable=True),
        sa.Column("subtotal_setelah_diskon", sa.DECIMAL(precision=14, scale=2), nullable=True),
        sa.Column("total_ditagih", sa.DECIMAL(precision=14, scale=2), nullable=True),
        sa.Column("id_staf_penerima", sa.Integer(), nullable=True),
        sa.Column("catatan", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id_faktur"),
        sa.ForeignKeyConstraint(["id_pemesanan"], ["pemesanan.id_pemesanan"], name="fk_faktur_po"),
        sa.ForeignKeyConstraint(["id_distributor"], ["master_distributor.id_distributor"], name="fk_faktur_dist"),
        sa.ForeignKeyConstraint(["id_staf_penerima"], ["master_staf.id_staf"], name="fk_faktur_staf"),
    )
    op.add_column("pemesanan_receive", sa.Column("id_faktur", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_receive_faktur", "pemesanan_receive", "faktur_penerimaan",
        ["id_faktur"], ["id_faktur"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_receive_faktur", "pemesanan_receive", type_="foreignkey")
    op.drop_column("pemesanan_receive", "id_faktur")
    op.drop_table("faktur_penerimaan")
