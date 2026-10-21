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

    def get_tindakan_for_update(self, id_kunjungan_tindakan: int) -> Optional[KunjunganTindakan]:
        """Baris tindakan BERKUNCI & segar (populate_existing: objek basi di sesi ditimpa)."""
        from sqlalchemy import select as _select
        return self.db.execute(
            _select(KunjunganTindakan)
            .where(KunjunganTindakan.id_kunjungan_tindakan == id_kunjungan_tindakan)
            .with_for_update().execution_options(populate_existing=True)
        ).scalar_one_or_none()

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
        List antrian perawat — kunjungan hari ini (bukan BATAL) yang PUNYA tindakan
        PENDING/PROSES (`kondisi_T`), apa pun labelnya.

        Bayar dulu T1-5 (spec §3.3): dulu membaca label KONSULTASI / ANTRI_TREATMENT /
        ON_TREATMENT. Akibatnya (a) pasien yang obatnya sudah lunas tapi tindakannya
        menyusul bisa "hilang" kalau labelnya ditulis lain, dan (b) sesi series di
        kunjungan ANTRI_KONSULTASI (Ruling 8, label sengaja tidak dipindah) tak pernah
        sampai ke perawat. Sekarang satu pasien boleh tampil di perawat DAN apotek/kasir.

        ⚠ KONSULTASI tanpa tindakan TIDAK lagi tampil ("situational awareness" lama):
        tombol Kerjakan-nya kosong, alasan yang sama dengan pencabutan ANTRI_KONSULTASI
        (TODO-NEW-4, DEC-063). Jangan kembalikan dengan menambah label ke saringan —
        tambahkan isinya ke `_status_kunjungan` kalau memang perlu.

        Return list of (Kunjungan, Pasien, count_pending, count_proses).
        """
        from app.services._status_kunjungan import kondisi_T, saringan_meja_hari_ini
        if today is None:
            today = date.today()

        stmt = (
            select(Kunjungan, Pasien)
            .join(Pasien, Kunjungan.id_pasien == Pasien.id_pasien)
            .where(saringan_meja_hari_ini(today))
            .where(kondisi_T())
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
        """1 SOAP terakhir untuk kunjungan ini. Draf apoteker DIKECUALIKAN — ruang
        tindakan tidak boleh bekerja atas catatan yang belum disetujui dokter."""
        stmt = (
            select(PemeriksaanKlinis)
            .where(PemeriksaanKlinis.id_kunjungan == id_kunjungan,
                   PemeriksaanKlinis.status_soap == "FINAL")
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
