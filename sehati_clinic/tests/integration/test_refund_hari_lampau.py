"""
T32 — refund atas transaksi hari lampau: PIN penyetuju + dibukukan di HARI REFUND.
Keputusan dr. Hansen 2026-10-05; rancangan: Project_Memory/DESAIN_T32_REFUND_HARI_LAMPAU.md

Non-destruktif: `refund_item_tertunda` melakukan commit() sendiri (dan audit penolakan
PIN juga), jadi di fixture `commit` sesi diganti `flush`. Semua tulisan tetap di satu
transaksi yang di-rollback di akhir — DB dev tidak berubah.

Yang dijaga (dan kenapa):
- Hari yang sama: kasir sendiri, tanpa PIN — perilaku lama tidak boleh rusak.
- Hari lampau: tanpa PIN / PIN salah / PIN staf berperan Kasir → DITOLAK; penolakan
  tercatat di audit.
- Penyetuju = pemroses → DITOLAK (empat mata).
- Header `total_tagihan` TIDAK berubah. Kalau mutasi lama dikembalikan, laporan akan
  mengurangi refund DUA KALI (migrasi 20261005_0100 sudah memulihkan header lama).
- Omzet hari ASAL tidak bergerak; omzet hari REFUND turun sebesar nilai refund.
- Void transaksi yang punya refund → DITOLAK (kalau tidak: uang keluar dua kali).
"""
import random
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import (
    AuditLog, Kunjungan, KunjunganResep, MasterProduk, MasterStaf, Pasien,
    StatusItemResepEnum, TransaksiDetailProduk, TransaksiKasir, TransaksiRefund,
)
from app.db.models._enums import StafRoleEnum, TipeProdukEnum
from app.db.session import SessionLocal
from app.services.kasir_service import KasirService
from app.services.reports_service import ReportsService

NILAI = Decimal("100000.00")
PIN_ADMIN = "246810"


@pytest.fixture
def db():
    s = SessionLocal()
    s.commit = s.flush  # service commit -> flush; semuanya di-rollback di akhir
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _staf(db, role, pin=None):
    s = MasterStaf(
        username=f"uji_t32_{random.randint(10**6, 10**7)}",
        password_hash=hash_password("tidak-dipakai"),
        role=role, nama_staf=f"Uji T32 {role.value}", is_active=True,
        pin=hash_password(pin) if pin else None,
    )
    db.add(s); db.flush()
    return s


def _setup(db, *, hari_lalu: int):
    """Satu transaksi BAYAR berisi satu obat DIBAYAR (belum diserahkan), Rp 100.000."""
    pasien = db.execute(select(Pasien).limit(1)).scalar_one_or_none()
    if pasien is None:
        pytest.skip("Butuh minimal 1 pasien di DB dev.")
    kasir = _staf(db, StafRoleEnum.KASIR)
    admin = _staf(db, StafRoleEnum.ADMIN, pin=PIN_ADMIN)

    now = KasirService._now_utc7().replace(tzinfo=None)
    waktu_bayar = now - timedelta(days=hari_lalu)

    k = Kunjungan(id_pasien=pasien.id_pasien, tgl_kunjungan=waktu_bayar)
    db.add(k); db.flush()
    p = MasterProduk(
        kode_produk=f"T32{random.randint(10000, 99999)}", nama_produk="Uji Refund T32",
        tipe_produk=TipeProdukEnum.RETAIL, satuan="pcs", default_iterasi=1,
        eligible_member_discount=False, stok_terkini=0,
    )
    db.add(p); db.flush()
    r = KunjunganResep(id_kunjungan=k.id_kunjungan, id_produk=p.id_produk, qty=1,
                       status_item=StatusItemResepEnum.DIBAYAR, id_staf_input=kasir.id_staf)
    db.add(r); db.flush()
    trx = TransaksiKasir(
        id_kunjungan=k.id_kunjungan, id_pasien=pasien.id_pasien, id_staf_kasir=kasir.id_staf,
        rincian_tagihan="uji T32", subtotal=NILAI, nominal_diskon=0, total_tagihan=NILAI,
        status_transaksi="BAYAR", waktu_bayar=waktu_bayar,
    )
    db.add(trx); db.flush()
    db.add(TransaksiDetailProduk(id_transaksi=trx.id_transaksi, id_produk=p.id_produk,
                                 qty=1, harga_satuan=NILAI, subtotal=NILAI, diskon_item=0))
    db.flush()
    return {"kasir": kasir, "admin": admin, "trx": trx, "resep": r,
            "tgl_asal": waktu_bayar.date(), "tgl_refund": now.date()}


def _refund(db, d, actor, **kw):
    return KasirService(db).refund_item_tertunda(
        id_resep=d["resep"].id_resep, alasan="uji T32", metode_refund="TUNAI",
        actor_id_staf=actor.id_staf, **kw)


def _omzet(db, tgl):
    return ReportsService(db).omzet_harian(tgl).total_omzet


# ---------------------------------------------------------------------------
def test_hari_sama_tanpa_pin_diterima(db):
    d = _setup(db, hari_lalu=0)
    hasil = _refund(db, d, d["kasir"])
    assert hasil["status"] == "success"
    ref = db.execute(select(TransaksiRefund).where(
        TransaksiRefund.id_resep == d["resep"].id_resep)).scalar_one()
    assert ref.id_staf_otorisasi is None


def test_hari_lampau_tanpa_pin_ditolak(db):
    d = _setup(db, hari_lalu=1)
    with pytest.raises(HTTPException) as e:
        _refund(db, d, d["kasir"])
    assert e.value.status_code == 401
    assert "PIN" in e.value.detail


def test_hari_lampau_pin_salah_ditolak_dan_diaudit(db):
    d = _setup(db, hari_lalu=1)
    with pytest.raises(HTTPException) as e:
        _refund(db, d, d["kasir"], id_staf_otorisasi=d["admin"].id_staf, pin_otorisasi="000000")
    assert e.value.status_code == 401
    jejak = db.execute(select(AuditLog).where(
        AuditLog.aksi == "REFUND_DITOLAK_PIN",
        AuditLog.id_target == d["trx"].id_transaksi)).scalars().all()
    assert len(jejak) == 1
    assert "000000" not in (jejak[0].keterangan or "")  # PIN tidak pernah ditulis


def test_hari_lampau_pin_staf_kasir_ditolak(db):
    """Kasir lain yang kebetulan punya PIN tetap bukan penyetuju refund."""
    d = _setup(db, hari_lalu=1)
    kasir_lain = _staf(db, StafRoleEnum.KASIR, pin="135790")
    with pytest.raises(HTTPException) as e:
        _refund(db, d, d["kasir"], id_staf_otorisasi=kasir_lain.id_staf, pin_otorisasi="135790")
    assert e.value.status_code == 401


def test_hari_lampau_dokter_bukan_penyetuju(db):
    """Dokter BOLEH mengotorisasi void, TIDAK boleh menyetujui refund (§4.1)."""
    d = _setup(db, hari_lalu=1)
    dokter = _staf(db, StafRoleEnum.DOKTER, pin="112233")
    with pytest.raises(HTTPException) as e:
        _refund(db, d, d["kasir"], id_staf_otorisasi=dokter.id_staf, pin_otorisasi="112233")
    assert e.value.status_code == 401


def test_penyetuju_sama_dengan_pemroses_ditolak(db):
    d = _setup(db, hari_lalu=1)
    with pytest.raises(HTTPException) as e:
        _refund(db, d, d["admin"], id_staf_otorisasi=d["admin"].id_staf, pin_otorisasi=PIN_ADMIN)
    assert e.value.status_code == 400


def test_hari_lampau_pin_admin_diterima_header_utuh(db):
    d = _setup(db, hari_lalu=1)
    hasil = _refund(db, d, d["kasir"], id_staf_otorisasi=d["admin"].id_staf,
                    pin_otorisasi=PIN_ADMIN)
    assert hasil["status"] == "success"
    ref = db.execute(select(TransaksiRefund).where(
        TransaksiRefund.id_resep == d["resep"].id_resep)).scalar_one()
    assert ref.id_staf_otorisasi == d["admin"].id_staf
    db.refresh(d["trx"])
    assert Decimal(str(d["trx"].total_tagihan)) == NILAI, \
        "header TIDAK boleh dikurangi — laporan sudah mengurangi refund per tanggal"


def test_omzet_hari_asal_tetap_hari_refund_turun(db):
    d = _setup(db, hari_lalu=1)
    asal_sebelum = _omzet(db, d["tgl_asal"])
    refund_sebelum = _omzet(db, d["tgl_refund"])
    _refund(db, d, d["kasir"], id_staf_otorisasi=d["admin"].id_staf, pin_otorisasi=PIN_ADMIN)
    assert _omzet(db, d["tgl_asal"]) == asal_sebelum, "hari asal (sudah tutup) berubah"
    assert _omzet(db, d["tgl_refund"]) == refund_sebelum - NILAI
    rpt = ReportsService(db).omzet_harian(d["tgl_refund"])
    assert rpt.total_refund >= NILAI
    # Rincian per kasir & per metode tetap berjumlah sama dengan total.
    assert sum(k.total_omzet for k in rpt.per_kasir) == rpt.total_omzet


def test_void_setelah_refund_ditolak(db):
    d = _setup(db, hari_lalu=0)
    _refund(db, d, d["kasir"])
    with pytest.raises(HTTPException) as e:
        KasirService(db)._pagari_void_sudah_refund(d["trx"])
    assert e.value.status_code == 400
    # Refund obat tertunda tidak punya nomor retur → disebut "refund #<id>".
    assert "pengembalian" in e.value.detail and "refund #" in e.value.detail


def test_void_tanpa_refund_tidak_dihalangi_pagar_ini(db):
    d = _setup(db, hari_lalu=0)
    KasirService(db)._pagari_void_sudah_refund(d["trx"])  # tidak raise
