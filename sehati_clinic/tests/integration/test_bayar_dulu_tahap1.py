"""Bayar dulu tahap 1 (2026-10-21) — Project_Memory/DESAIN_BAYAR_DULU_BERCABANG.md.

T1-1: migrasi 20261021_0100 — `kunjungan_tindakan.id_transaksi` (+ BATAL, PRABAYAR,
`transaksi_refund.id_kunjungan_tindakan`) dan backfillnya.
"""
import importlib.util
import pathlib
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.db.models import KunjunganTindakan
from tests.integration.test_audit_tahap2 import (V, _siapkan, _bayar, _tindakan_selesai,  # noqa: F401
                                                 _trx_terakhir, db)


def _muat_migrasi():
    path = (pathlib.Path(__file__).parents[2]
            / "migrations/versions/20261021_0100_bayar_dulu_tahap1.py")
    spec = importlib.util.spec_from_file_location("mig_bayar_dulu_t1", path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    return mig


def _tindakan_lunas(db, snapshot=True):
    """Tindakan SELESAI yang sudah DIBAYAR, lalu dikembalikan ke keadaan 'data lama':
    id_transaksi NULL (kolomnya baru). snapshot=False meniru data pra-F3."""
    staf, k = _siapkan(db)
    _tindakan_selesai(db, k, detik=-5)      # selesai SEBELUM bayar
    _bayar(db, k, staf)
    trx = _trx_terakhir(db, k)
    t = db.execute(select(KunjunganTindakan).where(
        KunjunganTindakan.id_kunjungan == k.id_kunjungan)).scalar_one()
    if not snapshot:
        db.execute(text("DELETE FROM transaksi_detail_tindakan WHERE id_transaksi = :t"),
                   {"t": trx.id_transaksi})
    db.execute(text("UPDATE kunjungan_tindakan SET id_transaksi = NULL "
                    "WHERE id_kunjungan_tindakan = :i"), {"i": t.id_kunjungan_tindakan})
    db.flush(); db.expire(t)
    return t, trx


def test_backfill_dari_snapshot(db):
    mig = _muat_migrasi()
    t, trx = _tindakan_lunas(db, snapshot=True)
    assert t.id_transaksi is None
    hasil = mig.isi_id_transaksi_tindakan(db.connection())
    db.expire(t)
    assert t.id_transaksi == trx.id_transaksi
    assert hasil["dari_snapshot"] >= 1


def test_backfill_dari_cutoff_pra_f3(db):
    mig = _muat_migrasi()
    t, trx = _tindakan_lunas(db, snapshot=False)
    assert trx.waktu_bayar >= t.waktu_selesai
    hasil = mig.isi_id_transaksi_tindakan(db.connection())
    db.expire(t)
    assert t.id_transaksi == trx.id_transaksi
    assert hasil["dari_cutoff"] >= 1


def test_backfill_aman_dijalankan_ulang(db):
    mig = _muat_migrasi()
    _tindakan_lunas(db, snapshot=True)
    _tindakan_lunas(db, snapshot=False)
    mig.isi_id_transaksi_tindakan(db.connection())
    kedua = mig.isi_id_transaksi_tindakan(db.connection())
    assert kedua["dari_snapshot"] == 0 and kedua["dari_cutoff"] == 0
