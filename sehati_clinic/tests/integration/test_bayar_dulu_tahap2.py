"""Bayar dulu tahap 2 (2026-10-21) — Project_Memory/RENCANA_BAYAR_DULU_TAHAP2.md.

T2-1: kasir boleh menagih tindakan yang BELUM dikerjakan (prabayar). "Tindakan bisa
ditagih" = bukan BATAL dan `id_transaksi IS NULL` — satu definisi di
`app/services/_status_kunjungan.py` (`tindakan_bisa_ditagih`), dipakai (K) dan tagihan.
"""
from sqlalchemy import select

from app.db.models import KunjunganTindakan
from app.services.kasir_service import KasirService
from tests.integration.test_audit_tahap2 import (V, _siapkan, _bayar, _tindakan_selesai,  # noqa: F401
                                                 _trx_terakhir, db)
from tests.integration.test_bayar_dulu_tahap1 import _soap, _tindakan_baru


# ---------------------------------------------------------------- T2-1
def test_bayar_menagih_tindakan_pending(db):
    """SOAP + tindakan PENDING: tagihan memuatnya (status PENDING), bayar menautkannya,
    pasien tetap di jalur perawat; selesai dikerjakan → COMPLETED tanpa tagihan susulan."""
    from app.services.treatment_service import TreatmentService
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    t = _tindakan_baru(db, k, "PENDING")
    tagihan = KasirService(db).get_tagihan(k.id_kunjungan)
    baris = [r for r in tagihan.rincian_tindakan if r.id_kunjungan_tindakan == t.id_kunjungan_tindakan]
    assert len(baris) == 1 and baris[0].status_tindakan == "PENDING"
    assert tagihan.ringkasan_biaya.subtotal_tindakan > 0
    _bayar(db, k, staf)
    db.refresh(t)
    assert t.id_transaksi == _trx_terakhir(db, k).id_transaksi
    assert V(k.status_antrian) == "ANTRI_TREATMENT"   # masih harus dikerjakan
    svc = TreatmentService(db)
    svc.start_tindakan(t.id_kunjungan_tindakan, staf.id_staf)
    svc.end_tindakan(t.id_kunjungan_tindakan, staf.id_staf)
    db.refresh(k)
    assert V(k.status_antrian) == "COMPLETED"          # tahap 1: ANTRI_BAYAR (susulan)
    trx_lama = _trx_terakhir(db, k).id_transaksi
    assert KasirService(db).get_tagihan(k.id_kunjungan).sudah_lunas is True
    assert _trx_terakhir(db, k).id_transaksi == trx_lama


def test_tindakan_proses_ikut_ditagih(db):
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    t = _tindakan_baru(db, k, "PROSES")
    tagihan = KasirService(db).get_tagihan(k.id_kunjungan)
    assert [(r.id_kunjungan_tindakan, r.status_tindakan) for r in tagihan.rincian_tindakan] \
        == [(t.id_kunjungan_tindakan, "PROSES")]


def test_tindakan_batal_tidak_ditagih(db):
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    batal = _tindakan_baru(db, k, "BATAL")
    hidup = _tindakan_baru(db, k, "PENDING")
    tagihan = KasirService(db).get_tagihan(k.id_kunjungan)
    ids = [r.id_kunjungan_tindakan for r in tagihan.rincian_tindakan]
    assert ids == [hidup.id_kunjungan_tindakan]
    _bayar(db, k, staf)
    db.refresh(batal)
    assert batal.id_transaksi is None


def test_kondisi_K_tindakan_pending_belum_ditagih(db):
    """(K) benar karena tindakan PENDING belum ditagih (bukan hanya karena SOAP tanpa
    transaksi): kunjungan yang sudah pernah dibayar lalu mendapat tindakan PENDING baru
    kembali ke antrian kasir."""
    from app.services import _status_kunjungan as sk
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    _bayar(db, k, staf)                       # konsul saja
    assert sk.ringkasan(db, k.id_kunjungan)["K"] is False
    _tindakan_baru(db, k, "PENDING")
    assert sk.ringkasan(db, k.id_kunjungan)["K"] is True
    _tindakan_baru(db, k, "BATAL")
    _bayar(db, k, staf)
    assert sk.ringkasan(db, k.id_kunjungan)["K"] is False   # BATAL tidak menahan (K)


def test_view_only_menampilkan_tindakan_yang_dibayar(db):
    """Mode lunas memuat tindakan ber-`id_transaksi`, apa pun statusnya (PENDING/SELESAI),
    dengan status masing-masing; BATAL tidak tampil."""
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    _tindakan_selesai(db, k, detik=-5)
    p = _tindakan_baru(db, k, "PENDING")
    batal = _tindakan_baru(db, k, "BATAL")
    _bayar(db, k, staf)
    tagihan = KasirService(db).get_tagihan(k.id_kunjungan)
    assert tagihan.sudah_lunas is True
    status = {r.id_kunjungan_tindakan: r.status_tindakan for r in tagihan.rincian_tindakan}
    assert status[p.id_kunjungan_tindakan] == "PENDING"
    assert sorted(status.values()) == ["PENDING", "SELESAI"]
    assert batal.id_kunjungan_tindakan not in status
    semua = db.execute(select(KunjunganTindakan).where(
        KunjunganTindakan.id_kunjungan == k.id_kunjungan,
        KunjunganTindakan.status_tindakan != "BATAL")).scalars().all()
    assert all(t.id_transaksi is not None for t in semua)


def test_satu_definisi_bisa_ditagih():
    """`kondisi_K` dan repo tagihan memakai ekspresi yang sama (Global Constraints)."""
    import inspect
    from app.repositories import kasir_repo
    from app.services import _status_kunjungan as sk
    assert "tindakan_bisa_ditagih()" in inspect.getsource(sk.kondisi_K)
    src = inspect.getsource(kasir_repo.KasirRepository.get_tindakan_untuk_tagihan)
    assert "tindakan_bisa_ditagih()" in src and "== \"SELESAI\"" not in src
