"""
ReportsService — laporan agregat.

Phase 1:
- omzet_harian(tanggal) → total + per kasir + per metode
- omzet_bulanan(tahun, bulan_dari, bulan_sampai) → per bulan + per metode agregat
- top_treatment(tgl_dari, tgl_sampai, status_filter, limit) → ranking treatment

Read-only — no audit hooks (laporan tidak mutating).
"""

from calendar import monthrange
from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import extract, func, select, case
from sqlalchemy.orm import Session

from app.services import _refund_bukuan as _rb
from app.db.models import (
    KunjunganTindakan,
    MasterStaf,
    MasterTreatment,
    StatusTindakanEnum,
    TransaksiKasir,
    TransaksiPembayaran,
)
from app.schemas.reports import (
    OmzetBulananResponse,
    OmzetHarianResponse,
    OmzetPerBulan,
    OmzetPerKasir,
    OmzetPerMetode,
    TopTreatmentItem,
    TopTreatmentResponse,
)


_BULAN_LABEL = [
    "", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
    "Jul", "Agu", "Sep", "Okt", "Nov", "Des",
]


class ReportsService:
    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # OMZET HARIAN
    # =========================================================================
    def omzet_harian(self, tanggal: date) -> OmzetHarianResponse:
        start = datetime.combine(tanggal, time.min)
        end = datetime.combine(tanggal, time.max)

        stmt_total = (
            select(
                func.count(TransaksiKasir.id_transaksi).label("count"),
                func.coalesce(func.sum(TransaksiKasir.total_tagihan), 0).label("total"),
                func.coalesce(func.sum(TransaksiKasir.nominal_diskon), 0).label("diskon"),
            )
            .where(TransaksiKasir.waktu_bayar >= start)
            .where(TransaksiKasir.waktu_bayar <= end)
            .where(TransaksiKasir.status_transaksi == "BAYAR")  # A1: exclude VOID
        )
        row = self.db.execute(stmt_total).first()
        total_trx = int(row[0] or 0)
        total_diskon = Decimal(str(row[2] or 0))
        # T32: refund dibukukan di HARI REFUND, bukan hari transaksi asal.
        total_refund = _rb.refund_total(self.db, start, end)
        total_omzet = Decimal(str(row[1] or 0)) - total_refund
        rata = (total_omzet / total_trx) if total_trx > 0 else Decimal("0")
        rata = rata.quantize(Decimal("0.01"))

        stmt_kasir = (
            select(
                TransaksiKasir.id_staf_kasir,
                MasterStaf.nama_staf,
                func.count(TransaksiKasir.id_transaksi).label("count"),
                func.coalesce(func.sum(TransaksiKasir.total_tagihan), 0).label("total"),
            )
            .join(MasterStaf, TransaksiKasir.id_staf_kasir == MasterStaf.id_staf)
            .where(TransaksiKasir.waktu_bayar >= start)
            .where(TransaksiKasir.waktu_bayar <= end)
            .where(TransaksiKasir.status_transaksi == "BAYAR")  # A1: exclude VOID
            .group_by(TransaksiKasir.id_staf_kasir, MasterStaf.nama_staf)
            .order_by(func.sum(TransaksiKasir.total_tagihan).desc())
        )
        # T32: refund dikurangkan dari PELAKU refund (sama dengan tutup kasir), supaya
        # jumlah per kasir tetap = total_omzet. Pelaku yang tak punya penjualan hari ini
        # tetap muncul (omzet negatif) — kalau disembunyikan, jumlahnya tak lagi cocok.
        _ref_staf = _rb.refund_per_staf(self.db, start, end)
        per_kasir = []
        for r in self.db.execute(stmt_kasir).all():
            per_kasir.append(OmzetPerKasir(
                id_staf_kasir=int(r[0]),
                nama_kasir=str(r[1]),
                jumlah_transaksi=int(r[2]),
                total_omzet=Decimal(str(r[3] or 0)) - _ref_staf.pop(int(r[0]), Decimal("0")),
            ))
        for id_staf, nilai in _ref_staf.items():
            staf = self.db.get(MasterStaf, id_staf)
            per_kasir.append(OmzetPerKasir(
                id_staf_kasir=id_staf,
                nama_kasir=staf.nama_staf if staf else f"staf #{id_staf}",
                jumlah_transaksi=0,
                total_omzet=-nilai,
            ))

        stmt_metode = (
            select(
                TransaksiPembayaran.metode_bayar,
                func.count(TransaksiPembayaran.id_pembayaran).label("count"),
                func.coalesce(func.sum(TransaksiPembayaran.nominal), 0).label("total"),
            )
            .join(TransaksiKasir, TransaksiPembayaran.id_transaksi == TransaksiKasir.id_transaksi)
            .where(TransaksiKasir.waktu_bayar >= start)
            .where(TransaksiKasir.waktu_bayar <= end)
            .where(TransaksiKasir.status_transaksi == "BAYAR")  # A1: exclude VOID
            .group_by(TransaksiPembayaran.metode_bayar)
            .order_by(func.sum(TransaksiPembayaran.nominal).desc())
        )
        # T32: refund dikurangkan per metode_refund, sama dengan tutup kasir.
        _ref_metode = _rb.refund_per_metode(self.db, start, end)
        per_metode = []
        for r in self.db.execute(stmt_metode).all():
            per_metode.append(OmzetPerMetode(
                metode_bayar=str(r[0]),
                jumlah_pembayaran=int(r[1]),
                total_nominal=Decimal(str(r[2] or 0))
                - _ref_metode.pop(str(r[0] or "TUNAI").upper(), Decimal("0")),
            ))
        for metode, nilai in _ref_metode.items():
            per_metode.append(OmzetPerMetode(
                metode_bayar=metode, jumlah_pembayaran=0, total_nominal=-nilai,
            ))

        return OmzetHarianResponse(
            tanggal=tanggal,
            waktu_rekap=datetime.now(),
            total_transaksi=total_trx,
            total_omzet=total_omzet,
            total_diskon=total_diskon,
            total_refund=total_refund,
            rata_per_transaksi=rata,
            per_kasir=per_kasir,
            per_metode=per_metode,
        )

    # =========================================================================
    # OMZET BULANAN
    # =========================================================================
    def omzet_bulanan(
        self,
        tahun: int,
        bulan_dari: int = 1,
        bulan_sampai: int = 12,
    ) -> OmzetBulananResponse:
        if not (2020 <= tahun <= 2099):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tahun tidak valid")
        if not (1 <= bulan_dari <= 12) or not (1 <= bulan_sampai <= 12):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bulan harus 1-12")
        if bulan_dari > bulan_sampai:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "bulan_dari > bulan_sampai")

        start = datetime.combine(date(tahun, bulan_dari, 1), time.min)
        last_day = monthrange(tahun, bulan_sampai)[1]
        end = datetime.combine(date(tahun, bulan_sampai, last_day), time.max)

        stmt_bulan = (
            select(
                extract("month", TransaksiKasir.waktu_bayar).label("bulan"),
                func.count(TransaksiKasir.id_transaksi).label("count"),
                func.coalesce(func.sum(TransaksiKasir.total_tagihan), 0).label("total"),
                func.coalesce(func.sum(TransaksiKasir.nominal_diskon), 0).label("diskon"),
            )
            .where(TransaksiKasir.waktu_bayar >= start)
            .where(TransaksiKasir.waktu_bayar <= end)
            .where(TransaksiKasir.status_transaksi == "BAYAR")  # A1: exclude VOID
            .group_by(extract("month", TransaksiKasir.waktu_bayar))
            .order_by(extract("month", TransaksiKasir.waktu_bayar))
        )
        rows = {int(r[0]): (int(r[1]), Decimal(str(r[2] or 0)), Decimal(str(r[3] or 0)))
                for r in self.db.execute(stmt_bulan).all()}

        # T32: refund dibukukan di BULAN refund-nya, bukan bulan transaksi asal.
        _ref_bulan = _rb.refund_per_bulan(self.db, start, end)

        per_bulan = []
        for b in range(bulan_dari, bulan_sampai + 1):
            count, omzet, diskon = rows.get(b, (0, Decimal("0"), Decimal("0")))
            refund_b = _ref_bulan.get(b, Decimal("0"))
            omzet = omzet - refund_b
            rata_b = (omzet / count).quantize(Decimal("0.01")) if count > 0 else Decimal("0")
            per_bulan.append(OmzetPerBulan(
                tahun=tahun,
                bulan=b,
                bulan_label=f"{_BULAN_LABEL[b]} {tahun}",
                jumlah_transaksi=count,
                total_omzet=omzet,
                total_diskon=diskon,
                rata_per_transaksi=rata_b,
                total_refund=refund_b,
            ))

        total_trx = sum(b.jumlah_transaksi for b in per_bulan)
        total_omzet = sum((b.total_omzet for b in per_bulan), Decimal("0"))
        total_diskon = sum((b.total_diskon for b in per_bulan), Decimal("0"))
        total_refund = sum((b.total_refund for b in per_bulan), Decimal("0"))
        n_bulan = bulan_sampai - bulan_dari + 1
        rata_per_bulan = (total_omzet / n_bulan).quantize(Decimal("0.01")) if n_bulan > 0 else Decimal("0")

        peak_label, peak_omzet = "", Decimal("0")
        for b in per_bulan:
            if b.total_omzet > peak_omzet:
                peak_omzet = b.total_omzet
                peak_label = b.bulan_label

        stmt_metode = (
            select(
                TransaksiPembayaran.metode_bayar,
                func.count(TransaksiPembayaran.id_pembayaran).label("count"),
                func.coalesce(func.sum(TransaksiPembayaran.nominal), 0).label("total"),
            )
            .join(TransaksiKasir, TransaksiPembayaran.id_transaksi == TransaksiKasir.id_transaksi)
            .where(TransaksiKasir.waktu_bayar >= start)
            .where(TransaksiKasir.waktu_bayar <= end)
            .where(TransaksiKasir.status_transaksi == "BAYAR")  # A1: exclude VOID
            .group_by(TransaksiPembayaran.metode_bayar)
            .order_by(func.sum(TransaksiPembayaran.nominal).desc())
        )
        _ref_metode = _rb.refund_per_metode(self.db, start, end)
        per_metode = []
        for r in self.db.execute(stmt_metode).all():
            per_metode.append(OmzetPerMetode(
                metode_bayar=str(r[0]),
                jumlah_pembayaran=int(r[1]),
                total_nominal=Decimal(str(r[2] or 0))
                - _ref_metode.pop(str(r[0] or "TUNAI").upper(), Decimal("0")),
            ))
        for metode, nilai in _ref_metode.items():
            per_metode.append(OmzetPerMetode(
                metode_bayar=metode, jumlah_pembayaran=0, total_nominal=-nilai,
            ))

        return OmzetBulananResponse(
            tahun=tahun,
            bulan_dari=bulan_dari,
            bulan_sampai=bulan_sampai,
            waktu_rekap=datetime.now(),
            total_transaksi=total_trx,
            total_omzet=total_omzet,
            total_diskon=total_diskon,
            total_refund=total_refund,
            rata_per_bulan=rata_per_bulan,
            peak_bulan_label=peak_label,
            peak_bulan_omzet=peak_omzet,
            per_bulan=per_bulan,
            per_metode=per_metode,
        )

    # =========================================================================
    # TOP TREATMENT
    # =========================================================================
    def top_treatment(
        self,
        tgl_dari: date,
        tgl_sampai: date,
        status_filter: str = "SELESAI",
        limit: int = 50,
    ) -> TopTreatmentResponse:
        """
        Ranking treatment paling sering dilakukan + paling profitable.

        - status_filter: "SELESAI" (default) atau "ALL"
        - Filter by kunjungan_tindakan.waktu_selesai (atau waktu_mulai kalau SELESAI tidak ada)
        - Omzet = count × master_treatment.harga (estimasi, sebelum diskon membership)
        """
        if tgl_dari > tgl_sampai:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "tgl_dari > tgl_sampai")

        start = datetime.combine(tgl_dari, time.min)
        end = datetime.combine(tgl_sampai, time.max)

        # Build query: GROUP BY treatment, count + sum harga
        stmt = (
            select(
                MasterTreatment.id_treatment,
                MasterTreatment.nama_treatment,
                MasterTreatment.role_pelaksana,
                MasterTreatment.harga,
                func.count(KunjunganTindakan.id_kunjungan_tindakan).label("count"),
            )
            .join(MasterTreatment, MasterTreatment.id_treatment == KunjunganTindakan.id_treatment)
            .where(KunjunganTindakan.waktu_selesai >= start)
            .where(KunjunganTindakan.waktu_selesai <= end)
            .group_by(
                MasterTreatment.id_treatment,
                MasterTreatment.nama_treatment,
                MasterTreatment.role_pelaksana,
                MasterTreatment.harga,
            )
        )
        if status_filter == "SELESAI":
            stmt = stmt.where(KunjunganTindakan.status_tindakan == StatusTindakanEnum.SELESAI)
        # else status_filter == "ALL" → no status where

        rows = self.db.execute(stmt).all()

        # Hitung omzet per row + total
        prelim = []
        total_omzet = Decimal("0")
        total_count = 0
        for r in rows:
            cnt = int(r[4])
            harga = Decimal(str(r[3] or 0))
            omzet = harga * cnt
            total_omzet += omzet
            total_count += cnt
            prelim.append({
                "id_treatment": int(r[0]),
                "nama_treatment": str(r[1]),
                "role_pelaksana": str(r[2]),
                "harga_satuan": harga,
                "jumlah_dilakukan": cnt,
                "estimasi_omzet": omzet,
            })

        # Sort by omzet desc
        prelim.sort(key=lambda x: x["estimasi_omzet"], reverse=True)

        # Build items dengan rank + persen kontribusi
        items: list[TopTreatmentItem] = []
        paling_laris_label, paling_laris_count = "", 0
        paling_profitable_label, paling_profitable_omzet = "", Decimal("0")

        for idx, p in enumerate(prelim[:limit], start=1):
            persen = float(p["estimasi_omzet"] / total_omzet * 100) if total_omzet > 0 else 0.0
            items.append(TopTreatmentItem(
                rank=idx,
                id_treatment=p["id_treatment"],
                nama_treatment=p["nama_treatment"],
                role_pelaksana=p["role_pelaksana"],
                harga_satuan=p["harga_satuan"],
                jumlah_dilakukan=p["jumlah_dilakukan"],
                estimasi_omzet=p["estimasi_omzet"],
                persen_kontribusi=round(persen, 2),
            ))
            if p["jumlah_dilakukan"] > paling_laris_count:
                paling_laris_count = p["jumlah_dilakukan"]
                paling_laris_label = p["nama_treatment"]
            if p["estimasi_omzet"] > paling_profitable_omzet:
                paling_profitable_omzet = p["estimasi_omzet"]
                paling_profitable_label = p["nama_treatment"]

        return TopTreatmentResponse(
            tgl_dari=tgl_dari,
            tgl_sampai=tgl_sampai,
            status_filter=status_filter,
            waktu_rekap=datetime.now(),
            total_tindakan=total_count,
            total_estimasi_omzet=total_omzet,
            paling_laris_label=paling_laris_label,
            paling_laris_count=paling_laris_count,
            paling_profitable_label=paling_profitable_label,
            paling_profitable_omzet=paling_profitable_omzet,
            items=items,
        )


    # =========================================================================
    # KINERJA DOKTER
    # =========================================================================
    def kinerja_dokter(
        self,
        tgl_dari: date,
        tgl_sampai: date,
        force_id_staf_filter: Optional[int] = None,
    ) -> "KinerjaDokterResponse":
        """
        Stats kinerja per dokter dalam rentang tanggal:
        - jumlah_konsul (count distinct kunjungan dari pemeriksaan_klinis)
        - pasien_unique (count distinct id_pasien)
        - jumlah_tindakan (kunjungan_tindakan SELESAI yang link ke kunjungan dokter ini)
        - estimasi_omzet (sum master_treatment.harga × count)
        - conversion_rate = konsul_dengan_tindakan / jumlah_konsul × 100

        REPORTS-COMPART (#324): kalau `force_id_staf_filter` dipass, hasil
        filter ke 1 dokter saja. Dipakai saat role=DOKTER login (auto-filter
        ke own data), backend enforce — tidak bisa di-bypass via URL.
        """
        from app.db.models import (
            Kunjungan, PemeriksaanKlinis, KunjunganTindakan,
            MasterTreatment, MasterStaf, StatusTindakanEnum,
        )
        from app.schemas.reports import KinerjaDokterItem, KinerjaDokterResponse

        if tgl_dari > tgl_sampai:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "tgl_dari > tgl_sampai")

        start = datetime.combine(tgl_dari, time.min)
        end = datetime.combine(tgl_sampai, time.max)

        # Query 1 — Konsul + pasien unique per dokter
        stmt_konsul = (
            select(
                PemeriksaanKlinis.id_staf_dokter,
                MasterStaf.nama_staf,
                func.count(func.distinct(PemeriksaanKlinis.id_kunjungan)).label("konsul"),
                func.count(func.distinct(PemeriksaanKlinis.id_pasien)).label("pasien_unq"),
            )
            .join(Kunjungan, Kunjungan.id_kunjungan == PemeriksaanKlinis.id_kunjungan)
            .join(MasterStaf, MasterStaf.id_staf == PemeriksaanKlinis.id_staf_dokter)
            # Kinerja dokter dihitung dari SOAP yang sah saja, bukan draf apoteker.
            .where(PemeriksaanKlinis.status_soap == "FINAL")
            .where(Kunjungan.tgl_kunjungan >= start)
            .where(Kunjungan.tgl_kunjungan <= end)
            .where(PemeriksaanKlinis.id_staf_dokter.is_not(None))
            .group_by(PemeriksaanKlinis.id_staf_dokter, MasterStaf.nama_staf)
        )
        # REPORTS-COMPART (#324): apply forced filter di SQL level
        if force_id_staf_filter is not None:
            stmt_konsul = stmt_konsul.where(
                PemeriksaanKlinis.id_staf_dokter == force_id_staf_filter
            )
        konsul_rows = self.db.execute(stmt_konsul).all()

        per_dokter = {}
        for r in konsul_rows:
            id_dr = int(r[0])
            per_dokter[id_dr] = {
                "id_staf": id_dr,
                "nama_dokter": str(r[1]),
                "jumlah_konsul": int(r[2]),
                "pasien_unique": int(r[3]),
                "konsul_dengan_tindakan": 0,
                "jumlah_tindakan": 0,
                "estimasi_omzet": Decimal("0"),
            }

        # Query 2 — Tindakan dari kunjungan dokter ini (SELESAI only)
        stmt_tindakan = (
            select(
                PemeriksaanKlinis.id_staf_dokter,
                func.count(KunjunganTindakan.id_kunjungan_tindakan).label("n_tindakan"),
                func.count(func.distinct(KunjunganTindakan.id_kunjungan)).label("konsul_tindakan"),
                func.coalesce(func.sum(MasterTreatment.harga), 0).label("omzet"),
            )
            .join(Kunjungan, Kunjungan.id_kunjungan == PemeriksaanKlinis.id_kunjungan)
            .join(KunjunganTindakan, KunjunganTindakan.id_kunjungan == PemeriksaanKlinis.id_kunjungan)
            .where(PemeriksaanKlinis.status_soap == "FINAL")
            .join(MasterTreatment, MasterTreatment.id_treatment == KunjunganTindakan.id_treatment)
            .where(Kunjungan.tgl_kunjungan >= start)
            .where(Kunjungan.tgl_kunjungan <= end)
            .where(KunjunganTindakan.status_tindakan == StatusTindakanEnum.SELESAI)
            .where(PemeriksaanKlinis.id_staf_dokter.is_not(None))
            .group_by(PemeriksaanKlinis.id_staf_dokter)
        )
        # REPORTS-COMPART (#324): apply forced filter di query 2 juga
        if force_id_staf_filter is not None:
            stmt_tindakan = stmt_tindakan.where(
                PemeriksaanKlinis.id_staf_dokter == force_id_staf_filter
            )
        for r in self.db.execute(stmt_tindakan).all():
            id_dr = int(r[0])
            if id_dr not in per_dokter:
                continue  # dokter tidak ada di query 1, skip (rare edge)
            per_dokter[id_dr]["jumlah_tindakan"] = int(r[1])
            per_dokter[id_dr]["konsul_dengan_tindakan"] = int(r[2])
            per_dokter[id_dr]["estimasi_omzet"] = Decimal(str(r[3] or 0))

        # Sort by omzet desc, then by konsul desc
        sorted_list = sorted(
            per_dokter.values(),
            key=lambda x: (x["estimasi_omzet"], x["jumlah_konsul"]),
            reverse=True,
        )

        # Build items + summary
        items = []
        top_omzet_label, top_omzet_value = "", Decimal("0")
        total_konsul = 0
        total_tindakan = 0
        total_omzet = Decimal("0")

        for idx, d in enumerate(sorted_list, start=1):
            conv = (d["konsul_dengan_tindakan"] / d["jumlah_konsul"] * 100) if d["jumlah_konsul"] > 0 else 0.0
            items.append(KinerjaDokterItem(
                rank=idx,
                id_staf=d["id_staf"],
                nama_dokter=d["nama_dokter"],
                pasien_unique=d["pasien_unique"],
                jumlah_konsul=d["jumlah_konsul"],
                konsul_dengan_tindakan=d["konsul_dengan_tindakan"],
                jumlah_tindakan=d["jumlah_tindakan"],
                estimasi_omzet=d["estimasi_omzet"],
                conversion_rate=round(conv, 2),
            ))
            total_konsul += d["jumlah_konsul"]
            total_tindakan += d["jumlah_tindakan"]
            total_omzet += d["estimasi_omzet"]
            if d["estimasi_omzet"] > top_omzet_value:
                top_omzet_value = d["estimasi_omzet"]
                top_omzet_label = d["nama_dokter"]

        return KinerjaDokterResponse(
            tgl_dari=tgl_dari,
            tgl_sampai=tgl_sampai,
            waktu_rekap=datetime.now(),
            total_dokter=len(items),
            total_konsul=total_konsul,
            total_tindakan=total_tindakan,
            total_estimasi_omzet=total_omzet,
            top_omzet_label=top_omzet_label,
            top_omzet_value=top_omzet_value,
            items=items,
        )


    # =========================================================================
    # AUDIT LOG VIEWER (Owner / Superadmin)
    # =========================================================================
    def audit_log_list(
        self,
        tgl_dari: date,
        tgl_sampai: date,
        id_staf: int | None = None,
        aksi: str | None = None,
        tabel_target: str | None = None,
        status_aksi: str | None = None,
        view_filter: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> "AuditLogResponse":
        """
        Paginated audit log dengan multi-filter.
        Filter:
        - tgl_dari/sampai (rentang waktu)
        - id_staf (specific user, None = semua)
        - aksi (partial match case-insensitive)
        - tabel_target (exact)
        - status_aksi (SUCCESS/FAILED, None = semua)
        """
        from app.db.models import AuditLog, MasterStaf
        from app.schemas.reports import AuditLogItem, AuditLogResponse

        if tgl_dari > tgl_sampai:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "tgl_dari > tgl_sampai")
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 500:
            page_size = 100

        start = datetime.combine(tgl_dari, time.min)
        end = datetime.combine(tgl_sampai, time.max)

        # Base query — JOIN MasterStaf untuk nama + role
        base = (
            select(AuditLog, MasterStaf.nama_staf, MasterStaf.role)
            .outerjoin(MasterStaf, MasterStaf.id_staf == AuditLog.id_staf)
            .where(AuditLog.waktu >= start)
            .where(AuditLog.waktu <= end)
        )
        if id_staf is not None:
            base = base.where(AuditLog.id_staf == id_staf)
        if aksi:
            base = base.where(AuditLog.aksi.ilike(f"%{aksi}%"))
        if tabel_target:
            base = base.where(AuditLog.tabel_target == tabel_target)
        if status_aksi:
            base = base.where(AuditLog.status_aksi == status_aksi)
        if view_filter == "only":
            base = base.where(AuditLog.aksi == "VIEW")
        elif view_filter == "exclude":
            base = base.where(AuditLog.aksi != "VIEW")

        # Count total (before pagination)
        from sqlalchemy import func as _func
        count_stmt = (
            select(_func.count(AuditLog.id_log))
            .where(AuditLog.waktu >= start)
            .where(AuditLog.waktu <= end)
        )
        if id_staf is not None:
            count_stmt = count_stmt.where(AuditLog.id_staf == id_staf)
        if aksi:
            count_stmt = count_stmt.where(AuditLog.aksi.ilike(f"%{aksi}%"))
        if tabel_target:
            count_stmt = count_stmt.where(AuditLog.tabel_target == tabel_target)
        if status_aksi:
            count_stmt = count_stmt.where(AuditLog.status_aksi == status_aksi)
        if view_filter == "only":
            count_stmt = count_stmt.where(AuditLog.aksi == "VIEW")
        elif view_filter == "exclude":
            count_stmt = count_stmt.where(AuditLog.aksi != "VIEW")
        total_count = int(self.db.execute(count_stmt).scalar() or 0)
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        if page > total_pages:
            page = total_pages

        # Fetch page (newest first)
        offset = (page - 1) * page_size
        stmt = base.order_by(AuditLog.waktu.desc()).limit(page_size).offset(offset)

        items = []
        for row in self.db.execute(stmt).all():
            log_obj = row[0]
            nama = row[1]
            role_obj = row[2]
            role_value = role_obj.value if hasattr(role_obj, "value") else (str(role_obj) if role_obj else None)
            status_value = (
                log_obj.status_aksi.value
                if hasattr(log_obj.status_aksi, "value")
                else str(log_obj.status_aksi)
            )
            items.append(AuditLogItem(
                id_log=int(log_obj.id_log),
                waktu=log_obj.waktu,
                id_staf=log_obj.id_staf,
                nama_staf=nama,
                role_staf=role_value,
                aksi=log_obj.aksi,
                tabel_target=log_obj.tabel_target,
                id_target=log_obj.id_target,
                status_aksi=status_value,
                keterangan=log_obj.keterangan,
                data_lama=log_obj.data_lama,
                data_baru=log_obj.data_baru,
            ))

        return AuditLogResponse(
            tgl_dari=tgl_dari,
            tgl_sampai=tgl_sampai,
            filter_id_staf=id_staf,
            filter_aksi=aksi,
            filter_tabel=tabel_target,
            filter_status=status_aksi,
            waktu_rekap=datetime.now(),
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            items=items,
        )

    def audit_log_dropdowns(self) -> dict:
        """Helper: ambil list distinct tabel_target + list staff untuk filter dropdown."""
        from app.db.models import AuditLog, MasterStaf

        tabel_rows = self.db.execute(
            select(AuditLog.tabel_target).distinct().order_by(AuditLog.tabel_target.asc())
        ).all()
        tabel_list = [r[0] for r in tabel_rows if r[0]]

        aksi_rows = self.db.execute(
            select(AuditLog.aksi).distinct().order_by(AuditLog.aksi.asc())
        ).all()
        aksi_list = [r[0] for r in aksi_rows if r[0]]

        staf_rows = self.db.execute(
            select(MasterStaf.id_staf, MasterStaf.nama_staf, MasterStaf.role)
            .order_by(MasterStaf.nama_staf.asc())
        ).all()
        staf_list = [
            {
                "id_staf": int(r[0]),
                "nama_staf": str(r[1]),
                "role": r[2].value if hasattr(r[2], "value") else str(r[2]),
            }
            for r in staf_rows
        ]

        return {"tabel_list": tabel_list, "staf_list": staf_list, "aksi_list": aksi_list}

    # =========================================================================
    # REKAP KASIR SHIFT — REPORTS-COMPART (#324)
    # =========================================================================
    def rekap_kasir_shift(
        self,
        tgl: date,
        force_id_staf_filter: Optional[int] = None,
    ) -> dict:
        """
        Rekap shift kasir untuk tanggal tertentu.
        Kalau force_id_staf_filter dipass, hanya tampilkan kasir tsb (auto-filter Kasir).
        Owner/Superadmin/Admin tanpa filter = lihat semua kasir.

        Return dict: { tanggal, total_transaksi, total_omzet, per_kasir, per_metode }
        """
        start = datetime.combine(tgl, time.min)
        end = datetime.combine(tgl, time.max)

        # Per kasir (id_staf yang proses transaksi)
        stmt_kasir = (
            select(
                TransaksiKasir.id_staf_kasir,
                MasterStaf.nama_staf,
                func.count(TransaksiKasir.id_transaksi).label("jml_trx"),
                func.coalesce(func.sum(TransaksiKasir.total_tagihan), 0).label("omzet"),
            )
            .join(MasterStaf, MasterStaf.id_staf == TransaksiKasir.id_staf_kasir)
            .where(TransaksiKasir.waktu_bayar >= start)
            .where(TransaksiKasir.waktu_bayar <= end)
            .where(TransaksiKasir.status_transaksi == "BAYAR")  # A1: exclude VOID
            .group_by(TransaksiKasir.id_staf_kasir, MasterStaf.nama_staf)
            .order_by(func.sum(TransaksiKasir.total_tagihan).desc())
        )
        if force_id_staf_filter is not None:
            stmt_kasir = stmt_kasir.where(TransaksiKasir.id_staf_kasir == force_id_staf_filter)

        # T32: refund hari ini dikurangkan dari PELAKU refund (sama dengan tutup kasir).
        _ref_staf = _rb.refund_per_staf(self.db, start, end)
        if force_id_staf_filter is not None:
            _ref_staf = {k: v for k, v in _ref_staf.items() if k == force_id_staf_filter}

        per_kasir = []
        total_trx = 0
        total_omzet = Decimal("0")
        for r in self.db.execute(stmt_kasir).all():
            jml = int(r[2])
            refund_k = _ref_staf.pop(int(r[0]), Decimal("0"))
            omz = Decimal(str(r[3] or 0)) - refund_k
            per_kasir.append({
                "id_staf": int(r[0]),
                "nama_kasir": str(r[1]),
                "jumlah_transaksi": jml,
                "total_omzet": omz,
                "total_refund": refund_k,
            })
            total_trx += jml
            total_omzet += omz
        for id_staf, nilai in _ref_staf.items():
            staf = self.db.get(MasterStaf, id_staf)
            per_kasir.append({
                "id_staf": id_staf,
                "nama_kasir": staf.nama_staf if staf else f"staf #{id_staf}",
                "jumlah_transaksi": 0,
                "total_omzet": -nilai,
                "total_refund": nilai,
            })
            total_omzet -= nilai

        return {
            "tanggal": tgl,
            "total_transaksi": total_trx,
            "total_omzet": total_omzet,
            "per_kasir": per_kasir,
        }
    # =========================================================================
    # Phase 6 (#364 DEC-063) — VOID REPORT
    # =========================================================================
    def get_void_report(
        self,
        tgl_dari: date,
        tgl_sampai: date,
        page: int = 1,
        page_size: int = 100,
        kasir_id: Optional[int] = None,
        voider_id: Optional[int] = None,
        reason: Optional[str] = None,
    ):
        """Paginated void report dengan filter + summary stats.

        Filter berdasarkan void_at (kapan di-void), bukan waktu_bayar.
        """
        from app.db.models import TransaksiKasir, Kunjungan, Pasien, MasterStaf
        from app.schemas.reports import VoidReportItem, VoidReportResponse
        from sqlalchemy import select as _sel, func as _func, and_, or_
        from sqlalchemy.orm import aliased

        d_start = datetime.combine(tgl_dari, datetime.min.time())
        d_end = datetime.combine(tgl_sampai, datetime.max.time())

        # Two aliases for MasterStaf: kasir vs voider
        kasir_s = aliased(MasterStaf, name="kasir_s")
        voider_s = aliased(MasterStaf, name="voider_s")

        # Base where
        conditions = [
            TransaksiKasir.status_transaksi == "VOID",
            TransaksiKasir.void_at >= d_start,
            TransaksiKasir.void_at <= d_end,
        ]
        if kasir_id:
            conditions.append(TransaksiKasir.id_staf_kasir == kasir_id)
        if voider_id:
            conditions.append(TransaksiKasir.void_by_id_staf == voider_id)
        if reason:
            conditions.append(TransaksiKasir.void_reason_code == reason)

        # Count + summary
        summary_row = self.db.execute(
            _sel(
                _func.count(TransaksiKasir.id_transaksi),
                _func.coalesce(_func.sum(TransaksiKasir.total_tagihan), 0),
                _func.coalesce(_func.sum(case((TransaksiKasir.late_void == True, 1), else_=0)), 0),
            ).where(*conditions)
        ).first()
        total_count = int(summary_row[0] or 0) if summary_row else 0
        total_nominal = float(summary_row[1] or 0) if summary_row else 0.0
        late_count = int(summary_row[2] or 0) if summary_row else 0

        # Pagination
        if page_size <= 0:
            page_size = 100
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        if page < 1:
            page = 1
        if page > total_pages:
            page = total_pages
        offset = (page - 1) * page_size

        # Items
        stmt = (
            _sel(
                TransaksiKasir,
                Kunjungan.id_kunjungan,
                Pasien.no_rm,
                Pasien.nama,
                kasir_s.nama_staf.label("kasir_nama"),
                voider_s.nama_staf.label("voider_nama"),
            )
            .join(Kunjungan, Kunjungan.id_kunjungan == TransaksiKasir.id_kunjungan, isouter=True)
            .join(Pasien, Pasien.id_pasien == Kunjungan.id_pasien, isouter=True)
            .join(kasir_s, kasir_s.id_staf == TransaksiKasir.id_staf_kasir, isouter=True)
            .join(voider_s, voider_s.id_staf == TransaksiKasir.void_by_id_staf, isouter=True)
            .where(*conditions)
            .order_by(TransaksiKasir.void_at.desc())
            .limit(page_size).offset(offset)
        )
        rows = self.db.execute(stmt).all()

        items = []
        for row in rows:
            trx = row[0]
            items.append(VoidReportItem(
                id_transaksi=trx.id_transaksi,
                id_kunjungan=row[1],
                no_rm=row[2] or "-",
                nama_pasien=row[3] or "-",
                waktu_bayar=trx.waktu_bayar,
                void_at=trx.void_at,
                total_tagihan=float(trx.total_tagihan or 0),
                void_reason_code=trx.void_reason_code,
                void_reason_note=trx.void_reason_note,
                void_approval_method=trx.void_approval_method,
                late_void=bool(trx.late_void),
                kasir_nama=row[4],
                voider_nama=row[5],
            ))

        return VoidReportResponse(
            tgl_dari=tgl_dari,
            tgl_sampai=tgl_sampai,
            filter_kasir_id=kasir_id,
            filter_voider_id=voider_id,
            filter_reason=reason,
            waktu_rekap=datetime.now(),
            total_count=total_count,
            total_nominal=total_nominal,
            late_void_count=late_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            items=items,
        )



    # =========================================================================
    # #363B - Rekap Resep Dispensed Apoteker
    # =========================================================================
    def get_apoteker_dispensed_report(
        self,
        tgl_dari,
        tgl_sampai,
        apoteker_id=None,
        page: int = 1,
        page_size: int = 100,
    ):
        """Rekap resep yang sudah diserahkan apoteker dalam rentang tanggal.

        Strategy (sejak task #54, 2026-09-22):
        1. Baca `kunjungan_resep` yang `status_item='DISERAHKAN'` dengan `waktu_serah`
           dalam rentang — atribusi apoteker menempel per BARIS (`id_staf_serah`).
        2. Data LAMA (diserahkan sebelum status itu ada, itemnya masih 'DIBAYAR') tetap
           lewat jalur audit `SERAH_OBAT`, tapi hanya untuk kunjungan yang tidak punya
           satu pun baris DISERAHKAN — supaya tidak dihitung dua kali.
        3. JOIN master_produk, master_staf, pasien untuk enrich data

        CATATAN: racikan belum masuk laporan ini (skemanya per-produk); bahan racikan
        yang diserahkan tidak tampil sebagai baris tersendiri.

        Filter:
        - apoteker_id: filter spesifik apoteker (optional)
        """
        from datetime import date, datetime
        from sqlalchemy import select, func, and_
        from app.db.models import AuditLog, KunjunganResep, MasterProduk, Pasien, Kunjungan
        from app.db.models._enums import StatusItemResepEnum
        from app.schemas.reports import (
            ApotekerDispensedItem,
            ApotekerSummaryPerStaf,
            ApotekerDispensedResponse,
        )

        # Normalize dates
        if isinstance(tgl_dari, str):
            tgl_dari = date.fromisoformat(tgl_dari)
        if isinstance(tgl_sampai, str):
            tgl_sampai = date.fromisoformat(tgl_sampai)
        start_dt = datetime.combine(tgl_dari, datetime.min.time())
        end_dt = datetime.combine(tgl_sampai, datetime.max.time())

        # ------------------------------------------------------------------
        # Task #54 (2026-09-22) — sumber kebenaran pindah dari AUDIT LOG ke ITEM.
        #
        # Cara lama: cari audit `SERAH_OBAT` per kunjungan, lalu tarik SEMUA resep
        # DIBAYAR kunjungan itu. Dua kesalahan begitu satu kunjungan bisa diserahkan
        # lebih dari sekali (penyerahan sebagian):
        #   1. peta ber-key id_kunjungan → event kedua MENIMPA event pertama, apoteker
        #      pertama kehilangan kreditnya;
        #   2. "semua resep DIBAYAR" ikut menghitung item yang belum diserahkan, dan
        #      menghitungnya LAGI pada event berikutnya.
        # Sekarang tiap baris resep menyimpan sendiri `id_staf_serah` + `waktu_serah`,
        # jadi kreditnya per item dan tidak mungkin tertimpa.
        # ------------------------------------------------------------------
        _kolom = (
            KunjunganResep.id_resep,
            KunjunganResep.id_kunjungan,
            KunjunganResep.id_produk,
            KunjunganResep.qty,
            KunjunganResep.aturan_pakai,
            MasterProduk.kode_produk,
            MasterProduk.nama_produk,
            MasterProduk.harga_jual,
            Kunjungan.id_pasien,
            Pasien.no_rm,
            Pasien.nama.label("nama_pasien"),
        )

        def _dengan_join(stmt):
            return (
                stmt
                .join(MasterProduk, MasterProduk.id_produk == KunjunganResep.id_produk)
                .join(Kunjungan, Kunjungan.id_kunjungan == KunjunganResep.id_kunjungan)
                .join(Pasien, Pasien.id_pasien == Kunjungan.id_pasien)
            )

        # Step 1: item yang BENAR-BENAR diserahkan, dengan atribusi per baris.
        baru_stmt = _dengan_join(
            select(*_kolom,
                   KunjunganResep.id_staf_serah.label("id_staf_apoteker"),
                   KunjunganResep.waktu_serah.label("waktu_serah"))
            .where(KunjunganResep.status_item == StatusItemResepEnum.DISERAHKAN)
            .where(KunjunganResep.waktu_serah.is_not(None))
            .where(KunjunganResep.waktu_serah >= start_dt)
            .where(KunjunganResep.waktu_serah <= end_dt)
        )
        if apoteker_id is not None:
            baru_stmt = baru_stmt.where(KunjunganResep.id_staf_serah == apoteker_id)
        resep_rows = list(self.db.execute(baru_stmt.order_by(
            KunjunganResep.id_resep.desc())).all())

        # Step 1b: DATA LAMA — kunjungan yang diserahkan sebelum status DISERAHKAN ada,
        # sehingga itemnya masih tercatat DIBAYAR. Untuk itu jalur audit tetap dipakai,
        # TAPI hanya untuk kunjungan yang tidak punya satu pun baris DISERAHKAN — kalau
        # tidak, kunjungan yang sama akan terhitung dua kali oleh dua jalur.
        audit_stmt = (
            select(
                AuditLog.id_target.label("id_kunjungan"),
                AuditLog.id_staf.label("id_staf_apoteker"),
                AuditLog.waktu.label("waktu_serah"),
            )
            .where(AuditLog.aksi == "SERAH_OBAT")
            .where(AuditLog.tabel_target == "kunjungan")
            .where(AuditLog.waktu >= start_dt)
            .where(AuditLog.waktu <= end_dt)
        )
        if apoteker_id is not None:
            audit_stmt = audit_stmt.where(AuditLog.id_staf == apoteker_id)
        legacy_map = {}
        for row in self.db.execute(audit_stmt).all():
            legacy_map[row.id_kunjungan] = (row.id_staf_apoteker, row.waktu_serah)
        if legacy_map:
            sudah_per_item = set(self.db.execute(
                select(KunjunganResep.id_kunjungan)
                .where(KunjunganResep.id_kunjungan.in_(list(legacy_map.keys())))
                .where(KunjunganResep.status_item == StatusItemResepEnum.DISERAHKAN)
                .distinct()
            ).scalars().all())
            for _idk in list(legacy_map.keys()):
                if _idk in sudah_per_item:
                    del legacy_map[_idk]
        if legacy_map:
            legacy_rows = list(self.db.execute(_dengan_join(
                select(*_kolom)
                .where(KunjunganResep.id_kunjungan.in_(list(legacy_map.keys())))
                .where(KunjunganResep.status_item == StatusItemResepEnum.DIBAYAR)
            ).order_by(KunjunganResep.id_resep.desc())).all())
            # Bungkus jadi bentuk yang sama: atribusi diambil dari audit kunjungannya.
            from types import SimpleNamespace as _NS
            for _r in legacy_rows:
                _apt, _wkt = legacy_map[_r.id_kunjungan]
                resep_rows.append(_NS(**_r._mapping, id_staf_apoteker=_apt,
                                      waktu_serah=_wkt))

        # Step 1c (2026-09-30): RACIKAN yang diserahkan. Sebelum ini laporan apoteker
        # hanya membaca `kunjungan_resep`, sehingga penyerahan racikan tidak terlihat
        # sama sekali — apoteker yang seharian meracik tampak tidak mengerjakan apa pun.
        # Atribusinya memakai kolom yang sama (`id_staf_serah` / `waktu_serah`) yang
        # memang sudah ada di `kunjungan_racikan` sejak task #54.
        from types import SimpleNamespace as _NS2
        from app.db.models.racikan import KunjunganRacikan as _KRC2
        _racik_stmt = (
            select(_KRC2, Pasien.no_rm, Pasien.nama.label("nama_pasien"))
            .join(Kunjungan, Kunjungan.id_kunjungan == _KRC2.id_kunjungan)
            .join(Pasien, Pasien.id_pasien == Kunjungan.id_pasien)
            .where(_KRC2.status_item == "DISERAHKAN")
            .where(_KRC2.waktu_serah.is_not(None))
            .where(_KRC2.waktu_serah >= start_dt)
            .where(_KRC2.waktu_serah <= end_dt)
        )
        if apoteker_id is not None:
            _racik_stmt = _racik_stmt.where(_KRC2.id_staf_serah == apoteker_id)
        for _rc, _norm, _nmpas in self.db.execute(_racik_stmt).all():
            resep_rows.append(_NS2(
                id_kunjungan=_rc.id_kunjungan,
                id_resep=None, id_produk=None, kode_produk=None,
                nama_produk=_rc.nama_snapshot,
                # qty=1 supaya subtotal = harga_jual; harga_jual dipakai sebagai
                # TOTAL racikan (bahan + ongkos racik) yang sudah terkunci.
                qty=1, harga_jual=_rc.total,
                aturan_pakai=_rc.aturan_pakai,
                no_rm=_norm, nama_pasien=_nmpas,
                id_staf_apoteker=_rc.id_staf_serah, waktu_serah=_rc.waktu_serah,
                is_racikan=True, jenis_racik=_rc.jenis_racik,
                jumlah_unit=int(_rc.jumlah_unit or 0),
            ))

        if not resep_rows:
            return ApotekerDispensedResponse(
                tgl_dari=tgl_dari, tgl_sampai=tgl_sampai,
                filter_apoteker_id=apoteker_id,
                waktu_rekap=datetime.now(),
                page=page, page_size=page_size, total_pages=1,
                items=[],
            )

        # Step 3: Build apoteker name map
        apoteker_ids = {r.id_staf_apoteker for r in resep_rows if r.id_staf_apoteker}
        apoteker_name_map = {}
        if apoteker_ids:
            staf_rows = self.db.execute(
                select(MasterStaf.id_staf, MasterStaf.nama_staf)
                .where(MasterStaf.id_staf.in_(list(apoteker_ids)))
            ).all()
            apoteker_name_map = {r.id_staf: r.nama_staf for r in staf_rows}

        # Step 4: Build items + summary
        all_items = []
        per_apoteker_agg = {}  # id_staf -> dict accumulator
        kunjungan_seen = set()

        for r in resep_rows:
            # Atribusi menempel di barisnya sendiri — tidak lagi dicari lewat kunjungan,
            # jadi dua penyerahan oleh dua apoteker di satu kunjungan tetap terpisah.
            id_apt = r.id_staf_apoteker
            waktu_serah = r.waktu_serah
            apt_nama = apoteker_name_map.get(id_apt, "(unknown)") if id_apt else "(unknown)"
            # A9: akumulasi Decimal (harga_jual = DECIMAL(12,2)); convert ke float di boundary
            qty = Decimal(str(r.qty or 0))
            harga = r.harga_jual if r.harga_jual is not None else Decimal(0)
            subtotal = qty * harga

            _is_racik = bool(getattr(r, "is_racikan", False))
            all_items.append(ApotekerDispensedItem(
                id_kunjungan=r.id_kunjungan,
                id_resep=r.id_resep,
                id_produk=r.id_produk,
                kode_produk=r.kode_produk,
                nama_produk=r.nama_produk,
                is_racikan=_is_racik,
                jenis_racik=getattr(r, "jenis_racik", None),
                # Racikan: tampilkan JUMLAH UNIT-nya (kapsul/pot), bukan qty=1 yang
                # hanya alat hitung subtotal di atas.
                qty=float(getattr(r, "jumlah_unit", 0) or 0) if _is_racik else float(qty),
                harga_satuan=float(harga),
                subtotal=float(subtotal),
                aturan_pakai=r.aturan_pakai,
                waktu_serah=waktu_serah,
                no_rm=r.no_rm,
                nama_pasien=r.nama_pasien,
                apoteker_nama=apt_nama,
                id_staf_apoteker=id_apt or 0,
            ))

            # Aggregate per apoteker
            key = id_apt or 0
            agg = per_apoteker_agg.setdefault(key, {
                "id_staf_apoteker": key,
                "apoteker_nama": apt_nama,
                "total_resep_item": 0,
                "kunjungan_set": set(),
                "total_qty": Decimal(0),
                "total_nominal": Decimal(0),
            })
            agg["total_resep_item"] += 1
            agg["kunjungan_set"].add(r.id_kunjungan)
            agg["total_qty"] += qty
            agg["total_nominal"] += subtotal
            kunjungan_seen.add(r.id_kunjungan)

        # Per-apoteker summary list (A9: grand total dihitung dari Decimal agg)
        per_apoteker = []
        grand_qty = Decimal(0)
        grand_nominal = Decimal(0)
        for agg in per_apoteker_agg.values():
            grand_qty += agg["total_qty"]
            grand_nominal += agg["total_nominal"]
            per_apoteker.append(ApotekerSummaryPerStaf(
                id_staf_apoteker=agg["id_staf_apoteker"],
                apoteker_nama=agg["apoteker_nama"],
                total_resep_item=agg["total_resep_item"],
                total_kunjungan=len(agg["kunjungan_set"]),
                total_qty=float(agg["total_qty"]),
                total_nominal=float(agg["total_nominal"]),
            ))
        per_apoteker.sort(key=lambda x: -x.total_nominal)

        # Totals
        total_resep_item = sum(p.total_resep_item for p in per_apoteker)
        total_qty = float(grand_qty)
        total_nominal = float(grand_nominal)
        total_kunjungan = len(kunjungan_seen)

        # Pagination on items
        total_pages = max(1, (len(all_items) + page_size - 1) // page_size)
        start_idx = (page - 1) * page_size
        page_items = all_items[start_idx:start_idx + page_size]

        return ApotekerDispensedResponse(
            tgl_dari=tgl_dari,
            tgl_sampai=tgl_sampai,
            filter_apoteker_id=apoteker_id,
            waktu_rekap=datetime.now(),
            total_kunjungan=total_kunjungan,
            total_resep_item=total_resep_item,
            total_qty=total_qty,
            total_nominal=total_nominal,
            per_apoteker=per_apoteker,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            items=page_items,
        )


    # =========================================================================
    # #363C - Rekap Write-off Produk
    # =========================================================================
    def get_writeoff_report(
        self,
        tgl_dari,
        tgl_sampai,
        apoteker_id=None,
        jenis_mutasi=None,
        page: int = 1,
        page_size: int = 100,
    ):
        """Rekap write-off produk dari audit_log (aksi LIKE 'WRITEOFF_PRODUK_%').

        Computes nominal loss = qty_dibuang * hpp_per_unit (HPP saat write-off
        bisa beda dengan HPP saat ini — pakai HPP master sekarang sebagai approx).
        """
        from datetime import date, datetime
        from sqlalchemy import select
        from app.db.models import AuditLog, MasterProduk
        from app.schemas.reports import (
            WriteOffReportItem,
            WriteOffSummaryPerJenis,
            WriteOffReportResponse,
        )

        if isinstance(tgl_dari, str):
            tgl_dari = date.fromisoformat(tgl_dari)
        if isinstance(tgl_sampai, str):
            tgl_sampai = date.fromisoformat(tgl_sampai)
        start_dt = datetime.combine(tgl_dari, datetime.min.time())
        end_dt = datetime.combine(tgl_sampai, datetime.max.time())

        # Query audit_log + JOIN master_produk + master_staf
        stmt = (
            select(
                AuditLog.id_log,
                AuditLog.waktu,
                AuditLog.aksi,
                AuditLog.id_target.label("id_produk"),
                AuditLog.id_staf.label("id_staf_apoteker"),
                AuditLog.data_lama,
                AuditLog.data_baru,
                AuditLog.keterangan,
                MasterProduk.kode_produk,
                MasterProduk.nama_produk,
                MasterProduk.hpp_per_unit,
                MasterStaf.nama_staf.label("apoteker_nama"),
            )
            .outerjoin(MasterProduk, MasterProduk.id_produk == AuditLog.id_target)
            .outerjoin(MasterStaf, MasterStaf.id_staf == AuditLog.id_staf)
            .where(AuditLog.tabel_target == "master_produk")
            .where(AuditLog.aksi.like("WRITEOFF_PRODUK_%"))
            .where(AuditLog.waktu >= start_dt)
            .where(AuditLog.waktu <= end_dt)
            .order_by(AuditLog.waktu.desc())
        )

        if apoteker_id is not None:
            stmt = stmt.where(AuditLog.id_staf == apoteker_id)
        if jenis_mutasi:
            j = jenis_mutasi.strip().upper()
            stmt = stmt.where(AuditLog.aksi == f"WRITEOFF_PRODUK_{j}")

        rows = list(self.db.execute(stmt).all())

        # Build items + aggregate
        all_items = []
        per_jenis_agg = {}
        for r in rows:
            # Extract jenis dari aksi "WRITEOFF_PRODUK_<JENIS>"
            jenis = r.aksi.replace("WRITEOFF_PRODUK_", "", 1)
            # Extract qty dari data_lama vs data_baru
            # A9: akumulasi Decimal (str() krn sumber JSON audit); convert ke float di boundary
            stok_sebelum = Decimal(str((r.data_lama or {}).get("stok_terkini", 0) or 0))
            stok_sesudah = Decimal(str((r.data_baru or {}).get("stok_terkini", 0) or 0))
            qty_dibuang = stok_sebelum - stok_sesudah
            hpp = Decimal(str(r.hpp_per_unit or 0))
            nominal_loss = qty_dibuang * hpp

            all_items.append(WriteOffReportItem(
                id_log=r.id_log,
                waktu=r.waktu,
                id_produk=r.id_produk,
                kode_produk=r.kode_produk or "(unknown)",
                nama_produk=r.nama_produk or "(produk dihapus)",
                jenis_mutasi=jenis,
                qty_dibuang=float(qty_dibuang),
                hpp_per_unit=float(hpp),
                nominal_loss=float(nominal_loss),
                stok_sebelum=float(stok_sebelum),
                stok_sesudah=float(stok_sesudah),
                id_staf_apoteker=r.id_staf_apoteker or 0,
                apoteker_nama=r.apoteker_nama or "(unknown)",
                keterangan=r.keterangan,
            ))

            # Aggregate per jenis
            agg = per_jenis_agg.setdefault(jenis, {
                "jenis_mutasi": jenis,
                "count": 0,
                "total_qty": Decimal(0),
                "total_nominal_loss": Decimal(0),
            })
            agg["count"] += 1
            agg["total_qty"] += qty_dibuang
            agg["total_nominal_loss"] += nominal_loss

        # Build per_jenis list (A9: convert Decimal agg -> float di boundary)
        per_jenis = [
            WriteOffSummaryPerJenis(
                jenis_mutasi=v["jenis_mutasi"],
                count=v["count"],
                total_qty=float(v["total_qty"]),
                total_nominal_loss=float(v["total_nominal_loss"]),
            )
            for v in per_jenis_agg.values()
        ]
        per_jenis.sort(key=lambda x: -x.total_nominal_loss)

        total_count = len(all_items)
        total_qty = float(sum((v["total_qty"] for v in per_jenis_agg.values()), Decimal(0)))
        total_nominal_loss = float(sum((v["total_nominal_loss"] for v in per_jenis_agg.values()), Decimal(0)))

        # Pagination
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        start_idx = (page - 1) * page_size
        page_items = all_items[start_idx:start_idx + page_size]

        return WriteOffReportResponse(
            tgl_dari=tgl_dari,
            tgl_sampai=tgl_sampai,
            filter_apoteker_id=apoteker_id,
            filter_jenis_mutasi=(jenis_mutasi.upper() if jenis_mutasi else None),
            waktu_rekap=datetime.now(),
            total_count=total_count,
            total_qty=total_qty,
            total_nominal_loss=total_nominal_loss,
            per_jenis=per_jenis,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            items=page_items,
        )


    # =========================================================================
    # #363D - Top Dispensed Products
    # =========================================================================
    def get_top_dispensed_products(
        self,
        tgl_dari,
        tgl_sampai,
        limit: int = 50,
        sort_by: str = "qty",
    ):
        """Top N produk paling sering / paling banyak qty / paling besar nominal
        di-dispense dalam rentang tanggal.

        sort_by: "qty" (default) | "nominal" | "count"
        """
        from datetime import date, datetime
        from sqlalchemy import select, func
        from app.db.models import AuditLog, KunjunganResep, MasterProduk
        from app.db.models._enums import StatusItemResepEnum
        from app.schemas.reports import TopProdukItem, TopProdukResponse

        if isinstance(tgl_dari, str):
            tgl_dari = date.fromisoformat(tgl_dari)
        if isinstance(tgl_sampai, str):
            tgl_sampai = date.fromisoformat(tgl_sampai)
        start_dt = datetime.combine(tgl_dari, datetime.min.time())
        end_dt = datetime.combine(tgl_sampai, datetime.max.time())

        if sort_by not in ("qty", "nominal", "count"):
            sort_by = "qty"
        if limit < 1:
            limit = 50
        if limit > 500:
            limit = 500

        # Step 1 (task #54): kumpulkan id_resep yang BENAR-BENAR diserahkan.
        # Cara lama — "semua resep DIBAYAR milik kunjungan yang punya audit SERAH_OBAT" —
        # ikut menghitung item yang belum pernah keluar begitu penyerahan boleh sebagian.
        id_resep_serah = list(self.db.execute(
            select(KunjunganResep.id_resep)
            .where(KunjunganResep.status_item == StatusItemResepEnum.DISERAHKAN)
            .where(KunjunganResep.waktu_serah.is_not(None))
            .where(KunjunganResep.waktu_serah >= start_dt)
            .where(KunjunganResep.waktu_serah <= end_dt)
        ).scalars().all())

        # Data LAMA: kunjungan ber-audit SERAH_OBAT yang belum punya status per item.
        legacy_kunj = set(self.db.execute(
            select(AuditLog.id_target)
            .where(AuditLog.aksi == "SERAH_OBAT")
            .where(AuditLog.tabel_target == "kunjungan")
            .where(AuditLog.waktu >= start_dt)
            .where(AuditLog.waktu <= end_dt)
        ).scalars().all())
        if legacy_kunj:
            sudah_per_item = set(self.db.execute(
                select(KunjunganResep.id_kunjungan)
                .where(KunjunganResep.id_kunjungan.in_(list(legacy_kunj)))
                .where(KunjunganResep.status_item == StatusItemResepEnum.DISERAHKAN)
                .distinct()
            ).scalars().all())
            legacy_kunj -= sudah_per_item
        if legacy_kunj:
            id_resep_serah += list(self.db.execute(
                select(KunjunganResep.id_resep)
                .where(KunjunganResep.id_kunjungan.in_(list(legacy_kunj)))
                .where(KunjunganResep.status_item == StatusItemResepEnum.DIBAYAR)
            ).scalars().all())

        # CATATAN (2026-09-30): dulu di sini ada `return items=[]` kalau tidak ada resep
        # yang diserahkan. Itu ikut menyembunyikan RACIKAN — hari yang seluruh
        # penyerahannya berupa racikan akan tampil sebagai laporan kosong. Sekarang
        # agregasi produk dilewati, tapi racikan tetap dihitung di bawah.
        rows = []
        if id_resep_serah:
            rows = self._agg_produk_dispensed(id_resep_serah)

        items_raw, total_nominal_all, total_events = self._rakit_item_produk(rows)

        # ---- RACIKAN (2026-09-30) -----------------------------------------
        # Dua pertanyaan berbeda, dijawab terpisah:
        #   (a) stok apa yang bergerak  → bahan racikan ditambahkan ke baris produk
        #   (b) racikan mana yang laris → peringkat racikan tersendiri
        items_raw, racikan_items, tot_batch, tot_nom_racik = self._tempel_racikan(
            items_raw, start_dt, end_dt, limit)

        return self._bungkus_top_produk(
            tgl_dari, tgl_sampai, limit, sort_by, items_raw,
            total_nominal_all, total_events,
            racikan_items, tot_batch, tot_nom_racik)

    def _agg_produk_dispensed(self, id_resep_serah):
        """Agregasi kunjungan_resep yang DISERAHKAN per produk."""
        from sqlalchemy import select, func
        from app.db.models import KunjunganResep, MasterProduk

        agg_stmt = (
            select(
                KunjunganResep.id_produk,
                func.sum(KunjunganResep.qty).label("total_qty"),
                func.count(KunjunganResep.id_resep).label("dispensed_count"),
                func.count(func.distinct(KunjunganResep.id_kunjungan)).label("unique_kunj"),
                MasterProduk.kode_produk,
                MasterProduk.nama_produk,
                MasterProduk.tipe_produk,
                MasterProduk.satuan,
                MasterProduk.harga_jual,
                MasterProduk.stok_terkini,
            )
            .join(MasterProduk, MasterProduk.id_produk == KunjunganResep.id_produk)
            .where(KunjunganResep.id_resep.in_(id_resep_serah))
            .group_by(
                KunjunganResep.id_produk,
                MasterProduk.kode_produk,
                MasterProduk.nama_produk,
                MasterProduk.tipe_produk,
                MasterProduk.satuan,
                MasterProduk.harga_jual,
                MasterProduk.stok_terkini,
            )
        )
        return list(self.db.execute(agg_stmt).all())

    def _rakit_item_produk(self, rows):
        """Baris agregasi → dict item + total nominal + jumlah event."""
        from decimal import Decimal
        items_raw = []
        total_nominal_all = Decimal(0)  # A9: akumulasi Decimal
        total_events = 0
        for r in rows:
            qty = Decimal(str(r.total_qty or 0))
            harga = r.harga_jual if r.harga_jual is not None else Decimal(0)
            nominal = qty * harga
            tipe = r.tipe_produk.value if hasattr(r.tipe_produk, "value") else (str(r.tipe_produk) if r.tipe_produk else None)
            items_raw.append({
                "id_produk": r.id_produk,
                "kode_produk": r.kode_produk,
                "nama_produk": r.nama_produk,
                "tipe_produk": tipe,
                "satuan": r.satuan,
                "total_qty": float(qty),
                "total_dispensed_count": int(r.dispensed_count or 0),
                "total_unique_kunjungan": int(r.unique_kunj or 0),
                "total_nominal": float(nominal),
                "avg_qty_per_kunjungan": (float(qty) / int(r.unique_kunj)) if r.unique_kunj else 0,
                "harga_satuan": float(harga),
                "stok_terkini": float(r.stok_terkini or 0),
            })
            total_nominal_all += nominal
            total_events += int(r.dispensed_count or 0)
        return items_raw, total_nominal_all, total_events

    def _tempel_racikan(self, items_raw, start_dt, end_dt, limit):
        """Tambahkan pemakaian bahan racikan ke baris produk + peringkat racikan.

        Racikan yang dihitung: status DISERAHKAN dengan `waktu_serah` di rentang —
        ukuran yang SAMA dengan resep produk, supaya keduanya bisa dibandingkan.

        ⚠ `dipakai` TIDAK dijumlahkan ke `total_qty`. Satuannya berbeda: bahan racikan
        dihitung dalam "butir" (mode MG) atau gram (mode GRAM), sedangkan `total_qty`
        memakai satuan JUAL produk. Angka gabungan akan terlihat rapi dan menyesatkan.
        """
        from decimal import Decimal
        from sqlalchemy import select, func
        from app.db.models import MasterProduk
        from app.db.models.racikan import KunjunganRacikan, KunjunganRacikanBahan
        from app.schemas.reports import TopRacikanItem

        head_ids = list(self.db.execute(
            select(KunjunganRacikan.id_kunjungan_racikan)
            .where(KunjunganRacikan.status_item == "DISERAHKAN")
            .where(KunjunganRacikan.waktu_serah.is_not(None))
            .where(KunjunganRacikan.waktu_serah >= start_dt)
            .where(KunjunganRacikan.waktu_serah <= end_dt)
        ).scalars().all())
        if not head_ids:
            return items_raw, [], 0, 0.0

        # ---- (a) bahan racikan → menempel ke baris produk
        bahan_rows = list(self.db.execute(
            select(
                KunjunganRacikanBahan.id_produk,
                func.sum(KunjunganRacikanBahan.dipakai).label("dipakai"),
                func.sum(KunjunganRacikanBahan.subtotal).label("nominal"),
                func.count(KunjunganRacikanBahan.id_kunjungan_racikan_bahan).label("n"),
                func.min(KunjunganRacikanBahan.satuan_dipakai).label("satuan"),
                func.count(func.distinct(KunjunganRacikanBahan.satuan_dipakai)).label("n_satuan"),
            )
            .where(KunjunganRacikanBahan.id_kunjungan_racikan.in_(head_ids))
            .group_by(KunjunganRacikanBahan.id_produk)
        ).all())

        by_id = {it["id_produk"]: it for it in items_raw}
        for b in bahan_rows:
            # Satu produk bisa terpakai dalam dua mode (butir & gram) di racikan
            # berbeda. Menjumlahkannya jadi satu angka salah — tandai apa adanya.
            _sat = b.satuan if int(b.n_satuan or 1) <= 1 else "campuran"
            if b.id_produk in by_id:
                it = by_id[b.id_produk]
                it["qty_racikan"] = float(b.dipakai or 0)
                it["satuan_racikan"] = _sat
                it["racikan_count"] = int(b.n or 0)
                it["nominal_racikan"] = float(b.nominal or 0)
            else:
                # Produk yang HANYA terpakai lewat racikan. Sebelum ini ia hilang
                # sama sekali dari laporan — terlihat seperti barang mati padahal
                # stoknya terkuras. Inilah inti keluhan "racikan tidak masuk laporan".
                mp = self.db.get(MasterProduk, b.id_produk)
                if mp is None:
                    continue
                _tipe = mp.tipe_produk.value if hasattr(mp.tipe_produk, "value") else (
                    str(mp.tipe_produk) if mp.tipe_produk else None)
                items_raw.append({
                    "id_produk": mp.id_produk, "kode_produk": mp.kode_produk,
                    "nama_produk": mp.nama_produk, "tipe_produk": _tipe,
                    "satuan": mp.satuan, "total_qty": 0.0,
                    "total_dispensed_count": 0, "total_unique_kunjungan": 0,
                    "total_nominal": 0.0, "avg_qty_per_kunjungan": 0.0,
                    "harga_satuan": float(mp.harga_jual or 0),
                    "stok_terkini": float(mp.stok_terkini or 0),
                    "qty_racikan": float(b.dipakai or 0), "satuan_racikan": _sat,
                    "racikan_count": int(b.n or 0),
                    "nominal_racikan": float(b.nominal or 0),
                    "hanya_dari_racikan": True,
                })

        # ---- (b) peringkat racikan
        rank_rows = list(self.db.execute(
            select(
                KunjunganRacikan.nama_snapshot,
                KunjunganRacikan.jenis_racik,
                func.count(KunjunganRacikan.id_kunjungan_racikan).label("batch"),
                func.sum(KunjunganRacikan.jumlah_unit).label("unit"),
                func.count(func.distinct(KunjunganRacikan.id_kunjungan)).label("kunj"),
                func.sum(KunjunganRacikan.total).label("nominal"),
                func.sum(KunjunganRacikan.biaya_racik).label("ongkos"),
            )
            .where(KunjunganRacikan.id_kunjungan_racikan.in_(head_ids))
            .group_by(KunjunganRacikan.nama_snapshot, KunjunganRacikan.jenis_racik)
            .order_by(func.count(KunjunganRacikan.id_kunjungan_racikan).desc())
        ).all())

        racikan_items, tot_batch, tot_nom = [], 0, Decimal(0)
        for i, r in enumerate(rank_rows[:limit], start=1):
            tot_batch += int(r.batch or 0)
            tot_nom += Decimal(str(r.nominal or 0))
            racikan_items.append(TopRacikanItem(
                rank=i, nama=r.nama_snapshot, jenis_racik=r.jenis_racik,
                total_batch=int(r.batch or 0), total_unit=int(r.unit or 0),
                total_unique_kunjungan=int(r.kunj or 0),
                total_nominal=float(r.nominal or 0),
                total_biaya_racik=float(r.ongkos or 0),
            ))
        return items_raw, racikan_items, tot_batch, float(tot_nom)

    def _bungkus_top_produk(self, tgl_dari, tgl_sampai, limit, sort_by, items_raw,
                            total_nominal_all, total_events,
                            racikan_items, tot_batch, tot_nom_racik):
        from datetime import datetime
        from app.schemas.reports import TopProdukItem, TopProdukResponse

        # Produk yang hanya terpakai lewat racikan punya total_qty 0, jadi pada
        # urutan "qty" ia tenggelam ke bawah. Itu disengaja — yang penting ia MUNCUL.
        sort_key = {
            "qty": lambda x: -x["total_qty"],
            "nominal": lambda x: -x["total_nominal"],
            "count": lambda x: -x["total_dispensed_count"],
        }[sort_by]
        items_raw.sort(key=sort_key)

        ranked = [TopProdukItem(rank=i, **it)
                  for i, it in enumerate(items_raw[:limit], start=1)]

        return TopProdukResponse(
            tgl_dari=tgl_dari,
            tgl_sampai=tgl_sampai,
            limit=limit,
            sort_by=sort_by,
            waktu_rekap=datetime.now(),
            total_unique_produk=len(items_raw),
            total_dispensing_events=total_events,
            total_nominal=float(total_nominal_all),
            items=ranked,
            racikan=racikan_items,
            total_racikan_batch=tot_batch,
            total_nominal_racikan=tot_nom_racik,
        )

    # =========================================================================
    # Top Diagnosa — "kasus terbanyak" (Langkah 4, 2026-09-30)
    # =========================================================================
    def get_top_diagnosa(
        self,
        tgl_dari: date,
        tgl_sampai: date,
        sistem: str = "SEMUA",       # SEMUA | ICD10 | ESTETIK
        hanya_primer: bool = False,
        sort_by: str = "pasien",     # pasien | kunjungan
        limit: int = 50,
    ) -> dict:
        """Ranking diagnosa dari `kunjungan_diagnosa`.

        ⚠ APA YANG DIHITUNG SEBAGAI "SATU KASUS" — ini mengubah JAWABANNYA,
          bukan sekadar tampilannya:

            jumlah_kunjungan  = berapa kali diagnosa ini dicatat.
                                Pasien akne yang kontrol 5x = 5.
                                Menjawab: BEBAN KERJA.
            jumlah_pasien     = berapa ORANG berbeda yang punya diagnosa ini.
                                Pasien akne yang kontrol 5x = 1.
                                Menjawab: PREVALENSI.

          Keduanya ditampilkan berdampingan supaya tidak ada yang salah baca.
          Rasio `kunjungan_per_pasien` adalah yang paling dekat dengan
          pertanyaan "kasus ini berulang atau sekali datang".

        ⚠ Memakai SNAPSHOT (`kode_snapshot`/`nama_snapshot`), bukan join ke
          `ref_diagnosa`. Yang dilaporkan adalah kode & nama yang BERLAKU SAAT
          diagnosa dibuat. Kalau master diagnosa kelak diganti namanya, laporan
          historis tidak ikut berubah — itu yang benar untuk rekam medis.

        ⚠ `jumlah_pasien` memakai `kunjungan.id_pasien`. Pasien yang sudah
          DIGABUNGKAN sudah dipindah barisnya oleh `gabungkan()`, jadi ia
          terhitung satu orang — bukan dua. Lihat `sehati-gabung-pasien`.
        """
        from app.db.models import Kunjungan, KunjunganDiagnosa

        if tgl_dari > tgl_sampai:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "tgl_dari > tgl_sampai")

        start = datetime.combine(tgl_dari, time.min)
        end = datetime.combine(tgl_sampai, time.max)

        stmt = (
            select(
                KunjunganDiagnosa.sistem_snapshot,
                KunjunganDiagnosa.kode_snapshot,
                KunjunganDiagnosa.nama_snapshot,
                func.count(KunjunganDiagnosa.id_kunjungan_diagnosa).label("n_kunj"),
                func.count(func.distinct(Kunjungan.id_pasien)).label("n_pasien"),
                func.sum(case((KunjunganDiagnosa.is_primer.is_(True), 1), else_=0))
                    .label("n_primer"),
                func.min(Kunjungan.tgl_kunjungan).label("pertama"),
                func.max(Kunjungan.tgl_kunjungan).label("terakhir"),
            )
            .join(Kunjungan, Kunjungan.id_kunjungan == KunjunganDiagnosa.id_kunjungan)
            .where(Kunjungan.tgl_kunjungan >= start)
            .where(Kunjungan.tgl_kunjungan <= end)
            .group_by(
                KunjunganDiagnosa.sistem_snapshot,
                KunjunganDiagnosa.kode_snapshot,
                KunjunganDiagnosa.nama_snapshot,
            )
        )
        if sistem in ("ICD10", "ESTETIK"):
            stmt = stmt.where(KunjunganDiagnosa.sistem_snapshot == sistem)
        if hanya_primer:
            stmt = stmt.where(KunjunganDiagnosa.is_primer.is_(True))

        rows = self.db.execute(stmt).all()

        items = []
        for r in rows:
            n_kunj, n_pasien = int(r[3] or 0), int(r[4] or 0)
            items.append({
                "sistem": r[0] or "—",
                # `kode_diagnosa`/`nama_diagnosa`, BUKAN `kode`/`nama`. Kunci
                # bernama `nama` di konteks pasien berarti nama ORANG — pemeriksa
                # otomatis menandainya sebagai kebocoran identitas, dan ia benar
                # untuk curiga. Satu kata dua arti adalah pola yang berulang
                # menggigit proyek ini; diberi nama tegas sekalian.
                "kode_diagnosa": r[1] or "—",
                "nama_diagnosa": r[2] or "—",
                "jumlah_kunjungan": n_kunj,
                "jumlah_pasien": n_pasien,
                "jumlah_primer": int(r[5] or 0),
                # Dibulatkan 2 desimal: 1.0 = sekali datang, >2 = kontrol berulang.
                "kunjungan_per_pasien": round(n_kunj / n_pasien, 2) if n_pasien else 0,
                "pertama": r[6],
                "terakhir": r[7],
            })

        kunci = "jumlah_pasien" if sort_by == "pasien" else "jumlah_kunjungan"
        # Kunci kedua supaya urutan STABIL — tanpa ini, baris berskor sama bisa
        # bertukar posisi antar muat-ulang dan terlihat seperti data berubah.
        items.sort(key=lambda x: (x[kunci], x["jumlah_kunjungan"],
                          x["nama_diagnosa"]),
                   reverse=True)

        total_kunj = sum(i["jumlah_kunjungan"] for i in items)
        total_pasien_baris = sum(i["jumlah_pasien"] for i in items)
        for i, it in enumerate(items[:limit], 1):
            it["rank"] = i
            it["persen_kunjungan"] = (
                round(it["jumlah_kunjungan"] * 100.0 / total_kunj, 1)
                if total_kunj else 0.0)

        # Pasien unik SEBENARNYA (bukan jumlah kolom di atas): satu pasien bisa
        # punya beberapa diagnosa berbeda, jadi menjumlahkan kolom jumlah_pasien
        # akan menghitungnya berkali-kali. Angka ini dipakai di ringkasan.
        q_unik = (
            select(func.count(func.distinct(Kunjungan.id_pasien)))
            .join(KunjunganDiagnosa,
                  KunjunganDiagnosa.id_kunjungan == Kunjungan.id_kunjungan)
            .where(Kunjungan.tgl_kunjungan >= start)
            .where(Kunjungan.tgl_kunjungan <= end)
        )
        if sistem in ("ICD10", "ESTETIK"):
            q_unik = q_unik.where(KunjunganDiagnosa.sistem_snapshot == sistem)
        if hanya_primer:
            q_unik = q_unik.where(KunjunganDiagnosa.is_primer.is_(True))
        pasien_unik = int(self.db.execute(q_unik).scalar() or 0)

        return {
            "tgl_dari": tgl_dari, "tgl_sampai": tgl_sampai,
            "sistem": sistem, "hanya_primer": hanya_primer, "sort_by": sort_by,
            "items": items[:limit],
            "total_diagnosa_unik": len(items),
            "total_kunjungan": total_kunj,
            "total_pasien_unik": pasien_unik,
            # Sengaja dibawa keluar supaya template bisa menjelaskan kenapa
            # kolom jumlah_pasien TIDAK boleh dijumlahkan.
            "jumlah_pasien_terjumlah": total_pasien_baris,
            "ditampilkan": len(items[:limit]),
        }
