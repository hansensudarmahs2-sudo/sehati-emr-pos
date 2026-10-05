"""
Retur dari pasien — Tahap 2 (jenis REFUND). DESAIN_RETUR_DARI_PASIEN.md §10–§13.
Non-destruktif: `commit` sesi diganti `flush`, semua di-rollback.

Yang dijaga (keputusan dr. Hansen 2026-10-05):
- hanya obat DISERAHKAN, ≤ 7 hari sejak serah; qty ≤ sisa yang belum diretur;
- retur SEBAGIAN butuh PIN Admin/Owner (penyetuju ≠ pemroses);
- uang lewat jalur T32: refund dibukukan hari ini, header transaksi asal UTUH,
  void transaksi asal sesudahnya ditolak;
- komisi: penuh → VOID; sebagian → koreksi negatif proporsional; sisa terakhir →
  VOID semuanya sehingga total komisi item = 0;
- stok kembali ke LOT ASAL (ED terjaga) + inventory_history RETUR_PASIEN; tanpa jejak
  lot → ditolak; tidak kembali → nilai_kerugian dari harga terima lot.
"""
import random
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.security import hash_password
from app.db.models import (
    InventoryHistory, KomisiLedger, Kunjungan, KunjunganLotTerpakai, KunjunganResep,
    MasterProduk, MasterStaf, Pasien, ReturPasien, ReturPasienLot, StatusItemResepEnum,
    StokLot, TransaksiDetailProduk, TransaksiKasir,
)
from app.db.models._enums import StafRoleEnum, TipeProdukEnum
from app.db.session import SessionLocal
from app.services.kasir_service import KasirService
from app.services.retur_pasien_service import ReturPasienService

PIN = "975310"


@pytest.fixture
def db():
    s = SessionLocal()
    s.commit = s.flush
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _staf(db, role, pin=None):
    s = MasterStaf(username=f"uji_rp_{random.randint(10**6, 10**7)}",
                   password_hash=hash_password("x"), role=role, nama_staf=f"Uji RP {role.value}",
                   is_active=True, pin=hash_password(pin) if pin else None)
    db.add(s); db.flush()
    return s


def _setup(db, *, qty=3, hari_serah=0, dengan_jejak=True, status_item="DISERAHKAN"):
    pasien = db.execute(select(Pasien).limit(1)).scalar_one()
    kasir = _staf(db, StafRoleEnum.KASIR)
    admin = _staf(db, StafRoleEnum.ADMIN, pin=PIN)
    dokter = _staf(db, StafRoleEnum.DOKTER)
    now = KasirService._now_utc7().replace(tzinfo=None)
    p = MasterProduk(kode_produk=f"RP{random.randint(10000, 99999)}", nama_produk="Uji Retur Krim",
                     tipe_produk=TipeProdukEnum.RETAIL, satuan="pcs", default_iterasi=1,
                     eligible_member_discount=False, stok_terkini=7, harga_jual=Decimal("100000"),
                     hpp_per_unit=Decimal("35000"))
    db.add(p); db.flush()
    lot = StokLot(tipe_item="PRODUK", id_produk=p.id_produk, lokasi="RETAIL", batch_no="UJI-RP",
                  tgl_ed=date(2027, 12, 31), qty_masuk=10, qty_sisa=7, harga_terima=Decimal("40000"),
                  status="AKTIF", tgl_masuk=date(2026, 1, 1))
    db.add(lot); db.flush()
    k = Kunjungan(id_pasien=pasien.id_pasien, tgl_kunjungan=now, status_antrian="COMPLETED",
                  id_staf_dokter_assigned=dokter.id_staf)
    db.add(k); db.flush()
    r = KunjunganResep(id_kunjungan=k.id_kunjungan, id_produk=p.id_produk, qty=qty,
                       status_item=StatusItemResepEnum(status_item), id_staf_input=dokter.id_staf,
                       waktu_serah=now - timedelta(days=hari_serah))
    db.add(r); db.flush()
    if dengan_jejak:
        db.add(KunjunganLotTerpakai(id_kunjungan=k.id_kunjungan, id_produk=p.id_produk,
                                    id_lot=lot.id_lot, qty=qty, id_resep=r.id_resep))
    nilai = Decimal("100000") * qty
    t = TransaksiKasir(id_kunjungan=k.id_kunjungan, id_pasien=pasien.id_pasien,
                       id_staf_kasir=kasir.id_staf, rincian_tagihan="uji retur",
                       subtotal=nilai, nominal_diskon=0, total_tagihan=nilai,
                       status_transaksi="BAYAR", waktu_bayar=now)
    db.add(t); db.flush()
    db.add(TransaksiDetailProduk(id_transaksi=t.id_transaksi, id_produk=p.id_produk, qty=qty,
                                 harga_satuan=100000, subtotal=nilai, diskon_item=0))
    db.add(KomisiLedger(id_transaksi=t.id_transaksi, id_kunjungan=k.id_kunjungan,
                        id_pasien=pasien.id_pasien, tanggal=now.date(), id_staf=dokter.id_staf,
                        role_snapshot="DOKTER", sumber="PRODUK", id_ref=r.id_resep,
                        nama_item="Uji Retur Krim", harga_jual=100000, komisi_tipe="NOMINAL",
                        komisi_value=10000, komisi_nominal=Decimal("10000") * qty, status="AKTIF"))
    db.flush()
    return {"kasir": kasir, "admin": admin, "produk": p, "lot": lot, "resep": r, "trx": t}


def _retur(db, d, **kw):
    arg = dict(id_resep=d["resep"].id_resep, jenis="REFUND", alasan_kode="TIDAK_PUAS",
               alasan_teks="uji", stok_kembali=True, actor_id_staf=d["kasir"].id_staf)
    arg.update(kw)
    return ReturPasienService(db).buat_retur(**arg)


def _komisi_aktif(db, d):
    return db.execute(select(func.coalesce(func.sum(KomisiLedger.komisi_nominal), 0)).where(
        KomisiLedger.id_ref == d["resep"].id_resep, KomisiLedger.status == "AKTIF")).scalar()


def test_retur_penuh_stok_kembali_ke_lot_asal(db):
    d = _setup(db)
    h = _retur(db, d)
    assert h["nomor_retur"].startswith("RPS-") and h["nilai"] == 300000
    db.refresh(d["lot"]); db.refresh(d["produk"]); db.refresh(d["trx"])
    assert float(d["lot"].qty_sisa) == 10 and float(d["produk"].stok_terkini) == 10
    assert Decimal(str(d["trx"].total_tagihan)) == Decimal("300000")   # header utuh (T32)
    assert _komisi_aktif(db, d) == 0                                    # komisi VOID
    hist = db.execute(select(InventoryHistory).where(
        InventoryHistory.id_produk == d["produk"].id_produk)).scalars().all()
    assert [h.jenis_mutasi.value for h in hist] == ["RETUR_PASIEN"]
    rp = db.execute(select(ReturPasien).where(ReturPasien.id_resep == d["resep"].id_resep)).scalar_one()
    lots = db.execute(select(ReturPasienLot).where(ReturPasienLot.id_retur == rp.id_retur)).scalars().all()
    assert [(l.id_lot, float(l.qty)) for l in lots] == [(d["lot"].id_lot, 3.0)]


def test_obat_belum_diserahkan_ditolak(db):
    d = _setup(db, status_item="DIBAYAR")
    with pytest.raises(HTTPException) as e:
        _retur(db, d)
    assert e.value.status_code == 400 and "SUDAH diserahkan" in e.value.detail


def test_lewat_7_hari_ditolak(db):
    d = _setup(db, hari_serah=8)
    with pytest.raises(HTTPException) as e:
        _retur(db, d)
    assert "batas retur 7 hari" in e.value.detail


def test_sebagian_butuh_pin_lalu_sisa_menutup_komisi(db):
    d = _setup(db)
    with pytest.raises(HTTPException) as e:                       # sebagian tanpa PIN
        _retur(db, d, qty=1)
    assert e.value.status_code == 401 and "SEBAGIAN" in e.value.detail
    _retur(db, d, qty=1, id_staf_otorisasi=d["admin"].id_staf, pin_otorisasi=PIN)
    assert _komisi_aktif(db, d) == Decimal("20000.00")            # 30.000 − 1/3
    with pytest.raises(HTTPException):                            # melebihi sisa
        _retur(db, d, qty=5, id_staf_otorisasi=d["admin"].id_staf, pin_otorisasi=PIN)
    _retur(db, d, qty=2, id_staf_otorisasi=d["admin"].id_staf, pin_otorisasi=PIN)
    assert _komisi_aktif(db, d) == 0                              # sisa terakhir → 0
    with pytest.raises(HTTPException) as e:
        _retur(db, d, qty=1, id_staf_otorisasi=d["admin"].id_staf, pin_otorisasi=PIN)
    assert "seluruhnya" in e.value.detail


# Dua test terpisah: penolakan di service me-ROLLBACK, dan di test (commit=flush) rollback
# itu ikut membuang data uji — skenario kedua butuh setup sendiri.
def test_stok_kembali_tanpa_jejak_ditolak(db):
    d = _setup(db, dengan_jejak=False)
    with pytest.raises(HTTPException) as e:
        _retur(db, d)
    assert "Jejak lot" in e.value.detail


def test_tanpa_jejak_tidak_kembali_rugi_dari_hpp(db):
    d = _setup(db, dengan_jejak=False)
    h = _retur(db, d, stok_kembali=False)
    assert h["nilai_kerugian"] == 3 * 35000                       # fallback HPP


def test_tidak_kembali_rugi_dari_harga_terima_lot(db):
    d = _setup(db)
    h = _retur(db, d, stok_kembali=False)
    assert h["nilai_kerugian"] == 3 * 40000
    db.refresh(d["lot"])
    assert float(d["lot"].qty_sisa) == 7                          # stok tidak bergerak


def test_void_transaksi_asal_sesudah_retur_ditolak(db):
    d = _setup(db)
    _retur(db, d)
    with pytest.raises(HTTPException) as e:
        KasirService(db)._pagari_void_sudah_refund(d["trx"])
    assert "refund" in e.value.detail.lower()


# ============================================================================
# Tahap 3 — TUKAR (keputusan dr. Hansen 2026-10-05, DESAIN §10a)
# ============================================================================
from app.db.models import KasirClosing, TransaksiPembayaran, TransaksiRefund  # noqa: E402
from app.services.kasir_closing_service import KasirClosingService  # noqa: E402
from app.services.reports_service import ReportsService  # noqa: E402


def _produk_y(db, harga):
    y = MasterProduk(kode_produk=f"RY{random.randint(10000, 99999)}", nama_produk="Uji Pengganti",
                     tipe_produk=TipeProdukEnum.RETAIL, satuan="pcs", default_iterasi=1,
                     eligible_member_discount=False, stok_terkini=5, harga_jual=Decimal(harga))
    db.add(y); db.flush()
    lot = StokLot(tipe_item="PRODUK", id_produk=y.id_produk, lokasi="RETAIL", batch_no="UJI-RY",
                  tgl_ed=date(2027, 6, 30), qty_masuk=5, qty_sisa=5, harga_terima=Decimal("1000"),
                  status="AKTIF", tgl_masuk=date(2026, 1, 1))
    db.add(lot); db.flush()
    return y, lot


def _laci_tunai(db):
    sesi = KasirClosing(shift_mulai=datetime.now(), modal_awal=0, status="OPEN")
    return KasirClosingService(db)._penjualan_per_metode(sesi)["TUNAI"]


def _omzet_hari_ini(db):
    return ReportsService(db).omzet_harian(datetime.now().date()).total_omzet


def test_tukar_lebih_mahal_pasien_bayar_selisih(db):
    d = _setup(db)
    y, lot_y = _produk_y(db, "400000")
    laci0, omzet0 = _laci_tunai(db), _omzet_hari_ini(db)
    h = _retur(db, d, jenis="TUKAR", metode_refund="TUNAI",
               pengganti=[{"id_produk": y.id_produk, "qty": 1}])
    assert h["selisih_dibayar"] == 100000 and h["nilai_hangus"] == 0
    assert _laci_tunai(db) - laci0 == Decimal("100000")          # laci: hanya selisih
    assert _omzet_hari_ini(db) - omzet0 == Decimal("100000")     # omzet: hanya selisih
    assert _komisi_aktif(db, d) == Decimal("30000")               # komisi X utuh
    pemb = {p.metode_bayar: float(p.nominal) for p in db.execute(select(TransaksiPembayaran).where(
        TransaksiPembayaran.id_transaksi == h["id_transaksi_pengganti"])).scalars()}
    assert pemb == {"TUKAR": 300000.0, "TUNAI": 100000.0}
    db.refresh(lot_y); db.refresh(y)
    assert float(lot_y.qty_sisa) == 4 and float(y.stok_terkini) == 4   # Y keluar FEFO
    ry = db.execute(select(KunjunganResep).where(KunjunganResep.id_produk == y.id_produk)).scalar_one()
    assert ry.status_item.value == "DISERAHKAN"
    assert db.execute(select(KunjunganLotTerpakai).where(
        KunjunganLotTerpakai.id_resep == ry.id_resep)).scalar_one().id_lot == lot_y.id_lot


def test_tukar_lebih_murah_sisa_hangus_laci_dan_omzet_diam(db):
    d = _setup(db)
    y, _ = _produk_y(db, "100000")
    laci0, omzet0 = _laci_tunai(db), _omzet_hari_ini(db)
    h = _retur(db, d, jenis="TUKAR", metode_refund="TUNAI",
               pengganti=[{"id_produk": y.id_produk, "qty": 1}], setuju_hangus=True)
    assert h["nilai_hangus"] == 200000 and h["selisih_dibayar"] == 0
    assert _laci_tunai(db) == laci0 and _omzet_hari_ini(db) == omzet0
    ref = db.execute(select(TransaksiRefund).where(
        TransaksiRefund.id_transaksi == d["trx"].id_transaksi)).scalar_one()
    assert (ref.metode_refund, float(ref.nilai_refund)) == ("TUKAR", 100000.0)
    rp = db.execute(select(ReturPasien).where(ReturPasien.id_resep == d["resep"].id_resep)).scalar_one()
    assert float(rp.nilai_hangus) == 200000 and rp.jenis.value == "TUKAR"


def test_tukar_tanpa_pengganti_atau_selisih_bermetode_tukar_ditolak(db):
    d = _setup(db)
    with pytest.raises(HTTPException) as e:
        _retur(db, d, jenis="TUKAR", pengganti=[])
    assert "pengganti" in e.value.detail
    y, _ = _produk_y(db, "400000")
    with pytest.raises(HTTPException) as e:
        _retur(db, d, jenis="TUKAR", metode_refund="TUKAR",
               pengganti=[{"id_produk": y.id_produk, "qty": 1}])
    assert "selisih" in e.value.detail


def test_sesudah_tukar_transaksi_asal_dan_pengganti_tetap_terlacak(db):
    """Dulu: 'transaksi BAYAR terbaru di kunjungan' — sesudah tukar, itu transaksi
    TUKAR, sehingga retur berikutnya atas obat ASAL salah transaksi."""
    d = _setup(db)
    y, _ = _produk_y(db, "250000")
    _retur(db, d, jenis="TUKAR", qty=1, metode_refund="TUNAI",
           pengganti=[{"id_produk": y.id_produk, "qty": 1}],
           id_staf_otorisasi=d["admin"].id_staf, pin_otorisasi=PIN)
    h2 = _retur(db, d, qty=1, id_staf_otorisasi=d["admin"].id_staf, pin_otorisasi=PIN)
    assert h2["nilai"] == 100000                                   # dari penjualan ASLI
    ry = db.execute(select(KunjunganResep).where(KunjunganResep.id_produk == y.id_produk)).scalar_one()
    h3 = ReturPasienService(db).buat_retur(
        id_resep=ry.id_resep, jenis="REFUND", alasan_kode="TIDAK_PUAS", alasan_teks="uji",
        stok_kembali=True, actor_id_staf=d["kasir"].id_staf)
    assert h3["nilai"] == 250000                                   # dari transaksi TUKAR


# ============================================================================
# Tahap 4 — ALERGI (DESAIN §10b, §12)
# ============================================================================
from app.db.models import PasienAlergi, PemeriksaanKlinis  # noqa: E402
from app.services.dashboard_service import DashboardService  # noqa: E402
from app.services.export_service import ExportService  # noqa: E402
from app.services.rekap_harian_service import RekapHarianService  # noqa: E402


def _hitung_kunjungan_hari_ini(db):
    hari = datetime.now().date()
    ds = DashboardService(db)
    return (ds._kpi_kunjungan_hari_ini(hari)["value"],
            ds._kpi_pasien_hari_ini(hari)["value"],
            RekapHarianService(db).rekap(hari)["total_kunjungan"],
            ExportService(db).export_daily_operational_summary(hari, hari)[0]["jumlah_kunjungan"])


def test_alergi_buat_kunjungan_retur_dengan_draf_untuk_dokter_asal(db):
    d = _setup(db)
    # Pasien BARU dan kunjungan asal KEMARIN: tanpa saringan, kunjungan retur hari ini
    # pasti menambah "pasien unik hari ini". (Versi pertama test ini memakai pasien yang
    # sudah berkunjung hari ini — saringan pasien-unik bisa dibuang tanpa ketahuan.)
    from app.db.models import GenderEnum
    baru = Pasien(no_rm=f"UJI-RP-{random.randint(10**5, 10**6)}", nama="Uji Retur Alergi",
                  jenis_kelamin=GenderEnum.LAKI_LAKI)
    db.add(baru); db.flush()
    asal = db.get(Kunjungan, d["resep"].id_kunjungan)
    asal.id_pasien = baru.id_pasien
    asal.tgl_kunjungan = datetime.now() - timedelta(days=1)
    d["trx"].id_pasien = baru.id_pasien
    db.flush()
    sebelum = _hitung_kunjungan_hari_ini(db)
    _retur(db, d, alasan_kode="ALERGI", alasan_teks="gatal & bengkak di wajah")
    rp = db.execute(select(ReturPasien).where(ReturPasien.id_resep == d["resep"].id_resep)).scalar_one()
    k = db.get(Kunjungan, rp.id_kunjungan_retur)
    asal = db.get(Kunjungan, d["resep"].id_kunjungan)
    assert (k.jenis_kunjungan, k.status_antrian) == ("RETUR_PASIEN", "COMPLETED")
    assert k.id_staf_dokter_assigned == asal.id_staf_dokter_assigned
    draf = db.execute(select(PemeriksaanKlinis).where(
        PemeriksaanKlinis.id_kunjungan == k.id_kunjungan)).scalar_one()
    assert draf.status_soap == "DRAFT_APOTEK" and "gatal & bengkak" in draf.anamnesa
    assert db.execute(select(func.count()).select_from(PemeriksaanKlinis).where(
        PemeriksaanKlinis.id_kunjungan == asal.id_kunjungan)).scalar() == 0   # asal tak disentuh
    assert _hitung_kunjungan_hari_ini(db) == sebelum   # KPI, rekap, ekspor: tidak dihitung


def test_alergi_keparahan_wajib_lalu_dicatat_tanpa_dobel(db):
    d = _setup(db)
    _retur(db, d, alasan_kode="ALERGI", alasan_teks="ruam")
    rp = db.execute(select(ReturPasien).where(ReturPasien.id_resep == d["resep"].id_resep)).scalar_one()
    svc = ReturPasienService(db)
    info = svc.info_retur_alergi(rp.id_kunjungan_retur)
    assert info["alergen"] == "Uji Retur Krim" and info["gejala"] == "ruam"    # kandungan kosong → nama
    with pytest.raises(HTTPException) as e:
        svc.catat_alergi_dari_retur(id_kunjungan=rp.id_kunjungan_retur, id_staf_dokter=d["admin"].id_staf,
                                    alergen=info["alergen"], gejala="ruam", tingkat_keparahan="")
    assert "WAJIB" in e.value.detail
    id1 = svc.catat_alergi_dari_retur(id_kunjungan=rp.id_kunjungan_retur, id_staf_dokter=d["admin"].id_staf,
                                      alergen="Adapalene", gejala="ruam", tingkat_keparahan="Sedang")
    al = db.get(PasienAlergi, id1)
    assert (al.alergen, al.tingkat_keparahan.value) == ("Adapalene", "Sedang")
    id2 = svc.catat_alergi_dari_retur(id_kunjungan=rp.id_kunjungan_retur, id_staf_dokter=d["admin"].id_staf,
                                      alergen="adapalene", gejala="x", tingkat_keparahan="Berat")
    assert id2 == id1                                           # tidak dobel


def test_alergi_yang_sudah_ada_tidak_ditambah_lagi(db):
    d = _setup(db)
    pid = d["trx"].id_pasien
    lama = PasienAlergi(id_pasien=pid, alergen="ADAPALENE", tingkat_keparahan="Ringan", is_active=True)
    db.add(lama); db.flush()
    _retur(db, d, alasan_kode="ALERGI", alasan_teks="perih")
    rp = db.execute(select(ReturPasien).where(ReturPasien.id_resep == d["resep"].id_resep)).scalar_one()
    n0 = db.execute(select(func.count()).select_from(PasienAlergi).where(PasienAlergi.id_pasien == pid)).scalar()
    idx = ReturPasienService(db).catat_alergi_dari_retur(
        id_kunjungan=rp.id_kunjungan_retur, id_staf_dokter=d["admin"].id_staf,
        alergen="Adapalene", gejala="perih", tingkat_keparahan="Sedang")
    assert idx == lama.id_alergi
    assert db.execute(select(func.count()).select_from(PasienAlergi).where(
        PasienAlergi.id_pasien == pid)).scalar() == n0


def test_bukan_alergi_tidak_membuat_kunjungan(db):
    d = _setup(db)
    _retur(db, d, alasan_kode="TIDAK_PUAS")
    rp = db.execute(select(ReturPasien).where(ReturPasien.id_resep == d["resep"].id_resep)).scalar_one()
    assert rp.id_kunjungan_retur is None


# ============================================================================
# Tahap 5 — nota retur, nota transaksi TUKAR, ekspor
# ============================================================================
from app.services.klinik_config_service import KlinikConfigService  # noqa: E402
from app.services.print_service import PrintService  # noqa: E402
from app.web.routes._shared import templates  # noqa: E402


def _render_nota_retur(db, id_retur):
    ctx = ReturPasienService(db).konteks_nota_retur(id_retur)
    ctx.update(klinik=KlinikConfigService(db).get_config(), tgl_cetak="uji", ok=None)
    html = templates.env.get_template("print/nota_retur.html").render(**ctx)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


import re  # noqa: E402


def test_nota_retur_refund_dan_tukar(db):
    d = _setup(db)
    h = _retur(db, d, qty=1, id_staf_otorisasi=d["admin"].id_staf, pin_otorisasi=PIN)
    t = _render_nota_retur(db, h["id_retur"])
    assert "PENGEMBALIAN DANA" in t and h["nomor_retur"] in t and "Rp 100.000" in t
    assert "(sebagian)" in t
    y, _ = _produk_y(db, "50000")
    h2 = _retur(db, d, jenis="TUKAR", qty=1, metode_refund="TUNAI",
                pengganti=[{"id_produk": y.id_produk, "qty": 1}], setuju_hangus=True,
                id_staf_otorisasi=d["admin"].id_staf, pin_otorisasi=PIN)
    t2 = _render_nota_retur(db, h2["id_retur"])
    assert "PENUKARAN PRODUK" in t2 and "Uji Pengganti" in t2
    assert "Sisa nilai tidak dikembalikan" in t2 and "Rp 50.000" in t2


def test_nota_transaksi_tukar_hanya_memuat_pengganti(db):
    """Kunjungan asal punya tindakan TANPA snapshot (pra-F3). Tanpa pengecualian TUKAR,
    nota pengganti jatuh ke jalur 'rekonstruksi' dan mencetak tindakan kunjungan asal."""
    from app.db.models import KunjunganTindakan, MasterTreatment
    from app.db.models._enums import StatusTindakanEnum
    d = _setup(db)
    tr = db.execute(select(MasterTreatment).limit(1)).scalar_one()
    db.add(KunjunganTindakan(id_kunjungan=d["resep"].id_kunjungan, id_treatment=tr.id_treatment,
                             status_tindakan=StatusTindakanEnum.SELESAI))
    db.flush()
    y, _ = _produk_y(db, "400000")
    h = _retur(db, d, jenis="TUKAR", metode_refund="TUNAI",
               pengganti=[{"id_produk": y.id_produk, "qty": 1}])
    n = PrintService(db).prepare_nota_context(h["id_transaksi_pengganti"])
    assert [i["label"] for i in n["items"]] == ["Uji Pengganti"]
    assert n["rekonstruksi"] is False


def test_ekspor_refund_memuat_kolom_retur(db):
    from app.services.export_service import ExportService
    d = _setup(db)
    y, _ = _produk_y(db, "100000")
    h = _retur(db, d, jenis="TUKAR", metode_refund="TUNAI",
               pengganti=[{"id_produk": y.id_produk, "qty": 1}], setuju_hangus=True)
    hari = datetime.now().date()
    baris = [r for r in ExportService(db).export_refunds_raw(hari, hari)
             if r["nomor_retur"] == h["nomor_retur"]]
    assert len(baris) == 1
    b = baris[0]
    assert (b["jenis_retur"], b["metode_refund"], b["nilai_hangus"]) == ("TUKAR", "TUKAR", 200000.0)


# ============================================================================
# Peringatan tukar (dr. Hansen 2026-10-05): "terutama yang lebih murah karena uang
# pasien akan hilang". Pratinjau tanpa tulis + persetujuan hangus dijaga DI SERVER.
# ============================================================================
def test_pratinjau_tukar_menghitung_tanpa_menulis(db):
    d = _setup(db)
    y, lot_y = _produk_y(db, "100000")
    n_retur = db.execute(select(func.count()).select_from(ReturPasien)).scalar()
    p = _retur(db, d, jenis="TUKAR", metode_refund="TUNAI", pratinjau=True,
               pengganti=[{"id_produk": y.id_produk, "qty": 1}])
    assert p["status"] == "pratinjau"
    assert (p["nilai_retur"], p["nilai_pengganti"], p["nilai_hangus"], p["selisih_dibayar"]) ==         (300000.0, 100000.0, 200000.0, 0.0)
    assert db.execute(select(func.count()).select_from(ReturPasien)).scalar() == n_retur
    db.refresh(lot_y)
    assert float(lot_y.qty_sisa) == 5                       # pengganti belum keluar
    assert _komisi_aktif(db, d) == Decimal("30000")


def test_tukar_lebih_murah_tanpa_persetujuan_ditolak(db):
    d = _setup(db)
    y, _ = _produk_y(db, "100000")
    with pytest.raises(HTTPException) as e:
        _retur(db, d, jenis="TUKAR", metode_refund="TUNAI",
               pengganti=[{"id_produk": y.id_produk, "qty": 1}])
    assert e.value.status_code == 400 and "TIDAK dikembalikan" in e.value.detail
    assert "Rp 200.000" in e.value.detail


def test_tukar_lebih_mahal_tidak_butuh_persetujuan_hangus(db):
    d = _setup(db)
    y, _ = _produk_y(db, "400000")
    h = _retur(db, d, jenis="TUKAR", metode_refund="TUNAI",
               pengganti=[{"id_produk": y.id_produk, "qty": 1}])
    assert h["selisih_dibayar"] == 100000
