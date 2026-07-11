"""Indeks audit_log — imbangi pertumbuhan pasca audit-baca (V7.2.1).

Menambah:
- ix_audit_log_waktu(waktu)                         → export staff_activity range-waktu.
- ix_audit_log_target(tabel_target,id_target,waktu) → "siapa membuka pasien X, kapan".

Defensif/idempoten: lewati pembuatan bila indeks sudah ada (aman untuk DB lama & baru).
(id_staf sudah terindeks otomatis via FK MySQL — tidak ditambah lagi.)

Revision ID: 20260707_0100
Revises: 20260706_0400
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa

revision = "20260707_0100"
down_revision = "20260706_0400"
branch_labels = None
depends_on = None

TABLE = "audit_log"
IDX_WAKTU = "ix_audit_log_waktu"
IDX_TARGET = "ix_audit_log_target"


def _existing(insp):
    return {ix["name"] for ix in insp.get_indexes(TABLE)}


def upgrade():
    insp = sa.inspect(op.get_bind())
    have = _existing(insp)
    if IDX_WAKTU not in have:
        op.create_index(IDX_WAKTU, TABLE, ["waktu"])
    if IDX_TARGET not in have:
        op.create_index(IDX_TARGET, TABLE, ["tabel_target", "id_target", "waktu"])


def downgrade():
    insp = sa.inspect(op.get_bind())
    have = _existing(insp)
    if IDX_TARGET in have:
        op.drop_index(IDX_TARGET, table_name=TABLE)
    if IDX_WAKTU in have:
        op.drop_index(IDX_WAKTU, table_name=TABLE)
