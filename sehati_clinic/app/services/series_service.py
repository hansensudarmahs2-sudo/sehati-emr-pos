"""
SeriesService — manage rencana series treatment + booking sesi berikutnya.

Flow:
- Dokter centang Series N saat SOAP → PemeriksaanService buat:
    - 1 PasienRencanaTreatment urutan_sesi=1, status=SCHEDULED (booked ke kunjungan hari ini)
    - 1 KunjunganTindakan dengan id_rencana=rencana_sesi1.id_rencana
    - N-1 PasienRencanaTreatment urutan_sesi=2..N, status=PENDING (menunggu booking FO)
- Kasir hitung tagihan di sesi 1 = jumlah_sesi × harga_paket (charge full paket).
- Sesi 2..N: FO buka pasien detail → klik "Pakai Sesi" → service ini buat:
    - KunjunganTindakan baru ke kunjungan aktif (atau gagal kalau pasien belum daftar)
    - Update rencana.status = SCHEDULED
    - Transition kunjungan ke ANTRI_TREATMENT

DEC-049: pricing paket di sesi 1, sesi 2..N tidak ada tagihan.
"""

from datetime import date
from typing import Any, Optional

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Kunjungan,
    KunjunganTindakan,
    MasterTreatment,
    PasienRencanaTreatment,
    StatusRencanaTreatmentEnum,
)
from app.services.audit_service import AuditService


class SeriesService:
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService(db)

    # =========================================================================
    # LIST — series aktif (PENDING) per pasien
    # =========================================================================
    def list_active_for_pasien(self, id_pasien: int) -> list[dict[str, Any]]:
        """
        Group rencana PENDING per (id_treatment, id_kunjungan_pembuat).
        Return list dict per series:
            {
                "id_treatment": int,
                "nama_tindakan": str,
                "id_kunjungan_pembuat": int,
                "harga_paket": float | None,
                "harga_normal": float,
                "total_sesi": int,         # total semua sesi
                "sisa_pending": int,       # sesi belum dibooked
                "sudah_terpakai": int,     # sesi dipakai (SCHEDULED/DONE)
                "rencana_pending": [       # list rencana PENDING (untuk button "Pakai Sesi N")
                    {"id_rencana": int, "urutan_sesi": int, "catatan_dokter": str},
                    ...
                ],
            }
        """
        # Query semua rencana untuk pasien ini, kelompok per series
        rows = self.db.execute(
            select(PasienRencanaTreatment)
            .where(PasienRencanaTreatment.id_pasien == id_pasien)
            .order_by(
                PasienRencanaTreatment.id_kunjungan_pembuat.desc(),
                PasienRencanaTreatment.urutan_sesi.asc(),
            )
        ).scalars().all()

        # Group per (id_treatment, id_kunjungan_pembuat)
        groups: dict[tuple, dict] = {}
        for r in rows:
            key = (r.id_treatment, r.id_kunjungan_pembuat)
            if key not in groups:
                groups[key] = {
                    "id_treatment": r.id_treatment,
                    "nama_tindakan": r.nama_tindakan,
                    "id_kunjungan_pembuat": r.id_kunjungan_pembuat,
                    "harga_paket": None,
                    "harga_normal": 0.0,
                    "total_sesi": 0,
                    "sisa_pending": 0,
                    "sudah_terpakai": 0,
                    "rencana_pending": [],
                }
            g = groups[key]
            g["total_sesi"] += 1
            status_v = r.status.value if hasattr(r.status, "value") else str(r.status)
            if status_v == "PENDING":
                g["sisa_pending"] += 1
                g["rencana_pending"].append({
                    "id_rencana": r.id_rencana,
                    "urutan_sesi": r.urutan_sesi,
                    "catatan_dokter": r.catatan_dokter or "",
                })
            else:
                g["sudah_terpakai"] += 1

        # Filter: hanya series yang masih ada sisa PENDING
        series_aktif = [g for g in groups.values() if g["sisa_pending"] > 0]

        # Lookup harga treatment
        if series_aktif:
            id_treatment_list = list({g["id_treatment"] for g in series_aktif})
            treatments = self.db.execute(
                select(MasterTreatment).where(MasterTreatment.id_treatment.in_(id_treatment_list))
            ).scalars().all()
            t_map = {t.id_treatment: t for t in treatments}
            for g in series_aktif:
                t = t_map.get(g["id_treatment"])
                if t:
                    g["harga_normal"] = float(t.harga)
                    g["harga_paket"] = float(t.harga_paket) if t.harga_paket else None

        return series_aktif

    # =========================================================================
    # USE SESSION — FO booking sesi berikutnya ke kunjungan hari ini
    # =========================================================================
    def use_session(
        self,
        id_rencana: int,
        id_kunjungan: int,
        actor_id_staf: int,
        request: Optional[Request] = None,
    ) -> dict[str, Any]:
        """
        Pakai sesi rencana (PENDING → SCHEDULED) + buat kunjungan_tindakan
        baru link ke rencana → pasien masuk antrian Ruang Tindakan.
        Kasir akan charge Rp 0 untuk sesi ini (karena id_rencana set + urutan_sesi > 1).
        """
        # Validate rencana
        rencana: Optional[PasienRencanaTreatment] = self.db.get(
            PasienRencanaTreatment, id_rencana,
        )
        if rencana is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Rencana series #{id_rencana} tidak ditemukan.",
            )
        status_v = (
            rencana.status.value
            if hasattr(rencana.status, "value")
            else str(rencana.status)
        )
        if status_v != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Rencana sesi {rencana.urutan_sesi} status saat ini '{status_v}'. "
                    f"Hanya status PENDING yang bisa di-pakai."
                ),
            )

        # Validate kunjungan
        kunjungan: Optional[Kunjungan] = self.db.get(Kunjungan, id_kunjungan)
        if kunjungan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Kunjungan #{id_kunjungan} tidak ditemukan.",
            )
        if kunjungan.id_pasien != rencana.id_pasien:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Kunjungan ini milik pasien lain (id_pasien={kunjungan.id_pasien}). "
                    f"Rencana sesi milik pasien id_pasien={rencana.id_pasien}."
                ),
            )

        status_lama_kunj = kunjungan.status_antrian
        FORBIDDEN_STATES = ("COMPLETED", "BATAL")
        if status_lama_kunj in FORBIDDEN_STATES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Kunjungan #{id_kunjungan} sudah {status_lama_kunj}. "
                    f"Daftarkan kunjungan baru untuk pakai sesi."
                ),
            )

        try:
            # 1. Create KunjunganTindakan link ke rencana
            tindakan = KunjunganTindakan(
                id_kunjungan=id_kunjungan,
                id_treatment=rencana.id_treatment,
                id_rencana=rencana.id_rencana,
            )
            self.db.add(tindakan)

            # 2. Update rencana status PENDING → SCHEDULED
            rencana.status = StatusRencanaTreatmentEnum.SCHEDULED

            # 3. Transition kunjungan ke ANTRI_TREATMENT (kalau belum maju)
            INITIAL_STATES = ("ANTRI_KONSULTASI", "KONSULTASI")
            if status_lama_kunj in INITIAL_STATES:
                kunjungan.status_antrian = "ANTRI_TREATMENT"

            # 4. Audit
            self.audit.log(
                aksi="SERIES_USE_SESSION",
                id_staf=actor_id_staf,
                tabel_target="pasien_rencana_treatment",
                id_target=id_rencana,
                data_lama={"status": status_v},
                data_baru={
                    "status": "SCHEDULED",
                    "id_kunjungan_baru": id_kunjungan,
                    "urutan_sesi": rencana.urutan_sesi,
                },
                keterangan=(
                    f"FO pakai sesi {rencana.urutan_sesi} dari series "
                    f"'{rencana.nama_tindakan}' (rencana #{id_rencana}) "
                    f"untuk kunjungan #{id_kunjungan}."
                ),
                request=request,
            )

            self.db.commit()
            self.db.refresh(tindakan)
            self.db.refresh(rencana)
            self.db.refresh(kunjungan)

            return {
                "status": "success",
                "message": (
                    f"Sesi {rencana.urutan_sesi} dari series "
                    f"'{rencana.nama_tindakan}' berhasil di-booked ke kunjungan."
                ),
                "data": {
                    "id_rencana": id_rencana,
                    "id_kunjungan_tindakan": tindakan.id_kunjungan_tindakan,
                    "urutan_sesi": rencana.urutan_sesi,
                    "status_kunjungan_baru": kunjungan.status_antrian,
                },
            }
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gagal pakai sesi: {e!s}",
            )


__all__ = ["SeriesService"]
