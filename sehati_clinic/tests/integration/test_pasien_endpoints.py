"""
Integration tests untuk Pasien endpoints (FO module).

Pakai DB asli + seed data SEED-001/002/003.
Read-only operations — no destructive writes.
"""

import pytest


pytestmark = pytest.mark.integration


# ============================================================================
# AUTH GUARDS
# ============================================================================
def test_cari_pasien_requires_auth(client):
    """GET /pasien/cari tanpa token → 401."""
    resp = client.get("/api/v1/pasien/cari?keyword=test")
    assert resp.status_code == 401


def test_detail_pasien_requires_auth(client):
    resp = client.get("/api/v1/pasien/1")
    assert resp.status_code == 401


def test_riwayat_pasien_requires_auth(client):
    resp = client.get("/api/v1/pasien/1/riwayat")
    assert resp.status_code == 401


# ============================================================================
# SEARCH
# ============================================================================
def test_cari_pasien_with_keyword(client, auth_headers, seed_andi):
    """Search 'SEED' harus return pasien SEED-001/002/003."""
    resp = client.get("/api/v1/pasien/cari?keyword=SEED", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["total_ditemukan"] >= 1
    rm_list = [p["no_rm"] for p in body["data"]]
    assert "SEED-001" in rm_list


def test_cari_pasien_returns_required_fields(client, auth_headers, seed_andi):
    resp = client.get("/api/v1/pasien/cari?keyword=SEED-001", headers=auth_headers)
    assert resp.status_code == 200
    pasien = resp.json()["data"][0]
    for field in ("id_pasien", "no_rm", "nama", "jenis_kelamin", "tipe_membership"):
        assert field in pasien


def test_cari_pasien_with_empty_keyword_validates(client, auth_headers):
    """Keyword wajib non-empty (min_length=1)."""
    resp = client.get("/api/v1/pasien/cari?keyword=", headers=auth_headers)
    assert resp.status_code == 422


def test_cari_pasien_keyword_not_found_returns_empty(client, auth_headers):
    resp = client.get(
        "/api/v1/pasien/cari?keyword=XYZ_NOT_EXIST_999",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["total_ditemukan"] == 0
    assert resp.json()["data"] == []


# ============================================================================
# DETAIL
# ============================================================================
def test_detail_pasien_seed_andi(client, auth_headers, seed_andi):
    """SEED-001 punya 1 alergi (paracetamol)."""
    resp = client.get(
        f"/api/v1/pasien/{seed_andi['id_pasien']}", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["no_rm"] == "SEED-001"
    assert body["nama"] == "SEED Andi Pratama"
    assert body["jenis_kelamin"] == "L"
    assert isinstance(body["alergi"], list)
    assert len(body["alergi"]) >= 1
    # Cek alergi paracetamol ada
    alergen_list = [a["alergen"] for a in body["alergi"]]
    assert "Paracetamol" in alergen_list


def test_detail_pasien_seed_budi_has_penyakit_kronis(
    client, auth_headers, seed_budi
):
    """SEED-003 punya hipertensi."""
    resp = client.get(
        f"/api/v1/pasien/{seed_budi['id_pasien']}", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tipe_membership"] == "VVIP"
    penyakit_names = [p["nama_penyakit"] for p in body["penyakit_kronis"]]
    assert "Hipertensi" in penyakit_names


def test_detail_pasien_not_found(client, auth_headers):
    """ID tidak ada → 404."""
    resp = client.get(
        "/api/v1/pasien/99999999", headers=auth_headers
    )
    assert resp.status_code == 404


# ============================================================================
# RIWAYAT (compound endpoint)
# ============================================================================
def test_riwayat_pasien_seed_sari_has_series(client, auth_headers, seed_sari):
    """SEED-002 punya 6 rencana series + 3 kunjungan executed."""
    resp = client.get(
        f"/api/v1/pasien/{seed_sari['id_pasien']}/riwayat",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["info_pasien"]["no_rm"] == "SEED-002"

    # Ada 3 kunjungan history
    assert body["total_kunjungan"] >= 3

    # Ada 6 rencana series
    assert len(body["riwayat_treatment"]) >= 6

    # Sesi 1-3 status DONE, sesi 4-6 PENDING
    sesi_done = [
        t for t in body["riwayat_treatment"]
        if t["status"] == "DONE"
    ]
    sesi_pending = [
        t for t in body["riwayat_treatment"]
        if t["status"] == "PENDING"
    ]
    assert len(sesi_done) >= 3
    assert len(sesi_pending) >= 3


def test_riwayat_pasien_seed_andi_has_transaksi(
    client, auth_headers, seed_andi
):
    """SEED-001 punya 1 kunjungan + transaksi paid."""
    resp = client.get(
        f"/api/v1/pasien/{seed_andi['id_pasien']}/riwayat",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_kunjungan"] >= 1
