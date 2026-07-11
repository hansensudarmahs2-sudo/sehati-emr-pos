"""add id_lot/batch_no/tgl_ed ke stock_opname_item (opname per-batch, P-L9a)

Revision ID: 20260703_1000
Revises: 20260702_2200
Create Date: 2026-07-03 10:00:00

Opname per-batch untuk PRODUK/RETAIL: 1 baris item = 1 lot.
- id_lot  : FK stok_lot (NULL utk BAHAN agregat lama, atau "batch baru ditemukan").
- batch_no: snapshot / entry No.batch (utk display & lot baru).
- tgl_ed  : snapshot / entry ED (utk lot baru).
Ref INVENTORY_LOT_ED_MODULE_DESIGN.md §12 (opname langsung per-batch).
"""
from alembic import op
import sqlalchemy as sa

revision = "20260703_1000"
down_revision = "20260702_2200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stock_opname_item", sa.Column("id_lot", sa.Integer(), nullable=True))
    op.add_column("stock_opname_item", sa.Column("batch_no", sa.String(length=50), nullable=True))
    op.add_column("stock_opname_item", sa.Column("tgl_ed", sa.Date(), nullable=True))
    op.create_foreign_key(
        "fk_opname_item_lot", "stock_opname_item", "stok_lot",
        ["id_lot"], ["id_lot"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_opname_item_lot", "stock_opname_item", type_="foreignkey")
    op.drop_column("stock_opname_item", "tgl_ed")
    op.drop_column("stock_opname_item", "batch_no")
    op.drop_column("stock_opname_item", "id_lot")
