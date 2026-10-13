"""Audit mendalam tahap 2 (alur klinis) — T2-1, T2-3, T2-4 (2026-10-13).

Memakai `proses_bayar` SEBENARNYA. Project_Memory/AUDIT_MENDALAM_2026-10-13.md.
- T2-1: obat lunas + tagihan susulan untuk tindakan → dulu COMPLETED, obat terdampar.
- T2-3: kunjungan BATAL dulu tetap bisa dibayar dan "hidup lagi".
- T2-4: FO dulu bisa ANTRI_BAYAR → COMPLETED (melewati kasir).
"""
import random
import secrets
from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

from app.core.security import hash_password
from app.db.models import (Kunjungan, KunjunganResep, KunjunganTindakan, MasterProduk,
                           MasterStaf, MasterTreatment)
from app.db.models._enums import GenderEnum, StafRoleEnum, StatusItemResepEnum
from app.db.session import SessionLocal
from app.schemas.kasir import BayarRequest, PembayaranItem
from app.schemas.pasien import PasienBaruRequest
from app.services.kasir_service import KasirService
from app.services.kunjungan_service import KunjunganService
from app.services.pasien_service import PasienService

V = lambda x: getattr(x, "value", x)  # noqa: E731


@pytest.fixture
def db():
    s = SessionLocal()
    s.commit = s.flush
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _siapkan(db, status="ANTRI_BAYAR"):
    staf = MasterStaf(username=f"uji_t2_{random.randint(10**6, 10**7)}",
                      password_hash=hash_password("x"), role=StafRoleEnum.KASIR,
                      nama_staf="Uji T2", is_active=True)
    db.add(staf); db.flush()
    r = PasienService(db).register_pasien_baru(
        PasienBaruRequest(nama=f"ZZ T2 {random.randint(10**6, 10**7)}",
                          jenis_kelamin=GenderEnum.LAKI_LAKI),
        id_staf_fo=staf.id_staf, buat_kunjungan=False)
    k = Kunjungan(id_pasien=r["data"]["id_pasien"], status_antrian=status,
                  id_staf_fo=staf.id_staf, nomor_antrean=999)
    db.add(k); db.flush()
    return staf, k


def _resep(db, k, staf, detik=0):
    p = db.execute(select(MasterProduk).where(MasterProduk.is_active.is_(True))
                   .where(MasterProduk.harga_jual > 0).limit(1)).scalar_one()
    r = KunjunganResep(id_kunjungan=k.id_kunjungan, id_produk=p.id_produk, qty=1,
                       status_item=StatusItemResepEnum.PENDING, id_staf_input=staf.id_staf)
    db.add(r); db.flush()
    if detik:
        r.waktu_input = datetime.now() + timedelta(seconds=detik); db.flush()
    return r


def _tindakan_selesai(db, k, detik=5):
    """`detik` > 0: selesai SESUDAH pembayaran sebelumnya (tagihan susulan, T2-1).
    `detik` < 0: selesai SEBELUM bayar pertama — kalau tidak, kasir menganggapnya baru
    lagi di tagihan susulan dan menagihnya dua kali (artefak test, bukan perilaku klinik)."""
    tr = db.execute(select(MasterTreatment).where(MasterTreatment.harga > 0).limit(1)).scalar_one()
    db.add(KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=tr.id_treatment,
                             status_tindakan="SELESAI",
                             waktu_selesai=datetime.now() + timedelta(seconds=detik)))
    db.flush()


def _bayar(db, k, staf):
    svc = KasirService(db)
    total = svc.get_tagihan(k.id_kunjungan).ringkasan_biaya.total_tagihan
    pemb = [PembayaranItem(metode_bayar="TUNAI", nominal=total)] if total > 0 else []
    svc.proses_bayar(BayarRequest(id_kunjungan=k.id_kunjungan, pembayaran=pemb,
                                  idempotency_key=secrets.token_hex(8)), staf.id_staf)
    db.refresh(k)


# ---------------------------------------------------------------- T2-1
def test_susulan_tindakan_tidak_menelantarkan_obat_lunas(db):
    staf, k = _siapkan(db)
    r1 = _resep(db, k, staf)
    _bayar(db, k, staf)
    assert k.status_antrian == "ANTRI_OBAT"
    _tindakan_selesai(db, k)
    k.status_antrian = "ANTRI_BAYAR"; db.flush()     # dokter tambah tindakan, perawat selesai
    _bayar(db, k, staf)                              # tagihan susulan: tindakan saja
    db.refresh(r1)
    assert V(r1.status_item) == "DIBAYAR"
    assert k.status_antrian == "ANTRI_OBAT"          # dulu COMPLETED → obat terdampar


def test_susulan_di_jalur_obat_tertunda_tetap_completed(db):
    """Sisa obat tertunda SENGAJA DIBAYAR + COMPLETED + tgl_janji_kirim (diurus modul
    Obat Tertunda) — perbaikan T2-1 tidak boleh menariknya kembali ke antrian apotek."""
    staf, k = _siapkan(db)
    _resep(db, k, staf)
    _bayar(db, k, staf)
    k.tgl_janji_kirim = date.today() + timedelta(days=3)
    _tindakan_selesai(db, k)
    k.status_antrian = "ANTRI_BAYAR"; db.flush()
    _bayar(db, k, staf)
    assert k.status_antrian == "COMPLETED"


def test_tanpa_obat_tetap_completed(db):
    staf, k = _siapkan(db)
    _tindakan_selesai(db, k)
    _bayar(db, k, staf)
    assert k.status_antrian == "COMPLETED"


# ---------------------------------------------------------------- T2-3
def test_kunjungan_batal_tidak_bisa_dibayar(db):
    staf, k = _siapkan(db)
    _resep(db, k, staf)
    k.status_antrian = "BATAL"; db.flush()
    with pytest.raises(HTTPException) as e:
        _bayar(db, k, staf)
    assert e.value.status_code == 400 and "DIBATALKAN" in e.value.detail


def test_pagar_batal_membaca_status_segar_bukan_salinan_di_sesi(db):
    """Objek kunjungan di sesi masih 'ANTRI_BAYAR' sementara DB sudah BATAL (dibatalkan
    orang lain). Tanpa populate_existing di kunci, pagar membaca salinan lama dan lolos."""
    staf, k = _siapkan(db)
    _resep(db, k, staf)
    db.execute(text("UPDATE kunjungan SET status_antrian='BATAL' WHERE id_kunjungan=:i"),
               {"i": k.id_kunjungan})
    assert k.status_antrian == "ANTRI_BAYAR"          # salinan di sesi masih lama
    with pytest.raises(HTTPException) as e:
        _bayar(db, k, staf)
    assert "DIBATALKAN" in e.value.detail


# ---------------------------------------------------------------- T2-4
def test_fo_tidak_bisa_melewati_kasir(db):
    staf, k = _siapkan(db, "ANTRI_BAYAR")
    with pytest.raises(HTTPException) as e:
        KunjunganService(db).ubah_status(k.id_kunjungan, "COMPLETED", actor_id_staf=staf.id_staf)
    assert e.value.status_code == 400


def test_menu_ubah_diturunkan_dari_satu_sumber():
    from app.services.kunjungan_service import _VALID_TRANSITIONS
    from app.web.routes.kunjungan import VALID_TRANSITIONS
    assert "COMPLETED" not in VALID_TRANSITIONS["ANTRI_BAYAR"]
    for asal, tujuan in VALID_TRANSITIONS.items():
        assert set(tujuan) == _VALID_TRANSITIONS[asal]


# ---------------------------------------------------------------- T2-2
# Split billing: T1 (resep A) + tagihan susulan T2 (resep B) di SATU kunjungan.
# Dulu void memilih per kunjungan: void T2 membatalkan obat T1 juga.
def _void(db, trx_id, staf):
    KasirService(db).void_transaksi(trx_id, "SALAH_INPUT", "uji T2-2", [], staf.id_staf)


def _trx_terakhir(db, k):
    from app.db.models import TransaksiKasir
    return db.execute(select(TransaksiKasir).where(TransaksiKasir.id_kunjungan == k.id_kunjungan)
                      .order_by(TransaksiKasir.id_transaksi.desc())).scalars().first()


def _split(db):
    staf, k = _siapkan(db)
    ra = _resep(db, k, staf)
    _bayar(db, k, staf)
    t1 = _trx_terakhir(db, k)
    rb = _resep(db, k, staf, detik=5)              # ditambah SESUDAH bayar 1
    k.status_antrian = "ANTRI_BAYAR"; db.flush()
    _bayar(db, k, staf)
    t2 = _trx_terakhir(db, k)
    return staf, k, ra, rb, t1, t2


def test_bayar_mencatat_transaksi_di_resep(db):
    staf, k, ra, rb, t1, t2 = _split(db)
    db.refresh(ra); db.refresh(rb)
    assert (ra.id_transaksi, rb.id_transaksi) == (t1.id_transaksi, t2.id_transaksi)


def test_void_t2_tidak_membatalkan_obat_t1(db):
    staf, k, ra, rb, t1, t2 = _split(db)
    _void(db, t2.id_transaksi, staf)
    db.refresh(ra); db.refresh(rb); db.refresh(k)
    assert (V(ra.status_item), V(rb.status_item)) == ("DIBAYAR", "BATAL")
    assert k.status_antrian == "ANTRI_OBAT"        # obat T1 masih menunggu diserahkan


def test_void_t1_tidak_membatalkan_obat_t2(db):
    staf, k, ra, rb, t1, t2 = _split(db)
    _void(db, t1.id_transaksi, staf)
    db.refresh(ra); db.refresh(rb)
    assert (V(ra.status_item), V(rb.status_item)) == ("BATAL", "DIBAYAR")


def test_tindakan_selesai_di_t1_tidak_menghalangi_void_t2_berisi_obat(db):
    staf, k = _siapkan(db)
    _tindakan_selesai(db, k, detik=-60)
    _bayar(db, k, staf)                            # T1: tindakan (snapshot F3 ditulis)
    rb = _resep(db, k, staf, detik=10)
    k.status_antrian = "ANTRI_BAYAR"; db.flush()
    _bayar(db, k, staf)                            # T2: obat saja
    _void(db, _trx_terakhir(db, k).id_transaksi, staf)   # dulu 400: "tindakan sudah selesai"
    db.refresh(rb)
    assert V(rb.status_item) == "BATAL"


def test_data_lama_ambigu_void_ditolak_tanpa_perubahan(db):
    staf, k, ra, rb, t1, t2 = _split(db)
    ra.id_transaksi = None; db.flush()             # = baris lama tanpa penanda
    with pytest.raises(HTTPException) as e:
        _void(db, t2.id_transaksi, staf)
    assert e.value.status_code == 409
    db.refresh(t2); db.refresh(rb)
    assert t2.status_transaksi == "BAYAR" and V(rb.status_item) == "DIBAYAR"


def test_satu_transaksi_perilaku_lama_utuh(db):
    staf, k = _siapkan(db)
    r = _resep(db, k, staf)
    _bayar(db, k, staf)
    r.id_transaksi = None; db.flush()              # data lama: tetap bisa di-void
    _void(db, _trx_terakhir(db, k).id_transaksi, staf)
    db.refresh(r); db.refresh(k)
    assert V(r.status_item) == "BATAL" and k.status_antrian == "COMPLETED"


# ---------------------------------------------------------------- T2-5
# Pembatalan kunjungan. Dulu BATAL hanya mengubah status: kuota hilang, sesi series
# tersangkut, kunjungan yang sudah dibayar pun bisa dibatalkan (obat terdampar).
def _batal(db, k, staf):
    KunjunganService(db).ubah_status(k.id_kunjungan, "BATAL", actor_id_staf=staf.id_staf,
                                     catatan_batal="uji T2-5")
    db.refresh(k)


def _kuota_terpakai(db, k):
    from app.db.models import MasterMembership, PasienMembershipHistory, PasienMembershipKuota
    m = db.execute(select(MasterMembership).limit(1)).scalar_one()
    h = PasienMembershipHistory(id_pasien=k.id_pasien, id_membership=m.id_membership,
                                tgl_aktif=date.today(), tgl_expired=date.today() + timedelta(days=30),
                                harga_bayar=0, is_active=True, status_aktivasi="ACTIVE")
    db.add(h); db.flush()
    tr = db.execute(select(MasterTreatment).limit(1)).scalar_one()
    q = PasienMembershipKuota(id_pasien=k.id_pasien, id_membership_history=h.id_history,
                              id_treatment=tr.id_treatment, periode_kuota="TOTAL_PAKET",
                              kuota_total=3, kuota_terpakai=1, is_active=True,
                              expired_at=datetime.now() + timedelta(days=30))
    db.add(q); db.flush()
    db.add(KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=tr.id_treatment,
                             id_kuota_member=q.id_kuota, status_tindakan="PENDING"))
    db.flush()
    return q


def _rencana(db, k, urutan, pembuat, status):
    from app.db.models import PasienRencanaTreatment
    tr = db.execute(select(MasterTreatment).limit(1)).scalar_one()
    r = PasienRencanaTreatment(id_pasien=k.id_pasien, id_treatment=tr.id_treatment,
                               urutan_sesi=urutan, nama_tindakan="Uji Series",
                               id_kunjungan_pembuat=pembuat, status=status)
    db.add(r); db.flush()
    return r


def test_batal_ditolak_bila_sudah_dibayar(db):
    staf, k = _siapkan(db)
    _resep(db, k, staf)
    _bayar(db, k, staf)                               # ANTRI_OBAT, obat lunas
    with pytest.raises(HTTPException) as e:
        _batal(db, k, staf)
    assert e.value.status_code == 409 and "VOID" in e.value.detail


def test_batal_ditolak_bila_tindakan_sudah_selesai(db):
    staf, k = _siapkan(db, "ANTRI_BAYAR")
    _tindakan_selesai(db, k, detik=-60)
    with pytest.raises(HTTPException) as e:
        _batal(db, k, staf)
    assert e.value.status_code == 409 and "SELESAI" in e.value.detail


def test_batal_mengembalikan_kuota(db):
    staf, k = _siapkan(db, "ANTRI_TREATMENT")
    q = _kuota_terpakai(db, k)
    _batal(db, k, staf)
    db.refresh(q)
    assert k.status_antrian == "BATAL" and q.kuota_terpakai == 0


def test_batal_series_lahir_dibatalkan_yang_dijadwalkan_kembali(db):
    staf, k = _siapkan(db, "ANTRI_TREATMENT")
    _, lama = _siapkan(db, "COMPLETED")
    lahir = _rencana(db, k, 2, k.id_kunjungan, "PENDING")         # series dibuat di sini
    jadwal = _rencana(db, k, 3, lama.id_kunjungan, "SCHEDULED")   # sesi series lain, dipakai di sini
    db.add(KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=jadwal.id_treatment,
                             id_rencana=jadwal.id_rencana, status_tindakan="PENDING"))
    db.flush()
    _batal(db, k, staf)
    db.refresh(lahir); db.refresh(jadwal)
    assert (V(lahir.status), V(jadwal.status)) == ("CANCELLED", "PENDING")


def test_selesai_lewat_menu_ditolak_bila_obat_lunas_belum_diserahkan(db):
    staf, k = _siapkan(db)
    _resep(db, k, staf)
    _bayar(db, k, staf)
    with pytest.raises(HTTPException) as e:
        KunjunganService(db).ubah_status(k.id_kunjungan, "COMPLETED", actor_id_staf=staf.id_staf)
    assert e.value.status_code == 409 and "LUNAS" in e.value.detail


def test_selesai_lewat_menu_boleh_di_jalur_obat_tertunda(db):
    staf, k = _siapkan(db)
    _resep(db, k, staf)
    _bayar(db, k, staf)
    k.tgl_janji_kirim = date.today() + timedelta(days=2); db.flush()
    KunjunganService(db).ubah_status(k.id_kunjungan, "COMPLETED", actor_id_staf=staf.id_staf)
    db.refresh(k)
    assert k.status_antrian == "COMPLETED"


# ---------------------------------------------------------------- T2-6
# Harga paket series ditagih bersama SESI 1; sesi 2..N Rp 0. Dulu sesi 2..N bisa dipakai
# walau sesi 1 belum dibayar → series gratis.
def _series(db, staf, k):
    """Bentuk persis seperti `PemeriksaanService` saat SOAP: rencana sesi 1 SCHEDULED +
    tindakannya (di sini sudah SELESAI), rencana sesi 2 PENDING."""
    from app.db.models import PasienRencanaTreatment
    tr = db.execute(select(MasterTreatment).where(MasterTreatment.harga > 0).limit(1)).scalar_one()
    s1 = PasienRencanaTreatment(id_pasien=k.id_pasien, id_treatment=tr.id_treatment, urutan_sesi=1,
                                nama_tindakan="Uji Series", id_kunjungan_pembuat=k.id_kunjungan,
                                status="SCHEDULED")
    s2 = PasienRencanaTreatment(id_pasien=k.id_pasien, id_treatment=tr.id_treatment, urutan_sesi=2,
                                nama_tindakan="Uji Series", id_kunjungan_pembuat=k.id_kunjungan,
                                status="PENDING")
    db.add_all([s1, s2]); db.flush()
    db.add(KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=tr.id_treatment,
                             id_rencana=s1.id_rencana, status_tindakan="SELESAI",
                             waktu_selesai=datetime.now() - timedelta(seconds=60)))
    db.flush()
    return s2


def _kunjungan_baru(db, k, staf):
    k2 = Kunjungan(id_pasien=k.id_pasien, status_antrian="ANTRI_KONSULTASI",
                   id_staf_fo=staf.id_staf, nomor_antrean=998)
    db.add(k2); db.flush()
    return k2


def test_sesi_2_ditolak_bila_sesi_1_belum_dibayar(db):
    from app.services.series_service import SeriesService
    staf, k = _siapkan(db)
    s2 = _series(db, staf, k)
    k2 = _kunjungan_baru(db, k, staf)
    with pytest.raises(HTTPException) as e:
        SeriesService(db).use_session(s2.id_rencana, k2.id_kunjungan, staf.id_staf)
    assert e.value.status_code == 409 and "SESI 1" in e.value.detail


def test_sesi_2_boleh_sesudah_sesi_1_dibayar(db):
    from app.services.series_service import SeriesService
    staf, k = _siapkan(db)
    s2 = _series(db, staf, k)
    _bayar(db, k, staf)                               # menagih sesi 1 (snapshot tindakan)
    k2 = _kunjungan_baru(db, k, staf)
    SeriesService(db).use_session(s2.id_rencana, k2.id_kunjungan, staf.id_staf)
    db.refresh(s2)
    assert V(s2.status) == "SCHEDULED"


def test_sesi_2_ditolak_bila_transaksi_sesi_1_sudah_void(db):
    """Transaksi sesi 1 yang VOID bukan bukti lunas. Void biasa menolak tindakan SELESAI,
    jadi keadaan ini jarang — tapi pagar tidak boleh bergantung pada pagar lain (suntikan
    "abaikan status BAYAR" sempat LOLOS sebelum test ini ditambahkan)."""
    from app.services.series_service import SeriesService
    staf, k = _siapkan(db)
    s2 = _series(db, staf, k)
    _bayar(db, k, staf)
    _trx_terakhir(db, k).status_transaksi = "VOID"; db.flush()
    k2 = _kunjungan_baru(db, k, staf)
    with pytest.raises(HTTPException) as e:
        SeriesService(db).use_session(s2.id_rencana, k2.id_kunjungan, staf.id_staf)
    assert e.value.status_code == 409


# ---------------------------------------------------------------- T2-7
# Penanda "sudah ditebus" dulu = ADA salinan, apa pun statusnya → salinan yang ditunda /
# di-void / kunjungannya batal menyembunyikan resep asli selamanya.
def _tebus_setup(db, status_salinan, status_kunj_tebus="ANTRI_BAYAR"):
    staf, k = _siapkan(db, "COMPLETED")
    asal = _resep(db, k, staf)                       # PENDING: pasien pulang tanpa bayar
    k2 = Kunjungan(id_pasien=k.id_pasien, status_antrian=status_kunj_tebus,
                   id_staf_fo=staf.id_staf, nomor_antrean=997)
    db.add(k2); db.flush()
    db.add(KunjunganResep(id_kunjungan=k2.id_kunjungan, id_produk=asal.id_produk, qty=1,
                          status_item=status_salinan, id_staf_input=staf.id_staf,
                          id_resep_asal=asal.id_resep))
    db.flush()
    return k, asal


def _ditawarkan(db, k, asal):
    from app.services.apotek_service import ApotekService
    rows = ApotekService(db).list_resep_belum_ditebus(k.id_pasien)
    return any((r.get("id_resep") if isinstance(r, dict) else getattr(r, "id_resep", None))
               == asal.id_resep for r in rows)


@pytest.mark.parametrize("status_salinan, kunj, ditawarkan", [
    ("PENDING", "ANTRI_BAYAR", False),   # sedang ditebus → disembunyikan (anti tebus ganda)
    ("DIBAYAR", "ANTRI_OBAT", False),
    ("DISERAHKAN", "COMPLETED", False),
    ("DITUNDA", "COMPLETED", True),      # dulu: hilang selamanya
    ("BATAL", "COMPLETED", True),        # dulu: hilang selamanya
    ("PENDING", "BATAL", True),          # kunjungan tebus dibatalkan — dulu hilang
])
def test_penanda_tebus_hanya_salinan_hidup(db, status_salinan, kunj, ditawarkan):
    k, asal = _tebus_setup(db, status_salinan, kunj)
    assert _ditawarkan(db, k, asal) is ditawarkan


@pytest.mark.parametrize("status_salinan, ditawarkan", [("PENDING", False), ("DITUNDA", True)])
def test_penanda_tebus_racikan_sama(db, status_salinan, ditawarkan):
    """Racikan memakai definisi yang SAMA (app/services/_tebus.py) — termasuk penyalinnya."""
    from app.db.models.racikan import KunjunganRacikan
    from app.services.apotek_service import ApotekService
    from app.services.racikan_service import RacikanService
    staf, k = _siapkan(db, "COMPLETED")
    asal = KunjunganRacikan(id_kunjungan=k.id_kunjungan, nama_snapshot="ZZ Racik Asal",
                            jenis_racik="PUYER", jumlah_unit=10, status_item="PENDING")
    db.add(asal); db.flush()
    k2 = Kunjungan(id_pasien=k.id_pasien, status_antrian="COMPLETED",
                   id_staf_fo=staf.id_staf, nomor_antrean=996)
    db.add(k2); db.flush()
    db.add(KunjunganRacikan(id_kunjungan=k2.id_kunjungan, nama_snapshot="ZZ Racik Salinan",
                            jenis_racik="PUYER", jumlah_unit=10, status_item=status_salinan,
                            id_kunjungan_racikan_asal=asal.id_kunjungan_racikan))
    db.flush()
    rows = ApotekService(db).list_racikan_belum_ditebus(k.id_pasien)
    ids = [(r.get("id_kunjungan_racikan") if isinstance(r, dict) else None) for r in rows]
    assert (asal.id_kunjungan_racikan in ids) is ditawarkan
    from app.services._tebus import racikan_sudah_ditebus
    assert racikan_sudah_ditebus(db, asal.id_kunjungan_racikan) is (not ditawarkan)


# ---------------------------------------------------------------- T2-8
# Tebus resep dulu menyalin baris lama TANPA pemeriksaan (racikan sudah diperiksa).
def _pagar_tebus(db, model, id_baris, id_pasien):
    from app.web.routes.apotek import _asal_tebus_atau_tolak
    return _asal_tebus_atau_tolak(db, model, id_baris, id_pasien)


def test_tebus_resep_sah_diterima(db):
    staf, k = _siapkan(db, "COMPLETED")
    r = _resep(db, k, staf)
    assert _pagar_tebus(db, KunjunganResep, r.id_resep, k.id_pasien) is r


def test_tebus_resep_pasien_lain_ditolak(db):
    staf, k = _siapkan(db, "COMPLETED")
    _, k_lain = _siapkan(db, "COMPLETED")
    r = _resep(db, k, staf)
    assert "bukan resep pasien ini" in _pagar_tebus(db, KunjunganResep, r.id_resep, k_lain.id_pasien)


def test_tebus_resep_yang_sudah_dibayar_ditolak(db):
    staf, k = _siapkan(db, "COMPLETED")
    r = _resep(db, k, staf)
    r.status_item = StatusItemResepEnum.DIBAYAR; db.flush()
    assert "sudah DIBAYAR" in _pagar_tebus(db, KunjunganResep, r.id_resep, k.id_pasien)


def test_tebus_ganda_ditolak(db):
    """Klik ganda / dua apoteker: permintaan kedua melihat salinan permintaan pertama."""
    k, asal = _tebus_setup(db, "PENDING")
    assert "sedang/sudah ditebus" in _pagar_tebus(db, KunjunganResep, asal.id_resep, k.id_pasien)


def test_tebus_racikan_pasien_lain_ditolak(db):
    from app.db.models.racikan import KunjunganRacikan
    staf, k = _siapkan(db, "COMPLETED")
    _, k_lain = _siapkan(db, "COMPLETED")
    rc = KunjunganRacikan(id_kunjungan=k.id_kunjungan, nama_snapshot="ZZ Racik",
                          jenis_racik="PUYER", jumlah_unit=10, status_item="PENDING")
    db.add(rc); db.flush()
    assert "bukan resep pasien ini" in _pagar_tebus(db, KunjunganRacikan, rc.id_kunjungan_racikan,
                                                     k_lain.id_pasien)


def test_route_tebus_memanggil_pagar_untuk_resep_dan_racikan():
    """Test di atas menguji PAGARNYA; ini menjaga route tetap memanggilnya (uji lewat route
    sungguhan akan commit ke DB dev). Lemah tapi jujur: menangkap pagar yang dicabut."""
    import inspect
    from app.web.routes import apotek
    src = inspect.getsource(apotek.apotek_tebus_resep_simpan)
    assert src.count("_asal_tebus_atau_tolak(") == 2
    assert "db.get(KunjunganResep, _rid)" not in src


# ---------------------------------------------------------------- T2-9
# Halaman SOAP basi: kartu ber-id racikan yang SUDAH dibayar/ditunda dulu dianggap kartu
# BARU → racikan PENDING kembar → ditagih lagi sebagai susulan.
def _kartu_racik(id_kr, pid, nama="ZZ Racik Basi"):
    return {"id_kunjungan_racikan": id_kr, "id_racikan": None, "nama": nama,
            "jenis_racik": "KAPSUL", "jumlah_unit": 10, "aturan_pakai": "uji",
            "bahan": [{"id_produk": pid, "dosis": 10, "satuan": "mg"}]}


@pytest.mark.parametrize("status_sekarang", ["DIBAYAR", "DITUNDA"])
def test_kartu_basi_racikan_yang_sudah_diproses_dilewati(db, status_sekarang):
    from app.db.models.racikan import KunjunganRacikan
    from app.services.racikan_service import RacikanService
    pid = db.execute(text("SELECT id_produk FROM master_produk WHERE is_active=1 AND harga_jual>0 "
                          "AND kekuatan_nilai IS NOT NULL LIMIT 1")).scalar()
    staf, k = _siapkan(db, "ANTRI_OBAT")
    svc = RacikanService(db)
    svc.save_kunjungan_racikan(k.id_kunjungan, [_kartu_racik(None, pid)], loaded_ids=[])
    rc = db.execute(select(KunjunganRacikan).where(KunjunganRacikan.id_kunjungan == k.id_kunjungan)
                    ).scalar_one()
    loaded = [rc.id_kunjungan_racikan]                     # halaman dimuat saat masih PENDING
    rc.status_item = status_sekarang; db.flush()           # lalu kasir membayar / menunda
    hasil = svc.save_kunjungan_racikan(k.id_kunjungan, [_kartu_racik(rc.id_kunjungan_racikan, pid)],
                                       loaded_ids=loaded)  # dokter menyimpan halaman basi
    n = db.execute(select(KunjunganRacikan).where(KunjunganRacikan.id_kunjungan == k.id_kunjungan)
                   ).scalars().all()
    assert len(n) == 1                                    # dulu: lahir baris PENDING kembar
    assert hasil["sudah_diproses"] == ["ZZ Racik Basi"] and hasil["baru"] == 0


# ---------------------------------------------------------------- T2-10
# Menyetujui draf apoteker = menjadi PENULIS catatan medis. Dulu Admin lolos.
@pytest.mark.parametrize("role, boleh", [
    ("Dokter", True), ("Superadmin", True), ("Owner", True),   # Superadmin = akun dr. Hansen
    ("Admin", False), ("Apoteker", False), ("Kasir", False),
])
def test_siapa_boleh_menyetujui_draf(role, boleh):
    from types import SimpleNamespace
    from app.web.routes.dokter import bisa_menyetujui_draf
    assert bisa_menyetujui_draf(SimpleNamespace(role=role)) is boleh


def test_route_setujui_memeriksa_role_sebelum_menyentuh_draf():
    import inspect
    from app.web.routes import dokter
    src = inspect.getsource(dokter.dokter_draf_soap_setujui)
    assert src.index("bisa_menyetujui_draf(user)") < src.index("db.get(PemeriksaanKlinis")


# ---------------------------------------------------------------- T2-11
# Upsell perawat = penulis kedua kunjungan_tindakan. Dulu: tanpa kuota, tanpa batas reopen.
def _treatment_tanpa_otorisasi(db):
    return db.execute(select(MasterTreatment).where(MasterTreatment.harga > 0)
                      .where((MasterTreatment.butuh_otorisasi.is_(None))
                             | (MasterTreatment.butuh_otorisasi.is_(False))).limit(1)).scalar_one()


def _kuota_untuk(db, k, tr, terpakai=0):
    from app.db.models import MasterMembership, PasienMembershipHistory, PasienMembershipKuota
    m = db.execute(select(MasterMembership).limit(1)).scalar_one()
    h = PasienMembershipHistory(id_pasien=k.id_pasien, id_membership=m.id_membership,
                                tgl_aktif=date.today(), tgl_expired=date.today() + timedelta(days=30),
                                harga_bayar=0, is_active=True, status_aktivasi="ACTIVE",
                                id_transaksi_aktivasi=None)
    db.add(h); db.flush()
    q = PasienMembershipKuota(id_pasien=k.id_pasien, id_membership_history=h.id_history,
                              id_treatment=tr.id_treatment, periode_kuota="TOTAL_PAKET",
                              kuota_total=3, kuota_terpakai=terpakai, is_active=True,
                              expired_at=datetime.now() + timedelta(days=30))
    db.add(q); db.flush()
    return q


def _upsell(db, k, staf, tr):
    from app.schemas.treatment import UpsellRequest
    from app.services.upsell_service import UpsellService
    return UpsellService(db).submit_upsell(
        UpsellRequest(id_kunjungan=k.id_kunjungan, tipe_item="TREATMENT", id_item=tr.id_treatment),
        staf.id_staf)


def test_upsell_memakai_kuota_lewat_jalur_yang_sama_dengan_soap(db, monkeypatch):
    """Upsell harus memanggil SATU fungsi kuota yang sama dengan SOAP dokter."""
    from app.services.membership_service import MembershipService
    dipanggil = {}
    def palsu(self, **kw):
        dipanggil.update(kw)
        return None
    monkeypatch.setattr(MembershipService, "pakai_kuota_bila_ada", palsu)
    staf, k = _siapkan(db, "ON_TREATMENT")
    tr = _treatment_tanpa_otorisasi(db)
    _upsell(db, k, staf, tr)
    assert dipanggil.get("id_treatment") == tr.id_treatment
    assert dipanggil.get("id_kunjungan") == k.id_kunjungan


def test_upsell_ditolak_sesudah_dua_transaksi(db):
    from app.db.models import TransaksiKasir
    staf, k = _siapkan(db, "ON_TREATMENT")
    for _ in range(2):
        db.add(TransaksiKasir(id_kunjungan=k.id_kunjungan, id_pasien=k.id_pasien,
                              id_staf_kasir=staf.id_staf, rincian_tagihan="uji", subtotal=0,
                              nominal_diskon=0, total_tagihan=0, status_transaksi="BAYAR"))
    db.flush()
    with pytest.raises(HTTPException) as e:
        _upsell(db, k, staf, _treatment_tanpa_otorisasi(db))
    assert e.value.status_code == 400 and "2x dibayar" in e.value.detail


def test_pakai_kuota_bila_ada_menaikkan_terpakai(db):
    """Fungsi bersama: kuota tersedia → id_kuota dikembalikan, terpakai naik 1."""
    from app.services.membership_service import MembershipService
    staf, k = _siapkan(db, "ON_TREATMENT")
    tr = _treatment_tanpa_otorisasi(db)
    q = _kuota_untuk(db, k, tr)
    from unittest import mock
    with mock.patch.object(MembershipService, "get_or_create_kuota_for_treatment",
                           return_value={"id_kuota": q.id_kuota, "sisa": 3}):
        hasil = MembershipService(db).pakai_kuota_bila_ada(
            id_pasien=k.id_pasien, id_treatment=tr.id_treatment, actor_id_staf=staf.id_staf,
            id_kunjungan=k.id_kunjungan)
    db.refresh(q)
    assert hasil == q.id_kuota and q.kuota_terpakai == 1


def test_soap_dokter_memakai_fungsi_kuota_bersama():
    """Jalur SOAP dokter tak punya test kuota sendiri (input_medis_lengkap) — logikanya
    dipindah ke pakai_kuota_bila_ada (Audit T2-11). Ini menjaga tidak ada yang menulis
    ulang logika kuota di sana lagi (dua penulis = dua perilaku, §4.1)."""
    import inspect
    from app.services import pemeriksaan_service
    src = inspect.getsource(pemeriksaan_service.PemeriksaanService)
    assert "pakai_kuota_bila_ada(" in src
    assert "increment_kuota_terpakai(" not in src
