"""
MembershipBenefitService (#362B-B) — CRUD master_membership_benefit_treatment.

Owner config kuota treatment per tier:
- Tier VIP: 6x facial/bulan, 2x laser/tahun
- Tier VVIP: 12x facial/bulan, 4x laser/tahun, dll

Saat aktivasi membership, kuota auto-create dari benefit ini (TOTAL_PAKET eager,
BULANAN lazy create saat dispense).
"""

from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    MasterMembership,
    MasterMembershipBenefitTreatment,
    MasterTreatment,
    PeriodeKuotaEnum,
)
from app.schemas.membership_benefit import (
    BenefitTreatmentCreate,
    BenefitTreatmentUpdate,
)
from app.services.audit_service import AuditService


class MembershipBenefitService:
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService(db)

    # =========================================================================
    # READ
    # =========================================================================
    def list_by_tier(
        self, id_membership: int, only_active: bool = False,
    ) -> list[dict]:
        """List benefit untuk tier tertentu + enriched dengan nama_treatment."""
        stmt = (
            select(MasterMembershipBenefitTreatment, MasterTreatment)
            .join(MasterTreatment, MasterTreatment.id_treatment == MasterMembershipBenefitTreatment.id_treatment)
            .where(MasterMembershipBenefitTreatment.id_membership == id_membership)
        )
        if only_active:
            stmt = stmt.where(MasterMembershipBenefitTreatment.is_active.is_(True))
        stmt = stmt.order_by(MasterTreatment.nama_treatment.asc())
        rows = self.db.execute(stmt).all()
        result = []
        for b, t in rows:
            periode = b.periode_kuota.value if hasattr(b.periode_kuota, "value") else str(b.periode_kuota)
            result.append({
                "id_benefit": b.id_benefit,
                "id_treatment": b.id_treatment,
                "nama_treatment": t.nama_treatment,
                "harga_treatment": float(t.harga or 0),
                "kuota_total": b.kuota_total,
                "periode_kuota": periode,
                "catatan": b.catatan,
                "is_active": b.is_active,
            })
        return result

    def get_by_id(self, id_benefit: int) -> MasterMembershipBenefitTreatment:
        b = self.db.get(MasterMembershipBenefitTreatment, id_benefit)
        if b is None:
            raise HTTPException(404, f"Benefit {id_benefit} tidak ditemukan.")
        return b

    # =========================================================================
    # CREATE
    # =========================================================================
    def create_benefit(
        self,
        payload: BenefitTreatmentCreate,
        actor_id_staf: int,
        request: Optional[Request] = None,
    ) -> MasterMembershipBenefitTreatment:
        # Validate FK
        tier = self.db.get(MasterMembership, payload.id_membership)
        if tier is None:
            raise HTTPException(400, f"Tier {payload.id_membership} tidak ditemukan.")
        treatment = self.db.get(MasterTreatment, payload.id_treatment)
        if treatment is None:
            raise HTTPException(400, f"Treatment {payload.id_treatment} tidak ditemukan.")

        # Cek duplicate (same tier + treatment)
        existing = self.db.execute(
            select(MasterMembershipBenefitTreatment)
            .where(MasterMembershipBenefitTreatment.id_membership == payload.id_membership)
            .where(MasterMembershipBenefitTreatment.id_treatment == payload.id_treatment)
            .where(MasterMembershipBenefitTreatment.is_active.is_(True))
            .limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                409,
                f"Sudah ada benefit untuk treatment '{treatment.nama_treatment}' di tier {tier.nama_tier}. "
                f"Edit existing atau hapus dulu.",
            )

        try:
            benefit = MasterMembershipBenefitTreatment(
                id_membership=payload.id_membership,
                id_treatment=payload.id_treatment,
                kuota_total=payload.kuota_total,
                periode_kuota=payload.periode_kuota,
                catatan=(payload.catatan or "").strip() or None,
                is_active=True,
            )
            self.db.add(benefit)
            self.db.flush()
            self.audit.log_create(
                id_staf=actor_id_staf,
                tabel="master_membership_benefit_treatment",
                id_target=benefit.id_benefit,
                data_baru={
                    "id_membership": payload.id_membership,
                    "nama_tier": tier.nama_tier,
                    "id_treatment": payload.id_treatment,
                    "nama_treatment": treatment.nama_treatment,
                    "kuota_total": payload.kuota_total,
                    "periode_kuota": (
                        payload.periode_kuota.value
                        if hasattr(payload.periode_kuota, "value")
                        else str(payload.periode_kuota)
                    ),
                },
                request=request,
            )
            self.db.commit()
            self.db.refresh(benefit)
            return benefit
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal create benefit: {e!s}")

    # =========================================================================
    # UPDATE
    # =========================================================================
    def update_benefit(
        self,
        id_benefit: int,
        payload: BenefitTreatmentUpdate,
        actor_id_staf: int,
        request: Optional[Request] = None,
    ) -> MasterMembershipBenefitTreatment:
        benefit = self.get_by_id(id_benefit)
        update_data = payload.model_dump(exclude_unset=True, exclude_none=True)
        try:
            data_lama = {
                k: (
                    getattr(benefit, k).value if hasattr(getattr(benefit, k), "value")
                    else getattr(benefit, k)
                )
                for k in update_data.keys() if hasattr(benefit, k)
            }
            if "catatan" in update_data:
                update_data["catatan"] = (update_data["catatan"] or "").strip() or None
            for k, v in update_data.items():
                setattr(benefit, k, v)
            self.db.flush()
            data_baru = {
                k: (v.value if hasattr(v, "value") else v) for k, v in update_data.items()
            }
            self.audit.log_update(
                id_staf=actor_id_staf,
                tabel="master_membership_benefit_treatment",
                id_target=id_benefit,
                data_lama=data_lama,
                data_baru=data_baru,
                request=request,
            )
            self.db.commit()
            self.db.refresh(benefit)
            return benefit
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal update benefit: {e!s}")

    # =========================================================================
    # DELETE (soft via is_active)
    # =========================================================================
    def set_active(
        self,
        id_benefit: int,
        is_active: bool,
        actor_id_staf: int,
        request: Optional[Request] = None,
    ):
        benefit = self.get_by_id(id_benefit)
        try:
            old = bool(benefit.is_active)
            benefit.is_active = is_active
            self.db.flush()
            self.audit.log_update(
                id_staf=actor_id_staf,
                tabel="master_membership_benefit_treatment",
                id_target=id_benefit,
                data_lama={"is_active": old},
                data_baru={"is_active": is_active},
                request=request,
            )
            self.db.commit()
            return benefit
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal toggle active: {e!s}")


__all__ = ["MembershipBenefitService"]
