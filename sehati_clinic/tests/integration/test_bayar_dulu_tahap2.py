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


# ---------------------------------------------------------------- T2-3
# Komisi tindakan = dibayar DAN selesai, mana pun yang terakhir. Sejak T2-1 tindakan bisa
# dibayar sebelum dikerjakan; dulu komisi hanya ditulis saat bayar dan hanya untuk tindakan
# SELESAI, jadi tindakan prabayar yang selesai belakangan TIDAK pernah berkomisi (tagihan
# susulan yang dulu "menangkapnya" kini tidak terjadi lagi).
def _beri_komisi(db, kt, perawat):
    """Treatment-nya diberi komisi perawat NOMINAL dan tindakannya diberi pelaksana —
    di DB dev banyak treatment tanpa komisi, jadi test tidak bergantung data master.
    Ikut rollback fixture."""
    from app.db.models import MasterTreatment
    tr = db.get(MasterTreatment, kt.id_treatment)
    tr.komisi_perawat_tipe = "NOMINAL"
    tr.komisi_perawat_value = 12345
    kt.id_perawat_pelaksana = perawat.id_staf
    db.flush()


def _komisi(db, kt, status="AKTIF"):
    from app.db.models import KomisiLedger
    return db.execute(select(KomisiLedger).where(
        KomisiLedger.sumber == "TINDAKAN",
        KomisiLedger.id_ref == kt.id_kunjungan_tindakan,
        KomisiLedger.status == status)).scalars().all()


def _selesai_sebelum_bayar(db, k):
    from datetime import datetime, timedelta
    t = _tindakan_baru(db, k, "SELESAI")
    t.waktu_selesai = datetime.now() - timedelta(seconds=5)
    db.flush()
    return t


def _kerjakan(db, kt, staf):
    from app.services.treatment_service import TreatmentService
    svc = TreatmentService(db)
    svc.start_tindakan(kt.id_kunjungan_tindakan, staf.id_staf)
    kt.id_perawat_pelaksana = staf.id_staf     # start tanpa user_role tidak mengisinya
    db.flush()
    svc.end_tindakan(kt.id_kunjungan_tindakan, staf.id_staf)
    db.refresh(kt)


def test_split_prabayar_komisi_saat_selesai_sekali_terikat_t1(db, monkeypatch):
    """Review Focus 3. T1 menagih A (sudah dikerjakan) + B (prabayar). B selesai → tepat
    satu komisi AKTIF, `id_transaksi` = T1, `tanggal` = tanggal SELESAI (bukan tanggal
    bayar); tagihan susulan T2 untuk item baru tidak mencatat B lagi."""
    from datetime import date, datetime as _dt, timedelta
    import app.services.treatment_service as _ts
    from tests.integration.test_audit_tahap2 import _resep
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    a = _selesai_sebelum_bayar(db, k)
    b = _tindakan_baru(db, k, "PENDING")
    _beri_komisi(db, a, staf)
    _beri_komisi(db, b, staf)
    _bayar(db, k, staf, konfirmasi_prabayar=True)
    t1 = _trx_terakhir(db, k)
    ka = _komisi(db, a)
    assert len(ka) == 1 and ka[0].id_transaksi == t1.id_transaksi and ka[0].tanggal == date.today()
    assert _komisi(db, b) == []                    # belum dikerjakan → belum berkomisi

    class _Besok(_dt):                              # selesai BESOK: tanggal selesai ≠ bayar
        @classmethod
        def now(cls, tz=None):
            return _dt.now(tz) + timedelta(days=1)
    monkeypatch.setattr(_ts, "datetime", _Besok)
    _kerjakan(db, b, staf)
    monkeypatch.undo()
    kb = _komisi(db, b)
    assert len(kb) == 1                            # dulu: 0 — komisi hilang
    assert kb[0].id_transaksi == t1.id_transaksi
    assert kb[0].tanggal == b.waktu_selesai.date() == date.today() + timedelta(days=1)
    assert float(kb[0].komisi_nominal) == 12345 and kb[0].id_staf == staf.id_staf

    _resep(db, k, staf, detik=5)                    # item baru → tagihan susulan T2
    _bayar(db, k, staf)
    t2 = _trx_terakhir(db, k)
    assert t2.id_transaksi != t1.id_transaksi
    assert [r.id_transaksi for r in _komisi(db, b)] == [t1.id_transaksi]
    assert [r.id_transaksi for r in _komisi(db, a)] == [t1.id_transaksi]


def test_bayar_sesudah_selesai_komisi_saat_bayar(db):
    """Perilaku lama tetap: tindakan selesai lebih dulu → komisi ditulis saat bayar,
    bertanggal bayar, terikat transaksi pembayarnya."""
    from datetime import date
    staf, k = _siapkan(db)
    a = _selesai_sebelum_bayar(db, k)
    _beri_komisi(db, a, staf)
    _bayar(db, k, staf)
    t1 = _trx_terakhir(db, k)
    ka = _komisi(db, a)
    assert len(ka) == 1 and ka[0].id_transaksi == t1.id_transaksi
    assert ka[0].tanggal == date.today()


def test_tindakan_selesai_tak_ditagih_tidak_berkomisi_dari_transaksi_lain(db, monkeypatch):
    """Tindakan C selesai SELAMA pembayaran T1 (sesudah tagihan dihitung) — C tidak ditagih
    T1 dan tetap `id_transaksi` NULL. Dulu komisi ditulis untuk SEMUA tindakan SELESAI di
    kunjungan, jadi C berkomisi atas transaksi yang tidak membayarnya; kalau T1 lalu
    di-void, komisi C ikut tertarik padahal tagihannya belum pernah ada."""
    from app.services.komisi_service import KomisiService
    from tests.integration.test_audit_tahap2 import _resep
    staf, k = _siapkan(db)
    _resep(db, k, staf)
    asli = KomisiService.catat_komisi_transaksi
    tampung = {}

    def _sela(self, **kw):
        c = _tindakan_baru(db, k, "SELESAI")        # perawat menekan Selesai di detik ini
        _beri_komisi(db, c, staf)
        tampung["c"] = c
        return asli(self, **kw)
    monkeypatch.setattr(KomisiService, "catat_komisi_transaksi", _sela)
    _bayar(db, k, staf)
    c = tampung["c"]
    db.refresh(c)
    assert c.id_transaksi is None
    assert _komisi(db, c) == []                    # dulu: 1 baris terikat T1


def _prabayar_lalu_void(db):
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    b = _tindakan_baru(db, k, "PENDING")
    _beri_komisi(db, b, staf)
    _bayar(db, k, staf, konfirmasi_prabayar=True)
    return staf, k, b, _trx_terakhir(db, k)


def test_selesai_sesudah_transaksi_pembayar_void_tanpa_komisi(db):
    """Review Focus 2 (Ruling P1): T1 di-VOID, B lalu selesai → TIDAK berkomisi.

    Sejak T2-4 void MELEPAS `id_transaksi` B, jadi `end_tindakan` tak memanggil komisi sama
    sekali. Pertahanan sendiri `catat_komisi_tindakan` (transaksi bukan BAYAR → 0) tetap
    diuji dengan menempelkan kembali penanda ke T1 — bentuk data bila pelepasan terlewat."""
    from tests.integration.test_audit_tahap2 import _void
    staf, k, b, t1 = _prabayar_lalu_void(db)
    _void(db, t1.id_transaksi, staf)
    db.refresh(t1); db.refresh(b)
    assert V(t1.status_transaksi) == "VOID" and b.id_transaksi is None   # T2-4
    b.id_transaksi = t1.id_transaksi; db.flush()
    _kerjakan(db, b, staf)
    assert _komisi(db, b) == [] and _komisi(db, b, "VOID") == []


def test_komisi_saat_selesai_ikut_void_bersama_transaksinya(db):
    """Baris komisi yang ditulis saat `end_tindakan` membawa `id_transaksi` pembayar, jadi
    `void_komisi_transaksi` (dipanggil KEDUA jalur void) ikut menariknya.

    Catatan: lewat layar, void T1 sesudah B selesai DITOLAK pagar "tindakan sudah selesai"
    (`_pagari_void_tindakan_selesai`) — komisi B tetap AKTIF. Yang diuji di sini: kalau
    void komisi dipanggil, baris saat-selesai tidak tertinggal."""
    import pytest
    from fastapi import HTTPException
    from app.services.komisi_service import KomisiService
    from tests.integration.test_audit_tahap2 import _void
    staf, k, b, t1 = _prabayar_lalu_void(db)
    _kerjakan(db, b, staf)
    assert len(_komisi(db, b)) == 1
    with pytest.raises(HTTPException) as e:
        _void(db, t1.id_transaksi, staf)
    assert e.value.status_code == 400 and len(_komisi(db, b)) == 1
    KomisiService(db).void_komisi_transaksi(t1.id_transaksi, staf.id_staf)
    assert _komisi(db, b) == [] and len(_komisi(db, b, "VOID")) == 1


# ---------------------------------------------------------------- T2-4
# Void transaksi yang MENAGIH tindakan yang belum dikerjakan (prabayar). Pasien batal membeli:
# tindakan PENDING/PROSES kembali "belum ditagih" (id_transaksi NULL), tetapi kuota yang
# dipegangnya TIDAK dikembalikan dan series yang sesi 1-nya tindakan itu TIDAK dibatalkan —
# tindakannya masih hidup dan masih memegang keduanya. Yang mengembalikan nanti: Batalkan
# tindakan (Ruling 12), tepat sekali. Dulu: id_transaksi tetap menempel ke transaksi VOID
# (tindakan tak bisa ditagih lagi, tak bisa dibatalkan — buntu), kuota dikembalikan oleh void
# DAN akan dikembalikan lagi oleh Batalkan, series dibatalkan padahal sesi 1-nya masih jalan.
import pytest as _pytest  # noqa: E402


def _prabayar_kuota(db, terpakai=2):
    """SOAP + tindakan kuota PENDING dibayar di muka. `terpakai=2`: satu slot milik kunjungan
    lain, supaya "dikembalikan dua kali" terlihat (lantai 0 menyamarkannya)."""
    from tests.integration.test_bayar_dulu_tahap1 import _kuota_pending
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    q, t = _kuota_pending(db, k)
    q.kuota_terpakai = terpakai; db.flush()
    _bayar(db, k, staf, konfirmasi_prabayar=True)
    db.refresh(t)
    trx = _trx_terakhir(db, k)
    assert t.id_transaksi == trx.id_transaksi
    return staf, k, q, t, trx


def _ids_tagihan(db, k):
    return [r.id_kunjungan_tindakan
            for r in KasirService(db).get_tagihan(k.id_kunjungan).rincian_tindakan]


@_pytest.mark.parametrize("jalur", ["void", "force"])
def test_void_prabayar_melepas_tindakan_kuota_tetap_lalu_batalkan_sekali(db, jalur):
    """Review Focus 1, kedua jalur void."""
    from tests.integration.test_bayar_dulu_tahap1 import _batalkan, _void_jalur
    staf, k, q, t, trx = _prabayar_kuota(db)
    _void_jalur(db, trx, staf, jalur)
    db.refresh(t); db.refresh(q); db.refresh(k); db.refresh(trx)
    assert V(trx.status_transaksi) == "VOID"
    assert t.id_transaksi is None                    # dulu: tetap = transaksi VOID
    assert V(t.status_tindakan) == "PENDING"
    assert q.kuota_terpakai == 2                     # dulu: 1 — dikembalikan void
    assert t.id_kunjungan_tindakan in _ids_tagihan(db, k)   # bisa ditagih lagi
    assert V(k.status_antrian) == "ANTRI_TREATMENT"  # dihitung ulang dari isi
    _batalkan(db, t, staf)                           # dulu: 400 "sudah dibayar"
    db.refresh(q); db.refresh(t)
    assert V(t.status_tindakan) == "BATAL"
    assert q.kuota_terpakai == 1                     # dikembalikan TEPAT sekali


def test_void_prabayar_proses_dilepas_tetap_proses(db):
    from tests.integration.test_audit_tahap2 import _void
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    t = _tindakan_baru(db, k, "PROSES")
    _bayar(db, k, staf, konfirmasi_prabayar=True)
    _void(db, _trx_terakhir(db, k).id_transaksi, staf)
    db.refresh(t); db.refresh(k)
    assert t.id_transaksi is None and V(t.status_tindakan) == "PROSES"
    assert t.id_kunjungan_tindakan in _ids_tagihan(db, k)
    assert V(k.status_antrian) == "ON_TREATMENT"


@_pytest.mark.parametrize("jalur", ["void", "force"])
def test_void_prabayar_tidak_membatalkan_series_sesi_1_hidup(db, jalur):
    """Sesi 1 series (pembawa harga paket) dibayar di muka lalu transaksinya di-void: series
    TIDAK dibatalkan (sesi 1 masih PENDING). Batalkan sesi 1 sesudahnya → series batal
    (aturan `_batal_tindakan`: sesi 1 belum dibayar)."""
    from tests.integration.test_audit_tahap2 import _rencana
    from tests.integration.test_bayar_dulu_tahap1 import _batalkan, _void_jalur
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    s1 = _rencana(db, k, 1, k.id_kunjungan, "SCHEDULED")
    s2 = _rencana(db, k, 2, k.id_kunjungan, "PENDING")
    t = KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=s1.id_treatment,
                          id_rencana=s1.id_rencana, status_tindakan="PENDING")
    db.add(t); db.flush()
    _bayar(db, k, staf, konfirmasi_prabayar=True)
    db.refresh(t)
    assert t.id_transaksi is not None
    _void_jalur(db, _trx_terakhir(db, k), staf, jalur)
    db.refresh(s1); db.refresh(s2); db.refresh(t)
    assert (V(s1.status), V(s2.status)) == ("SCHEDULED", "PENDING")   # dulu: CANCELLED
    assert t.id_transaksi is None
    _batalkan(db, t, staf)
    db.refresh(s1); db.refresh(s2)
    assert (V(s1.status), V(s2.status)) == ("CANCELLED", "CANCELLED")


def _penyetuju(db):
    import secrets
    from app.core.security import hash_password
    from app.db.models import MasterStaf
    from app.db.models._enums import StafRoleEnum
    admin = MasterStaf(username=f"uji_t24_a_{secrets.token_hex(3)}", password_hash=hash_password("x"),
                       role=StafRoleEnum.ADMIN, nama_staf="Uji T24 Admin", is_active=True)
    sup = MasterStaf(username=f"uji_t24_s_{secrets.token_hex(3)}", password_hash=hash_password("x"),
                     role=StafRoleEnum.SUPERADMIN, nama_staf="Uji T24 Sup", is_active=True,
                     pin=hash_password("4321"))
    db.add_all([admin, sup]); db.flush()
    return admin, sup


def test_void_lampau_prabayar_pin_melepas_tindakan_dan_uang_keluar(db):
    """Pola K4-1: transaksi prabayar KEMARIN di-void hari ini dengan PIN penyetuju → uang
    keluar tercatat (jenis VOID), tindakan dilepas, kuota tetap, lalu Batalkan sekali."""
    from datetime import timedelta
    from app.db.models import TransaksiRefund
    from app.db.models._enums import StafRoleEnum
    from tests.integration.test_bayar_dulu_tahap1 import _batalkan
    staf, k, q, t, trx = _prabayar_kuota(db)
    trx.waktu_bayar = trx.waktu_bayar - timedelta(days=1); db.flush()
    admin, sup = _penyetuju(db)
    KasirService(db).force_past_day_void(
        trx.id_transaksi, "CUSTOMER_CANCEL", "uji void lampau prabayar", [], admin.id_staf,
        StafRoleEnum.ADMIN, id_staf_otorisasi=sup.id_staf, pin_otorisasi="4321")
    db.refresh(trx); db.refresh(t); db.refresh(q)
    assert (V(trx.status_transaksi), bool(trx.late_void)) == ("VOID", True)
    if trx.total_tagihan and trx.total_tagihan > 0:
        assert db.execute(select(TransaksiRefund).where(
            TransaksiRefund.id_transaksi == trx.id_transaksi,
            TransaksiRefund.jenis_refund == "VOID")).first() is not None
    assert t.id_transaksi is None and q.kuota_terpakai == 2
    assert t.id_kunjungan_tindakan in _ids_tagihan(db, k)
    _batalkan(db, t, staf)
    db.refresh(q)
    assert q.kuota_terpakai == 1


def test_void_prabayar_audit_pelepasan(db):
    from app.db.models import AuditLog
    from tests.integration.test_audit_tahap2 import _void
    staf, k, q, t, trx = _prabayar_kuota(db)
    _void(db, trx.id_transaksi, staf)
    log = db.execute(select(AuditLog).where(
        AuditLog.aksi == "VOID_TINDAKAN_DILEPAS",
        AuditLog.id_target == t.id_kunjungan_tindakan)).scalars().all()
    assert len(log) == 1


def test_kedua_jalur_void_lewat_helper_bersama():
    """CLAUDE.md §4.1: jalur void ADA DUA. Langkah cascade (series, status, kuota, pelepasan
    tindakan) hanya boleh dipanggil lewat SATU helper, supaya langkah baru tak hilang di satu
    jalur (pernah: 3 langkah rollback hilang di force_past_day_void)."""
    import inspect
    for fn in (KasirService.void_transaksi, KasirService.force_past_day_void):
        src = inspect.getsource(fn)
        assert "self._cascade_void_bersama(" in src
        for langsung in ("_cancel_series_sesi_pending(", "_cascade_void_kunjungan(",
                         "_revert_kuota_per_tindakan(", "_lepas_tindakan_hidup("):
            assert langsung not in src, (fn.__name__, langsung)


def test_void_mengunci_kunjungan_sebelum_menulis_tindakan(db):
    """Ruling P4: kunjungan = titik serialisasi. Void (trx → kunjungan → tindakan) tidak boleh
    menyentuh baris tindakan sebelum kunci kunjungan."""
    import re
    from tests.integration.test_audit_tahap3 import _berkunci
    from tests.integration.test_audit_tahap4 import _rekam_dengan_commit
    staf, k, q, t, trx = _prabayar_kuota(db)
    qs = _rekam_dengan_commit(db, lambda: KasirService(db).void_transaksi(
        trx.id_transaksi, "SALAH_INPUT", "uji urutan kunci", [], staf.id_staf))
    i_kj = qs.index(_berkunci(qs, "kunjungan")[0])
    tulis_kt = [i for i, x in enumerate(qs) if re.match(r"UPDATE kunjungan_tindakan\b", x)]
    kunci_kt = [qs.index(x) for x in _berkunci(qs, "kunjungan_tindakan")]
    assert tulis_kt, "void prabayar harus menulis kunjungan_tindakan (melepas id_transaksi)"
    assert i_kj < min(tulis_kt + kunci_kt)


def test_end_tindakan_kunci_kunjungan_dulu_tanpa_for_share(db):
    """Ruling P4 (deadlock): void kini MENULIS baris tindakan sambil memegang trx + kunjungan.
    `end_tindakan` dulu mengunci tindakan lalu membaca trx FOR SHARE → void (trx X, menunggu
    tindakan) vs end (tindakan X, menunggu trx S) = deadlock. Sekarang end: baca-segar →
    kunjungan FOR UPDATE → tindakan FOR UPDATE → status trx dibaca biasa."""
    from tests.integration.test_audit_tahap3 import _berkunci
    from tests.integration.test_audit_tahap4 import _rekam_dengan_commit
    from app.services.treatment_service import TreatmentService
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    b = _tindakan_baru(db, k, "PENDING")
    _beri_komisi(db, b, staf)
    _bayar(db, k, staf, konfirmasi_prabayar=True)
    svc = TreatmentService(db)
    svc.start_tindakan(b.id_kunjungan_tindakan, staf.id_staf)
    b.id_perawat_pelaksana = staf.id_staf; db.flush()
    qs = _rekam_dengan_commit(db, lambda: svc.end_tindakan(b.id_kunjungan_tindakan, staf.id_staf))
    i_commit = qs.index("<<COMMIT>>")
    i_kj = qs.index(_berkunci(qs, "kunjungan")[0])
    i_kt = qs.index(_berkunci(qs, "kunjungan_tindakan")[0])
    assert i_commit < i_kj < i_kt
    assert not [x for x in qs[i_commit + 1:i_kj] if x.startswith("SELECT")]
    assert not [x for x in qs if "FOR SHARE" in x or "LOCK IN SHARE MODE" in x]
    assert len(_komisi(db, b)) == 1                  # komisi saat selesai tetap tercatat


def test_catat_komisi_transaksi_tanpa_id_transaksi_tidak_menyentuh_tindakan(db):
    """Minor dari T2-3: `id_transaksi=None` dulu menjadi `id_transaksi IS NULL` di kueri
    tindakan (tindakan BELUM ditagih). Sekarang dilewati eksplisit — tak ada kueri tindakan."""
    import re
    from app.services.komisi_service import KomisiService
    from tests.integration.test_audit_tahap3 import _rekam_sql
    staf, k = _siapkan(db)
    c = _tindakan_baru(db, k, "SELESAI")
    _beri_komisi(db, c, staf)
    with _rekam_sql(db) as qs:
        n = KomisiService(db).catat_komisi_transaksi(
            id_transaksi=None, id_kunjungan=k.id_kunjungan, id_pasien=k.id_pasien,
            id_dokter_assigned=None, rincian_produk=[])
    assert n == 0 and _komisi(db, c) == []
    assert not [x for x in qs if re.search(r"FROM kunjungan_tindakan(?![A-Za-z0-9_])", x)]
