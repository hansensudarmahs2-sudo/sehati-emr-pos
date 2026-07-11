"""
AntropometriService — pengukuran fisik pasien per kunjungan.

Operasi:
- upsert(payload): tambah atau update antropometri (1 row per kunjungan)
- get_for_kunjungan(id): get 1 record by id_kunjungan
- get_terakhir_with_clinical(id_pasien): antropometri terbaru + BMI/fat%/lean%
- get_timeline(id_pasien, limit): semua riwayat + BMI computed per row

Catatan klinis:
- Body fat % butuh jenis_kelamin & usia pasien (dari tabel pasien). Sekalian
  service yang hitung biar frontend ringan.
"""

from datetime import datetime
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.models import KunjunganAntropometri
from app.repositories.kunjungan_repo import KunjunganRepository
from app.repositories.pasien_repo import PasienRepository
from app.schemas.antropometri import (
    AntropometriResponse,
    AntropometriTerakhirResponse,
    AntropometriTimelineItem,
    AntropometriTimelineResponse,
    AntropometriUpsertRequest,
)
from app.services._clinical_calc import (
    hitung_bmi,
    hitung_body_fat_pollock,
    hitung_lean_pct,
    hitung_usia,
    kategori_bmi,
    sum_skinfold,
)
from app.services.audit_service import AuditService


class AntropometriService:
    def __init__(self, db: Session):
        self.db = db
        self.kunjungan_repo = KunjunganRepository(db)
        self.pasien_repo = PasienRepository(db)
        self.audit = AuditService(db)

    # =========================================================================
    # UPSERT — atomic INSERT atau UPDATE
    # =========================================================================
    def upsert(
        self,
        payload: AntropometriUpsertRequest,
        id_staf: int,
        request: Optional[Request] = None,
    ) -> dict:
        """
        Cek existing antropometri untuk id_kunjungan ini:
        - Ada → UPDATE field-field yang dikirim
        - Belum ada → INSERT baru

        Memastikan 1 kunjungan = max 1 row antropometri (mencegah duplicate
        kalau perawat & dokter input bersamaan).
        """
        # 1. Validasi kunjungan exists
        kunjungan = self.kunjungan_repo.get_by_id(payload.id_kunjungan)
        if kunjungan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Kunjungan {payload.id_kunjungan} tidak ditemukan.",
            )

        try:
            # Build field dict — hanya kirim field yang TIDAK None / kosong
            # supaya UPDATE tidak overwrite data yang sudah ada dengan None.
            field_set = {
                "berat_badan": payload.berat_badan,
                "tinggi_badan": payload.tinggi_badan,
                "tekanan_darah": (payload.tekanan_darah or None) if payload.tekanan_darah and payload.tekanan_darah.strip() else None,
                "suhu_tubuh": payload.suhu_tubuh,
                "skinfold_titik_1": payload.skinfold_titik_1,
                "skinfold_titik_2": payload.skinfold_titik_2,
                "skinfold_titik_3": payload.skinfold_titik_3,
                "lingkar_perut": payload.lingkar_perut,
            }
            field_terisi = {k: v for k, v in field_set.items() if v is not None}

            # 2. Cek existing
            existing = self.kunjungan_repo.get_antropometri_by_kunjungan(payload.id_kunjungan)

            if existing is not None:
                # UPDATE — snapshot lama untuk audit
                data_lama = {
                    k: getattr(existing, k)
                    for k in field_terisi.keys()
                    if hasattr(existing, k)
                }
                self.kunjungan_repo.update_antropometri(existing, field_terisi)
                # id_staf yang update (tidak di-overwrite ke perawat lama)
                existing.id_staf = id_staf
                self.db.flush()

                self.audit.log_update(
                    id_staf=id_staf,
                    tabel="kunjungan_antropometri",
                    id_target=existing.id_antropometri,
                    data_lama=data_lama,
                    data_baru=field_terisi,
                    request=request,
                )
                self.db.commit()
                self.db.refresh(existing)
                return {
                    "status": "success",
                    "message": "Data antropometri kunjungan ini berhasil diperbarui.",
                    "data": {
                        "id_antropometri": existing.id_antropometri,
                        "id_kunjungan": payload.id_kunjungan,
                        "action": "updated",
                    },
                }

            # INSERT — baru
            antro = KunjunganAntropometri(
                id_kunjungan=payload.id_kunjungan,
                id_staf=id_staf,
                **field_terisi,
            )
            self.kunjungan_repo.add_antropometri(antro)

            self.audit.log_create(
                id_staf=id_staf,
                tabel="kunjungan_antropometri",
                id_target=antro.id_antropometri,
                data_baru={
                    "id_kunjungan": payload.id_kunjungan,
                    **{k: v for k, v in field_terisi.items()},
                },
                request=request,
            )
            self.db.commit()
            self.db.refresh(antro)
            return {
                "status": "success",
                "message": "Data antropometri baru berhasil ditambahkan.",
                "data": {
                    "id_antropometri": antro.id_antropometri,
                    "id_kunjungan": payload.id_kunjungan,
                    "action": "created",
                },
            }
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gagal simpan antropometri: {str(e)}",
            )

    # =========================================================================
    # GET — single record by id_kunjungan
    # =========================================================================
    def get_for_kunjungan(self, id_kunjungan: int) -> AntropometriResponse:
        antro = self.kunjungan_repo.get_antropometri_by_kunjungan(id_kunjungan)
        if antro is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Antropometri untuk kunjungan {id_kunjungan} tidak ditemukan.",
            )
        return AntropometriResponse.model_validate(antro)

    # =========================================================================
    # GET TERAKHIR — last + computed clinical
    # =========================================================================
    def get_terakhir_with_clinical(self, id_pasien: int) -> AntropometriTerakhirResponse:
        """
        Antropometri terbaru pasien + BMI + body fat % + lean %.

        Untuk dashboard dokter (grid kanan antropometri).
        """
        pasien = self.pasien_repo.get_by_id(id_pasien)
        if pasien is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Pasien dengan ID {id_pasien} tidak ditemukan.",
            )

        antro = self.kunjungan_repo.get_antropometri_terakhir(id_pasien)
        if antro is None:
            return AntropometriTerakhirResponse(has_data=False)

        usia = hitung_usia(pasien.tgl_lahir)
        bmi = hitung_bmi(antro.berat_badan, antro.tinggi_badan)
        sum_sf = sum_skinfold(
            antro.skinfold_titik_1,
            antro.skinfold_titik_2,
            antro.skinfold_titik_3,
        )
        jk = pasien.jenis_kelamin.value if hasattr(pasien.jenis_kelamin, "value") else str(pasien.jenis_kelamin or "")
        fat_pct = hitung_body_fat_pollock(jk, usia, sum_sf) if sum_sf > 0 else 0.0
        lean_pct = hitung_lean_pct(fat_pct)

        return AntropometriTerakhirResponse(
            has_data=True,
            berat_badan=antro.berat_badan,
            tinggi_badan=antro.tinggi_badan,
            tekanan_darah=antro.tekanan_darah,
            suhu_tubuh=antro.suhu_tubuh,
            skinfold_titik_1=antro.skinfold_titik_1,
            skinfold_titik_2=antro.skinfold_titik_2,
            skinfold_titik_3=antro.skinfold_titik_3,
            lingkar_perut=antro.lingkar_perut,
            tgl_ukur=(antro.created_at.date() if antro.created_at else None),
            bmi=bmi if bmi > 0 else None,
            kategori_bmi=kategori_bmi(bmi) if bmi > 0 else None,
            sum_skinfold=sum_sf if sum_sf > 0 else None,
            body_fat_pct=fat_pct if fat_pct > 0 else None,
            lean_mass_pct=lean_pct if lean_pct > 0 else None,
            usia_saat_ukur=usia if usia > 0 else None,
        )

    # =========================================================================
    # GET TIMELINE — semua riwayat + BMI per row
    # =========================================================================
    def get_timeline(self, id_pasien: int, limit: int = 50) -> AntropometriTimelineResponse:
        """Semua antropometri pasien, sorted DESC by created_at. BMI computed per row."""
        pasien = self.pasien_repo.get_by_id(id_pasien)
        if pasien is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Pasien dengan ID {id_pasien} tidak ditemukan.",
            )

        usia = hitung_usia(pasien.tgl_lahir)
        jk = pasien.jenis_kelamin.value if hasattr(pasien.jenis_kelamin, "value") else str(pasien.jenis_kelamin or "")

        rows = self.kunjungan_repo.list_antropometri_pasien(id_pasien, limit=limit)
        items = []
        for antro in rows:
            bmi = hitung_bmi(antro.berat_badan, antro.tinggi_badan)
            sum_sf = sum_skinfold(
                antro.skinfold_titik_1,
                antro.skinfold_titik_2,
                antro.skinfold_titik_3,
            )
            fat_pct = hitung_body_fat_pollock(jk, usia, sum_sf) if sum_sf > 0 else 0.0
            items.append(AntropometriTimelineItem(
                id_antropometri=antro.id_antropometri,
                id_kunjungan=antro.id_kunjungan,
                tgl_ukur=antro.created_at,
                berat_badan=antro.berat_badan,
                tinggi_badan=antro.tinggi_badan,
                tekanan_darah=antro.tekanan_darah,
                lingkar_perut=antro.lingkar_perut,
                bmi=bmi if bmi > 0 else None,
                body_fat_pct=fat_pct if fat_pct > 0 else None,
            ))

        return AntropometriTimelineResponse(
            id_pasien=id_pasien,
            total=len(items),
            data=items,
        )


__all__ = ["AntropometriService"]
