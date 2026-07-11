"""
MK-L3 — No. RM pasien baru pakai rm_prefix dari master_klinik_config (fallback env).
Run: .venv/bin/pytest tests/integration/test_rm_prefix_config.py -v
"""
from datetime import date

import pytest

from app.db.session import SessionLocal
from app.db.models import MasterKlinikConfig
from app.repositories.pasien_repo import PasienRepository


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def test_rm_prefix_dari_config(db):
    cfg = db.get(MasterKlinikConfig, 1)
    assert cfg is not None
    old = cfg.rm_prefix
    try:
        cfg.rm_prefix = "ZZ"
        db.commit()
        rm = PasienRepository(db).generate_next_no_rm(today=date(2026, 7, 3))
        assert rm.startswith("ZZ-260703-"), rm
    finally:
        cfg.rm_prefix = old
        db.commit()
