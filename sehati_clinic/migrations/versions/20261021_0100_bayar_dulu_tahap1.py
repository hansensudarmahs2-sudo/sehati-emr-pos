"""Bayar dulu tahap 1: kunjungan_tindakan.id_transaksi, status BATAL, sumber PRABAYAR.

Disetujui dr. Hansen 2026-10-21 (Project_Memory/DESAIN_BAYAR_DULU_BERCABANG.md §3.1).

Migrasi ini HANYA menambah; belum ada kode yang membacanya (tugas berikutnya).

1. `kunjungan_tindakan.id_transaksi` (FK + indeks) — tindakan tahu DIBAYAR oleh transaksi
   MANA, sejajar `kunjungan_resep.id_transaksi` (T2-2) dan `kunjungan_racikan.id_transaksi`.
   Dulu satu-satunya jejak adalah `transaksi_detail_tindakan` (snapshot F3) — tidak ada
   untuk data sebelum F3, dan membuat "sudah dibayar?" harus join.
2. `kunjungan_tindakan.status_tindakan` + 'BATAL' — tindakan yang dibatalkan sebelum dikerjakan
   (bayar dulu: tindakan sudah ditagih tapi pasien batal) tidak boleh dihapus, uangnya ada.
3. `pasien_rencana_treatment.sumber_rencana` + 'PRABAYAR' — series yang dibeli di muka.
4. `transaksi_refund.id_kunjungan_tindakan` (FK + indeks) — refund per tindakan, sejajar
   `id_resep` / `id_kunjungan_racikan`.

BACKFILL `id_transaksi` untuk tindakan yang sudah lunas, dua langkah berurutan:
  (1) snapshot `transaksi_detail_tindakan` di transaksi BAYAR (jejak pasti);
  (2) tindakan SELESAI tanpa snapshot (data pra-F3) → transaksi BAYAR PALING AWAL di
      kunjungannya yang `waktu_bayar >= waktu_selesai` — aturan yang SAMA dengan pemisahan
      tagihan susulan kasir dan dengan backfill resep (20261013_0100).
Aman dijalankan ulang (hanya menyentuh baris yang id_transaksi-nya masih NULL).
Upgrade GAGAL bila masih ada tindakan SELESAI di kunjungan yang sudah lunas tapi tak
terpasangkan — menebak di sini berarti tindakan yang bisa ditagih dua kali.

PAGAR SEBELUM DDL (review akhir tahap 1, I5): `tindakan_tak_terpasangkan` (SELECT murni di
skema LAMA) dijalankan PALING AWAL — MySQL meng-commit setiap ALTER secara implisit, jadi
pagar yang hanya ada sesudah backfill meninggalkan DB setengah termigrasi. Pagar sesudah
backfill tetap ada sebagai pengaman kedua.
Prapemeriksaan yang sama bisa dijalankan di mini PC SEBELUM deploy (hanya membaca):
    cd /srv/sehati
    docker compose exec -T sehati-db sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" db_sehati' < deploy/precheck_20261021_0100.sql
Hasil kosong = aman. Baris yang keluar = periksa manual dulu.
"""
import sqlalchemy as sa
from alembic import op

revision = "20261021_0100"
down_revision = "20261016_0200"
branch_labels = None
depends_on = None

_STATUS_LAMA = "ENUM('PENDING','PROSES','SELESAI')"
_STATUS_BARU = "ENUM('PENDING','PROSES','SELESAI','BATAL')"
_SUMBER_LAMA = "ENUM('DOKTER_PLAN','MEMBERSHIP','PROMO')"
_SUMBER_BARU = "ENUM('DOKTER_PLAN','MEMBERSHIP','PROMO','PRABAYAR')"


def upgrade():
    bind = op.get_bind()
    # Pagar PERTAMA, sebelum DDL apa pun (review akhir tahap 1, I5). MySQL meng-commit setiap
    # ALTER secara implisit: pagar yang hanya ada SESUDAH backfill membuat upgrade gagal
    # dengan kolom & enum SUDAH berubah tetapi alembic_version belum — DB setengah jadi.
    yatim = tindakan_tak_terpasangkan(bind)
    if yatim:
        raise RuntimeError(
            f"[20261021_0100] {len(yatim)} tindakan SELESAI di kunjungan lunas tidak bisa "
            f"dipasangkan ke transaksi (id_kunjungan_tindakan: {yatim[:50]}). TIDAK ADA yang "
            f"diubah. Periksa manual dulu (deploy/precheck_20261021_0100.sql).")
    op.execute(f"ALTER TABLE kunjungan_tindakan MODIFY status_tindakan {_STATUS_BARU} "
               "NULL DEFAULT 'PENDING'")
    op.execute(f"ALTER TABLE pasien_rencana_treatment MODIFY sumber_rencana {_SUMBER_BARU} "
               "NOT NULL DEFAULT 'DOKTER_PLAN'")

    op.add_column("kunjungan_tindakan", sa.Column(
        "id_transaksi", sa.Integer, nullable=True,
        comment="Transaksi yang membayar tindakan ini (bayar dulu T1). NULL = belum dibayar / data lama."))
    op.create_foreign_key("fk_kt_transaksi", "kunjungan_tindakan", "transaksi_kasir",
                          ["id_transaksi"], ["id_transaksi"])
    op.create_index("ix_kt_transaksi", "kunjungan_tindakan", ["id_transaksi"])

    op.add_column("transaksi_refund", sa.Column(
        "id_kunjungan_tindakan", sa.Integer, nullable=True,
        comment="Refund per tindakan (bayar dulu). NULL = bukan refund tindakan."))
    op.create_foreign_key("fk_refund_kt", "transaksi_refund", "kunjungan_tindakan",
                          ["id_kunjungan_tindakan"], ["id_kunjungan_tindakan"])
    op.create_index("ix_refund_kt", "transaksi_refund", ["id_kunjungan_tindakan"])

    hasil = isi_id_transaksi_tindakan(bind)
    print(f"[20261021_0100] backfill kunjungan_tindakan.id_transaksi: "
          f"{hasil['dari_snapshot']} dari snapshot, {hasil['dari_cutoff']} dari cutoff waktu, "
          f"{hasil['tetap_null_di_kunjungan_lunas']} tetap NULL di kunjungan lunas.")
    if hasil["tetap_null_di_kunjungan_lunas"] > 0:
        ids = [r[0] for r in bind.execute(sa.text(_SQL_TETAP_NULL.format(sel="kt.id_kunjungan_tindakan")
                                                   + " LIMIT 50")).all()]
        raise RuntimeError(
            f"{hasil['tetap_null_di_kunjungan_lunas']} tindakan SELESAI di kunjungan lunas tidak "
            f"bisa dipasangkan ke transaksi (id_kunjungan_tindakan: {ids}). Periksa manual dulu.")


# Prapemeriksaan — HANYA membaca, dan hanya memakai kolom yang SUDAH ada sebelum migrasi ini
# (tanpa kt.id_transaksi), jadi bisa dijalankan di mini PC sebelum deploy. Tindakan SELESAI di
# kunjungan yang punya transaksi BAYAR, yang TIDAK tertangkap langkah backfill mana pun:
# tak ada snapshot di transaksi BAYAR (langkah 1) dan tak ada transaksi BAYAR di kunjungannya
# yang waktu_bayar >= waktu_selesai (langkah 2). Satu sumber dengan
# deploy/precheck_20261021_0100.sql (test_precheck_sql_berkas_sama_dengan_migrasi).
# ⚠ Termasuk tindakan SUSULAN yang memang belum ditagih (selesai sesudah pembayaran terakhir):
# jalankan sesudah semua tagihan hari itu dibayar — kasir tak bisa tutup sebelum itu.
_SQL_PRECHECK = (
    "SELECT {sel} FROM kunjungan_tindakan kt "
    "WHERE kt.status_tindakan = 'SELESAI' "
    "AND EXISTS (SELECT 1 FROM transaksi_kasir t "
    "WHERE t.id_kunjungan = kt.id_kunjungan AND t.status_transaksi = 'BAYAR') "
    "AND NOT EXISTS (SELECT 1 FROM transaksi_detail_tindakan d "
    "JOIN transaksi_kasir t ON t.id_transaksi = d.id_transaksi "
    "WHERE d.id_kunjungan_tindakan = kt.id_kunjungan_tindakan AND t.status_transaksi = 'BAYAR') "
    "AND NOT EXISTS (SELECT 1 FROM transaksi_kasir t "
    "WHERE t.id_kunjungan = kt.id_kunjungan AND t.status_transaksi = 'BAYAR' "
    "AND kt.waktu_selesai IS NOT NULL AND t.waktu_bayar >= kt.waktu_selesai)"
)


def tindakan_tak_terpasangkan(bind) -> list:
    """id_kunjungan_tindakan yang akan tetap NULL sesudah backfill (lihat `_SQL_PRECHECK`)."""
    return [r[0] for r in bind.execute(sa.text(
        _SQL_PRECHECK.format(sel="kt.id_kunjungan_tindakan")
        + " ORDER BY kt.id_kunjungan_tindakan")).all()]


# Tindakan SELESAI yang id_transaksi-nya masih NULL padahal kunjungannya sudah punya transaksi BAYAR.
# Pagar KEDUA (sesudah backfill) — seharusnya tak pernah terpicu bila prapemeriksaan lolos.
_SQL_TETAP_NULL = (
    "SELECT {sel} FROM kunjungan_tindakan kt "
    "WHERE kt.status_tindakan = 'SELESAI' AND kt.id_transaksi IS NULL "
    "AND EXISTS (SELECT 1 FROM transaksi_kasir t "
    "            WHERE t.id_kunjungan = kt.id_kunjungan AND t.status_transaksi = 'BAYAR')"
)


def isi_id_transaksi_tindakan(bind) -> dict:
    """Logika backfill, dipisah supaya bisa diuji (tests/integration/test_bayar_dulu_tahap1.py)."""
    # (1) Snapshot F3: jejak pasti. MIN() bila satu tindakan muncul di >1 transaksi BAYAR.
    r1 = bind.execute(sa.text(
        "UPDATE kunjungan_tindakan kt "
        "JOIN (SELECT d.id_kunjungan_tindakan AS idk, MIN(d.id_transaksi) AS idt "
        "      FROM transaksi_detail_tindakan d "
        "      JOIN transaksi_kasir t ON t.id_transaksi = d.id_transaksi "
        "      WHERE t.status_transaksi = 'BAYAR' AND d.id_kunjungan_tindakan IS NOT NULL "
        "      GROUP BY d.id_kunjungan_tindakan) s ON s.idk = kt.id_kunjungan_tindakan "
        "SET kt.id_transaksi = s.idt "
        "WHERE kt.id_transaksi IS NULL"))
    # (2) Pra-F3: transaksi BAYAR paling awal yang waktu_bayar >= waktu_selesai.
    r2 = bind.execute(sa.text(
        "UPDATE kunjungan_tindakan kt "
        "SET kt.id_transaksi = (SELECT t.id_transaksi FROM transaksi_kasir t "
        "    WHERE t.id_kunjungan = kt.id_kunjungan AND t.status_transaksi = 'BAYAR' "
        "      AND t.waktu_bayar >= kt.waktu_selesai "
        "    ORDER BY t.waktu_bayar, t.id_transaksi LIMIT 1) "
        "WHERE kt.status_tindakan = 'SELESAI' AND kt.id_transaksi IS NULL "
        "  AND kt.waktu_selesai IS NOT NULL "
        # EXISTS supaya rowcount = baris yang BENAR-BENAR terisi, bukan yang sekadar dicocokkan.
        "  AND EXISTS (SELECT 1 FROM transaksi_kasir t2 WHERE t2.id_kunjungan = kt.id_kunjungan "
        "              AND t2.status_transaksi = 'BAYAR' AND t2.waktu_bayar >= kt.waktu_selesai)"))
    tetap = bind.execute(sa.text(_SQL_TETAP_NULL.format(sel="COUNT(*)"))).scalar()
    return {"dari_snapshot": r1.rowcount, "dari_cutoff": r2.rowcount, "tetap_null_di_kunjungan_lunas": int(tetap)}


def downgrade():
    bind = op.get_bind()
    n_batal = bind.execute(sa.text(
        "SELECT COUNT(*) FROM kunjungan_tindakan WHERE status_tindakan = 'BATAL'")).scalar()
    n_prabayar = bind.execute(sa.text(
        "SELECT COUNT(*) FROM pasien_rencana_treatment WHERE sumber_rencana = 'PRABAYAR'")).scalar()
    if n_batal or n_prabayar:
        raise RuntimeError(
            f"Downgrade ditolak: {n_batal} tindakan berstatus BATAL dan {n_prabayar} rencana "
            "bersumber PRABAYAR akan kehilangan nilainya.")
    # FK dulu, baru indeks: MySQL menolak membuang indeks yang masih dipakai FK (error 1553).
    op.drop_constraint("fk_refund_kt", "transaksi_refund", type_="foreignkey")
    op.drop_index("ix_refund_kt", table_name="transaksi_refund")
    op.drop_column("transaksi_refund", "id_kunjungan_tindakan")
    op.drop_constraint("fk_kt_transaksi", "kunjungan_tindakan", type_="foreignkey")
    op.drop_index("ix_kt_transaksi", table_name="kunjungan_tindakan")
    op.drop_column("kunjungan_tindakan", "id_transaksi")
    op.execute(f"ALTER TABLE pasien_rencana_treatment MODIFY sumber_rencana {_SUMBER_LAMA} "
               "NOT NULL DEFAULT 'DOKTER_PLAN'")
    op.execute(f"ALTER TABLE kunjungan_tindakan MODIFY status_tindakan {_STATUS_LAMA} "
               "NULL DEFAULT 'PENDING'")
