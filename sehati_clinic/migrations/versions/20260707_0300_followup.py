"""followup — tabel modul reminder follow-up (#7).

Konsep per-item treatment (konsultasi=treatment) — lihat FOLLOWUP_REMINDER_DESIGN.md.
Defensif/idempoten: skip create bila tabel sudah ada.

Revision ID: 20260707_0300
Revises: 20260707_0200
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa

revision = "20260707_0300"
down_revision = "20260707_0200"
branch_labels = None
depends_on = None

TABLE = "followup"
JENIS = ("KONSULTASI", "TREATMENT")
STATUS = ("PENDING", "CONFIRMED", "RESCHEDULED", "NO_ANSWER", "CANCELLED")


def upgrade():
    insp = sa.inspect(op.get_bind())
    if TABLE in insp.get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id_followup", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id_pasien", sa.Integer(), nullable=False),
        sa.Column("id_kunjungan", sa.Integer(), nullable=False),
        sa.Column("id_treatment", sa.Integer(), nullable=True),
        sa.Column("jenis", sa.Enum(*JENIS, name="jenisfollowupenum"), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.Enum(*STATUS, name="statusfollowupenum"),
                  server_default="PENDING", nullable=False),
        sa.Column("id_staf_handler", sa.Integer(), nullable=True),
        sa.Column("waktu_handle", sa.DateTime(), nullable=True),
        sa.Column("catatan", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(),
                  server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["id_pasien"], ["pasien.id_pasien"]),
        sa.ForeignKeyConstraint(["id_kunjungan"], ["kunjungan.id_kunjungan"]),
        sa.ForeignKeyConstraint(["id_treatment"], ["master_treatment.id_treatment"]),
        sa.ForeignKeyConstraint(["id_staf_handler"], ["master_staf.id_staf"]),
        sa.PrimaryKeyConstraint("id_followup"),
    )
    op.create_index("ix_followup_due_status", TABLE, ["due_date", "status"])
    op.create_index("ix_followup_pasien", TABLE, ["id_pasien"])
    op.create_index("ix_followup_kunjungan", TABLE, ["id_kunjungan"])


def downgrade():
    insp = sa.inspect(op.get_bind())
    if TABLE in insp.get_table_names():
        op.drop_table(TABLE)
