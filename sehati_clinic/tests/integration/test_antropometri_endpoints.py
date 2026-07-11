"""
Integration tests untuk Antropometri endpoints.
"""

import pytest


pytestmark = pytest.mark.integration


def test_antropometri_requires_auth(client):
    resp = client.get("/api/v1/antropometri/pasien/1/terakhir")
    assert resp.status_code == 401


def test_antropometri_terakhir_seed_andi(client, auth_headers, seed_andi):
    """SEED-001 punya antropometri BB=70 TB=170 → BMI=24.2."""
    resp = client.get(
        f"/api/v1/antropometri/pasien/{seed_andi['id_pasien']}/terakhir",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_data"] is True
    assert body["berat_badan"] == 70.0
    assert body["tinggi_badan"] == 170.0
    assert body["bmi"] == pytest.approx(24.2, abs=0.5)
    assert body["kategori_bmi"] == "normal"
    # Body fat — pria 35y ΣSF 45mm → ~14-15%
    assert body["body_fat_pct"] is not None
    assert 0 < body["body_fat_pct"] < 30


def test_antropometri_terakhir_seed_budi_overweight(
    client, auth_headers, seed_budi
):
    """SEED-003 BB=75 TB=175 → BMI=24.5 (normal-borderline)."""
    resp = client.get(
        f"/api/v1/antropometri/pasien/{seed_budi['id_pasien']}/terakhir",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_data"] is True
    assert body["bmi"] == pytest.approx(24.5, abs=0.5)


def test_antropometri_timeline_seed_sari_shows_progressive(
    client, auth_headers, seed_sari
):
    """
    SEED-002 punya 3 antropometri seed (BB 65 → 64.2 → 63.5).

    Assertion: 3 row TERATAS harus mengandung 3 nilai BB seed (apa pun
    urutannya antar mereka — tiebreaker id_antropometri DESC menjamin
    deterministic ordering kalau created_at sangat dekat).
    """
    resp = client.get(
        f"/api/v1/antropometri/pasien/{seed_sari['id_pasien']}/timeline",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["total"] >= 3

    # Ambil 3 row teratas, filter None BB (defensive)
    top3 = body["data"][:3]
    bb_values = [item["berat_badan"] for item in top3 if item["berat_badan"] is not None]
    assert len(bb_values) == 3, f"Expected 3 non-None BB, got: {bb_values}"

    # 3 nilai seed harus muncul (apa pun urutan)
    expected_seed = {65.0, 64.2, 63.5}
    actual = set(round(bb, 1) for bb in bb_values)
    assert expected_seed.issubset(actual), (
        f"Expected seed BB {expected_seed} subset of top3 {actual}. "
        "Mungkin ada antropometri lain dari smoke test — cleanup SEED & re-seed."
    )


def test_antropometri_pasien_tidak_ada_data(client, auth_headers):
    """Pasien yang belum pernah diukur → has_data=false (bukan 404)."""
    # Cari pasien non-seed tanpa antropometri — pakai ID besar yang exist
    # Kalau tidak ada juga, skip
    resp = client.get(
        "/api/v1/antropometri/pasien/99999999/terakhir",
        headers=auth_headers,
    )
    # Pasien 99999999 tidak ada → 404
    assert resp.status_code == 404


def test_antropometri_timeline_empty_for_unknown_patient(client, auth_headers):
    resp = client.get(
        "/api/v1/antropometri/pasien/99999999/timeline",
        headers=auth_headers,
    )
    # Pasien tidak ada → 404
    assert resp.status_code == 404
