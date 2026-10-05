"""
DashboardService — compute stats per role untuk dashboard page.

Dispatcher: get_stats_for_role(actor, today) → dict dengan key 'role' + stats.

Re-use existing repos (KasirRepository, ApotekRepository, TreatmentRepository, dll)
sebanyak mungkin supaya tidak duplicate logic.
"""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

# Kunjungan retur (RETUR_PASIEN) bukan kunjungan klinis — tidak dihitung di KPI
# (keputusan dr. Hansen 2026-10-05, DESAIN_RETUR_DARI_PASIEN.md §12).
from app.services._jenis_kunjungan import JENIS_KUNJUNGAN_BUKAN_KLINIS

from sqlalchemy import and_, func, select, case
from sqlalchemy.orm import Session

from app.db.models import (
    InventoryStok,
    Kunjungan,
    KunjunganTindakan,
    MasterProduk,
    MasterStaf,
    Pasien,
    PemeriksaanKlinis,
    Pemesanan,
    StafRoleEnum,
    StatusPemesananEnum,
    StockOpname,
    StatusOpnameEnum,
    TransaksiKasir,
    TransaksiPembayaran,
)


class DashboardService:
    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # MAIN DISPATCHER
    # =========================================================================
    def get_stats_for_role(self, actor: MasterStaf, today: Optional[date] = None) -> dict:
        """Dispatch berdasarkan role actor. Return dict {role, stats, alerts}."""
        if today is None:
            today = date.today()

        role = actor.role.value if hasattr(actor.role, "value") else str(actor.role)

        builders = {
            "Owner": self._owner_stats,
            "Superadmin": self._owner_stats,  # sama seperti Owner
            "Admin": self._admin_stats,
            "FO": self._fo_stats,
            "Dokter": self._dokter_stats,
            "Perawat": self._perawat_stats,
            "Kasir": self._kasir_stats,
            "Apoteker": self._apoteker_stats,
            "Purchasing": self._purchasing_stats,
        }
        builder = builders.get(role, self._default_stats)
        return builder(actor, today)

    # =========================================================================
    # OWNER / SUPERADMIN — comprehensive overview
    # =========================================================================
    def _owner_stats(self, actor: MasterStaf, today: date) -> dict:
        return {
            "role": "Owner",
            "kpi": [
                self._kpi_omzet_hari_ini(today),
                self._kpi_pasien_hari_ini(today),
                self._kpi_kunjungan_hari_ini(today),
                self._kpi_tindakan_completed_hari_ini(today),
            ],
            "antrian_per_stage": self._antrian_per_stage(today),
            "alerts": [
                self._alert_stok_urgent(),
                self._alert_po_outstanding(),
                self._alert_opname_draft(),
            ],
            "recent_activity": self._recent_kunjungan(today, limit=5),
            # Phase 5 (#364 DEC-063): Void hari ini section
            "void_today": self._void_today_stats(today),
        }

    # =========================================================================
    # ADMIN — operasional tanpa detail finansial
    # =========================================================================
    def _admin_stats(self, actor: MasterStaf, today: date) -> dict:
        return {
            "role": "Admin",
            "kpi": [
                self._kpi_pasien_hari_ini(today),
                self._kpi_kunjungan_hari_ini(today),
                self._kpi_tindakan_completed_hari_ini(today),
                {"label": "Total Transaksi", "value": self._count_transaksi_today(today), "icon": "💰", "color": "blue"},
            ],
            "antrian_per_stage": self._antrian_per_stage(today),
            "alerts": [],
            "recent_activity": self._recent_kunjungan(today, limit=5),
        }

    # =========================================================================
    # FO — antrian + pasien baru
    # =========================================================================
    def _fo_stats(self, actor: MasterStaf, today: date) -> dict:
        return {
            "role": "FO",
            "kpi": [
                self._kpi_pasien_hari_ini(today),
                {"label": "Pasien Baru Hari Ini", "value": self._count_pasien_baru_today(today), "icon": "➕", "color": "emerald"},
                self._kpi_kunjungan_hari_ini(today),
                {"label": "Antrian Konsultasi", "value": self._count_antrian_status(today, "ANTRI_KONSULTASI"), "icon": "📋", "color": "amber"},
            ],
            "antrian_per_stage": self._antrian_per_stage(today),
            "shortcuts": [
                {"label": "+ Daftar Pasien Baru", "url": "/web/pendaftaran-pasien", "icon": "➕", "color": "emerald"},
                {"label": "Cari Pasien", "url": "/web/pasien", "icon": "🔍", "color": "blue"},
                {"label": "Antrian Hari Ini", "url": "/web/kunjungan", "icon": "📋", "color": "purple"},
            ],
        }

    # =========================================================================
    # DOKTER — filter per dokter
    # =========================================================================
    def _dokter_stats(self, actor: MasterStaf, today: date) -> dict:
        today_start = datetime.combine(today, time.min)
        today_end = datetime.combine(today, time.max)

        # Antrian yang lewat dokter ini hari ini (relevant filter — gampangnya: ANTRI_KONSULTASI/KONSULTASI today)
        antrian_count = self.db.execute(
            select(func.count(Kunjungan.id_kunjungan))
            .where(Kunjungan.tgl_kunjungan >= today_start)
            .where(Kunjungan.tgl_kunjungan <= today_end)
            .where(Kunjungan.status_antrian.in_(["ANTRI_KONSULTASI", "KONSULTASI"]))
        ).scalar() or 0

        # SOAP yang dokter ini buat hari ini
        soap_count = self.db.execute(
            select(func.count(PemeriksaanKlinis.id_pemeriksaan))
            .where(PemeriksaanKlinis.id_staf_dokter == actor.id_staf)
            # Draf apoteker tidak dihitung sebagai SOAP dokter ini.
            .where(PemeriksaanKlinis.status_soap == "FINAL")
            .where(PemeriksaanKlinis.created_at >= today_start)
            .where(PemeriksaanKlinis.created_at <= today_end)
        ).scalar() or 0

        return {
            "role": "Dokter",
            "kpi": [
                {"label": "Antrian Konsultasi", "value": antrian_count, "icon": "🩺", "color": "blue"},
                {"label": "Pasien Konsul Hari Ini", "value": soap_count, "icon": "✅", "color": "emerald"},
                self._kpi_kunjungan_hari_ini(today),
                {"label": "Tindakan Pending", "value": self._count_tindakan_status(today, "PENDING"), "icon": "💉", "color": "amber"},
            ],
            "shortcuts": [
                {"label": "Antrian Saya", "url": "/web/dokter/antrian", "icon": "🩺", "color": "blue"},
                {"label": "Cari Pasien", "url": "/web/pasien", "icon": "🔍", "color": "slate"},
            ],
        }

    # =========================================================================
    # PERAWAT — tindakan focus
    # =========================================================================
    def _perawat_stats(self, actor: MasterStaf, today: date) -> dict:
        return {
            "role": "Perawat",
            "kpi": [
                {"label": "Antrian Tindakan", "value": self._count_antrian_status(today, "ANTRI_TREATMENT"), "icon": "💉", "color": "purple"},
                {"label": "Sedang Dikerjakan", "value": self._count_antrian_status(today, "ON_TREATMENT"), "icon": "⏳", "color": "amber"},
                {"label": "Tindakan PENDING", "value": self._count_tindakan_status(today, "PENDING"), "icon": "📋", "color": "blue"},
                {"label": "Tindakan SELESAI Hari Ini", "value": self._count_tindakan_status(today, "SELESAI"), "icon": "✅", "color": "emerald"},
            ],
            "shortcuts": [
                {"label": "Ruang Tindakan", "url": "/web/ruang-tindakan/antrian", "icon": "💉", "color": "purple"},
                {"label": "Cari Pasien", "url": "/web/pasien", "icon": "🔍", "color": "slate"},
            ],
        }

    # =========================================================================
    # KASIR — antrian bayar + shift sendiri
    # =========================================================================
    def _kasir_stats(self, actor: MasterStaf, today: date) -> dict:
        # Omzet shift kasir ini hari ini
        today_start = datetime.combine(today, time.min)
        today_end = datetime.combine(today, time.max)

        omzet_shift = self.db.execute(
            select(func.coalesce(func.sum(TransaksiPembayaran.nominal), 0))
            .join(TransaksiKasir, TransaksiKasir.id_transaksi == TransaksiPembayaran.id_transaksi)
            .where(TransaksiKasir.id_staf_kasir == actor.id_staf)
            .where(TransaksiKasir.waktu_bayar >= today_start)
            .where(TransaksiKasir.waktu_bayar <= today_end)
            .where(TransaksiKasir.status_transaksi == "BAYAR")  # A1: exclude VOID
        ).scalar() or 0
        # T32: refund oleh kasir ini hari ini (atribusi pelaku, sama dengan tutup kasir).
        from app.services import _refund_bukuan as _rb
        omzet_shift = Decimal(str(omzet_shift)) - _rb.refund_per_staf(
            self.db, today_start, today_end).get(actor.id_staf, Decimal("0"))

        trx_count = self.db.execute(
            select(func.count(TransaksiKasir.id_transaksi))
            .where(TransaksiKasir.id_staf_kasir == actor.id_staf)
            .where(TransaksiKasir.waktu_bayar >= today_start)
            .where(TransaksiKasir.waktu_bayar <= today_end)
            .where(TransaksiKasir.status_transaksi == "BAYAR")  # A1: exclude VOID
        ).scalar() or 0

        return {
            "role": "Kasir",
            "kpi": [
                {"label": "Antrian Bayar", "value": self._count_antrian_status(today, "ANTRI_BAYAR"), "icon": "💰", "color": "amber"},
                {"label": "Omzet Shift Saya", "value_money": float(omzet_shift), "icon": "💵", "color": "emerald"},
                {"label": "Transaksi Saya Hari Ini", "value": trx_count, "icon": "🧾", "color": "blue"},
                self._kpi_kunjungan_hari_ini(today),
            ],
            "shortcuts": [
                {"label": "Kasir / POS", "url": "/web/kasir/antrian", "icon": "💰", "color": "amber"},
                {"label": "Cari Pasien", "url": "/web/pasien", "icon": "🔍", "color": "slate"},
            ],
        }

    # =========================================================================
    # APOTEKER — antrian obat + stok urgent
    # =========================================================================
    def _apoteker_stats(self, actor: MasterStaf, today: date) -> dict:
        return {
            "role": "Apoteker",
            "kpi": [
                {"label": "Antrian Obat", "value": self._count_antrian_status(today, "ANTRI_OBAT"), "icon": "💊", "color": "teal"},
                {"label": "Stok ≤ Minimal", "value": self._count_stok_urgent(), "icon": "📉", "color": "red"},
                self._kpi_kunjungan_hari_ini(today),
                {"label": "PO Retail Aktif", "value": self._count_po_aktif_retail(), "icon": "📋", "color": "blue"},
            ],
            "alerts": [
                self._alert_stok_urgent(),
            ],
            "shortcuts": [
                {"label": "Apotek", "url": "/web/apotek", "icon": "💊", "color": "teal"},
                {"label": "Suggested Order", "url": "/web/apotek/suggested-order", "icon": "📊", "color": "amber"},
                {"label": "Pesan Produk Retail", "url": "/web/pengadaan/pemesanan/baru", "icon": "🛒", "color": "blue"},
            ],
        }

    # =========================================================================
    # PURCHASING — PO focus
    # =========================================================================
    def _purchasing_stats(self, actor: MasterStaf, today: date) -> dict:
        return {
            "role": "Purchasing",
            "kpi": [
                {"label": "PO SUBMITTED", "value": self._count_po_by_status(StatusPemesananEnum.SUBMITTED), "icon": "📝", "color": "amber"},
                {"label": "PO ORDERED", "value": self._count_po_by_status(StatusPemesananEnum.ORDERED), "icon": "📦", "color": "blue"},
                {"label": "Receive Pending (PARTIAL)", "value": self._count_po_by_status(StatusPemesananEnum.PARTIAL_RECEIVED), "icon": "📥", "color": "purple"},
                {"label": "Stok ≤ Minimal (semua)", "value": self._count_stok_urgent(), "icon": "📉", "color": "red"},
            ],
            "alerts": [
                self._alert_stok_urgent(),
            ],
            "shortcuts": [
                {"label": "+ Buat PO", "url": "/web/pengadaan/pemesanan/baru", "icon": "➕", "color": "blue"},
                {"label": "Stock Opname", "url": "/web/pengadaan/opname", "icon": "✓", "color": "purple"},
                {"label": "History Mutasi", "url": "/web/pengadaan/mutasi", "icon": "📊", "color": "slate"},
            ],
        }

    # =========================================================================
    # DEFAULT (role tidak dikenali)
    # =========================================================================
    def _default_stats(self, actor: MasterStaf, today: date) -> dict:
        return {
            "role": "Default",
            "kpi": [
                {"label": "Server Status", "value": "● Jalan", "icon": "✓", "color": "emerald"},
            ],
            "shortcuts": [],
        }

    # =========================================================================
    # KPI BUILDERS (shared)
    # =========================================================================
    def _kpi_omzet_hari_ini(self, today: date) -> dict:
        today_start = datetime.combine(today, time.min)
        today_end = datetime.combine(today, time.max)
        # JOIN ke TransaksiKasir karena TransaksiPembayaran tidak punya kolom waktu sendiri
        omzet = self.db.execute(
            select(func.coalesce(func.sum(TransaksiPembayaran.nominal), 0))
            .join(TransaksiKasir, TransaksiKasir.id_transaksi == TransaksiPembayaran.id_transaksi)
            .where(TransaksiKasir.waktu_bayar >= today_start)
            .where(TransaksiKasir.waktu_bayar <= today_end)
            .where(TransaksiKasir.status_transaksi == "BAYAR")  # A1: exclude VOID
        ).scalar() or 0
        # T32: kurangi refund yang dibukukan hari ini. Pembayaran tidak pernah dikurangi
        # refund (header pun tidak lagi), jadi tanpa ini KPI selalu lebih besar dari
        # laporan omzet di hari yang ada refund-nya.
        from app.services import _refund_bukuan as _rb
        omzet = Decimal(str(omzet)) - _rb.refund_total(self.db, today_start, today_end)
        return {"label": "Omzet Hari Ini", "value_money": float(omzet), "icon": "💵", "color": "emerald"}

    def _kpi_pasien_hari_ini(self, today: date) -> dict:
        today_start = datetime.combine(today, time.min)
        today_end = datetime.combine(today, time.max)
        n = self.db.execute(
            select(func.count(func.distinct(Kunjungan.id_pasien)))
            .where(Kunjungan.tgl_kunjungan >= today_start)
            .where(Kunjungan.tgl_kunjungan <= today_end)
            .where(Kunjungan.jenis_kunjungan.notin_(JENIS_KUNJUNGAN_BUKAN_KLINIS))
        ).scalar() or 0
        return {"label": "Pasien Unik Hari Ini", "value": n, "icon": "👥", "color": "blue"}

    def _kpi_kunjungan_hari_ini(self, today: date) -> dict:
        today_start = datetime.combine(today, time.min)
        today_end = datetime.combine(today, time.max)
        n = self.db.execute(
            select(func.count(Kunjungan.id_kunjungan))
            .where(Kunjungan.tgl_kunjungan >= today_start)
            .where(Kunjungan.tgl_kunjungan <= today_end)
            .where(Kunjungan.jenis_kunjungan.notin_(JENIS_KUNJUNGAN_BUKAN_KLINIS))
        ).scalar() or 0
        return {"label": "Total Kunjungan", "value": n, "icon": "📋", "color": "purple"}

    def _kpi_tindakan_completed_hari_ini(self, today: date) -> dict:
        n = self._count_tindakan_status(today, "SELESAI")
        return {"label": "Tindakan Selesai", "value": n, "icon": "✅", "color": "emerald"}

    # =========================================================================
    # COUNT HELPERS
    # =========================================================================
    def _count_antrian_status(self, today: date, status: str) -> int:
        today_start = datetime.combine(today, time.min)
        today_end = datetime.combine(today, time.max)
        return int(self.db.execute(
            select(func.count(Kunjungan.id_kunjungan))
            .where(Kunjungan.tgl_kunjungan >= today_start)
            .where(Kunjungan.tgl_kunjungan <= today_end)
            .where(Kunjungan.status_antrian == status)
            .where(Kunjungan.jenis_kunjungan.notin_(JENIS_KUNJUNGAN_BUKAN_KLINIS))
        ).scalar() or 0)

    def _count_tindakan_status(self, today: date, status: str) -> int:
        today_start = datetime.combine(today, time.min)
        today_end = datetime.combine(today, time.max)
        return int(self.db.execute(
            select(func.count(KunjunganTindakan.id_kunjungan_tindakan))
            .join(Kunjungan, Kunjungan.id_kunjungan == KunjunganTindakan.id_kunjungan)
            .where(Kunjungan.tgl_kunjungan >= today_start)
            .where(Kunjungan.tgl_kunjungan <= today_end)
            .where(KunjunganTindakan.status_tindakan == status)
        ).scalar() or 0)

    def _count_pasien_baru_today(self, today: date) -> int:
        today_start = datetime.combine(today, time.min)
        today_end = datetime.combine(today, time.max)
        return int(self.db.execute(
            select(func.count(Pasien.id_pasien))
            .where(Pasien.created_at >= today_start)
            .where(Pasien.created_at <= today_end)
        ).scalar() or 0)

    # =========================================================================
    # PHASE 5 (#364 DEC-063) — VOID TODAY STATS
    # =========================================================================
    def _void_today_stats(self, today: date) -> dict:
        """Hitung statistik void transaksi hari ini berdasarkan void_at (bukan waktu_bayar).

        Returns dict dengan:
        - count: total transaksi yang di-void hari ini
        - total_nominal: total Rupiah yang di-void (referensi loss potential)
        - late_void_count: subset yang force past-day
        - by_reason: list dict {reason_code, count, total_nominal}
        - by_method: list dict {method, count} (SELF vs Force Past-Day implied by late_void)
        """
        today_start = datetime.combine(today, time.min)
        today_end = datetime.combine(today, time.max)

        # Total count + nominal
        row = self.db.execute(
            select(
                func.count(TransaksiKasir.id_transaksi),
                func.coalesce(func.sum(TransaksiKasir.total_tagihan), 0),
                func.sum(case((TransaksiKasir.late_void == True, 1), else_=0)),
            )
            .where(TransaksiKasir.status_transaksi == "VOID")
            .where(TransaksiKasir.void_at >= today_start)
            .where(TransaksiKasir.void_at <= today_end)
        ).first()
        total_count = int(row[0] or 0) if row else 0
        total_nominal = float(row[1] or 0) if row else 0.0
        late_count = int(row[2] or 0) if row else 0

        # Breakdown by reason
        by_reason_rows = self.db.execute(
            select(
                TransaksiKasir.void_reason_code,
                func.count(TransaksiKasir.id_transaksi),
                func.coalesce(func.sum(TransaksiKasir.total_tagihan), 0),
            )
            .where(TransaksiKasir.status_transaksi == "VOID")
            .where(TransaksiKasir.void_at >= today_start)
            .where(TransaksiKasir.void_at <= today_end)
            .group_by(TransaksiKasir.void_reason_code)
            .order_by(func.count(TransaksiKasir.id_transaksi).desc())
        ).all()
        by_reason = [
            {
                "reason_code": r[0] or "-",
                "count": int(r[1] or 0),
                "total_nominal": float(r[2] or 0),
            }
            for r in by_reason_rows
        ]

        return {
            "count": total_count,
            "total_nominal": total_nominal,
            "late_void_count": late_count,
            "by_reason": by_reason,
        }

    def _count_transaksi_today(self, today: date) -> int:
        today_start = datetime.combine(today, time.min)
        today_end = datetime.combine(today, time.max)
        return int(self.db.execute(
            select(func.count(TransaksiKasir.id_transaksi))
            .where(TransaksiKasir.waktu_bayar >= today_start)
            .where(TransaksiKasir.waktu_bayar <= today_end)
            .where(TransaksiKasir.status_transaksi == "BAYAR")  # A1: exclude VOID
        ).scalar() or 0)

    def _count_stok_urgent(self) -> int:
        # DYN-L3: pakai ambang EFEKTIF (MAX manual, ROP dinamis) — bukan stok_minimal statis.
        from app.services.apotek_service import ApotekService
        return ApotekService(self.db).count_low_stock_effective()

    def _count_po_by_status(self, status: StatusPemesananEnum) -> int:
        return int(self.db.execute(
            select(func.count(Pemesanan.id_pemesanan))
            .where(Pemesanan.status == status)
        ).scalar() or 0)

    def _count_po_aktif_retail(self) -> int:
        return int(self.db.execute(
            select(func.count(Pemesanan.id_pemesanan))
            .where(Pemesanan.status.in_([
                StatusPemesananEnum.SUBMITTED,
                StatusPemesananEnum.ORDERED,
                StatusPemesananEnum.PARTIAL_RECEIVED,
            ]))
        ).scalar() or 0)

    # =========================================================================
    # ANTRIAN BREAKDOWN
    # =========================================================================
    def _antrian_per_stage(self, today: date) -> list[dict]:
        stages = [
            ("ANTRI_KONSULTASI", "Antri Konsul", "amber", "📋"),
            ("KONSULTASI", "Konsultasi", "blue", "🩺"),
            ("ANTRI_TREATMENT", "Antri Treatment", "purple", "💉"),
            ("ON_TREATMENT", "Sedang Tindakan", "indigo", "⏳"),
            ("ANTRI_BAYAR", "Antri Bayar", "amber", "💰"),
            ("ANTRI_OBAT", "Antri Obat", "teal", "💊"),
        ]
        return [
            {
                "status": code,
                "label": label,
                "color": color,
                "icon": icon,
                "count": self._count_antrian_status(today, code),
            }
            for code, label, color, icon in stages
        ]

    # =========================================================================
    # ALERTS
    # =========================================================================
    def _alert_stok_urgent(self) -> dict:
        n = self._count_stok_urgent()
        return {
            "label": "Produk Stok ≤ Minimal",
            "count": n,
            "severity": "high" if n > 5 else ("medium" if n > 0 else "ok"),
            "url": "/web/apotek/stok?filter_stok=low",
            "icon": "📉",
        } if n > 0 else None

    def _alert_po_outstanding(self) -> dict:
        n = self._count_po_aktif_retail()
        return {
            "label": "PO Outstanding",
            "count": n,
            "severity": "medium" if n > 0 else "ok",
            "url": "/web/pengadaan/pemesanan",
            "icon": "📋",
        } if n > 0 else None

    def _alert_opname_draft(self) -> dict:
        n = int(self.db.execute(
            select(func.count(StockOpname.id_opname))
            .where(StockOpname.status == StatusOpnameEnum.DRAFT)
        ).scalar() or 0)
        return {
            "label": "Opname Menunggu Approve",
            "count": n,
            "severity": "medium" if n > 0 else "ok",
            "url": "/web/pengadaan/opname",
            "icon": "✓",
        } if n > 0 else None

    # =========================================================================
    # RECENT ACTIVITY
    # =========================================================================
    def _recent_kunjungan(self, today: date, limit: int = 5) -> list[dict]:
        today_start = datetime.combine(today, time.min)
        rows = self.db.execute(
            select(Kunjungan, Pasien)
            .join(Pasien, Pasien.id_pasien == Kunjungan.id_pasien)
            .where(Kunjungan.tgl_kunjungan >= today_start)
            .order_by(Kunjungan.tgl_kunjungan.desc())
            .limit(limit)
        ).all()
        return [
            {
                "id_kunjungan": k.id_kunjungan,
                "nama_pasien": p.nama,
                "no_rm": p.no_rm,
                "tgl_kunjungan": k.tgl_kunjungan.strftime("%H:%M") if k.tgl_kunjungan else "-",
                "status": k.status_antrian or "—",
                "keluhan_utama": (k.keluhan_utama or "")[:50],
            }
            for k, p in rows
        ]


__all__ = ["DashboardService"]
