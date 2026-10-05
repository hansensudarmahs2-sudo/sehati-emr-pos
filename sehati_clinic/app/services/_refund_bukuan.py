"""Pembukuan refund menurut TANGGAL REFUND — satu definisi untuk semua laporan uang.

T32 (keputusan dr. Hansen 2026-10-05, Project_Memory/DESAIN_T32_REFUND_HARI_LAMPAU.md):
refund TIDAK lagi mengurangi `transaksi_kasir.total_tagihan` transaksi asal. Laporan
yang menjumlah omzet wajib mengurangi refund lewat modul ini, supaya:

  - hari ASAL tetap seperti saat tutup kasir & saat diekspor ke Finance;
  - hari REFUND yang menanggungnya — hari uangnya benar-benar keluar laci.

Atribusinya sama dengan tutup kasir (`kasir_closing_service`), yang sudah benar sejak
#54-F: per PELAKU refund (`id_staf_refund`) dan per `metode_refund`.

Kenapa satu modul: dulu ada 12 titik agregasi yang "otomatis benar" karena header
dimutasi. Sekarang setiap titik harus memanggil sesuatu — kalau masing-masing menulis
query refund sendiri, salah satunya PASTI berbeda (filter status, kolom tanggal).
Itu pola CLAUDE.md §4.1 yang paling sering menggigit proyek ini.

⚠ Refund atas transaksi yang kemudian VOID tidak dihitung: transaksinya sudah keluar
penuh dari omzet. Sejak T32 void atas transaksi ber-refund ditolak, jadi ini hanya
menjaga data lama.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.db.models import TransaksiKasir, TransaksiRefund


def _dasar(stmt, start: datetime, end: datetime):
    return (
        stmt.join(TransaksiKasir, TransaksiKasir.id_transaksi == TransaksiRefund.id_transaksi)
        .where(TransaksiKasir.status_transaksi == "BAYAR")
        .where(TransaksiRefund.tgl_refund >= start)
        .where(TransaksiRefund.tgl_refund <= end)
    )


def _d(x) -> Decimal:
    return Decimal(str(x or 0))


def refund_total(db: Session, start: datetime, end: datetime) -> Decimal:
    """Total refund yang dibukukan pada rentang [start, end]."""
    return _d(db.execute(_dasar(
        select(func.coalesce(func.sum(TransaksiRefund.nilai_refund), 0)), start, end
    )).scalar())


def refund_per_staf(db: Session, start: datetime, end: datetime) -> dict[int, Decimal]:
    """{id_staf_refund: total} — pelaku refund, sama dengan tutup kasir."""
    rows = db.execute(_dasar(
        select(TransaksiRefund.id_staf_refund, func.sum(TransaksiRefund.nilai_refund)),
        start, end,
    ).group_by(TransaksiRefund.id_staf_refund)).all()
    return {int(i): _d(t) for i, t in rows if i is not None}


def refund_per_metode(db: Session, start: datetime, end: datetime) -> dict[str, Decimal]:
    """{METODE: total}. Dinormalkan .upper() + default TUNAI, sama dengan tutup kasir."""
    out: dict[str, Decimal] = {}
    rows = db.execute(_dasar(
        select(TransaksiRefund.metode_refund, func.sum(TransaksiRefund.nilai_refund)),
        start, end,
    ).group_by(TransaksiRefund.metode_refund)).all()
    for m, t in rows:
        k = (m or "TUNAI").upper()
        out[k] = out.get(k, Decimal("0")) + _d(t)
    return out


def refund_per_tanggal(db: Session, start: datetime, end: datetime) -> dict:
    """{date: total} — untuk laporan per hari (ekspor ringkasan harian)."""
    rows = db.execute(_dasar(
        select(func.date(TransaksiRefund.tgl_refund), func.sum(TransaksiRefund.nilai_refund)),
        start, end,
    ).group_by(func.date(TransaksiRefund.tgl_refund))).all()
    return {d: _d(t) for d, t in rows}


def refund_per_bulan(db: Session, start: datetime, end: datetime) -> dict[int, Decimal]:
    """{bulan(1-12): total} — untuk omzet bulanan (rentang dalam satu tahun)."""
    rows = db.execute(_dasar(
        select(extract("month", TransaksiRefund.tgl_refund), func.sum(TransaksiRefund.nilai_refund)),
        start, end,
    ).group_by(extract("month", TransaksiRefund.tgl_refund))).all()
    return {int(b): _d(t) for b, t in rows}


def refund_per_kunjungan(
    db: Session, start: datetime, end: datetime
) -> list[tuple[Optional[int], Decimal]]:
    """[(id_kunjungan transaksi asal, nilai)] — untuk pembagian konsultasi/retail."""
    rows = db.execute(_dasar(
        select(TransaksiKasir.id_kunjungan, TransaksiRefund.nilai_refund), start, end,
    )).all()
    return [(k, _d(t)) for k, t in rows]


__all__ = [
    "refund_total", "refund_per_staf", "refund_per_metode",
    "refund_per_tanggal", "refund_per_bulan", "refund_per_kunjungan",
]
