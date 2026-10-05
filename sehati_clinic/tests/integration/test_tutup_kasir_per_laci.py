"""
T28 — tutup kasir per LACI per TANGGAL + peringatan uang di luar jendela shift.
Keputusan dr. Hansen 2026-10-05: satu laci, satu shift per hari; uang di luar jam
tetap dihitung + diperingatkan; sesi kedua di hari yang sama ditolak; uang sesudah
tutup hanya diperingatkan (angka tutup kasir tidak diubah).
Rancangan: Project_Memory/DESAIN_T28_TUTUP_KASIR_PER_TANGGAL.md

Non-destruktif: `commit` sesi diganti `flush`, semua di-rollback di akhir.

Kenapa tiap test ada:
- sebelum_buka   : dulu `waktu_bayar >= shift_mulai` membuang uang yang masuk sebelum
                   "Buka Kasir" ditekan — uangnya ada di laci, hitungannya tidak.
- petugas_lain   : dulu hanya pembayaran oleh pembuka sesi yang dihitung — bayar oleh
                   FO/Owner tidak masuk hitungan SIAPA PUN.
- refund         : refund hari ini atas transaksi kemarin mengurangi laci HARI INI.
- satu_sesi      : satu laci = satu sesi terbuka, satu sesi per tanggal.
- sesi_kemarin   : menutup sesi kemarin tidak boleh terhalang antrian HARI INI.
"""
import random
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import (
    KasirClosing, Kunjungan, MasterStaf, Pasien, TransaksiKasir, TransaksiPembayaran,
    TransaksiRefund,
)
from app.db.models._enums import StafRoleEnum
from app.db.session import SessionLocal
from app.services.kasir_closing_service import KasirClosingService


@pytest.fixture
def db():
    s = SessionLocal()
    s.commit = s.flush
    try:
        # Laci harus kosong dari sesi OPEN lain supaya hasilnya tidak bergantung DB.
        if s.execute(select(KasirClosing).where(KasirClosing.status == "OPEN")).first():
            pytest.skip("DB dev sudah punya sesi kasir OPEN — test ini butuh laci kosong.")
        yield s
    finally:
        s.rollback()
        s.close()


def _staf(db, role):
    s = MasterStaf(username=f"uji_t28_{random.randint(10**6, 10**7)}",
                   password_hash=hash_password("x"), role=role,
                   nama_staf=f"Uji T28 {role.value}", is_active=True)
    db.add(s); db.flush()
    return s


def _bayar(db, staf, nominal, waktu, metode="TUNAI"):
    pasien = db.execute(select(Pasien).limit(1)).scalar_one()
    k = Kunjungan(id_pasien=pasien.id_pasien, tgl_kunjungan=waktu, status_antrian="COMPLETED")
    db.add(k); db.flush()
    t = TransaksiKasir(id_kunjungan=k.id_kunjungan, id_pasien=pasien.id_pasien,
                       id_staf_kasir=staf.id_staf, rincian_tagihan="uji T28",
                       subtotal=nominal, nominal_diskon=0, total_tagihan=nominal,
                       status_transaksi="BAYAR", waktu_bayar=waktu)
    db.add(t); db.flush()
    db.add(TransaksiPembayaran(id_transaksi=t.id_transaksi, metode_bayar=metode, nominal=nominal))
    db.flush()
    return t


def _sesi(db, pembuka, shift_mulai):
    s = KasirClosing(id_staf_kasir=pembuka.id_staf, shift_mulai=shift_mulai,
                     status="OPEN", modal_awal=0, id_staf_buka=pembuka.id_staf)
    db.add(s); db.flush()
    return s


def _tunai(svc, sesi):
    return svc.get_closing_preview()["metode"][0]["penjualan_sistem"]


def test_bayar_sebelum_buka_tetap_dihitung_dan_diperingatkan(db):
    kasir = _staf(db, StafRoleEnum.KASIR)
    buka = datetime.now().replace(second=0, microsecond=0)
    if buka.hour < 1:
        pytest.skip("Terlalu dekat tengah malam untuk skenario 'sebelum buka'.")
    svc = KasirClosingService(db)
    sesi = _sesi(db, kasir, buka)
    base = _tunai(svc, sesi)
    t = _bayar(db, kasir, Decimal("250000"), buka - timedelta(minutes=30))
    p = svc.get_closing_preview()
    assert p["metode"][0]["penjualan_sistem"] == base + Decimal("250000")
    assert t.id_transaksi in [x["id_transaksi"] for x in p["sebelum_buka"]]


def test_bayar_oleh_petugas_lain_dihitung(db):
    kasir = _staf(db, StafRoleEnum.KASIR)
    fo = _staf(db, StafRoleEnum.FO)
    svc = KasirClosingService(db)
    sesi = _sesi(db, kasir, datetime.now() - timedelta(minutes=5))
    base = _tunai(svc, sesi)
    _bayar(db, fo, Decimal("120000"), datetime.now())
    p = svc.get_closing_preview()
    assert p["metode"][0]["penjualan_sistem"] == base + Decimal("120000")
    baris_fo = [x for x in p["per_petugas"] if x["id_staf"] == fo.id_staf]
    assert baris_fo and baris_fo[0]["penjualan"] == Decimal("120000")


def test_refund_hari_ini_atas_transaksi_kemarin_mengurangi_laci_hari_ini(db):
    kasir = _staf(db, StafRoleEnum.KASIR)
    svc = KasirClosingService(db)
    sesi = _sesi(db, kasir, datetime.now() - timedelta(minutes=5))
    base = _tunai(svc, sesi)
    t = _bayar(db, kasir, Decimal("300000"), datetime.now() - timedelta(days=1))
    assert _tunai(svc, sesi) == base  # transaksi kemarin bukan laci hari ini
    db.add(TransaksiRefund(id_transaksi=t.id_transaksi, nilai_refund=Decimal("50000"),
                           metode_refund="TUNAI", tgl_refund=datetime.now(),
                           id_staf_refund=kasir.id_staf, alasan="uji T28"))
    db.flush()
    assert _tunai(svc, sesi) == base - Decimal("50000")


def test_satu_laci_satu_sesi(db):
    kasir = _staf(db, StafRoleEnum.KASIR)
    lain = _staf(db, StafRoleEnum.ADMIN)
    svc = KasirClosingService(db)
    svc.buka_kasir(id_staf_kasir=kasir.id_staf, modal_awal=100000)
    with pytest.raises(HTTPException) as e:            # orang lain, laci masih terbuka
        svc.buka_kasir(id_staf_kasir=lain.id_staf, modal_awal=0)
    assert e.value.status_code == 400 and "masih terbuka" in e.value.detail
    sesi = svc.get_open_session()
    sesi.status = "CLOSED"; sesi.shift_tutup = datetime.now(); db.flush()
    with pytest.raises(HTTPException) as e:            # hari ini sudah pernah ada sesi
        svc.buka_kasir(id_staf_kasir=lain.id_staf, modal_awal=0)
    assert e.value.status_code == 400 and "sudah pernah dibuka" in e.value.detail


def test_sesi_kemarin_tidak_terhalang_antrian_hari_ini(db):
    kasir = _staf(db, StafRoleEnum.KASIR)
    svc = KasirClosingService(db)
    _sesi(db, kasir, datetime.now() - timedelta(days=1))
    pasien = db.execute(select(Pasien).limit(1)).scalar_one()
    db.add(Kunjungan(id_pasien=pasien.id_pasien, tgl_kunjungan=datetime.now(),
                     status_antrian="ANTRI_OBAT"))
    db.flush()
    tutup = svc.tutup_kasir(kasir.id_staf, {"TUNAI": 0}, catatan="uji T28 sesi kemarin")
    assert tutup.status == "CLOSED"


def test_bayar_sesudah_tutup_diperingatkan_angka_tidak_berubah(db):
    # Sesi dibuat langsung CLOSED: yang diuji peringatannya, bukan proses tutupnya
    # (DB dev bisa punya antrian hari ini yang — benar — memblokir tutup_kasir).
    kasir = _staf(db, StafRoleEnum.KASIR)
    svc = KasirClosingService(db)
    tutup = _sesi(db, kasir, datetime.now() - timedelta(hours=2))
    tutup.status = "CLOSED"
    tutup.shift_tutup = datetime.now() - timedelta(minutes=10)
    tutup.total_expected = Decimal("0")
    db.flush()
    expected_tutup = tutup.total_expected
    t = _bayar(db, kasir, Decimal("75000"), datetime.now())
    sesudah = svc._pembayaran_di_luar_jendela(tutup, sesudah_tutup=True)
    assert t.id_transaksi in [x["id_transaksi"] for x in sesudah]
    db.refresh(tutup)
    assert tutup.total_expected == expected_tutup
