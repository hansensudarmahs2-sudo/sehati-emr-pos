"""
Shared pytest fixtures.

Pakai DB asli `db_sehati` untuk integration tests, dengan asumsi:
- Ada user `dokter_andi` (atau staf existing yang ditentukan via env TEST_USERNAME)
- Password test staf di-set via env TEST_PASSWORD (default 'password123')
- Seed data SEED-001/002/003 sudah dijalankan (run `tools/seed_test_scenarios.py`)

Test TIDAK destructive — read-only operations + session state.
"""

import os
import pytest
from fastapi.testclient import TestClient

from app.main import app


# ============================================================================
# CLIENT — session-scoped
# ============================================================================
@pytest.fixture(scope="session")
def client() -> TestClient:
    """FastAPI TestClient — sesi-scoped, dipakai semua test."""
    return TestClient(app)


# ============================================================================
# TEST CREDENTIALS — via env vars, default ke dokter_andi
# ============================================================================
@pytest.fixture(scope="session")
def test_username() -> str:
    """Username staf yang dipakai untuk test integration auth."""
    return os.getenv("TEST_USERNAME", "dokter_andi")


@pytest.fixture(scope="session")
def test_password() -> str:
    """Password staf test. ⚠️ override via env TEST_PASSWORD kalau perlu."""
    return os.getenv("TEST_PASSWORD", "password123")


@pytest.fixture(scope="session")
def login_creds(test_username, test_password) -> dict:
    """Credentials untuk login test (dict, untuk POST form data)."""
    return {"username": test_username, "password": test_password}


# ============================================================================
# AUTH HEADERS — login & return Authorization Bearer header
# ============================================================================
@pytest.fixture(scope="session")
def auth_headers(client, login_creds) -> dict:
    """
    Login sekali, return headers `{Authorization: Bearer <token>}` untuk
    test endpoint yang butuh auth.

    SESSION-scoped — semua test berbagi 1 token (efisien, hindari
    spam login).

    Kalau login gagal (password salah, akun non-aktif), test akan
    skip dengan pesan jelas.
    """
    resp = client.post("/api/v1/auth/login", data=login_creds)
    if resp.status_code != 200:
        pytest.skip(
            f"Login gagal ({resp.status_code}): {resp.text[:200]}. "
            f"Set env TEST_USERNAME/TEST_PASSWORD atau update fixture."
        )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# SEED DATA FIXTURES — auto-skip kalau seed belum dijalankan
# ============================================================================
def _find_pasien_by_no_rm(client, headers, no_rm: str) -> dict | None:
    """Helper — cari pasien by no_rm, return dict pasien atau None."""
    resp = client.get(f"/api/v1/pasien/cari?keyword={no_rm}", headers=headers)
    if resp.status_code != 200:
        return None
    data = resp.json().get("data", [])
    for p in data:
        if p.get("no_rm") == no_rm:
            return p
    return None


@pytest.fixture(scope="session")
def seed_andi(client, auth_headers) -> dict:
    """SEED-001 Andi Pratama (single treatment COMPLETED kemarin)."""
    pasien = _find_pasien_by_no_rm(client, auth_headers, "SEED-001")
    if pasien is None:
        pytest.skip(
            "Seed data SEED-001 belum ada. Jalankan dulu: "
            "python ../tools/seed_test_scenarios.py"
        )
    return pasien


@pytest.fixture(scope="session")
def seed_sari(client, auth_headers) -> dict:
    """SEED-002 Sari Dewi (series 6 sesi)."""
    pasien = _find_pasien_by_no_rm(client, auth_headers, "SEED-002")
    if pasien is None:
        pytest.skip(
            "Seed data SEED-002 belum ada. Jalankan dulu: "
            "python ../tools/seed_test_scenarios.py"
        )
    return pasien


@pytest.fixture(scope="session")
def seed_budi(client, auth_headers) -> dict:
    """SEED-003 Budi Santoso (VVIP, ANTRI_BAYAR hari ini)."""
    pasien = _find_pasien_by_no_rm(client, auth_headers, "SEED-003")
    if pasien is None:
        pytest.skip(
            "Seed data SEED-003 belum ada. Jalankan dulu: "
            "python ../tools/seed_test_scenarios.py"
        )
    return pasien
