"""
Integration tests untuk Kunjungan endpoints.

Read-only — list antrian + detail. Hindari modify status (side-effect).
"""

import pytest


pytestmark = pytest.mark.integration


# ============================================================================
# AUTH GUARDS
# ============================================================================
def test_antrian_requires_auth(client):
    resp = client.get("/api/v1/kunjungan/antrian")
    assert resp.status_code == 401


def test_detail_kunjungan_requires_auth(client):
    resp = client.get("/api/v1/kunjungan/1")
    assert resp.status_code == 401


# ============================================================================
# LIST ANTRIAN
# ============================================================================
def test_antrian_hari_ini_returns_list(client, auth_headers):
    """Endpoint antrian return list (mungkin kosong kalau hari ini belum ada)."""
    resp = client.get("/api/v1/kunjungan/antrian", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert "tanggal" in body
    assert "total" in body
    assert isinstance(body["data"], list)


def test_antrian_seed_budi_appears_today(client, auth_headers, seed_budi):
    """SEED-003 punya kunjungan hari ini status ANTRI_BAYAR — harus muncul di antrian."""
    resp = client.get("/api/v1/kunjungan/antrian", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    # ANTRI_BAYAR adalah salah satu status aktif default exclude_completed=true
    no_rm_list = [item["no_rm"] for item in body["data"]]
    # SEED-003 ada di antrian hari ini
    assert "SEED-003" in no_rm_list


def test_antrian_item_has_required_fields(client, auth_headers, seed_budi):
    """Setiap item antrian harus punya snapshot pasien field."""
    resp = client.get("/api/v1/kunjungan/antrian", headers=auth_headers)
    items = resp.json()["data"]
    if not items:
        pytest.skip("Antrian hari ini kosong")
    item = items[0]
    for field in (
        "id_kunjungan", "nomor_antrean", "status_antrian",
        "id_pasien", "no_rm", "nama_pasien",
    ):
        assert field in item


def test_antrian_include_completed_restricted_by_role(client, auth_headers):
    """
    `include_completed=true` butuh role Admin/Owner/Superadmin.

    Test ini akan return 200 kalau test user kebetulan punya role tsb,
    atau 403 kalau role-nya operasional (Dokter/Perawat/Kasir/FO).
    Kedua-duanya valid; yang penting bukan 500.
    """
    resp = client.get(
        "/api/v1/kunjungan/antrian?include_completed=true",
        headers=auth_headers,
    )
    assert resp.status_code in (200, 403)


# ============================================================================
# DETAIL KUNJUNGAN
# ============================================================================
def test_detail_kunjungan_seed_budi(client, auth_headers, seed_budi):
    """Detail kunjungan SEED-003 hari ini."""
    # Ambil id_kunjungan dari antrian (karena SEED-003 ada di antrian hari ini)
    antri = client.get("/api/v1/kunjungan/antrian", headers=auth_headers).json()
    budi_kunjungan = next(
        (item for item in antri["data"] if item["no_rm"] == "SEED-003"),
        None,
    )
    assert budi_kunjungan, "SEED-003 tidak ada di antrian hari ini"

    resp = client.get(
        f"/api/v1/kunjungan/{budi_kunjungan['id_kunjungan']}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["no_rm"] == "SEED-003"
    assert body["status_antrian"] == "ANTRI_BAYAR"
    assert body["nama_pasien"] == "SEED Budi Santoso"


def test_detail_kunjungan_not_found(client, auth_headers):
    resp = client.get("/api/v1/kunjungan/99999999", headers=auth_headers)
    assert resp.status_code == 404


# ============================================================================
# RUANG TINDAKAN — verify perawat sekarang lihat ANTRI_KONSULTASI + KONSULTASI
# ============================================================================
def test_ruang_tindakan_antrian_requires_auth(client):
    resp = client.get("/api/v1/ruang-tindakan/antrian")
    assert resp.status_code == 401


def test_ruang_tindakan_antrian_status_filter(client, auth_headers):
    """
    Setiap item di /ruang-tindakan/antrian harus punya status DI dalam:
    {ANTRI_KONSULTASI, KONSULTASI, ANTRI_TREATMENT, ON_TREATMENT}.

    Status ANTRI_BAYAR & ANTRI_OBAT TIDAK boleh muncul (bukan ranah perawat).
    """
    resp = client.get("/api/v1/ruang-tindakan/antrian", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    valid_statuses = {
        "ANTRI_KONSULTASI", "KONSULTASI",
        "ANTRI_TREATMENT", "ON_TREATMENT",
    }
    excluded_statuses = {"ANTRI_BAYAR", "ANTRI_OBAT", "COMPLETED", "BATAL"}
    for item in body["data"]:
        assert item["status_antrian"] in valid_statuses, (
            f"Status '{item['status_antrian']}' tidak boleh muncul di ruang-tindakan"
        )
        assert item["status_antrian"] not in excluded_statuses
