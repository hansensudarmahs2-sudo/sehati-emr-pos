"""modul diagnosa: ref_diagnosa + diagnosa_paket_item + kunjungan_diagnosa

Modul #24–#27 (ICD-10 WHO + estetik internal JD-xxx, paket auto-fill, multi-diagnosa).
Desain: Project_Memory/DESAIN_MODUL_DIAGNOSA_ICD_ESTETIK.md

Non-destruktif: kolom pemeriksaan_klinis.diagnosa (teks bebas) TIDAK diubah;
tetap dipakai sebagai diagnosa naratif opsional.

Revision ID: 20260920_0100
Revises: 20260918_0100
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa


revision = "20260920_0100"
down_revision = "20260918_0100"
branch_labels = None
depends_on = None


def _tables(bind):
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    if "ref_diagnosa" not in tables:
        op.create_table(
            "ref_diagnosa",
            sa.Column("id_diagnosa", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("sistem", sa.Enum("ICD10", "ESTETIK", name="sistemdiagnosaenum"), nullable=False),
            sa.Column("kode", sa.String(20), nullable=False),
            sa.Column("nama", sa.String(255), nullable=False),
            sa.Column("nama_en", sa.String(255), nullable=True),
            sa.Column("kategori", sa.String(100), nullable=True),
            sa.Column("default_kontrol_hari", sa.Integer, nullable=False, server_default="7"),
            sa.Column("is_active", sa.Boolean, nullable=True, server_default="1"),
            sa.Column("catatan", sa.Text, nullable=True),
            sa.Column("created_at", sa.TIMESTAMP, server_default=sa.func.current_timestamp(), nullable=True),
            sa.Column("updated_at", sa.TIMESTAMP, server_default=sa.func.current_timestamp(), nullable=True),
            sa.UniqueConstraint("sistem", "kode", name="uq_refdiagnosa_sistem_kode"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
        )

    if "diagnosa_paket_item" not in tables:
        op.create_table(
            "diagnosa_paket_item",
            sa.Column("id_paket_item", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("id_diagnosa", sa.Integer, sa.ForeignKey("ref_diagnosa.id_diagnosa"), nullable=False),
            sa.Column("tipe_item", sa.Enum("TREATMENT", "PRODUK", name="tipeitempaketenum"), nullable=False),
            sa.Column("id_treatment", sa.Integer, sa.ForeignKey("master_treatment.id_treatment"), nullable=True),
            sa.Column("id_produk", sa.Integer, sa.ForeignKey("master_produk.id_produk"), nullable=True),
            sa.Column("qty_default", sa.DECIMAL(12, 2), nullable=True, server_default="1"),
            sa.Column("aturan_pakai_default", sa.String(100), nullable=True),
            sa.Column("urutan", sa.Integer, nullable=False, server_default="0"),
            sa.Column("catatan", sa.String(200), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP, server_default=sa.func.current_timestamp(), nullable=True),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
        )
        op.create_index("ix_paket_id_diagnosa", "diagnosa_paket_item", ["id_diagnosa"])

    if "kunjungan_diagnosa" not in tables:
        op.create_table(
            "kunjungan_diagnosa",
            sa.Column("id_kunjungan_diagnosa", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("id_kunjungan", sa.Integer, sa.ForeignKey("kunjungan.id_kunjungan"), nullable=False),
            sa.Column("id_diagnosa", sa.Integer, sa.ForeignKey("ref_diagnosa.id_diagnosa"), nullable=True),
            sa.Column("sistem_snapshot", sa.String(10), nullable=True),
            sa.Column("kode_snapshot", sa.String(20), nullable=True),
            sa.Column("nama_snapshot", sa.String(255), nullable=False),
            sa.Column("is_primer", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("urutan", sa.Integer, nullable=False, server_default="0"),
            sa.Column("catatan", sa.String(255), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP, server_default=sa.func.current_timestamp(), nullable=True),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
        )
        op.create_index("ix_kunjdx_id_kunjungan", "kunjungan_diagnosa", ["id_kunjungan"])


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if "kunjungan_diagnosa" in tables:
        op.drop_table("kunjungan_diagnosa")
    if "diagnosa_paket_item" in tables:
        op.drop_table("diagnosa_paket_item")
    if "ref_diagnosa" in tables:
        op.drop_table("ref_diagnosa")
