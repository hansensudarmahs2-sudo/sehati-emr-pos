"""
InventoryService — mutasi stok BHP + CRUD master bahan.
"""

from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.db.models import InventoryStok, JenisMutasiEnum, TreatmentKomponen
from app.repositories.inventory_repo import InventoryRepository
from app.repositories.treatment_repo import TreatmentRepository
from app.services.audit_service import AuditService


class InventoryService:
    def __init__(self, db: Session):
        self.db = db
        self.inv_repo = InventoryRepository(db)
        self.treatment_repo = TreatmentRepository(db)

    def deduct_for_treatment(
        self,
        id_treatment: int,
        id_kunjungan_tindakan: int,
        id_kunjungan: int,
        id_staf: int,
    ) -> list[dict]:
        komponen_list = self.treatment_repo.list_komponen_bahan(id_treatment)
        hasil_potong = []

        for komp in komponen_list:
            if komp.id_bahan is None:
                continue

            bahan = self.inv_repo.get_stok_for_update(komp.id_bahan)
            if bahan is None:
                continue

            qty_dipakai = komp.qty
            stok_akhir = self.inv_repo.update_stok_kabin(bahan, delta=-qty_dipakai)

            self.inv_repo.add_history(
                id_bahan=komp.id_bahan,
                id_staf=id_staf,
                jenis=JenisMutasiEnum.TINDAKAN,
                qty_perubahan=-qty_dipakai,
                stok_akhir=stok_akhir,
                referensi=f"Tindakan ID-{id_kunjungan_tindakan}",
                keterangan=f"Auto-potong BHP Kunjungan #{id_kunjungan}",
            )

            hasil_potong.append({
                "id_bahan": komp.id_bahan,
                "nama_bahan": bahan.nama_bahan,
                "qty_potong": qty_dipakai,
                "stok_akhir": stok_akhir,
            })

        return hasil_potong

    # =========================================================================
    # MASTER BAHAN CRUD (service-owned transaction — DEC-030)
    # =========================================================================

    def create_bahan_with_audit(
        self,
        bahan: InventoryStok,
        actor_id_staf: int,
        request: Optional[Request] = None,
    ) -> InventoryStok:
        try:
            created = self.inv_repo.create_bahan(bahan)
            AuditService(self.db).log_create(
                id_staf=actor_id_staf,
                tabel="inventory_stok",
                id_target=created.id_bahan,
                data_baru={
                    "nama_bahan": created.nama_bahan,
                    "satuan": created.satuan,
                    "stok_gudang_utama": float(created.stok_gudang_utama or 0),
                    "stok_kabin": float(created.stok_kabin or 0),
                },
                request=request,
            )
            self.db.commit()
            self.db.refresh(created)
            return created
        except Exception:
            self.db.rollback()
            raise

    def update_bahan_with_audit(
        self,
        bahan: InventoryStok,
        data_lama: dict,
        update_data: dict,
        actor_id_staf: int,
        request: Optional[Request] = None,
    ) -> InventoryStok:
        try:
            updated = self.inv_repo.update_bahan(bahan, update_data)
            AuditService(self.db).log_update(
                id_staf=actor_id_staf,
                tabel="inventory_stok",
                id_target=bahan.id_bahan,
                data_lama=data_lama,
                data_baru=update_data,
                request=request,
            )
            self.db.commit()
            self.db.refresh(updated)
            return updated
        except Exception:
            self.db.rollback()
            raise


__all__ = ["InventoryService"]
