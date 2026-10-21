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
    # Ruling 7: isi habis karena void ≠ kunjungan kosong (beli produk yang di-void).
    ("tanpa SOAP, resep BATAL + transaksi VOID", "ANTRI_OBAT",
     dict(resep=["BATAL"], bayar=True, status_trx="VOID"), "COMPLETED"),
    ("tanpa SOAP, tanpa item, sudah dibayar (MEMBERSHIP_ONLY lama)", "ANTRI_BAYAR",
     dict(bayar=True), "COMPLETED"),
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
        "ada_isi": True, "ada_soap": True, "ada_transaksi": True}


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


# ---------------------------------------------------------------- T1-4
# Semua penulis status otomatis lewat `hitung_ulang_status`. Memakai service SEBENARNYA
# (bayar, mulai/selesai tindakan, upsell, void) — yang diuji alurnya, bukan tabelnya.
def _soap(db, k, staf):
    from app.db.models import PemeriksaanKlinis
    db.add(PemeriksaanKlinis(id_kunjungan=k.id_kunjungan, id_pasien=k.id_pasien,
                             id_staf_dokter=staf.id_staf, status_soap="FINAL"))
    db.flush()


def _tindakan_baru(db, k, status="PENDING"):
    from app.db.models import MasterTreatment
    tr = db.execute(select(MasterTreatment).where(MasterTreatment.harga > 0).limit(1)).scalar_one()
    t = KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=tr.id_treatment,
                          status_tindakan=status,
                          waktu_mulai=datetime.now() if status == "PROSES" else None)
    db.add(t); db.flush()
    return t


def test_t44_bayar_saat_tindakan_pending_tetap_di_jalur_perawat(db):
    """Audit T4-4: bayar saat tindakan B masih PENDING dulu membuat kunjungan COMPLETED,
    sehingga B hilang dari layar perawat dan tak pernah tertagih."""
    from app.services.treatment_service import TreatmentService
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    _tindakan_selesai(db, k, detik=-5)               # A
    b = _tindakan_baru(db, k, "PENDING")             # B
    _bayar(db, k, staf)                              # menagih A saja
    assert V(k.status_antrian) == "ANTRI_TREATMENT"  # dulu COMPLETED
    svc = TreatmentService(db)
    svc.start_tindakan(b.id_kunjungan_tindakan, staf.id_staf)
    db.refresh(k)
    assert V(k.status_antrian) == "ON_TREATMENT"
    hasil = svc.end_tindakan(b.id_kunjungan_tindakan, staf.id_staf)
    db.refresh(k)
    assert V(k.status_antrian) == "ANTRI_BAYAR"
    assert hasil["data"]["status_kunjungan_baru"] == "ANTRI_BAYAR"
    _bayar(db, k, staf)                              # susulan: B
    db.refresh(b)
    assert b.id_transaksi == _trx_terakhir(db, k).id_transaksi
    assert V(k.status_antrian) == "COMPLETED"


def test_selesai_tindakan_sesudah_lunas_dan_obat_menunggu(db):
    """Obat lunas belum diserahkan + tindakan susulan → kasir dulu, lalu KEMBALI ke apotek
    (T2-1 kini tercakup (O) di fungsi bersama, bukan cabang khusus di proses_bayar)."""
    from tests.integration.test_audit_tahap2 import _resep
    from app.services.treatment_service import TreatmentService
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    r = _resep(db, k, staf)
    _bayar(db, k, staf)
    assert V(k.status_antrian) == "ANTRI_OBAT"
    t = _tindakan_baru(db, k, "PROSES")
    TreatmentService(db).end_tindakan(t.id_kunjungan_tindakan, staf.id_staf)
    db.refresh(k)
    assert V(k.status_antrian) == "ANTRI_BAYAR"
    _bayar(db, k, staf)
    db.refresh(r)
    assert V(r.status_item) == "DIBAYAR"
    assert V(k.status_antrian) == "ANTRI_OBAT"


def _upsell_produk(db, k, staf):
    from app.db.models import MasterProduk
    from app.schemas.treatment import UpsellRequest
    from app.services.upsell_service import UpsellService
    p = db.execute(select(MasterProduk).where(MasterProduk.is_active.is_(True))
                   .where(MasterProduk.harga_jual > 0).limit(1)).scalar_one()
    return UpsellService(db).submit_upsell(
        UpsellRequest(id_kunjungan=k.id_kunjungan, tipe_item="PRODUK", id_item=p.id_produk),
        staf.id_staf)


def test_upsell_produk_tidak_meninggalkan_on_treatment(db):
    """Dulu upsell PRODUK memaksa ON_TREATMENT tanpa tindakan aktif — tak ada penulis lain
    yang memajukannya, kunjungan tersangkut di ruang tindakan dan produknya tak tertagih."""
    staf, k = _siapkan(db, "ANTRI_BAYAR")
    _soap(db, k, staf)
    hasil = _upsell_produk(db, k, staf)
    db.refresh(k)
    assert V(k.status_antrian) == "ANTRI_BAYAR"
    assert hasil["data"]["status_kunjungan"] == "ANTRI_BAYAR"


def test_upsell_tindakan_ke_antrian_perawat(db):
    from tests.integration.test_audit_tahap2 import _upsell, _treatment_tanpa_otorisasi
    staf, k = _siapkan(db, "ANTRI_BAYAR")
    _soap(db, k, staf)
    _upsell(db, k, staf, _treatment_tanpa_otorisasi(db))
    db.refresh(k)
    assert V(k.status_antrian) == "ANTRI_TREATMENT"   # PENDING, belum dimulai


def test_void_satu_satunya_transaksi_hari_ini_tetap_completed(db):
    """Ruling 6: transaksi VOID = kasir sudah menangani; kunjungan tidak kembali ke kasir."""
    from tests.integration.test_audit_tahap2 import _resep, _void
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    r = _resep(db, k, staf)
    _bayar(db, k, staf)
    assert V(k.status_antrian) == "ANTRI_OBAT"
    _void(db, _trx_terakhir(db, k).id_transaksi, staf)
    db.refresh(r); db.refresh(k)
    assert V(r.status_item) == "BATAL"
    assert V(k.status_antrian) == "COMPLETED"


# Penulis `kunjungan.status_antrian` yang SAH di luar fungsi bersama. Daftar EKSPLISIT
# (berkas, fungsi): menambah penulis baru = menambah baris di sini DENGAN alasannya.
PENULIS_STATUS_SAH = {
    ("app/services/_status_kunjungan.py", "hitung_ulang_status"),   # satu-satunya penulis otomatis
    ("app/repositories/kunjungan_repo.py", "update_status"),        # alat tulisnya sendiri
    # Dropdown FO: transisi pra-SOAP & BATAL (Task 7). Helper BATAL-nya
    # (`_pagari_batal`, `_bereskan_batal`) tidak menulis status sendiri.
    ("app/services/kunjungan_service.py", "ubah_status"),
}
# Pembuat kunjungan BARU (`Kunjungan(status_antrian=...)`): status awal, belum ada isi untuk
# dihitung. Route `web/routes/pasien.py`, `web/routes/pendaftaran.py` dan check-in
# `booking_service` hanya mengisi `KunjunganLamaRequest.status_antrian` lalu lewat
# `kunjungan_lama` — jadi yang tercatat di sini konstruktornya.
PEMBUAT_KUNJUNGAN_SAH = {
    ("app/services/kunjungan_service.py", "kunjungan_lama"),        # daftar biasa / booking / series
    ("app/services/kunjungan_service.py", "beli_produk_lengkap"),   # kunjungan beli produk
    ("app/services/pasien_service.py", "register_pasien_baru"),     # pasien baru + kunjungan
    ("app/services/membership_service.py", "create_kunjungan_billing"),  # warisan pra-M2
    ("app/services/retur_pasien_service.py", "_buat_kunjungan_alergi"),  # kunjungan RETUR_PASIEN
}


def _penulis_status_di(path, rel):
    import ast
    pohon = ast.parse(path.read_text(encoding="utf-8"))
    tulis, buat = [], []

    def jalan(node, fungsi):
        for anak in ast.iter_child_nodes(node):
            f = anak.name if isinstance(anak, (ast.FunctionDef, ast.AsyncFunctionDef)) else fungsi
            if isinstance(anak, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                targets = anak.targets if isinstance(anak, ast.Assign) else [anak.target]
                if any(isinstance(t, ast.Attribute) and t.attr == "status_antrian" for t in targets):
                    tulis.append((rel, f, anak.lineno))
            if isinstance(anak, ast.Call):
                if (isinstance(anak.func, ast.Attribute) and anak.func.attr == "update_status"
                        # Opname/PO juga punya `update_status` — entitas lain.
                        and "kunjungan" in ast.unparse(anak.func.value).lower()):
                    tulis.append((rel, f, anak.lineno))
                if (isinstance(anak.func, ast.Name) and anak.func.id == "setattr"
                        and any(isinstance(a, ast.Constant) and a.value == "status_antrian"
                                for a in anak.args)):
                    tulis.append((rel, f, anak.lineno))
                if (isinstance(anak.func, ast.Name) and anak.func.id == "Kunjungan"
                        and any(kw.arg == "status_antrian" for kw in anak.keywords)):
                    buat.append((rel, f, anak.lineno))
            jalan(anak, f)

    jalan(pohon, None)
    return tulis, buat


def test_tidak_ada_penulis_status_liar():
    akar = pathlib.Path(__file__).parents[2]
    tulis, buat = [], []
    for path in sorted((akar / "app").rglob("*.py")):
        rel = path.relative_to(akar).as_posix()
        t, b = _penulis_status_di(path, rel)
        tulis += t
        buat += b
    liar = [t for t in tulis if (t[0], t[1]) not in PENULIS_STATUS_SAH]
    assert liar == [], f"Penulis status kunjungan di luar hitung_ulang_status: {liar}"
    pembuat_liar = [b for b in buat if (b[0], b[1]) not in PEMBUAT_KUNJUNGAN_SAH]
    assert pembuat_liar == [], f"Pembuat kunjungan baru yang belum terdaftar: {pembuat_liar}"
    # Pemindai benar-benar melihat sesuatu: kalau pola AST-nya rusak, daftar kosong dan
    # dua assert di atas lulus tanpa arti.
    assert {(t[0], t[1]) for t in tulis} == PENULIS_STATUS_SAH
    assert {(b[0], b[1]) for b in buat} == PEMBUAT_KUNJUNGAN_SAH


@pytest.mark.parametrize("awal,harapan", [("ANTRI_KONSULTASI", "ANTRI_KONSULTASI"),
                                          ("ANTRI_TREATMENT", "ANTRI_TREATMENT")])
def test_pakai_sesi_series_status_dari_isi(db, awal, harapan):
    """Ruling 8: kunjungan pra-SOAP TIDAK dipindah (dulu ANTRI_KONSULTASI → ANTRI_TREATMENT,
    pasien hilang dari antrian dokter); antrian perawat Task 5 membaca tindakan PENDING
    langsung. Jalur FO 'lanjut series' membuat kunjungan ANTRI_TREATMENT → tetap di sana."""
    from tests.integration.test_audit_tahap2 import _series, _kunjungan_baru
    from app.services.series_service import SeriesService
    staf, k = _siapkan(db)
    s2 = _series(db, staf, k)
    _bayar(db, k, staf)
    k2 = _kunjungan_baru(db, k, staf)
    k2.status_antrian = awal; db.flush()
    SeriesService(db).use_session(s2.id_rencana, k2.id_kunjungan, staf.id_staf)
    db.refresh(k2)
    assert V(k2.status_antrian) == harapan
