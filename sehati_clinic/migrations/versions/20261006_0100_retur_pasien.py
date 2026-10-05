"""Retur dari pasien: tabel retur_pasien + retur_pasien_lot + jenis mutasi RETUR_PASIEN.

Disetujui dr. Hansen 2026-10-05 — Project_Memory/DESAIN_RETUR_DARI_PASIEN.md §13.

Migrasi JINAK: dua tabel BARU dan satu nilai ENUM baru di AKHIR daftar
`inventory_history.jenis_mutasi`. Tidak mengubah satu baris data pun, tidak mengubah kolom
lama.

Keputusan bentuk yang penting (alasan lengkap di §13):
- `retur_pasien` SENGAJA tanpa `id_pasien`: setiap tabel ber-id_pasien wajib masuk registry
  penggabungan pasien (cek_gabung_pasien GAGAL kalau tidak), dan setiap tambahan di sana
  adalah satu tempat lagi yang bisa terlupa (CLAUDE.md §4.1). Pasien = lewat
  `id_transaksi_asal`.
- `jenis` dan `alasan_kode` ENUM, bukan VARCHAR: VARCHAR menerima nilai ngawur diam-diam
  (CLAUDE.md §4.5).
- CHECK di DB (MySQL ≥ 8.0.16; dev 8.0.46, mini PC mysql:8.0): tepat satu dari
  id_resep / id_kunjungan_racikan, dan qty > 0. Pagar di kode bisa dilewati skrip; pagar di
  DB tidak.
- `retur_pasien_lot` tabel anak: satu item bisa diserahkan dari DUA lot (FEFO), retur
  sebagian harus tahu lot mana menerima berapa.

Revision ID: 20261006_0100
Revises: 20261005_0100
Create Date: 2026-10-05
"""
import sqlalchemy as sa
from alembic import op

revision = "20261006_0100"
down_revision = "20261005_0100"
branch_labels = None
depends_on = None

INDUK = "retur_pasien"
ANAK = "retur_pasien_lot"
_MUTASI_LAMA = ("TINDAKAN", "PENJUALAN", "RESTOCK", "EXPIRED", "RUSAK", "PENYESUAIAN")
_MUTASI_BARU = _MUTASI_LAMA + ("RETUR_PASIEN",)


def _enum_sql(nilai) -> str:
    return "ENUM(" + ",".join(f"'{v}'" for v in nilai) + ")"


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tabel = set(insp.get_table_names())

    if INDUK in tabel:
        print(f"[migrasi {revision}] {INDUK} sudah ada. Lewati.")
    else:
        op.create_table(
            INDUK,
            sa.Column("id_retur", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("nomor_retur", sa.String(30), nullable=False,
                      comment="RPS-YYYY-MM-###### diturunkan dari id_retur saat INSERT."),
            sa.Column("id_transaksi_asal", sa.Integer(), nullable=False),
            sa.Column("id_resep", sa.Integer(), nullable=True),
            sa.Column("id_kunjungan_racikan", sa.Integer(), nullable=True),
            sa.Column("qty", sa.DECIMAL(10, 2), nullable=False),
            sa.Column("is_sebagian", sa.Boolean(), nullable=False,
                      comment="qty < qty diserahkan — butuh PIN Admin/Owner."),
            sa.Column("waktu_serah_asal", sa.DateTime(), nullable=False,
                      comment="Snapshot waktu_serah — bukti aturan 7 hari."),
            sa.Column("jenis", sa.Enum("REFUND", "TUKAR", name="jenis_retur_pasien"),
                      nullable=False),
            sa.Column("alasan_kode",
                      sa.Enum("TIDAK_PUAS", "ALERGI", "EFEK_SAMPING", "SALAH_PRODUK",
                              "RUSAK", "LAINNYA", name="alasan_retur_pasien"),
                      nullable=False),
            sa.Column("alasan_teks", sa.Text(), nullable=False),
            sa.Column("nilai_retur", sa.DECIMAL(12, 2), nullable=False,
                      comment="Nilai BERSIH yang dibayar pasien (proporsional qty)."),
            sa.Column("stok_kembali", sa.Boolean(), nullable=False),
            sa.Column("nilai_kerugian", sa.DECIMAL(12, 2), nullable=False,
                      server_default="0.00",
                      comment="HPP lot bila TIDAK kembali stok — dasar laporan susut."),
            sa.Column("id_refund", sa.Integer(), nullable=True),
            sa.Column("id_transaksi_pengganti", sa.Integer(), nullable=True),
            sa.Column("nilai_pengganti", sa.DECIMAL(12, 2), nullable=True),
            sa.Column("selisih_dibayar", sa.DECIMAL(12, 2), nullable=False,
                      server_default="0.00"),
            sa.Column("nilai_hangus", sa.DECIMAL(12, 2), nullable=False,
                      server_default="0.00",
                      comment="Pengganti lebih murah: sisa TIDAK dikembalikan. Diekspor ke Finance."),
            sa.Column("id_kunjungan_retur", sa.Integer(), nullable=True,
                      comment="Hanya ALERGI: kunjungan RETUR_PASIEN berisi draf SOAP."),
            sa.Column("id_alergi", sa.Integer(), nullable=True,
                      comment="Diisi saat dokter menyetujui draf (alergi otomatis)."),
            sa.Column("id_staf", sa.Integer(), nullable=False),
            sa.Column("id_staf_otorisasi", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(),
                      server_default=sa.func.current_timestamp(), nullable=True),
            sa.UniqueConstraint("nomor_retur", name="ux_retur_pasien_nomor"),
            sa.ForeignKeyConstraint(["id_transaksi_asal"], ["transaksi_kasir.id_transaksi"],
                                    name="fk_rp_trx_asal"),
            sa.ForeignKeyConstraint(["id_resep"], ["kunjungan_resep.id_resep"],
                                    name="fk_rp_resep"),
            sa.ForeignKeyConstraint(["id_kunjungan_racikan"],
                                    ["kunjungan_racikan.id_kunjungan_racikan"],
                                    name="fk_rp_racikan"),
            sa.ForeignKeyConstraint(["id_refund"], ["transaksi_refund.id_refund"],
                                    name="fk_rp_refund"),
            sa.ForeignKeyConstraint(["id_transaksi_pengganti"], ["transaksi_kasir.id_transaksi"],
                                    name="fk_rp_trx_pengganti"),
            sa.ForeignKeyConstraint(["id_kunjungan_retur"], ["kunjungan.id_kunjungan"],
                                    name="fk_rp_kunjungan_retur"),
            sa.ForeignKeyConstraint(["id_alergi"], ["pasien_alergi.id_alergi"],
                                    name="fk_rp_alergi"),
            sa.ForeignKeyConstraint(["id_staf"], ["master_staf.id_staf"], name="fk_rp_staf"),
            sa.ForeignKeyConstraint(["id_staf_otorisasi"], ["master_staf.id_staf"],
                                    name="fk_rp_staf_otorisasi"),
            sa.CheckConstraint(
                "(id_resep IS NULL) <> (id_kunjungan_racikan IS NULL)",
                name="ck_rp_satu_item"),
            sa.CheckConstraint("qty > 0", name="ck_rp_qty_positif"),
            comment="Retur obat/produk yang SUDAH diserahkan ke pasien (refund atau tukar).",
        )
        op.create_index("ix_rp_trx_asal", INDUK, ["id_transaksi_asal"])
        op.create_index("ix_rp_resep", INDUK, ["id_resep"])
        op.create_index("ix_rp_racikan", INDUK, ["id_kunjungan_racikan"])
        op.create_index("ix_rp_created", INDUK, ["created_at"])
        print(f"[migrasi {revision}] {INDUK} dibuat.")

    if ANAK in tabel:
        print(f"[migrasi {revision}] {ANAK} sudah ada. Lewati.")
    else:
        op.create_table(
            ANAK,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("id_retur", sa.Integer(), nullable=False),
            sa.Column("id_lot", sa.Integer(), nullable=False),
            sa.Column("qty", sa.DECIMAL(10, 2), nullable=False),
            sa.ForeignKeyConstraint(["id_retur"], [f"{INDUK}.id_retur"], name="fk_rpl_retur"),
            sa.ForeignKeyConstraint(["id_lot"], ["stok_lot.id_lot"], name="fk_rpl_lot"),
            sa.CheckConstraint("qty > 0", name="ck_rpl_qty_positif"),
            comment="Lot ASAL yang menerima barang kembali (hanya bila stok_kembali).",
        )
        op.create_index("ix_rpl_retur", ANAK, ["id_retur"])
        print(f"[migrasi {revision}] {ANAK} dibuat.")

    # Nilai ENUM baru di AKHIR daftar — MySQL tidak menyentuh baris yang ada.
    kolom = {c["name"]: c for c in insp.get_columns("inventory_history")}
    if "RETUR_PASIEN" in str(kolom["jenis_mutasi"]["type"]):
        print(f"[migrasi {revision}] jenis_mutasi sudah memuat RETUR_PASIEN. Lewati.")
    else:
        op.execute(f"ALTER TABLE inventory_history MODIFY jenis_mutasi "
                   f"{_enum_sql(_MUTASI_BARU)} NOT NULL")
        print(f"[migrasi {revision}] jenis_mutasi + 'RETUR_PASIEN'.")


def downgrade():
    # Downgrade DITOLAK kalau sudah ada jejak retur: membuangnya berarti menghapus catatan
    # uang yang dikembalikan & barang yang kembali ke stok, diam-diam.
    bind = op.get_bind()
    tabel = set(sa.inspect(bind).get_table_names())
    n_retur = bind.execute(sa.text(f"SELECT COUNT(*) FROM {INDUK}")).scalar() if INDUK in tabel else 0
    n_mutasi = bind.execute(sa.text(
        "SELECT COUNT(*) FROM inventory_history WHERE jenis_mutasi='RETUR_PASIEN'")).scalar()
    if n_retur or n_mutasi:
        raise RuntimeError(
            f"Downgrade {revision} DITOLAK: {n_retur} baris retur_pasien, {n_mutasi} mutasi "
            "RETUR_PASIEN. Itu jejak uang & stok — backup dan putuskan dulu.")
    if ANAK in tabel:
        op.drop_table(ANAK)
    if INDUK in tabel:
        op.drop_table(INDUK)
    op.execute(f"ALTER TABLE inventory_history MODIFY jenis_mutasi "
               f"{_enum_sql(_MUTASI_LAMA)} NOT NULL")
