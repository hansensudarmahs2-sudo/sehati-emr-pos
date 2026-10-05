"""Refund hari lampau: kolom penyetuju + pulihkan header yang dulu dimutasi (T32).

Disetujui dr. Hansen 2026-10-05 — lihat Project_Memory/DESAIN_T32_REFUND_HARI_LAMPAU.md.

DUA LANGKAH, urutannya disengaja:

1. SKEMA — `transaksi_refund.id_staf_otorisasi` (INT NULL, FK master_staf).
   Penyetuju (Admin/Superadmin/Owner, lewat PIN) untuk refund atas transaksi hari
   lampau. NULL = refund hari yang sama (kasir sendiri) atau baris lama.

2. DATA — kembalikan `transaksi_kasir.total_tagihan` ke nilai SEBELUM refund.
   Dulu `refund_item_tertunda` MENGURANGI header transaksi asal, sehingga omzet
   HARI ASAL turun (hari yang mungkin sudah tutup kasir & sudah diekspor). Mulai
   sekarang header tidak disentuh dan laporan mengurangi refund pada TANGGAL REFUND.
   Tanpa pemulihan ini, refund lama akan dikurangi DUA KALI.

   ⚠ HANYA refund dari jalur aplikasi yang dipulihkan — dikenali dari `id_resep`
   atau `id_kunjungan_racikan` yang terisi (jalur itu selalu mengisi salah satunya).
   `scripts/seed_finance_cleanslate.py` juga menulis refund, tapi TANPA mengurangi
   header dan tanpa kedua kolom itu; memulihkannya akan MENGGELEMBUNGKAN omzet.

   Bukti kebenaran dicetak: SUM(total_tagihan) − SUM(refund dipulihkan) sesudah
   harus SAMA dengan SUM(total_tagihan) sebelum.

⚠ Langkah 2 TIDAK idempoten sendirian. Ia satu UPDATE (atomik di InnoDB) dan
   alembic hanya menjalankan revisi ini sekali. Kalau migrasi pernah gagal SETELAH
   langkah 2 tapi SEBELUM alembic_version tercatat, JANGAN jalankan ulang begitu
   saja — periksa dulu angka yang tercetak.

Revision ID: 20261005_0100
Revises: 20260930_0200
Create Date: 2026-10-05
"""
import sqlalchemy as sa
from alembic import op

revision = "20261005_0100"
down_revision = "20260930_0200"
branch_labels = None
depends_on = None

TABLE = "transaksi_refund"
KOLOM = "id_staf_otorisasi"
FK = "fk_refund_staf_otorisasi"

# Refund yang DULU memutasi header: hanya yang ditulis jalur aplikasi.
_REFUND_JALUR_APLIKASI = "(id_resep IS NOT NULL OR id_kunjungan_racikan IS NOT NULL)"


def _total(bind) -> float:
    return float(bind.execute(sa.text(
        "SELECT COALESCE(SUM(total_tagihan), 0) FROM transaksi_kasir"
    )).scalar() or 0)


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # ---- 1. Skema ---------------------------------------------------------
    kolom_ada = {c["name"] for c in insp.get_columns(TABLE)}
    if KOLOM in kolom_ada:
        print(f"[migrasi {revision}] {TABLE}.{KOLOM} sudah ada. Lewati langkah 1.")
    else:
        op.add_column(TABLE, sa.Column(
            KOLOM, sa.Integer(), nullable=True,
            comment="Penyetuju (Admin/Superadmin/Owner via PIN) untuk refund hari lampau. "
                    "NULL = refund hari yang sama atau baris lama.",
        ))
        op.create_foreign_key(FK, TABLE, "master_staf", [KOLOM], ["id_staf"])
        print(f"[migrasi {revision}] {TABLE}.{KOLOM} ditambahkan.")

    # ---- 2. Data: pulihkan header -----------------------------------------
    n_refund, sum_refund = bind.execute(sa.text(
        f"SELECT COUNT(*), COALESCE(SUM(nilai_refund), 0) FROM {TABLE} "
        f"WHERE {_REFUND_JALUR_APLIKASI}"
    )).one()
    n_lain = bind.execute(sa.text(
        f"SELECT COUNT(*) FROM {TABLE} WHERE NOT {_REFUND_JALUR_APLIKASI}"
    )).scalar()
    sebelum = _total(bind)

    bind.execute(sa.text(f"""
        UPDATE transaksi_kasir t
        JOIN (SELECT id_transaksi, SUM(nilai_refund) AS s
                FROM {TABLE}
               WHERE {_REFUND_JALUR_APLIKASI}
               GROUP BY id_transaksi) r ON r.id_transaksi = t.id_transaksi
           SET t.total_tagihan = t.total_tagihan + r.s
    """))

    sesudah = _total(bind)
    cocok = abs((sesudah - float(sum_refund)) - sebelum) < 0.005
    print(f"[migrasi {revision}] header dipulihkan: {n_refund} refund, Rp {float(sum_refund):,.2f}")
    print(f"[migrasi {revision}]   SUM(total_tagihan) sebelum {sebelum:,.2f} -> sesudah {sesudah:,.2f}")
    print(f"[migrasi {revision}]   sesudah − refund == sebelum : {'COCOK' if cocok else 'TIDAK COCOK'}")
    if n_lain:
        print(f"[migrasi {revision}]   {n_lain} refund TIDAK disentuh (bukan jalur aplikasi — "
              f"mis. data seed yang tak pernah memutasi header)")
    if not cocok:
        raise RuntimeError("Pemulihan header tidak cocok — migrasi dihentikan.")


def downgrade():
    # Kembalikan ke perilaku lama: header dikurangi refund lagi, lalu buang kolom.
    # Hanya benar kalau KODE juga dikembalikan ke versi yang memutasi header.
    bind = op.get_bind()
    bind.execute(sa.text(f"""
        UPDATE transaksi_kasir t
        JOIN (SELECT id_transaksi, SUM(nilai_refund) AS s
                FROM {TABLE}
               WHERE {_REFUND_JALUR_APLIKASI}
               GROUP BY id_transaksi) r ON r.id_transaksi = t.id_transaksi
           SET t.total_tagihan = GREATEST(0, t.total_tagihan - r.s)
    """))
    insp = sa.inspect(bind)
    if KOLOM in {c["name"] for c in insp.get_columns(TABLE)}:
        op.drop_constraint(FK, TABLE, type_="foreignkey")
        op.drop_column(TABLE, KOLOM)
