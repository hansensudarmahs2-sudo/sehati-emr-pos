"""extend jadwal_booking untuk modul Booking (dokter dituju, keluhan, audit, reserved siap-bayar)

Revision ID: 20260629_0900
Revises: 20260627_1200
Create Date: 2026-06-29 09:00:00

Konteks (Modul Booking Fase 1, BOOKING_MODULE_DESIGN.md):
- jadwal_booking sudah ada (tgl/jam/status/pasien). Tambah field yang dibutuhkan UI kalender +
  alur check-in, plus kolom RESERVED untuk booking-berbayar (deposit PARKIR, belum dipakai).
"""

from alembic import op
import sqlalchemy as sa


revision = "20260629_0900"
down_revision = "20260627_1200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jadwal_booking", sa.Column("id_staf_dokter_dituju", sa.Integer(), nullable=True))
    op.add_column("jadwal_booking", sa.Column("keluhan_utama", sa.Text(), nullable=True))
    op.add_column("jadwal_booking", sa.Column("catatan", sa.Text(), nullable=True))
    op.add_column("jadwal_booking", sa.Column("id_staf_input", sa.Integer(), nullable=True))
    op.add_column(
        "jadwal_booking",
        sa.Column(
            "updated_at", sa.TIMESTAMP(),
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
            nullable=True,
        ),
    )
    # RESERVED (siap-bayar; belum dipakai)
    op.add_column("jadwal_booking", sa.Column("biaya_booking", sa.DECIMAL(precision=12, scale=2), nullable=True))
    op.add_column("jadwal_booking", sa.Column("status_pembayaran_booking", sa.String(length=20), nullable=True))

    op.create_foreign_key(
        "fk_booking_dokter_dituju", "jadwal_booking", "master_staf",
        ["id_staf_dokter_dituju"], ["id_staf"],
    )
    op.create_foreign_key(
        "fk_booking_staf_input", "jadwal_booking", "master_staf",
        ["id_staf_input"], ["id_staf"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_booking_dokter_dituju", "jadwal_booking", type_="foreignkey")
    op.drop_constraint("fk_booking_staf_input", "jadwal_booking", type_="foreignkey")
    for col in (
        "status_pembayaran_booking", "biaya_booking", "updated_at",
        "id_staf_input", "catatan", "keluhan_utama", "id_staf_dokter_dituju",
    ):
        op.drop_column("jadwal_booking", col)
