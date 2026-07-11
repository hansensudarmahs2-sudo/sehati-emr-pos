"""
MasterMembershipService (#362A) — business logic untuk CRUD tier membership.

Tier name validation: nama_tier harus match MembershipTierEnum value
(REGULAR/VIP/VVIP) untuk sync dengan pasien.tipe_membership column.
Adding new tier butuh add enum value dulu di _enums.py (Phase 2 future).
"""

from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.models import MasterMembership, MembershipTierEnum
from app.repositories.master_membership_repo import MasterMembershipRepository
from app.schemas.master_membership import (
    MasterMembershipCreate,
    MasterMembershipUpdate,
)
from app.services.audit_service import AuditService


# Valid tier names = enum values (sync constraint)
_VALID_TIER_NAMES = {e.value for e in MembershipTierEnum}


class MasterMembershipService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = MasterMembershipRepository(db)
        self.audit = AuditService(db)

    # =========================================================================
    # READ
    # =========================================================================
    def get_by_id(self, id_membership: int) -> MasterMembership:
        tier = self.repo.get_by_id(id_membership)
        if tier is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Membership tier dengan ID {id_membership} tidak ditemukan.",
            )
        return tier

    def list_all(
        self,
        keyword: Optional[str] = None,
        only_active: bool = False,
        limit: int = 200,
    ) -> list[MasterMembership]:
        return self.repo.list_all(keyword=keyword, only_active=only_active, limit=limit)

    # =========================================================================
    # CREATE
    # =========================================================================
    def create_tier(
        self,
        payload: MasterMembershipCreate,
        actor_id_staf: int,
        request: Optional[Request] = None,
    ) -> MasterMembership:
        nama_clean = payload.nama_tier.strip().upper()

        # ENUM sync validation
        if nama_clean not in _VALID_TIER_NAMES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Nama tier '{nama_clean}' tidak valid. Harus salah satu dari: "
                    f"{sorted(_VALID_TIER_NAMES)}. Untuk add tier baru, "
                    f"tambah dulu enum value di app/db/models/_enums.py "
                    f"(butuh redeploy)."
                ),
            )

        # Unique check
        existing = self.repo.get_by_nama_tier(nama_clean)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Tier '{nama_clean}' sudah ada di master_membership.",
            )

        try:
            tier = MasterMembership(
                nama_tier=nama_clean,
                harga_aktivasi=payload.harga_aktivasi,
                durasi_bulan=payload.durasi_bulan,
                free_konsultasi_dokter=payload.free_konsultasi_dokter,
                diskon_treatment_persen=payload.diskon_treatment_persen,
                diskon_produk_persen=payload.diskon_produk_persen,
                urutan_tampilan=payload.urutan_tampilan,
                catatan=(payload.catatan or "").strip() or None,
                is_active=True,
            )
            self.repo.create(tier)
            self.audit.log_create(
                id_staf=actor_id_staf,
                tabel="master_membership",
                id_target=tier.id_membership,
                data_baru={
                    "nama_tier": nama_clean,
                    "harga_aktivasi": float(payload.harga_aktivasi),
                    "durasi_bulan": payload.durasi_bulan,
                    "free_konsultasi_dokter": payload.free_konsultasi_dokter,
                    "diskon_treatment_persen": float(payload.diskon_treatment_persen),
                    "diskon_produk_persen": float(payload.diskon_produk_persen),
                },
                request=request,
            )
            self.db.commit()
            self.db.refresh(tier)
            return tier
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gagal create tier membership: {str(e)}",
            )

    # =========================================================================
    # UPDATE
    # =========================================================================
    def update_tier(
        self,
        id_membership: int,
        payload: MasterMembershipUpdate,
        actor_id_staf: int,
        request: Optional[Request] = None,
    ) -> MasterMembership:
        tier = self.get_by_id(id_membership)
        update_data = payload.model_dump(exclude_unset=True, exclude_none=True)

        # Validate new nama_tier kalau ganti
        if "nama_tier" in update_data:
            nama_clean = update_data["nama_tier"].strip().upper()
            if nama_clean not in _VALID_TIER_NAMES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Nama tier '{nama_clean}' tidak valid. Harus: "
                        f"{sorted(_VALID_TIER_NAMES)}."
                    ),
                )
            if nama_clean != tier.nama_tier:
                existing = self.repo.get_by_nama_tier(nama_clean)
                if existing is not None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Tier '{nama_clean}' sudah dipakai tier lain.",
                    )
            update_data["nama_tier"] = nama_clean

        if "catatan" in update_data:
            update_data["catatan"] = (update_data["catatan"] or "").strip() or None

        try:
            # Snapshot lama
            data_lama = {
                k: (
                    float(getattr(tier, k))
                    if isinstance(getattr(tier, k), Decimal)
                    else getattr(tier, k)
                )
                for k in update_data.keys()
                if hasattr(tier, k)
            }

            self.repo.update(tier, update_data)

            data_baru = {
                k: (float(v) if isinstance(v, Decimal) else v)
                for k, v in update_data.items()
            }
            self.audit.log_update(
                id_staf=actor_id_staf,
                tabel="master_membership",
                id_target=tier.id_membership,
                data_lama=data_lama,
                data_baru=data_baru,
                request=request,
            )
            self.db.commit()
            self.db.refresh(tier)
            return tier
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gagal update tier: {str(e)}",
            )

    # =========================================================================
    # SET ACTIVE (soft delete)
    # =========================================================================
    def set_active(
        self,
        id_membership: int,
        is_active: bool,
        actor_id_staf: Optional[int] = None,
        request: Optional[Request] = None,
    ) -> MasterMembership:
        tier = self.get_by_id(id_membership)
        old_state = bool(tier.is_active)
        try:
            updated = self.repo.set_active(tier, is_active)
            self.audit.log_update(
                id_staf=actor_id_staf or 0,
                tabel="master_membership",
                id_target=updated.id_membership,
                data_lama={"is_active": old_state},
                data_baru={"is_active": is_active},
                request=request,
            )
            self.db.commit()
            self.db.refresh(updated)
            return updated
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal set_active tier: {e!s}")


__all__ = ["MasterMembershipService"]
