"""Satu-satunya definisi "isi kunjungan -> status kunjungan" (bayar dulu, tahap 1).

Spec: Project_Memory/DESAIN_BAYAR_DULU_BERCABANG.md §3.2 (+ klarifikasi 2026-10-21).

Kenapa satu modul (CLAUDE.md §4.1, "satu hal, dua penulis"): `kunjungan.status_antrian`
dulu ditulis tangan di belasan tempat (dokter simpan SOAP, perawat selesai, kasir bayar,
apotek serah, void ...), masing-masing dengan tebakannya sendiri soal "apa yang tersisa".
Begitu satu kunjungan boleh punya beberapa cabang sekaligus (tindakan jalan, obat sudah
dibayar, tagihan susulan), tebakan itu saling bertabrakan. Sekarang ada TIGA kondisi
yang dirumuskan SEKALI di sini:

  (T) ada tindakan PENDING/PROSES                   -> masih di ruang treatment
  (K) ada yang BELUM DITAGIH                        -> antrian kasir
  (O) ada obat DIBAYAR, belum diserahkan            -> antrian apotek

Dua pemakai, satu definisi:
  1. `status_seharusnya` / `hitung_ulang_status` — penulis status (Task 4).
  2. `kondisi_T()` / `kondisi_K()` / `kondisi_O()` — ekspresi EXISTS yang dipakai langsung
     oleh kueri antrian perawat/kasir/apotek (Task 5). Kalau antrian punya saringan
     sendiri, suatu hari ia berbeda dari label status dan kunjungan "hilang" dari layar
     tanpa error. Jangan menulis ulang kondisi ini di tempat lain: panggil fungsinya.

Catatan arti:
  - Resep DITUNDA ("sisakan") BUKAN tersisa untuk (K): ia diurus modul Obat Tertunda.
  - Obat DIBAYAR yang `tgl_janji_kirim`-nya terisi bukan (O): jalur obat tertunda
    sengaja DIBAYAR + COMPLETED + tgl_janji_kirim (lihat test T2-1).
  - (K) juga benar bila sudah ada SOAP FINAL dan belum ada transaksi kasir SAMA SEKALI
    (status apa pun): konsultasi tanpa item pun tetap ditagih (biaya konsul). Transaksi
    VOID berarti kasir sudah pernah menangani kunjungan ini.
  - Tahap 1 hanya menagih tindakan SELESAI; PENDING/PROSES masuk (T), bukan (K).
  - "Jangan disentuh" (None) hanya untuk kunjungan yang BELUM BERISI apa pun: tanpa SOAP
    FINAL, tanpa item hidup, DAN tanpa transaksi kasir (status apa pun). Kunjungan yang
    isinya habis karena void (item BATAL + transaksi VOID) dihitung biasa → COMPLETED.
    (Ruling 7, bayar dulu T1-4 — menyempurnakan klarifikasi §3.2.)

Tidak ada commit di sini; pemanggil memegang kunci/transaksi.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    Kunjungan,
    KunjunganResep,
    KunjunganTindakan,
    PemeriksaanKlinis,
    StatusItemResepEnum,
    StatusTindakanEnum,
    TransaksiKasir,
)
from app.db.models.racikan import KunjunganRacikan
from app.repositories.kunjungan_repo import KunjunganRepository

_BATAL = "BATAL"
# Status yang tidak boleh ditimpa oleh label hitungan.
_STATUS_TANPA_SOAP_DIBIARKAN = ("ANTRI_KONSULTASI", "KONSULTASI")


def _ada(*kriteria):
    """EXISTS berkorelasi ke `Kunjungan` di kueri luar (auto-correlate)."""
    return exists().where(*kriteria)


def _tindakan(*kriteria):
    return _ada(KunjunganTindakan.id_kunjungan == Kunjungan.id_kunjungan, *kriteria)


def _resep(*kriteria):
    return _ada(KunjunganResep.id_kunjungan == Kunjungan.id_kunjungan, *kriteria)


def _racikan(*kriteria):
    return _ada(KunjunganRacikan.id_kunjungan == Kunjungan.id_kunjungan, *kriteria)


def _item_obat(status_resep, status_racikan):
    return or_(_resep(KunjunganResep.status_item == status_resep),
               _racikan(KunjunganRacikan.status_item == status_racikan))


def kondisi_T_proses():
    return _tindakan(KunjunganTindakan.status_tindakan == StatusTindakanEnum.PROSES)


def kondisi_T_pending():
    return _tindakan(KunjunganTindakan.status_tindakan == StatusTindakanEnum.PENDING)


def kondisi_T():
    """Masih ada tindakan yang belum selesai dikerjakan."""
    return or_(kondisi_T_proses(), kondisi_T_pending())


def kondisi_ada_soap():
    """SOAP FINAL (draf apoteker bukan SOAP — lihat komentar `status_soap`)."""
    return _ada(PemeriksaanKlinis.id_kunjungan == Kunjungan.id_kunjungan,
                PemeriksaanKlinis.status_soap == "FINAL")


def kondisi_K():
    """Ada yang belum ditagih (antrian kasir)."""
    tindakan_belum_ditagih = _tindakan(
        KunjunganTindakan.status_tindakan == StatusTindakanEnum.SELESAI,
        KunjunganTindakan.id_transaksi.is_(None))
    obat_pending = _item_obat(StatusItemResepEnum.PENDING, "PENDING")
    belum_pernah_ditagih = and_(
        kondisi_ada_soap(),
        # Transaksi berstatus APA PUN dihitung, termasuk VOID: kunjungan yang satu-satunya
        # transaksinya di-void (resep/racikan jadi BATAL, SOAP tetap FINAL) sudah ditangani
        # kasir; kalau dihitung "belum ditagih" ia balik ke antrian kasir dan memblokir
        # tutup kasir. Susulan sesudah void tetap tertangkap klausa lain (resep/racikan
        # PENDING, tindakan SELESAI tanpa id_transaksi).
        ~kondisi_ada_transaksi())
    return or_(tindakan_belum_ditagih, obat_pending, belum_pernah_ditagih)


def kondisi_O():
    """Ada obat sudah dibayar tapi belum diserahkan (antrian apotek)."""
    return and_(_item_obat(StatusItemResepEnum.DIBAYAR, "DIBAYAR"),
                Kunjungan.tgl_janji_kirim.is_(None))


def kondisi_tertunda():
    """Obat TERTUNDA: obat DIBAYAR + janji kirim/ambil, kunjungan bukan BATAL.

    SATU definisi untuk daftar Obat Tertunda, dua lencananya (dashboard & header) dan
    pintu serah (`ApotekService.serahkan_obat`). Bayar dulu, review akhir tahap 1 (I3):
    dulu keempatnya menyalin `status_antrian == 'COMPLETED'` — benar selama tunda selalu
    menutup kunjungan. Sejak Ruling 9 tunda juga diterima saat tindakan masih berjalan
    (label ON_TREATMENT/ANTRI_TREATMENT), dan obat itu lalu hilang dari SEMUA layar
    (keluar dari apotek karena janji terisi, tak masuk Obat Tertunda karena belum
    COMPLETED) dan pintu serah menolaknya. Syarat obat DIBAYAR: janji yang tersisa
    sesudah semua itemnya di-refund/diserahkan bukan obat tertunda.
    Kebalikan persis dari (O) untuk obat DIBAYAR: (O) = tanpa janji, ini = dengan janji.
    """
    return and_(Kunjungan.status_antrian != _BATAL,
                Kunjungan.tgl_janji_kirim.is_not(None),
                _item_obat(StatusItemResepEnum.DIBAYAR, "DIBAYAR"))


def obat_tertunda_di(db: Session, id_kunjungan: int) -> bool:
    """`kondisi_tertunda` untuk satu kunjungan (pintu serah)."""
    return bool(db.execute(select(kondisi_tertunda()).select_from(Kunjungan)
                           .where(Kunjungan.id_kunjungan == id_kunjungan)).scalar())


def ringkas_obat_tertunda(db: Session, today: Optional[date] = None) -> dict:
    """{"total", "overdue"} untuk lencana Obat Tertunda — HARUS sama dengan panjang
    `ApotekService.list_obat_tertunda` (test_obat_tertunda_saat_tindakan_berjalan_...)."""
    today = today or date.today()
    tgl = db.execute(select(Kunjungan.tgl_janji_kirim).where(kondisi_tertunda())).scalars().all()
    return {"total": len(tgl), "overdue": sum(1 for d in tgl if d is not None and d <= today)}


def kondisi_ada_transaksi():
    """Ada transaksi kasir berstatus APA PUN (VOID = kasir sudah menangani)."""
    return _ada(TransaksiKasir.id_kunjungan == Kunjungan.id_kunjungan)


def kondisi_ada_isi():
    """Ada tindakan/resep/racikan apa pun selain yang BATAL."""
    return or_(
        _tindakan(or_(KunjunganTindakan.status_tindakan.is_(None),
                      KunjunganTindakan.status_tindakan != StatusTindakanEnum.BATAL)),
        _resep(or_(KunjunganResep.status_item.is_(None),
                   KunjunganResep.status_item != StatusItemResepEnum.BATAL)),
        _racikan(or_(KunjunganRacikan.status_item.is_(None),
                     KunjunganRacikan.status_item != _BATAL)),
    )


# ---------------------------------------------------------------------------------
# Antrian meja (bayar dulu T1-5, spec §3.3). Ketiga antrian dan lencana menunya memakai
# saringan + kondisi DI BAWAH INI, bukan label. Kalau lencana menghitung label sementara
# daftar membaca isi, angka merah di menu berselisih dengan isi layar (mis. obat lunas
# saat tindakan berjalan: label ON_TREATMENT, tapi tampil di apotek).
# Kunci dict = `badge_status` di app/web/menu.py — JANGAN diganti tanpa mengubah menu.
# Dokter TIDAK di sini: antrian dokter tetap membaca label (spec §3.3).
# ---------------------------------------------------------------------------------
def kondisi_meja_perawat():
    """Antrian perawat = (T) ATAU label KONSULTASI (Ruling 10, bayar dulu T1-5).

    Kenapa label KONSULTASI ikut (satu-satunya label di antrian meja): tautan "Kerjakan"
    di antrian perawat adalah SATU-SATUNYA pintu ke form upsell perawat. Pasien yang
    sedang konsultasi tampil di sana supaya perawat bisa menambahkan tindakan PERTAMA
    selama konsultasi — saat itu belum ada tindakan, jadi (T) saja tidak akan
    menampilkannya. Membuang klausa ini = perawat kehilangan jalan masuk ke upsell.
    ANTRI_KONSULTASI sengaja TIDAK (TODO-NEW-4/DEC-063: pasien belum dipanggil dokter).
    """
    return or_(kondisi_T(), Kunjungan.status_antrian == "KONSULTASI")


KONDISI_MEJA = {
    "ANTRI_TREATMENT": kondisi_meja_perawat,  # perawat: tindakan PENDING/PROSES, atau sedang konsul
    "ANTRI_BAYAR": kondisi_K,       # kasir: ada yang belum ditagih
    "ANTRI_OBAT": kondisi_O,        # apotek: obat DIBAYAR, belum diserahkan, tanpa janji
}


def saringan_meja_hari_ini(today: date):
    """Saringan bersama tiga meja: kunjungan HARI INI, bukan BATAL, dan KLINIS.

    Hari ini saja (seperti sebelumnya): sisa kemarin diurus jalurnya sendiri (Obat
    Tertunda, tutup kasir). Status NULL ikut tersaring (`!=` tidak benar untuk NULL) —
    sama dengan dulu, saat antrian hanya menampilkan label tertentu.

    Bukan-klinis (I4, review akhir tahap 1): kunjungan RETUR_PASIEN adalah wadah draf SOAP
    alergi (COMPLETED, tanpa transaksi). Begitu drafnya disetujui ada SOAP FINAL tanpa
    transaksi → (K) benar → pasien muncul di kasir untuk "konsultasi" yang tak pernah
    terjadi. Dulu antrian membaca label (COMPLETED) sehingga tak terlihat."""
    from app.services._jenis_kunjungan import JENIS_KUNJUNGAN_BUKAN_KLINIS
    return and_(func.date(Kunjungan.tgl_kunjungan) == today,
                Kunjungan.status_antrian != _BATAL,
                Kunjungan.jenis_kunjungan.notin_(JENIS_KUNJUNGAN_BUKAN_KLINIS))


def hitung_antrian_meja(db: Session, today: date) -> dict:
    """Jumlah kunjungan per meja — HARUS sama dengan panjang daftar antriannya
    (test_lencana_meja_sama_dengan_panjang_antrian). Satu kueri."""
    kolom = [func.coalesce(func.sum(case((k(), 1), else_=0)), 0) for k in KONDISI_MEJA.values()]
    baris = db.execute(select(*kolom).select_from(Kunjungan)
                       .where(saringan_meja_hari_ini(today))).one()
    return {kunci: int(n or 0) for kunci, n in zip(KONDISI_MEJA, baris)}


def ringkasan(db: Session, id_kunjungan: int) -> dict:
    baris = db.execute(
        select(kondisi_T_proses(), kondisi_T_pending(), kondisi_K(), kondisi_O(),
               kondisi_ada_isi(), kondisi_ada_soap(), kondisi_ada_transaksi())
        .select_from(Kunjungan).where(Kunjungan.id_kunjungan == id_kunjungan)
    ).one_or_none()
    kunci = ("T_proses", "T_pending", "K", "O", "ada_isi", "ada_soap", "ada_transaksi")
    if baris is None:
        return {k: False for k in kunci}
    return {k: bool(v) for k, v in zip(kunci, baris)}


def status_seharusnya(db: Session, id_kunjungan: int) -> Optional[str]:
    """Label status menurut isi kunjungan; None = jangan disentuh."""
    from app.services._jenis_kunjungan import JENIS_KUNJUNGAN_BUKAN_KLINIS
    baris = db.execute(select(Kunjungan.status_antrian, Kunjungan.jenis_kunjungan)
                       .where(Kunjungan.id_kunjungan == id_kunjungan)).one_or_none()
    if baris is None:
        return None
    status = getattr(baris[0], "value", baris[0])
    if status is None or status == _BATAL:
        return None
    # Kunjungan NON-KLINIS (RETUR_PASIEN — wadah draf SOAP alergi, dibuat langsung COMPLETED,
    # tak pernah ke kasir) tidak disentuh. Tanpa ini draf yang disetujui dokter (SOAP FINAL,
    # tanpa transaksi) memenuhi klausa SOAP pada (K) → ANTRI_BAYAR → gerbang tutup kasir (yang
    # membaca label) tertahan. Meja sudah menyaring jenis ini (`saringan_meja_hari_ini`);
    # fungsi status harus sepakat. Sisa tinjauan akhir tahap 1, 2026-10-21.
    if getattr(baris[1], "value", baris[1]) in JENIS_KUNJUNGAN_BUKAN_KLINIS:
        return None
    r = ringkasan(db, id_kunjungan)
    # "Belum berisi apa pun" = tanpa SOAP, tanpa item hidup, DAN belum pernah ke kasir.
    # Syarat transaksi (Ruling 7, Task 4): kunjungan beli produk yang satu-satunya
    # transaksinya di-void (resep jadi BATAL) BUKAN kunjungan kosong — tanpa syarat ini
    # ia tertinggal ANTRI_OBAT selamanya; begitu pula kunjungan MEMBERSHIP_ONLY lama.
    if not r["ada_soap"] and not r["ada_isi"] and not r["ada_transaksi"]:
        return None
    if status in _STATUS_TANPA_SOAP_DIBIARKAN and not r["ada_soap"]:
        return None
    if r["T_proses"]:
        return "ON_TREATMENT"
    if r["T_pending"]:
        return "ANTRI_TREATMENT"
    if r["K"]:
        return "ANTRI_BAYAR"
    if r["O"]:
        return "ANTRI_OBAT"
    return "COMPLETED"


def hitung_ulang_status(db: Session, id_kunjungan: int) -> str:
    """Tulis label bila ada dan berbeda; kembalikan status akhir. Tidak commit."""
    kunjungan = db.get(Kunjungan, id_kunjungan)
    label = status_seharusnya(db, id_kunjungan)
    saat_ini = getattr(kunjungan.status_antrian, "value", kunjungan.status_antrian)
    if label is not None and label != saat_ini:
        KunjunganRepository(db).update_status(kunjungan, label)
        return label
    return saat_ini
