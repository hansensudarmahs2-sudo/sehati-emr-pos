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
    # Tanpa susulan: mode lihat-saja (sudah_lunas) hanya dipilih bila TIDAK ada item baru.
    t2 = KasirService(db).get_tagihan(k.id_kunjungan)
    assert t2.sudah_lunas is True
    assert [r.id_kunjungan_tindakan for r in t2.rincian_tindakan] == [t.id_kunjungan_tindakan]


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


# ---------------------------------------------------------------- T2-1 fix round 1 (Ruling P3)
# Race bayar vs Batalkan: bayar mengunci kunjungan; Batalkan dulu hanya mengunci baris
# tindakan. Tagihan sudah memuat T PENDING → perawat Batalkan (BATAL, kuota kembali, commit)
# → `mark_tindakan_dibayar` menautkan T yang sudah BATAL dan pasien membayarnya.
def test_batalkan_mengunci_kunjungan_sebelum_tindakan(db):
    from tests.integration.test_audit_tahap3 import _berkunci
    from tests.integration.test_audit_tahap4 import _rekam_dengan_commit
    from app.services.treatment_service import TreatmentService
    staf, k = _siapkan(db)
    t = _tindakan_baru(db, k, "PENDING")
    q = _rekam_dengan_commit(db, lambda: TreatmentService(db).batalkan_tindakan(
        t.id_kunjungan_tindakan, "pasien menolak", staf.id_staf))
    i_commit = q.index("<<COMMIT>>")
    i_kj = q.index(_berkunci(q, "kunjungan")[0])
    i_t = q.index(_berkunci(q, "kunjungan_tindakan")[0])
    assert i_commit < i_kj < i_t                      # dulu: kunjungan tak dikunci
    assert not [x for x in q[i_commit + 1:i_kj] if x.startswith("SELECT")]


def test_tindakan_dibatalkan_saat_bayar_ditolak_409(db, monkeypatch):
    """Pagar cadangan (P3a): tindakan di tagihan yang tak lagi bisa ditagih saat ditautkan
    → 409 + rollback sebelum commit apa pun; tak ada transaksi."""
    import pytest
    from fastapi import HTTPException
    from tests.integration.test_audit_tahap4 import _bayar_req
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    t = _tindakan_baru(db, k, "PENDING")
    svc = KasirService(db)
    req = _bayar_req(svc, k)
    asli = KasirService.get_tagihan
    kejadian = []

    def tagihan_lalu_dibatalkan(self, id_kunjungan, user_role=None):
        hasil = asli(self, id_kunjungan, user_role)
        t.status_tindakan = "BATAL"; db.flush()       # perawat Batalkan (commit) di sini
        kejadian.append("tagihan")
        return hasil
    monkeypatch.setattr(KasirService, "get_tagihan", tagihan_lalu_dibatalkan)
    commit_asli, rollback_asli = db.commit, db.rollback
    monkeypatch.setattr(db, "commit", lambda: (kejadian.append("commit"), commit_asli())[1])
    monkeypatch.setattr(db, "rollback", lambda: (kejadian.append("rollback"), rollback_asli())[1])
    id_k = k.id_kunjungan
    with pytest.raises(HTTPException) as e:
        svc.proses_bayar(req, staf.id_staf)
    assert e.value.status_code == 409 and e.value.detail == KasirService._PESAN_TAGIHAN_BERUBAH
    sesudah = kejadian[kejadian.index("tagihan"):]
    assert "rollback" in sesudah and "commit" not in sesudah[:sesudah.index("rollback")]
    from app.db.models import TransaksiKasir
    assert db.execute(select(TransaksiKasir).where(
        TransaksiKasir.id_kunjungan == id_k)).first() is None


def test_series_sesi_1_prabayar_ditagih_sekali(db):
    """MINOR 4: sesi 1 series PENDING dibayar di muka → harga paket (per sesi × N) ditagih
    sekali; susulan sesudah sesi itu selesai tidak menagihnya lagi."""
    from app.db.models import MasterTreatment, TransaksiDetailTindakan
    from app.services._series import jumlah_sesi
    from app.services.treatment_service import TreatmentService
    from tests.integration.test_audit_tahap2 import _rencana, _resep
    from decimal import Decimal
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    s1 = _rencana(db, k, 1, k.id_kunjungan, "SCHEDULED")
    _rencana(db, k, 2, k.id_kunjungan, "PENDING")
    _rencana(db, k, 3, k.id_kunjungan, "PENDING")
    t = KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=s1.id_treatment,
                          id_rencana=s1.id_rencana, status_tindakan="PENDING")
    db.add(t); db.flush()
    tr = db.get(MasterTreatment, s1.id_treatment)
    per_sesi = Decimal(str(tr.harga_paket if tr.harga_paket is not None else tr.harga))
    harapan = per_sesi * jumlah_sesi(db, s1)
    tagihan = KasirService(db).get_tagihan(k.id_kunjungan)
    assert [r.harga for r in tagihan.rincian_tindakan] == [harapan]
    _bayar(db, k, staf)
    svc = TreatmentService(db)
    svc.start_tindakan(t.id_kunjungan_tindakan, staf.id_staf)
    svc.end_tindakan(t.id_kunjungan_tindakan, staf.id_staf)
    _resep(db, k, staf)                                # susulan: obat saja
    susulan = KasirService(db).get_tagihan(k.id_kunjungan)
    assert susulan.sudah_lunas is False
    assert susulan.rincian_tindakan == []
    assert susulan.ringkasan_biaya.subtotal_tindakan == 0
    _bayar(db, k, staf)
    n = db.execute(select(TransaksiDetailTindakan).where(
        TransaksiDetailTindakan.id_kunjungan_tindakan == t.id_kunjungan_tindakan)).all()
    assert len(n) == 1
