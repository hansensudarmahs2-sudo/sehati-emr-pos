#!/usr/bin/env python3
"""
Master Health Check Runner — Sehati Clinic

Jalankan semua check script otomatis, gabung output ke 1 markdown log.

Usage:
    cd /path/to/sehati_clinic
    python ../Project_Memory/HealthCheck/scripts/run_health_check.py

Optional flags:
    --mode weekly|baseline|post-deploy|adhoc  (default: weekly)
    --by "Nama Pengguna"                       (default: ENV USER atau "unknown")
    --no-db                                    (skip DB check, kalau MySQL offline)
"""

import argparse
import io
import os
import subprocess
import sys
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEALTHCHECK_DIR = HERE.parent
LOGS_DIR = HEALTHCHECK_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

PROJECT_ROOT_CANDIDATES = [
    HERE.parents[2] / "sehati_clinic",
    HERE.parents[1] / "sehati_clinic",
    Path.cwd() / "sehati_clinic",
    Path.cwd(),
]
SEHATI_ROOT = next((p for p in PROJECT_ROOT_CANDIDATES if (p / "app" / "config.py").exists()), None)


def parse_findings_count(output: str) -> dict:
    """Parse counter dari output script: 🔴 Critical: **N**, 🟠 High: **N**, dst."""
    import re
    counters = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for sev, label in [("CRITICAL", "Critical"), ("HIGH", "High"), ("MEDIUM", "Medium"), ("LOW", "Low")]:
        m = re.search(rf"{label}:\s*\*\*(\d+)\*\*", output)
        if m:
            counters[sev] = int(m.group(1))
    return counters


def run_script(name: str, path: Path) -> tuple[str, dict, int]:
    """Run a check script, capture stdout, return (output, counters, exit_code)."""
    try:
        result = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True, text=True, timeout=120,
            cwd=str(SEHATI_ROOT) if SEHATI_ROOT else None,
        )
        output = result.stdout
        if result.stderr:
            output += f"\n### ⚠ Stderr\n```\n{result.stderr[:2000]}\n```\n"
        counters = parse_findings_count(output)
        return output, counters, result.returncode
    except subprocess.TimeoutExpired:
        return f"## ⏱ {name}\n\n⚠ Script timeout (>120s).\n", {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}, 2
    except Exception as e:
        return f"## ⚠ {name}\n\n❌ Script gagal: {e}\n", {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}, 2


def find_previous_log() -> Path | None:
    """Find log file paling baru di logs/ untuk trend comparison."""
    logs = sorted([p for p in LOGS_DIR.glob("*.md") if p.is_file()])
    return logs[-1] if logs else None


def parse_log_counters(log_path: Path) -> dict:
    """Extract overall counter dari log lama."""
    if not log_path or not log_path.exists():
        return {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    import re
    src = log_path.read_text(encoding="utf-8", errors="replace")
    counters = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    # Cari section "## Overall Summary" lalu hitung total per severity
    overall = re.search(r"## Overall Summary(.*?)(?=^##|\Z)", src, re.DOTALL | re.MULTILINE)
    if overall:
        text = overall.group(1)
        for sev in counters:
            m = re.search(rf"{sev}.*?\*\*(\d+)\*\*", text)
            if m:
                counters[sev] = int(m.group(1))
    return counters


def trend_arrow(current: int, previous: int) -> str:
    if current < previous:
        return f"↓ improving (was {previous})"
    if current > previous:
        return f"↑ worsening (was {previous})"
    return f"= stable (was {previous})"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="weekly",
                        choices=["weekly", "baseline", "post-deploy", "adhoc"])
    parser.add_argument("--by", default=os.environ.get("USER", "unknown"))
    parser.add_argument("--no-db", action="store_true")
    args = parser.parse_args()

    if SEHATI_ROOT is None:
        print("❌ ERROR: Cannot find sehati_clinic project root. Pastikan dijalankan dari folder yang benar.")
        sys.exit(2)

    started_at = datetime.now()
    print(f"🩺 Sehati Clinic Health Check — {args.mode}")
    print(f"   Started: {started_at:%Y-%m-%d %H:%M:%S}")
    print(f"   Run by:  {args.by}")
    print(f"   Project: {SEHATI_ROOT}")
    print()

    # ----- Run check scripts -----
    scripts = []
    if not args.no_db:
        scripts.append(("DB Integrity", HERE / "db_integrity.py"))
    scripts.append(("Backend Audit Gaps", HERE / "audit_gaps.py"))
    scripts.append(("Security + PII Scan", HERE / "pii_scan.py"))

    all_outputs = []
    overall = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    section_results = []

    for name, path in scripts:
        if not path.exists():
            print(f"   ⚠ Skip {name} — script tidak ada: {path}")
            continue
        print(f"   ▶ Running: {name}...")
        output, counters, rc = run_script(name, path)
        all_outputs.append(output)
        for sev in overall:
            overall[sev] += counters[sev]
        section_results.append({
            "name": name, "counters": counters, "exit_code": rc,
        })

    duration_sec = (datetime.now() - started_at).total_seconds()

    # ----- Trend vs previous run -----
    prev_log = find_previous_log()
    prev_counters = parse_log_counters(prev_log) if prev_log else {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    prev_label = prev_log.name if prev_log else "(baseline — no previous run)"

    # ----- Build log markdown -----
    log_name = f"{started_at:%Y-%m-%d}_{args.mode}.md"
    log_path = LOGS_DIR / log_name

    lines = []
    lines.append(f"# Health Check — {started_at:%Y-%m-%d} ({args.mode})\n")
    lines.append(f"**Run by:** {args.by}")
    lines.append(f"**Started:** {started_at:%Y-%m-%d %H:%M:%S}")
    lines.append(f"**Duration:** {duration_sec:.1f} detik")
    lines.append(f"**Previous run:** {prev_label}")
    lines.append("")

    lines.append("## Overall Summary\n")
    total = sum(overall.values())
    lines.append(f"- Total findings: **{total}**")
    lines.append(f"- 🔴 CRITICAL: **{overall['CRITICAL']}**")
    lines.append(f"- 🟠 HIGH: **{overall['HIGH']}**")
    lines.append(f"- 🟡 MEDIUM: **{overall['MEDIUM']}**")
    lines.append(f"- 🟢 LOW: **{overall['LOW']}**")
    lines.append("")

    lines.append("### Per Section\n")
    lines.append("| Section | CRITICAL | HIGH | MEDIUM | LOW | Exit |")
    lines.append("|---------|----------|------|--------|-----|------|")
    for s in section_results:
        c = s["counters"]
        lines.append(f"| {s['name']} | {c['CRITICAL']} | {c['HIGH']} | {c['MEDIUM']} | {c['LOW']} | {s['exit_code']} |")
    lines.append("")

    lines.append("## Trend (vs previous run)\n")
    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        lines.append(f"- {sev}: **{overall[sev]}** {trend_arrow(overall[sev], prev_counters[sev])}")
    lines.append("")

    lines.append("## Action Items\n")
    if overall["CRITICAL"] > 0:
        lines.append("- [ ] 🔴 **CRITICAL** — Investigate & patch dalam 24 jam, masukkan ke `07_known_issues.md`")
    if overall["HIGH"] > 0:
        lines.append("- [ ] 🟠 **HIGH** — Plan fix sprint ini (≤ 7 hari)")
    if overall["MEDIUM"] > 0:
        lines.append("- [ ] 🟡 **MEDIUM** — Plan fix sprint berikutnya")
    if total == 0:
        lines.append("- ✅ Tidak ada action item — semua check lulus.")
    lines.append("")

    lines.append("---\n")
    lines.append("# Detail per Section\n")
    lines.extend(all_outputs)

    lines.append("\n---\n")
    lines.append(f"_Log generated by `run_health_check.py` pada {started_at:%Y-%m-%d %H:%M:%S}_")

    log_path.write_text("\n".join(lines), encoding="utf-8")

    # ----- Print summary to stdout -----
    print()
    print(f"📝 Log saved: {log_path.relative_to(HEALTHCHECK_DIR.parent)}")
    print()
    print("Ringkasan:")
    print(f"  🔴 CRITICAL: {overall['CRITICAL']}")
    print(f"  🟠 HIGH:     {overall['HIGH']}")
    print(f"  🟡 MEDIUM:   {overall['MEDIUM']}")
    print(f"  🟢 LOW:      {overall['LOW']}")
    print()
    if overall["CRITICAL"]:
        print("⚠  ADA CRITICAL FINDINGS — review log segera!")
        sys.exit(1)
    elif overall["HIGH"]:
        print("⚠  Ada HIGH findings — plan fix sprint ini.")
        sys.exit(1)
    else:
        print("✅ Health Check lulus.")


if __name__ == "__main__":
    main()
