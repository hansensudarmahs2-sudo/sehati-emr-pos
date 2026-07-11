"""add kasir_closing (Tutup Kasir / Rekonsiliasi — Kasir-1)

Revision ID: 20260627_0900
Revises: 20260527_1700
Create Date: 2026-06-27 09:00:00

Konteks (Kasir-1, dr. Hansen):
- Sehati sudah hitung total SISTEM per metode (rekap_shift) tapi belum ada
  workflow cocokkan dengan uang FISIK + catat selisih + simpan closing record.
- Tabel `kasir_closing` = sesi shift kasir dengan siklus OPEN -> CLOSED.
  - OPEN   : dibuat saat Buka Kasir (set modal_awal + shift_mulai).
  - CLOSED : dilengkapi saat Tutup Kasir (counted per metode, selisih).

Keputusan dr. Hansen (2026-06-27):
- Detail per metode = JSON column (`detail_metode`), bukan tabel terpisah.
- Buka Kasir eksplisit (Phase 1.5): modal_awal di-set saat Buka Kasir,
  anchor expected = shift_mulai baris ini (independen dari waktu login).
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260627_0900"
down_revision = "20260527_1700"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kasir_closing",
        sa.Column("id_closing", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id_staf_kasir", sa.Integer(), nullable=False),
        # Siklus shift
        sa.Column("shift_mulai", sa.DateTime(), nullable=False),
        sa.Column("shift_tutup", sa.DateTime(), nullable=True),
        sa.Column(
            "status", sa.String(length=20),
            server_default="OPEN", nullable=False,
        ),
        # Modal & rekonsiliasi
        sa.Column(
            "modal_awal", sa.DECIMAL(precision=12, scale=2),
            server_default="0.00", nullable=False,
        ),
        sa.Column("total_expected", sa.DECIMAL(precision=12, scale=2), nullable=True),
        sa.Column("total_counted", sa.DECIMAL(precision=12, scale=2), nullable=True),
        sa.Column("total_selisih", sa.DECIMAL(precision=12, scale=2), nullable=True),
        sa.Column("detail_metode", sa.JSON(), nullable=True),
        sa.Column("catatan", sa.Text(), nullable=True),
        # Audit aktor
        sa.Column("id_staf_buka", sa.Integer(), nullable=True),
        sa.Column("id_staf_tutup", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True,
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(),
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["id_staf_kasir"], ["master_staf.id_staf"]),
        sa.ForeignKeyConstraint(["id_staf_buka"], ["master_staf.id_staf"]),
        sa.ForeignKeyConstraint(["id_staf_tutup"], ["master_staf.id_staf"]),
        sa.PrimaryKeyConstraint("id_closing"),
    )
    # Index: cari sesi OPEN per kasir (cepat untuk cek "sudah buka kasir?")
    op.create_index(
        "ix_kasir_closing_kasir_status",
        "kasir_closing",
        ["id_staf_kasir", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_kasir_closing_kasir_status", table_name="kasir_closing")
    op.drop_table("kasir_closing")
