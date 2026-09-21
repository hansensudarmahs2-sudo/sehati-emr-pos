"""racikan: master_biaya_racik + master_racikan + master_racikan_bahan

Fase 1 modul racikan. Formula menyimpan KOMPOSISI (bukan harga); harga dihitung
saat dipakai dari harga bahan terkini + tarif flat ongkos racik.
Desain: Project_Memory/DESAIN_MODUL_RACIKAN.md

Tarif awal (keputusan dr. Hansen 2026-09-20): KAPSUL 50.000, PUYER 50.000, KRIM 0.

Revision ID: 20260921_0100
Revises: 20260920_0300
Create Date: 2026-09-21
"""
from alembic import op
import sqlalchemy as sa


revision = "20260921_0100"
down_revision = "20260920_0300"
branch_labels = None
depends_on = None


def _tables(bind):
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    if "master_biaya_racik" not in tables:
        op.create_table(
            "master_biaya_racik",
            sa.Column("id_biaya_racik", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("jenis_racik", sa.String(20), nullable=False, unique=True),
            sa.Column("nama", sa.String(50), nullable=False),
            sa.Column("tarif", sa.DECIMAL(12, 2), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean, nullable=True, server_default="1"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
        )

    if "master_racikan" not in tables:
        op.create_table(
            "master_racikan",
            sa.Column("id_racikan", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("nama", sa.String(100), nullable=False),
            sa.Column("jenis_racik", sa.String(20), nullable=False),
            sa.Column("default_jumlah_unit", sa.Integer, nullable=False, server_default="1"),
            sa.Column("default_aturan_pakai", sa.String(100), nullable=True),
            sa.Column("catatan", sa.Text, nullable=True),
            sa.Column("is_active", sa.Boolean, nullable=True, server_default="1"),
            sa.Column("created_at", sa.TIMESTAMP, server_default=sa.func.current_timestamp(), nullable=True),
            sa.Column("updated_at", sa.TIMESTAMP, server_default=sa.func.current_timestamp(), nullable=True),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
        )

    if "master_racikan_bahan" not in tables:
        op.create_table(
            "master_racikan_bahan",
            sa.Column("id_racikan_bahan", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("id_racikan", sa.Integer, sa.ForeignKey("master_racikan.id_racikan"), nullable=False),
            sa.Column("id_produk", sa.Integer, sa.ForeignKey("master_produk.id_produk"), nullable=False),
            sa.Column("dosis_per_unit", sa.DECIMAL(10, 3), nullable=False),
            sa.Column("satuan_dosis", sa.String(10), nullable=False, server_default="mg"),
            sa.Column("urutan", sa.Integer, nullable=False, server_default="0"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
        )
        op.create_index("ix_racikanbahan_id_racikan", "master_racikan_bahan", ["id_racikan"])

    # Seed tarif — idempoten lewat UNIQUE(jenis_racik).
    op.execute(
        "INSERT IGNORE INTO master_biaya_racik (jenis_racik, nama, tarif, is_active) VALUES "
        "('KAPSUL','Racik Kapsul',50000,1),"
        "('PUYER','Racik Puyer',50000,1),"
        "('KRIM','Racik Krim',0,1)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if "master_racikan_bahan" in tables:
        op.drop_table("master_racikan_bahan")
    if "master_racikan" in tables:
        op.drop_table("master_racikan")
    if "master_biaya_racik" in tables:
        op.drop_table("master_biaya_racik")
