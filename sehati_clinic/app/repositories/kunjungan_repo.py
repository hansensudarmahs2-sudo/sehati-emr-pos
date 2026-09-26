"""
KunjunganRepository — CRUD untuk kunjungan + antropometri.

Note: scope minimal untuk support pasien_service.register_pasien_baru.
Akan di-extend untuk full FO/dokter/perawat flow di chunk lain.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Kunjungan, KunjunganAntropometri, Pasien, PemeriksaanKlinis


class KunjunganRepository:
    """CRUD untuk tabel kunjungan + antropometri."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, kunjungan: Kunjungan) -> Kunjungan:
        self.db.add(kunjungan)
        self.db.flush()
        return kunjungan

    def get_by_id(self, id_kunjungan: int) -> Optional[Kunjungan]:
        return self.db.get(Kunjungan, id_kunjungan)

    def get_by_id_for_update(self, id_kunjungan: int) -> Optional[Kunjungan]:
        """Lock baris kunjungan (SELECT ... FOR UPDATE) sampai commit/rollback.

        P0-2 (AUDIT_SEHATI_2026-07-10): dipakai `proses_bayar` untuk men-serialisasi
        pembayaran konkuren pada kunjungan yang sama (anti double-charge item sama).
        """
        from sqlalchemy import select

        stmt = (
            select(Kunjungan)
            .where(Kunjungan.id_kunjungan == id_kunjungan)
            .with_for_update()
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_nomor_antrian_berikutnya(self, today: Optional[date] = None) -> int:
        """
        Kembalikan nomor antrian berikutnya untuk hari ini.

        Pertahankan logika dokter dari `dapatkan_antrian_hari_ini()` di kode lama —
        ambil MAX(nomor_antrean) hari ini + 1.
        """
        if today is None:
            today = date.today()

        stmt = (
            select(func.max(Kunjungan.nomor_antrean))
            .where(func.date(Kunjungan.tgl_kunjungan) == today)
        )
        result = self.db.execute(stmt).scalar()
        return (result or 0) + 1

    def list_antrian_hari_ini(self, today: Optional[date] = None) -> list[Kunjungan]:
        """List semua kunjungan hari ini, urut by nomor_antrean."""
        if today is None:
            today = date.today()

        stmt = (
            select(Kunjungan)
            .where(func.date(Kunjungan.tgl_kunjungan) == today)
            .order_by(Kunjungan.nomor_antrean.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_active_kunjungan_today(
        self,
        id_pasien: int,
        today: Optional[date] = None,
    ) -> Optional[Kunjungan]:
        """
        Cek pasien sudah punya kunjungan AKTIF hari ini.

        "Aktif" = status BUKAN COMPLETED dan BUKAN BATAL.
        Return row Kunjungan kalau ada, None kalau tidak.

        Dipakai untuk guard di KunjunganService.kunjungan_lama supaya FO
        tidak bisa daftarkan pasien yang sama 2x di hari yang sama.
        """
        if today is None:
            today = date.today()

        terminal = ("COMPLETED", "BATAL")
        stmt = (
            select(Kunjungan)
            .where(
                Kunjungan.id_pasien == id_pasien,
                func.date(Kunjungan.tgl_kunjungan) == today,
                ~Kunjungan.status_antrian.in_(terminal),
            )
            .order_by(Kunjungan.id_kunjungan.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_antrian_hari_ini_with_pasien(
        self,
        today: Optional[date] = None,
        status_filter: Optional[list[str]] = None,
    ) -> list[tuple[Kunjungan, Pasien, Optional[str]]]:
        """
        List antrian hari ini + data pasien + nama dokter dituju (JOIN — hindari N+1).

        Return list of (Kunjungan, Pasien, dokter_dituju_nama: Optional[str]) tuples,
        urut by nomor_antrean.
        FO-ASSIGN-DOKTER #329 FIX-1: LEFT JOIN ke MasterStaf untuk get nama dokter
        yang di-assign FO. NULL kalau bebas claim.
        """
        from app.db.models import MasterStaf as _MasterStaf
        from sqlalchemy.orm import aliased

        if today is None:
            today = date.today()

        DokterAssigned = aliased(_MasterStaf)
        stmt = (
            select(Kunjungan, Pasien, DokterAssigned.nama_staf)
            .join(Pasien, Kunjungan.id_pasien == Pasien.id_pasien)
            .outerjoin(
                DokterAssigned,
                DokterAssigned.id_staf == Kunjungan.id_staf_dokter_assigned,
            )
            .where(func.date(Kunjungan.tgl_kunjungan) == today)
            .order_by(Kunjungan.nomor_antrean.asc())
        )
        if status_filter:
            stmt = stmt.where(Kunjungan.status_antrian.in_(status_filter))

        rows = self.db.execute(stmt).all()
        return [(row[0], row[1], row[2]) for row in rows]

    def list_antrian_dokter_view(
        self,
        today: Optional[date] = None,
        id_staf_dokter: Optional[int] = None,
    ) -> list[tuple[Kunjungan, Pasien, bool]]:
        """
        Antrian view untuk dokter — hanya pasien yang relevant ke dokter.

        Filter logic:
        - ANTRI_KONSULTASI + KONSULTASI: SEMUA pasien (belum ada owner — siap
          di-claim dokter manapun)
        - ANTRI_TREATMENT / ON_TREATMENT / ANTRI_BAYAR / ANTRI_OBAT:
            * Kalau id_staf_dokter dikasih → hanya kunjungan yang SOAP-nya
              dibuat oleh dokter tsb (SOAP-GUARD scoping per-dokter)
            * Kalau id_staf_dokter=None → kunjungan yang ada SOAP-nya
              (siapa saja) — back-compat dengan API endpoint legacy
        - COMPLETED & BATAL: tidak include

        Return list of (Kunjungan, Pasien, sudah_konsultasi: bool).
        Field `sudah_konsultasi` di-evaluasi vs ANY dokter (untuk badge UI),
        bukan vs dokter yang query — supaya tetap konsisten artinya.
        """
        if today is None:
            today = date.today()

        active_pre = ["ANTRI_KONSULTASI", "KONSULTASI"]
        active_post = ["ANTRI_TREATMENT", "ON_TREATMENT", "ANTRI_BAYAR", "ANTRI_OBAT"]

        # Subquery: id_kunjungan yang ada di pemeriksaan_klinis (any dokter)
        # Draf apoteker (status_soap='DRAFT_APOTEK') BUKAN SOAP — ia belum disetujui
        # dokter mana pun. Tanpa saringan ini, kunjungan resep online akan terlihat
        # seolah konsulnya sudah selesai.
        soap_exists_subq = (
            select(PemeriksaanKlinis.id_kunjungan)
            .where(PemeriksaanKlinis.id_kunjungan == Kunjungan.id_kunjungan,
                   PemeriksaanKlinis.status_soap == "FINAL")
            .exists()
        )

        from sqlalchemy import and_, or_

        # Filter clause untuk active_post: depends on id_staf_dokter
        if id_staf_dokter is not None:
            # Scoping per-dokter: hanya tampil kalau SOAP dibuat dokter ini
            soap_own_subq = (
                select(PemeriksaanKlinis.id_kunjungan)
                .where(
                    PemeriksaanKlinis.id_kunjungan == Kunjungan.id_kunjungan,
                    PemeriksaanKlinis.id_staf_dokter == id_staf_dokter,
                    PemeriksaanKlinis.status_soap == "FINAL",
                )
                .exists()
            )
            active_post_clause = and_(
                Kunjungan.status_antrian.in_(active_post),
                soap_own_subq,
            )
            # FO-ASSIGN-DOKTER (Task #329): scoping untuk ANTRI_KONSULTASI/KONSULTASI
            # - assigned IS NULL → tampil ke semua (kunjungan tanpa pre-assign)
            # - assigned = current dokter → tampil
            # - assigned = dokter lain → hide
            active_pre_clause = and_(
                Kunjungan.status_antrian.in_(active_pre),
                or_(
                    Kunjungan.id_staf_dokter_assigned.is_(None),
                    Kunjungan.id_staf_dokter_assigned == id_staf_dokter,
                ),
            )
        else:
            # Back-compat: tampil kalau ada SOAP (siapa saja)
            active_post_clause = and_(
                Kunjungan.status_antrian.in_(active_post),
                soap_exists_subq,
            )
            # Back-compat: tampil semua ANTRI_KONSULTASI/KONSULTASI
            active_pre_clause = Kunjungan.status_antrian.in_(active_pre)

        # Main query
        stmt = (
            select(Kunjungan, Pasien, soap_exists_subq.label("sudah_konsultasi"))
            .join(Pasien, Kunjungan.id_pasien == Pasien.id_pasien)
            .where(func.date(Kunjungan.tgl_kunjungan) == today)
            .where(
                or_(
                    active_pre_clause,
                    active_post_clause,
                )
            )
            .order_by(Kunjungan.nomor_antrean.asc())
        )
        rows = self.db.execute(stmt).all()
        return [(row[0], row[1], bool(row[2])) for row in rows]

    def get_with_pasien(self, id_kunjungan: int) -> Optional[tuple[Kunjungan, Pasien]]:
        """Get 1 kunjungan + pasien-nya (untuk detail page)."""
        stmt = (
            select(Kunjungan, Pasien)
            .join(Pasien, Kunjungan.id_pasien == Pasien.id_pasien)
            .where(Kunjungan.id_kunjungan == id_kunjungan)
        )
        row = self.db.execute(stmt).first()
        if row is None:
            return None
        return (row[0], row[1])

    def update_status(self, kunjungan: Kunjungan, status_baru: str) -> Kunjungan:
        kunjungan.status_antrian = status_baru
        self.db.flush()
        return kunjungan

    # ----- Antropometri -----
    def add_antropometri(self, antro: KunjunganAntropometri) -> KunjunganAntropometri:
        self.db.add(antro)
        self.db.flush()
        return antro

    def get_antropometri_terakhir(self, id_pasien: int) -> Optional[KunjunganAntropometri]:
        """
        Antropometri terbaru dari semua kunjungan pasien (untuk header).

        Ordering rule (per keputusan dr. Hansen Week 4 smoke test):
        - Primary: `updated_at` DESC — yang terakhir di-edit menang.
          Ini supaya kalau dokter koreksi antropometri row lama, koreksi itu
          yang muncul di header (bukan row yang last INSERTED).
        - Fallback: `created_at` DESC — untuk row lama (sebelum migrasi
          tambah updated_at) yang nilai updated_at-nya backfill = created_at,
          atau edge case race condition.
        """
        stmt = (
            select(KunjunganAntropometri)
            .join(Kunjungan, KunjunganAntropometri.id_kunjungan == Kunjungan.id_kunjungan)
            .where(Kunjungan.id_pasien == id_pasien)
            .order_by(
                func.coalesce(
                    KunjunganAntropometri.updated_at,
                    KunjunganAntropometri.created_at,
                ).desc()
            )
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_antropometri_by_kunjungan(
        self, id_kunjungan: int
    ) -> Optional[KunjunganAntropometri]:
        """Get antropometri untuk 1 kunjungan (1:1 by design)."""
        stmt = (
            select(KunjunganAntropometri)
            .where(KunjunganAntropometri.id_kunjungan == id_kunjungan)
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def update_antropometri(
        self,
        antro: KunjunganAntropometri,
        data: dict,
    ) -> KunjunganAntropometri:
        """Update field antropometri yang ada (in-place). Caller commit-nya."""
        for key, value in data.items():
            if hasattr(antro, key):
                setattr(antro, key, value)
        self.db.flush()
        return antro

    def list_antropometri_timeline(
        self,
        id_pasien: int,
        limit: int = 50,
    ) -> list[KunjunganAntropometri]:
        """Timeline antropometri untuk 1 pasien — sorted desc by created_at."""
        stmt = (
            select(KunjunganAntropometri)
            .join(Kunjungan, Kunjungan.id_kunjungan == KunjunganAntropometri.id_kunjungan)
            .where(Kunjungan.id_pasien == id_pasien)
            .order_by(KunjunganAntropometri.created_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())
