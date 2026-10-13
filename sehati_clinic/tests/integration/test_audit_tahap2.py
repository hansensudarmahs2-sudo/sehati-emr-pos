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


def _tindakan_selesai(db, k):
    tr = db.execute(select(MasterTreatment).where(MasterTreatment.harga > 0).limit(1)).scalar_one()
    db.add(KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=tr.id_treatment,
                             status_tindakan="SELESAI",
                             waktu_selesai=datetime.now() + timedelta(seconds=5)))
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
