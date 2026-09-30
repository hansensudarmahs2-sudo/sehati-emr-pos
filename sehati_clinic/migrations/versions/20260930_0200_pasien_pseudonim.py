"""Tabel peta pseudonim pasien untuk paket klinis (Oracle / Council AI).

⚠ TABEL PALING SENSITIF DI SISTEM — satu-satunya yang menyambungkan riwayat
  klinis di paket ekspor ke orang sungguhan.

Disetujui dr. Hansen 2026-09-30 setelah menimbang alternatif "berkas terpisah
tanpa mengubah database". Alasan tabel dipilih (keduanya diperiksa, bukan
diasumsikan):
  1. Berkas lepas TIDAK ikut backup mana pun. `deploy/backup.sh` hanya mengambil
     `mysqldump db_sehati` + `tar /app/static/uploads`; volume Docker persisten
     hanya `sehati_db_data` + `sehati_uploads`. Peta yang hilang = pseudonim tidak
     bisa dibuat ulang sama = analisis longitudinal runtuh TANPA GEJALA.
  2. Ekspor bisa jalan dari cron DAN tombol UI. UNIQUE + transaksi mencegah satu
     pasien dapat dua pid; berkas JSON tidak punya keduanya.

Migrasi ini JINAK: CREATE TABLE baru, tidak menyentuh satu pun kolom yang sudah
ada, tidak mengubah satu baris data. downgrade = DROP TABLE.

Revision ID: 20260930_0200
Revises: 20260930_0100
Create Date: 2026-09-30
"""
import sqlalchemy as sa
from alembic import op

revision = "20260930_0200"
down_revision = "20260930_0100"
branch_labels = None
depends_on = None

TABLE = "pasien_pseudonim"


def upgrade():
    insp = sa.inspect(op.get_bind())
    if TABLE in insp.get_table_names():
        print(f"[migrasi {revision}] {TABLE} sudah ada. Lewati.")
        return
    op.create_table(
        TABLE,
        sa.Column("id_pasien", sa.Integer(), nullable=False,
                  comment="Satu baris per pasien. PK menjamin tidak ada pid ganda."),
        sa.Column("pid", sa.String(16), nullable=False,
                  comment="Pseudonim acak. JANGAN PERNAH di-UPDATE — pid harus "
                          "stabil selamanya, kalau berubah riwayat longitudinal "
                          "pasien itu terputus tanpa gejala."),
        sa.Column("created_at", sa.TIMESTAMP(),
                  server_default=sa.func.current_timestamp(), nullable=True),
        sa.ForeignKeyConstraint(["id_pasien"], ["pasien.id_pasien"],
                                name="fk_pseudonim_pasien"),
        sa.PrimaryKeyConstraint("id_pasien"),
        sa.UniqueConstraint("pid", name="ux_pseudonim_pid"),
        comment="Peta id_pasien -> pid. TIDAK BOLEH ikut paket ekspor apa pun.",
    )
    print(f"[migrasi {revision}] {TABLE} dibuat. Baris diisi saat ekspor klinis "
          f"pertama (get-or-create), bukan sekarang.")


def downgrade():
    # ⚠ DROP TABLE di sini MENGHAPUS SELURUH PETA PSEUDONIM. Kalau paket klinis
    #   sudah pernah keluar, pid-nya tidak bisa dibuat ulang sama dan seluruh
    #   analisis longitudinal yang sudah berjalan menjadi tidak bisa disambung.
    #   Backup DB dulu sebelum downgrade ini dijalankan.
    insp = sa.inspect(op.get_bind())
    if TABLE in insp.get_table_names():
        op.drop_table(TABLE)
