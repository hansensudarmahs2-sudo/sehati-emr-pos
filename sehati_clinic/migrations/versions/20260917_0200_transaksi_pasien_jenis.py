"""transaksi_kasir: + id_pasien (link langsung) + jenis_transaksi (KLINIS/MEMBERSHIP).

Fondasi M2 (isolasi transaksi membership): membership jadi transaksi berdiri sendiri
(id_kunjungan=NULL) → butuh id_pasien langsung + penanda jenis. Backfill: semua
transaksi lama = KLINIS, id_pasien diisi dari kunjungan. Defensif/idempoten.

Revision ID: 20260917_0200
Revises: 20260917_0100
Create Date: 2026-09-17
"""
from alembic import op
import sqlalchemy as sa

revision = "20260917_0200"
down_revision = "20260917_0100"
branch_labels = None
depends_on = None

TABLE = "transaksi_kasir"


def _cols(insp):
    return {c["name"] for c in insp.get_columns(TABLE)}


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    have = _cols(insp)

    if "id_pasien" not in have:
        op.add_column(TABLE, sa.Column("id_pasien", sa.Integer(), nullable=True))
        op.create_index("ix_transaksi_kasir_id_pasien", TABLE, ["id_pasien"])
        # FK ke pasien (nullable; aman). Nama eksplisit utk downgrade.
        try:
            op.create_foreign_key(
                "fk_transaksi_kasir_id_pasien", TABLE, "pasien",
                ["id_pasien"], ["id_pasien"],
            )
        except Exception as e:
            print(f"[migrasi 0200] lewati FK id_pasien (non-fatal): {e}")

    if "jenis_transaksi" not in have:
        op.add_column(
            TABLE,
            sa.Column("jenis_transaksi", sa.String(20), nullable=False,
                      server_default="KLINIS"),
        )

    # Backfill id_pasien dari kunjungan (transaksi lama semua punya kunjungan).
    op.execute(
        "UPDATE transaksi_kasir t "
        "JOIN kunjungan k ON t.id_kunjungan = k.id_kunjungan "
        "SET t.id_pasien = k.id_pasien "
        "WHERE t.id_pasien IS NULL"
    )
    # jenis_transaksi lama = KLINIS (server_default sudah menangani baris lama,
    # tapi set eksplisit utk jelas).
    op.execute("UPDATE transaksi_kasir SET jenis_transaksi = 'KLINIS' WHERE jenis_transaksi IS NULL OR jenis_transaksi = ''")


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    have = _cols(insp)
    if "jenis_transaksi" in have:
        op.drop_column(TABLE, "jenis_transaksi")
    if "id_pasien" in have:
        try:
            op.drop_constraint("fk_transaksi_kasir_id_pasien", TABLE, type_="foreignkey")
        except Exception:
            pass
        try:
            op.drop_index("ix_transaksi_kasir_id_pasien", table_name=TABLE)
        except Exception:
            pass
        op.drop_column(TABLE, "id_pasien")
