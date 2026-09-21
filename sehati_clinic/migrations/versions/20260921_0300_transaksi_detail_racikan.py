"""racikan Fase 3: transaksi_detail_racikan + kunjungan_racikan.id_transaksi

Kasir menagih racikan. Baris tagihannya disimpan di tabel detail SENDIRI, bukan
menumpang `transaksi_detail_produk` yang kolom `id_produk`-nya NOT NULL (satu racikan
terdiri dari banyak bahan). `kunjungan_racikan.id_transaksi` menautkan balik supaya
jejak "racikan ini ditagih di transaksi mana" bisa ditelusuri dua arah.

Revision ID: 20260921_0300
Revises: 20260921_0200
Create Date: 2026-09-21
"""
from alembic import op
import sqlalchemy as sa


revision = "20260921_0300"
down_revision = "20260921_0200"
branch_labels = None
depends_on = None


def _inspector(bind):
    return sa.inspect(bind)


def upgrade() -> None:
    bind = op.get_bind()
    insp = _inspector(bind)
    tables = set(insp.get_table_names())

    if "transaksi_detail_racikan" not in tables:
        op.create_table(
            "transaksi_detail_racikan",
            sa.Column("id_detail_racikan", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("id_transaksi", sa.Integer,
                      sa.ForeignKey("transaksi_kasir.id_transaksi"), nullable=False),
            sa.Column("id_kunjungan_racikan", sa.Integer,
                      sa.ForeignKey("kunjungan_racikan.id_kunjungan_racikan"), nullable=False),
            sa.Column("nama_snapshot", sa.String(100), nullable=False),
            sa.Column("jenis_racik", sa.String(20), nullable=False),
            sa.Column("jumlah_unit", sa.Integer, nullable=False),
            sa.Column("subtotal_bahan", sa.DECIMAL(12, 2), nullable=False, server_default="0"),
            sa.Column("biaya_racik", sa.DECIMAL(12, 2), nullable=False, server_default="0"),
            sa.Column("diskon_item", sa.DECIMAL(12, 2), nullable=False, server_default="0"),
            sa.Column("subtotal", sa.DECIMAL(12, 2), nullable=False),
            sa.Column("void_reverse_stok", sa.Boolean, nullable=False, server_default="0"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
        )
        op.create_index("ix_trxracik_id_transaksi", "transaksi_detail_racikan", ["id_transaksi"])
        op.create_index("ix_trxracik_id_kunjracik", "transaksi_detail_racikan", ["id_kunjungan_racikan"])

    if "kunjungan_racikan" in tables:
        cols = {c["name"] for c in insp.get_columns("kunjungan_racikan")}
        if "id_transaksi" not in cols:
            op.add_column(
                "kunjungan_racikan",
                sa.Column("id_transaksi", sa.Integer, nullable=True),
            )
            op.create_foreign_key(
                "fk_kunjracik_transaksi", "kunjungan_racikan", "transaksi_kasir",
                ["id_transaksi"], ["id_transaksi"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = _inspector(bind)
    tables = set(insp.get_table_names())

    if "kunjungan_racikan" in tables:
        cols = {c["name"] for c in insp.get_columns("kunjungan_racikan")}
        if "id_transaksi" in cols:
            try:
                op.drop_constraint("fk_kunjracik_transaksi", "kunjungan_racikan", type_="foreignkey")
            except Exception:
                pass
            op.drop_column("kunjungan_racikan", "id_transaksi")

    if "transaksi_detail_racikan" in tables:
        op.drop_table("transaksi_detail_racikan")
