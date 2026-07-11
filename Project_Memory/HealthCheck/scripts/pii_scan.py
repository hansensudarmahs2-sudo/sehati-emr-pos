#!/usr/bin/env python3
"""
Security + PII Leak Scan — Sehati Clinic

Scans:
- SEC-01 CSRF token di semua form POST templates
- SEC-02 PII fields di audit_log keterangan (DB query) + di template responses
- SEC-04 Cookie secure config
- SEC-05 JWT secret hardcoded
- SEC-07 Role check ad-hoc (bypass require_X_role helper)

Jalankan dari root project sehati_clinic:
    cd /path/to/sehati_clinic
    python ../Project_Memory/HealthCheck/scripts/pii_scan.py
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT_CANDIDATES = [
    HERE.parents[2] / "sehati_clinic",
    HERE.parents[1] / "sehati_clinic",
    Path.cwd() / "sehati_clinic",
    Path.cwd(),
]
SEHATI_ROOT = next((p for p in PROJECT_ROOT_CANDIDATES if (p / "app" / "config.py").exists()), None)
if SEHATI_ROOT is None:
    print("ERROR: Cannot find sehati_clinic project root.")
    sys.exit(1)

APP_DIR = SEHATI_ROOT / "app"
TEMPLATES_DIR = APP_DIR / "web" / "templates"

# PII field names yang sensitif
PII_FIELDS = ["nomor_ktp", "tanggal_lahir", "tgl_lahir", "alamat", "nomor_hp"]


def iter_files(dir_path: Path, ext: str):
    if not dir_path.exists():
        return []
    return sorted([p for p in dir_path.rglob(f"*.{ext}") if "__pycache__" not in p.parts])


def read_safe(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


# =============================================================================
# Checks
# =============================================================================

def check_sec01_csrf_token() -> list[dict]:
    """SEC-01 — Semua POST form di template harus punya csrf_input."""
    findings = []
    form_re = re.compile(r"<form[^>]+method\s*=\s*['\"]?POST['\"]?[^>]*>", re.IGNORECASE)

    for f in iter_files(TEMPLATES_DIR, "html"):
        src = read_safe(f)
        forms = list(form_re.finditer(src))
        for m in forms:
            # Cek 500 chars setelah <form> apakah ada csrf_input
            window = src[m.end():m.end() + 500]
            if "csrf_input" not in window:
                # Hitung line number
                line_no = src[:m.start()].count("\n") + 1
                findings.append({
                    "code": "SEC-01", "severity": "HIGH",
                    "file": str(f.relative_to(SEHATI_ROOT)),
                    "detail": f"line {line_no}: POST form tanpa csrf_input dalam 500 chars setelah <form>",
                })
    return findings


def check_sec02_pii_in_audit_keterangan() -> list[dict]:
    """SEC-02 — Cari kemungkinan PII masuk ke audit_log.keterangan via code."""
    findings = []
    # Pattern: keterangan=f"...{pasien.nomor_ktp}..." atau keterangan dengan PII field
    keterangan_re = re.compile(r"keterangan\s*=\s*[fF]?['\"]([^'\"]*)['\"]")

    for f in iter_files(APP_DIR / "services", "py"):
        src = read_safe(f)
        for i, line in enumerate(src.splitlines(), start=1):
            m = keterangan_re.search(line)
            if m:
                text = m.group(1).lower()
                for pii in PII_FIELDS:
                    if pii in text:
                        findings.append({
                            "code": "SEC-02", "severity": "CRITICAL",
                            "file": str(f.relative_to(SEHATI_ROOT)),
                            "detail": f"line {i}: audit_log.keterangan kemungkinan berisi `{pii}` — PII leak risk",
                        })
                        break

    # Cek juga f-string yang masukin .nomor_ktp dst di audit
    fstring_pii_re = re.compile(r"keterangan\s*=\s*[fF]['\"][^'\"]*\{[^}]*\.(nomor_ktp|tanggal_lahir|tgl_lahir|alamat|nomor_hp)[^}]*\}")
    for f in iter_files(APP_DIR / "services", "py"):
        src = read_safe(f)
        for i, line in enumerate(src.splitlines(), start=1):
            if fstring_pii_re.search(line):
                findings.append({
                    "code": "SEC-02", "severity": "CRITICAL",
                    "file": str(f.relative_to(SEHATI_ROOT)),
                    "detail": f"line {i}: f-string ke keterangan berisi accessor PII field",
                })

    return findings


def check_sec04_cookie_secure_config() -> list[dict]:
    """SEC-04 — cookie_secure harus terkonfigurasi di config (bukan hardcoded False)."""
    findings = []
    config_py = APP_DIR / "config.py"
    if not config_py.exists():
        return findings
    src = read_safe(config_py)
    # Cari cookie_secure
    if "cookie_secure" not in src:
        findings.append({
            "code": "SEC-04", "severity": "HIGH",
            "file": "app/config.py",
            "detail": "Tidak ada setting `cookie_secure` — production cookie tidak Secure flag",
        })
    return findings


def check_sec05_jwt_hardcoded() -> list[dict]:
    """SEC-05 — JWT secret hardcoded."""
    findings = []
    # Cari "jwt_secret = 'xxx'" yang bukan dari env
    pat = re.compile(r"(jwt_secret|JWT_SECRET)\s*=\s*['\"]([^'\"]{8,})['\"]")
    for f in iter_files(APP_DIR, "py"):
        if f.name in ("config.py",):
            continue  # config boleh ambil dari env via Field
        src = read_safe(f)
        for i, line in enumerate(src.splitlines(), start=1):
            m = pat.search(line)
            if m:
                if "os.getenv" in line or "settings." in line:
                    continue
                findings.append({
                    "code": "SEC-05", "severity": "CRITICAL",
                    "file": str(f.relative_to(SEHATI_ROOT)),
                    "detail": f"line {i}: JWT secret hardcoded — harus dari env via settings",
                })
    return findings


def check_sec07_ad_hoc_role_check() -> list[dict]:
    """SEC-07 — Role check langsung di router (if user.role == 'X') bypass helper."""
    findings = []
    routes_dir = APP_DIR / "web" / "routes"
    if not routes_dir.exists():
        return findings
    # Pattern: if user.role == "X" atau if actor.role == "X"
    pat = re.compile(r"if\s+(?:user|actor|staf)\.role\s*==\s*['\"]?\w+['\"]?")
    for f in iter_files(routes_dir, "py"):
        src = read_safe(f)
        for i, line in enumerate(src.splitlines(), start=1):
            if pat.search(line):
                findings.append({
                    "code": "SEC-07", "severity": "MEDIUM",
                    "file": str(f.relative_to(SEHATI_ROOT)),
                    "detail": f"line {i}: ad-hoc role check — pakai `require_X_role()` helper di _shared.py",
                })
    return findings


# =============================================================================
# Main
# =============================================================================

def main():
    all_findings = []
    all_findings += check_sec01_csrf_token()
    all_findings += check_sec02_pii_in_audit_keterangan()
    all_findings += check_sec04_cookie_secure_config()
    all_findings += check_sec05_jwt_hardcoded()
    all_findings += check_sec07_ad_hoc_role_check()

    by_sev = {"CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": []}
    for f in all_findings:
        by_sev[f["severity"]].append(f)

    print("## 🔒 Security + PII Scan\n")
    print(f"- Total findings: **{len(all_findings)}**")
    print(f"- 🔴 Critical: **{len(by_sev['CRITICAL'])}**")
    print(f"- 🟠 High: **{len(by_sev['HIGH'])}**")
    print(f"- 🟡 Medium: **{len(by_sev['MEDIUM'])}**")
    print()

    for sev, icon in [("CRITICAL", "🔴"), ("HIGH", "🟠"), ("MEDIUM", "🟡"), ("LOW", "🟢")]:
        if not by_sev[sev]:
            continue
        print(f"### {icon} {sev}\n")
        for f in by_sev[sev]:
            print(f"- **[{f['code']}]** `{f['file']}`")
            print(f"  - {f['detail']}")
        print()

    if not all_findings:
        print("✅ Security + PII scan lulus — tidak ada finding.\n")

    if by_sev["CRITICAL"] or by_sev["HIGH"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
