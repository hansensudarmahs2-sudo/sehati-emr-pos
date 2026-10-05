"""
A2 (DEC-079) — REGRESI: transaksi VOID dikecualikan dari agregasi uang.

Strategi NON-DESTRUKTIF: semua tulisan dilakukan di 1 session lalu di-ROLLBACK
di teardown → DB asli tidak berubah. Memakai db_sehati (atau TEST DB).
Pola assert = DELTA: tambah BAYAR → angka naik; tambah VOID → angka TIDAK naik.

Run:
    cd sehati_clinic && .venv/bin/pytest tests/integration/test_kasir_void_exclusion.py -v
"""
import random
import time
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.db.models import (
    KasirClosing,
    Kunjungan,
    KunjunganResep,
    StatusItemResepEnum,
    MasterStaf,
    Pasien,
    TransaksiKasir,
    TransaksiPembayaran,
)
from app.services.kasir_closing_service import KasirClosingService
from app.services.kasir_service import KasirService
from app.services.reports_service import ReportsService


@pytest.fixture
def db():
    """Session non-destruktif — rollback semua di akhir."""
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _first_staf(db):
    st = db.execute(select(MasterStaf).limit(1)).scalars().first()
    if st is None:
        pytest.skip("Tidak ada staf di DB — seed dulu.")
    return st


def _mk_kunjungan(db):
    rm = f"A2T-{int(time.time())}-{random.randint(100, 999)}"
    p = Pasien(no_rm=rm, nama="A2 Test Pasien")
    db.add(p)
    db.flush()
    k = Kunjungan(id_pasien=p.id_pasien, status_antrian="COMPLETED", tgl_kunjungan=datetime.now())
    db.add(k)
    db.flush()
    return k.id_kunjungan


def _mk_trx(db, id_staf, total, status="BAYAR", metode="TUNAI", id_kunjungan=None):
    now = datetime.now()
    trx = TransaksiKasir(
        id_kunjungan=id_kunjungan,
        id_staf_kasir=id_staf,
        rincian_tagihan="A2 regression test",
        subtotal=Decimal(str(total)),
        nominal_diskon=Decimal("0"),
        total_tagihan=Decimal(str(total)),
        waktu_bayar=now,
        status_transaksi=status,
    )
    if status == "VOID":
        trx.void_at = now
    db.add(trx)
    db.flush()
    db.add(TransaksiPembayaran(
        id_transaksi=trx.id_transaksi, metode_bayar=metode, nominal=Decimal(str(total)),
    ))
    db.flush()
    return trx


# =============================================================================
# 1. ReportsService.omzet_harian — exclude VOID
# =============================================================================
def test_omzet_harian_excludes_void(db):
    staf = _first_staf(db)
    today = date.today()
    svc = ReportsService(db)

    base = svc.omzet_harian(today)
    base_omzet = Decimal(str(base.total_omzet))
    base_count = base.total_transaksi

    _mk_trx(db, staf.id_staf, 100000, status="BAYAR")
    after_bayar = svc.omzet_harian(today)
    assert Decimal(str(after_bayar.total_omzet)) == base_omzet + Decimal("100000")
    assert after_bayar.total_transaksi == base_count + 1

    _mk_trx(db, staf.id_staf, 500000, status="VOID")
    after_void = svc.omzet_harian(today)
    # VOID TIDAK boleh menambah omzet maupun count
    assert Decimal(str(after_void.total_omzet)) == base_omzet + Decimal("100000")
    assert after_void.total_transaksi == base_count + 1


# =============================================================================
# 2. KasirService.rekap_shift — exclude VOID (daftar + per-metode)
# =============================================================================
def test_rekap_shift_excludes_void(db):
    staf = _first_staf(db)
    # Anchor shift ke awal hari supaya transaksi test ter-cover.
    staf.waktu_mulai_shift = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    db.flush()
    svc = KasirService(db)

    base = svc.rekap_shift(staf.id_staf)
    base_omzet = Decimal(str(base.total_omzet))
    base_n = base.total_transaksi

    idk = _mk_kunjungan(db)  # rekap_shift.daftar inner-join kunjungan → butuh id_kunjungan
    _mk_trx(db, staf.id_staf, 100000, status="BAYAR", metode="TUNAI", id_kunjungan=idk)
    a = svc.rekap_shift(staf.id_staf)
    assert Decimal(str(a.total_omzet)) == base_omzet + Decimal("100000")
    assert a.total_transaksi == base_n + 1

    idk2 = _mk_kunjungan(db)
    _mk_trx(db, staf.id_staf, 700000, status="VOID", metode="TUNAI", id_kunjungan=idk2)
    b = svc.rekap_shift(staf.id_staf)
    assert Decimal(str(b.total_omzet)) == base_omzet + Decimal("100000")  # VOID diabaikan
    assert b.total_transaksi == base_n + 1


# =============================================================================
# 3. KasirClosingService._penjualan_per_metode — exclude VOID (sudah benar; lock)
# =============================================================================
def _sesi_laci_hari_ini():
    """T28: expected tutup kasir kini milik LACI per TANGGAL (siapa pun pemrosesnya).
    Objek sesi transien — tidak ditulis ke DB; cukup `shift_mulai` untuk tanggalnya."""
    return KasirClosing(shift_mulai=datetime.now(), modal_awal=0, status="OPEN")


def test_closing_penjualan_per_metode_excludes_void(db):
    staf = _first_staf(db)
    svc = KasirClosingService(db)
    sesi = _sesi_laci_hari_ini()

    base = svc._penjualan_per_metode(sesi)
    base_tunai = Decimal(str(base.get("TUNAI", 0)))

    _mk_trx(db, staf.id_staf, 100000, status="BAYAR", metode="TUNAI")
    a = svc._penjualan_per_metode(sesi)
    assert Decimal(str(a.get("TUNAI", 0))) == base_tunai + Decimal("100000")

    _mk_trx(db, staf.id_staf, 700000, status="VOID", metode="TUNAI")
    b = svc._penjualan_per_metode(sesi)
    assert Decimal(str(b.get("TUNAI", 0))) == base_tunai + Decimal("100000")  # VOID diabaikan


# =============================================================================
# 4. void membalikkan stok (_reverse_stok_per_item) — non-destruktif (rollback)
# =============================================================================
def test_void_reverse_stok(db):
    from app.db.models import MasterProduk, TransaksiDetailProduk, Kunjungan

    staf = _first_staf(db)
    produk = db.execute(select(MasterProduk).limit(1)).scalars().first()
    if produk is None:
        pytest.skip("Tidak ada produk di DB.")
    kunjungan = db.query(Kunjungan).first()
    if kunjungan is None:
        pytest.skip("Tidak ada kunjungan di DB.")
    # Task #54 (2026-09-22) — BUKTI PENYERAHAN PER ITEM.
    # Dulu cukup menyetel COMPLETED, mengikuti tebakan "COMPLETED = sudah diserah".
    # Tebakan itu DICABUT #54: kunjungan bisa COMPLETED sementara itemnya belum
    # diserahkan, dan memakainya akan mengembalikan stok yang tidak pernah keluar.
    # _mode_per_item kini menuntut jejak nyata (resep DISERAHKAN); tanpa itu
    # _reverse_stok_per_item menjawab 0 — jawaban yang BENAR.
    kunjungan.status_antrian = "COMPLETED"
    db.flush()
    base_stok = float(produk.stok_terkini or 0)
    db.add(KunjunganResep(
        id_kunjungan=kunjungan.id_kunjungan, id_produk=produk.id_produk, qty=2,
        aturan_pakai="-", status_item=StatusItemResepEnum.DISERAHKAN,
        id_staf_input=staf.id_staf,
    ))
    db.flush()

    trx = _mk_trx(db, staf.id_staf, 50000, status="BAYAR", id_kunjungan=kunjungan.id_kunjungan)
    detail = TransaksiDetailProduk(
        id_transaksi=trx.id_transaksi,
        id_produk=produk.id_produk,
        qty=2,
        harga_satuan=Decimal("25000"),
        subtotal=Decimal("50000"),
    )
    db.add(detail)
    db.flush()

    svc = KasirService(db)
    n = svc._reverse_stok_per_item(trx, [detail.id_detail], staf.id_staf, None)
    db.flush()
    assert n == 1
    # objek produk dimutasi langsung oleh helper → stok naik sebesar qty
    assert float(produk.stok_terkini) == base_stok + 2
    assert detail.void_reverse_stok is True


# =============================================================================
# 5. PARITY — Tutup Kasir preview per-metode == rekap_shift per-metode (BAYAR only)
# =============================================================================
def test_parity_closing_vs_rekap_per_metode(db):
    staf = _first_staf(db)
    staf.waktu_mulai_shift = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    db.flush()
    sejak = staf.waktu_mulai_shift

    closing = KasirClosingService(db)
    kasir = KasirService(db)

    def _tunai_closing():
        return Decimal(str(closing._penjualan_per_metode(_sesi_laci_hari_ini()).get("TUNAI", 0)))

    def _tunai_rekap():
        for m in kasir.rekap_shift(staf.id_staf).per_metode:
            if m.metode_bayar == "TUNAI":
                return Decimal(str(m.total_nominal))
        return Decimal("0")

    # T28 (2026-10-05): angka ABSOLUT tidak lagi sama, dan memang tidak boleh —
    # tutup kasir menghitung SATU LACI (semua petugas di tanggal itu), rekap_shift
    # hanya kasir ini. Yang tetap wajib sama adalah PERUBAHANNYA: transaksi BAYAR
    # menambah keduanya sebesar nilainya, VOID tidak menambah apa pun.
    c0, r0 = _tunai_closing(), _tunai_rekap()

    # Tambah BAYAR 100rb + VOID 700rb (TUNAI)
    _mk_trx(db, staf.id_staf, 100000, status="BAYAR", metode="TUNAI")
    _mk_trx(db, staf.id_staf, 700000, status="VOID", metode="TUNAI")

    c1, r1 = _tunai_closing(), _tunai_rekap()
    assert c1 == c0 + Decimal("100000")   # hanya BAYAR yang dihitung
    assert r1 == r0 + Decimal("100000")   # parity PERUBAHAN; dua-duanya exclude VOID
