"""
MasterMembership repository — CRUD operations.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MasterMembership


class MasterMembershipRepository:
    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # READ
    # =========================================================================
    def get_by_id(self, id_membership: int) -> Optional[MasterMembership]:
        return self.db.get(MasterMembership, id_membership)

    def get_by_nama_tier(self, nama_tier: str) -> Optional[MasterMembership]:
        stmt = (
            select(MasterMembership)
            .where(MasterMembership.nama_tier == nama_tier)
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_all(
        self,
        keyword: Optional[str] = None,
        only_active: bool = False,
        limit: int = 200,
    ) -> list[MasterMembership]:
        stmt = select(MasterMembership)
        if keyword:
            kw = f"%{keyword.strip()}%"
            stmt = stmt.where(MasterMembership.nama_tier.ilike(kw))
        if only_active:
            stmt = stmt.where(MasterMembership.is_active.is_(True))
        stmt = stmt.order_by(
            MasterMembership.urutan_tampilan.asc(),
            MasterMembership.nama_tier.asc(),
        ).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    # =========================================================================
    # CRUD MUTATING
    # =========================================================================
    def create(self, tier: MasterMembership) -> MasterMembership:
        self.db.add(tier)
        self.db.flush()
        return tier

    def update(self, tier: MasterMembership, data: dict) -> MasterMembership:
        """Partial update — only fields present in data."""
        for key, value in data.items():
            if hasattr(tier, key):
                setattr(tier, key, value)
        self.db.flush()
        return tier

    def set_active(self, tier: MasterMembership, is_active: bool) -> MasterMembership:
        tier.is_active = is_active
        self.db.flush()
        return tier
