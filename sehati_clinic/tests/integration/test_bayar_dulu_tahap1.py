"""Bayar dulu tahap 1 (2026-10-21) — Project_Memory/DESAIN_BAYAR_DULU_BERCABANG.md.

T1-1: migrasi 20261021_0100 — `kunjungan_tindakan.id_transaksi` (+ BATAL, PRABAYAR,
`transaksi_refund.id_kunjungan_tindakan`) dan backfillnya.
"""
import importlib.util
import pathlib
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.db.models import KunjunganTindakan
from tests.integration.test_audit_tahap2 import (V, _siapkan, _bayar, _tindakan_selesai,  # noqa: F401
                                                 _trx_terakhir, db)


def _muat_migrasi():
    path = (pathlib.Path(__file__).parents[2]
            / "migrations/versions/20261021_0100_bayar_dulu_tahap1.py")
    spec = importlib.util.spec_from_file_location("mig_bayar_dulu_t1", path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    return mig


def _tindakan_lunas(db, snapshot=True):
    """Tindakan SELESAI yang sudah DIBAYAR, lalu dikembalikan ke keadaan 'data lama':
    id_transaksi NULL (kolomnya baru). snapshot=False meniru data pra-F3."""
    staf, k = _siapkan(db)
    _tindakan_selesai(db, k, detik=-5)      # selesai SEBELUM bayar
    _bayar(db, k, staf)
    trx = _trx_terakhir(db, k)
    t = db.execute(select(KunjunganTindakan).where(
        KunjunganTindakan.id_kunjungan == k.id_kunjungan)).scalar_one()
    if not snapshot:
        db.execute(text("DELETE FROM transaksi_detail_tindakan WHERE id_transaksi = :t"),
                   {"t": trx.id_transaksi})
    db.execute(text("UPDATE kunjungan_tindakan SET id_transaksi = NULL "
                    "WHERE id_kunjungan_tindakan = :i"), {"i": t.id_kunjungan_tindakan})
    db.flush(); db.expire(t)
    return t, trx


def test_backfill_dari_snapshot(db):
    mig = _muat_migrasi()
    t, trx = _tindakan_lunas(db, snapshot=True)
    assert t.id_transaksi is None
    hasil = mig.isi_id_transaksi_tindakan(db.connection())
    db.expire(t)
    assert t.id_transaksi == trx.id_transaksi
    assert hasil["dari_snapshot"] >= 1


def test_backfill_dari_cutoff_pra_f3(db):
    mig = _muat_migrasi()
    t, trx = _tindakan_lunas(db, snapshot=False)
    assert trx.waktu_bayar >= t.waktu_selesai
    hasil = mig.isi_id_transaksi_tindakan(db.connection())
    db.expire(t)
    assert t.id_transaksi == trx.id_transaksi
    assert hasil["dari_cutoff"] >= 1


def test_backfill_aman_dijalankan_ulang(db):
    mig = _muat_migrasi()
    _tindakan_lunas(db, snapshot=True)
    _tindakan_lunas(db, snapshot=False)
    mig.isi_id_transaksi_tindakan(db.connection())
    kedua = mig.isi_id_transaksi_tindakan(db.connection())
    assert kedua["dari_snapshot"] == 0 and kedua["dari_cutoff"] == 0


# ---------------------------------------------------------------- T1-2
def test_bayar_menandai_tindakan_yang_ditagih(db):
    staf, k = _siapkan(db)
    _tindakan_selesai(db, k, detik=-5)
    _bayar(db, k, staf)
    trx = _trx_terakhir(db, k)
    t = db.execute(select(KunjunganTindakan).where(
        KunjunganTindakan.id_kunjungan == k.id_kunjungan)).scalar_one()
    assert t.id_transaksi == trx.id_transaksi


def test_tindakan_selesai_di_detik_bayar_tetap_tertagih_susulan(db):
    """Dulu saringan `waktu_selesai > waktu_bayar` menghilangkan tindakan yang selesai
    di detik yang sama dengan bayar dulu."""
    from app.services.kasir_service import KasirService
    staf, k = _siapkan(db)
    _tindakan_selesai(db, k, detik=-5)
    _bayar(db, k, staf)
    t1 = _trx_terakhir(db, k)
    tr = db.execute(select(KunjunganTindakan.id_treatment).where(
        KunjunganTindakan.id_kunjungan == k.id_kunjungan)).scalars().first()
    db.add(KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=tr,
                             status_tindakan="SELESAI", waktu_selesai=t1.waktu_bayar))
    db.flush()
    tagihan = KasirService(db).get_tagihan(k.id_kunjungan)
    assert tagihan.sudah_lunas is False
    assert len(tagihan.rincian_tindakan) == 1


def test_tindakan_lunas_tidak_ditagih_ulang(db):
    from app.services.kasir_service import KasirService
    staf, k = _siapkan(db)
    _tindakan_selesai(db, k, detik=-5)
    _bayar(db, k, staf)
    tagihan = KasirService(db).get_tagihan(k.id_kunjungan)
    assert tagihan.sudah_lunas is True


# ---------------------------------------------------------------- T1-3
# Modul `_status_kunjungan`: isi kunjungan -> status. Baris dimasukkan langsung (bukan lewat
# service) supaya yang diuji murni definisi (T)/(K)/(O), bukan alur penulisnya.
def _isi(db, k, staf, *, soap=False, tindakan=(), resep=(), racikan=(), bayar=False,
         janji=False, status_trx="BAYAR"):
    from app.db.models import (KunjunganResep, MasterProduk, MasterTreatment,
                               PemeriksaanKlinis, StatusItemResepEnum, TransaksiKasir)
    from app.db.models.racikan import KunjunganRacikan
    if soap:
        db.add(PemeriksaanKlinis(id_kunjungan=k.id_kunjungan, id_pasien=k.id_pasien,
                                 id_staf_dokter=staf.id_staf, status_soap="FINAL"))
    trx = None
    if bayar:
        trx = TransaksiKasir(id_kunjungan=k.id_kunjungan, id_pasien=k.id_pasien,
                             id_staf_kasir=staf.id_staf, rincian_tagihan="uji", subtotal=0,
                             nominal_diskon=0, total_tagihan=0, status_transaksi=status_trx)
        db.add(trx); db.flush()
    tr = db.execute(select(MasterTreatment).where(MasterTreatment.harga > 0).limit(1)).scalar_one()
    for st in tindakan:
        db.add(KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=tr.id_treatment,
                                 status_tindakan=st))
    p = db.execute(select(MasterProduk).where(MasterProduk.is_active.is_(True))
                   .where(MasterProduk.harga_jual > 0).limit(1)).scalar_one()
    for st in resep:
        db.add(KunjunganResep(id_kunjungan=k.id_kunjungan, id_produk=p.id_produk, qty=1,
                              status_item=StatusItemResepEnum(st), id_staf_input=staf.id_staf))
    for st in racikan:
        db.add(KunjunganRacikan(id_kunjungan=k.id_kunjungan, nama_snapshot="uji",
                                jenis_racik="PULVERES", jumlah_unit=1, status_item=st))
    if janji:
        k.tgl_janji_kirim = datetime.now().date()
    db.flush()
    return trx


def _tindakan_ditagih(db, k, trx):
    db.execute(text("UPDATE kunjungan_tindakan SET id_transaksi = :t WHERE id_kunjungan = :k "
                    "AND status_tindakan = 'SELESAI'"), {"t": trx.id_transaksi, "k": k.id_kunjungan})
    db.flush()


KASUS_STATUS = [
    # (nama, awal, isi, harapan)
    ("tindakan proses", "ANTRI_BAYAR", dict(soap=True, tindakan=["PROSES"]), "ON_TREATMENT"),
    ("proses mengalahkan pending", "ANTRI_BAYAR",
     dict(soap=True, tindakan=["PENDING", "PROSES"]), "ON_TREATMENT"),
    ("tindakan pending", "ANTRI_BAYAR", dict(soap=True, tindakan=["PENDING"]), "ANTRI_TREATMENT"),
    ("selesai belum dibayar", "ON_TREATMENT", dict(soap=True, tindakan=["SELESAI"]), "ANTRI_BAYAR"),
    ("resep pending", "ANTRI_KONSULTASI", dict(soap=True, resep=["PENDING"]), "ANTRI_BAYAR"),
    ("racikan pending", "ANTRI_KONSULTASI", dict(soap=True, racikan=["PENDING"]), "ANTRI_BAYAR"),
    ("resep dibayar belum serah", "ANTRI_BAYAR",
     dict(soap=True, resep=["DIBAYAR"], bayar=True), "ANTRI_OBAT"),
    ("racikan dibayar belum serah", "ANTRI_BAYAR",
     dict(soap=True, racikan=["DIBAYAR"], bayar=True), "ANTRI_OBAT"),
    ("dibayar tapi ada tindakan pending", "ANTRI_OBAT",
     dict(soap=True, resep=["DIBAYAR"], tindakan=["PENDING"], bayar=True), "ANTRI_TREATMENT"),
    ("semua lunas dan diserahkan", "ANTRI_OBAT",
     dict(soap=True, resep=["DISERAHKAN"], racikan=["DISERAHKAN"], bayar=True), "COMPLETED"),
    ("SOAP tanpa item tanpa transaksi", "ANTRI_KONSULTASI", dict(soap=True), "ANTRI_BAYAR"),
    ("SOAP + satu transaksi VOID + resep BATAL", "ANTRI_BAYAR",
     dict(soap=True, resep=["BATAL"], bayar=True, status_trx="VOID"), "COMPLETED"),
    ("SOAP tanpa item sudah dibayar", "ANTRI_BAYAR", dict(soap=True, bayar=True), "COMPLETED"),
    ("obat dibayar + tgl_janji_kirim", "ANTRI_BAYAR",
     dict(soap=True, resep=["DIBAYAR"], bayar=True, janji=True), "COMPLETED"),
    ("resep DITUNDA bukan tersisa", "ANTRI_BAYAR",
     dict(soap=True, resep=["DITUNDA", "DISERAHKAN"], bayar=True), "COMPLETED"),
    ("item BATAL saja, sudah dibayar", "ANTRI_BAYAR",
     dict(soap=True, resep=["BATAL"], tindakan=["BATAL"], bayar=True), "COMPLETED"),
    ("tanpa SOAP, ada item (apotek)", "ANTRI_OBAT", dict(resep=["PENDING"]), "ANTRI_BAYAR"),
    # None = jangan disentuh
    ("tanpa SOAP tanpa isi", "ANTRI_TREATMENT", dict(), None),
    ("tanpa SOAP, hanya item BATAL", "ANTRI_TREATMENT", dict(resep=["BATAL"]), None),
    ("BATAL", "BATAL", dict(soap=True, resep=["PENDING"]), None),
    ("masih konsultasi tanpa SOAP", "KONSULTASI", dict(resep=["PENDING"]), None),
    ("masih antri konsultasi tanpa SOAP", "ANTRI_KONSULTASI", dict(tindakan=["PENDING"]), None),
]


@pytest.mark.parametrize("nama,awal,isi,harapan", KASUS_STATUS, ids=[c[0] for c in KASUS_STATUS])
def test_status_seharusnya_tabel(db, nama, awal, isi, harapan):
    from app.services import _status_kunjungan as sk
    staf, k = _siapkan(db, awal)
    _isi(db, k, staf, **isi)
    assert sk.status_seharusnya(db, k.id_kunjungan) == harapan
    # hitung_ulang: menulis hanya bila ada label & beda; selalu mengembalikan status akhir.
    akhir = sk.hitung_ulang_status(db, k.id_kunjungan)
    assert akhir == (harapan or awal)
    db.refresh(k)
    assert V(k.status_antrian) == (harapan or awal)


def test_tindakan_selesai_yang_sudah_ditagih_bukan_K(db):
    from app.services import _status_kunjungan as sk
    staf, k = _siapkan(db, "ANTRI_BAYAR")
    trx = _isi(db, k, staf, soap=True, tindakan=["SELESAI"], bayar=True)
    assert sk.ringkasan(db, k.id_kunjungan)["K"] is True       # id_transaksi masih NULL
    _tindakan_ditagih(db, k, trx)
    r = sk.ringkasan(db, k.id_kunjungan)
    assert r["K"] is False and sk.status_seharusnya(db, k.id_kunjungan) == "COMPLETED"


def test_ringkasan_kunci_dan_nilai(db):
    from app.services import _status_kunjungan as sk
    staf, k = _siapkan(db, "ANTRI_BAYAR")
    _isi(db, k, staf, soap=True, tindakan=["PROSES", "PENDING"], resep=["DIBAYAR"], bayar=True)
    assert sk.ringkasan(db, k.id_kunjungan) == {
        "T_proses": True, "T_pending": True, "K": False, "O": True,
        "ada_isi": True, "ada_soap": True}


def test_draf_apoteker_bukan_soap(db):
    from app.db.models import PemeriksaanKlinis
    from app.services import _status_kunjungan as sk
    staf, k = _siapkan(db, "ANTRI_KONSULTASI")
    db.add(PemeriksaanKlinis(id_kunjungan=k.id_kunjungan, id_pasien=k.id_pasien,
                             status_soap="DRAFT_APOTEK")); db.flush()
    assert sk.ringkasan(db, k.id_kunjungan)["ada_soap"] is False
    assert sk.status_seharusnya(db, k.id_kunjungan) is None


def test_hitung_ulang_tidak_commit(db):
    from app.services import _status_kunjungan as sk
    staf, k = _siapkan(db, "ANTRI_KONSULTASI")
    _isi(db, k, staf, soap=True)
    ditandai = []
    db.commit = lambda: ditandai.append(1)
    assert sk.hitung_ulang_status(db, k.id_kunjungan) == "ANTRI_BAYAR"
    assert ditandai == []


@pytest.mark.parametrize("nama", ["T", "K", "O"])
def test_kondisi_bisa_dipakai_di_where(db, nama):
    """Kontrak untuk Task 5: ekspresi EXISTS berkorelasi, cocok di `select(...).where(...)`."""
    from app.db.models import Kunjungan
    from app.services import _status_kunjungan as sk
    kond = {"T": sk.kondisi_T, "K": sk.kondisi_K, "O": sk.kondisi_O}[nama]
    isi_cocok = {"T": dict(soap=True, tindakan=["PROSES"], bayar=True),
                 "K": dict(soap=True, resep=["PENDING"]),
                 "O": dict(soap=True, resep=["DIBAYAR"], bayar=True)}[nama]
    isi_tidak = {"T": dict(soap=True, tindakan=["SELESAI"], bayar=True),
                 "K": dict(soap=True, resep=["DISERAHKAN"], bayar=True),
                 "O": dict(soap=True, resep=["DIBAYAR"], bayar=True, janji=True)}[nama]
    staf, ya = _siapkan(db, "ANTRI_BAYAR")
    _, tidak = _siapkan(db, "ANTRI_BAYAR")
    _isi(db, ya, staf, **isi_cocok)
    t_tidak = _isi(db, tidak, staf, **isi_tidak)
    if t_tidak is not None:
        _tindakan_ditagih(db, tidak, t_tidak)
    ids = set(db.execute(select(Kunjungan.id_kunjungan).where(
        Kunjungan.id_kunjungan.in_([ya.id_kunjungan, tidak.id_kunjungan]), kond())).scalars())
    assert ids == {ya.id_kunjungan}
