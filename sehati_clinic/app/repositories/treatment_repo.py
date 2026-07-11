"""
TreatmentRepository — CRUD untuk kunjungan_tindakan (Ruang Tindakan workflow).

Plus query helper untuk antrian perawat dan detail tindakan.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Kunjungan,
    KunjunganTindakan,
    MasterStaf,
    MasterTreatment,
    Pasien,
    PemeriksaanKlinis,
    TreatmentKomponen,
)


class TreatmentRepository:
    """CRUD untuk kunjungan_tindakan + queries antrian/detail."""

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # CRUD master_treatment — untuk halaman Master Treatment (Owner/Superadmin)
    # =========================================================================
    def get_master_by_id(self, id_treatment: int) -> Optional[MasterTreatment]:
        return self.db.get(MasterTreatment, id_treatment)

    def list_master_all(
        self, keyword: Optional[str] = None, only_active: bool = False, limit: int = 500
    ) -> list[MasterTreatment]:
        """List semua master_treatment dengan filter optional."""
        stmt = select(MasterTreatment)
        if keyword and keyword.strip():
            term = f"%{keyword.strip()}%"
            stmt = stmt.where(MasterTreatment.nama_treatment.ilike(term))
        if only_active:
            stmt = stmt.where(MasterTreatment.is_active.is_(True))
        stmt = stmt.order_by(MasterTreatment.nama_treatment.asc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def create_master(self, treatment: MasterTreatment) -> MasterTreatment:
        self.db.add(treatment)
        self.db.flush()
        return treatment

    def update_master(self, treatment: MasterTreatment, data: dict) -> MasterTreatment:
        for k, v in data.items():
            if hasattr(treatment, k):
                setattr(treatment, k, v)
        self.db.flush()
        return treatment

    def set_active_master(self, treatment: MasterTreatment, is_active: bool) -> MasterTreatment:
        treatment.is_active = is_active
        self.db.flush()
        return treatment

    # =========================================================================
    # GET master treatment list — untuk dropdown SOAP form
    # =========================================================================
    def list_master_active(self, limit: int = 200) -> list[MasterTreatment]:
        """
        List master_treatment yang is_active=True, urut by nama_treatment.
        Dipakai untuk dropdown tindakan di SOAP form dokter.
        """
        stmt = (
            select(MasterTreatment)
            .where(MasterTreatment.is_active.is_(True))
            .order_by(MasterTreatment.nama_treatment.asc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    # =========================================================================
    # GET kunjungan_tindakan untuk start/end
    # =========================================================================
    def get_tindakan_by_id(self, id_kunjungan_tindakan: int) -> Optional[KunjunganTindakan]:
        return self.db.get(KunjunganTindakan, id_kunjungan_tindakan)

    def update_status_tindakan(
        self,
        tindakan: KunjunganTindakan,
        status_baru: str,
        id_staf_pelaksana: Optional[int] = None,
        waktu_mulai: Optional[datetime] = None,
        waktu_selesai: Optional[datetime] = None,
    ) -> KunjunganTindakan:
        tindakan.status_tindakan = status_baru
        if id_staf_pelaksana is not None:
            tindakan.id_staf_pelaksana = id_staf_pelaksana
        if waktu_mulai is not None:
            tindakan.waktu_mulai = waktu_mulai
        if waktu_selesai is not None:
            tindakan.waktu_selesai = waktu_selesai
        self.db.flush()
        return tindakan

    # =========================================================================
    # Smart check — ada tindakan PENDING/PROSES tersisa?
    # =========================================================================
    def count_tindakan_aktif(self, id_kunjungan: int) -> int:
        """Hitung tindakan yang masih PENDING atau PROSES untuk kunjungan ini."""
        stmt = (
            select(func.count(KunjunganTindakan.id_kunjungan_tindakan))
            .where(KunjunganTindakan.id_kunjungan == id_kunjungan)
            .where(KunjunganTindakan.status_tindakan.in_(["PENDING", "PROSES"]))
        )
        return int(self.db.execute(stmt).scalar() or 0)

    # =========================================================================
    # Antrian Ruang Tindakan hari ini
    # =========================================================================
    def list_antrian_ruang_tindakan(
        self,
        today: Optional[date] = None,
    ) -> list[tuple[Kunjungan, Pasien, int, int]]:
        """
        List antrian perawat — pasien hari ini dengan status:
        - KONSULTASI: visibility untuk situational awareness (pasien sedang konsul,
          perawat bisa standby kalau load akan tinggi)
        - ANTRI_TREATMENT / ON_TREATMENT: ranah perawat langsung

        Status ANTRI_KONSULTASI TIDAK include lagi (TODO-NEW-4, 11 Juni 2026):
        - Reasoning: pasien belum dipanggil dokter, perawat tidak bisa kerjakan
          apapun. Saat dulu di-include untuk "situational awareness" ternyata
          membuat UI clutter karena tombol Mulai tidak ada efek (kosong).
        - DEC-063 sambungan: hapus ANTRI_KONSULTASI dari list.

        Status ANTRI_BAYAR & ANTRI_OBAT TIDAK include — itu ranah kasir/apoteker.
        COMPLETED & BATAL juga tidak include.

        Return list of (Kunjungan, Pasien, count_pending, count_proses).
        """
        if today is None:
            today = date.today()

        stmt = (
            select(Kunjungan, Pasien)
            .join(Pasien, Kunjungan.id_pasien == Pasien.id_pasien)
            .where(func.date(Kunjungan.tgl_kunjungan) == today)
            .where(Kunjungan.status_antrian.in_([
                "KONSULTASI",
                "ANTRI_TREATMENT",
                "ON_TREATMENT",
            ]))
            .order_by(Kunjungan.nomor_antrean.asc())
        )
        rows = self.db.execute(stmt).all()

        # Per row, count tindakan PENDING & PROSES (sub-query bisa, tapi clean separate query)
        result = []
        for kunjungan, pasien in rows:
            stmt_pending = (
                select(func.count(KunjunganTindakan.id_kunjungan_tindakan))
                .where(KunjunganTindakan.id_kunjungan == kunjungan.id_kunjungan)
                .where(KunjunganTindakan.status_tindakan == "PENDING")
            )
            stmt_proses = (
                select(func.count(KunjunganTindakan.id_kunjungan_tindakan))
                .where(KunjunganTindakan.id_kunjungan == kunjungan.id_kunjungan)
                .where(KunjunganTindakan.status_tindakan == "PROSES")
            )
            n_pending = int(self.db.execute(stmt_pending).scalar() or 0)
            n_proses = int(self.db.execute(stmt_proses).scalar() or 0)
            result.append((kunjungan, pasien, n_pending, n_proses))
        return result

    # =========================================================================
    # Detail kunjungan untuk iPad ruang tindakan
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

    def get_pemeriksaan_klinis(self, id_kunjungan: int) -> Optional[PemeriksaanKlinis]:
        """1 SOAP terakhir untuk kunjungan ini."""
        stmt = (
            select(PemeriksaanKlinis)
            .where(PemeriksaanKlinis.id_kunjungan == id_kunjungan)
            .order_by(PemeriksaanKlinis.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_tindakan_for_kunjungan(
        self, id_kunjungan: int
    ) -> list[tuple[KunjunganTindakan, MasterTreatment, Optional[MasterStaf]]]:
        """List tindakan untuk 1 kunjungan + JOIN MasterTreatment + MasterStaf pelaksana."""
        stmt = (
            select(KunjunganTindakan, MasterTreatment, MasterStaf)
            .join(MasterTreatment, KunjunganTindakan.id_treatment == MasterTreatment.id_treatment)
            .outerjoin(MasterStaf, KunjunganTindakan.id_staf_pelaksana == MasterStaf.id_staf)
            .where(KunjunganTindakan.id_kunjungan == id_kunjungan)
            .order_by(KunjunganTindakan.id_kunjungan_tindakan.asc())
        )
        rows = self.db.execute(stmt).all()
        return [(t, tr, s) for t, tr, s in rows]

    def list_komponen_bahan(self, id_treatment: int) -> list[TreatmentKomponen]:
        """List bahan klinik (komponen) yang dipakai per treatment — untuk auto-deduct BHP."""
        stmt = (
            select(TreatmentKomponen)
            .where(TreatmentKomponen.id_treatment == id_treatment)
        )
        return list(self.db.execute(stmt).scalars().all())


__all__ = ["TreatmentRepository"]
