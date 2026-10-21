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
    _bayar(db, k, staf, konfirmasi_prabayar=True)
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
    _bayar(db, k, staf, konfirmasi_prabayar=True)
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
    _bayar(db, k, staf, konfirmasi_prabayar=True)
    assert sk.ringkasan(db, k.id_kunjungan)["K"] is False   # BATAL tidak menahan (K)


def test_view_only_menampilkan_tindakan_yang_dibayar(db):
    """Mode lunas memuat tindakan ber-`id_transaksi`, apa pun statusnya (PENDING/SELESAI),
    dengan status masing-masing; BATAL tidak tampil."""
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    _tindakan_selesai(db, k, detik=-5)
    p = _tindakan_baru(db, k, "PENDING")
    batal = _tindakan_baru(db, k, "BATAL")
    _bayar(db, k, staf, konfirmasi_prabayar=True)
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
    req.konfirmasi_prabayar = True                    # T2-2: tagihan memuat tindakan PENDING
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
    _bayar(db, k, staf, konfirmasi_prabayar=True)
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


# ---------------------------------------------------------------- T2-2 konfirmasi dibayar di muka
_PESAN_PRABAYAR = ("Ada tindakan yang belum dikerjakan di tagihan ini. Centang konfirmasi "
                   "'dibayar di muka' untuk melanjutkan.")


def _req(svc, k, **kw):
    import secrets
    from app.schemas.kasir import BayarRequest, PembayaranItem
    total = svc.get_tagihan(k.id_kunjungan).ringkasan_biaya.total_tagihan
    pemb = [PembayaranItem(metode_bayar="TUNAI", nominal=total)] if total > 0 else []
    return BayarRequest(id_kunjungan=k.id_kunjungan, pembayaran=pemb,
                        idempotency_key=secrets.token_hex(8), **kw)


def test_bayar_prabayar_ditolak_tanpa_konfirmasi(db):
    import pytest
    from fastapi import HTTPException
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    _tindakan_baru(db, k, "PENDING")
    svc = KasirService(db)
    with pytest.raises(HTTPException) as e:
        svc.proses_bayar(_req(svc, k), staf.id_staf)           # API v1: field tak dikirim
    assert e.value.status_code == 400 and e.value.detail == _PESAN_PRABAYAR
    assert _trx_terakhir(db, k) is None                         # tak ada tulisan sama sekali


def test_bayar_prabayar_diterima_dengan_konfirmasi(db):
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    t = _tindakan_baru(db, k, "PROSES")
    svc = KasirService(db)
    svc.proses_bayar(_req(svc, k, konfirmasi_prabayar=True), staf.id_staf)
    db.refresh(t)
    assert t.id_transaksi == _trx_terakhir(db, k).id_transaksi


def test_bayar_tanpa_prabayar_tidak_butuh_konfirmasi(db):
    """Hanya tindakan SELESAI (atau tanpa tindakan): perilaku lama, tanpa konfirmasi."""
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    _tindakan_selesai(db, k)
    svc = KasirService(db)
    svc.proses_bayar(_req(svc, k), staf.id_staf)
    assert _trx_terakhir(db, k) is not None


def _masuk(c):
    import os, re
    hal = c.get("/web/login")
    data = {"username": os.environ["TEST_USERNAME"], "password": os.environ["TEST_PASSWORD"]}
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', hal.text)
    if m:
        data["csrf_token"] = m.group(1)
    c.post("/web/login", data=data)


def _klien(db):
    import os
    import pytest
    from fastapi.testclient import TestClient
    from app.core.deps import get_db
    from app.main import app
    if not (os.getenv("TEST_USERNAME") and os.getenv("TEST_PASSWORD")):
        pytest.skip("butuh TEST_USERNAME/TEST_PASSWORD")

    def _db():
        yield db
    app.dependency_overrides[get_db] = _db
    return TestClient(app, follow_redirects=False), app, get_db


def test_layar_kasir_memuat_kotak_dan_centang_di_kedua_form(db):
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    _tindakan_baru(db, k, "PENDING")
    c, app, get_db = _klien(db)
    try:
        _masuk(c)
        r = c.get(f"/web/kasir/tagihan/{k.id_kunjungan}")
        assert r.status_code == 200
        if 'name="idempotency_key"' not in r.text:
            import pytest
            pytest.skip("akun uji tidak berhak melihat form bayar")
        assert "Tindakan berikut belum dikerjakan — dibayar di muka." in r.text
        assert r.text.count('name="konfirmasi_prabayar"') == 1 and "belum dikerjakan</span>" in r.text
        # Form Rp 0: tindakan prabayar harga 0 -> pakai treatment gratis bila ada.
        from sqlalchemy import update
        from app.db.models import MasterTreatment
        t0 = KunjunganTindakan  # noqa: F841
        # Rp 0 dicapai lewat harga snapshot nol: ubah harga treatment di sesi test (rollback).
        tr_id = db.execute(select(KunjunganTindakan.id_treatment).where(
            KunjunganTindakan.id_kunjungan == k.id_kunjungan)).scalar_one()
        db.execute(update(MasterTreatment).where(MasterTreatment.id_treatment == tr_id)
                   .values(harga=0, harga_paket=0)); db.flush()
        r0 = c.get(f"/web/kasir/tagihan/{k.id_kunjungan}")
        assert "Tidak Ada Tagihan" in r0.text
        assert r0.text.count("name=\"konfirmasi_prabayar\"") == 1
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_layar_kasir_tanpa_prabayar_tidak_memuat_kotak(db):
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    _tindakan_selesai(db, k)
    c, app, get_db = _klien(db)
    try:
        _masuk(c)
        r = c.get(f"/web/kasir/tagihan/{k.id_kunjungan}")
        assert r.status_code == 200
        assert 'name="konfirmasi_prabayar"' not in r.text
        assert "dibayar di muka" not in r.text
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_route_bayar_tanpa_centang_redirect_error_dan_dengan_centang_lolos(db):
    from urllib.parse import quote
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    _tindakan_baru(db, k, "PENDING")
    svc = KasirService(db)
    total = svc.get_tagihan(k.id_kunjungan).ringkasan_biaya.total_tagihan
    c, app, get_db = _klien(db)
    try:
        _masuk(c)
        hal = c.get(f"/web/kasir/tagihan/{k.id_kunjungan}")
        if 'name="idempotency_key"' not in hal.text:
            import pytest
            pytest.skip("akun uji tidak berhak membayar")
        import re
        csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', hal.text)
        form = {"metode_bayar": "TUNAI", "nominal": str(total), "sidik": svc.sidik_tagihan(
            svc.get_tagihan(k.id_kunjungan))}
        if csrf:
            form["csrf_token"] = csrf.group(1)
        r = c.post(f"/web/kasir/tagihan/{k.id_kunjungan}/bayar", data=form)
        assert r.status_code == 303
        assert r.headers["location"].endswith("?err=" + quote(_PESAN_PRABAYAR))
        assert _trx_terakhir(db, k) is None
        r2 = c.post(f"/web/kasir/tagihan/{k.id_kunjungan}/bayar",
                    data={**form, "konfirmasi_prabayar": "1"})
        assert r2.status_code == 303 and "/bayar/sukses/" in r2.headers["location"]
        assert _trx_terakhir(db, k) is not None
    finally:
        app.dependency_overrides.pop(get_db, None)
