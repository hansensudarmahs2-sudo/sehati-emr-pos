"""
Smoke tests — pastikan aplikasi minimal jalan tanpa crash.

Run: pytest tests/test_smoke.py
"""

from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)


def test_root_endpoint():
    """GET / harus redirect (303) ke halaman login web."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/web/login"


def test_health_endpoint():
    """GET /health harus return status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_docs_accessible():
    """Swagger UI (/docs) harus dapat diakses."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "swagger" in response.text.lower()
