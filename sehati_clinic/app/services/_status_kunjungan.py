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

Tidak ada commit di sini; pemanggil memegang kunci/transaksi.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import and_, exists, or_, select
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
        ~_ada(TransaksiKasir.id_kunjungan == Kunjungan.id_kunjungan))
    return or_(tindakan_belum_ditagih, obat_pending, belum_pernah_ditagih)


def kondisi_O():
    """Ada obat sudah dibayar tapi belum diserahkan (antrian apotek)."""
    return and_(_item_obat(StatusItemResepEnum.DIBAYAR, "DIBAYAR"),
                Kunjungan.tgl_janji_kirim.is_(None))


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


def ringkasan(db: Session, id_kunjungan: int) -> dict:
    baris = db.execute(
        select(kondisi_T_proses(), kondisi_T_pending(), kondisi_K(), kondisi_O(),
               kondisi_ada_isi(), kondisi_ada_soap())
        .select_from(Kunjungan).where(Kunjungan.id_kunjungan == id_kunjungan)
    ).one_or_none()
    kunci = ("T_proses", "T_pending", "K", "O", "ada_isi", "ada_soap")
    if baris is None:
        return {k: False for k in kunci}
    return {k: bool(v) for k, v in zip(kunci, baris)}


def status_seharusnya(db: Session, id_kunjungan: int) -> Optional[str]:
    """Label status menurut isi kunjungan; None = jangan disentuh."""
    status = db.execute(select(Kunjungan.status_antrian)
                        .where(Kunjungan.id_kunjungan == id_kunjungan)).scalar_one_or_none()
    status = getattr(status, "value", status)
    if status is None or status == _BATAL:
        return None
    r = ringkasan(db, id_kunjungan)
    if not r["ada_soap"] and not r["ada_isi"]:
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
