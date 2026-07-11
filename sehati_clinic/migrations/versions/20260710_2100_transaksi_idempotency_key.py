"""transaksi_kasir.idempotency_key — backstop DB anti double-submit (P0-2).

AUDIT_SEHATI_2026-07-10 P0-2: dua `proses_bayar` untuk SUBMIT yang sama (double-click/
retry/race) bisa membuat transaksi + komisi ganda karena guard "sudah lunas" non-locking
dan tak ada constraint. Split/partial billing SAH (satu kunjungan boleh >1 BAYAR), jadi
dedupe di-key ke INTENT pembayaran (token per-submit), BUKAN ke id_kunjungan.

Kolom `idempotency_key` diisi per-submit dari form kasir (token stabil per render).
UNIQUE menolak submit identik yang diulang. NULL diperbolehkan duplikat di MySQL → baris
lama / tanpa token tidak bentrok.

Defensif/idempoten: skip add bila kolom/index sudah ada.

Revision ID: 20260710_2100
Revises: 20260707_0400
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "20260710_2100"
down_revision = "20260707_0400"
branch_labels = None
depends_on = None

TABLE = "transaksi_kasir"
COL = "idempotency_key"
IDX = "uq_transaksi_kasir_idempotency_key"


def _cols(insp):
    return {c["name"] for c in insp.get_columns(TABLE)}


def _indexes(insp):
    return {i["name"] for i in insp.get_indexes(TABLE)}


def upgrade():
    insp = sa.inspect(op.get_bind())
    if COL not in _cols(insp):
        op.add_column(
            TABLE,
            sa.Column(
                COL, sa.String(64), nullable=True,
                comment="Token intent pembayaran per-submit (P0-2). UNIQUE; NULL boleh duplikat.",
            ),
        )
    insp = sa.inspect(op.get_bind())
    if IDX not in _indexes(insp):
        op.create_index(IDX, TABLE, [COL], unique=True)


def downgrade():
    insp = sa.inspect(op.get_bind())
    if IDX in _indexes(insp):
        op.drop_index(IDX, table_name=TABLE)
    insp = sa.inspect(op.get_bind())
    if COL in _cols(insp):
        op.drop_column(TABLE, COL)
