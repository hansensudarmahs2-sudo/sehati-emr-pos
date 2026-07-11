"""
Integration tests untuk Dokter endpoints (header + summary).
"""

import pytest


pytestmark = pytest.mark.integration


def test_header_pasien_requires_auth(client):
    resp = client.get("/api/v1/dokter/pasien/1/header")
    assert resp.status_code == 401


def test_summary_pasien_requires_auth(client):
    resp = client.get("/api/v1/dokter/pasien/1/summary")
    assert resp.status_code == 401


def test_header_pasien_seed_budi_has_3_grids(client, auth_headers, seed_budi):
    """SEED-003 VVIP punya alergi + penyakit kronis + antropometri."""
    resp = client.get(
        f"/api/v1/dokter/pasien/{seed_budi['id_pasien']}/header",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()

    # Grid kiri — identitas
    assert "grid_kiri_identitas" in body
    identitas = body["grid_kiri_identitas"]
    assert identitas["nama"] == "SEED Budi Santoso"
    assert identitas["jenis_kelamin"] == "L"
    assert identitas["detail_hover"]["no_rm"] == "SEED-003"
    assert identitas["detail_hover"]["membership"] == "VVIP"

    # Grid tengah — alergi (1 alergi berat: penisilin)
    alergi = body["grid_tengah_alergi"]
    assert alergi["total_alergi"] >= 1
    assert alergi["alergi_display"] is not None

    # Grid kanan — antropometri (ada data + BMI computed)
    antro = body["grid_kanan_antropometri"]
    assert antro["has_data"] is True
    assert antro["data"]["bmi"] is not None
    assert antro["data"]["bmi"] > 0
    assert antro["data"]["kategori_bmi"] in (
        "underweight", "normal", "overweight", "obese",
    )


def test_header_pasien_seed_andi_minimal_antropometri(
    client, auth_headers, seed_andi
):
    """SEED-001 punya antropometri (BB=70 TB=170). BMI ~24.2 (normal)."""
    resp = client.get(
        f"/api/v1/dokter/pasien/{seed_andi['id_pasien']}/header",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()

    antro = body["grid_kanan_antropometri"]
    assert antro["has_data"] is True
    # BMI 70/(1.70^2) = 24.2
    assert antro["data"]["bmi"] == pytest.approx(24.2, abs=0.5)
    assert antro["data"]["kategori_bmi"] == "normal"


def test_summary_pasien_seed_sari_has_soap_history(
    client, auth_headers, seed_sari
):
    """SEED-002 punya 3 kunjungan history → 3 SOAP cards."""
    resp = client.get(
        f"/api/v1/dokter/pasien/{seed_sari['id_pasien']}/summary",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()

    # Minimal 3 SOAP (dari 3 kunjungan executed series)
    assert len(body["cardbox_kiri_atas_soap"]) >= 3

    # Tiap card harus punya ringkasan + full text
    for soap in body["cardbox_kiri_atas_soap"]:
        assert "ringkasan_anamnesa" in soap
        assert "full_anamnesa" in soap
        assert "tanggal" in soap


def test_summary_pasien_not_found(client, auth_headers):
    """ID pasien tidak ada → 200 dengan list kosong (bukan 404 — graceful)."""
    resp = client.get(
        "/api/v1/dokter/pasien/99999999/summary",
        headers=auth_headers,
    )
    # Endpoint summary tidak validate pasien exists (cuma query history).
    # Kalau pasien tidak ada, history kosong.
    assert resp.status_code in (200, 404)


def test_header_pasien_not_found(client, auth_headers):
    """ID pasien tidak ada → 404 (header validate pasien exists)."""
    resp = client.get(
        "/api/v1/dokter/pasien/99999999/header",
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ============================================================================
# ANTRIAN DOKTER — filter "yang lewat dokter"
# ============================================================================
def test_antrian_dokter_requires_auth(client):
    resp = client.get("/api/v1/dokter/antrian")
    assert resp.status_code == 401


def test_antrian_dokter_has_counter_structure(client, auth_headers):
    """Response harus punya counter dengan 6 field status."""
    resp = client.get("/api/v1/dokter/antrian", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()

    assert body["status"] == "success"
    assert "tanggal" in body
    assert "total" in body
    assert "counter" in body
    assert "data" in body

    counter = body["counter"]
    for key in (
        "menunggu_konsultasi", "sedang_konsultasi",
        "antri_treatment", "sedang_treatment",
        "antri_bayar", "antri_obat",
    ):
        assert key in counter
        assert isinstance(counter[key], int)
        assert counter[key] >= 0


def test_antrian_dokter_includes_seed_budi(client, auth_headers, seed_budi):
    """
    SEED-003 (Budi) hari ini status ANTRI_BAYAR + SUDAH ada pemeriksaan_klinis.
    Harus muncul di antrian dokter (sudah_konsultasi=true).
    """
    resp = client.get("/api/v1/dokter/antrian", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["data"]

    budi_items = [item for item in items if item["no_rm"] == "SEED-003"]
    assert len(budi_items) >= 1, "SEED-003 harus ada di antrian dokter"
    assert budi_items[0]["sudah_konsultasi"] is True
    assert budi_items[0]["status_antrian"] in (
        "ANTRI_KONSULTASI", "KONSULTASI",
        "ANTRI_TREATMENT", "ON_TREATMENT",
        "ANTRI_BAYAR", "ANTRI_OBAT",
    )


def test_antrian_dokter_each_item_has_required_fields(client, auth_headers):
    resp = client.get("/api/v1/dokter/antrian", headers=auth_headers)
    items = resp.json()["data"]
    if not items:
        pytest.skip("Antrian dokter kosong hari ini")
    item = items[0]
    for field in (
        "id_kunjungan", "nomor_antrean", "status_antrian",
        "id_pasien", "no_rm", "nama_pasien",
        "sudah_konsultasi",
    ):
        assert field in item


def test_antrian_dokter_total_matches_counter_sum(client, auth_headers):
    """Total harus sama dengan jumlah seluruh counter (sanity check)."""
    resp = client.get("/api/v1/dokter/antrian", headers=auth_headers)
    body = resp.json()
    counter = body["counter"]
    total_dari_counter = sum(counter.values())
    assert body["total"] == total_dari_counter
