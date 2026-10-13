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
