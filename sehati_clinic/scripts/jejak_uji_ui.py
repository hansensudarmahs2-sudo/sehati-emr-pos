"""Jejak uji UI — catat apa yang BENAR-BENAR terjadi di DB selama dr. Hansen menguji di layar.

Kenapa ada: uji UI menjawab "layarnya benar?", tapi audit alur uang berkali-kali
menemukan layar yang benar di atas data yang salah (komisi AKTIF atas transaksi VOID,
lot fantom, header termutasi). Skrip ini merekam sisi DB-nya supaya setiap butir di
`Project_Memory/UJI_UI_AUDIT_2026-10-05.md` punya bukti, bukan hanya kesan.

HANYA MEMBACA. Tidak ada INSERT/UPDATE/DELETE; sesi selalu di-rollback. Tidak memanggil
`prepare_nota_context` (yang menulis audit PRINT_NOTA).

Pakai (dari sehati_clinic/, venv aktif):
    python -m scripts.jejak_uji_ui --mulai      # SEBELUM uji: simpan titik awal
    python -m scripts.jejak_uji_ui              # SESUDAH uji: tampilkan + simpan laporan

Laporan: `uji_ui_log/jejak_<waktu>.md` (folder DIABAIKAN git — isinya data DB, walau dev).
Pasien hanya disebut dengan no_rm, tidak pernah nama.

⚠ Menolak jalan kalau DB berisi > 200 pasien (kemungkinan produksi) kecuali --paksa:
  keterangan audit bisa memuat nama obat/pasien, dan laporan ini ditulis ke disk.
"""

import argparse
import json
import sys
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

from app.db.session import SessionLocal

FOLDER = Path("uji_ui_log")
PENANDA = FOLDER / "penanda.json"

# Tabel yang dicatat baris BARU-nya (id terbesar saat --mulai).
TABEL_ID = {
    "audit_log": "id_log",
    "transaksi_kasir": "id_transaksi",
    "transaksi_refund": "id_refund",
    "kasir_closing": "id_closing",
    "komisi_ledger": "id_komisi",
    "transaksi_detail_tindakan": "id_detail_tindakan",
    "stok_lot": "id_lot",
    "kunjungan_lot_terpakai": "id_terpakai",
    "pasien_membership_history": "id_history",
}


def _rp(x) -> str:
    return f"Rp {Decimal(str(x or 0)):,.0f}".replace(",", ".")


class Laporan:
    def __init__(self):
        self.baris: list[str] = []
        self.n_lulus = self.n_gagal = self.n_info = 0

    def h(self, judul):
        self.baris += ["", f"## {judul}", ""]

    def t(self, s=""):
        self.baris.append(s)

    def cek(self, ok: bool, label: str, rinci: str = "", rinci_ok: str = ""):
        """`rinci` = penjelasan KEGAGALAN (hanya dicetak kalau gagal); `rinci_ok` = angka
        pendukung yang dicetak kalau lulus. Dulu satu `rinci` dicetak di kedua kasus, jadi
        baris [OK] memuat teks seperti "header berbeda — refund memutasi header lagi?"."""
        tanda = "✅" if ok else "❌"
        self.n_lulus += ok
        self.n_gagal += (not ok)
        teks = rinci_ok if ok else rinci
        self.baris.append(f"- {tanda} **{label}**" + (f" — {teks}" if teks else ""))

    def info(self, label: str, rinci: str = ""):
        self.n_info += 1
        self.baris.append(f"- ℹ️ {label}" + (f" — {rinci}" if rinci else ""))


def mulai(db):
    FOLDER.mkdir(exist_ok=True)
    titik = {"waktu": datetime.now().isoformat(timespec="seconds"), "id": {}}
    for tabel, kol in TABEL_ID.items():
        titik["id"][tabel] = int(db.execute(text(f"SELECT COALESCE(MAX({kol}),0) FROM {tabel}")).scalar())
    PENANDA.write_text(json.dumps(titik, indent=2), encoding="utf-8")
    print(f"Titik awal disimpan {titik['waktu']} → {PENANDA}")
    for t, v in titik["id"].items():
        print(f"  {t:28} id > {v}")
    print("\nSilakan uji di UI. Sesudahnya jalankan: python3 -m scripts.jejak_uji_ui")


def jejak(db, titik) -> Laporan:
    L = Laporan()
    sejak = titik["waktu"]
    ids = titik["id"]
    L.t(f"# Jejak uji UI — {datetime.now():%Y-%m-%d %H:%M}")
    L.t(f"Sejak titik awal **{sejak}**. Hanya membaca; pasien disebut dengan no_rm.")

    # ------------------------------------------------------------------ 1. audit
    L.h("1. Aksi yang tercatat di audit_log (urut waktu)")
    rows = db.execute(text("""
        SELECT a.id_log, a.waktu, a.aksi, a.status_aksi, s.username, a.tabel_target,
               a.id_target, LEFT(COALESCE(a.keterangan,''), 140)
          FROM audit_log a LEFT JOIN master_staf s ON s.id_staf = a.id_staf
         WHERE a.id_log > :i AND a.aksi NOT IN ('VIEW','LOGIN','LOGOUT','PRINT_NOTA')
         ORDER BY a.id_log"""), {"i": ids["audit_log"]}).all()
    if not rows:
        L.info("Tidak ada aksi baru (selain VIEW/LOGIN/PRINT)")
    for r in rows:
        L.t(f"- `{r[1]:%H:%M:%S}` **{r[2]}** [{r[3]}] oleh {r[4] or '—'} → {r[5] or ''}#{r[6] or ''} · {r[7]}")
    n_gagal = db.execute(text(
        "SELECT COUNT(*) FROM audit_log WHERE id_log > :i AND aksi='AUDIT_GAGAL'"),
        {"i": ids["audit_log"]}).scalar()
    L.cek(n_gagal == 0, "T23/T24 · tidak ada AUDIT_GAGAL",
          f"{n_gagal} baris — buka keterangannya: audit gagal ditulis tapi aksi tetap jalan" if n_gagal else "")

    # ------------------------------------------------------------ 2. transaksi
    L.h("2. Transaksi baru")
    trx = db.execute(text("""
        SELECT t.id_transaksi, t.waktu_bayar, t.status_transaksi, t.jenis_transaksi,
               t.subtotal, t.nominal_diskon, t.total_tagihan, s.username, p.no_rm,
               t.id_kunjungan, t.doc_number
          FROM transaksi_kasir t
          LEFT JOIN master_staf s ON s.id_staf = t.id_staf_kasir
          LEFT JOIN pasien p ON p.id_pasien = t.id_pasien
         WHERE t.id_transaksi > :i ORDER BY t.id_transaksi"""), {"i": ids["transaksi_kasir"]}).all()
    if not trx:
        L.info("Tidak ada transaksi baru")
    for r in trx:
        L.t(f"- #{r[0]} `{r[1]:%H:%M}` {r[2]} {r[3]} · {r[8] or '—'} · oleh {r[7]} · "
            f"subtotal {_rp(r[4])} − diskon {_rp(r[5])} = **{_rp(r[6])}** · doc_number={r[10] or 'NULL'}")
        if r[2] == "BAYAR":
            L.cek(abs(Decimal(str(r[4] or 0)) - Decimal(str(r[5] or 0)) - Decimal(str(r[6] or 0))) < Decimal("0.01"),
                  f"T32 · header #{r[0]} utuh (subtotal − diskon = total)",
                  "header berbeda — refund memutasi header lagi?")
            pemb = db.execute(text(
                "SELECT COALESCE(SUM(nominal),0) FROM transaksi_pembayaran WHERE id_transaksi=:t"),
                {"t": r[0]}).scalar()
            L.cek(Decimal(str(pemb)) == Decimal(str(r[6] or 0)), f"T31 · #{r[0]} pembayaran = tagihan",
                  f"dibayar {_rp(pemb)} vs tagihan {_rp(r[6])} — selisih akan tampak di tutup kasir")
        if r[9] is not None and r[2] == "BAYAR":
            n_tnd = db.execute(text("""SELECT COUNT(*) FROM kunjungan_tindakan
                WHERE id_kunjungan=:k AND status_tindakan='SELESAI'"""), {"k": r[9]}).scalar()
            n_snap = db.execute(text("""SELECT COUNT(*) FROM transaksi_detail_tindakan d
                JOIN transaksi_kasir t ON t.id_transaksi=d.id_transaksi WHERE t.id_kunjungan=:k"""),
                {"k": r[9]}).scalar()
            if n_tnd:
                L.cek(n_snap > 0, f"F3/T27 · #{r[0]} punya snapshot tindakan",
                      f"{n_tnd} tindakan SELESAI tapi 0 baris snapshot — nota akan 'direkonstruksi'",
                      f"{n_tnd} tindakan SELESAI, {n_snap} baris snapshot")

    # ---------------------------------------------------------- 3. refund
    L.h("3. Refund baru (T32)")
    ref = db.execute(text("""
        SELECT r.id_refund, r.tgl_refund, r.id_transaksi, r.nilai_refund, r.metode_refund,
               s.username, o.username, DATE(t.waktu_bayar) < DATE(r.tgl_refund), t.status_transaksi
          FROM transaksi_refund r
          JOIN transaksi_kasir t ON t.id_transaksi = r.id_transaksi
          LEFT JOIN master_staf s ON s.id_staf = r.id_staf_refund
          LEFT JOIN master_staf o ON o.id_staf = r.id_staf_otorisasi
         WHERE r.id_refund > :i ORDER BY r.id_refund"""), {"i": ids["transaksi_refund"]}).all()
    if not ref:
        L.info("Tidak ada refund baru")
    for r in ref:
        L.t(f"- refund #{r[0]} `{r[1]:%d/%m %H:%M}` trx #{r[2]} {_rp(r[3])} {r[4]} · oleh {r[5]} · "
            f"penyetuju {r[6] or '—'} · hari lampau={bool(r[7])}")
        if r[7]:
            L.cek(r[6] is not None and r[6] != r[5], f"T32 · refund #{r[0]} hari lampau disetujui orang LAIN")
        L.cek(r[8] == "BAYAR", f"T32 · transaksi asal refund #{r[0]} tidak di-VOID")
    tolak = db.execute(text("""SELECT COUNT(*) FROM audit_log
        WHERE id_log > :i AND aksi='REFUND_DITOLAK_PIN'"""), {"i": ids["audit_log"]}).scalar()
    if tolak:
        L.info(f"{tolak} percobaan refund ditolak karena PIN (tercatat, sesuai rancangan)")
    bocor = db.execute(text("""SELECT COUNT(*) FROM audit_log
        WHERE id_log > :i AND aksi='REFUND_DITOLAK_PIN' AND keterangan REGEXP 'pin_otorisasi='"""),
        {"i": ids["audit_log"]}).scalar()
    L.cek(bocor == 0, "T32 · PIN tidak pernah tertulis di audit")

    # ------------------------------------------------------- 4. tutup kasir
    L.h("4. Sesi kasir (T28)")
    ses = db.execute(text("""
        SELECT c.id_closing, c.status, c.shift_mulai, c.shift_tutup, b.username, u.username,
               c.modal_awal, c.total_expected, c.total_counted, c.total_selisih
          FROM kasir_closing c
          LEFT JOIN master_staf b ON b.id_staf = c.id_staf_buka
          LEFT JOIN master_staf u ON u.id_staf = c.id_staf_tutup
         WHERE c.id_closing > :i OR c.status = 'OPEN' OR c.shift_tutup >= :w
         ORDER BY c.id_closing"""), {"i": ids["kasir_closing"], "w": sejak}).all()
    if not ses:
        L.info("Tidak ada sesi kasir baru/terbuka")
    for r in ses:
        L.t(f"- sesi #{r[0]} {r[1]} · buka {r[2]:%d/%m %H:%M} oleh {r[4]}"
            + (f" · tutup {r[3]:%H:%M} oleh {r[5]}" if r[3] else "")
            + (f" · expected {_rp(r[7])} counted {_rp(r[8])} selisih {_rp(r[9])}" if r[7] is not None else ""))
    dobel = db.execute(text("""SELECT DATE(shift_mulai) tgl, COUNT(*) FROM kasir_closing
        WHERE shift_mulai >= DATE(:w)
        GROUP BY DATE(shift_mulai) HAVING COUNT(*) > 1"""), {"w": sejak}).all()
    L.cek(not dobel, "T28 · satu sesi per tanggal", ", ".join(f"{d}: {n}" for d, n in dobel))
    n_open = db.execute(text("SELECT COUNT(*) FROM kasir_closing WHERE status='OPEN'")).scalar()
    L.cek(n_open <= 1, "T28 · paling banyak satu laci terbuka", f"{n_open} sesi OPEN", f"{n_open} sesi OPEN")
    for r in ses:
        if r[1] == "CLOSED" and r[3] is not None:
            setelah = db.execute(text("""SELECT COUNT(*), COALESCE(SUM(p.nominal),0)
                FROM transaksi_kasir t JOIN transaksi_pembayaran p ON p.id_transaksi=t.id_transaksi
                WHERE t.status_transaksi='BAYAR' AND t.waktu_bayar > :tt
                  AND DATE(t.waktu_bayar) = DATE(:tm)"""), {"tt": r[3], "tm": r[2]}).one()
            if setelah[0]:
                L.info(f"sesi #{r[0]}: {setelah[0]} pembayaran ({_rp(setelah[1])}) masuk SESUDAH tutup — "
                       "harus tampil di slip Z sebagai peringatan")

    # ---------------------------------------------- 5. omzet: semua pembaca sepakat?
    L.h("5. Omzet hari ini — semua pembaca harus sepakat (T32/T28)")
    hari = date.today()
    awal, akhir = datetime.combine(hari, time.min), datetime.combine(hari, time.max)
    try:
        from app.services.reports_service import ReportsService
        from app.services.rekap_harian_service import RekapHarianService
        from app.services.dashboard_service import DashboardService
        from app.services.export_service import ExportService
        rpt = ReportsService(db).omzet_harian(hari)
        rh = RekapHarianService(db).rekap(hari)
        kpi = DashboardService(db)._kpi_omzet_hari_ini(hari)["value_money"]
        eks = [x for x in ExportService(db).export_daily_operational_summary(hari, hari)][0]["total_omzet"]
        L.t(f"- Laporan omzet {_rp(rpt.total_omzet)} (refund hari ini {_rp(rpt.total_refund)}) · "
            f"rekap owner {_rp(rh['total_omzet'])} · KPI dashboard {_rp(kpi)} · ekspor Finance {_rp(eks)}")
        L.cek(rpt.total_omzet == rh["total_omzet"], "Laporan omzet = rekap harian owner")
        L.cek(abs(float(rpt.total_omzet) - float(eks)) < 0.01, "Laporan omzet = ekspor ringkasan Finance")
        L.cek(sum(k.total_omzet for k in rpt.per_kasir) == rpt.total_omzet,
              "Rincian per kasir berjumlah = total")
        L.cek(abs(float(sum(m.total_nominal for m in rpt.per_metode)) - float(kpi)) < 0.01,
              "Rincian per metode = KPI dashboard (dua-duanya basis pembayaran − refund)")
    except Exception as e:  # jangan biarkan satu laporan mematikan seluruh jejak
        L.cek(False, "Omzet hari ini bisa dihitung", f"{type(e).__name__}: {e}")

    # -------------------------------------------------- 6. komisi & membership
    L.h("6. Komisi & membership atas transaksi VOID (Temuan 3/5/11) — SELURUH DB")
    kv = db.execute(text("""SELECT COUNT(*), COALESCE(SUM(k.komisi_nominal),0)
        FROM komisi_ledger k JOIN transaksi_kasir t ON t.id_transaksi=k.id_transaksi
        WHERE t.status_transaksi='VOID' AND k.status='AKTIF'""")).one()
    L.cek(kv[0] == 0, "Tidak ada komisi AKTIF atas transaksi VOID",
          f"{kv[0]} baris, {_rp(kv[1])} — ikut terbayar di laporan komisi" if kv[0] else "")
    mv = db.execute(text("""SELECT COUNT(*) FROM pasien_membership_history h
        JOIN transaksi_kasir t ON t.id_transaksi=h.id_transaksi_aktivasi
        WHERE t.status_transaksi='VOID' AND h.status_aktivasi IN ('PAID','ACTIVE')""")).scalar()
    L.cek(mv == 0, "Tidak ada membership PAID/ACTIVE atas transaksi VOID", f"{mv} baris" if mv else "")
    lintas = db.execute(text("""SELECT COUNT(*) FROM pasien_membership_history h
        JOIN transaksi_kasir t ON t.id_transaksi=h.id_transaksi_aktivasi
        LEFT JOIN kunjungan k ON k.id_kunjungan=t.id_kunjungan
        WHERE h.id_pasien NOT IN (COALESCE(t.id_pasien,0), COALESCE(k.id_pasien,0))""")).scalar()
    L.cek(lintas == 0, "Membership tidak menunjuk transaksi pasien LAIN", f"{lintas} baris" if lintas else "")
    baru_k = db.execute(text("""SELECT k.id_komisi, k.id_transaksi, k.sumber, k.nama_item,
        k.komisi_nominal, k.status, s.username FROM komisi_ledger k
        LEFT JOIN master_staf s ON s.id_staf=k.id_staf WHERE k.id_komisi > :i ORDER BY k.id_komisi"""),
        {"i": ids["komisi_ledger"]}).all()
    for r in baru_k:
        L.t(f"- komisi #{r[0]} trx #{r[1]} {r[2]} {r[3]} {_rp(r[4])} {r[5]} → {r[6]}")

    # ------------------------------------------------------------- 7. stok
    L.h("7. Stok: buku lot vs cache (Temuan 20/30)")
    beda = db.execute(text("""
        SELECT p.id_produk, p.nama_produk, p.stok_terkini, COALESCE(SUM(l.qty_sisa),0) lot
          FROM master_produk p
          LEFT JOIN stok_lot l ON l.id_produk=p.id_produk AND l.tipe_item='PRODUK' AND l.status='AKTIF'
         WHERE p.id_produk IN (
               SELECT id_produk FROM kunjungan_lot_terpakai WHERE id_terpakai > :a
               UNION SELECT id_produk FROM stok_lot WHERE id_lot > :b AND id_produk IS NOT NULL)
         GROUP BY p.id_produk, p.nama_produk, p.stok_terkini"""),
        {"a": ids["kunjungan_lot_terpakai"], "b": ids["stok_lot"]}).all()
    if not beda:
        L.info("Tidak ada produk yang stoknya tersentuh")
    for r in beda:
        L.cek(abs(float(r[2] or 0) - float(r[3] or 0)) < 0.001, f"{r[1]}: cache = jumlah lot",
              f"cache {r[2]} vs lot {r[3]}", f"cache {r[2]} = lot {r[3]}")
    lot_baru = db.execute(text("""SELECT id_lot, batch_no, qty_masuk, tgl_ed FROM stok_lot
        WHERE id_lot > :i ORDER BY id_lot"""), {"i": ids["stok_lot"]}).all()
    for r in lot_baru:
        L.t(f"- lot baru #{r[0]} {r[1]} qty {r[2]} ED {r[3]}")
        if (r[1] or "").startswith("VOID-RETURN"):
            L.info(f"lot VOID-RETURN #{r[0]} — wajar HANYA untuk data lama (pra-#54); "
                   "untuk data baru periksa dengan cek_serah_tanpa_lot")

    L.h("Ringkasan")
    L.t(f"**{L.n_lulus} lulus · {L.n_gagal} GAGAL · {L.n_info} info**")
    return L


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mulai", action="store_true", help="simpan titik awal sebelum uji")
    ap.add_argument("--paksa", action="store_true", help="jalan walau DB tampak produksi")
    a = ap.parse_args()
    # Mode dev menyalakan echo SQL (app/db/session.py) — ratusan baris query menenggelamkan
    # laporannya. Dimatikan HANYA untuk skrip ini.
    import logging
    from app.db.session import engine
    engine.echo = False
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    db = SessionLocal()
    try:
        n_pasien = db.execute(text("SELECT COUNT(*) FROM pasien")).scalar()
        if n_pasien > 200 and not a.paksa:
            sys.exit(f"DITOLAK: {n_pasien} pasien — ini tampak DB produksi. Laporan menulis data ke "
                     "disk. Pakai --paksa kalau memang sengaja.")
        if a.mulai:
            mulai(db)
            return
        if not PENANDA.exists():
            sys.exit("Belum ada titik awal. Jalankan dulu: python3 -m scripts.jejak_uji_ui --mulai")
        titik = json.loads(PENANDA.read_text(encoding="utf-8"))
        L = jejak(db, titik)
        isi = "\n".join(L.baris) + "\n"
        keluar = FOLDER / f"jejak_{datetime.now():%Y%m%d_%H%M%S}.md"
        keluar.write_text(isi, encoding="utf-8")
        # Terminal Windows/WSL menghitung emoji selebar 2 kolom dan menggambar ulang satu
        # huruf ("OPEEN", "barris") — berkasnya benar, layarnya yang salah. Teks biasa di layar.
        print(isi.replace("✅", "[OK]").replace("❌", "[GAGAL]").replace("ℹ️", "[i]"))
        print(f"\nDisimpan: {keluar}")
        sys.exit(1 if L.n_gagal else 0)
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
