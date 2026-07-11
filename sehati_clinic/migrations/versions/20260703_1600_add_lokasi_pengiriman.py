"""SHIP-L1: master lokasi_pengiriman (ship-to) + kolom kirim-ke di pemesanan

Revision ID: 20260703_1600
Revises: 20260703_1400
Create Date: 2026-07-03 16:00:00

Aditif. Ref NOTA_PO_FAKTUR_IMPROVEMENTS §E. Alamat "kirim ke" fleksibel (klinik/gudang/purchasing),
terpisah dari identitas klinik (Opsi A, bukan master_klinik). PO snapshot nama+alamat kirim.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260703_1600"
down_revision = "20260703_1400"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lokasi_pengiriman",
        sa.Column("id_lokasi", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nama", sa.String(length=100), nullable=False),
        sa.Column("alamat", sa.Text(), nullable=True),
        sa.Column("telepon", sa.String(length=30), nullable=True),
        sa.Column("kontak_person", sa.String(length=100), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id_lokasi"),
    )
    op.add_column("pemesanan", sa.Column("id_lokasi_pengiriman", sa.Integer(), nullable=True))
    op.add_column("pemesanan", sa.Column("kirim_ke_nama", sa.String(length=100), nullable=True))
    op.add_column("pemesanan", sa.Column("kirim_ke_alamat", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_pemesanan_lokasi", "pemesanan", "lokasi_pengiriman",
        ["id_lokasi_pengiriman"], ["id_lokasi"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_pemesanan_lokasi", "pemesanan", type_="foreignkey")
    op.drop_column("pemesanan", "kirim_ke_alamat")
    op.drop_column("pemesanan", "kirim_ke_nama")
    op.drop_column("pemesanan", "id_lokasi_pengiriman")
    op.drop_table("lokasi_pengiriman")
