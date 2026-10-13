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
