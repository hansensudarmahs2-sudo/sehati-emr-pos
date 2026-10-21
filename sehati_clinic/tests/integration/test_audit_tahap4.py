"""Audit mendalam tahap 4 (kasir & uang) — 2026-10-15.

Project_Memory/AUDIT_MENDALAM_2026-10-13.md, tahap 4. Layanan ASLI di sesi yang di-rollback
(commit = flush). Balapan sungguhan butuh dua koneksi yang commit; yang diuji di sini adalah
URUTAN pembacaan & penulisan yang membuat balapan itu aman — bukti dua koneksi dijalankan
terpisah di DB dev (dicatat di dokumen audit).
"""
import secrets
from datetime import datetime

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


# ---------------------------------------------------------------- T4-6
# Cek "sudah ada sesi hari ini" = SELECT biasa lalu INSERT, tanpa pagar unik: dua klik Buka
# Kasir (atau Kasir + Admin) bersamaan → dua sesi OPEN satu tanggal; satu tertinggal OPEN
# memblokir esok hari, laporan tutup kasir menghitung hari itu dua kali. Perbaikan (disetujui
# dr. Hansen 2026-10-16): indeks UNIK `tanggal_sesi` — database sendiri yang menolak.
def _hari_ini_kosong(db):
    from datetime import datetime as _dt
    from app.db.models import KasirClosing
    if db.execute(select(KasirClosing).where(
            KasirClosing.shift_mulai >= _dt.combine(_dt.now().date(), _dt.min.time()))).first():
        pytest.skip("Hari ini sudah ada sesi kasir di DB dev — test ini butuh hari yang kosong.")


def test_dua_sesi_satu_tanggal_ditolak_database(db):
    from datetime import datetime as _dt, timedelta
    from sqlalchemy.exc import IntegrityError
    from app.db.models import KasirClosing
    staf, _k = _siapkan(db)
    tgl = _dt(2031, 1, 1, 9, 0)                      # tanggal yang pasti kosong
    db.add(KasirClosing(id_staf_kasir=staf.id_staf, shift_mulai=tgl, status="OPEN", modal_awal=0))
    db.flush()
    db.add(KasirClosing(id_staf_kasir=staf.id_staf, shift_mulai=tgl + timedelta(hours=2),
                        status="OPEN", modal_awal=0))
    with pytest.raises(IntegrityError) as e:         # dulu: diterima
        db.flush()
    assert "ux_kasir_closing_tanggal" in str(e.value.orig)


def test_buka_kasir_yang_kalah_balapan_dapat_pesan_rapi(db, monkeypatch):
    """Permintaan kedua lolos cek (potret basi) — sesi pemenang baru saja masuk."""
    from datetime import datetime as _dt
    from app.db.models import KasirClosing
    from app.services.kasir_closing_service import KasirClosingService
    _hari_ini_kosong(db)
    staf, _k = _siapkan(db)
    db.add(KasirClosing(id_staf_kasir=staf.id_staf, shift_mulai=_dt.now(), status="OPEN",
                        modal_awal=0))                # pemenang
    db.flush()
    svc = KasirClosingService(db)
    monkeypatch.setattr(svc, "get_open_session", lambda *a, **k: None)
    monkeypatch.setattr(svc, "_sesi_pada_tanggal", lambda *a, **k: None)
    with pytest.raises(HTTPException) as e:
        svc.buka_kasir(id_staf_kasir=staf.id_staf, modal_awal=0)
    assert e.value.status_code == 400 and "sudah dibuka" in e.value.detail


def test_tutup_kasir_membaca_sesi_berkunci(db):
    from datetime import datetime as _dt, timedelta
    from app.db.models import KasirClosing
    from app.services.kasir_closing_service import KasirClosingService
    staf, k = _siapkan(db)
    k.status_antrian = "COMPLETED"; db.flush()
    if db.execute(select(KasirClosing).where(KasirClosing.status == "OPEN")).first():
        pytest.skip("DB dev sudah punya sesi kasir OPEN.")
    db.add(KasirClosing(id_staf_kasir=staf.id_staf, shift_mulai=_dt(2031, 1, 2, 9, 0),
                        status="OPEN", modal_awal=0))
    db.flush()
    def _tutup():
        try:
            KasirClosingService(db).tutup_kasir(staf.id_staf, {"TUNAI": 0})
        except HTTPException:
            pass            # pagar antrian DB dev boleh menolak; yang diuji urutan kuncinya
    q = _rekam_dengan_commit(db, _tutup)
    i_commit, i_kunci = _urutan(q, lambda x: x == "<<COMMIT>>",
                                lambda x: "FROM kasir_closing" in x and "FOR UPDATE" in x)
    assert i_commit < i_kunci                         # dulu: sesi dibaca tanpa kunci


def test_baca_segar_menolak_sesi_dengan_perubahan_tertunda(db):
    """Pola commit-di-awal tidak boleh diam-diam meng-commit pekerjaan pemanggil."""
    from app.services._baca_segar import mulai_baca_segar
    staf, k = _siapkan(db)
    k.status_antrian = "ANTRI_OBAT"                   # belum di-flush
    with pytest.raises(RuntimeError):
        mulai_baca_segar(db)


# ---------------------------------------------------------------- T4-8
# Metode bayar/refund dulu teks bebas (hanya .upper()). Tutup kasir hanya menghitung lima
# metode kanonik → POST rakitan `metode=GRATIS`/`TUKAR` menaikkan omzet tanpa laci yang
# mengharapkan uangnya; refund ber-metode aneh mengurangi omzet tanpa mengurangi laci.
@pytest.mark.parametrize("metode", ["GRATIS", "TUKAR", "CASH", ""])
def test_metode_bayar_di_luar_daftar_ditolak(metode):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        PembayaranItem(metode_bayar=metode, nominal=1000)


def test_metode_bayar_kanonik_dinormalisasi():
    assert PembayaranItem(metode_bayar=" qris ", nominal=1000).metode_bayar == "QRIS"


def test_refund_tertunda_metode_aneh_ditolak(db):
    staf, k = _siapkan(db)
    r = _resep(db, k, staf)
    _bayar(db, k, staf)
    with pytest.raises(HTTPException) as e:
        KasirService(db).refund_item_tertunda(id_resep=r.id_resep, alasan="uji T4-8",
                                              metode_refund="TUKAR", actor_id_staf=staf.id_staf)
    assert e.value.status_code == 400


def test_retur_refund_metode_tukar_ditolak(db):
    from tests.integration.test_retur_pasien import _retur, _setup
    d = _setup(db)
    with pytest.raises(HTTPException) as e:
        _retur(db, d, metode_refund="TUKAR")
    assert e.value.status_code == 400


# ---------------------------------------------------------------- T4-9
# Bayar & aktivasi membership = cek status lalu tulis, dengan `db.get` biasa. Klik ganda
# "Aktifkan" pada perpanjangan/upgrade → kuota benefit DUA kali (tak ada indeks unik), carry-
# over ditambah dua kali. Bayar ganda (kunci idempotensi beda) → transaksi pertama yatim.
def _pending_dibayar(db, staf, id_pasien, aksi="ACTIVATION"):
    from app.services.membership_service import MembershipService
    m = MembershipService(db)
    h = m.create_pending(id_pasien=id_pasien, id_membership=1, actor_id_staf=staf.id_staf,
                         action_type=aksi)
    m.bayar_membership(h.id_history, [PembayaranItem(metode_bayar="TUNAI", nominal=10**7)],
                       staf.id_staf, idempotency_key=secrets.token_hex(8))
    return m, h


def test_aktivasi_membership_membaca_berkunci(db):
    staf, k = _siapkan(db)
    m, h = _pending_dibayar(db, staf, k.id_pasien)
    q = _rekam_dengan_commit(db, lambda: m.activate_membership(h.id_history, staf.id_staf))
    i_commit, i_kunci = _urutan(q, lambda x: x == "<<COMMIT>>",
                                lambda x: "FROM pasien_membership_history" in x and "FOR UPDATE" in x)
    assert i_commit < i_kunci                         # dulu: db.get tanpa kunci
    assert not [x for x in q[i_commit + 1:i_kunci] if x.startswith("SELECT")]


def test_aktivasi_kedua_ditolak_walau_objek_di_sesi_basi(db):
    from sqlalchemy import text
    from app.db.models import PasienMembershipKuota
    staf, k = _siapkan(db)
    m, h = _pending_dibayar(db, staf, k.id_pasien)
    db.execute(text("UPDATE pasien_membership_history SET is_active=1, status_aktivasi=\x27ACTIVE\x27 "
                    "WHERE id_history=:i"), {"i": h.id_history})   # permintaan lain sudah
    n0 = db.execute(select(PasienMembershipKuota).where(
        PasienMembershipKuota.id_membership_history == h.id_history)).all()
    with pytest.raises(HTTPException):
        m.activate_membership(h.id_history, staf.id_staf)
    n1 = db.execute(select(PasienMembershipKuota).where(
        PasienMembershipKuota.id_membership_history == h.id_history)).all()
    assert len(n1) == len(n0)                         # dulu: kuota dibuat lagi


def test_bayar_membership_membaca_berkunci(db):
    from app.services.membership_service import MembershipService
    staf, k = _siapkan(db)
    m = MembershipService(db)
    h = m.create_pending(id_pasien=k.id_pasien, id_membership=1, actor_id_staf=staf.id_staf,
                         action_type="ACTIVATION")
    q = _rekam_dengan_commit(db, lambda: m.bayar_membership(
        h.id_history, [PembayaranItem(metode_bayar="TUNAI", nominal=10**7)], staf.id_staf,
        idempotency_key=secrets.token_hex(8)))
    i_commit, i_kunci = _urutan(q, lambda x: x == "<<COMMIT>>",
                                lambda x: "FROM pasien_membership_history" in x and "FOR UPDATE" in x)
    assert i_commit < i_kunci


# ---------------------------------------------------------------- T4-10
# Keputusan dr. Hansen 2026-10-16: diskon member produk berlaku untuk SEMUA produk (perilaku
# kasir). Satu-satunya pembaca tanda `eligible_member_discount` = harga pengganti TUKAR — dulu
# produk tak bertanda tidak didiskon saat ditukar, sehingga menukar dengan produk yang SAMA
# membuat pasien member membayar "selisih" sebesar diskonnya.
def test_harga_pengganti_tukar_diskon_semua_produk(db, monkeypatch):
    from decimal import Decimal as D
    from app.services.membership_service import DiskonMembership, MembershipService
    from app.services.retur_pasien_service import ReturPasienService
    from tests.integration.test_retur_pasien import _setup
    d = _setup(db)
    assert d["produk"].eligible_member_discount is False          # produk TIDAK bertanda
    monkeypatch.setattr(MembershipService, "get_diskon_for_pasien",
                        lambda self, id_pasien: DiskonMembership(D("0"), D("10"), "VIP", True))
    rows, total = ReturPasienService(db)._harga_pengganti(
        d["trx"], [{"id_produk": d["produk"].id_produk, "qty": 1}])
    (_p, _q, harga, sub, disk), = rows
    assert (sub, disk, total) == (D("100000.00"), D("10000.00"), D("90000.00"))  # dulu diskon 0


# ---------------------------------------------------------------- T4-11
# Harga sesi 1 series = per_sesi × JUMLAH rencana dengan kunci (pasien, treatment, kunjungan
# pembuat) — tanpa pengelompokan per series. Dua series treatment yang sama di satu kunjungan
# (SOAP berisi dua, atau reopen) → sesi 1 masing-masing ditagih N1+N2 sesi.
def _series(db, k, tr, n, status_s1="SCHEDULED"):
    from app.db.models import KunjunganTindakan, PasienRencanaTreatment
    r1 = PasienRencanaTreatment(id_pasien=k.id_pasien, id_treatment=tr.id_treatment, urutan_sesi=1,
                                nama_tindakan=tr.nama_treatment, id_kunjungan_pembuat=k.id_kunjungan,
                                status=status_s1)
    db.add(r1); db.flush()
    for i in range(2, n + 1):
        db.add(PasienRencanaTreatment(id_pasien=k.id_pasien, id_treatment=tr.id_treatment,
                                      urutan_sesi=i, nama_tindakan=tr.nama_treatment,
                                      id_kunjungan_pembuat=k.id_kunjungan, status="PENDING"))
    db.flush()
    kt = KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=tr.id_treatment,
                           id_rencana=r1.id_rencana, status_tindakan="SELESAI",
                           waktu_selesai=datetime.now())
    db.add(kt); db.flush()
    return kt


def test_harga_sesi1_series_hanya_menghitung_seriesnya_sendiri(db):
    from decimal import Decimal as D
    from app.db.models import MasterTreatment
    staf, k = _siapkan(db)
    tr = MasterTreatment(nama_treatment="ZZ Laser T4-11", harga=D("500000"), harga_paket=D("400000"),
                         role_pelaksana="Dokter", durasi_menit=30)
    db.add(tr); db.flush()
    kt_a = _series(db, k, tr, 4)
    kt_b = _series(db, k, tr, 2)
    harga = {r.id_kunjungan_tindakan: r.harga for r in
             KasirService(db).get_tagihan(k.id_kunjungan).rincian_tindakan}
    assert harga[kt_a.id_kunjungan_tindakan] == D("1600000")      # 4 × 400.000 (dulu 6 ×)
    assert harga[kt_b.id_kunjungan_tindakan] == D("800000")       # 2 × 400.000 (dulu 6 ×)


def _dua_series(db):
    from decimal import Decimal as D
    from app.db.models import MasterTreatment, PasienRencanaTreatment, TransaksiDetailTindakan, TransaksiKasir
    staf, k = _siapkan(db)
    tr = MasterTreatment(nama_treatment="ZZ Laser T4-11b", harga=D("500000"), harga_paket=D("400000"),
                         role_pelaksana="Dokter", durasi_menit=30)
    db.add(tr); db.flush()
    kt_a = _series(db, k, tr, 3)
    kt_b = _series(db, k, tr, 2)
    t_a = TransaksiKasir(id_kunjungan=k.id_kunjungan, id_pasien=k.id_pasien, id_staf_kasir=staf.id_staf,
                         rincian_tagihan="uji T4-11", subtotal=1200000, nominal_diskon=0,
                         total_tagihan=1200000, status_transaksi="BAYAR", waktu_bayar=datetime.now())
    db.add(t_a); db.flush()
    db.add(TransaksiDetailTindakan(id_transaksi=t_a.id_transaksi, id_kunjungan_tindakan=kt_a.id_kunjungan_tindakan,
                                   id_treatment=tr.id_treatment, qty=1, harga_satuan=1200000,
                                   diskon_item=0, subtotal=1200000))
    db.flush()
    rencana = lambda kt: db.execute(select(PasienRencanaTreatment).where(   # noqa: E731
        PasienRencanaTreatment.id_rencana >= kt.id_rencana).where(
        PasienRencanaTreatment.id_kunjungan_pembuat == k.id_kunjungan).order_by(
        PasienRencanaTreatment.id_rencana)).scalars().all()
    semua = rencana(kt_a)
    a = [r for r in semua if r.id_rencana < kt_b.id_rencana]
    b = [r for r in semua if r.id_rencana >= kt_b.id_rencana]
    return staf, k, kt_a, kt_b, a, b


def test_sesi2_series_belum_dibayar_tidak_lolos_karena_series_lain_lunas(db):
    from app.services.series_service import SeriesService
    _staf, _k, _kt_a, _kt_b, _a, b = _dua_series(db)
    with pytest.raises(HTTPException):                        # dulu: lolos (sesi 1 A lunas)
        SeriesService(db)._pagari_sesi_1_lunas(b[1])


def test_void_hanya_membatalkan_series_yang_ditagih_transaksinya(db, monkeypatch):
    staf, k, _kt_a, kt_b, a, b = _dua_series(db)
    svc = KasirService(db)
    monkeypatch.setattr(svc, "_lingkup_void", lambda trx: {
        "tunggal": False, "resep": set(), "racikan": set(),
        "tindakan": {kt_b.id_kunjungan_tindakan}, "series_pembuat": True})
    trx_b = _trx_terakhir(db, k)
    svc._cancel_series_sesi_pending(trx_b, staf.id_staf, None)
    for r in a + b:
        db.refresh(r)
    assert [V(r.status) for r in a[1:]] == ["PENDING", "PENDING"]   # dulu CANCELLED (sudah lunas)
    assert [V(r.status) for r in b] == ["CANCELLED", "CANCELLED"]


# ---------------------------------------------------------------- K4-1 void hari lampau
# Keputusan dr. Hansen 2026-10-15/16: void hari lampau = UANG KELUAR di tanggal void (seperti
# refund T32), omzet hari asal TIDAK berubah, wajib PIN penyetuju ≠ pemroses. Dulu: transaksi
# hilang dari omzet hari asal (yang sudah ditutup & diekspor), laci hari void tak berkurang.
def _void_lampau_siap(db, nominal_bayar=None):
    from datetime import timedelta
    from app.core.security import hash_password
    from app.db.models import MasterStaf, TransaksiPembayaran
    from app.db.models._enums import StafRoleEnum
    staf, k = _siapkan(db)
    _resep(db, k, staf)
    svc = KasirService(db)
    total = svc.get_tagihan(k.id_kunjungan).ringkasan_biaya.total_tagihan
    svc.proses_bayar(BayarRequest(
        id_kunjungan=k.id_kunjungan, idempotency_key=secrets.token_hex(8),
        pembayaran=[PembayaranItem(metode_bayar="QRIS", nominal=D2(1000)),
                    PembayaranItem(metode_bayar="TUNAI", nominal=(nominal_bayar or total) - D2(1000))]),
        staf.id_staf)
    t = _trx_terakhir(db, k)
    t.waktu_bayar = t.waktu_bayar - timedelta(days=1); db.flush()   # dibayar KEMARIN
    admin = MasterStaf(username=f"uji_vl_a_{secrets.token_hex(3)}", password_hash=hash_password("x"),
                       role=StafRoleEnum.ADMIN, nama_staf="Uji VL Admin", is_active=True)
    sup = MasterStaf(username=f"uji_vl_s_{secrets.token_hex(3)}", password_hash=hash_password("x"),
                     role=StafRoleEnum.SUPERADMIN, nama_staf="Uji VL Sup", is_active=True,
                     pin=hash_password("4321"))
    db.add_all([admin, sup]); db.flush()
    return k, t, total, admin, sup


def D2(x):
    from decimal import Decimal
    return Decimal(str(x))


def _void_lampau(db, t, admin, **kw):
    from app.db.models._enums import StafRoleEnum
    return KasirService(db).force_past_day_void(
        t.id_transaksi, "CUSTOMER_CANCEL", "uji void lampau", [], admin.id_staf,
        StafRoleEnum.ADMIN, **kw)


def test_void_lampau_tanpa_pin_ditolak(db):
    _k, t, _total, admin, _sup = _void_lampau_siap(db)
    with pytest.raises(HTTPException) as e:
        _void_lampau(db, t, admin)
    assert e.value.status_code == 401                 # dulu: diterima tanpa penyetuju


def test_void_lampau_mencatat_uang_keluar_di_tanggal_void(db):
    from datetime import date as _date
    from app.db.models import TransaksiRefund
    _k, t, total, admin, sup = _void_lampau_siap(db, nominal_bayar=None)
    _void_lampau(db, t, admin, id_staf_otorisasi=sup.id_staf, pin_otorisasi="4321")
    rows = db.execute(select(TransaksiRefund).where(
        TransaksiRefund.id_transaksi == t.id_transaksi)).scalars().all()
    assert sorted((r.jenis_refund, r.metode_refund, D2(r.nilai_refund)) for r in rows) == sorted(
        [("VOID", "QRIS", D2(1000)), ("VOID", "TUNAI", D2(total) - D2(1000))])
    assert all(r.tgl_refund.date() == _date.today() and r.id_staf_otorisasi == sup.id_staf
               for r in rows)
    db.refresh(t)
    assert (V(t.status_transaksi), bool(t.late_void)) == ("VOID", True)


def test_void_lampau_uang_keluar_tidak_memuat_kembalian(db):
    from app.db.models import TransaksiPembayaran, TransaksiRefund
    _k, t, total, admin, sup = _void_lampau_siap(db)
    tunai = db.execute(select(TransaksiPembayaran).where(
        TransaksiPembayaran.id_transaksi == t.id_transaksi,
        TransaksiPembayaran.metode_bayar == "TUNAI")).scalar_one()
    tunai.nominal = D2(tunai.nominal) + D2(50000); db.flush()   # bayar lebih, kembali 50rb
    _void_lampau(db, t, admin, id_staf_otorisasi=sup.id_staf, pin_otorisasi="4321")
    keluar = sum(D2(r.nilai_refund) for r in db.execute(select(TransaksiRefund).where(
        TransaksiRefund.id_transaksi == t.id_transaksi)).scalars())
    assert keluar == D2(total)                        # bukan total + kembalian


def test_void_lampau_omzet_hari_asal_tetap_hari_void_berkurang(db):
    from datetime import date as _date, timedelta
    from app.services.reports_service import ReportsService
    _k, t, total, admin, sup = _void_lampau_siap(db)
    rs = ReportsService(db)
    kemarin, hari_ini = _date.today() - timedelta(days=1), _date.today()
    o_kemarin0 = D2(rs.omzet_harian(kemarin).total_omzet)
    o_hari0 = D2(rs.omzet_harian(hari_ini).total_omzet)
    _void_lampau(db, t, admin, id_staf_otorisasi=sup.id_staf, pin_otorisasi="4321")
    assert D2(rs.omzet_harian(kemarin).total_omzet) == o_kemarin0          # dulu turun
    assert D2(rs.omzet_harian(hari_ini).total_omzet) == o_hari0 - D2(total)  # dulu tetap


def test_void_hari_sama_tanpa_uang_keluar(db):
    from app.db.models import TransaksiRefund
    staf, k = _siapkan(db)
    _resep(db, k, staf)
    _bayar(db, k, staf)
    t = _trx_terakhir(db, k)
    KasirService(db).void_transaksi(t.id_transaksi, "SALAH_INPUT", "uji void hari sama", [], staf.id_staf)
    assert db.execute(select(TransaksiRefund).where(
        TransaksiRefund.id_transaksi == t.id_transaksi)).first() is None


def test_migrasi_mengisi_uang_keluar_void_lampau_lama(db):
    """Migrasi 20261016_0200: void hari lampau SEBELUM K4-1 (tanpa baris uang keluar) diberi
    baris VOID dengan alokasi yang sama dengan kode; dijalankan ulang → tidak dobel."""
    import importlib.util, pathlib
    from datetime import timedelta
    from app.db.models import TransaksiPembayaran, TransaksiRefund
    path = pathlib.Path(__file__).parents[2] / "migrations/versions/20261016_0200_uang_keluar_void_lampau.py"
    spec = importlib.util.spec_from_file_location("mig_k41", path)
    mig = importlib.util.module_from_spec(spec); spec.loader.exec_module(mig)
    _k, t, total, _admin, _sup = _void_lampau_siap(db)
    tunai = db.execute(select(TransaksiPembayaran).where(
        TransaksiPembayaran.id_transaksi == t.id_transaksi,
        TransaksiPembayaran.metode_bayar == "TUNAI")).scalar_one()
    tunai.nominal = D2(tunai.nominal) + D2(20000)           # kembalian 20rb
    t.status_transaksi = "VOID"; t.late_void = True          # seperti void lama: tanpa baris
    t.void_at = t.waktu_bayar + timedelta(days=1); t.void_by_id_staf = _admin.id_staf
    db.flush()
    n_trx, n_baris = mig.isi_uang_keluar(db.connection())
    rows = db.execute(select(TransaksiRefund).where(
        TransaksiRefund.id_transaksi == t.id_transaksi)).scalars().all()
    assert sorted((r.metode_refund, D2(r.nilai_refund)) for r in rows) == sorted(
        [("QRIS", D2(1000)), ("TUNAI", D2(total) - D2(1000))])
    assert all(r.jenis_refund == "VOID" and r.tgl_refund == t.void_at for r in rows)
    assert mig.isi_uang_keluar(db.connection())[1] == 0       # jalan ulang: tidak dobel


@pytest.mark.parametrize("geser_hari", [1, 0])        # 1 = hari asal (kemarin), 0 = hari void
def test_void_lampau_semua_pembaca_uang_sepakat(db, geser_hari):
    """Laporan omzet = rekap harian = ekspor Finance = KPI dashboard (basis pembayaran) =
    jumlah per kasir — di hari asal DAN di hari void. 17 saringan di 6 berkas diganti satu
    definisi (`terhitung_omzet`); satu yang terlewat akan membuat angka ini berbeda."""
    from datetime import date as _date, timedelta
    from app.services.dashboard_service import DashboardService
    from app.services.export_service import ExportService
    from app.services.rekap_harian_service import RekapHarianService
    from app.services.reports_service import ReportsService
    _k, t, _total, admin, sup = _void_lampau_siap(db)
    _void_lampau(db, t, admin, id_staf_otorisasi=sup.id_staf, pin_otorisasi="4321")
    hari = _date.today() - timedelta(days=geser_hari)
    rpt = ReportsService(db).omzet_harian(hari)
    rh = RekapHarianService(db).rekap(hari)
    eks = ExportService(db).export_daily_operational_summary(hari, hari)[0]["total_omzet"]
    kpi = DashboardService(db)._kpi_omzet_hari_ini(hari)["value_money"]
    assert D2(rpt.total_omzet) == D2(rh["total_omzet"])
    assert abs(float(rpt.total_omzet) - float(eks)) < 0.01
    assert sum(D2(x.total_omzet) for x in rpt.per_kasir) == D2(rpt.total_omzet)
    assert abs(float(sum(D2(m.total_nominal) for m in rpt.per_metode)) - float(kpi)) < 0.01


def test_layar_void_lampau_meminta_penyetuju_dan_pin(db):
    """Halaman tagihan transaksi KEMARIN: form Force Void memuat pilihan penyetuju (tanpa
    akun yang sedang login) + PIN, dan keterangan "uang dicatat keluar hari ini". Dirender
    lewat aplikasi sungguhan dengan sesi test yang di-rollback (tanpa data tertinggal)."""
    import os, re
    from fastapi.testclient import TestClient
    from app.core.deps import get_db
    from app.main import app
    if not (os.getenv("TEST_USERNAME") and os.getenv("TEST_PASSWORD")):
        pytest.skip("butuh TEST_USERNAME/TEST_PASSWORD")
    k, _t, _total, _admin, sup = _void_lampau_siap(db)

    def _db():
        yield db
    app.dependency_overrides[get_db] = _db
    try:
        c = TestClient(app)
        hal = c.get("/web/login")
        data = {"username": os.environ["TEST_USERNAME"], "password": os.environ["TEST_PASSWORD"]}
        m = re.search(r'name="csrf_token"\s+value="([^"]+)"', hal.text)
        if m:
            data["csrf_token"] = m.group(1)
        c.post("/web/login", data=data)
        r = c.get(f"/web/kasir/tagihan/{k.id_kunjungan}")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    if "force-void-modal" not in r.text:
        pytest.skip("akun uji tidak berhak force void")
    assert 'name="id_staf_otorisasi"' in r.text and 'name="pin_otorisasi"' in r.text
    assert f'value="{sup.id_staf}"' in r.text                 # penyetuju lain ditawarkan
    assert "dicatat KELUAR HARI INI" in r.text


# ---------------------------------------------------------------- K4-2 tukar lalu refund
# Keputusan dr. Hansen 2026-10-15: rantai "tukar lalu uang kembali" dibiarkan (komisi obat
# asal tetap, batas 7 hari mulai ulang dari serah pengganti), TAPI wajib PIN penyetuju ≠
# pemroses — uang keluar atas obat pengganti, yang asalnya sudah pernah dikembalikan sekali.
def _sudah_ditukar(db):
    from app.db.models import KunjunganResep
    from tests.integration.test_retur_pasien import PIN, _produk_y, _retur, _setup
    d = _setup(db)
    y, _ = _produk_y(db, "250000")
    _retur(db, d, jenis="TUKAR", qty=1, metode_refund="TUNAI",
           pengganti=[{"id_produk": y.id_produk, "qty": 1}],
           id_staf_otorisasi=d["admin"].id_staf, pin_otorisasi=PIN)
    ry = db.execute(select(KunjunganResep).where(KunjunganResep.id_produk == y.id_produk)).scalar_one()
    return d, ry


def _retur_pengganti(db, d, ry, **kw):
    from app.services.retur_pasien_service import ReturPasienService
    arg = dict(id_resep=ry.id_resep, jenis="REFUND", alasan_kode="TIDAK_PUAS",
               alasan_teks="uji K4-2", stok_kembali=True, actor_id_staf=d["kasir"].id_staf)
    arg.update(kw)
    return ReturPasienService(db).buat_retur(**arg)


def test_refund_obat_pengganti_tukar_tanpa_pin_ditolak(db):
    d, ry = _sudah_ditukar(db)
    with pytest.raises(HTTPException) as e:
        _retur_pengganti(db, d, ry)
    assert e.value.status_code == 401                     # dulu: diterima tanpa penyetuju
    assert "tukar" in e.value.detail.lower()


def test_refund_obat_pengganti_tukar_dengan_pin_orang_lain(db):
    from app.db.models import TransaksiRefund
    from tests.integration.test_retur_pasien import PIN
    d, ry = _sudah_ditukar(db)
    h = _retur_pengganti(db, d, ry, id_staf_otorisasi=d["admin"].id_staf, pin_otorisasi=PIN)
    assert h["nilai"] == 250000
    ref = db.execute(select(TransaksiRefund).where(TransaksiRefund.id_resep == ry.id_resep)).scalar_one()
    assert ref.id_staf_otorisasi == d["admin"].id_staf


def test_tukar_ulang_obat_pengganti_tidak_butuh_pin(db):
    """Yang diwajibkan PIN hanya UANG kembali; tukar ke produk lain tetap seperti sebelumnya."""
    from tests.integration.test_retur_pasien import _produk_y
    d, ry = _sudah_ditukar(db)
    z, _ = _produk_y(db, "250000")
    h = _retur_pengganti(db, d, ry, jenis="TUKAR", metode_refund="TUNAI",
                         pengganti=[{"id_produk": z.id_produk, "qty": 1}])
    assert h["nilai"] == 250000
