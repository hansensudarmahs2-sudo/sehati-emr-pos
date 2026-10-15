"""kasir_closing.tanggal_sesi + indeks UNIK — satu sesi laci per tanggal (Audit T4-6).

Disetujui dr. Hansen 2026-10-16 (Project_Memory/AUDIT_MENDALAM_2026-10-13.md, T4-6).

Masalah: T28 (satu laci, satu sesi per tanggal) dijaga dengan "SELECT dulu, lalu INSERT"
tanpa kunci dan tanpa indeks unik. Dua klik Buka Kasir bersamaan (atau Kasir + Admin)
sama-sama lolos cek → dua sesi OPEN di tanggal yang sama. `tutup_kasir` hanya menutup yang
terbaru; yang lain tertinggal OPEN dan memblokir buka kasir esok hari, dan begitu ditutup,
Laporan Tutup Kasir menghitung hari itu DUA kali. Kunci baris tak bisa menjaganya (tabel bisa
kosong untuk tanggal itu), kunci bernama MySQL melekat pada KONEKSI (lepas ke pool sesudah
commit) — maka pagar unik di database.

Migrasi:
1. Kolom TERHITUNG `tanggal_sesi` = DATE(shift_mulai), STORED (tidak pernah ditulis aplikasi).
2. Indeks UNIK `ux_kasir_closing_tanggal`. Nama ini DIPAKAI `KasirClosingService` untuk
   mengenali pelanggarannya — jangan diganti tanpa mengubah layanan (pelajaran T34: jangan
   menangkap IntegrityError generik).
3. Sebelum itu: kalau data sudah punya dua sesi di satu tanggal, migrasi BERHENTI dan
   menyebut id-nya. Data seperti itu harus diputuskan dr. Hansen, bukan ditebak migrasi.
"""
import sqlalchemy as sa
from alembic import op

revision = "20261016_0100"
down_revision = "20261013_0100"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    ganda = bind.execute(sa.text(
        "SELECT DATE(shift_mulai) AS tgl, GROUP_CONCAT(id_closing ORDER BY id_closing) AS ids "
        "FROM kasir_closing GROUP BY DATE(shift_mulai) HAVING COUNT(*) > 1")).all()
    if ganda:
        rincian = "; ".join(f"{tgl}: sesi {ids}" for tgl, ids in ganda)
        raise RuntimeError(
            "kasir_closing punya lebih dari satu sesi di tanggal yang sama — migrasi "
            f"20261016_0100 dihentikan. {rincian}. Putuskan sesi mana yang sah sebelum "
            "menjalankan ulang.")
    op.execute(
        "ALTER TABLE kasir_closing ADD COLUMN tanggal_sesi DATE "
        "GENERATED ALWAYS AS (DATE(shift_mulai)) STORED "
        "COMMENT 'Tanggal sesi laci = DATE(shift_mulai). UNIK: satu sesi per tanggal (Audit T4-6).'")
    op.create_index("ux_kasir_closing_tanggal", "kasir_closing", ["tanggal_sesi"], unique=True)


def downgrade():
    op.drop_index("ux_kasir_closing_tanggal", table_name="kasir_closing")
    op.drop_column("kasir_closing", "tanggal_sesi")
