"""
StafRepository — CRUD layer untuk MasterStaf.

Pattern: Repository hanya berisi query. Business logic ada di service layer.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MasterStaf, StafRoleEnum


class StafRepository:
    """CRUD untuk tabel master_staf."""

    def __init__(self, db: Session):
        self.db = db

    # ----- Read -----
    def get_by_id(self, id_staf: int) -> Optional[MasterStaf]:
        return self.db.get(MasterStaf, id_staf)

    def get_by_username(self, username: str) -> Optional[MasterStaf]:
        stmt = select(MasterStaf).where(MasterStaf.username == username)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_all(
        self,
        only_active: bool = False,
        role_filter: Optional[StafRoleEnum] = None,
    ) -> list[MasterStaf]:
        """List semua staf. Pakai filter optional."""
        stmt = select(MasterStaf)
        if only_active:
            stmt = stmt.where(MasterStaf.is_active.is_(True))
        if role_filter is not None:
            stmt = stmt.where(MasterStaf.role == role_filter)
        stmt = stmt.order_by(MasterStaf.id_staf.asc())
        return list(self.db.execute(stmt).scalars().all())

    def list_active(self) -> list[MasterStaf]:
        return self.list_all(only_active=True)

    # ----- Create -----
    def create(self, staf: MasterStaf) -> MasterStaf:
        self.db.add(staf)
        self.db.flush()  # assign id_staf
        return staf

    # ----- Update profile -----
    def update(self, staf: MasterStaf, data: dict) -> MasterStaf:
        """Update field-field non-sensitive (nama, role, username)."""
        ALLOWED = {"nama_staf", "role", "username"}
        for key, value in data.items():
            if key in ALLOWED:
                setattr(staf, key, value)
        self.db.flush()
        return staf

    def set_active(self, staf: MasterStaf, is_active: bool) -> MasterStaf:
        staf.is_active = is_active
        # Kalau di-disable, paksa logout
        if not is_active:
            staf.is_logged_in = False
            staf.token_expired_at = None
        self.db.flush()
        return staf

    # ----- Update password/PIN (sensitive) -----
    def update_password(self, staf: MasterStaf, new_password_hash: str) -> MasterStaf:
        staf.password_hash = new_password_hash
        # Reset password = paksa logout (security best practice)
        staf.is_logged_in = False
        staf.token_expired_at = None
        self.db.flush()
        return staf

    def update_pin(self, staf: MasterStaf, new_pin_hash: Optional[str]) -> MasterStaf:
        staf.pin = new_pin_hash
        self.db.flush()
        return staf

    # ----- Session management (dari auth flow) -----
    def mark_logged_in(
        self,
        staf: MasterStaf,
        token_expired_at: datetime,
        shift_anchor: datetime,
    ) -> MasterStaf:
        """Set is_logged_in=True + anchor shift (preserve kalau hari sama)."""
        staf.is_logged_in = True
        staf.token_expired_at = token_expired_at

        today = shift_anchor.date()
        if not staf.waktu_mulai_shift or staf.waktu_mulai_shift.date() != today:
            staf.waktu_mulai_shift = shift_anchor

        self.db.flush()
        return staf

    def mark_logged_out(self, staf: MasterStaf) -> MasterStaf:
        """Clear session, keep waktu_mulai_shift utuh."""
        staf.is_logged_in = False
        staf.token_expired_at = None
        self.db.flush()
        return staf


__all__ = ["StafRepository"]
