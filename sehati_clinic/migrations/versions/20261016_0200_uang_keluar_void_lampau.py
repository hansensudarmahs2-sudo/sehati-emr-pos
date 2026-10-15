"""Uang keluar untuk void HARI LAMPAU yang sudah terjadi (audit K4-1) — migrasi DATA.

Disetujui dr. Hansen 2026-10-16 (Project_Memory/AUDIT_MENDALAM_2026-10-13.md, K4-1).

Sejak K4-1, transaksi VOID ber-`late_void` TETAP dihitung omzet hari bayarnya
(`_refund_bukuan.terhitung_omzet`), dan uangnya keluar di tanggal void lewat baris
`transaksi_refund` berjenis VOID (`KasirService._catat_uang_keluar_void`). Void hari lampau
yang terjadi SEBELUM perubahan itu tidak punya baris uang keluar — tanpa migrasi ini hari
asalnya kembali menghitung transaksi itu, tapi hari void-nya tidak berkurang.

Aturan alokasi SAMA dengan kode: satu baris per metode bayar asal, metode non-TUNAI lebih
dulu, TUNAI menampung sisanya, total = total_tagihan (kembalian tidak ikut keluar).
Hanya transaksi `status_transaksi='VOID' AND late_void=1` yang BELUM punya baris jenis VOID —
aman dijalankan ulang. Pelaku = `void_by_id_staf`; penyetuju dibiarkan NULL (dulu tak ada).
Migrasi mencetak jumlah transaksi & baris yang dibuat.
"""
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision = "20261016_0200"
down_revision = "20261016_0100"
branch_labels = None
depends_on = None


def upgrade():
    n_trx, n_baris = isi_uang_keluar(op.get_bind())
    print(f"[20261016_0200] void hari lampau tanpa uang keluar: {n_trx} transaksi, "
          f"{n_baris} baris transaksi_refund jenis VOID dibuat.")


def isi_uang_keluar(bind) -> tuple:
    """Logika migrasi, dipisah supaya bisa diuji (tests/integration/test_audit_tahap4.py)."""
    trx_list = bind.execute(sa.text(
        "SELECT t.id_transaksi, t.total_tagihan, t.void_at, t.void_by_id_staf, "
        "       t.void_reason_code, t.void_reason_note "
        "FROM transaksi_kasir t "
        "WHERE t.status_transaksi = 'VOID' AND t.late_void = 1 AND t.void_at IS NOT NULL "
        "  AND NOT EXISTS (SELECT 1 FROM transaksi_refund r "
        "                  WHERE r.id_transaksi = t.id_transaksi AND r.jenis_refund = 'VOID')"
    )).all()
    n_baris = 0
    for id_trx, total, void_at, id_staf, kode, catatan in trx_list:
        sisa = Decimal(str(total or 0))
        bayar = bind.execute(sa.text(
            "SELECT metode_bayar, nominal FROM transaksi_pembayaran "
            "WHERE id_transaksi = :i ORDER BY id_pembayaran"), {"i": id_trx}).all()
        bayar = sorted(bayar, key=lambda p: (str(p[0] or "").upper() == "TUNAI"))
        for metode, nominal in bayar:
            if sisa <= 0:
                break
            nilai = min(Decimal(str(nominal or 0)), sisa)
            if nilai <= 0:
                continue
            bind.execute(sa.text(
                "INSERT INTO transaksi_refund (id_transaksi, tgl_refund, nilai_refund, "
                "metode_refund, alasan, id_staf_refund, jenis_refund) "
                "VALUES (:i, :tgl, :nilai, :metode, :alasan, :staf, 'VOID')"),
                {"i": id_trx, "tgl": void_at, "nilai": nilai,
                 "metode": str(metode or "TUNAI").upper(),
                 "alasan": (f"Void hari lampau — {kode or '-'}: {catatan or '-'} "
                            f"(diisi migrasi 20261016_0200)")[:1000],
                 "staf": id_staf})
            sisa -= nilai
            n_baris += 1
    return len(trx_list), n_baris


def downgrade():
    op.execute("DELETE FROM transaksi_refund WHERE jenis_refund = 'VOID' "
               "AND alasan LIKE '%(diisi migrasi 20261016_0200)%'")
