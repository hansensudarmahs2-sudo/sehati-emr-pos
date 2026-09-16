"""membership status_aktivasi + pasien.no_member — CS-activation (M1).

Ref: Project_Memory/MEMBERSHIP_AKTIVASI_CS_DESIGN.md. Defensif/idempoten.
Backfill: is_active=1→ACTIVE; is_active=0 & no txn→PENDING; is_active=0 & ada txn→EXPIRED.

Revision ID: 20260916_0200
Revises: 20260916_0100
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa

revision = "20260916_0200"
down_revision = "20260916_0100"
branch_labels = None
depends_on = None

STATUS = ("PENDING", "PAID", "ACTIVE", "EXPIRED", "CANCELLED")


def _cols(insp, t):
    return {c["name"] for c in insp.get_columns(t)}


def upgrade():
    insp = sa.inspect(op.get_bind())
    # 1) pasien_membership_history.status_aktivasi
    if "status_aktivasi" not in _cols(insp, "pasien_membership_history"):
        op.add_column("pasien_membership_history", sa.Column(
            "status_aktivasi", sa.Enum(*STATUS, name="statusaktivasienum"),
            server_default="PENDING", nullable=False,
        ))
        # backfill dari kombinasi lama
        op.execute("UPDATE pasien_membership_history SET status_aktivasi='ACTIVE' WHERE is_active=1")
        op.execute("UPDATE pasien_membership_history SET status_aktivasi='PENDING' WHERE is_active=0 AND id_transaksi_aktivasi IS NULL")
        op.execute("UPDATE pasien_membership_history SET status_aktivasi='EXPIRED' WHERE is_active=0 AND id_transaksi_aktivasi IS NOT NULL")
    # 2) pasien.no_member (+ unique index)
    if "no_member" not in _cols(insp, "pasien"):
        op.add_column("pasien", sa.Column("no_member", sa.String(30), nullable=True))
        existing_idx = {i["name"] for i in insp.get_indexes("pasien")}
        if "ux_pasien_no_member" not in existing_idx:
            op.create_index("ux_pasien_no_member", "pasien", ["no_member"], unique=True)


def downgrade():
    insp = sa.inspect(op.get_bind())
    if "no_member" in _cols(insp, "pasien"):
        try:
            op.drop_index("ux_pasien_no_member", table_name="pasien")
        except Exception:
            pass
        op.drop_column("pasien", "no_member")
    if "status_aktivasi" in _cols(insp, "pasien_membership_history"):
        op.drop_column("pasien_membership_history", "status_aktivasi")
