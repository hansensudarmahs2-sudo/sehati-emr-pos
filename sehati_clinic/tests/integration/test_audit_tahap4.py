"""Audit mendalam tahap 4 (kasir & uang) — 2026-10-15.

Project_Memory/AUDIT_MENDALAM_2026-10-13.md, tahap 4. Layanan ASLI di sesi yang di-rollback
(commit = flush). Balapan sungguhan butuh dua koneksi yang commit; yang diuji di sini adalah
URUTAN pembacaan & penulisan yang membuat balapan itu aman — bukti dua koneksi dijalankan
terpisah di DB dev (dicatat di dokumen audit).
"""
import secrets

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.db.models import KunjunganResep
from app.schemas.kasir import BayarRequest, PembayaranItem
from app.services.kasir_service import KasirService
from tests.integration.test_audit_tahap2 import (  # noqa: F401  (fixture db dipakai ulang)
    V, _bayar, _resep, _siapkan, _tindakan_selesai, _trx_terakhir, db,
)
from tests.integration.test_audit_tahap3 import _rekam_sql


def _bayar_req(svc, k, key=None):
    total = svc.get_tagihan(k.id_kunjungan).ringkasan_biaya.total_tagihan
    pemb = [PembayaranItem(metode_bayar="TUNAI", nominal=total)] if total > 0 else []
    return BayarRequest(id_kunjungan=k.id_kunjungan, pembayaran=pemb,
                        idempotency_key=key or secrets.token_hex(8))


# ---------------------------------------------------------------- T4-1 (a)
# REPEATABLE-READ: SELECT pertama permintaan (get_user_from_cookie) menetapkan POTRET. Kunci
# kunjungan menunggu bayar pertama selesai, tapi SELECT biasa sesudahnya tetap membaca potret
# → "belum ada transaksi" → tagihan KEDUA penuh. Perbaikan: akhiri transaksi baca SEBELUM
# mengunci, sehingga potret baru dibuat SESUDAH kunci didapat (InnoDB membuat read view pada
# pembacaan konsisten PERTAMA; SELECT ... FOR UPDATE bukan pembacaan konsisten).
def test_bayar_mengakhiri_potret_sebelum_mengunci_kunjungan(db):
    staf, k = _siapkan(db)
    _resep(db, k, staf)
    svc = KasirService(db)
    req = _bayar_req(svc, k)                         # SELECT biasa = potret permintaan
    with _rekam_sql(db) as q:
        _flush = db.commit
        db.commit = lambda: (q.append("<<COMMIT>>"), _flush())[1]
        try:
            svc.proses_bayar(req, staf.id_staf)
        finally:
            db.commit = _flush
    i_commit = q.index("<<COMMIT>>")
    i_kunci = next(i for i, x in enumerate(q) if x.startswith("SELECT")
                   and "FROM kunjungan " in x + " " and "FOR UPDATE" in x)
    assert i_commit < i_kunci                         # dulu: tak ada commit sebelum kunci
    assert not [x for x in q[i_commit + 1:i_kunci] if x.startswith("SELECT")]


# ---------------------------------------------------------------- T4-1 (b)
# Tanda DIBAYAR dulu mengenai SEMUA resep/racikan PENDING saat UPDATE, bukan yang ditagih:
# resep yang masuk (SOAP/upsell — keduanya tak mengunci kunjungan) SELAMA bayar ikut lunas
# tanpa ditagih → diserahkan gratis.
def test_resep_yang_masuk_saat_bayar_tidak_ikut_lunas(db, monkeypatch):
    staf, k = _siapkan(db)
    _resep(db, k, staf)
    svc = KasirService(db)
    req = _bayar_req(svc, k)
    asli = KasirService.get_tagihan
    telat = {}

    def get_tagihan_lalu_resep_masuk(self, id_kunjungan, user_role=None):
        t = asli(self, id_kunjungan, user_role)
        if not telat:                                 # dokter menyimpan SOAP saat ini
            telat["r"] = _resep(db, k, staf)
        return t
    monkeypatch.setattr(KasirService, "get_tagihan", get_tagihan_lalu_resep_masuk)
    svc.proses_bayar(req, staf.id_staf)
    monkeypatch.setattr(KasirService, "get_tagihan", asli)

    r = telat["r"]; db.refresh(r)
    assert V(r.status_item) == "PENDING"              # dulu DIBAYAR tanpa ditagih
    t2 = svc.get_tagihan(k.id_kunjungan)              # muncul di tagihan susulan
    assert [x.id_resep for x in t2.rincian_produk] == [r.id_resep]
    assert not t2.sudah_lunas


def test_bayar_tetap_menandai_semua_item_yang_ditagih(db):
    staf, k = _siapkan(db)
    r1 = _resep(db, k, staf)
    r2 = _resep(db, k, staf)
    _bayar(db, k, staf)
    db.refresh(r1); db.refresh(r2)
    assert (V(r1.status_item), V(r2.status_item)) == ("DIBAYAR", "DIBAYAR")
    t = _trx_terakhir(db, k)
    assert (r1.id_transaksi, r2.id_transaksi) == (t.id_transaksi, t.id_transaksi)


# ---------------------------------------------------------------- T4-2
# Retur mengunci baris item, tapi tidak mengubahnya (tetap DISERAHKAN). Pagar sebenarnya —
# jumlah yang SUDAH diretur — dibaca SELECT biasa = potret permintaan. Klik ganda / dua
# petugas: retur kedua melihat "belum diretur" → uang kembali DUA kali, stok +2×q, tanpa PIN.
def _commit_ditandai(db, q):
    _flush = db.commit
    def _c():
        q.append("<<COMMIT>>")
        return _flush()
    return _flush, _c


def test_retur_mengakhiri_potret_sebelum_mengunci_item(db):
    from tests.integration.test_retur_pasien import _retur, _setup
    d = _setup(db)
    with _rekam_sql(db) as q:
        asli, db.commit = _commit_ditandai(db, q)
        try:
            _retur(db, d)
        finally:
            db.commit = asli
    i_commit = q.index("<<COMMIT>>")
    i_kunci = next(i for i, x in enumerate(q) if "FROM kunjungan_resep" in x and "FOR UPDATE" in x)
    assert i_commit < i_kunci                         # dulu: tak ada commit sebelum kunci
    assert not [x for x in q[i_commit + 1:i_kunci] if x.startswith("SELECT")]


# ---------------------------------------------------------------- T4-3
# Aktivasi perpanjangan/upgrade menonaktifkan membership LAMA dan memindahkan sisa kuotanya
# ke history baru. Void dulu me-revert history baru saja → pasien jadi REGULAR, kuota lama
# hilang. Keputusan dr. Hansen 2026-10-15 (pilihan b): void seperti itu DITOLAK.
def _member(db, staf, id_pasien, aksi, id_membership=1):
    from app.services.membership_service import MembershipService
    m = MembershipService(db)
    h = m.create_pending(id_pasien=id_pasien, id_membership=id_membership,
                         actor_id_staf=staf.id_staf, action_type=aksi)
    harga = m.bayar_membership(h.id_history, [PembayaranItem(metode_bayar="TUNAI", nominal=10**7)],
                               staf.id_staf, idempotency_key=secrets.token_hex(8))
    m.activate_membership(h.id_history, staf.id_staf)
    return h, harga["id_transaksi"]


def test_void_perpanjangan_membership_aktif_ditolak(db):
    from app.db.models import Pasien
    staf, k = _siapkan(db)
    h1, _t1 = _member(db, staf, k.id_pasien, "ACTIVATION")
    h2, t2 = _member(db, staf, k.id_pasien, "RENEWAL")
    with pytest.raises(HTTPException) as e:
        KasirService(db).void_transaksi(t2, "SALAH_INPUT", "uji T4-3", [], staf.id_staf)
    assert e.value.status_code == 409
    db.refresh(h2)
    assert h2.is_active                                # tidak di-revert
    assert V(db.get(Pasien, k.id_pasien).tipe_membership) == "VIP"   # dulu REGULAR


def test_void_aktivasi_pertama_tetap_boleh(db):
    from app.db.models import Pasien
    staf, k = _siapkan(db)
    h1, t1 = _member(db, staf, k.id_pasien, "ACTIVATION")
    KasirService(db).void_transaksi(t1, "SALAH_INPUT", "uji T4-3", [], staf.id_staf)
    db.refresh(h1)
    assert not h1.is_active
    assert V(db.get(Pasien, k.id_pasien).tipe_membership) == "REGULAR"


def test_void_hari_lampau_perpanjangan_membership_juga_ditolak(db):
    from datetime import timedelta
    from app.db.models import TransaksiKasir
    from app.db.models._enums import StafRoleEnum
    staf, k = _siapkan(db)
    _member(db, staf, k.id_pasien, "ACTIVATION")
    _h2, t2 = _member(db, staf, k.id_pasien, "RENEWAL")
    trx = db.get(TransaksiKasir, t2)
    trx.waktu_bayar = trx.waktu_bayar - timedelta(days=1); db.flush()
    with pytest.raises(HTTPException) as e:
        KasirService(db).force_past_day_void(t2, "SALAH_INPUT", "uji T4-3", [], staf.id_staf, StafRoleEnum.SUPERADMIN)
    assert e.value.status_code == 409


def test_pesan_error_di_url_tidak_terpotong():
    """Route void dulu menempel `?err={e.detail}` mentah: # memotong pesan (fragmen URL)."""
    from urllib.parse import urlsplit
    from starlette.datastructures import QueryParams
    from app.web.routes.kasir import _q_err as q_kasir
    from app.web.routes.dokter import _q_err as q_dokter
    pesan = "Transaksi #12 menggantikan membership lama (#7, #8) & sisa kuota +3 hilang"
    for q in (q_kasir, q_dokter):
        url = urlsplit(f"/web/kasir/bayar/sukses/12?err={q(pesan)}")
        assert url.fragment == ""
        assert QueryParams(url.query)["err"] == pesan


# ---------------------------------------------------------------- T4-5
# Refund obat tertunda mengunci ITEM saja; void mengunci transaksi→kunjungan, lalu pagar
# "sudah ada refund" dibaca SELECT biasa (potret awal permintaan). Refund commit di antara →
# void tak melihatnya → uang yang sama keluar DUA kali; refund atas transaksi VOID hilang dari
# hitungan laci. Perbaikan: refund ikut mengunci KUNJUNGAN (urutan sama dengan bayar/serah/
# void), dan keduanya menutup transaksi baca sebelum mengunci.
def _urutan(q, *penanda):
    return [next(i for i, x in enumerate(q) if p(x)) for p in penanda]


def _rekam_dengan_commit(db, fn):
    with _rekam_sql(db) as q:
        asli, db.commit = _commit_ditandai(db, q)
        try:
            fn()
        finally:
            db.commit = asli
    return q


def test_void_mengakhiri_potret_sebelum_mengunci(db):
    staf, k = _siapkan(db)
    _resep(db, k, staf)
    _bayar(db, k, staf)
    t = _trx_terakhir(db, k)
    q = _rekam_dengan_commit(db, lambda: KasirService(db).void_transaksi(
        t.id_transaksi, "SALAH_INPUT", "uji T4-5", [], staf.id_staf))
    i_commit, i_trx = _urutan(q, lambda x: x == "<<COMMIT>>",
                              lambda x: "FROM transaksi_kasir" in x and "FOR UPDATE" in x)
    assert i_commit < i_trx                           # dulu: tak ada commit sebelum kunci
    assert not [x for x in q[i_commit + 1:i_trx] if x.startswith("SELECT")]


def test_refund_tertunda_mengunci_kunjungan_dulu(db):
    staf, k = _siapkan(db)
    r = _resep(db, k, staf)
    _bayar(db, k, staf)
    q = _rekam_dengan_commit(db, lambda: KasirService(db).refund_item_tertunda(
        id_resep=r.id_resep, alasan="uji T4-5", actor_id_staf=staf.id_staf))
    from tests.integration.test_audit_tahap3 import _berkunci
    i_commit = q.index("<<COMMIT>>")
    i_kj = q.index(_berkunci(q, "kunjungan")[0])
    i_item = q.index(_berkunci(q, "kunjungan_resep")[0])
    assert i_commit < i_kj < i_item                   # dulu: kunjungan tak dikunci
    assert not [x for x in q[i_commit + 1:i_kj] if x.startswith("SELECT")]
