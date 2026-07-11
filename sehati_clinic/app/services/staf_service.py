"""
StafService — business logic untuk SDM management.

Audit log:
- Semua aksi mutating dicatat lewat `self.audit`.
- Password & PIN RAW value tidak pernah masuk audit log — hanya
  "PASSWORD_RESET" / "PIN_RESET" event + id_staf target.
"""

from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.db.models import MasterStaf, StafRoleEnum
from app.repositories.staf_repo import StafRepository
from app.schemas.staf import StafCreateRequest, StafResponse, StafUpdateRequest
from app.services.audit_service import AuditService


class StafService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = StafRepository(db)
        self.audit = AuditService(db)

    def list_all(self, only_active: bool = False, role: Optional[StafRoleEnum] = None) -> list[StafResponse]:
        staf_list = self.repo.list_all(only_active=only_active, role_filter=role)
        return [StafResponse.from_orm_with_pin_check(s) for s in staf_list]

    def get_by_id(self, id_staf: int) -> StafResponse:
        staf = self.repo.get_by_id(id_staf)
        if staf is None:
            raise HTTPException(status_code=404, detail=f"Staf dengan ID {id_staf} tidak ditemukan.")
        return StafResponse.from_orm_with_pin_check(staf)

    def _validate_role_change(
        self,
        actor_id_staf: Optional[int],
        target_staf,  # MasterStaf instance, can be None for create
        new_role,
    ) -> None:
        """TIER-SYS (Decision C): validate role assignment per tier hierarchy.

        Rules:
        - Lower tier cannot edit higher tier target.
        - Actor cannot promote to tier higher than self.
        - OWNER role NEVER assignable via UI (must be set via SQL direct).
          Exception: actor IS Owner editing own profile and role unchanged.
        - If actor_id_staf is None: skip check (system-initiated or legacy callsite).
        """
        if actor_id_staf is None:
            return
        # Lazy import to avoid circular dependency at module load
        from app.web.routes._shared import (
            ROLE_TIERS,
            user_tier,
            can_edit_role_of,
            can_promote_to_role,
        )

        actor = self.repo.get_by_id(actor_id_staf)
        if actor is None:
            raise HTTPException(403, "Actor staf tidak ditemukan untuk validasi tier.")

        # Edit existing target — cek tier
        if target_staf is not None:
            if not can_edit_role_of(actor, target_staf):
                raise HTTPException(
                    status_code=403,
                    detail=(
                        f"Anda ({actor.role.value}) tidak punya wewenang edit role staf "
                        f"'{target_staf.nama_staf}' ({target_staf.role.value}). "
                        f"Lower tier tidak boleh edit higher tier."
                    ),
                )

        # Cek promote-to-role
        if new_role is None:
            return

        # OWNER role hard guard
        if new_role == StafRoleEnum.OWNER:
            # Allow only if target sudah Owner (role unchanged, just edit profile)
            if target_staf is not None and target_staf.role == StafRoleEnum.OWNER:
                return
            raise HTTPException(
                status_code=403,
                detail=(
                    "Role OWNER tidak bisa di-set via sistem. "
                    "Pembuatan atau perubahan Owner hanya via SQL direct ke database. "
                    "Hubungi admin teknis (single Owner per database)."
                ),
            )

        # Cek promote tier
        if not can_promote_to_role(actor, new_role):
            new_role_str = new_role.value if hasattr(new_role, "value") else str(new_role)
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Anda ({actor.role.value}) tidak bisa promote ke role '{new_role_str}'. "
                    f"Hanya bisa promote ke tier setara atau lebih rendah."
                ),
            )

    def register_staf_baru(self, payload: StafCreateRequest, actor_id_staf: Optional[int] = None, request: Optional[Request] = None) -> StafResponse:
        # TIER-SYS guard (Decision C)
        self._validate_role_change(actor_id_staf, target_staf=None, new_role=payload.role)
        existing = self.repo.get_by_username(payload.username)
        if existing:
            raise HTTPException(status_code=409, detail=f"Username '{payload.username}' sudah dipakai.")
        try:
            staf = MasterStaf(
                username=payload.username,
                password_hash=hash_password(payload.password),
                nama_staf=payload.nama_staf,
                role=payload.role,
                pin=hash_password(payload.pin) if payload.pin else None,
                is_active=True,
                is_logged_in=False,
            )
            self.repo.create(staf)
            self.audit.log_create(
                id_staf=actor_id_staf or 0,
                tabel="master_staf",
                id_target=staf.id_staf,
                data_baru={
                    "username": staf.username,
                    "nama_staf": staf.nama_staf,
                    "role": staf.role.value if hasattr(staf.role, "value") else str(staf.role),
                    "has_pin": staf.pin is not None,
                },
                request=request,
            )
            self.db.commit()
            self.db.refresh(staf)
            return StafResponse.from_orm_with_pin_check(staf)
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Gagal register staf: {str(e)}")

    def update_profile(self, id_staf: int, payload: StafUpdateRequest, actor_id_staf: Optional[int] = None, request: Optional[Request] = None) -> StafResponse:
        staf = self.repo.get_by_id(id_staf)
        if staf is None:
            raise HTTPException(status_code=404, detail=f"Staf dengan ID {id_staf} tidak ditemukan.")
        update_data = payload.model_dump(exclude_unset=True, exclude_none=True)
        # TIER-SYS guard (Decision C): validate role change kalau payload include "role"
        new_role = update_data.get("role")
        self._validate_role_change(actor_id_staf, target_staf=staf, new_role=new_role)
        if "username" in update_data and update_data["username"] != staf.username:
            existing = self.repo.get_by_username(update_data["username"])
            if existing:
                raise HTTPException(status_code=409, detail=f"Username '{update_data['username']}' sudah dipakai.")
        try:
            data_lama = {
                k: (staf.role.value if k == "role" and hasattr(staf.role, "value") else getattr(staf, k))
                for k in update_data.keys() if hasattr(staf, k)
            }
            self.repo.update(staf, update_data)
            data_baru = {k: (v.value if hasattr(v, "value") else v) for k, v in update_data.items()}
            self.audit.log_update(
                id_staf=actor_id_staf or 0,
                tabel="master_staf",
                id_target=staf.id_staf,
                data_lama=data_lama,
                data_baru=data_baru,
                request=request,
            )
            self.db.commit()
            self.db.refresh(staf)
            return StafResponse.from_orm_with_pin_check(staf)
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Gagal update profile: {str(e)}")

    def reset_password(self, id_staf: int, new_password: str, actor_id_staf: Optional[int] = None, request: Optional[Request] = None) -> dict:
        staf = self.repo.get_by_id(id_staf)
        if staf is None:
            raise HTTPException(status_code=404, detail=f"Staf dengan ID {id_staf} tidak ditemukan.")
        try:
            self.repo.update_password(staf, hash_password(new_password))
            self.audit.log(
                aksi="PASSWORD_RESET",
                id_staf=actor_id_staf or 0,
                tabel_target="master_staf",
                id_target=staf.id_staf,
                keterangan=f"Password '{staf.username}' di-reset oleh staf_id={actor_id_staf}. User dipaksa logout.",
                request=request,
            )
            self.db.commit()
            return {"status": "success", "message": f"Password '{staf.username}' berhasil di-reset. User akan diminta login ulang."}
        except Exception as e:
            self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Gagal reset password: {str(e)}")

    def reset_pin(self, id_staf: int, new_pin: Optional[str], actor_id_staf: Optional[int] = None, request: Optional[Request] = None) -> dict:
        staf = self.repo.get_by_id(id_staf)
        if staf is None:
            raise HTTPException(status_code=404, detail=f"Staf dengan ID {id_staf} tidak ditemukan.")
        try:
            new_pin_hash = hash_password(new_pin) if new_pin else None
            self.repo.update_pin(staf, new_pin_hash)
            action = "di-set" if new_pin else "dihapus"
            self.audit.log(
                aksi="PIN_RESET" if new_pin else "PIN_REMOVED",
                id_staf=actor_id_staf or 0,
                tabel_target="master_staf",
                id_target=staf.id_staf,
                keterangan=f"PIN {action}",
                request=request,
            )
            self.db.commit()
            self.db.refresh(staf)
            return {"status": "success", "message": f"PIN {action} untuk {staf.nama_staf}."}
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Gagal reset PIN: {str(e)}")

    def change_own_password(self, current_user: MasterStaf, old_password: str, new_password: str, request: Optional[Request] = None) -> dict:
        from app.core.security import verify_password
        if not verify_password(old_password, current_user.password_hash):
            raise HTTPException(status_code=403, detail="Password lama tidak cocok.")
        try:
            self.repo.update_password(current_user, hash_password(new_password))
            self.audit.log(
                aksi="PASSWORD_SELF_CHANGE",
                id_staf=current_user.id_staf,
                tabel_target="master_staf",
                id_target=current_user.id_staf,
                keterangan="Password ganti sendiri",
                request=request,
            )
            self.db.commit()
            return {"status": "success", "message": "Password berhasil diganti."}
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Gagal ganti password: {str(e)}")

    def set_active(self, id_staf: int, is_active: bool, actor_id_staf: Optional[int] = None, request: Optional[Request] = None) -> dict:
        staf = self.repo.get_by_id(id_staf)
        if staf is None:
            raise HTTPException(status_code=404, detail=f"Staf dengan ID {id_staf} tidak ditemukan.")
        try:
            # FIX BUG-T3 (10 Juni 2026): repo.update() has allowlist {nama_staf,role,username}
            # — is_active is rejected silently. Use dedicated set_active() repo method
            # which also force-logout on deactivate.
            self.repo.set_active(staf, is_active)
            self.audit.log(
                aksi="STAF_ACTIVATE" if is_active else "STAF_DEACTIVATE",
                id_staf=actor_id_staf or 0,
                tabel_target="master_staf",
                id_target=staf.id_staf,
                data_lama={"is_active": not is_active},
                data_baru={"is_active": is_active},
                request=request,
            )
            self.db.commit()
            self.db.refresh(staf)
            return {"status": "success", "message": f"Staf {staf.nama_staf} {'aktif' if is_active else 'non-aktif'}."}
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Gagal ubah status: {str(e)}")

    # =========================================================================
    # UPDATE ROLE (#326 — Owner-only, block self-edit, block dokter w/ antrian aktif)
    # =========================================================================
    def update_role(
        self,
        id_staf: int,
        new_role: StafRoleEnum,
        actor_id_staf: int,
        request: Optional[Request] = None,
    ) -> dict:
        """Owner-only: ubah role staf existing.

        Validasi:
        1. Tier hierarchy (via _validate_role_change)
        2. Self-edit block: actor tidak boleh ubah role diri sendiri
        3. Dokter dengan antrian aktif: block kalau target dokter masih punya antrian
           PENDING/IN_PROGRESS hari ini
        """
        target = self.repo.get_by_id(id_staf)
        if target is None:
            raise HTTPException(404, f"Staf dengan ID {id_staf} tidak ditemukan.")

        # Validasi 1: self-edit block
        if actor_id_staf == id_staf:
            raise HTTPException(
                403,
                "Tidak boleh ubah role diri sendiri. Untuk demosi Owner, "
                "minta Owner lain atau ubah via SQL direct.",
            )

        # Validasi 2: tier hierarchy (existing helper handles OWNER-guard + tier)
        self._validate_role_change(actor_id_staf, target, new_role)

        # Validasi 3: dokter dengan antrian aktif → block
        if target.role == StafRoleEnum.DOKTER:
            from app.db.models import Kunjungan, StatusKunjunganEnum
            from sqlalchemy import select, and_
            from datetime import date as date_cls

            active_statuses = [
                StatusKunjunganEnum.ANTRI_KONSULTASI,
                StatusKunjunganEnum.KONSULTASI,
                StatusKunjunganEnum.ANTRI_TINDAKAN,
                StatusKunjunganEnum.TINDAKAN,
                StatusKunjunganEnum.ANTRI_OBAT,
                StatusKunjunganEnum.ANTRI_KASIR,
            ]
            count = self.db.scalar(
                select(__import__('sqlalchemy').func.count(Kunjungan.id_kunjungan))
                .where(and_(
                    Kunjungan.id_staf_dokter_assigned == id_staf,
                    Kunjungan.tgl_kunjungan == date_cls.today(),
                    Kunjungan.status_kunjungan.in_(active_statuses),
                ))
            )
            if count and count > 0:
                raise HTTPException(
                    400,
                    f"Dokter {target.nama_staf} masih punya {count} antrian aktif hari ini. "
                    f"Tunggu sampai semua antrian selesai sebelum ubah role.",
                )

        # Lakukan update
        try:
            old_role = target.role
            self.repo.update(target, {"role": new_role})
            self.audit.log(
                aksi="STAF_ROLE_CHANGE",
                id_staf=actor_id_staf,
                tabel_target="master_staf",
                id_target=target.id_staf,
                data_lama={"role": old_role.value if hasattr(old_role, "value") else str(old_role)},
                data_baru={"role": new_role.value if hasattr(new_role, "value") else str(new_role)},
                request=request,
            )
            self.db.commit()
            self.db.refresh(target)
            return {
                "status": "success",
                "message": f"Role {target.nama_staf} diubah ke {new_role.value}.",
            }
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal ubah role: {e!s}")


__all__ = ["StafService"]
