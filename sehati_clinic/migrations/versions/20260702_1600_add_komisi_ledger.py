"""add tabel komisi_ledger (K-L1 modul komisi)

Revision ID: 20260702_1600
Revises: 20260702_1400
Create Date: 2026-07-02 16:00:00

Ledger komisi staf (Dokter & Perawat). 1 baris = 1 komisi diperoleh, snapshot saat bayar.
Ref KOMISI_MODULE_DESIGN.md §4 + DEC-087.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260702_1600"
down_revision = "20260702_1400"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "komisi_ledger",
        sa.Column("id_komisi", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tanggal", sa.Date(), nullable=False),
        sa.Column("id_transaksi", sa.Integer(), nullable=True),
        sa.Column("id_kunjungan", sa.Integer(), nullable=True),
        sa.Column("id_pasien", sa.Integer(), nullable=True),
        sa.Column("id_staf", sa.Integer(), nullable=False),
        sa.Column("role_snapshot", sa.String(length=20), nullable=False, comment="DOKTER / PERAWAT"),
        sa.Column("sumber", sa.String(length=20), nullable=False, comment="TINDAKAN / PRODUK"),
        sa.Column("id_ref", sa.Integer(), nullable=True, comment="id_kunjungan_tindakan / id_resep"),
        sa.Column("nama_item", sa.String(length=150), nullable=True),
        sa.Column("harga_jual", sa.DECIMAL(precision=12, scale=2), server_default="0", nullable=False),
        sa.Column("komisi_tipe", sa.String(length=20), nullable=True),
        sa.Column("komisi_value", sa.DECIMAL(precision=12, scale=2), nullable=True),
        sa.Column("komisi_nominal", sa.DECIMAL(precision=12, scale=2), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=10), server_default="AKTIF", nullable=False, comment="AKTIF / VOID"),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id_komisi"),
        sa.ForeignKeyConstraint(["id_transaksi"], ["transaksi_kasir.id_transaksi"], name="fk_komisi_transaksi"),
        sa.ForeignKeyConstraint(["id_kunjungan"], ["kunjungan.id_kunjungan"], name="fk_komisi_kunjungan"),
        sa.ForeignKeyConstraint(["id_pasien"], ["pasien.id_pasien"], name="fk_komisi_pasien"),
        sa.ForeignKeyConstraint(["id_staf"], ["master_staf.id_staf"], name="fk_komisi_staf"),
    )
    op.create_index("ix_komisi_tanggal", "komisi_ledger", ["tanggal"])
    op.create_index("ix_komisi_id_staf", "komisi_ledger", ["id_staf"])
    op.create_index("ix_komisi_id_transaksi", "komisi_ledger", ["id_transaksi"])


def downgrade() -> None:
    op.drop_index("ix_komisi_id_transaksi", table_name="komisi_ledger")
    op.drop_index("ix_komisi_id_staf", table_name="komisi_ledger")
    op.drop_index("ix_komisi_tanggal", table_name="komisi_ledger")
    op.drop_table("komisi_ledger")
