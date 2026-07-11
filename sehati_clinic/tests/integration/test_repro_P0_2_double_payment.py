"""
P0-2 (AUDIT_SEHATI_2026-07-10) — backstop DB anti double-submit pembayaran.

Klarifikasi domain (dr. Hansen, 2026-07-10): SPLIT/PARTIAL BILLING NYATA — satu
kunjungan BOLEH punya >1 transaksi BAYAR hidup. Maka dedupe di-key ke INTENT
pembayaran (token per-submit), BUKAN ke id_kunjungan. Yang harus ditolak =
"submit pembayaran yang SAMA diproses dua kali" (double-click/retry/race).

Fix (terpasang):
- Kolom `transaksi_kasir.idempotency_key` + UNIQUE index
  `uq_transaksi_kasir_idempotency_key` (migrasi 20260710_2100). NULL boleh duplikat
  (baris lama / split tanpa token tidak bentrok).
- `proses_bayar` mengunci baris kunjungan (`SELECT ... FOR UPDATE`) + mengisi
  idempotency_key dari token form; submit identik yang diulang → IntegrityError →
  ditangani ramah (bukan 500, bukan transaksi ganda).

Sifat test: NON-DESTRUKTIF (fixture `db` rollback; hanya flush).
Run: .venv/bin/pytest tests/integration/test_repro_P0_2_double_payment.py -v
"""
import pytest
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.db.models import Kunjungan, MasterStaf, TransaksiKasir


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _bayar_trx(kunjungan_id, staf_id, idem=None, total=50000):
    return TransaksiKasir(
        id_kunjungan=kunjungan_id, id_staf_kasir=staf_id,
        rincian_tagihan="repro P0-2", total_tagihan=total,
        status_transaksi="BAYAR", idempotency_key=idem,
    )


def _staf_kunjungan(db):
    staf = db.query(MasterStaf).first()
    kunjungan = db.query(Kunjungan).first()
    if staf is None or kunjungan is None:
        pytest.skip("Butuh minimal 1 baris master_staf dan 1 baris kunjungan di DB test.")
    return staf, kunjungan


def test_idempotency_key_sama_ditolak_split_dgn_key_beda_boleh(db):
    """Submit identik (idempotency key SAMA) DITOLAK; split billing (key BEDA) BOLEH."""
    staf, kunjungan = _staf_kunjungan(db)
    kid = kunjungan.id_kunjungan
    key = "repro-P0-2-idem-001"

    # Submit #1.
    db.add(_bayar_trx(kid, staf.id_staf, idem=key)); db.flush()

    # Submit #2 IDENTIK (key sama) → UNIQUE menolak.
    ditolak = False
    try:
        db.add(_bayar_trx(kid, staf.id_staf, idem=key)); db.flush()
    except IntegrityError:
        ditolak = True
    assert ditolak, "Double-submit dgn idempotency key sama HARUS ditolak DB (UNIQUE)."

    # Reset sesi (IntegrityError mengabort transaksi), lalu buktikan split SAH lolos.
    db.rollback()
    staf, kunjungan = _staf_kunjungan(db)
    kid = kunjungan.id_kunjungan
    db.add(_bayar_trx(kid, staf.id_staf, idem="repro-P0-2-idem-A")); db.flush()
    db.add(_bayar_trx(kid, staf.id_staf, idem="repro-P0-2-idem-B")); db.flush()  # tak boleh raise


def test_idempotency_key_null_boleh_duplikat(db):
    """NULL idempotency_key SENGAJA boleh duplikat (MySQL) → baris lama / tanpa token
    tidak saling bentrok. Ini yang membuat backstop aman terhadap split & data lama."""
    staf, kunjungan = _staf_kunjungan(db)
    kid = kunjungan.id_kunjungan
    db.add(_bayar_trx(kid, staf.id_staf, idem=None)); db.flush()
    db.add(_bayar_trx(kid, staf.id_staf, idem=None)); db.flush()  # tak boleh raise
