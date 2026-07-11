"""
KasirRepository — CRUD untuk kasir + apotek (transaksi_kasir, detail, pembayaran).

Plus queries:
- antrian ANTRI_BAYAR hari ini
- riwayat bayar hari ini (untuk akses cetak nota pasca-bayar)
- tindakan SELESAI per kunjungan (sumber tagihan treatment)
- resep PENDING per kunjungan (sumber tagihan produk)
- cek existing transaksi (bulletproof check anti-duplicate billing)
- rekap shift per kasir
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Kunjungan,
    KunjunganResep,
    KunjunganTindakan,
    MasterProduk,
    MasterStaf,
    MasterTreatment,
    Pasien,
    TransaksiDetailProduk,
    TransaksiKasir,
    TransaksiPembayaran,
)


class KasirRepository:
    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # ANTRIAN — ANTRI_BAYAR hari ini
    # =========================================================================
    def list_antrian_bayar(
        self, today: Optional[date] = None
    ) -> list[tuple[Kunjungan, Pasien, int, int]]:
        """
        List antrian ANTRI_BAYAR hari ini + count tindakan & resep.

        Return list of (Kunjungan, Pasien, jumlah_tindakan, jumlah_resep_pending).
        """
        if today is None:
            today = date.today()

        stmt = (
            select(Kunjungan, Pasien)
            .join(Pasien, Kunjungan.id_pasien == Pasien.id_pasien)
            .where(func.date(Kunjungan.tgl_kunjungan) == today)
            .where(Kunjungan.status_antrian == "ANTRI_BAYAR")
            .order_by(Kunjungan.nomor_antrean.asc())
        )
        rows = self.db.execute(stmt).all()

        result = []
        for kunjungan, pasien in rows:
            n_tindakan = self.db.execute(
                select(func.count(KunjunganTindakan.id_kunjungan_tindakan))
                .where(KunjunganTindakan.id_kunjungan == kunjungan.id_kunjungan)
                .where(KunjunganTindakan.status_tindakan == "SELESAI")
            ).scalar() or 0
            n_resep = self.db.execute(
                select(func.count(KunjunganResep.id_resep))
                .where(KunjunganResep.id_kunjungan == kunjungan.id_kunjungan)
                .where(KunjunganResep.status_item == "PENDING")
            ).scalar() or 0
            result.append((kunjungan, pasien, int(n_tindakan), int(n_resep)))
        return result

    # =========================================================================
    # RIWAYAT BAYAR HARI INI — untuk akses cetak nota pasca-bayar
    # =========================================================================
    def list_riwayat_bayar_hari_ini(
        self, today: Optional[date] = None
    ) -> list[tuple[TransaksiKasir, Kunjungan, Pasien]]:
        """
        List transaksi yang waktu_bayar-nya hari ini, urut terbaru dulu.

        Return list of (TransaksiKasir, Kunjungan, Pasien) untuk diakses
        cetak nota dan view detail tagihan dari halaman antrian.
        """
        if today is None:
            today = date.today()

        stmt = (
            select(TransaksiKasir, Kunjungan, Pasien)
            .join(Kunjungan, TransaksiKasir.id_kunjungan == Kunjungan.id_kunjungan)
            .join(Pasien, Kunjungan.id_pasien == Pasien.id_pasien)
            .where(func.date(TransaksiKasir.waktu_bayar) == today)
            .order_by(TransaksiKasir.waktu_bayar.desc())
        )
        rows = self.db.execute(stmt).all()
        return [(row[0], row[1], row[2]) for row in rows]

    # =========================================================================
    # TAGIHAN — sumber data
    # =========================================================================
    def get_kunjungan_with_pasien(
        self, id_kunjungan: int
    ) -> Optional[tuple[Kunjungan, Pasien]]:
        stmt = (
            select(Kunjungan, Pasien)
            .join(Pasien, Kunjungan.id_pasien == Pasien.id_pasien)
            .where(Kunjungan.id_kunjungan == id_kunjungan)
        )
        row = self.db.execute(stmt).first()
        return (row[0], row[1]) if row else None

    def get_tindakan_selesai_for_billing(
        self, id_kunjungan: int
    ) -> list[tuple[KunjunganTindakan, MasterTreatment]]:
        """List tindakan SELESAI di kunjungan ini + master_treatment (untuk harga)."""
        stmt = (
            select(KunjunganTindakan, MasterTreatment)
            .join(MasterTreatment, KunjunganTindakan.id_treatment == MasterTreatment.id_treatment)
            .where(KunjunganTindakan.id_kunjungan == id_kunjungan)
            .where(KunjunganTindakan.status_tindakan == "SELESAI")
            .order_by(KunjunganTindakan.id_kunjungan_tindakan.asc())
        )
        rows = self.db.execute(stmt).all()
        return [(row[0], row[1]) for row in rows]

    def get_resep_pending_for_billing(
        self, id_kunjungan: int
    ) -> list[tuple[KunjunganResep, MasterProduk]]:
        """List resep PENDING di kunjungan ini + master_produk."""
        stmt = (
            select(KunjunganResep, MasterProduk)
            .join(MasterProduk, KunjunganResep.id_produk == MasterProduk.id_produk)
            .where(KunjunganResep.id_kunjungan == id_kunjungan)
            .where(KunjunganResep.status_item == "PENDING")
            .order_by(KunjunganResep.id_resep.asc())
        )
        rows = self.db.execute(stmt).all()
        return [(row[0], row[1]) for row in rows]

    # =========================================================================
    # BULLETPROOF — cek transaksi existing
    # =========================================================================
    def get_transaksi_for_kunjungan(self, id_kunjungan: int) -> Optional[TransaksiKasir]:
        """
        Cek apakah kunjungan ini sudah ada transaksi.
        Return LATEST transaksi (ORDER BY waktu_bayar DESC) supaya cutoff
        untuk deteksi items_belum_berbayar (FLOW-D Part B) tepat.
        """
        stmt = (
            select(TransaksiKasir)
            .where(TransaksiKasir.id_kunjungan == id_kunjungan)
            .order_by(TransaksiKasir.waktu_bayar.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def count_transaksi_for_kunjungan(self, id_kunjungan: int) -> int:
        """
        Hitung total transaksi untuk kunjungan ini. Dipakai oleh
        PemeriksaanService untuk cap max 1 reopen per kunjungan (FLOW-D Part C).
        """
        from sqlalchemy import func as _func
        stmt = (
            select(_func.count(TransaksiKasir.id_transaksi))
            .where(TransaksiKasir.id_kunjungan == id_kunjungan)
        )
        return int(self.db.execute(stmt).scalar() or 0)

    # =========================================================================
    # BAYAR — INSERT transaksi + detail + pembayaran
    # =========================================================================
    def create_transaksi(self, trx: TransaksiKasir) -> TransaksiKasir:
        self.db.add(trx)
        self.db.flush()
        return trx

    def add_detail_produk(self, detail: TransaksiDetailProduk) -> TransaksiDetailProduk:
        self.db.add(detail)
        self.db.flush()
        return detail

    def add_pembayaran(self, pembayaran: TransaksiPembayaran) -> TransaksiPembayaran:
        self.db.add(pembayaran)
        self.db.flush()
        return pembayaran

    def mark_resep_dibayar(self, id_kunjungan: int) -> int:
        """
        Update semua kunjungan_resep PENDING di kunjungan ini → DIBAYAR.
        Return count yang ter-update.
        """
        from sqlalchemy import update
        stmt = (
            update(KunjunganResep)
            .where(KunjunganResep.id_kunjungan == id_kunjungan)
            .where(KunjunganResep.status_item == "PENDING")
            .values(status_item="DIBAYAR")
        )
        result = self.db.execute(stmt)
        return result.rowcount or 0

    # =========================================================================
    # VOID ITEM
    # =========================================================================
    def get_resep_by_id(self, id_resep: int) -> Optional[KunjunganResep]:
        return self.db.get(KunjunganResep, id_resep)

    def void_resep(
        self,
        resep: KunjunganResep,
        id_staf_void: int,
    ) -> KunjunganResep:
        """Set status BATAL + id_staf_void + waktu_void."""
        resep.status_item = "BATAL"
        resep.id_staf_void = id_staf_void
        resep.waktu_void = datetime.now()  # A4: WIB (match void_at)
        self.db.flush()
        return resep

    # =========================================================================
    # REKAP SHIFT
    # =========================================================================
    def list_past_day_transaksi(
        self,
        tgl_mulai: datetime,
        tgl_akhir: datetime,
        no_rm: str = "",
        status_filter: str = "",
    ) -> list[tuple[TransaksiKasir, Pasien]]:
        """Phase 7 (#364): List transaksi dalam range tanggal untuk Admin/Owner.

        Filter:
        - tgl_mulai .. tgl_akhir (inclusive) berdasarkan waktu_bayar
        - no_rm: substring match (kosong = semua)
        - status_filter: 'BAYAR' / 'VOID' / 'all' (kosong = semua)
        """
        stmt = (
            select(TransaksiKasir, Pasien)
            .join(Kunjungan, TransaksiKasir.id_kunjungan == Kunjungan.id_kunjungan, isouter=True)
            .join(Pasien, Kunjungan.id_pasien == Pasien.id_pasien, isouter=True)
            .where(TransaksiKasir.waktu_bayar >= tgl_mulai)
            .where(TransaksiKasir.waktu_bayar < tgl_akhir)
            .order_by(TransaksiKasir.waktu_bayar.desc())
        )
        if no_rm:
            stmt = stmt.where(Pasien.no_rm.like(f"%{no_rm}%"))
        if status_filter and status_filter.upper() in ("BAYAR", "VOID"):
            stmt = stmt.where(TransaksiKasir.status_transaksi == status_filter.upper())
        rows = self.db.execute(stmt).all()
        return [(row[0], row[1]) for row in rows]

    def list_transaksi_shift(
        self,
        id_staf_kasir: int,
        sejak: datetime,
    ) -> list[tuple[TransaksiKasir, Pasien]]:
        """List transaksi yang dibuat oleh kasir ini sejak waktu_mulai_shift."""
        stmt = (
            select(TransaksiKasir, Pasien)
            .join(Kunjungan, TransaksiKasir.id_kunjungan == Kunjungan.id_kunjungan)
            .join(Pasien, Kunjungan.id_pasien == Pasien.id_pasien)
            .where(TransaksiKasir.id_staf_kasir == id_staf_kasir)
            .where(TransaksiKasir.waktu_bayar >= sejak)
            .where(TransaksiKasir.status_transaksi == "BAYAR")  # A1: exclude VOID
            .order_by(TransaksiKasir.waktu_bayar.desc())
        )
        rows = self.db.execute(stmt).all()
        return [(row[0], row[1]) for row in rows]

    def aggregate_pembayaran_shift(
        self,
        id_staf_kasir: int,
        sejak: datetime,
    ) -> list[tuple[str, int, Decimal]]:
        """
        Group pembayaran by metode_bayar untuk transaksi kasir ini sejak shift mulai.

        Return list of (metode_bayar, jumlah_transaksi, total_nominal).
        """
        stmt = (
            select(
                TransaksiPembayaran.metode_bayar,
                func.count(TransaksiPembayaran.id_pembayaran).label("count"),
                func.sum(TransaksiPembayaran.nominal).label("total"),
            )
            .join(TransaksiKasir, TransaksiPembayaran.id_transaksi == TransaksiKasir.id_transaksi)
            .where(TransaksiKasir.id_staf_kasir == id_staf_kasir)
            .where(TransaksiKasir.waktu_bayar >= sejak)
            .where(TransaksiKasir.status_transaksi == "BAYAR")  # A1: exclude VOID
            .group_by(TransaksiPembayaran.metode_bayar)
        )
        rows = self.db.execute(stmt).all()
        return [(row[0], int(row[1]), Decimal(str(row[2] or 0))) for row in rows]


__all__ = ["KasirRepository"]
