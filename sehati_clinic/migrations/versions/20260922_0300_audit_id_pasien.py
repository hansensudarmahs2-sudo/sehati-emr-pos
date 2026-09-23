"""audit integritas ID pasien (#18 Lapis-2): tabel keputusan 'bukan duplikat'

Modul audit menyisir tabel `pasien` untuk kandidat orang yang sama tercatat dua kali.
Sebagian kandidat memang BUKAN duplikat — kakak-adik dengan nama mirip, atau dua orang
yang kebetulan senama dan sealamat. Tanpa tempat menyimpan keputusan itu, pasangan yang
sama muncul lagi setiap kali laporan dijalankan sampai petugas berhenti membacanya, dan
laporan yang tidak dibaca tidak melindungi siapa pun.

Pasangan disimpan TERURUT (`id_pasien_a` < `id_pasien_b`) supaya (A,B) dan (B,A) tidak
bisa tersimpan dua kali; unique index menegakkannya di tingkat DB, bukan cuma di kode.

TIDAK ada kolom untuk merge di sini. Penggabungan pasien memindahkan kunjungan,
transaksi, membership, alergi dan riwayat penyakit — kalau salah, rekam medis dua orang
tercampur. Itu desain terpisah, sengaja belum dibangun.

Revision ID: 20260922_0300
Revises: 20260922_0200
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa


revision = "20260922_0300"
down_revision = "20260922_0200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "pasien_duplikat_dismiss" in set(insp.get_table_names()):
        return

    op.create_table(
        "pasien_duplikat_dismiss",
        sa.Column("id_dismiss", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("id_pasien_a", sa.Integer, sa.ForeignKey("pasien.id_pasien"),
                  nullable=False, comment="SELALU id yang lebih kecil."),
        sa.Column("id_pasien_b", sa.Integer, sa.ForeignKey("pasien.id_pasien"),
                  nullable=False, comment="SELALU id yang lebih besar."),
        sa.Column("alasan", sa.String(255), nullable=True,
                  comment="Kenapa dinyatakan bukan duplikat — untuk ditinjau ulang kelak."),
        sa.Column("id_staf", sa.Integer, sa.ForeignKey("master_staf.id_staf"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.func.current_timestamp(),
                  nullable=True),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ux_dismiss_pasangan", "pasien_duplikat_dismiss",
                    ["id_pasien_a", "id_pasien_b"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "pasien_duplikat_dismiss" in set(insp.get_table_names()):
        op.drop_table("pasien_duplikat_dismiss")
