"""kunjungan_lot_terpakai — jejak lot terpotong saat serah obat (P0-1/H2 lot-provenance).

AUDIT_SEHATI_2026-07-10: supaya void mengembalikan qty ke LOT ASLI (ED asli terjaga,
FEFO benar) alih-alih membuat lot 'VOID-RETURN' tgl_ed=NULL yang tenggelam di belakang
antrean FEFO. Diisi di serahkan_obat; dibaca _reverse_stok_per_item.

Defensif/idempoten: skip create bila tabel sudah ada.

Revision ID: 20260710_2200
Revises: 20260710_2100
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "20260710_2200"
down_revision = "20260710_2100"
branch_labels = None
depends_on = None

TABLE = "kunjungan_lot_terpakai"


def _has_table(insp) -> bool:
    return TABLE in insp.get_table_names()


def upgrade():
    insp = sa.inspect(op.get_bind())
    if _has_table(insp):
        return
    op.create_table(
        TABLE,
        sa.Column("id_terpakai", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id_kunjungan", sa.Integer(), sa.ForeignKey("kunjungan.id_kunjungan"), nullable=False),
        sa.Column("id_produk", sa.Integer(), sa.ForeignKey("master_produk.id_produk"), nullable=False),
        sa.Column("id_lot", sa.Integer(), sa.ForeignKey("stok_lot.id_lot"), nullable=False),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("reversed_at", sa.TIMESTAMP(), nullable=True,
                  comment="Diisi saat qty dikembalikan ke lot (void) — cegah double-restore."),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
    )
    op.create_index("ix_klt_kunjungan_produk", TABLE, ["id_kunjungan", "id_produk"])


def downgrade():
    insp = sa.inspect(op.get_bind())
    if _has_table(insp):
        op.drop_table(TABLE)
