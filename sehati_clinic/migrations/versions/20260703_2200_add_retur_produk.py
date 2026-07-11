"""RT-L1: tabel retur_produk + retur_produk_item

Revision ID: 20260703_2200
Revises: 20260703_2000
Create Date: 2026-07-03 22:00:00

Retur produk mendekati ED ke distributor. Approve = potong lot. Ref RETUR_MODULE_DESIGN §7/§8.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260703_2200"
down_revision = "20260703_2000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "retur_produk",
        sa.Column("id_retur", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nomor_retur", sa.String(length=50), nullable=False),
        sa.Column("tgl_retur", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("id_distributor", sa.Integer(), nullable=True),
        sa.Column("alasan", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=15), server_default="DRAFT", nullable=False),
        sa.Column("jenis_penyelesaian", sa.String(length=15), nullable=True),
        sa.Column("id_staf_pembuat", sa.Integer(), nullable=False),
        sa.Column("id_staf_approver", sa.Integer(), nullable=True),
        sa.Column("tgl_approve", sa.DateTime(), nullable=True),
        sa.Column("nomor_nota", sa.String(length=100), nullable=True),
        sa.Column("tgl_nota", sa.Date(), nullable=True),
        sa.Column("total_nilai", sa.DECIMAL(precision=14, scale=2), nullable=True),
        sa.Column("catatan", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id_retur"),
        sa.UniqueConstraint("nomor_retur", name="uq_retur_nomor"),
        sa.ForeignKeyConstraint(["id_distributor"], ["master_distributor.id_distributor"], name="fk_retur_dist"),
        sa.ForeignKeyConstraint(["id_staf_pembuat"], ["master_staf.id_staf"], name="fk_retur_pembuat"),
        sa.ForeignKeyConstraint(["id_staf_approver"], ["master_staf.id_staf"], name="fk_retur_approver"),
    )
    op.create_table(
        "retur_produk_item",
        sa.Column("id_retur_item", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id_retur", sa.Integer(), nullable=False),
        sa.Column("id_produk", sa.Integer(), nullable=True),
        sa.Column("id_lot", sa.Integer(), nullable=True),
        sa.Column("nama_snapshot", sa.String(length=100), nullable=False),
        sa.Column("batch_no", sa.String(length=50), nullable=True),
        sa.Column("tgl_ed", sa.Date(), nullable=True),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("harga_terima", sa.DECIMAL(precision=12, scale=2), nullable=True),
        sa.Column("alasan_item", sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint("id_retur_item"),
        sa.ForeignKeyConstraint(["id_retur"], ["retur_produk.id_retur"], ondelete="CASCADE", name="fk_returitem_retur"),
        sa.ForeignKeyConstraint(["id_produk"], ["master_produk.id_produk"], name="fk_returitem_produk"),
        sa.ForeignKeyConstraint(["id_lot"], ["stok_lot.id_lot"], name="fk_returitem_lot"),
    )


def downgrade() -> None:
    op.drop_table("retur_produk_item")
    op.drop_table("retur_produk")
