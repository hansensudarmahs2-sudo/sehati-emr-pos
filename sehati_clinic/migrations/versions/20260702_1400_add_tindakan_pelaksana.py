"""add id_dokter_pelaksana + id_perawat_pelaksana ke kunjungan_tindakan (K-L0 komisi)

Revision ID: 20260702_1400
Revises: 20260702_1000
Create Date: 2026-07-02 14:00:00

Fondasi modul Komisi (DEC-087). Atribusi komisi butuh 2 pelaksana per tindakan:
- id_dokter_pelaksana → penerima komisi_dokter (auto = dokter yang di-assign kunjungan).
- id_perawat_pelaksana → penerima komisi_perawat (perawat yang memulai tindakan).
Keduanya nullable; rate 0 / pelaksana kosong = tak ada komisi untuk role itu.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260702_1400"
down_revision = "20260702_1000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("kunjungan_tindakan",
        sa.Column("id_dokter_pelaksana", sa.Integer(), nullable=True,
                  comment="Dokter pelaksana (komisi_dokter). Auto = dokter assigned kunjungan."))
    op.add_column("kunjungan_tindakan",
        sa.Column("id_perawat_pelaksana", sa.Integer(), nullable=True,
                  comment="Perawat pelaksana (komisi_perawat) = perawat yang memulai tindakan."))
    op.create_foreign_key("fk_ktindakan_dokter_pelaksana", "kunjungan_tindakan",
                          "master_staf", ["id_dokter_pelaksana"], ["id_staf"])
    op.create_foreign_key("fk_ktindakan_perawat_pelaksana", "kunjungan_tindakan",
                          "master_staf", ["id_perawat_pelaksana"], ["id_staf"])


def downgrade() -> None:
    op.drop_constraint("fk_ktindakan_perawat_pelaksana", "kunjungan_tindakan", type_="foreignkey")
    op.drop_constraint("fk_ktindakan_dokter_pelaksana", "kunjungan_tindakan", type_="foreignkey")
    op.drop_column("kunjungan_tindakan", "id_perawat_pelaksana")
    op.drop_column("kunjungan_tindakan", "id_dokter_pelaksana")
