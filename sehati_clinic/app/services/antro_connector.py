"""Konektor AI Antropometri sisi Sehati (lapisan network) — AN-L1b.

Probe `/health` + kirim `/intake` (Bearer A). Pakai urllib (stdlib) → tanpa
dependensi baru. Payload dibangun oleh antro_connector_core (pure/testable).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from app.config import settings
from app.services import antro_connector_core as core

SCHEMA_VERSION = core.SCHEMA_VERSION


class AntroConnectorError(Exception):
    """Kegagalan komunikasi/otorisasi ke modul antropometri."""


def is_enabled() -> bool:
    """True bila base_url + token A sudah dikonfigurasi (konektor aktif)."""
    return bool(settings.antro_base_url and settings.antro_intake_token)


def _url(path: str) -> str:
    return settings.antro_base_url.rstrip("/") + path


def health(timeout: float = 5.0) -> dict:
    req = urllib.request.Request(_url("/health"), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (LAN, config-driven)
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:  # noqa: PERF203
        raise AntroConnectorError(f"health HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise AntroConnectorError(f"health gagal: {e.reason}") from e


def intake(payload: dict, timeout: float = 15.0) -> dict:
    """POST payload ke modul /intake dengan Bearer A. Balas {assessment_id, url, status}."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _url("/intake"), data=data, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.antro_intake_token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise AntroConnectorError(f"intake HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise AntroConnectorError(f"intake gagal: {e.reason}") from e


def _get_json(path: str, timeout: float) -> dict:
    req = urllib.request.Request(
        _url(path), method="GET",
        headers={"Authorization": f"Bearer {settings.antro_intake_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise AntroConnectorError(f"{path} HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise AntroConnectorError(f"{path} gagal: {e.reason}") from e


def status(assessment_id: str, timeout: float = 5.0) -> dict:
    """PULL status 1 laporan: {assessment_id, status, source, updated_at, view_url}."""
    return _get_json(f"/status/{urllib.parse.quote(str(assessment_id))}", timeout)


def reports(rm: str | None = None, timeout: float = 5.0) -> dict:
    """PULL daftar laporan (papan laporan). Filter rm bila diberikan."""
    path = "/reports"
    if rm:
        path += "?rm=" + urllib.parse.quote(str(rm))
    return _get_json(path, timeout)


def regenerate(assessment_id: str, timeout: float = 15.0) -> dict:
    """Minta modul buat ulang laporan (re-send) — untuk status FAILED."""
    req = urllib.request.Request(
        _url(f"/regenerate/{urllib.parse.quote(str(assessment_id))}"), data=b"", method="POST",
        headers={"Authorization": f"Bearer {settings.antro_intake_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise AntroConnectorError(f"regenerate HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise AntroConnectorError(f"regenerate gagal: {e.reason}") from e


# build_intake_payload di-reekspor untuk kenyamanan pemakai.
build_intake_payload = core.build_intake_payload
