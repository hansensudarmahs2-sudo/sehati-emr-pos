"""RT: apoteker PJ (nama+SIPA) di retur_produk (regulasi Form Retur)

Revision ID: 20260703_2400
Revises: 20260703_2200
Create Date: 2026-07-03 23:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "20260703_2400"
down_revision = "20260703_2200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("retur_produk", sa.Column("id_apoteker", sa.Integer(), nullable=True))
    op.add_column("retur_produk", sa.Column("apoteker_nama", sa.String(length=100), nullable=True))
    op.add_column("retur_produk", sa.Column("apoteker_sipa", sa.String(length=60), nullable=True))
    op.create_foreign_key("fk_retur_apoteker", "retur_produk", "klinik_apoteker",
                          ["id_apoteker"], ["id_apoteker"])


def downgrade() -> None:
    op.drop_constraint("fk_retur_apoteker", "retur_produk", type_="foreignkey")
    op.drop_column("retur_produk", "apoteker_sipa")
    op.drop_column("retur_produk", "apoteker_nama")
    op.drop_column("retur_produk", "id_apoteker")
