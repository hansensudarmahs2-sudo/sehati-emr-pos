"""
Integration tests untuk auth endpoints.

Pakai DB sehati real + TestClient.
Asumsi ada staf existing dengan username 'dokter_andi' (lihat conftest.py).

⚠️ Test ini akan UPDATE field is_logged_in / token_expired_at di DB.
Tidak destructive, cuma session state.

Untuk run hanya integration test:
    pytest tests/integration/

Untuk skip integration kalau DB tidak available:
    pytest tests/unit/ -m "not integration"
"""

import pytest


pytestmark = pytest.mark.integration


@pytest.fixture
def login_creds(test_username):
    """Credentials untuk login test. Password harus disesuaikan dengan DB asli."""
    return {
        "username": test_username,
        "password": "password123",  # ⚠️ ganti sesuai password real staf test
    }


def test_login_endpoint_exists(client):
    """POST /api/v1/auth/login harus ada (return 422 untuk request kosong)."""
    response = client.post("/api/v1/auth/login")
    # 422 = validation error (form data required), bukan 404
    assert response.status_code in (400, 422)


def test_login_wrong_password_returns_401(client, test_username):
    """Password salah harus return 401."""
    response = client.post(
        "/api/v1/auth/login",
        data={"username": test_username, "password": "WrongPassword999"},
    )
    assert response.status_code == 401


def test_login_nonexistent_user_returns_401(client):
    """Username tidak ada harus return 401 (sama dengan password salah — security)."""
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "nonexistent_user_xyz", "password": "whatever"},
    )
    assert response.status_code == 401


def test_me_without_token_returns_401(client):
    """Endpoint /me tanpa token harus 401."""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_full_login_flow(client, login_creds):
    """
    End-to-end flow: login → dapat token → /me → logout → /me return 401.

    ⚠️ Akan skip kalau password di fixture tidak sesuai DB real.
    """
    # 1. Login
    login_resp = client.post("/api/v1/auth/login", data=login_creds)
    if login_resp.status_code == 401:
        pytest.skip(
            f"Password '{login_creds['password']}' tidak cocok dengan DB. "
            "Update fixture login_creds dengan password real staf test."
        )
    assert login_resp.status_code == 200

    body = login_resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["user"]["username"] == login_creds["username"]

    token = body["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. /me — return user data
    me_resp = client.get("/api/v1/auth/me", headers=headers)
    assert me_resp.status_code == 200
    me_body = me_resp.json()
    assert me_body["username"] == login_creds["username"]
    assert me_body["is_logged_in"] is True

    # 3. Logout
    logout_resp = client.post("/api/v1/auth/logout", headers=headers)
    assert logout_resp.status_code == 200
    assert logout_resp.json()["status"] == "success"

    # 4. /me setelah logout — 401
    me_after = client.get("/api/v1/auth/me", headers=headers)
    assert me_after.status_code == 401
