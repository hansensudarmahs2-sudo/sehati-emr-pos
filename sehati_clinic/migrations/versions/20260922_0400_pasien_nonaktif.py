"""nonaktifkan pasien duplikat (#18): status aktif + jejak penggabungan

Rekam medis tidak menghapus pasien. Kunjungan, transaksi, resep dan komisi semuanya
menunjuk ke `id_pasien`; menghapus barisnya memutus rujukan itu dan riwayatnya tidak
bisa dipulihkan.

Ada bahaya kedua yang lebih halus: `PasienRepository.generate_next_no_rm` menentukan
nomor berikutnya dari **nomor TERTINGGI yang ada** pada tanggal itu. Jadi menghapus
pasien terakhir hari ini membuat pendaftaran berikutnya mendapat nomor yang SAMA —
daur ulang RM yang terjadi tanpa peringatan. Nomor RM dipakai di luar sistem juga
(formulir kertas, label foto, surat rujukan, nota tercetak, audit_log); kalau kelak
menunjuk orang lain, rujukan lama itu jadi salah orang dan tidak bisa diperbaiki
secara surut.

Karena itu: pasien **dinonaktifkan**, nomornya **dipensiunkan**. Lompatan urutan tidak
merugikan siapa pun — tidak ada yang membaca no_rm sebagai hitungan pasien.

`nomor_ktp` duplikat DILEPAS saat nonaktif (disimpan di `nomor_ktp_lama`), supaya NIK
itu bisa dipakai pasien yang bertahan. Tanpa ini, unique index NIK yang menyusul akan
memblokir pasien yang benar gara-gara duplikat yang sudah mati memegang NIK-nya.

Revision ID: 20260922_0400
Revises: 20260922_0300
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa


revision = "20260922_0400"
down_revision = "20260922_0300"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("pasien")}

    if "is_active" not in cols:
        op.add_column("pasien", sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default="1",
            comment="0 = NONAKTIF (duplikat/keliru). Hilang dari pencarian, data tetap utuh.",
        ))
        op.create_index("ix_pasien_is_active", "pasien", ["is_active"])
    if "nonaktif_at" not in cols:
        op.add_column("pasien", sa.Column("nonaktif_at", sa.DateTime, nullable=True))
    if "nonaktif_alasan" not in cols:
        op.add_column("pasien", sa.Column("nonaktif_alasan", sa.String(255), nullable=True))
    if "id_staf_nonaktif" not in cols:
        op.add_column("pasien", sa.Column("id_staf_nonaktif", sa.Integer, nullable=True))
        op.create_foreign_key("fk_pasien_staf_nonaktif", "pasien", "master_staf",
                              ["id_staf_nonaktif"], ["id_staf"])
    if "digabung_ke_id_pasien" not in cols:
        op.add_column("pasien", sa.Column(
            "digabung_ke_id_pasien", sa.Integer, nullable=True,
            comment="Pasien yang BERTAHAN. Petunjuk ke mana riwayat orang ini seharusnya dibaca.",
        ))
        op.create_foreign_key("fk_pasien_digabung_ke", "pasien", "pasien",
                              ["digabung_ke_id_pasien"], ["id_pasien"])
    if "nomor_ktp_lama" not in cols:
        op.add_column("pasien", sa.Column(
            "nomor_ktp_lama", sa.String(30), nullable=True,
            comment="NIK yang DILEPAS saat nonaktif — disimpan supaya jejaknya tidak hilang.",
        ))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("pasien")}

    for nama, fk in (
        ("nomor_ktp_lama", None),
        ("digabung_ke_id_pasien", "fk_pasien_digabung_ke"),
        ("id_staf_nonaktif", "fk_pasien_staf_nonaktif"),
        ("nonaktif_alasan", None),
        ("nonaktif_at", None),
    ):
        if nama in cols:
            if fk:
                try:
                    op.drop_constraint(fk, "pasien", type_="foreignkey")
                except Exception:
                    pass
            op.drop_column("pasien", nama)
    if "is_active" in cols:
        try:
            op.drop_index("ix_pasien_is_active", table_name="pasien")
        except Exception:
            pass
        op.drop_column("pasien", "is_active")
