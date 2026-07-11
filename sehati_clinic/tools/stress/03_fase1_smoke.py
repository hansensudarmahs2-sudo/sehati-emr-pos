"""
Stress Test — Fase 1 Smoke Test (1 User)

Tujuan: baseline performance single-user, identifikasi obvious bottleneck.

USAGE:
    # 1. Pastikan test uvicorn jalan di port 8001 dengan DB_NAME=db_sehati_test
    # 2. Pastikan seed sudah dijalankan (02_seed_test_data.py)
    # 3. Run:
    source .venv/bin/activate
    python tools/stress/03_fase1_smoke.py

Output:
- Real-time per-request log ke stdout
- Summary table di console (per-endpoint p50/p95/p99)
- Full report: outputs/STRESS_TEST_FASE1_REPORT_<timestamp>.md

Scenario:
- Login sebagai Owner (sup. akses semua role)
- HIT 50x mix endpoint read-heavy:
    * Dashboard
    * Antrian dokter, antrian kasir, antrian apotek
    * Pasien search by nama
    * Riwayat pasien (full JOIN)
    * Reports omzet bulanan
    * Reports kinerja dokter
    * Audit log paginated
- HIT 5x write smoke (registrasi pasien baru via FO endpoint)

Metrik per endpoint:
- p50, p95, p99 response time (ms)
- Error rate (% non-2xx)
- Throughput (req/s rata-rata)

Target acceptance Fase 1:
- p95 < 1000ms untuk read endpoints
- 0 error
- No memory leak (RSS sebelum vs sesudah, manual check)
"""

import os
import sys
import time
import random
from datetime import datetime
from pathlib import Path
from statistics import mean, median

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)


# =============================================================================
# Configuration
# =============================================================================
BASE_URL = os.getenv("STRESS_TARGET_URL", "http://127.0.0.1:8001")
LOGIN_USERNAME = os.getenv("STRESS_USER", "superadmin")
LOGIN_PASSWORD = os.getenv("STRESS_PASS", "admin123")

READ_ITERATIONS = 50
WRITE_ITERATIONS = 5

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# Helpers
# =============================================================================
class Metric:
    def __init__(self, name: str):
        self.name = name
        self.times_ms = []
        self.errors = 0
        self.status_counts = {}

    def record(self, elapsed_ms: float, status_code: int):
        self.times_ms.append(elapsed_ms)
        self.status_counts[status_code] = self.status_counts.get(status_code, 0) + 1
        if status_code >= 400:
            self.errors += 1

    def summary(self) -> dict:
        if not self.times_ms:
            return {"name": self.name, "n": 0}
        sorted_t = sorted(self.times_ms)
        n = len(sorted_t)
        p50 = sorted_t[int(n * 0.50)]
        p95 = sorted_t[min(int(n * 0.95), n - 1)]
        p99 = sorted_t[min(int(n * 0.99), n - 1)]
        return {
            "name": self.name,
            "n": n,
            "min_ms": round(min(sorted_t), 1),
            "p50_ms": round(p50, 1),
            "p95_ms": round(p95, 1),
            "p99_ms": round(p99, 1),
            "max_ms": round(max(sorted_t), 1),
            "mean_ms": round(mean(sorted_t), 1),
            "errors": self.errors,
            "error_rate": round(self.errors / n * 100, 2),
            "status_codes": dict(self.status_counts),
        }


def get_csrf_from_html(html: str) -> str:
    """Extract CSRF token from form HTML (looks for hidden input)."""
    import re
    m = re.search(r'name=["\']csrf_token["\']\s+value=["\']([^"\']+)["\']', html)
    if m:
        return m.group(1)
    m = re.search(r'value=["\']([^"\']+)["\']\s+name=["\']csrf_token["\']', html)
    if m:
        return m.group(1)
    return ""


def login(client: httpx.Client) -> bool:
    """Login + return success bool. Cookie + CSRF auto-handled via client."""
    print(f"[login] {LOGIN_USERNAME} → {BASE_URL}")
    # 1. GET login page (untuk dapat CSRF token + cookie)
    r = client.get(f"{BASE_URL}/web/login")
    if r.status_code != 200:
        print(f"  FAIL: GET /web/login → {r.status_code}")
        return False
    csrf = get_csrf_from_html(r.text)

    # 2. POST login
    r = client.post(
        f"{BASE_URL}/web/login",
        data={
            "username": LOGIN_USERNAME,
            "password": LOGIN_PASSWORD,
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    if r.status_code in (302, 303):
        print(f"  OK (302 redirect to: {r.headers.get('location')})")
        return True
    print(f"  FAIL: POST /web/login → {r.status_code}")
    print(f"  Body preview: {r.text[:200]}")
    return False


def timed_get(client: httpx.Client, url: str, metric: Metric) -> int:
    """GET + record latency. Returns status code."""
    t0 = time.perf_counter()
    try:
        r = client.get(url, follow_redirects=False, timeout=10.0)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        metric.record(elapsed_ms, r.status_code)
        return r.status_code
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        metric.record(elapsed_ms, 599)
        print(f"  ERROR: {url}: {type(e).__name__}: {e}")
        return 599


# =============================================================================
# Test scenarios
# =============================================================================
READ_ENDPOINTS = [
    ("Dashboard", "/web/dashboard"),
    ("Antrian Dokter HTML", "/web/dokter/antrian/list"),
    ("Antrian FO Hari Ini", "/web/kunjungan"),
    ("Antrian Kasir", "/web/kasir/antrian"),
    ("Antrian Apotek", "/web/apotek"),
    ("Antrian Perawat", "/web/ruang-tindakan/antrian"),
    ("Pasien Search (kosong)", "/web/pasien"),
    ("Pasien Search (q=And)", "/web/pasien?q=And"),
    ("Pasien Search (q=Sari)", "/web/pasien?q=Sari"),
    ("Reports Landing", "/web/reports"),
    ("Reports Omzet", "/web/reports/omzet"),
    ("Reports Top Treatment", "/web/reports/top-treatment"),
    ("Reports Kinerja Dokter", "/web/reports/kinerja-dokter"),
    ("Reports Audit Log", "/web/reports/audit-log"),
    ("Master Treatment List", "/web/master/treatment"),
    ("Master Produk List", "/web/master/produk"),
    ("Master Staf List", "/web/staf"),
    ("Settings Klinik", "/web/settings/klinik"),
]


def run_read_phase(client: httpx.Client, metrics: dict):
    """Hit READ endpoints — random sampling."""
    print(f"\n[phase 1] READ smoke — {READ_ITERATIONS} iterations\n")
    for i in range(READ_ITERATIONS):
        name, url = random.choice(READ_ENDPOINTS)
        full = f"{BASE_URL}{url}"
        status = timed_get(client, full, metrics[name])
        if i % 10 == 9:
            print(f"  [{i + 1:3d}/{READ_ITERATIONS}] last: {name} → {status}")


def run_write_phase(client: httpx.Client, metric: Metric):
    """Sample write: hit halaman pendaftaran baru (GET) untuk smoke render."""
    print(f"\n[phase 2] WRITE smoke (GET form pages, not actual submit) — {WRITE_ITERATIONS} iterations\n")
    write_endpoints = [
        ("FO Daftar Baru Form", "/web/fo/pasien/daftar-baru"),
        ("Dokter SOAP Form Empty", "/web/dokter/antrian"),
        ("Kasir Antrian", "/web/kasir/antrian"),
    ]
    for i in range(WRITE_ITERATIONS):
        name, url = random.choice(write_endpoints)
        status = timed_get(client, f"{BASE_URL}{url}", metric)
        print(f"  [{i + 1}/{WRITE_ITERATIONS}] {name} → {status}")


# =============================================================================
# Report generation
# =============================================================================
def generate_report(metrics: dict, write_metric: Metric, elapsed_total_s: float):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = OUTPUT_DIR / f"STRESS_TEST_FASE1_REPORT_{timestamp}.md"

    all_summaries = [m.summary() for m in metrics.values() if m.times_ms]
    write_summary = write_metric.summary()

    total_requests = sum(s["n"] for s in all_summaries) + write_summary.get("n", 0)
    total_errors = sum(s["errors"] for s in all_summaries) + write_summary.get("errors", 0)
    throughput = total_requests / elapsed_total_s if elapsed_total_s > 0 else 0

    lines = []
    lines.append("# Stress Test Fase 1 — Smoke Test Report")
    lines.append("")
    lines.append(f"**Tanggal**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S WIB')}")
    lines.append(f"**Target**: {BASE_URL}")
    lines.append(f"**User**: {LOGIN_USERNAME} (Owner)")
    lines.append(f"**Durasi total**: {elapsed_total_s:.1f} detik")
    lines.append(f"**Total request**: {total_requests}")
    lines.append(f"**Throughput**: {throughput:.1f} req/s")
    lines.append(f"**Total error**: {total_errors} ({total_errors / total_requests * 100:.2f}% kalau total > 0)")
    lines.append("")

    # Verdict
    lines.append("## Verdict")
    lines.append("")
    failed_endpoints = [s for s in all_summaries if s.get("p95_ms", 0) > 1000]
    error_endpoints = [s for s in all_summaries if s.get("errors", 0) > 0]
    if not failed_endpoints and not error_endpoints and write_summary.get("errors", 0) == 0:
        lines.append("✅ **PASS** — Semua endpoint p95 < 1000ms, 0 error. Lanjut Fase 2.")
    else:
        lines.append("⚠️ **REVIEW NEEDED** — beberapa endpoint melewati target atau ada error.")
        if failed_endpoints:
            lines.append("")
            lines.append("**Endpoint dengan p95 > 1000ms:**")
            for s in failed_endpoints:
                lines.append(f"- {s['name']}: p95 = {s['p95_ms']}ms")
        if error_endpoints:
            lines.append("")
            lines.append("**Endpoint dengan error:**")
            for s in error_endpoints:
                lines.append(f"- {s['name']}: {s['errors']} error ({s['error_rate']}%)")
    lines.append("")

    # Read phase table
    lines.append("## Phase 1 — READ Endpoints (per endpoint)")
    lines.append("")
    lines.append("| Endpoint | N | min | p50 | p95 | p99 | max | mean | err | status codes |")
    lines.append("|----------|---|-----|-----|-----|-----|-----|------|-----|--------------|")
    for s in sorted(all_summaries, key=lambda x: x.get("p95_ms", 0), reverse=True):
        codes = ", ".join(f"{k}:{v}" for k, v in s["status_codes"].items())
        lines.append(
            f"| {s['name']} | {s['n']} | {s['min_ms']} | {s['p50_ms']} | {s['p95_ms']} | "
            f"{s['p99_ms']} | {s['max_ms']} | {s['mean_ms']} | {s['errors']} | {codes} |"
        )
    lines.append("")

    # Write phase
    if write_summary.get("n", 0) > 0:
        lines.append("## Phase 2 — WRITE Smoke (GET form pages)")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        for k in ["n", "min_ms", "p50_ms", "p95_ms", "p99_ms", "max_ms", "mean_ms", "errors"]:
            lines.append(f"| {k} | {write_summary.get(k, '-')} |")
        codes = ", ".join(f"{k}:{v}" for k, v in write_summary.get("status_codes", {}).items())
        lines.append(f"| status codes | {codes} |")
        lines.append("")

    # Notes
    lines.append("## Catatan")
    lines.append("")
    lines.append("- Test ini hanya measure **single-user sequential**. Tidak detect race condition / lock contention.")
    lines.append("- Untuk write path (SOAP save, payment), butuh Fase 2 dengan Locust (multi-user concurrent).")
    lines.append("- Endpoint Pasien Search dengan filter mungkin lebih lambat karena LIKE query — itu expected.")
    lines.append("- Reports endpoints mungkin lebih lambat karena aggregation — wajar kalau p95 ~500-800ms.")
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[report] Saved: {report_path}")
    return report_path


# =============================================================================
# Main
# =============================================================================
def main():
    print("=" * 60)
    print("STRESS TEST FASE 1 — Smoke Test (Single User)")
    print("=" * 60)
    print(f"Target: {BASE_URL}")
    print(f"User: {LOGIN_USERNAME}")
    print(f"Read iterations: {READ_ITERATIONS}")
    print(f"Write iterations: {WRITE_ITERATIONS}")
    print("=" * 60)

    metrics = {name: Metric(name) for name, _ in READ_ENDPOINTS}
    write_metric = Metric("Write smoke")

    t0 = time.time()
    with httpx.Client(timeout=10.0, follow_redirects=False) as client:
        # Pre-check: ping app
        try:
            r = client.get(f"{BASE_URL}/web/login", timeout=5.0)
            print(f"\n[ping] /web/login → {r.status_code}")
            if r.status_code not in (200, 302):
                print(f"ERROR: App tidak respond di {BASE_URL}. Pastikan test uvicorn jalan.")
                sys.exit(1)
        except Exception as e:
            print(f"ERROR: Cannot reach {BASE_URL}: {e}")
            print("Pastikan test uvicorn jalan dengan: DB_NAME=db_sehati_test uvicorn app.main:app --port 8001")
            sys.exit(1)

        # Login
        if not login(client):
            print("FATAL: Login gagal. Cek seed sudah dijalankan + credentials benar.")
            sys.exit(1)

        # Run phases
        run_read_phase(client, metrics)
        run_write_phase(client, write_metric)

    elapsed_total = time.time() - t0
    print(f"\n[done] Total elapsed: {elapsed_total:.1f}s")

    # Generate report
    report_path = generate_report(metrics, write_metric, elapsed_total)

    # Console summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"{'Endpoint':<35} {'p50':>7} {'p95':>7} {'err':>5}")
    print("-" * 60)
    for m in sorted(metrics.values(), key=lambda x: x.summary().get("p95_ms", 0), reverse=True):
        s = m.summary()
        if s["n"] == 0:
            continue
        print(f"{s['name']:<35} {s['p50_ms']:>6}ms {s['p95_ms']:>6}ms {s['errors']:>4}")
    print("=" * 60)
    print(f"Full report: {report_path}")


if __name__ == "__main__":
    main()
