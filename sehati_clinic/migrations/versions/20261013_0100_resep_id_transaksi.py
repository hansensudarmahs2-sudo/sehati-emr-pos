"""kunjungan_resep.id_transaksi — resep tahu DIBAYAR oleh transaksi MANA (Audit T2-2).

Disetujui dr. Hansen 2026-10-13 (Project_Memory/AUDIT_MENDALAM_2026-10-13.md, T2-2).

Masalah: pada split billing (T1 + tagihan susulan T2 di satu kunjungan), void T2
membatalkan obat milik T1 juga — pembatal resep memilih per `id_kunjungan`, karena resep
tidak pernah mencatat transaksinya. Racikan sudah punya `id_transaksi` (dan tindakan lewat
`transaksi_detail_tindakan.id_kunjungan_tindakan`); resep satu-satunya yang tidak.

Migrasi:
1. Kolom `id_transaksi` NULL + FK + indeks (sejajar `kunjungan_racikan.id_transaksi`).
2. BACKFILL baris yang sudah lunas (DIBAYAR / DISERAHKAN): dipasangkan ke transaksi BAYAR
   PALING AWAL di kunjungannya yang `waktu_bayar >= waktu_input` — aturan yang SAMA dengan
   pemisahan tagihan susulan kasir (item baru = `waktu_input > waktu_bayar` transaksi
   sebelumnya). Baris yang tak punya pasangan dibiarkan NULL; void untuk kunjungan dengan
   >1 transaksi lalu MENOLAK alih-alih menebak (KasirService._lingkup_void).
   Data saat migrasi = trial run (CLAUDE.md §8), dampaknya kecil.
"""
import sqlalchemy as sa
from alembic import op

revision = "20261013_0100"
down_revision = "20261007_0100"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("kunjungan_resep", sa.Column(
        "id_transaksi", sa.Integer, nullable=True,
        comment="Transaksi yang membayar baris ini (Audit T2-2). NULL = belum dibayar / data lama."))
    op.create_foreign_key("fk_kr_transaksi", "kunjungan_resep", "transaksi_kasir",
                          ["id_transaksi"], ["id_transaksi"])
    op.create_index("ix_kr_transaksi", "kunjungan_resep", ["id_transaksi"])

    bind = op.get_bind()
    baris = bind.execute(sa.text(
        "SELECT id_resep, id_kunjungan, waktu_input FROM kunjungan_resep "
        "WHERE status_item IN ('DIBAYAR', 'DISERAHKAN') AND waktu_input IS NOT NULL")).all()
    for id_resep, id_kunjungan, waktu_input in baris:
        tid = bind.execute(sa.text(
            "SELECT id_transaksi FROM transaksi_kasir WHERE id_kunjungan = :k "
            "AND status_transaksi = 'BAYAR' AND waktu_bayar >= :w "
            "ORDER BY waktu_bayar, id_transaksi LIMIT 1"),
            {"k": id_kunjungan, "w": waktu_input}).scalar()
        if tid is not None:
            bind.execute(sa.text("UPDATE kunjungan_resep SET id_transaksi = :t WHERE id_resep = :r"),
                         {"t": tid, "r": id_resep})


def downgrade():
    op.drop_index("ix_kr_transaksi", table_name="kunjungan_resep")
    op.drop_constraint("fk_kr_transaksi", "kunjungan_resep", type_="foreignkey")
    op.drop_column("kunjungan_resep", "id_transaksi")
