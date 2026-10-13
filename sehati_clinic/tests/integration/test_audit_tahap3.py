"""Audit mendalam tahap 3 (apotek & stok) — 2026-10-13.

Project_Memory/AUDIT_MENDALAM_2026-10-13.md, tahap 3. Memakai layanan ASLI di sesi yang
di-rollback (commit = flush).
"""
import random
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.db.models import KunjunganLotTerpakai, KunjunganResep, MasterProduk, StokLot
from app.db.models._enums import StatusItemResepEnum, TipeProdukEnum
from tests.integration.test_audit_tahap2 import (  # noqa: F401  (fixture db dipakai ulang)
    V, _bayar, _siapkan, _trx_terakhir, db,
)
from app.services.kasir_service import KasirService


def _produk_dengan_lot(db, qty_lot=10):
    p = MasterProduk(kode_produk=f"T3{random.randint(10000, 99999)}", nama_produk="ZZ Uji T3",
                     tipe_produk=TipeProdukEnum.RETAIL, satuan="pcs", default_iterasi=1,
                     eligible_member_discount=False, stok_terkini=qty_lot,
                     harga_jual=Decimal("10000"), hpp_per_unit=Decimal("4000"))
    db.add(p); db.flush()
    lot = StokLot(tipe_item="PRODUK", id_produk=p.id_produk, lokasi="RETAIL", batch_no="UJI-T3",
                  tgl_ed=date(2028, 1, 1), qty_masuk=qty_lot, qty_sisa=qty_lot, status="AKTIF",
                  tgl_masuk=date(2026, 1, 1))
    db.add(lot); db.flush()
    return p, lot


def _resep_produk(db, k, staf, p, qty, detik=0):
    r = KunjunganResep(id_kunjungan=k.id_kunjungan, id_produk=p.id_produk, qty=qty,
                       status_item=StatusItemResepEnum.PENDING, id_staf_input=staf.id_staf)
    db.add(r); db.flush()
    if detik:
        r.waktu_input = datetime.now() + timedelta(seconds=detik); db.flush()
    return r


def _serahkan_seperti_apotek(db, k, r, p, lot):
    """Jejak persis `serahkan_obat`: status DISERAHKAN, lot & cache dipotong, jejak lot."""
    r.status_item = StatusItemResepEnum.DISERAHKAN
    r.waktu_serah = datetime.now()
    lot.qty_sisa = float(lot.qty_sisa) - float(r.qty)
    p.stok_terkini = float(p.stok_terkini) - float(r.qty)
    db.add(KunjunganLotTerpakai(id_kunjungan=k.id_kunjungan, id_produk=p.id_produk,
                                id_lot=lot.id_lot, qty=r.qty, id_resep=r.id_resep))
    db.flush()


# ---------------------------------------------------------------- T3-1
def test_void_t2_tidak_mengembalikan_stok_obat_yang_diserahkan_lewat_t1(db):
    """T1: obat X ×3 DISERAHKAN. Susulan T2: obat X ×2 belum diserahkan. Void T2 + centang
    'produk masih utuh' → dulu stok +2 HANTU dan jejak lot T1 ditandai reversed."""
    staf, k = _siapkan(db)
    p, lot = _produk_dengan_lot(db)
    ra = _resep_produk(db, k, staf, p, 3)
    _bayar(db, k, staf)
    _serahkan_seperti_apotek(db, k, ra, p, lot)                 # cache 7, lot 7
    _resep_produk(db, k, staf, p, 2, detik=5)
    k.status_antrian = "ANTRI_BAYAR"; db.flush()
    _bayar(db, k, staf)
    t2 = _trx_terakhir(db, k)
    KasirService(db).void_transaksi(t2.id_transaksi, "SALAH_INPUT", "uji T3-1",
                                    [f"PRD:{p.id_produk}"], staf.id_staf)
    db.refresh(p); db.refresh(lot)
    assert (float(p.stok_terkini), float(lot.qty_sisa)) == (7.0, 7.0)   # dulu 9 / 9
    jr = db.execute(select(KunjunganLotTerpakai).where(
        KunjunganLotTerpakai.id_resep == ra.id_resep)).scalar_one()
    assert jr.reversed_at is None                                         # jejak T1 utuh


# ---------------------------------------------------------------- T3-2
# Balapan sungguhan butuh dua koneksi yang commit (= menulis permanen ke DB dev). Yang diuji
# di sini: jalur ASLI dijalankan dan SQL-nya direkam — keputusan harus memakai pembacaan
# BERKUNCI (REPEATABLE-READ: SELECT biasa membaca potret awal permintaan), dalam urutan
# produk → lot (sama dengan serah, supaya tak saling mengunci).
from contextlib import contextmanager  # noqa: E402
from sqlalchemy import event  # noqa: E402


@contextmanager
def _rekam_sql(db):
    terekam = []
    eng = db.get_bind()
    def _cat(conn, cursor, statement, params, context, executemany):
        terekam.append(" ".join(statement.split()))
    event.listen(eng, "before_cursor_execute", _cat)
    try:
        yield terekam
    finally:
        event.remove(eng, "before_cursor_execute", _cat)


def _berkunci(terekam, tabel):
    """Kueri FOR UPDATE atas tabel PERSIS ini. Pencocokan substring biasa ("FROM kunjungan")
    ikut cocok dengan kunjungan_resep — suntikan "serah tanpa kunci kunjungan" sempat LOLOS."""
    import re
    pola = re.compile(rf"FROM {re.escape(tabel)}(?![A-Za-z0-9_])")
    return [q for q in terekam if pola.search(q) and "FOR UPDATE" in q]


def test_serah_mengunci_kunjungan_resep_dan_lot(db):
    from app.schemas.apotek import SerahkanObatRequest
    from app.services.apotek_service import ApotekService
    staf, k = _siapkan(db)
    p, lot = _produk_dengan_lot(db)
    r = _resep_produk(db, k, staf, p, 2)
    _bayar(db, k, staf)
    with _rekam_sql(db) as q:
        ApotekService(db).serahkan_obat(SerahkanObatRequest(id_kunjungan=k.id_kunjungan), staf.id_staf)
    assert _berkunci(q, "kunjungan") and _berkunci(q, "kunjungan_resep") and _berkunci(q, "stok_lot")
    db.refresh(r); db.refresh(lot)
    assert V(r.status_item) == "DISERAHKAN" and float(lot.qty_sisa) == 8.0


def test_serah_kedua_ditolak(db):
    """Klik ganda yang tiba BERURUTAN: permintaan kedua tak menyerahkan lagi."""
    from app.schemas.apotek import SerahkanObatRequest
    from app.services.apotek_service import ApotekService
    staf, k = _siapkan(db)
    p, lot = _produk_dengan_lot(db)
    _resep_produk(db, k, staf, p, 2)
    _bayar(db, k, staf)
    svc = ApotekService(db)
    svc.serahkan_obat(SerahkanObatRequest(id_kunjungan=k.id_kunjungan), staf.id_staf)
    with pytest.raises(HTTPException):
        svc.serahkan_obat(SerahkanObatRequest(id_kunjungan=k.id_kunjungan), staf.id_staf)
    db.refresh(lot)
    assert float(lot.qty_sisa) == 8.0


def test_void_mengunci_transaksi_lalu_kunjungan_sebelum_pagar(db):
    staf, k = _siapkan(db)
    p, _ = _produk_dengan_lot(db)
    _resep_produk(db, k, staf, p, 2)
    _bayar(db, k, staf)
    t = _trx_terakhir(db, k)
    with _rekam_sql(db) as q:
        KasirService(db).void_transaksi(t.id_transaksi, "SALAH_INPUT", "uji T3-2", [], staf.id_staf)
    i_trx = next(i for i, x in enumerate(q) if "FROM transaksi_kasir" in x and "FOR UPDATE" in x)
    i_kj = q.index(_berkunci(q, "kunjungan")[0])
    i_pagar = next(i for i, x in enumerate(q) if "FROM kunjungan_resep" in x and "FOR UPDATE" in x)
    assert i_trx < i_kj < i_pagar


def test_refund_tertunda_membaca_item_dan_anti_dobel_berkunci(db):
    """Juga membuktikan jalur refund BERJALAN — patch pertama memakai nama yang tak
    diimpor di fungsi ini (NameError saat dipakai), tertangkap sebelum test."""
    staf, k = _siapkan(db)
    p, _ = _produk_dengan_lot(db)
    r = _resep_produk(db, k, staf, p, 2)
    _bayar(db, k, staf)
    with _rekam_sql(db) as q:
        KasirService(db).refund_item_tertunda(
            id_resep=r.id_resep, alasan="uji T3-2", metode_refund="TUNAI",
            actor_id_staf=staf.id_staf)
    assert _berkunci(q, "kunjungan_resep") and _berkunci(q, "transaksi_refund")
    db.refresh(r)
    assert V(r.status_item) == "BATAL"


# ---------------------------------------------------------------- T3-3
# Penerimaan barang: route memuat item PO lebih dulu; kunci `get_item_for_update` tanpa
# populate_existing mengembalikan salinan LAMA → pagar "melebihi sisa" dihitung dari angka
# basi → pesanan 10 diterima 20.
def _po_produk(db, staf, p, qty=10):
    from app.db.models import Pemesanan, PemesananItem
    from app.db.models._enums import StatusPemesananEnum
    po = Pemesanan(nomor_po=f"PO-UJI-{random.randint(10**6, 10**7)}", tgl_pemesanan=datetime.now(),
                   status=StatusPemesananEnum.ORDERED, id_staf_pemesan=staf.id_staf)
    db.add(po); db.flush()
    it = PemesananItem(id_pemesanan=po.id_pemesanan, tipe_item="PRODUK", id_produk=p.id_produk,
                       nama_snapshot=p.nama_produk, qty_dipesan=qty, qty_diterima=0)
    db.add(it); db.flush()
    return po, it


def _terima(db, staf, po, it, qty):
    from app.schemas.pengadaan import ReceiveItemRequest
    from app.services.pemesanan_service import PemesananService
    return PemesananService(db).receive_item(
        id_pemesanan=po.id_pemesanan,
        payload=ReceiveItemRequest(id_pemesanan_item=it.id_item, qty_diterima=qty,
                                   batch_no="UJI-T33", tgl_ed=date(2028, 1, 1),
                                   harga_terima=Decimal("4000")),
        actor=staf)


def test_terima_ganda_ditolak_walau_item_di_sesi_basi(db):
    from sqlalchemy import text
    from app.db.models._enums import StafRoleEnum
    from app.repositories.pemesanan_repo import PemesananRepository
    staf, _k = _siapkan(db)
    staf.role = StafRoleEnum.SUPERADMIN; db.flush()
    p, _ = _produk_dengan_lot(db, qty_lot=0)
    po, it = _po_produk(db, staf, p)
    PemesananRepository(db).get_items_by_po(po.id_pemesanan)        # seperti route: item dimuat
    db.execute(text("UPDATE pemesanan_item SET qty_diterima = 10 WHERE id_item = :i"),
               {"i": it.id_item})                                    # permintaan lain sudah terima
    assert float(it.qty_diterima) == 0                                # salinan di sesi masih lama
    with pytest.raises(HTTPException) as e:
        _terima(db, staf, po, it, 10)
    assert e.value.status_code == 400 and "melebihi sisa" in e.value.detail


def test_terima_bertahap_normal_lalu_kelebihan_ditolak(db):
    """Jalur biasa tetap utuh: 6 + 4 diterima (stok & lot naik), unit ke-11 ditolak."""
    from app.db.models._enums import StafRoleEnum
    staf, _k = _siapkan(db)
    staf.role = StafRoleEnum.SUPERADMIN; db.flush()
    p, _ = _produk_dengan_lot(db, qty_lot=0)
    po, it = _po_produk(db, staf, p)
    _terima(db, staf, po, it, 6)
    _terima(db, staf, po, it, 4)
    db.refresh(it); db.refresh(p)
    assert float(it.qty_diterima) == 10 and float(p.stok_terkini) == 10
    with pytest.raises(HTTPException):
        _terima(db, staf, po, it, 1)


# ---------------------------------------------------------------- T3-4
# Kepala faktur dulu menjumlah SEMUA item yang dicentang, termasuk yang GAGAL diterima.
def test_kepala_faktur_dihitung_ulang_dari_item_yang_diterima(db):
    from app.db.models import FakturPenerimaan, PemesananItem
    from app.db.models._enums import StafRoleEnum
    from app.schemas.pengadaan import ReceiveItemRequest
    from app.services.pemesanan_service import PemesananService
    staf, _k = _siapkan(db)
    staf.role = StafRoleEnum.SUPERADMIN; db.flush()
    pa, _ = _produk_dengan_lot(db, qty_lot=0)
    pb, _ = _produk_dengan_lot(db, qty_lot=0)
    po, ia = _po_produk(db, staf, pa)
    ia.harga_satuan = Decimal("50000")
    ib = PemesananItem(id_pemesanan=po.id_pemesanan, tipe_item="PRODUK", id_produk=pb.id_produk,
                       nama_snapshot=pb.nama_produk, qty_dipesan=2, qty_diterima=0,
                       harga_satuan=Decimal("1000000"))
    db.add(ib); db.flush()
    # Kepala seperti yang ditulis route: dari KEDUA item (2.500.000 × 1,11 = 2.775.000)
    fak = FakturPenerimaan(id_pemesanan=po.id_pemesanan, nomor_faktur="F-UJI-T34",
                           ppn_persen=Decimal("11"), id_staf_penerima=staf.id_staf,
                           subtotal_order=Decimal("2500000"), subtotal_setelah_diskon=Decimal("2500000"),
                           diskon_persen=Decimal("0"), extra_diskon=Decimal("0"),
                           total_ditagih=Decimal("2775000"))
    db.add(fak); db.flush()
    # Hanya 6 dari 10 unit A yang masuk; B "gagal". Sebagian (bukan penuh) supaya rumus yang
    # salah memakai qty PESANAN ikut ketahuan — suntikan itu sempat LOLOS saat A diterima penuh.
    PemesananService(db).receive_item(
        id_pemesanan=po.id_pemesanan,
        payload=ReceiveItemRequest(id_pemesanan_item=ia.id_item, qty_diterima=6, batch_no="T34",
                                   tgl_ed=date(2028, 1, 1), harga_terima=Decimal("50000"),
                                   id_faktur=fak.id_faktur),
        actor=staf)
    hasil = PemesananService(db).hitung_ulang_faktur(fak.id_faktur)
    db.refresh(fak)
    assert hasil["total_ditagih"] == Decimal("333000.00") == fak.total_ditagih   # 300.000 × 1,11
    assert fak.subtotal_order == Decimal("300000.00")


def test_route_faktur_menghitung_ulang_bila_ada_item_gagal():
    import inspect
    from app.web.routes import pengadaan
    src = inspect.getsource(pengadaan)
    blok = src[src.index('ok = f"{n_ok} item diterima'):]
    blok = blok[:blok.index("return RedirectResponse")]
    assert "if errors:" in blok and "hitung_ulang_faktur(" in blok and "db.commit()" in blok


# ---------------------------------------------------------------- T3-5
# Opname disetujui SESUDAH lot habis dipakai serah: selisih positif ditambahkan ke lot
# tapi status tetap HABIS → cache & FEFO (hanya AKTIF) tak melihatnya: stok tak terlihat.
def _opname_lot(db, staf, p, lot, qty_fisik):
    from app.db.models._enums import LokasiOpnameEnum
    from app.schemas.pengadaan import StockOpnameCreateRequest, StockOpnameItemInput
    from app.services.opname_service import OpnameService
    return OpnameService(db).create_opname(
        payload=StockOpnameCreateRequest(
            lokasi=LokasiOpnameEnum.RETAIL, catatan="uji T3-5",
            items=[StockOpnameItemInput(tipe_item="PRODUK", id_produk=p.id_produk,
                                        id_lot=lot.id_lot, qty_fisik=qty_fisik)]),
        actor=staf)


def test_opname_menghidupkan_lot_yang_habis(db):
    from app.db.models._enums import StafRoleEnum
    from app.services.opname_service import OpnameService
    staf, _k = _siapkan(db)
    staf.role = StafRoleEnum.SUPERADMIN; db.flush()
    p, lot = _produk_dengan_lot(db, qty_lot=5)
    op = _opname_lot(db, staf, p, lot, 7)                    # potret 5, fisik 7 → +2
    lot.qty_sisa = 0; lot.status = "HABIS"; p.stok_terkini = 0; db.flush()   # serah sesudah draf
    OpnameService(db).approve(op.id_opname, actor=staf)
    db.refresh(lot); db.refresh(p)
    assert (lot.status, float(lot.qty_sisa)) == ("AKTIF", 2.0)          # dulu HABIS / 2
    assert float(p.stok_terkini) == 2.0                                   # dulu 0 — tak terlihat
