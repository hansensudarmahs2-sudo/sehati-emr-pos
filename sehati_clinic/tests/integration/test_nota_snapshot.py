"""
T27 — nota dari yang DITAGIH (snapshot transaksi_detail_*), tindakan kuota sebagai
benefit prabayar. Keputusan dr. Hansen 2026-10-05; DESAIN_T27_NOTA_DARI_SNAPSHOT.md

Non-destruktif: `commit` sesi diganti `flush`, semua di-rollback.

Yang dijaga:
- tindakan kuota tercetak Rp 0 + "Benefit <tier> (prabayar) · nilai normal", BUKAN
  baris Rp 500.000 dengan total Rp 0;
- harga master naik sesudah bayar → nota lama TIDAK berubah;
- data sebelum F3 (tak ada snapshot tindakan di kunjungan itu) → jalur lama +
  penanda `rekonstruksi`;
- transaksi obat-saja dan transaksi KEDUA split billing → bukan "rekonstruksi", dan
  tidak memuat tindakan milik transaksi lain;
- jumlah baris − diskon = TOTAL pada jalur snapshot.
"""
import random
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.models import (
    Kunjungan, KunjunganTindakan, MasterMembership, MasterProduk, MasterStaf,
    MasterTreatment, Pasien, PasienMembershipHistory, PasienMembershipKuota,
    TransaksiDetailProduk, TransaksiDetailTindakan, TransaksiKasir,
)
from app.db.models._enums import StatusTindakanEnum, TipeProdukEnum
from app.db.session import SessionLocal
from app.services.print_service import PrintService


@pytest.fixture
def db():
    s = SessionLocal()
    s.commit = s.flush
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def dasar(db):
    pasien = db.execute(select(Pasien).limit(1)).scalar_one_or_none()
    staf = db.execute(select(MasterStaf).limit(1)).scalar_one_or_none()
    tier = db.execute(select(MasterMembership).limit(1)).scalar_one_or_none()
    if not (pasien and staf and tier):
        pytest.skip("Butuh pasien, staf, dan master_membership di DB dev.")
    tr = MasterTreatment(nama_treatment=f"Uji T27 {random.randint(1000, 9999)}",
                         harga=Decimal("500000"), role_pelaksana="Dokter", durasi_menit=30)
    db.add(tr); db.flush()
    return {"pasien": pasien, "staf": staf, "tier": tier, "treatment": tr}


def _kunjungan(db, d):
    k = Kunjungan(id_pasien=d["pasien"].id_pasien, tgl_kunjungan=datetime.now(),
                  status_antrian="COMPLETED")
    db.add(k); db.flush()
    return k


def _tindakan(db, d, k, **kw):
    kt = KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=d["treatment"].id_treatment,
                           status_tindakan=StatusTindakanEnum.SELESAI, **kw)
    db.add(kt); db.flush()
    return kt


def _trx(db, d, k, total):
    t = TransaksiKasir(id_kunjungan=k.id_kunjungan, id_pasien=d["pasien"].id_pasien,
                       id_staf_kasir=d["staf"].id_staf, rincian_tagihan="uji T27",
                       subtotal=total, nominal_diskon=0, total_tagihan=total,
                       status_transaksi="BAYAR", waktu_bayar=datetime.now())
    db.add(t); db.flush()
    return t


def _kuota(db, d):
    h = PasienMembershipHistory(id_pasien=d["pasien"].id_pasien, id_membership=d["tier"].id_membership,
                                tgl_aktif=date.today(), tgl_expired=date.today() + timedelta(days=360),
                                harga_bayar=0)
    db.add(h); db.flush()
    q = PasienMembershipKuota(id_pasien=d["pasien"].id_pasien, id_membership_history=h.id_history,
                              id_treatment=d["treatment"].id_treatment, periode_kuota="TOTAL_PAKET",
                              kuota_total=5, kuota_terpakai=1, expired_at=date.today() + timedelta(days=360))
    db.add(q); db.flush()
    return q


def _nota(db, t):
    return PrintService(db).prepare_nota_context(t.id_transaksi)


def test_tindakan_kuota_rp0_dengan_nilai_normal(db, dasar):
    k = _kunjungan(db, dasar)
    kt = _tindakan(db, dasar, k, id_kuota_member=_kuota(db, dasar).id_kuota)
    t = _trx(db, dasar, k, Decimal("0"))
    db.add(TransaksiDetailTindakan(id_transaksi=t.id_transaksi, id_kunjungan_tindakan=kt.id_kunjungan_tindakan,
                                   id_treatment=dasar["treatment"].id_treatment, qty=1,
                                   harga_satuan=0, diskon_item=0, subtotal=0))
    db.flush()
    n = _nota(db, t)
    baris = [i for i in n["items"] if i["tipe"] == "TND"]
    assert len(baris) == 1
    assert baris[0]["harga"] == 0 and baris[0]["subtotal"] == 0
    assert baris[0]["ket_prabayar"] == f"Benefit {dasar['tier'].nama_tier} (prabayar)"
    assert baris[0]["nilai_normal"] == 500000
    assert n["diskon_benefit"] == 0           # tidak ada lagi baris pengurang
    assert n["nilai_benefit_prabayar"] == 500000
    assert n["rekonstruksi"] is False and n["total"] == 0


def test_harga_master_naik_nota_lama_tetap(db, dasar):
    k = _kunjungan(db, dasar)
    kt = _tindakan(db, dasar, k)
    t = _trx(db, dasar, k, Decimal("500000"))
    db.add(TransaksiDetailTindakan(id_transaksi=t.id_transaksi, id_kunjungan_tindakan=kt.id_kunjungan_tindakan,
                                   id_treatment=dasar["treatment"].id_treatment, qty=1,
                                   harga_satuan=500000, diskon_item=0, subtotal=500000))
    db.flush()
    dasar["treatment"].harga = Decimal("1000000"); db.flush()
    baris = [i for i in _nota(db, t)["items"] if i["tipe"] == "TND"]
    assert baris[0]["harga"] == 500000


def test_data_sebelum_f3_ditandai_rekonstruksi(db, dasar):
    k = _kunjungan(db, dasar)
    _tindakan(db, dasar, k)
    t = _trx(db, dasar, k, Decimal("500000"))   # tanpa transaksi_detail_tindakan
    n = _nota(db, t)
    assert n["rekonstruksi"] is True
    assert [i["harga"] for i in n["items"] if i["tipe"] == "TND"] == [500000]


def test_obat_saja_bukan_rekonstruksi(db, dasar):
    k = _kunjungan(db, dasar)
    p = MasterProduk(kode_produk=f"T27{random.randint(10000, 99999)}", nama_produk="Uji Obat T27",
                     tipe_produk=TipeProdukEnum.RETAIL, satuan="pcs", default_iterasi=1,
                     eligible_member_discount=False, stok_terkini=0, harga_jual=Decimal("99000"))
    db.add(p); db.flush()
    t = _trx(db, dasar, k, Decimal("85000"))
    db.add(TransaksiDetailProduk(id_transaksi=t.id_transaksi, id_produk=p.id_produk, qty=1,
                                 harga_satuan=85000, subtotal=85000))
    db.flush()
    n = _nota(db, t)
    assert n["rekonstruksi"] is False
    assert [(i["tipe"], i["harga"]) for i in n["items"]] == [("OBT", 85000)]  # harga DITAGIH, bukan master 99.000
    assert sum(i["subtotal"] for i in n["items"]) - n["diskon"] == n["total"]


def test_split_billing_tidak_memuat_tindakan_transaksi_lain(db, dasar):
    k = _kunjungan(db, dasar)
    kt = _tindakan(db, dasar, k)
    a = _trx(db, dasar, k, Decimal("500000"))
    db.add(TransaksiDetailTindakan(id_transaksi=a.id_transaksi, id_kunjungan_tindakan=kt.id_kunjungan_tindakan,
                                   id_treatment=dasar["treatment"].id_treatment, qty=1,
                                   harga_satuan=500000, diskon_item=0, subtotal=500000))
    b = _trx(db, dasar, k, Decimal("0"))         # transaksi kedua kunjungan yang sama
    db.flush()
    nb = _nota(db, b)
    assert [i for i in nb["items"] if i["tipe"] == "TND"] == []
    assert nb["rekonstruksi"] is False
