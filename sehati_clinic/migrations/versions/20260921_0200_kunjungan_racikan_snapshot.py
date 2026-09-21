"""racikan: kunjungan_racikan + kunjungan_racikan_bahan (snapshot resep racikan)

Fase 2. Harga dikunci saat dokter simpan SOAP → kasir hanya membaca.
`dipakai` = butir (mode MG, sudah CEIL) atau gram (mode GRAM, pro-rata);
angka ini yang dipotong dari stok bahan saat penyerahan (Fase 3).

Revision ID: 20260921_0200
Revises: 20260921_0100
Create Date: 2026-09-21
"""
from alembic import op
import sqlalchemy as sa


revision = "20260921_0200"
down_revision = "20260921_0100"
branch_labels = None
depends_on = None


def _tables(bind):
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    if "kunjungan_racikan" not in tables:
        op.create_table(
            "kunjungan_racikan",
            sa.Column("id_kunjungan_racikan", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("id_kunjungan", sa.Integer, sa.ForeignKey("kunjungan.id_kunjungan"), nullable=False),
            sa.Column("id_racikan", sa.Integer, sa.ForeignKey("master_racikan.id_racikan"), nullable=True),
            sa.Column("nama_snapshot", sa.String(100), nullable=False),
            sa.Column("jenis_racik", sa.String(20), nullable=False),
            sa.Column("jumlah_unit", sa.Integer, nullable=False),
            sa.Column("aturan_pakai", sa.String(100), nullable=True),
            sa.Column("subtotal_bahan", sa.DECIMAL(12, 2), nullable=False, server_default="0"),
            sa.Column("biaya_racik", sa.DECIMAL(12, 2), nullable=False, server_default="0"),
            sa.Column("total", sa.DECIMAL(12, 2), nullable=False, server_default="0"),
            sa.Column("status_item", sa.String(20), nullable=False, server_default="PENDING"),
            sa.Column("created_at", sa.TIMESTAMP, server_default=sa.func.current_timestamp(), nullable=True),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
        )
        op.create_index("ix_kunjracik_id_kunjungan", "kunjungan_racikan", ["id_kunjungan"])

    if "kunjungan_racikan_bahan" not in tables:
        op.create_table(
            "kunjungan_racikan_bahan",
            sa.Column("id_kunjungan_racikan_bahan", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("id_kunjungan_racikan", sa.Integer,
                      sa.ForeignKey("kunjungan_racikan.id_kunjungan_racikan"), nullable=False),
            sa.Column("id_produk", sa.Integer, sa.ForeignKey("master_produk.id_produk"), nullable=True),
            sa.Column("nama_snapshot", sa.String(100), nullable=False),
            sa.Column("dosis_per_unit", sa.DECIMAL(10, 3), nullable=False),
            sa.Column("satuan_dosis", sa.String(10), nullable=False),
            sa.Column("kekuatan_snapshot", sa.DECIMAL(10, 3), nullable=True),
            sa.Column("mode_hitung", sa.String(10), nullable=False, server_default="MG"),
            sa.Column("dipakai", sa.DECIMAL(12, 3), nullable=False),
            sa.Column("satuan_dipakai", sa.String(10), nullable=False),
            sa.Column("harga_satuan", sa.DECIMAL(12, 2), nullable=False),
            sa.Column("subtotal", sa.DECIMAL(12, 2), nullable=False),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
        )
        op.create_index("ix_kunjracikbahan_parent", "kunjungan_racikan_bahan", ["id_kunjungan_racikan"])


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if "kunjungan_racikan_bahan" in tables:
        op.drop_table("kunjungan_racikan_bahan")
    if "kunjungan_racikan" in tables:
        op.drop_table("kunjungan_racikan")
