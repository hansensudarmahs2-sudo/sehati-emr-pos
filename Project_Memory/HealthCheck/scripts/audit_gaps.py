#!/usr/bin/env python3
"""
Backend Audit Gaps Health Check — Sehati Clinic

Scan code untuk:
- Python AST parse (BE-01)
- db.commit() di router (BE-02)
- Service mutating tanpa AuditService call (BE-03)
- Bare except (BE-04)
- Hardcoded secret (BE-05)
- Import wrong Base path (BE-07)

Jalankan dari root project sehati_clinic:
    cd /path/to/sehati_clinic
    python ../Project_Memory/HealthCheck/scripts/audit_gaps.py
"""

import ast
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


# =============================================================================
# Helpers
# =============================================================================

def iter_py(dir_path: Path):
    return sorted([p for p in dir_path.rglob("*.py") if "__pycache__" not in p.parts])


def read_safe(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


# =============================================================================
# Checks
# =============================================================================

def check_be01_ast() -> list[dict]:
    """BE-01 — All .py harus parse-able."""
    findings = []
    for f in iter_py(APP_DIR):
        src = read_safe(f)
        try:
            ast.parse(src)
        except SyntaxError as e:
            findings.append({
                "code": "BE-01", "severity": "CRITICAL",
                "file": str(f.relative_to(SEHATI_ROOT)),
                "detail": f"SyntaxError line {e.lineno}: {e.msg}",
            })
    return findings


def check_be02_router_commit() -> list[dict]:
    """BE-02 — db.commit() di app/web/routes/ atau app/api/v1/ adalah violation DEC-030."""
    findings = []
    for sub in ["web/routes", "api/v1"]:
        target = APP_DIR / sub
        if not target.exists():
            continue
        for f in iter_py(target):
            src = read_safe(f)
            for i, line in enumerate(src.splitlines(), start=1):
                if re.search(r"\bdb\.commit\s*\(", line):
                    # Skip kalau ada # noqa atau dalam komentar
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    findings.append({
                        "code": "BE-02", "severity": "HIGH",
                        "file": str(f.relative_to(SEHATI_ROOT)),
                        "detail": f"line {i}: `{stripped[:120]}` — router tidak boleh commit (DEC-030)",
                    })
    return findings


def check_be03_audit_coverage() -> list[dict]:
    """BE-03 — Service yang ada keyword mutating tapi tidak panggil AuditService.

    Heuristic kasar: cari method service yang ada `db.add(`, `db.delete(`, atau update statement,
    yang file-nya tidak panggil `AuditService` sama sekali.
    """
    findings = []
    services_dir = APP_DIR / "services"
    if not services_dir.exists():
        return findings

    mutating_re = re.compile(r"db\.(add|delete)\s*\(|\.execute\(\s*update\(|\.execute\(\s*delete\(")
    audit_call_re = re.compile(r"AuditService\s*\(|\.log_action\s*\(")

    for f in iter_py(services_dir):
        if f.name == "audit_service.py":
            continue
        src = read_safe(f)
        has_mutating = bool(mutating_re.search(src))
        has_audit = bool(audit_call_re.search(src))
        if has_mutating and not has_audit:
            findings.append({
                "code": "BE-03", "severity": "HIGH",
                "file": str(f.relative_to(SEHATI_ROOT)),
                "detail": "Service mutating tapi tidak panggil AuditService — audit log gap",
            })
    return findings


def check_be04_bare_except() -> list[dict]:
    """BE-04 — Bare `except:` atau `except Exception: pass`."""
    findings = []
    bare_re = re.compile(r"^\s*except\s*:\s*$|^\s*except\s+Exception\s*:\s*$")
    pass_re = re.compile(r"^\s*pass\s*$")

    for f in iter_py(APP_DIR):
        src = read_safe(f)
        lines = src.splitlines()
        for i, line in enumerate(lines):
            if bare_re.match(line):
                # Cek line berikutnya pass
                if i + 1 < len(lines) and pass_re.match(lines[i + 1]):
                    findings.append({
                        "code": "BE-04", "severity": "MEDIUM",
                        "file": str(f.relative_to(SEHATI_ROOT)),
                        "detail": f"line {i+1}: bare except + pass — silent failure",
                    })
    return findings


def check_be05_hardcoded_secret() -> list[dict]:
    """BE-05 — Hardcoded secret string."""
    findings = []
    # Cari string yang assignment ke variable yang nama-nya mengandung secret/password/key, dengan nilai literal > 10 chars
    pat = re.compile(
        r"(jwt_secret|secret_key|password|api_key)\s*=\s*['\"]([^'\"]{10,})['\"]",
        re.IGNORECASE,
    )
    for f in iter_py(APP_DIR):
        # Skip config.py (memang ambil dari env)
        if f.name in ("config.py", "test_config.py"):
            continue
        src = read_safe(f)
        for i, line in enumerate(src.splitlines(), start=1):
            m = pat.search(line)
            if m:
                # Skip kalau jelas placeholder/example
                val = m.group(2).lower()
                if val in ("changeme", "your_secret_here", "xxxxxx", "placeholder", "example"):
                    continue
                # Skip kalau diambil dari env via os.getenv atau settings
                if "os.getenv" in line or "settings." in line or "getenv" in line:
                    continue
                findings.append({
                    "code": "BE-05", "severity": "CRITICAL",
                    "file": str(f.relative_to(SEHATI_ROOT)),
                    "detail": f"line {i}: hardcoded {m.group(1)} — pindah ke .env",
                })
    return findings


def check_be07_wrong_base_import() -> list[dict]:
    """BE-07 — Import Base dari app.db.session (harusnya app.db.base)."""
    findings = []
    pat = re.compile(r"from\s+app\.db\.session\s+import\s+.*\bBase\b")
    for f in iter_py(APP_DIR):
        src = read_safe(f)
        for i, line in enumerate(src.splitlines(), start=1):
            if pat.search(line):
                findings.append({
                    "code": "BE-07", "severity": "HIGH",
                    "file": str(f.relative_to(SEHATI_ROOT)),
                    "detail": f"line {i}: import Base dari session — harusnya `from app.db.base import Base`",
                })
    return findings


# =============================================================================
# Main
# =============================================================================

def main():
    all_findings = []
    all_findings += check_be01_ast()
    all_findings += check_be02_router_commit()
    all_findings += check_be03_audit_coverage()
    all_findings += check_be04_bare_except()
    all_findings += check_be05_hardcoded_secret()
    all_findings += check_be07_wrong_base_import()

    by_sev = {"CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": []}
    for f in all_findings:
        by_sev[f["severity"]].append(f)

    print("## 🐍 Backend Audit Gaps Check\n")
    print(f"- Total findings: **{len(all_findings)}**")
    print(f"- 🔴 Critical: **{len(by_sev['CRITICAL'])}**")
    print(f"- 🟠 High: **{len(by_sev['HIGH'])}**")
    print(f"- 🟡 Medium: **{len(by_sev['MEDIUM'])}**")
    print(f"- 🟢 Low: **{len(by_sev['LOW'])}**")
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
        print("✅ Backend audit gaps check lulus — tidak ada finding.\n")

    # Exit code: 1 kalau ada CRITICAL atau HIGH
    if by_sev["CRITICAL"] or by_sev["HIGH"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
