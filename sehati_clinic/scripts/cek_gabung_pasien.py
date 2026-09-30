"""Pemeriksa penggabungan pasien — termasuk GERBANG tabel tak terdaftar.

Bahaya utama yang dijaga:
  Kalau ada tabel ber-`id_pasien` yang TIDAK terdaftar di
  `AuditPasienService.TABEL_PINDAH`, barisnya tetap menunjuk pasien duplikat
  setelah penggabungan. Rekam medis tampak menyatu, tapi sepotong riwayat
  tertinggal — DIAM-DIAM, tanpa error, tanpa gejala di layar mana pun.
  Migrasi yang menambah tabel baru adalah cara paling mudah hal ini terjadi.

Yang diuji:
  A. Registry vs information_schema — GAGAL kalau ada tabel ber-id_pasien di DB
     yang tidak terdaftar dan tidak ada di daftar pengecualian ber-alasan
  B. Pratinjau MURNI BACA — jumlah baris tidak berubah setelah dipanggil
  C. Penggabungan end-to-end pada pasien UJI yang dibuat script ini sendiri:
     riwayat pindah, jumlahnya cocok dengan pratinjau, duplikat nonaktif,
     dismiss dibereskan, audit memuat rincian per tabel
  D. Membership ganda -> DITOLAK
  E. Pasangan yang sudah digabung tidak muncul lagi di scan duplikat
  F. Pratinjau memuat angka untuk catatan kertas (id pasien, id transaksi, nota)

⚠ Bagian C & D MENULIS ke DB: membuat pasien uji bernama "ZZ UJI GABUNG ..."
  lalu menggabungkannya. Karena penggabungan TIDAK BISA DIBATALKAN, script ini
  hanya mau jalan kalau DB-nya bukan produksi (lihat _pastikan_bukan_produksi).

Jalankan dari `sehati_clinic/`:  python -m scripts.cek_gabung_pasien
"""
import logging
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.db.session import engine as _eng  # noqa: E402

# Mematikan level logger SAJA tidak cukup: `create_engine(echo=True)` memasang
# handler-nya sendiri saat engine dibuat. Harus `engine.echo = False` SESUDAH
# engine di-import. Pola yang sama dipakai scripts/gen_finance_export.py.
_eng.echo = False
for _n in ("sqlalchemy.engine", "sqlalchemy.engine.Engine"):
    logging.getLogger(_n).setLevel(logging.WARNING)

from app.services.audit_pasien_service import (  # noqa: E402
    TABEL_DIKECUALIKAN, TABEL_PINDAH, AuditPasienService,
)

PREFIKS_UJI = "ZZ UJI GABUNG"
_lulus, _gagal = 0, 0


def cek(label, ok, detail=""):
    global _lulus, _gagal
    if ok:
        _lulus += 1
        print(f"  ✓ {label}" + (f"\n      {detail}" if detail else ""))
    else:
        _gagal += 1
        print(f"  ✗ {label}" + (f"\n      {detail}" if detail else ""))


def _pastikan_bukan_produksi(db):
    """Penggabungan tidak bisa dibatalkan — jangan pernah menguji di DB klinik.

    Pagar sengaja LONGGAR tapi jelas: nama database harus memuat 'dev' atau
    'test', ATAU tidak boleh ada pasien selain pasien uji & seed. Kalau ragu,
    berhenti. Lebih baik pemeriksa menolak jalan daripada menggabungkan pasien
    sungguhan tanpa bisa dibatalkan.
    """
    nama_db = db.execute(text("SELECT DATABASE()")).scalar() or ""
    n_pasien = db.execute(text("SELECT COUNT(*) FROM pasien")).scalar() or 0
    aman = ("dev" in nama_db.lower() or "test" in nama_db.lower() or n_pasien <= 50)
    if not aman:
        print(f"\n  ⛔ BERHENTI. Database '{nama_db}' punya {n_pasien} pasien dan "
              f"namanya tidak memuat 'dev'/'test'.\n"
              f"     Bagian C & D menggabungkan pasien, dan penggabungan TIDAK BISA "
              f"DIBATALKAN.\n"
              f"     Jalankan pemeriksa ini hanya di DB pengembangan.")
        return False
    print(f"      DB '{nama_db}', {n_pasien} pasien -> aman untuk uji tulis")
    return True


# ------------------------------------------------------------------ A. registry
def bagian_a(db):
    print("A. Registry tabel vs information_schema\n")
    baris = db.execute(text(
        "SELECT TABLE_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND COLUMN_NAME = 'id_pasien' "
        "ORDER BY TABLE_NAME")).all()
    di_db = {r[0] for r in baris}
    terdaftar = {t for t, _ in TABEL_PINDAH}
    dikecualikan = set(TABEL_DIKECUALIKAN)

    belum = sorted(di_db - terdaftar - dikecualikan)
    # Angkanya harus berjumlah. `pasien_duplikat_dismiss` ada di daftar
    # pengecualian tapi TIDAK ada di `di_db` (kolomnya id_pasien_a/b), jadi yang
    # dilaporkan adalah irisan — bukan panjang daftar pengecualian.
    kecuali_relevan = sorted(di_db & dikecualikan)
    cek("Tidak ada tabel ber-id_pasien yang belum terdaftar", not belum,
        f"{len(di_db)} tabel ber-kolom id_pasien di DB = "
        f"{len(terdaftar)} dipindahkan + {len(kecuali_relevan)} dikecualikan "
        f"({', '.join(kecuali_relevan)})"
        if not belum else
        "BELUM TERDAFTAR (riwayat akan tertinggal diam-diam):\n      "
        + "\n      ".join(belum)
        + "\n      -> tambahkan ke TABEL_PINDAH, atau ke TABEL_DIKECUALIKAN "
          "beserta ALASANNYA")

    hantu = sorted(terdaftar - di_db)
    cek("Tidak ada tabel terdaftar yang sudah tidak ada di DB", not hantu,
        "semua ada" if not hantu else
        f"TIDAK ADA di DB (UPDATE akan error saat gabung): {hantu}")

    print("\n   Pengecualian terdaftar (disengaja):")
    for t, alasan in TABEL_DIKECUALIKAN.items():
        print(f"      {t}\n         -> {alasan}")


# -------------------------------------------------------------- pasien uji
def _id_staf_apa_saja(db) -> int:
    """Satu id_staf yang benar-benar ADA. transaksi_kasir.id_staf_kasir NOT NULL
    dan ber-FK ke master_staf — angka 1 yang ditebak bisa saja tidak ada."""
    sid = db.execute(text(
        "SELECT id_staf FROM master_staf ORDER BY id_staf LIMIT 1")).scalar()
    if sid is None:
        raise RuntimeError("Tidak ada baris di master_staf — seed dulu DB-nya.")
    return int(sid)


def _id_membership_apa_saja(db):
    """id_membership yang ADA, atau None kalau master_membership kosong."""
    return db.execute(text(
        "SELECT id_membership FROM master_membership ORDER BY id_membership "
        "LIMIT 1")).scalar()


def _buat_pasien_uji(db, suffix: str) -> int:
    """Buat satu pasien uji + 1 kunjungan + 1 transaksi + 1 alergi.

    ⚠ Kolomnya diambil dari model, bukan dari ingatan. Yang sempat salah saat
      ditulis: `pasien_alergi.alergen` (BUKAN nama_alergi), dan transaksi_kasir
      butuh `id_staf_kasir` + `rincian_tagihan` yang keduanya NOT NULL.
      `kunjungan.tgl_kunjungan` & `status_antrian` punya server_default, jadi
      tidak wajib — tapi diisi supaya barisnya masuk akal kalau terlihat orang.
    """
    stamp = datetime.now().strftime("%H%M%S%f")[:10]
    no_rm = f"ZZ{stamp}{suffix}"[:20]
    sid = _id_staf_apa_saja(db)

    # ⚠ jenis_kelamin di DB adalah ENUM('L','P') — nilainya 'L', BUKAN 'PRIA'.
    #   GenderEnum.LAKI_LAKI = "L". Nama anggota enum Python bukan nilai kolomnya;
    #   MySQL menolaknya dengan "Data truncated", pesan yang tidak menyebut sebabnya.
    db.execute(text(
        "INSERT INTO pasien (no_rm, nama, jenis_kelamin, tgl_lahir, is_active) "
        "VALUES (:rm, :nama, 'L', :tgl, 1)"),
        {"rm": no_rm, "nama": f"{PREFIKS_UJI} {suffix}", "tgl": date(1990, 1, 1)})
    pid = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()

    db.execute(text(
        "INSERT INTO kunjungan (id_pasien, tgl_kunjungan, status_antrian) "
        "VALUES (:p, :t, 'COMPLETED')"), {"p": pid, "t": datetime.now()})
    kid = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()

    db.execute(text(
        "INSERT INTO transaksi_kasir "
        "(id_kunjungan, id_pasien, id_staf_kasir, jenis_transaksi, "
        " rincian_tagihan, total_tagihan, status_transaksi, doc_number) "
        # status_transaksi hanya mengenal 'BAYAR' dan 'VOID' (kolomnya VARCHAR,
        # jadi nilai ngawur DITERIMA diam-diam dan baru bikin laporan aneh nanti).
        # Nominalnya sengaja 1 rupiah: baris ini sempat hidup beberapa milidetik
        # dan kalau kebetulan ada yang membuka laporan kas hari ini, jangan sampai
        # menggeser angkanya secara berarti.
        "VALUES (:k, :p, :s, 'KLINIS', :rinci, 1, 'BAYAR', :nota)"),
        {"k": kid, "p": pid, "s": sid, "rinci": '[{"uji":"cek_gabung_pasien"}]',
         "nota": f"NOTA-UJI-{suffix}-{stamp}"[:30]})

    db.execute(text(
        "INSERT INTO pasien_alergi (id_pasien, alergen, tingkat_keparahan, is_active) "
        "VALUES (:p, 'UJI-alergen', 'Ringan', 1)"), {"p": pid})
    db.commit()
    return int(pid)


def _bersihkan_pasien_uji(db):
    """Hapus SEMUA jejak pasien uji. Hanya menyentuh nama ber-PREFIKS_UJI."""
    ids = [r[0] for r in db.execute(text(
        "SELECT id_pasien FROM pasien WHERE nama LIKE :p"),
        {"p": f"{PREFIKS_UJI}%"}).all()]
    if not ids:
        return 0
    marks = ",".join(str(int(i)) for i in ids)
    db.execute(text(f"DELETE FROM pasien_duplikat_dismiss "
                    f"WHERE id_pasien_a IN ({marks}) OR id_pasien_b IN ({marks})"))
    db.execute(text(f"DELETE FROM transaksi_kasir WHERE id_pasien IN ({marks})"))
    for tabel, _ in TABEL_PINDAH:
        if tabel == "transaksi_kasir":
            continue
        db.execute(text(f"DELETE FROM {tabel} WHERE id_pasien IN ({marks})"))
    db.execute(text(f"DELETE FROM pasien WHERE id_pasien IN ({marks})"))
    db.commit()
    return len(ids)


# ------------------------------------------------------------------- B/C/D/E/F
def bagian_bcdef(db):
    svc = AuditPasienService(db)

    print("\nB. Pratinjau MURNI BACA\n")
    dup = _buat_pasien_uji(db, "DUP")
    srv = _buat_pasien_uji(db, "SRV")
    sebelum = svc._hitung_baris(dup)
    pra = svc.pratinjau_gabung(dup, srv)
    sesudah = svc._hitung_baris(dup)
    cek("Jumlah baris tidak berubah setelah pratinjau", sebelum == sesudah,
        f"total {sum(sebelum.values())} baris, tetap sama")
    cek("Pratinjau menyatakan bisa digabung", pra["bisa_digabung"],
        f"penghalang: {pra['penghalang']}")

    print("\nF. Pratinjau memuat angka untuk catatan kertas\n")
    cek("Ada id_pasien & no_rm KEDUA pasien",
        all(pra[k].get("id_pasien") and pra[k].get("no_rm")
            for k in ("duplikat", "bertahan")),
        f"{pra['duplikat']['no_rm']} -> {pra['bertahan']['no_rm']}")
    cek("Ada daftar id transaksi", bool(pra["transaksi"]),
        f"{len(pra['transaksi'])} transaksi: "
        f"{[t['id_transaksi'] for t in pra['transaksi']]}")
    cek("Ada nomor nota (bukan '—')",
        all(t["no_nota"] != "—" for t in pra["transaksi"]),
        f"nota: {[t['no_nota'] for t in pra['transaksi']]}")
    cek("Ada jumlah baris PER TABEL",
        len(pra["baris"]) == len(TABEL_PINDAH),
        f"{len(pra['baris'])} tabel, total {pra['total_baris']} baris")

    print("\nD. Membership ganda -> DITOLAK\n")
    id_mb = _id_membership_apa_saja(db)
    if id_mb is None:
        cek("Uji membership ganda", False,
            "DILEWATI: master_membership kosong, tidak bisa membuat membership uji. "
            "Seed master_membership lalu jalankan ulang.")
    else:
        sid = _id_staf_apa_saja(db)
        d2 = _buat_pasien_uji(db, "MD")
        s2 = _buat_pasien_uji(db, "MS")
        for pid in (d2, s2):
            # tgl_expired NOT NULL — jangan ditebak sebagai opsional
            db.execute(text(
                "INSERT INTO pasien_membership_history "
                "(id_pasien, id_membership, tgl_aktif, tgl_expired, harga_bayar, "
                " id_staf_aktivasi, is_active) "
                "VALUES (:p, :m, :t, :e, 0, :s, 1)"),
                {"p": pid, "m": id_mb, "t": date.today(),
                 "e": date(date.today().year + 1, 1, 1), "s": sid})
        db.commit()
        _, _, halangan = svc._pagar_gabung(d2, s2)
        cek("Pagar mendeteksi membership ganda", bool(halangan),
            halangan[0][:110] if halangan else "TIDAK TERDETEKSI")
        pra2 = svc.pratinjau_gabung(d2, s2)
        cek("Pratinjau menolak dan MENJELASKAN kenapa",
            not pra2["bisa_digabung"] and bool(pra2["penghalang"]),
            "tombol mati dengan alasan yang bisa dibaca petugas")
        ditolak = False
        try:
            svc.gabungkan(d2, s2, "uji membership ganda", actor_id_staf=sid)
        except Exception as e:
            ditolak = getattr(e, "status_code", None) == 409
        cek("gabungkan() menolak dengan 409", ditolak,
            "eksekusi tidak percaya hasil pratinjau — pagarnya dijalankan ulang")

    print("\nC. Penggabungan end-to-end\n")
    n_srv_awal = svc._hitung_baris(srv)
    db.execute(text(
        "INSERT INTO pasien_duplikat_dismiss (id_pasien_a, id_pasien_b, alasan) "
        "VALUES (:a, :b, 'uji')"),
        {"a": min(dup, srv), "b": max(dup, srv)})
    db.commit()

    hasil = svc.gabungkan(dup, srv, "uji otomatis cek_gabung_pasien",
                          actor_id_staf=_id_staf_apa_saja(db))
    n_dup_sisa = svc._hitung_baris(dup)
    n_srv_akhir = svc._hitung_baris(srv)

    cek("Tidak ada baris yang masih menunjuk duplikat",
        sum(n_dup_sisa.values()) == 0,
        f"sisa: { {t: n for t, n in n_dup_sisa.items() if n} or 'nihil'}")
    cek("Jumlah yang dipindah cocok dengan pratinjau",
        hasil["data"]["total_dipindah"] == pra["total_baris"],
        f"pratinjau {pra['total_baris']}, dipindah "
        f"{hasil['data']['total_dipindah']}")
    naik = {t: n_srv_akhir[t] - n_srv_awal[t] for t in n_srv_akhir}
    cek("Pasien bertahan naik tepat sebanyak yang dipindah",
        sum(naik.values()) == hasil["data"]["total_dipindah"],
        f"naik {sum(naik.values())} baris")

    d_row = db.execute(text(
        "SELECT is_active, digabung_ke_id_pasien, nomor_ktp FROM pasien "
        "WHERE id_pasien = :i"), {"i": dup}).one()
    cek("Duplikat nonaktif & menunjuk pasien yang bertahan",
        d_row[0] == 0 and d_row[1] == srv,
        f"is_active={d_row[0]}, digabung_ke={d_row[1]}")

    n_dis = db.execute(text(
        "SELECT COUNT(*) FROM pasien_duplikat_dismiss "
        "WHERE id_pasien_a = :i OR id_pasien_b = :i"), {"i": dup}).scalar()
    cek("Baris pasien_duplikat_dismiss dibereskan", n_dis == 0,
        f"dismiss_dihapus={hasil['data']['dismiss_dihapus']}, sisa={n_dis}")

    # kolomnya id_log, bukan id_audit — diperiksa dari model, tidak ditebak
    audit = db.execute(text(
        "SELECT data_baru FROM audit_log WHERE aksi = 'PASIEN_GABUNG' "
        "AND id_target = :i ORDER BY id_log DESC LIMIT 1"), {"i": dup}).scalar()
    ada_rincian = bool(audit) and "baris_dipindah" in str(audit)
    ada_nota = bool(audit) and "no_nota_pindah" in str(audit)
    cek("audit_log memuat rincian per tabel", ada_rincian)
    cek("audit_log memuat id transaksi & nomor nota", ada_nota,
        "satu-satunya bukti digital; sisanya di catatan kertas")

    print("\nE. Pasangan yang sudah digabung tidak muncul lagi di scan\n")
    # scan() mengembalikan {"kandidat": [{"id_a","id_b","a","b",...}]}
    hasil_scan = svc.scan()
    kandidat = hasil_scan.get("kandidat") or []
    muncul = [(k["id_a"], k["id_b"]) for k in kandidat
              if dup in (k["id_a"], k["id_b"])]
    cek("Duplikat yang sudah digabung tidak jadi kandidat", not muncul,
        f"scan hanya memuat pasien aktif ({hasil_scan['total_kandidat']} kandidat "
        f"dari {hasil_scan['total_pasien']} pasien)" if not muncul
        else f"MASIH MUNCUL sebagai kandidat: {muncul}")


def main():
    db = SessionLocal()
    try:
        bagian_a(db)
        print("\n   Pagar keselamatan uji tulis:")
        if not _pastikan_bukan_produksi(db):
            print(f"\nHASIL SEBAGIAN: {_lulus} lulus, {_gagal} gagal "
                  f"(bagian B–F dilewati)")
            return 1 if _gagal else 0
        _bersihkan_pasien_uji(db)
        try:
            bagian_bcdef(db)
        finally:
            n = _bersihkan_pasien_uji(db)
            print(f"\n   Bersih-bersih: {n} pasien uji dihapus.")
        print(f"\nHASIL: {_lulus} lulus, {_gagal} gagal")
        return 1 if _gagal else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
