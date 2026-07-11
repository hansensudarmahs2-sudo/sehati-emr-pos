"""M-FIN-1 (Tier 1): finance bridge fields on transaksi_kasir + transaksi_detail_produk

Kontrak Data v2 (Finance Module) — gap G1/G2/G4/G8-snapshot.
- transaksi_kasir       : + doc_number (unik, TRX-YYYY-MM-######), + updated_at (auto-bump)
- transaksi_detail_produk: + diskon_item (alokasi diskon per item), + hpp_satuan (snapshot COGS)

Aditif & aman: semua NULLable / server_default → data lama tetap valid.
Backfill: doc_number dari id_transaksi + bulan; updated_at dari waktu_bayar.

Revision ID: 20260706_0100
Revises: 20260703_2400
Create Date: 2026-07-06 01:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "20260706_0100"
down_revision = "20260703_2400"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- transaksi_kasir ---
    op.add_column("transaksi_kasir", sa.Column("doc_number", sa.String(length=30), nullable=True))
    op.add_column(
        "transaksi_kasir",
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
            nullable=True,
        ),
    )

    # --- transaksi_detail_produk ---
    op.add_column(
        "transaksi_detail_produk",
        sa.Column("diskon_item", sa.DECIMAL(precision=12, scale=2),
                  server_default="0.00", nullable=True),
    )
    op.add_column(
        "transaksi_detail_produk",
        sa.Column("hpp_satuan", sa.DECIMAL(precision=12, scale=2), nullable=True),
    )

    # --- Backfill baris lama ---
    op.execute(text(
        "UPDATE transaksi_kasir "
        "SET doc_number = CONCAT('TRX-', "
        "DATE_FORMAT(COALESCE(waktu_bayar, NOW()), '%Y-%m-'), "
        "LPAD(id_transaksi, 6, '0')) "
        "WHERE doc_number IS NULL"
    ))
    op.execute(text(
        "UPDATE transaksi_kasir "
        "SET updated_at = COALESCE(waktu_bayar, NOW()) "
        "WHERE updated_at IS NULL"
    ))

    # --- Unique index doc_number (setelah backfill) ---
    op.create_index(
        "uq_transaksi_kasir_doc_number", "transaksi_kasir", ["doc_number"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_transaksi_kasir_doc_number", table_name="transaksi_kasir")
    op.drop_column("transaksi_detail_produk", "hpp_satuan")
    op.drop_column("transaksi_detail_produk", "diskon_item")
    op.drop_column("transaksi_kasir", "updated_at")
    op.drop_column("transaksi_kasir", "doc_number")
