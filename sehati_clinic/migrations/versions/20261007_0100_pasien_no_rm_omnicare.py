"""Pasien: kolom `no_rm_omnicare` (nomor RM sistem lama, JJ-/JC-).

Disetujui dr. Hansen 2026-10-07. Klinik masih input ganda Sehati + Omnicare; Sehati
jadi SUMBER nomor RM Omnicare, sekaligus persiapan migrasi data lama.

Migrasi JINAK: satu kolom BARU yang boleh NULL + unique index. Tidak mengubah satu
baris pun — pasien yang sudah ada dibiarkan kosong (keputusan dr. Hansen: dirapikan
sendiri lewat desktop).

UNIQUE ditulis di migrasi DAN di model (`Pasien.__table_args__`). Pelajaran Temuan 34:
pagar yang hanya hidup di migrasi hilang dari DB hasil `create_all()`.
Bentuk & alasan nama kolom: app/core/no_rm_omnicare.py.
"""
import sqlalchemy as sa
from alembic import op

revision = "20261007_0100"
down_revision = "20261006_0100"
branch_labels = None
depends_on = None

TABEL = "pasien"
KOLOM = "no_rm_omnicare"
INDEKS = "ux_pasien_no_rm_omnicare"


def upgrade():
    op.add_column(TABEL, sa.Column(
        KOLOM, sa.String(10), nullable=True,
        comment="No. RM Omnicare/sistem lama, bentuk baku JJ-8123 / JC-2010. "
                "NULL = belum diisi. Unik bila diisi."))
    op.create_index(INDEKS, TABEL, [KOLOM], unique=True)


def downgrade():
    bind = op.get_bind()
    n = bind.execute(sa.text(
        f"SELECT COUNT(*) FROM {TABEL} WHERE {KOLOM} IS NOT NULL")).scalar()
    if n:
        raise RuntimeError(
            f"Downgrade DITOLAK: {n} pasien sudah punya No. RM Omnicare. Menghapus "
            f"kolom ini menghapus satu-satunya jembatan ke nomor di Omnicare.")
    op.drop_index(INDEKS, table_name=TABEL)
    op.drop_column(TABEL, KOLOM)
