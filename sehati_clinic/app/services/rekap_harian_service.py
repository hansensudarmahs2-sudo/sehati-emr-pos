"""
RekapHarianService — Rekap Harian Kasir Analitik (Kasir-2).

Laporan analitik HARIAN untuk owner (beda dari Kasir-1 yang soal rekonsiliasi kas).
Menjawab: "hari ini klinik ngapain aja?"

Metrik (semua EXCLUDE VOID — status_transaksi='BAYAR'):
1. Pasien berkunjung   : jumlah pasien unik yang punya kunjungan tgl ini.
2. Transaksi & omzet    : jumlah transaksi (incl beli-produk) + total rupiah + rata-rata.
3. Per metode bayar     : jumlah transaksi (distinct) + total rupiah per metode.
4. Single vs Split      : transaksi 1 metode vs >1 metode (count).
5. Konsultasi vs Retail : transaksi dari kunjungan klinis (ada tindakan/SOAP) vs
                          beli-produk murni (tanpa tindakan & tanpa pemeriksaan_klinis).
6. Per kasir            : jumlah transaksi + omzet per kasir.

Basis waktu: waktu_bayar (transaksi) & tgl_kunjungan (pasien) — konsisten omzet_harian.
"""

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.services import _refund_bukuan as _rb
# Kunjungan retur (RETUR_PASIEN) bukan kunjungan klinis — tidak dihitung (keputusan
# dr. Hansen 2026-10-05, DESAIN_RETUR_DARI_PASIEN.md §12).
from app.services._jenis_kunjungan import JENIS_KUNJUNGAN_BUKAN_KLINIS
from app.db.models import (
    Kunjungan,
    KunjunganTindakan,
    MasterStaf,
    PemeriksaanKlinis,
    TransaksiKasir,
    TransaksiPembayaran,
)


class RekapHarianService:
    def __init__(self, db: Session):
        self.db = db

    def rekap(self, tanggal: date) -> dict:
        db = self.db
        start = datetime.combine(tanggal, time.min)
        end = datetime.combine(tanggal, time.max)

        def _bayar_today(stmt):
            """Filter umum: transaksi BAYAR pada tanggal ini."""
            return (
                stmt.where(TransaksiKasir.status_transaksi == "BAYAR")
                .where(TransaksiKasir.waktu_bayar >= start)
                .where(TransaksiKasir.waktu_bayar <= end)
            )

        # ---- 1. Pasien berkunjung (unik) tgl ini ----
        pasien_berkunjung = db.execute(
            select(func.count(func.distinct(Kunjungan.id_pasien)))
            .where(Kunjungan.tgl_kunjungan >= start)
            .where(Kunjungan.tgl_kunjungan <= end)
            .where(Kunjungan.jenis_kunjungan.notin_(JENIS_KUNJUNGAN_BUKAN_KLINIS))
        ).scalar() or 0
        total_kunjungan = db.execute(
            select(func.count(Kunjungan.id_kunjungan))
            .where(Kunjungan.tgl_kunjungan >= start)
            .where(Kunjungan.tgl_kunjungan <= end)
            .where(Kunjungan.jenis_kunjungan.notin_(JENIS_KUNJUNGAN_BUKAN_KLINIS))
        ).scalar() or 0

        # ---- 2. Transaksi & omzet ----
        row = db.execute(_bayar_today(
            select(
                func.count(TransaksiKasir.id_transaksi),
                func.coalesce(func.sum(TransaksiKasir.total_tagihan), 0),
            )
        )).first()
        total_trx = int(row[0] or 0)
        # T32: refund dibukukan di HARI REFUND (bisa atas transaksi hari lampau).
        # Atribusi per metode & per kasir sama dengan tutup kasir (`_refund_bukuan`).
        total_refund = _rb.refund_total(db, start, end)
        total_omzet = Decimal(str(row[1] or 0)) - total_refund
        rata = (total_omzet / total_trx).quantize(Decimal("0.01")) if total_trx > 0 else Decimal("0")

        # ---- 3. Per metode bayar (jumlah transaksi distinct + rupiah) ----
        metode_rows = db.execute(_bayar_today(
            select(
                TransaksiPembayaran.metode_bayar,
                func.count(func.distinct(TransaksiPembayaran.id_transaksi)),
                func.coalesce(func.sum(TransaksiPembayaran.nominal), 0),
            ).join(TransaksiKasir, TransaksiPembayaran.id_transaksi == TransaksiKasir.id_transaksi)
            .group_by(TransaksiPembayaran.metode_bayar)
            .order_by(func.sum(TransaksiPembayaran.nominal).desc())
        )).all()
        _ref_metode = _rb.refund_per_metode(db, start, end)
        per_metode = [
            {"metode_bayar": str(m), "jumlah_transaksi": int(n),
             "total_nominal": Decimal(str(t or 0))
             - _ref_metode.pop(str(m or "TUNAI").upper(), Decimal("0"))}
            for m, n, t in metode_rows
        ]
        per_metode += [
            {"metode_bayar": m, "jumlah_transaksi": 0, "total_nominal": -v}
            for m, v in _ref_metode.items()
        ]

        # ---- 4. Single vs Split (jumlah pembayaran per transaksi) ----
        pay_count_rows = db.execute(_bayar_today(
            select(
                TransaksiPembayaran.id_transaksi,
                func.count(TransaksiPembayaran.id_pembayaran),
            ).join(TransaksiKasir, TransaksiPembayaran.id_transaksi == TransaksiKasir.id_transaksi)
            .group_by(TransaksiPembayaran.id_transaksi)
        )).all()
        n_single = sum(1 for _tid, c in pay_count_rows if int(c) <= 1)
        n_split = sum(1 for _tid, c in pay_count_rows if int(c) > 1)

        # ---- 5. Konsultasi vs Retail (beli-produk) ----
        # Kunjungan "klinis" = punya tindakan ATAU pemeriksaan_klinis (SOAP).
        klinis_tindakan = set(db.execute(
            select(func.distinct(KunjunganTindakan.id_kunjungan))
        ).scalars().all())
        klinis_soap = set(db.execute(
            select(func.distinct(PemeriksaanKlinis.id_kunjungan))
            # Draf apoteker belum menjadikan kunjungan itu "klinis".
            .where(PemeriksaanKlinis.status_soap == "FINAL")
        ).scalars().all())
        klinis_set = klinis_tindakan | klinis_soap

        trx_rows = db.execute(_bayar_today(
            select(TransaksiKasir.id_kunjungan, TransaksiKasir.total_tagihan)
        )).all()
        konsul_n = konsul_rp = 0
        retail_n = retail_rp = 0
        konsul_rp = Decimal("0")
        retail_rp = Decimal("0")
        for id_kunjungan, total in trx_rows:
            nilai = Decimal(str(total or 0))
            if id_kunjungan is not None and id_kunjungan in klinis_set:
                konsul_n += 1
                konsul_rp += nilai
            else:
                retail_n += 1
                retail_rp += nilai
        # T32: refund hari ini mengurangi golongan TRANSAKSI ASAL-nya (konsultasi/retail),
        # tanpa menambah hitungan transaksi.
        for id_kunjungan, nilai in _rb.refund_per_kunjungan(db, start, end):
            if id_kunjungan is not None and id_kunjungan in klinis_set:
                konsul_rp -= nilai
            else:
                retail_rp -= nilai

        # ---- 6. Per kasir ----
        kasir_rows = db.execute(_bayar_today(
            select(
                TransaksiKasir.id_staf_kasir,
                MasterStaf.nama_staf,
                func.count(TransaksiKasir.id_transaksi),
                func.coalesce(func.sum(TransaksiKasir.total_tagihan), 0),
            ).join(MasterStaf, TransaksiKasir.id_staf_kasir == MasterStaf.id_staf)
            .group_by(TransaksiKasir.id_staf_kasir, MasterStaf.nama_staf)
            .order_by(func.sum(TransaksiKasir.total_tagihan).desc())
        )).all()
        _ref_staf = _rb.refund_per_staf(db, start, end)
        per_kasir = [
            {"id_staf_kasir": int(i), "nama_kasir": str(nm),
             "jumlah_transaksi": int(n),
             "total_omzet": Decimal(str(t or 0)) - _ref_staf.pop(int(i), Decimal("0"))}
            for i, nm, n, t in kasir_rows
        ]
        for id_staf, nilai in _ref_staf.items():
            staf = db.get(MasterStaf, id_staf)
            per_kasir.append({
                "id_staf_kasir": id_staf,
                "nama_kasir": staf.nama_staf if staf else f"staf #{id_staf}",
                "jumlah_transaksi": 0, "total_omzet": -nilai,
            })

        return {
            "tanggal": tanggal,
            "pasien_berkunjung": int(pasien_berkunjung),
            "total_kunjungan": int(total_kunjungan),
            "total_transaksi": total_trx,
            "total_omzet": total_omzet,
            "total_refund": total_refund,
            "rata_per_transaksi": rata,
            "per_metode": per_metode,
            "single_count": n_single,
            "split_count": n_split,
            "konsultasi": {"jumlah": konsul_n, "total": konsul_rp},
            "retail": {"jumlah": retail_n, "total": retail_rp},
            "per_kasir": per_kasir,
        }


__all__ = ["RekapHarianService"]
