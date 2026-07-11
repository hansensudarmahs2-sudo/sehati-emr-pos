"""AN-L2c: uji helper display AntroReportService.laporan_by_rm.

Fokus: bucket approved/pending/failed, pilih latest, dan DEGRADE ANGGUN
(konektor gagal/nonaktif -> dict aman, tak melempar) sehingga halaman Sehati
tetap ter-render. Jalankan di venv Sehati: pytest tests/test_antro_laporan_display.py
"""
import app.services.antro_connector as conn
from app.services.antro_report_service import AntroReportService


def _rows():
    return {"count": 4, "reports": [
        {"assessment_id": "a1", "status": "approved", "name": "RM-1", "date": "2026-07-01",
         "updated_at": "2026-07-01T10:00", "view_url": "http://m/review/a1"},
        {"assessment_id": "a2", "status": "waiting_approval", "name": "RM-1", "date": "2026-07-05",
         "updated_at": "2026-07-05T09:00", "view_url": "http://m/review/a2"},
        {"assessment_id": "a3", "status": "processed", "name": "RM-1", "date": "2026-07-04",
         "updated_at": "2026-07-04T09:00", "view_url": "http://m/review/a3"},
        {"assessment_id": "a4", "status": "failed", "name": "RM-1", "date": "2026-07-03",
         "updated_at": "2026-07-03T09:00", "view_url": "http://m/review/a4"},
    ]}


def test_buckets_dan_latest(monkeypatch):
    monkeypatch.setattr(conn, "is_enabled", lambda: True)
    monkeypatch.setattr(conn, "reports", lambda rm=None, timeout=3.0: _rows())
    info = AntroReportService().laporan_by_rm("RM-1")
    assert info["enabled"] and info["available"] and info["error"] is None
    assert [r["assessment_id"] for r in info["approved"]] == ["a1"]
    assert {r["assessment_id"] for r in info["pending"]} == {"a2"}          # HANYA waiting_approval
    assert {r["assessment_id"] for r in info["processing"]} == {"a3"}       # HANYA processed (sedang diproses)
    assert [r["assessment_id"] for r in info["failed"]] == ["a4"]
    assert info["latest"]["assessment_id"] == "a2"  # updated_at terbaru


def test_nonaktif_aman(monkeypatch):
    monkeypatch.setattr(conn, "is_enabled", lambda: False)
    info = AntroReportService().laporan_by_rm("RM-1")
    assert info["enabled"] is False
    assert info["available"] is False
    assert info["reports"] == [] and info["latest"] is None


def test_konektor_gagal_degrade(monkeypatch):
    monkeypatch.setattr(conn, "is_enabled", lambda: True)
    def _boom(rm=None, timeout=3.0):
        raise conn.AntroConnectorError("connection refused")
    monkeypatch.setattr(conn, "reports", _boom)
    info = AntroReportService().laporan_by_rm("RM-1")   # TIDAK boleh melempar
    assert info["available"] is False
    assert info["error"] and "refused" in info["error"]
    assert info["approved"] == [] and info["pending"] == []


def test_rm_kosong(monkeypatch):
    monkeypatch.setattr(conn, "is_enabled", lambda: True)
    info = AntroReportService().laporan_by_rm(None)
    assert info["available"] is False and info["reports"] == []
