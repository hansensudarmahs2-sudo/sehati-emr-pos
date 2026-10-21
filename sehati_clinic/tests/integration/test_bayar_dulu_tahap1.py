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
from tests.integration.test_audit_tahap2 import (V, _siapkan, _bayar, _resep, _tindakan_selesai,  # noqa: F401
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


# ---------------------------------------------------------------- T1-5
# Antrian perawat/apotek/kasir membaca ISI kunjungan (`kondisi_T/K/O`), bukan label
# `status_antrian`. Satu pasien boleh tampil di dua meja sekaligus (spec §3.3).
def _di_antrian(db, k):
    """Meja mana saja yang menampilkan kunjungan `k` hari ini."""
    from datetime import date
    from app.repositories.apotek_repo import ApotekRepository
    from app.repositories.kasir_repo import KasirRepository
    from app.repositories.treatment_repo import TreatmentRepository
    hari_ini = date.today()
    meja = set()
    if any(r[0].id_kunjungan == k.id_kunjungan
           for r in TreatmentRepository(db).list_antrian_ruang_tindakan(today=hari_ini)):
        meja.add("perawat")
    if any(r[0].id_kunjungan == k.id_kunjungan
           for r in ApotekRepository(db).list_antrian_obat(today=hari_ini)):
        meja.add("apotek")
    if any(r[0].id_kunjungan == k.id_kunjungan
           for r in KasirRepository(db).list_antrian_bayar(today=hari_ini)):
        meja.add("kasir")
    return meja


def _obat_lunas_lalu_tindakan(db, status_tindakan):
    """Resep DIBAYAR belum diserahkan, lalu dokter/perawat menambah tindakan."""
    from tests.integration.test_audit_tahap2 import _resep
    from app.services._status_kunjungan import hitung_ulang_status
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    r = _resep(db, k, staf)
    _bayar(db, k, staf)
    assert V(k.status_antrian) == "ANTRI_OBAT"
    t = _tindakan_baru(db, k, status_tindakan)
    hitung_ulang_status(db, k.id_kunjungan)
    db.refresh(k)
    return staf, k, r, t


def test_pasien_tampil_di_apotek_dan_perawat_bersamaan(db):
    """Review Focus 4: obat lunas + tindakan PENDING. Label = ANTRI_TREATMENT; dulu apotek
    hanya membaca ANTRI_OBAT sehingga obat yang sudah dibayar hilang dari layar apoteker."""
    _, k, _, _ = _obat_lunas_lalu_tindakan(db, "PENDING")
    assert V(k.status_antrian) == "ANTRI_TREATMENT"
    assert _di_antrian(db, k) == {"perawat", "apotek"}


def test_apotek_bisa_serah_saat_label_on_treatment(db):
    """Ruling 4: tindakan PROSES (label ON_TREATMENT). Dulu serah ditolak 400 karena
    status bukan ANTRI_OBAT. Sesudah serah label TETAP ON_TREATMENT — tindakan masih jalan."""
    from app.schemas.apotek import SerahkanObatRequest
    from app.services.apotek_service import ApotekService
    staf, k, r, _ = _obat_lunas_lalu_tindakan(db, "PROSES")
    assert V(k.status_antrian) == "ON_TREATMENT"
    hasil = ApotekService(db).serahkan_obat(SerahkanObatRequest(id_kunjungan=k.id_kunjungan),
                                            staf.id_staf)
    db.refresh(r); db.refresh(k)
    assert V(r.status_item) == "DISERAHKAN"
    assert V(k.status_antrian) == "ON_TREATMENT"
    assert hasil["data"]["status_kunjungan_baru"] == "ON_TREATMENT"
    assert _di_antrian(db, k) == {"perawat"}


def test_serah_tetap_ditolak_tanpa_obat_dibayar(db):
    """Pagar serah dilonggarkan ke ISI, bukan dihapus: kunjungan tanpa obat DIBAYAR dan
    bukan jalur obat tertunda tetap ditolak di pintu (pesan status, bukan pesan item)."""
    from fastapi import HTTPException
    from app.schemas.apotek import SerahkanObatRequest
    from app.services.apotek_service import ApotekService
    staf, k = _siapkan(db, "ON_TREATMENT")
    _soap(db, k, staf)
    _tindakan_baru(db, k, "PROSES")
    with pytest.raises(HTTPException) as e:
        ApotekService(db).serahkan_obat(SerahkanObatRequest(id_kunjungan=k.id_kunjungan),
                                        staf.id_staf)
    assert e.value.status_code == 400 and "ON_TREATMENT" in e.value.detail


def test_serah_ditolak_untuk_kunjungan_batal(db):
    from fastapi import HTTPException
    from app.schemas.apotek import SerahkanObatRequest
    from app.services.apotek_service import ApotekService
    staf, k = _siapkan(db, "BATAL")
    _isi(db, k, staf, soap=True, resep=["DIBAYAR"], bayar=True)
    with pytest.raises(HTTPException) as e:
        ApotekService(db).serahkan_obat(SerahkanObatRequest(id_kunjungan=k.id_kunjungan),
                                        staf.id_staf)
    assert e.value.status_code == 400 and "BATAL" in e.value.detail


def test_antrian_kasir_dari_item_belum_ditagih(db):
    """Tindakan A SELESAI belum ditagih + tindakan B masih PROSES: label ON_TREATMENT (dulu
    kasir hanya membaca ANTRI_BAYAR → A tak terlihat kasir). Sesudah bayar → hilang dari
    kasir, tetap di perawat."""
    staf, k = _siapkan(db, "ON_TREATMENT")
    _soap(db, k, staf)
    _tindakan_selesai(db, k, detik=-5)
    _tindakan_baru(db, k, "PROSES")
    assert _di_antrian(db, k) == {"perawat", "kasir"}
    _bayar(db, k, staf)
    assert V(k.status_antrian) == "ON_TREATMENT"
    assert _di_antrian(db, k) == {"perawat"}


def test_antrian_kasir_tindakan_selesai_sebelum_soap(db):
    """Temuan review T1-4: kunjungan KONSULTASI (belum ada SOAP) + tindakan upsell SELESAI
    belum ditagih. Label sengaja tidak disentuh (KONSULTASI), tapi (K) benar → kasir."""
    from app.services._status_kunjungan import hitung_ulang_status
    staf, k = _siapkan(db, "KONSULTASI")
    _tindakan_selesai(db, k, detik=-5)
    hitung_ulang_status(db, k.id_kunjungan)
    db.refresh(k)
    assert V(k.status_antrian) == "KONSULTASI"
    # Perawat juga: label KONSULTASI tetap di antrian perawat (Ruling 10).
    assert _di_antrian(db, k) == {"kasir", "perawat"}


def test_antrian_perawat_tetap_menampilkan_konsultasi_tanpa_tindakan(db):
    """Ruling 10: tautan Kerjakan di antrian perawat satu-satunya pintu ke form upsell —
    pasien yang sedang konsul (belum ada tindakan) harus tetap tampil."""
    staf, k = _siapkan(db, "KONSULTASI")
    assert _di_antrian(db, k) == {"perawat"}
    staf, k2 = _siapkan(db, "ANTRI_KONSULTASI")
    assert _di_antrian(db, k2) == set()          # belum dipanggil dokter (DEC-063)


def test_tunda_saat_label_on_treatment(db):
    """Ruling 9: obat lunas + tindakan PROSES (label ON_TREATMENT) tampil di apotek, jadi
    Tunda harus diterima. Dulu ditolak 400 ("tidak bisa ditunda")."""
    from datetime import date
    from app.services.apotek_service import ApotekService
    staf, k, r, _ = _obat_lunas_lalu_tindakan(db, "PROSES")
    assert V(k.status_antrian) == "ON_TREATMENT"
    janji = date.today() + timedelta(days=2)
    ApotekService(db).tunda_serah_obat(k.id_kunjungan, janji, "uji", staf.id_staf)
    db.refresh(k); db.refresh(r)
    assert k.tgl_janji_kirim == janji
    assert V(r.status_item) == "DIBAYAR"
    assert V(k.status_antrian) == "ON_TREATMENT"
    # Keluar dari antrian apotek (janji terisi). Masuk daftar Obat Tertunda walau label
    # ON_TREATMENT — dulu daftar itu hanya membaca COMPLETED sehingga komentar lama di sini
    # ("→ Obat Tertunda") tidak benar; sejak I3 (`kondisi_tertunda`) benar dan diuji.
    assert _di_antrian(db, k) == {"perawat"}
    assert k.id_kunjungan in [x["id_kunjungan"] for x in ApotekService(db).list_obat_tertunda()]


def test_tunda_ditolak_untuk_kunjungan_batal(db):
    from datetime import date
    from fastapi import HTTPException
    from app.services.apotek_service import ApotekService
    staf, k = _siapkan(db, "BATAL")
    _isi(db, k, staf, soap=True, resep=["DIBAYAR"], bayar=True)
    with pytest.raises(HTTPException) as e:
        ApotekService(db).tunda_serah_obat(k.id_kunjungan, date.today(), None, staf.id_staf)
    assert e.value.status_code == 400


def test_hitungan_tindakan_kasir_hanya_yang_bisa_ditagih(db):
    """Kolom jumlah tindakan di antrian kasir = tindakan SELESAI tanpa transaksi (arti K);
    dulu tagihan susulan ikut menghitung tindakan yang sudah lunas."""
    from datetime import date
    from app.repositories.kasir_repo import KasirRepository
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    _tindakan_selesai(db, k, detik=-5)
    _bayar(db, k, staf)
    _tindakan_selesai(db, k, detik=5)                # susulan
    baris = [r for r in KasirRepository(db).list_antrian_bayar(today=date.today())
             if r[0].id_kunjungan == k.id_kunjungan]
    assert len(baris) == 1 and baris[0][2] == 1


def test_antrian_perawat_tindakan_series_sebelum_konsultasi(db):
    """Ruling 8: sesi series di kunjungan ANTRI_KONSULTASI (label tidak dipindah) tetap
    sampai ke perawat karena antriannya membaca tindakan PENDING."""
    staf, k = _siapkan(db, "ANTRI_KONSULTASI")
    _tindakan_baru(db, k, "PENDING")
    assert _di_antrian(db, k) == {"perawat"}


def test_antrian_tetap_hanya_hari_ini_dan_tanpa_batal(db):
    isi = dict(soap=True, tindakan=["PENDING", "SELESAI"], resep=["DIBAYAR"], bayar=True)
    staf, kemarin = _siapkan(db, "ANTRI_TREATMENT")
    _isi(db, kemarin, staf, **isi)
    kemarin.tgl_kunjungan = datetime.now() - timedelta(days=1); db.flush()
    assert _di_antrian(db, kemarin) == set()
    staf, batal = _siapkan(db, "BATAL")
    _isi(db, batal, staf, **isi)
    assert _di_antrian(db, batal) == set()
    # Pembanding: isi yang sama, hari ini, tidak BATAL → tiga meja sekaligus.
    staf, hidup = _siapkan(db, "ANTRI_TREATMENT")
    _isi(db, hidup, staf, **isi)
    assert _di_antrian(db, hidup) == {"perawat", "apotek", "kasir"}


def test_apotek_tidak_menampilkan_obat_tertunda(db):
    """Obat DIBAYAR + tgl_janji_kirim: tetap di daftar Obat Tertunda, bukan antrian apotek."""
    staf, k = _siapkan(db, "COMPLETED")
    _isi(db, k, staf, soap=True, resep=["DIBAYAR"], bayar=True, janji=True)
    assert _di_antrian(db, k) == set()


def test_lencana_meja_sama_dengan_panjang_antrian(db):
    """Lencana menu (perawat/kasir/apotek) dihitung dari kondisi yang SAMA dengan daftar —
    dulu menghitung label, sehingga lencana dan layar bisa berselisih."""
    from datetime import date
    from app.repositories.apotek_repo import ApotekRepository
    from app.repositories.kasir_repo import KasirRepository
    from app.repositories.treatment_repo import TreatmentRepository
    from app.services._status_kunjungan import hitung_antrian_meja
    _obat_lunas_lalu_tindakan(db, "PENDING")
    staf, k = _siapkan(db, "ON_TREATMENT")
    _soap(db, k, staf)
    _tindakan_selesai(db, k, detik=-5)
    _tindakan_baru(db, k, "PROSES")
    _siapkan(db, "KONSULTASI")                       # Ruling 10: lencana ikut menghitungnya
    hari_ini = date.today()
    n = hitung_antrian_meja(db, hari_ini)
    assert n["ANTRI_TREATMENT"] == len(TreatmentRepository(db).list_antrian_ruang_tindakan(today=hari_ini))
    assert n["ANTRI_OBAT"] == len(ApotekRepository(db).list_antrian_obat(today=hari_ini))
    assert n["ANTRI_BAYAR"] == len(KasirRepository(db).list_antrian_bayar(today=hari_ini))
    assert n["ANTRI_TREATMENT"] >= 2 and n["ANTRI_OBAT"] >= 1 and n["ANTRI_BAYAR"] >= 1


# ---------------------------------------------------------------- T1-6
PESAN_SIDIK = ("Tagihan berubah sejak halaman dibuka — ada item baru dari dokter/perawat. "
               "Halaman dimuat ulang; periksa lalu bayar lagi.")


def _bayar_dgn_sidik(db, k, staf, sidik):
    import secrets
    from app.schemas.kasir import BayarRequest, PembayaranItem
    from app.services.kasir_service import KasirService
    svc = KasirService(db)
    total = svc.get_tagihan(k.id_kunjungan).ringkasan_biaya.total_tagihan
    pemb = [PembayaranItem(metode_bayar="TUNAI", nominal=total)] if total > 0 else []
    return svc.proses_bayar(BayarRequest(id_kunjungan=k.id_kunjungan, pembayaran=pemb,
                                         idempotency_key=secrets.token_hex(8),
                                         sidik=sidik), staf.id_staf)


def _jumlah_trx(db, k):
    from app.db.models import TransaksiKasir
    return len(db.execute(select(TransaksiKasir).where(
        TransaksiKasir.id_kunjungan == k.id_kunjungan)).scalars().all())


def test_sidik_beda_pembayaran_ditahan(db):
    """Review Focus 5: halaman dibuka -> dokter menambah resep -> Bayar ditahan (409),
    tidak ada transaksi. Tanpa ini kasir menagih himpunan yang tidak sama dengan yang dilihat."""
    from fastapi import HTTPException
    from app.services.kasir_service import KasirService
    staf, k = _siapkan(db)
    _resep(db, k, staf)
    sidik_lama = KasirService(db).sidik_tagihan(KasirService(db).get_tagihan(k.id_kunjungan))
    _resep(db, k, staf)                                  # item baru sesudah halaman dibuka
    with pytest.raises(HTTPException) as e:
        _bayar_dgn_sidik(db, k, staf, sidik_lama)
    assert e.value.status_code == 409 and e.value.detail == PESAN_SIDIK
    assert _jumlah_trx(db, k) == 0


def test_sidik_sama_lolos(db):
    from app.services.kasir_service import KasirService
    staf, k = _siapkan(db)
    _resep(db, k, staf)
    svc = KasirService(db)
    sidik = svc.sidik_tagihan(svc.get_tagihan(k.id_kunjungan))
    assert sidik.startswith("R:")
    _bayar_dgn_sidik(db, k, staf, sidik)
    assert _jumlah_trx(db, k) == 1


def test_tanpa_sidik_api_tetap_jalan(db):
    staf, k = _siapkan(db)
    _resep(db, k, staf)
    _bayar_dgn_sidik(db, k, staf, None)
    assert _jumlah_trx(db, k) == 1


def _login_testclient(c):
    import os, re
    hal = c.get("/web/login")
    data = {"username": os.environ["TEST_USERNAME"], "password": os.environ["TEST_PASSWORD"]}
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', hal.text)
    if m:
        data["csrf_token"] = m.group(1)
    c.post("/web/login", data=data)
    return data.get("csrf_token")


def test_halaman_tagihan_memuat_sidik(db):
    import os
    from fastapi.testclient import TestClient
    from app.core.deps import get_db
    from app.main import app
    if not (os.getenv("TEST_USERNAME") and os.getenv("TEST_PASSWORD")):
        pytest.skip("butuh TEST_USERNAME/TEST_PASSWORD")
    staf, k = _siapkan(db)
    _resep(db, k, staf)

    def _db():
        yield db
    app.dependency_overrides[get_db] = _db
    try:
        c = TestClient(app)
        _login_testclient(c)
        r = c.get(f"/web/kasir/tagihan/{k.id_kunjungan}")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert 'name="sidik"' in r.text and 'name="sidik" value="R:' in r.text


def test_rute_bayar_sidik_basi_dialihkan_tanpa_transaksi(db):
    import os
    from urllib.parse import quote
    from fastapi.testclient import TestClient
    from app.core.deps import get_db
    from app.main import app
    if not (os.getenv("TEST_USERNAME") and os.getenv("TEST_PASSWORD")):
        pytest.skip("butuh TEST_USERNAME/TEST_PASSWORD")
    staf, k = _siapkan(db)
    _resep(db, k, staf)
    total = float(__import__("app.services.kasir_service", fromlist=["x"]).KasirService(db)
                  .get_tagihan(k.id_kunjungan).ringkasan_biaya.total_tagihan)

    def _db():
        yield db
    app.dependency_overrides[get_db] = _db
    try:
        c = TestClient(app, follow_redirects=False)
        csrf = _login_testclient(c)
        form = {"metode_bayar": "TUNAI", "nominal": str(total), "idempotency_key": "uji-sidik-basi",
                "sidik": "R:1"}                          # sidik basi: bukan himpunan sebenarnya
        if csrf:
            form["csrf_token"] = csrf
        r = c.post(f"/web/kasir/tagihan/{k.id_kunjungan}/bayar", data=form)
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 303
    assert quote(PESAN_SIDIK) in r.headers["location"]
    assert r.headers["location"].startswith(f"/web/kasir/tagihan/{k.id_kunjungan}?err=")
    assert _jumlah_trx(db, k) == 0


# ---------------------------------------------------------------- T1-7
# Status kunjungan kini ringkasan yang dihitung (`_status_kunjungan.py`); FO tidak boleh
# memajukannya dengan tangan. DEC-015 (ON_TREATMENT → COMPLETED) ikut dihapus.
@pytest.mark.parametrize("asal,tujuan", [
    ("KONSULTASI", "ANTRI_BAYAR"),
    ("KONSULTASI", "ANTRI_TREATMENT"),
    ("KONSULTASI", "ANTRI_OBAT"),
    ("ANTRI_TREATMENT", "ON_TREATMENT"),
    ("ON_TREATMENT", "COMPLETED"),
    ("ON_TREATMENT", "ANTRI_BAYAR"),
    ("ANTRI_BAYAR", "ANTRI_OBAT"),
    ("ANTRI_OBAT", "COMPLETED"),
])
def test_fo_tidak_bisa_memajukan_status(db, asal, tujuan):
    from fastapi import HTTPException
    from app.services.kunjungan_service import KunjunganService
    staf, k = _siapkan(db, asal)
    with pytest.raises(HTTPException) as e:
        KunjunganService(db).ubah_status(k.id_kunjungan, tujuan, actor_id_staf=staf.id_staf)
    assert e.value.status_code == 400
    db.refresh(k)
    assert V(k.status_antrian) == asal


@pytest.mark.parametrize("asal", ["ANTRI_KONSULTASI", "KONSULTASI", "ANTRI_TREATMENT",
                                  "ON_TREATMENT", "ANTRI_BAYAR", "ANTRI_OBAT"])
def test_fo_tetap_bisa_batal(db, asal):
    from app.services.kunjungan_service import KunjunganService
    staf, k = _siapkan(db, asal)
    KunjunganService(db).ubah_status(k.id_kunjungan, "BATAL", actor_id_staf=staf.id_staf)
    db.refresh(k)
    assert V(k.status_antrian) == "BATAL"


def test_fo_tetap_bisa_mulai_konsultasi(db):
    from app.services.kunjungan_service import KunjunganService
    staf, k = _siapkan(db, "ANTRI_KONSULTASI")
    KunjunganService(db).ubah_status(k.id_kunjungan, "KONSULTASI", actor_id_staf=staf.id_staf)
    db.refresh(k)
    assert V(k.status_antrian) == "KONSULTASI"

# ---------------------------------------------------------------------------
# T1-8: pemeriksa cek_status_kunjungan — uji DUA ARAH (CLAUDE.md §5)
# ---------------------------------------------------------------------------

def test_pemeriksa_status_dua_arah(db):
    from datetime import date
    from scripts.cek_status_kunjungan import periksa
    from app.services._status_kunjungan import hitung_ulang_status
    staf, k = _siapkan(db, "ANTRI_BAYAR")
    _resep(db, k, staf)
    db.flush()
    # Arah 1: label konsisten dengan isi (lewat satu-satunya penghitung) ->
    # pemeriksa tidak melaporkan kunjungan ini.
    hitung_ulang_status(db, k.id_kunjungan)
    db.flush()
    assert k.id_kunjungan not in [s[0] for s in periksa(db, date.today())]
    # Arah 2: label salah disisipkan -> pemeriksa melaporkan persis kunjungan itu.
    benar = V(k.status_antrian)
    k.status_antrian = "COMPLETED" if benar != "COMPLETED" else "ANTRI_BAYAR"
    db.flush()
    sel = [s for s in periksa(db, date.today()) if s[0] == k.id_kunjungan]
    assert sel == [(k.id_kunjungan, V(k.status_antrian), benar)]


# ===========================================================================
# Gelombang perbaikan review akhir tahap 1 (2026-10-21): C1, I1–I6.
# ===========================================================================
from fastapi import HTTPException  # noqa: E402

ALASAN = "pasien menolak tindakan"


def _batalkan(db, t, staf, alasan=ALASAN):
    from app.services.treatment_service import TreatmentService
    return TreatmentService(db).batalkan_tindakan(t.id_kunjungan_tindakan, alasan, staf.id_staf)


def _kuota_pending(db, k):
    """Tindakan PENDING yang memakai kuota member (terpakai=1), persis bentuk SOAP."""
    from tests.integration.test_audit_tahap2 import _kuota_terpakai
    q = _kuota_terpakai(db, k)
    t = db.execute(select(KunjunganTindakan).where(
        KunjunganTindakan.id_kunjungan == k.id_kunjungan,
        KunjunganTindakan.id_kuota_member == q.id_kuota)).scalar_one()
    return q, t


def _serah(db, k, staf):
    from app.schemas.apotek import SerahkanObatRequest
    from app.services.apotek_service import ApotekService
    ApotekService(db).serahkan_obat(SerahkanObatRequest(id_kunjungan=k.id_kunjungan), staf.id_staf)


# ---------------------------------------------------------------- C1 (Ruling 12)
def test_batalkan_tindakan_pending_belum_dibayar(db):
    """Konsul (resep) dibayar & diserahkan, tindakan kuota ditolak pasien → BATAL, kuota
    kembali, kunjungan selesai dan tak lagi menghalangi tutup kasir."""
    from app.db.models import AuditLog
    from app.services.kasir_closing_service import KasirClosingService
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    _resep(db, k, staf)
    q, t = _kuota_pending(db, k)
    _bayar(db, k, staf)
    _serah(db, k, staf)
    db.refresh(k)
    assert V(k.status_antrian) == "ANTRI_TREATMENT"
    sebelum = KasirClosingService(db)._pending_antrian_hari_ini().get("ANTRI_TREATMENT", 0)
    hasil = _batalkan(db, t, staf)
    db.refresh(t); db.refresh(q); db.refresh(k)
    assert V(t.status_tindakan) == "BATAL"
    assert q.kuota_terpakai == 0
    assert V(k.status_antrian) == "COMPLETED"
    assert hasil["data"]["status_kunjungan_baru"] == "COMPLETED"
    sesudah = KasirClosingService(db)._pending_antrian_hari_ini().get("ANTRI_TREATMENT", 0)
    assert sesudah == sebelum - 1
    log = db.execute(select(AuditLog).where(AuditLog.aksi == "TINDAKAN_BATAL",
                                            AuditLog.id_target == t.id_kunjungan_tindakan)).scalar_one()
    assert ALASAN in str(log.data_baru)


def test_batalkan_tindakan_yang_sudah_dibayar_ditolak(db):
    staf, k = _siapkan(db, "ANTRI_TREATMENT")
    trx = _isi(db, k, staf, soap=True, bayar=True)
    t = _tindakan_baru(db, k, "PENDING")
    t.id_transaksi = trx.id_transaksi; db.flush()
    with pytest.raises(HTTPException) as e:
        _batalkan(db, t, staf)
    assert e.value.status_code == 400 and "sudah dibayar" in e.value.detail
    db.refresh(t)
    assert V(t.status_tindakan) == "PENDING"


@pytest.mark.parametrize("st", ["PROSES", "SELESAI"])
def test_batalkan_tindakan_yang_sudah_dikerjakan_ditolak(db, st):
    staf, k = _siapkan(db, "ON_TREATMENT")
    _soap(db, k, staf)
    t = _tindakan_baru(db, k, st)
    with pytest.raises(HTTPException) as e:
        _batalkan(db, t, staf)
    assert e.value.status_code == 400 and "sudah dikerjakan" in e.value.detail
    db.refresh(t)
    assert V(t.status_tindakan) == st


@pytest.mark.parametrize("alasan", ["", "   ", "abc "])
def test_batalkan_tindakan_tanpa_alasan_ditolak(db, alasan):
    staf, k = _siapkan(db, "ANTRI_TREATMENT")
    _soap(db, k, staf)
    t = _tindakan_baru(db, k, "PENDING")
    with pytest.raises(HTTPException) as e:
        _batalkan(db, t, staf, alasan)
    assert e.value.status_code == 400 and "Alasan" in e.value.detail
    db.refresh(t)
    assert V(t.status_tindakan) == "PENDING"


def test_batalkan_sesi_series_yang_dijadwalkan_kembali_pending(db):
    """Sesi 2 series lain dipakai di kunjungan ini lalu dibatalkan → sesi itu PENDING lagi
    (bisa dipakai di kunjungan lain); series itu sendiri TIDAK dibatalkan."""
    from tests.integration.test_audit_tahap2 import _rencana
    staf, k = _siapkan(db, "ANTRI_TREATMENT")
    _, lama = _siapkan(db, "COMPLETED")
    s1 = _rencana(db, k, 1, lama.id_kunjungan, "DONE")
    s2 = _rencana(db, k, 2, lama.id_kunjungan, "SCHEDULED")
    s3 = _rencana(db, k, 3, lama.id_kunjungan, "PENDING")
    t = KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=s2.id_treatment,
                          id_rencana=s2.id_rencana, status_tindakan="PENDING")
    db.add(t); db.flush()
    _batalkan(db, t, staf)
    for r in (s1, s2, s3):
        db.refresh(r)
    assert (V(s1.status), V(s2.status), V(s3.status)) == ("DONE", "PENDING", "PENDING")


def test_batalkan_sesi_1_series_lahir_di_sini_membatalkan_seriesnya(db):
    """Sesi 1 pembawa harga paket belum dibayar → sisa sesi tak boleh tertinggal untuk dipakai
    gratis (aturan T2-6 `_bereskan_batal`). Series LAIN yang lahir di kunjungan yang sama
    tidak ikut (anggota series lewat `_series.anggota`)."""
    from tests.integration.test_audit_tahap2 import _rencana
    staf, k = _siapkan(db, "ANTRI_TREATMENT")
    s1 = _rencana(db, k, 1, k.id_kunjungan, "SCHEDULED")
    s2 = _rencana(db, k, 2, k.id_kunjungan, "PENDING")
    lain1 = _rencana(db, k, 1, k.id_kunjungan, "SCHEDULED")      # series kedua, treatment sama
    lain2 = _rencana(db, k, 2, k.id_kunjungan, "PENDING")
    t = KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=s1.id_treatment,
                          id_rencana=s1.id_rencana, status_tindakan="PENDING")
    db.add(t); db.flush()
    _batalkan(db, t, staf)
    for r in (s1, s2, lain1, lain2):
        db.refresh(r)
    assert [V(r.status) for r in (s1, s2)] == ["CANCELLED", "CANCELLED"]
    assert [V(r.status) for r in (lain1, lain2)] == ["SCHEDULED", "PENDING"]


def test_batal_kunjungan_sesudah_batalkan_tindakan_tidak_mengembalikan_kuota_dua_kali(db):
    """`_bereskan_batal` dan `batalkan_tindakan` memakai satu helper; tindakan yang sudah
    BATAL tidak dikembalikan kuotanya lagi saat kunjungannya dibatalkan."""
    from tests.integration.test_audit_tahap2 import _batal
    staf, k = _siapkan(db, "ANTRI_TREATMENT")
    q, t = _kuota_pending(db, k)
    q.kuota_terpakai = 2; db.flush()                 # satu slot lagi milik kunjungan lain
    _batalkan(db, t, staf)
    db.refresh(q)
    assert q.kuota_terpakai == 1
    _batal(db, k, staf)
    db.refresh(q)
    assert q.kuota_terpakai == 1


def _klien_login(db):
    import os
    from fastapi.testclient import TestClient
    from app.core.deps import get_db
    from app.main import app
    if not (os.getenv("TEST_USERNAME") and os.getenv("TEST_PASSWORD")):
        pytest.skip("butuh TEST_USERNAME/TEST_PASSWORD")

    def _db():
        yield db
    app.dependency_overrides[get_db] = _db
    c = TestClient(app, follow_redirects=False)
    csrf = _login_testclient(c)
    return app, c, csrf


def test_layar_perawat_menampilkan_tombol_batalkan(db):
    from app.core.deps import get_db
    staf, k = _siapkan(db, "ANTRI_TREATMENT")
    trx = _isi(db, k, staf, soap=True, bayar=True)
    t = _tindakan_baru(db, k, "PENDING")
    lunas = _tindakan_baru(db, k, "PENDING")
    lunas.id_transaksi = trx.id_transaksi; db.flush()
    app, c, _csrf = _klien_login(db)
    try:
        r = c.get(f"/web/ruang-tindakan/kunjungan/{k.id_kunjungan}")
    finally:
        app.dependency_overrides.pop(get_db, None)
    if r.status_code == 403:
        pytest.skip("akun uji tidak berhak membuka ruang tindakan")
    assert r.status_code == 200
    assert f'action="/web/ruang-tindakan/tindakan/{t.id_kunjungan_tindakan}/batalkan"' in r.text
    assert f'/tindakan/{lunas.id_kunjungan_tindakan}/batalkan"' not in r.text
    assert 'name="alasan"' in r.text


def test_rute_batalkan_tindakan(db):
    from app.core.deps import get_db
    staf, k = _siapkan(db, "ANTRI_TREATMENT")
    _soap(db, k, staf)
    t = _tindakan_baru(db, k, "PENDING")
    app, c, csrf = _klien_login(db)
    try:
        form = {"alasan": "x"}                       # terlalu pendek → kembali dengan err
        if csrf:
            form["csrf_token"] = csrf
        r1 = c.post(f"/web/ruang-tindakan/tindakan/{t.id_kunjungan_tindakan}/batalkan", data=form)
        form["alasan"] = ALASAN
        r2 = c.post(f"/web/ruang-tindakan/tindakan/{t.id_kunjungan_tindakan}/batalkan", data=form)
    finally:
        app.dependency_overrides.pop(get_db, None)
    if r1.status_code == 403:
        pytest.skip("akun uji tidak berhak")
    assert r1.status_code == 303
    assert r1.headers["location"].startswith(f"/web/ruang-tindakan/kunjungan/{k.id_kunjungan}?err=")
    assert r2.status_code == 303
    assert r2.headers["location"].startswith(f"/web/ruang-tindakan/kunjungan/{k.id_kunjungan}?ok=")
    db.refresh(t)
    assert V(t.status_tindakan) == "BATAL"


# ---------------------------------------------------------------- I1 (Ruling 13)
def _void_jalur(db, trx, staf, jalur):
    from app.db.models._enums import StafRoleEnum
    from app.services.kasir_service import KasirService
    if jalur == "void":
        KasirService(db).void_transaksi(trx.id_transaksi, "SALAH_INPUT", "uji ruling 13", [], staf.id_staf)
    else:
        KasirService(db).force_past_day_void(trx.id_transaksi, "SALAH_INPUT", "uji ruling 13", [],
                                             staf.id_staf, StafRoleEnum.SUPERADMIN)


@pytest.mark.parametrize("jalur", ["void", "force"])
def test_void_tidak_menyentuh_kuota_tindakan_yang_belum_ditagih(db, jalur):
    """Konsul+obat dibayar, tindakan kuota masih PENDING (belum ditagih). Void transaksi itu
    dulu (TUNGGAL = semua tindakan kunjungan) mengembalikan kuota tindakan yang tidak pernah
    ditagihnya — lalu Batalkan mengembalikannya LAGI."""
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    _resep(db, k, staf)
    q, t = _kuota_pending(db, k)
    _bayar(db, k, staf)
    _void_jalur(db, _trx_terakhir(db, k), staf, jalur)
    db.refresh(q); db.refresh(t); db.refresh(k)
    assert q.kuota_terpakai == 1
    assert V(t.status_tindakan) == "PENDING"
    assert V(k.status_antrian) == "ANTRI_TREATMENT"
    _batalkan(db, t, staf)
    db.refresh(q)
    assert q.kuota_terpakai == 0


@pytest.mark.parametrize("jalur", ["void", "force"])
def test_tindakan_susulan_belum_ditagih_tidak_menghalangi_void(db, jalur):
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    r = _resep(db, k, staf)
    _bayar(db, k, staf)
    _tindakan_selesai(db, k, detik=5)                # susulan SELESAI, belum ditagih
    _void_jalur(db, _trx_terakhir(db, k), staf, jalur)   # dulu 400 "tindakan SUDAH SELESAI"
    db.refresh(r); db.refresh(k)
    assert V(r.status_item) == "BATAL"
    assert V(k.status_antrian) == "ANTRI_BAYAR"      # susulan tetap harus ditagih


def test_void_tetap_menolak_tindakan_selesai_yang_ditagihnya(db):
    """Pembanding: pagar §7 untuk tindakan yang DITAGIH transaksi ini tetap utuh."""
    staf, k = _siapkan(db)
    _tindakan_selesai(db, k, detik=-5)
    _bayar(db, k, staf)
    with pytest.raises(HTTPException) as e:
        _void_jalur(db, _trx_terakhir(db, k), staf, "void")
    assert e.value.status_code == 400 and "SUDAH" in e.value.detail


def test_void_tidak_membatalkan_series_yang_sesi_1_nya_belum_ditagih(db):
    """Series lahir di kunjungan ini, sesi 1 masih PENDING (belum ditagih). Void transaksi
    konsul dulu membatalkan seriesnya (TUNGGAL = semua series kunjungan) — padahal harga
    paketnya baru ditagih bersama sesi 1 nanti."""
    from tests.integration.test_audit_tahap2 import _rencana
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    _resep(db, k, staf)
    s1 = _rencana(db, k, 1, k.id_kunjungan, "SCHEDULED")
    s2 = _rencana(db, k, 2, k.id_kunjungan, "PENDING")
    db.add(KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=s1.id_treatment,
                             id_rencana=s1.id_rencana, status_tindakan="PENDING"))
    db.flush()
    _bayar(db, k, staf)
    _void_jalur(db, _trx_terakhir(db, k), staf, "void")
    db.refresh(s1); db.refresh(s2)
    assert (V(s1.status), V(s2.status)) == ("SCHEDULED", "PENDING")


def test_lingkup_void_tindakan_dari_id_transaksi_dengan_cadangan_snapshot(db):
    """Lingkup tindakan = `id_transaksi`; baris lama tanpa penanda memakai snapshot F3."""
    from app.services.kasir_service import KasirService
    staf, k = _siapkan(db)
    _tindakan_selesai(db, k, detik=-5)
    _bayar(db, k, staf)
    trx = _trx_terakhir(db, k)
    t = db.execute(select(KunjunganTindakan).where(
        KunjunganTindakan.id_kunjungan == k.id_kunjungan)).scalar_one()
    belum = _tindakan_baru(db, k, "PENDING")
    svc = KasirService(db)
    assert svc._lingkup_void(trx)["tindakan"] == {t.id_kunjungan_tindakan}
    t.id_transaksi = None; db.flush()                # data lama: hanya snapshot
    assert svc._lingkup_void(trx)["tindakan"] == {t.id_kunjungan_tindakan}
    assert belum.id_kunjungan_tindakan not in svc._lingkup_void(trx)["tindakan"]


# ---------------------------------------------------------------- I2
def _urutan_commit_lalu_kunci(db, panggil):
    import re
    from tests.integration.test_audit_tahap3 import _rekam_sql
    with _rekam_sql(db) as q:
        _flush = db.commit
        db.commit = lambda: (q.append("<<COMMIT>>"), _flush())[1]
        try:
            panggil()
        finally:
            db.commit = _flush
    pola = re.compile(r"FROM kunjungan(?![A-Za-z0-9_])")
    i_kunci = next((i for i, x in enumerate(q) if x.startswith("SELECT") and pola.search(x)
                    and "FOR UPDATE" in x), None)
    assert i_kunci is not None, "kunjungan tidak dikunci"
    i_commit = q.index("<<COMMIT>>")
    assert i_commit < i_kunci                        # potret ditutup SEBELUM kunci
    assert not [x for x in q[i_commit + 1:i_kunci] if x.startswith("SELECT")]


def test_serah_mengakhiri_potret_sebelum_mengunci_kunjungan(db):
    from app.schemas.apotek import SerahkanObatRequest
    from app.services.apotek_service import ApotekService
    staf, k = _siapkan(db)
    _resep(db, k, staf)
    _bayar(db, k, staf)
    svc = ApotekService(db)
    _urutan_commit_lalu_kunci(db, lambda: svc.serahkan_obat(
        SerahkanObatRequest(id_kunjungan=k.id_kunjungan), staf.id_staf))


def test_tunda_mengunci_kunjungan_dengan_potret_segar(db):
    from datetime import date
    from app.services.apotek_service import ApotekService
    staf, k = _siapkan(db)
    _resep(db, k, staf)
    _bayar(db, k, staf)
    svc = ApotekService(db)
    _urutan_commit_lalu_kunci(db, lambda: svc.tunda_serah_obat(
        k.id_kunjungan, date.today() + timedelta(days=1), None, staf.id_staf))


# ---------------------------------------------------------------- I3
def test_obat_tertunda_saat_tindakan_berjalan_tampil_dan_bisa_diserahkan(db):
    """Tunda saat tindakan PROSES (label ON_TREATMENT): dulu daftar & lencana Obat Tertunda
    hanya membaca COMPLETED, jadi obatnya hilang dari semua layar sampai tindakan selesai,
    dan pintu serah menolaknya."""
    from datetime import date
    from app.services._status_kunjungan import ringkas_obat_tertunda
    from app.services.apotek_service import ApotekService
    staf, k, r, _ = _obat_lunas_lalu_tindakan(db, "PROSES")
    sebelum = ringkas_obat_tertunda(db)["total"]
    ApotekService(db).tunda_serah_obat(k.id_kunjungan, date.today() + timedelta(days=2),
                                       "uji", staf.id_staf)
    db.refresh(k)
    assert V(k.status_antrian) == "ON_TREATMENT"
    assert k.id_kunjungan in [x["id_kunjungan"] for x in ApotekService(db).list_obat_tertunda()]
    assert ringkas_obat_tertunda(db)["total"] == sebelum + 1
    _serah(db, k, staf)
    db.refresh(r); db.refresh(k)
    assert V(r.status_item) == "DISERAHKAN"
    assert k.tgl_janji_kirim is None
    assert k.id_kunjungan not in [x["id_kunjungan"] for x in ApotekService(db).list_obat_tertunda()]


def test_obat_tertunda_tanpa_item_dibayar_tidak_dihitung(db):
    """Janji kirim tersisa tanpa obat DIBAYAR (mis. semuanya sudah di-refund) bukan tertunda."""
    from app.services._status_kunjungan import ringkas_obat_tertunda
    from app.services.apotek_service import ApotekService
    staf, k = _siapkan(db, "COMPLETED")
    _isi(db, k, staf, soap=True, resep=["BATAL"], bayar=True, janji=True)
    assert k.id_kunjungan not in [x["id_kunjungan"] for x in ApotekService(db).list_obat_tertunda()]
    _, k2 = _siapkan(db, "COMPLETED")
    sebelum = ringkas_obat_tertunda(db)["total"]
    _isi(db, k2, staf, soap=True, resep=["DIBAYAR"], bayar=True, janji=True)
    assert ringkas_obat_tertunda(db)["total"] == sebelum + 1


def test_lencana_obat_tertunda_memakai_satu_ekspresi():
    """Daftar, dua lencana, dan pintu serah membaca `kondisi_tertunda` — bukan salinan
    `status_antrian == "COMPLETED"` sendiri-sendiri."""
    akar = pathlib.Path(__file__).parents[2]
    for rel in ("app/web/routes/auth.py", "app/web/routes/_shared.py"):
        src = (akar / rel).read_text(encoding="utf-8")
        assert "ringkas_obat_tertunda" in src, rel
        assert "tgl_janji_kirim.is_not(None)" not in src, rel
    src = (akar / "app/services/apotek_service.py").read_text(encoding="utf-8")
    assert src.count("kondisi_tertunda") >= 1 and src.count("obat_tertunda_di(") >= 1
    assert '_K.status_antrian == "COMPLETED"' not in src


# ---------------------------------------------------------------- I4
def test_kunjungan_retur_pasien_tidak_di_meja_kasir(db):
    """Kunjungan RETUR_PASIEN (wadah draf SOAP alergi) COMPLETED + SOAP FINAL, tanpa
    transaksi: (K) benar, tapi ia bukan kunjungan klinis — tak boleh muncul di kasir."""
    from datetime import date
    from app.services._status_kunjungan import hitung_antrian_meja
    from app.services._jenis_kunjungan import JENIS_RETUR
    staf, k = _siapkan(db, "COMPLETED")
    _soap(db, k, staf)
    assert "kasir" in _di_antrian(db, k)             # pembanding: kunjungan klinis biasa
    n = hitung_antrian_meja(db, date.today())["ANTRI_BAYAR"]
    k.jenis_kunjungan = JENIS_RETUR; db.flush()
    assert _di_antrian(db, k) == set()
    assert hitung_antrian_meja(db, date.today())["ANTRI_BAYAR"] == n - 1


# ---------------------------------------------------------------- I5
def test_precheck_migrasi_menemukan_tindakan_yang_akan_tetap_null(db):
    """Pemeriksaan SEBELUM DDL: tindakan SELESAI di kunjungan lunas yang tak punya snapshot dan
    selesai SESUDAH semua pembayaran — tak bisa dipasangkan, upgrade akan berhenti."""
    mig = _muat_migrasi()
    t_ok, _trx = _tindakan_lunas(db, snapshot=False)         # pra-F3, terpasangkan (cutoff)
    staf, k = _siapkan(db)
    _resep(db, k, staf)
    _bayar(db, k, staf)
    _tindakan_selesai(db, k, detik=60)                        # selesai sesudah bayar
    yatim = db.execute(select(KunjunganTindakan).where(
        KunjunganTindakan.id_kunjungan == k.id_kunjungan)).scalar_one()
    ids = mig.tindakan_tak_terpasangkan(db.connection())
    assert yatim.id_kunjungan_tindakan in ids
    assert t_ok.id_kunjungan_tindakan not in ids


def test_precheck_sql_berkas_sama_dengan_migrasi():
    """deploy/precheck_20261021_0100.sql = SELECT yang SAMA dengan pagar migrasi (satu sumber)."""
    mig = _muat_migrasi()
    akar = pathlib.Path(__file__).parents[2]
    berkas = (akar / "deploy/precheck_20261021_0100.sql").read_text(encoding="utf-8")
    isi = " ".join(b for b in berkas.splitlines() if not b.strip().startswith("--"))
    norm = lambda s: " ".join(s.replace(";", " ").split())  # noqa: E731
    assert norm(mig._SQL_PRECHECK.format(sel="kt.id_kunjungan_tindakan")) in norm(isi)
    kata = norm(isi).upper().split()
    assert not any(w in kata for w in ("UPDATE", "DELETE", "INSERT", "ALTER", "DROP"))


# ---------------------------------------------------------------- I6
def test_antrian_kasir_menandai_tindakan_belum_selesai(db):
    from datetime import date
    from app.repositories.kasir_repo import KasirRepository
    staf, k = _siapkan(db, "ON_TREATMENT")
    _soap(db, k, staf)
    _tindakan_selesai(db, k, detik=-5)
    _tindakan_baru(db, k, "PROSES")
    _, k2 = _siapkan(db, "ANTRI_BAYAR")
    _soap(db, k2, staf)
    _tindakan_selesai(db, k2, detik=-5)
    baris = {r[0].id_kunjungan: r for r in KasirRepository(db).list_antrian_bayar(today=date.today())}
    assert baris[k.id_kunjungan][4] is True
    assert baris[k2.id_kunjungan][4] is False
