"""
Tutup Kasir — HARD BLOCK bila masih ada pasien antri hari ini (keputusan dr. Hansen
2026-07-10). Alasan: status antri yang tertinggal tak auto-transisi (menggantung);
harus diselesaikan (bayar/serah) atau FO ubah statusnya dulu sebelum kasir ditutup.

Set "aktif/antri" = semua status KECUALI terminal (COMPLETED, BATAL).

Sifat test: NON-DESTRUKTIF (fixture `db` rollback; guard me-raise SEBELUM commit).
"""
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.db.session import SessionLocal
from app.db.models import Kunjungan, MasterStaf, KasirClosing
from app.services.kasir_closing_service import KasirClosingService


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _first_kunjungan(db):
    k = db.query(Kunjungan).first()
    if k is None:
        pytest.skip("Butuh minimal 1 baris kunjungan.")
    return k


def test_pending_helper_deteksi_status_aktif(db):
    k = _first_kunjungan(db)
    k.status_antrian = "ANTRI_OBAT"
    k.tgl_kunjungan = datetime.now()
    db.flush()
    pend = KasirClosingService(db)._pending_antrian_hari_ini()
    assert pend.get("ANTRI_OBAT", 0) >= 1


def test_pending_helper_kecualikan_terminal(db):
    k = _first_kunjungan(db)
    k.status_antrian = "COMPLETED"
    k.tgl_kunjungan = datetime.now()
    db.flush()
    pend = KasirClosingService(db)._pending_antrian_hari_ini()
    assert "COMPLETED" not in pend and "BATAL" not in pend


def test_tutup_kasir_ditolak_saat_ada_pasien_antri(db):
    staf = db.query(MasterStaf).first()
    if staf is None:
        pytest.skip("Butuh master_staf.")
    # Sesi OPEN untuk kasir ini.
    sesi = KasirClosing(
        id_staf_kasir=staf.id_staf, shift_mulai=datetime.now(),
        status="OPEN", modal_awal=0, id_staf_buka=staf.id_staf,
    )
    db.add(sesi); db.flush()
    # Pasien masih antri hari ini.
    k = _first_kunjungan(db)
    k.status_antrian = "ANTRI_OBAT"
    k.tgl_kunjungan = datetime.now()
    db.flush()

    with pytest.raises(HTTPException) as ei:
        KasirClosingService(db).tutup_kasir(staf.id_staf, {"TUNAI": 0})
    assert ei.value.status_code == 400
    assert "belum selesai" in ei.value.detail.lower() or "antri" in ei.value.detail.lower()
