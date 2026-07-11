"""add master_penyakit_kronis (vocab bersama) + kode_penyakit di pasien_penyakit_kronis

Revision ID: 20260627_1200
Revises: 20260627_0900
Create Date: 2026-06-27 12:00:00

Konteks (Fondasi konektor AI + upgrade data Sehati):
- Penyakit kronis Sehati sebelumnya murni free text (pasien_penyakit_kronis.nama_penyakit).
- Tambah master kanonik `master_penyakit_kronis` (kode stabil) = kosakata BERSAMA Sehati +
  modul AI (Antropometri/DermAI). Ref CONTRACT_SEHATI_ANTROPOMETRI_v0.1.md §5.
- `kode = 99` dipakukan untuk "Lain-lain (free text)".
- `pasien_penyakit_kronis.kode_penyakit` (nullable) menautkan baris ke master.
  Data lama tetap valid (kode NULL) — migrasi best-effort match dilakukan di service/script terpisah.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260627_1200"
down_revision = "20260627_0900"
branch_labels = None
depends_on = None


# Seed kanonik (draft — dr. Hansen boleh koreksi via UI/master nanti).
_SEED = [
    {"kode": 1, "nama": "Diabetes Mellitus", "urutan": 1},
    {"kode": 2, "nama": "Hipertensi", "urutan": 2},
    {"kode": 3, "nama": "Penyakit Jantung", "urutan": 3},
    {"kode": 4, "nama": "Penyakit Ginjal Kronik", "urutan": 4},
    {"kode": 5, "nama": "Penyakit Hati (Liver)", "urutan": 5},
    {"kode": 6, "nama": "Asma / PPOK", "urutan": 6},
    {"kode": 7, "nama": "Gangguan Tiroid", "urutan": 7},
    {"kode": 8, "nama": "Stroke / Serebrovaskular", "urutan": 8},
    {"kode": 9, "nama": "Gangguan Makan (Eating Disorder)", "urutan": 9},
    {"kode": 10, "nama": "Masalah Ortopedik / Sendi", "urutan": 10},
    {"kode": 99, "nama": "Lain-lain", "urutan": 99},
]


def upgrade() -> None:
    master = op.create_table(
        "master_penyakit_kronis",
        sa.Column("kode", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("nama", sa.String(length=100), nullable=False),
        sa.Column("urutan", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.PrimaryKeyConstraint("kode"),
    )
    op.bulk_insert(master, _SEED)

    op.add_column(
        "pasien_penyakit_kronis",
        sa.Column("kode_penyakit", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_penyakit_kronis_kode",
        "pasien_penyakit_kronis",
        "master_penyakit_kronis",
        ["kode_penyakit"],
        ["kode"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_penyakit_kronis_kode", "pasien_penyakit_kronis", type_="foreignkey")
    op.drop_column("pasien_penyakit_kronis", "kode_penyakit")
    op.drop_table("master_penyakit_kronis")
