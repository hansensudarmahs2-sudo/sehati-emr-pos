"""AN-L2b: test rakit payload sisi Sehati (build_payload)."""
import sys, types
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.antro_report_service import AntroReportService


class _JK:
    def __init__(self, v): self.value = v

class _Pasien:
    def __init__(self):
        self.no_rm = "RM-000123"; self.id_pasien = 7
        self.jenis_kelamin = _JK("L"); self.tgl_lahir = date(1984, 1, 1); self.nama = "Uji"

class _Antro:
    id_kunjungan = 99
    tinggi_badan = 170.0; berat_badan = 88.0; lingkar_perut = 102.0
    skinfold_titik_1 = 20.0; skinfold_titik_2 = 30.0; skinfold_titik_3 = 22.0


def test_build_payload_full():
    svc = AntroReportService()
    p = svc.build_payload(pasien=_Pasien(), antro=_Antro(), actor_role="Perawat",
                          actor_staf_id=8, actor_name="Suster", return_url="http://sehati.local/back")
    assert p["request_meta"]["rm_number"] == "RM-000123"
    assert p["request_meta"]["encounter_id"] == "99"
    assert p["request_meta"]["return_url"] == "http://sehati.local/back"
    assert p["patient"]["sex"] == "male"                  # L -> male
    assert p["actor"]["role"] == "nurse"                  # Perawat -> nurse
    assert p["measurements"]["height_cm"] == 170.0
    assert set(p["measurements"]["skinfold_mm"]) == {"chest", "abdomen", "thigh"}
    assert p["measurements"]["skinfold_protocol"] == "JP3_MALE"


def test_build_payload_partial_no_antro():
    svc = AntroReportService()
    p = svc.build_payload(pasien=_Pasien(), antro=None, actor_role="Dokter", actor_staf_id=5)
    assert p["measurements"]["height_cm"] is None          # intake parsial
    assert p["measurements"]["skinfold_mm"] == {}
    assert p["request_meta"]["encounter_id"] == "7"        # fallback id_pasien
