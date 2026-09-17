"""pasien.nomor_ktp UNIQUE (NIK) — fleksibel: kosong=NULL (boleh banyak), unik bila diisi.

Defensif/idempoten: normalisasi ''→NULL dulu, skip bila index sudah ada,
dan guard error jelas kalau ada NIK kembar (harus dibereskan manual dulu).

Revision ID: 20260917_0100
Revises: 20260916_0200
Create Date: 2026-09-17
"""
from alembic import op
import sqlalchemy as sa

revision = "20260917_0100"
down_revision = "20260916_0200"
branch_labels = None
depends_on = None

INDEX = "ux_pasien_nomor_ktp"
TABLE = "pasien"


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. Normalisasi string kosong -> NULL (biar tidak bentrok UNIQUE).
    op.execute("UPDATE pasien SET nomor_ktp = NULL WHERE nomor_ktp = ''")

    # 2. Idempoten: kalau index sudah ada, selesai.
    existing = {ix["name"] for ix in insp.get_indexes(TABLE)}
    if INDEX in existing:
        return

    # 3. Kalau ADA NIK kembar (mis. data uji sengaja dibiarkan): JANGAN paksa
    #    unique index (akan gagal & memblok startup). Skip dgn peringatan.
    #    Perlindungan tetap ada di level aplikasi (cek NIK saat daftar/edit).
    #    Kunci unik DB bisa dipasang nanti (setelah kembar dibereskan) lewat
    #    migrasi lanjutan / jalankan create_index manual.
    dups = bind.execute(sa.text(
        "SELECT nomor_ktp, COUNT(*) AS c FROM pasien "
        "WHERE nomor_ktp IS NOT NULL AND nomor_ktp <> '' "
        "GROUP BY nomor_ktp HAVING c > 1"
    )).fetchall()
    if dups:
        daftar = ", ".join(str(d[0]) for d in dups)
        print(
            f"[migrasi 20260917_0100] LEWATI unique index NIK: masih ada NIK kembar "
            f"({daftar}). Perlindungan app tetap aktif. Bereskan kembar lalu pasang "
            f"index manual: CREATE UNIQUE INDEX {INDEX} ON {TABLE}(nomor_ktp);"
        )
        return

    # 4. Pasang UNIQUE index (NULL boleh banyak; NIK terisi wajib unik).
    op.create_index(INDEX, TABLE, ["nomor_ktp"], unique=True)


def downgrade():
    insp = sa.inspect(op.get_bind())
    existing = {ix["name"] for ix in insp.get_indexes(TABLE)}
    if INDEX in existing:
        op.drop_index(INDEX, table_name=TABLE)
