"""add stok_lot (inventory per-lot batch+ED) + backfill batch-pembuka (P-L3)

Revision ID: 20260702_2000
Revises: 20260702_1800
Create Date: 2026-07-02 20:00:00

Satu tabel stok_lot untuk produk retail + bahan/BHP. Backfill "batch pembuka" dari stok saat ini
(batch_no & tgl_ed dikosongkan). Ref INVENTORY_LOT_ED_MODULE_DESIGN.md.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260702_2000"
down_revision = "20260702_1800"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stok_lot",
        sa.Column("id_lot", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tipe_item", sa.String(length=10), nullable=False, comment="PRODUK / BAHAN"),
        sa.Column("id_produk", sa.Integer(), nullable=True),
        sa.Column("id_bahan", sa.Integer(), nullable=True),
        sa.Column("lokasi", sa.String(length=20), nullable=False, comment="RETAIL / GUDANG_UTAMA / KABIN"),
        sa.Column("batch_no", sa.String(length=50), nullable=True),
        sa.Column("tgl_ed", sa.Date(), nullable=True),
        sa.Column("qty_masuk", sa.Float(), server_default="0", nullable=False),
        sa.Column("qty_sisa", sa.Float(), server_default="0", nullable=False),
        sa.Column("harga_terima", sa.DECIMAL(precision=12, scale=2), nullable=True),
        sa.Column("id_receive", sa.Integer(), nullable=True),
        sa.Column("id_distributor", sa.Integer(), nullable=True),
        sa.Column("tgl_masuk", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=10), server_default="AKTIF", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id_lot"),
        sa.ForeignKeyConstraint(["id_produk"], ["master_produk.id_produk"], name="fk_lot_produk"),
        sa.ForeignKeyConstraint(["id_bahan"], ["inventory_stok.id_bahan"], name="fk_lot_bahan"),
        sa.ForeignKeyConstraint(["id_receive"], ["pemesanan_receive.id_receive"], name="fk_lot_receive"),
        sa.ForeignKeyConstraint(["id_distributor"], ["master_distributor.id_distributor"], name="fk_lot_distributor"),
    )
    op.create_index("ix_lot_produk", "stok_lot", ["id_produk"])
    op.create_index("ix_lot_bahan", "stok_lot", ["id_bahan"])
    op.create_index("ix_lot_ed", "stok_lot", ["tgl_ed"])
    op.create_index("ix_lot_status", "stok_lot", ["status"])

    # ---- Backfill batch-pembuka (ED & batch dikosongkan) ----
    # Produk retail
    op.execute(sa.text("""
        INSERT INTO stok_lot (tipe_item, id_produk, lokasi, qty_masuk, qty_sisa, tgl_masuk, status, created_at)
        SELECT 'PRODUK', id_produk, 'RETAIL', stok_terkini, stok_terkini, CURDATE(), 'AKTIF', NOW()
        FROM master_produk
        WHERE stok_terkini IS NOT NULL AND stok_terkini > 0
    """))
    # Bahan — Gudang Utama
    op.execute(sa.text("""
        INSERT INTO stok_lot (tipe_item, id_bahan, lokasi, qty_masuk, qty_sisa, tgl_masuk, status, created_at)
        SELECT 'BAHAN', id_bahan, 'GUDANG_UTAMA', stok_gudang_utama, stok_gudang_utama, CURDATE(), 'AKTIF', NOW()
        FROM inventory_stok
        WHERE stok_gudang_utama IS NOT NULL AND stok_gudang_utama > 0
    """))
    # Bahan — Kabin
    op.execute(sa.text("""
        INSERT INTO stok_lot (tipe_item, id_bahan, lokasi, qty_masuk, qty_sisa, tgl_masuk, status, created_at)
        SELECT 'BAHAN', id_bahan, 'KABIN', stok_kabin, stok_kabin, CURDATE(), 'AKTIF', NOW()
        FROM inventory_stok
        WHERE stok_kabin IS NOT NULL AND stok_kabin > 0
    """))


def downgrade() -> None:
    op.drop_index("ix_lot_status", table_name="stok_lot")
    op.drop_index("ix_lot_ed", table_name="stok_lot")
    op.drop_index("ix_lot_bahan", table_name="stok_lot")
    op.drop_index("ix_lot_produk", table_name="stok_lot")
    op.drop_table("stok_lot")
