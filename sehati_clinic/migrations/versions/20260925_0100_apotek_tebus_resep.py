"""apotek kanal penebusan resep (R1): jenis kunjungan, peresep luar, tebus lanjut, draf SOAP

Tiga asal resep yang berbeda perlakuan komisinya:
  RESEP_LUAR   — dokter di luar klinik, TANPA komisi
  RESEP_ONLINE — dokter internal jarak jauh, komisi ADA, SOAP disusun apoteker lalu
                 disetujui dokter
  TEBUS_LANJUT — resep internal dari kunjungan lama yang ditebus belakangan, komisi ke
                 peresep ASLI

Desain lengkap: `Project_Memory/DESAIN_RESEP_LUAR_APOTEK.md`.

Kenapa kolom `jenis_kunjungan` baru ada sekarang: selama ini pembeda "konsultasi" vs
"beli produk saja" HANYA hidup sebagai `"flow": "BELI_PRODUK_ONLY"` di JSON `audit_log`
(`kunjungan_service.py:522`) — tidak bisa di-query untuk UI maupun laporan. Kolom ini
menutup lubang itu sekalian.

Kenapa TEBUS_LANJUT membuat kunjungan BARU (bukan menghidupkan kunjungan lama): antrian
kasir & apotek menyaring HARI INI (`apotek_repo.list_antrian_obat`). Kunjungan lama yang
diaktifkan ulang tidak akan muncul di layar siapa pun. `id_kunjungan_asal` menautkannya
balik; `kunjungan_resep.id_resep_asal` menandai baris mana yang disalin, sekaligus jadi
SATU-SATUNYA penanda anti-tebus-ganda (tidak ada kolom "sudah ditebus" yang bisa
berselisih dengan kenyataan).

Draf SOAP menumpang tabel `pemeriksaan_klinis` (id_staf_dokter memang sudah nullable),
supaya begitu disetujui ia otomatis ikut ke riwayat, resume medis, dan tautan diagnosa.
⚠ Konsekuensinya: SEMUA query lama atas tabel itu harus disaring `status_soap='FINAL'`
— lihat peringatan §5b di dokumen desain.

Revision ID: 20260925_0100
Revises: 20260922_0400
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa


revision = "20260925_0100"
down_revision = "20260922_0400"
branch_labels = None
depends_on = None


def _cols(insp, table):
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # ---- kunjungan -----------------------------------------------------------
    cols = _cols(insp, "kunjungan")
    if "jenis_kunjungan" not in cols:
        op.add_column("kunjungan", sa.Column(
            "jenis_kunjungan", sa.String(20), nullable=False, server_default="KLINIS",
            comment="KLINIS / RESEP_LUAR / RESEP_ONLINE / TEBUS_LANJUT",
        ))
        op.create_index("ix_kunjungan_jenis", "kunjungan", ["jenis_kunjungan"])
    if "peresep_luar_nama" not in cols:
        op.add_column("kunjungan", sa.Column("peresep_luar_nama", sa.String(100), nullable=True))
    if "peresep_luar_asal" not in cols:
        op.add_column("kunjungan", sa.Column("peresep_luar_asal", sa.String(150), nullable=True))
    if "id_kunjungan_asal" not in cols:
        op.add_column("kunjungan", sa.Column(
            "id_kunjungan_asal", sa.Integer, nullable=True,
            comment="Kunjungan tempat resep ini semula ditulis (TEBUS_LANJUT).",
        ))
        op.create_foreign_key("fk_kunjungan_asal", "kunjungan", "kunjungan",
                              ["id_kunjungan_asal"], ["id_kunjungan"])

    # ---- kunjungan_resep -----------------------------------------------------
    cols = _cols(insp, "kunjungan_resep")
    if "id_resep_asal" not in cols:
        op.add_column("kunjungan_resep", sa.Column(
            "id_resep_asal", sa.Integer, nullable=True,
            comment="Baris resep asal yang disalin saat tebus lanjut. Keberadaan salinan "
                    "= penanda baris asal SUDAH ditebus (anti tebus ganda).",
        ))
        op.create_foreign_key("fk_resep_asal", "kunjungan_resep", "kunjungan_resep",
                              ["id_resep_asal"], ["id_resep"])
        op.create_index("ix_resep_asal", "kunjungan_resep", ["id_resep_asal"])

    # ---- pemeriksaan_klinis (draf SOAP apoteker) -----------------------------
    cols = _cols(insp, "pemeriksaan_klinis")
    if "status_soap" not in cols:
        op.add_column("pemeriksaan_klinis", sa.Column(
            "status_soap", sa.String(20), nullable=False, server_default="FINAL",
            comment="DRAFT_APOTEK = draf dari chat, belum disetujui dokter. FINAL = sah.",
        ))
        op.create_index("ix_soap_status", "pemeriksaan_klinis", ["status_soap"])
    if "id_staf_penyusun" not in cols:
        op.add_column("pemeriksaan_klinis", sa.Column(
            "id_staf_penyusun", sa.Integer, nullable=True,
            comment="Apoteker yang menyusun draf. TIDAK dihapus saat dokter menyetujui — "
                    "asal-usul catatan tetap terbaca.",
        ))
        op.create_foreign_key("fk_soap_penyusun", "pemeriksaan_klinis", "master_staf",
                              ["id_staf_penyusun"], ["id_staf"])
    if "waktu_konsultasi" not in cols:
        op.add_column("pemeriksaan_klinis", sa.Column(
            "waktu_konsultasi", sa.DateTime, nullable=True,
            comment="Kapan percakapan/konsultasinya terjadi — BUKAN kapan dicatat.",
        ))
    if "waktu_disetujui" not in cols:
        op.add_column("pemeriksaan_klinis", sa.Column(
            "waktu_disetujui", sa.DateTime, nullable=True,
            comment="Kapan dokter menyetujui draf. Dipisah dari waktu_konsultasi supaya "
                    "rekam medis tidak terbaca seolah pemeriksaan terjadi hari persetujuan.",
        ))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    cols = _cols(insp, "pemeriksaan_klinis")
    for nama, fk, idx in (
        ("waktu_disetujui", None, None),
        ("waktu_konsultasi", None, None),
        ("id_staf_penyusun", "fk_soap_penyusun", None),
        ("status_soap", None, "ix_soap_status"),
    ):
        if nama in cols:
            if fk:
                try:
                    op.drop_constraint(fk, "pemeriksaan_klinis", type_="foreignkey")
                except Exception:
                    pass
            if idx:
                try:
                    op.drop_index(idx, table_name="pemeriksaan_klinis")
                except Exception:
                    pass
            op.drop_column("pemeriksaan_klinis", nama)

    cols = _cols(insp, "kunjungan_resep")
    if "id_resep_asal" in cols:
        for drop, kind in (("ix_resep_asal", "index"), ("fk_resep_asal", "fk")):
            try:
                if kind == "index":
                    op.drop_index(drop, table_name="kunjungan_resep")
                else:
                    op.drop_constraint(drop, "kunjungan_resep", type_="foreignkey")
            except Exception:
                pass
        op.drop_column("kunjungan_resep", "id_resep_asal")

    cols = _cols(insp, "kunjungan")
    if "id_kunjungan_asal" in cols:
        try:
            op.drop_constraint("fk_kunjungan_asal", "kunjungan", type_="foreignkey")
        except Exception:
            pass
        op.drop_column("kunjungan", "id_kunjungan_asal")
    for nama in ("peresep_luar_asal", "peresep_luar_nama"):
        if nama in cols:
            op.drop_column("kunjungan", nama)
    if "jenis_kunjungan" in cols:
        try:
            op.drop_index("ix_kunjungan_jenis", table_name="kunjungan")
        except Exception:
            pass
        op.drop_column("kunjungan", "jenis_kunjungan")
