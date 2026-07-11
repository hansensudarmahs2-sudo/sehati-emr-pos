"""PO-B: termin, validitas, apoteker penanggung jawab di pemesanan (PO ideal)

Revision ID: 20260703_1400
Revises: 20260703_1200
Create Date: 2026-07-03 14:00:00

Aditif. Ref NOTA_PO_FAKTUR_IMPROVEMENTS §B.
- termin_hari    : jatuh tempo bayar (hari) setelah barang diterima.
- validitas_hari : masa berlaku PO (hari sejak tgl PO). NULL = tanpa batas.
- id_apoteker    : FK klinik_apoteker (wajib dipilih di form).
- apoteker_nama / apoteker_sipa : snapshot saat buat PO (akurat historis di cetakan).
"""
from alembic import op
import sqlalchemy as sa

revision = "20260703_1400"
down_revision = "20260703_1200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pemesanan", sa.Column("termin_hari", sa.Integer(), nullable=True))
    op.add_column("pemesanan", sa.Column("validitas_hari", sa.Integer(), nullable=True))
    op.add_column("pemesanan", sa.Column("id_apoteker", sa.Integer(), nullable=True))
    op.add_column("pemesanan", sa.Column("apoteker_nama", sa.String(length=100), nullable=True))
    op.add_column("pemesanan", sa.Column("apoteker_sipa", sa.String(length=60), nullable=True))
    op.create_foreign_key(
        "fk_pemesanan_apoteker", "pemesanan", "klinik_apoteker",
        ["id_apoteker"], ["id_apoteker"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_pemesanan_apoteker", "pemesanan", type_="foreignkey")
    op.drop_column("pemesanan", "apoteker_sipa")
    op.drop_column("pemesanan", "apoteker_nama")
    op.drop_column("pemesanan", "id_apoteker")
    op.drop_column("pemesanan", "validitas_hari")
    op.drop_column("pemesanan", "termin_hari")
