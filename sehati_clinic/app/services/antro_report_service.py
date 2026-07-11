"""AN-L2: layanan Sehati → modul Antropometri.

DISIPLIN: hanya OUTBOUND (fire-and-forget intake) + PULL (status/daftar). NOL endpoint tulis-masuk
di Sehati. Sehati TIDAK menyimpan metrik/laporan — modul yang pegang; Sehati menampilkan via pull.
Konektor gagal → caller tangani anggun ("modul tak tersedia").
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.services import antro_connector as conn
from app.services._clinical_calc import hitung_usia
from app.services.antro_connector_core import build_intake_payload, skinfold_named

_WIB = ZoneInfo("Asia/Jakarta")


def _jk(pasien) -> str:
    v = getattr(pasien, "jenis_kelamin", None)
    return getattr(v, "value", v) or "L"


class AntroReportService:
    def __init__(self, db=None):
        self.db = db

    @staticmethod
    def enabled() -> bool:
        """True bila konektor antropo dikonfigurasi (base_url + token)."""
        return conn.is_enabled()

    def build_payload(self, *, pasien, antro, actor_role, actor_staf_id,
                      actor_name=None, return_url=None, idempotency_key=None) -> dict:
        """Rakit sehati_antro_input dari domain Sehati (identitas display + ukuran + de-id).
        antro boleh None (intake parsial — modul yang mengisi ukuran)."""
        jk = _jk(pasien)
        skin = {}
        if antro is not None:
            skin = skinfold_named(jk, antro.skinfold_titik_1, antro.skinfold_titik_2, antro.skinfold_titik_3)
        return build_intake_payload(
            rm_number=pasien.no_rm,
            encounter_id=(antro.id_kunjungan if antro is not None else pasien.id_pasien),
            assessed_at=datetime.now(_WIB).isoformat(),
            actor_role=actor_role, actor_staf_id=actor_staf_id, actor_name=actor_name,
            jenis_kelamin=jk, age=hitung_usia(pasien.tgl_lahir) or 0,
            dob=(pasien.tgl_lahir.isoformat() if getattr(pasien, "tgl_lahir", None) else None),
            height_cm=(antro.tinggi_badan if antro is not None else None),
            weight_kg=(antro.berat_badan if antro is not None else None),
            waist_cm=(antro.lingkar_perut if antro is not None else None),
            skinfold_mm=skin,
            return_url=return_url,
            idempotency_key=idempotency_key,
        )

    # --- OUTBOUND (fire-and-forget) ---
    def kirim(self, payload: dict) -> dict:
        """POST /intake → {assessment_id, url}. Modul memproses di latar; Sehati buka url."""
        return conn.intake(payload)

    # --- PULL (baca-saja) ---
    def daftar(self, rm: str | None = None) -> dict:
        return conn.reports(rm=rm)

    def status(self, assessment_id: str) -> dict:
        return conn.status(assessment_id)

    def resend(self, assessment_id: str) -> dict:
        return conn.regenerate(assessment_id)

    # --- DISPLAY helper (untuk UI Sehati) — SELALU balas dict aman, tak melempar ---
    def laporan_by_rm(self, rm: str | None) -> dict:
        """Rangkum laporan modul untuk 1 pasien (by no_rm).

        Dipanggil saat render halaman pasien. Bila konektor nonaktif / modul mati /
        gagal -> balas dict dengan available=False + error, sehingga halaman Sehati
        tetap ter-render (degrade anggun, NOL ketergantungan pada modul).
        """
        info = {
            "enabled": self.enabled(), "available": False, "error": None,
            "reports": [], "approved": [], "pending": [], "processing": [], "failed": [], "latest": None,
        }
        if not info["enabled"] or not rm:
            return info
        try:
            res = conn.reports(rm=rm, timeout=3.0)  # display: degrade cepat bila modul lambat/mati
        except Exception as exc:  # noqa: BLE001 - konektor gagal = degrade
            info["error"] = str(exc)
            return info
        rows = res.get("reports") or []
        info["available"] = True
        info["reports"] = rows
        info["approved"] = [r for r in rows if r.get("status") == "approved"]
        info["pending"] = [r for r in rows if r.get("status") == "waiting_approval"]
        info["processing"] = [r for r in rows if r.get("status") == "processed"]
        info["failed"] = [r for r in rows if r.get("status") == "failed"]
        if rows:
            info["latest"] = max(rows, key=lambda r: (r.get("updated_at") or r.get("date") or ""))
        return info
