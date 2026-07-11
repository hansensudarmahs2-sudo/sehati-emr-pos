"""
Stress Test — Fase 2 Concurrent Ringan (3 User via Locust)

Tujuan: validasi tidak ada race condition di workflow normal.

USAGE:
    # 1. Pastikan test uvicorn jalan di port 8001 dengan DB_NAME=db_sehati_test
    # 2. Pastikan seed sudah dijalankan (02_seed_test_data.py)
    # 3. Install Locust kalau belum:
    pip install locust

    # 4. Quick smoke (1 menit, untuk verify script jalan):
    locust -f tools/stress/04_fase2_locust.py \\
        --host http://127.0.0.1:8001 \\
        --users 3 --spawn-rate 1 \\
        --run-time 1m --headless \\
        --csv outputs/stress_fase2_quick \\
        --html outputs/stress_fase2_quick.html

    # 5. Full run (30 menit, per roadmap):
    locust -f tools/stress/04_fase2_locust.py \\
        --host http://127.0.0.1:8001 \\
        --users 3 --spawn-rate 1 \\
        --run-time 30m --headless \\
        --csv outputs/stress_fase2_full \\
        --html outputs/stress_fase2_full.html

User profiles (per roadmap):
- 1 FO  — daftar pasien tiap 30 detik
- 1 Dokter — cek antrian + pasien detail tiap 60 detik
- 1 Kasir — cek antrian + view tagihan tiap 90 detik

Wait times di-randomize ±20% untuk simulasi realistic.

Khusus diuji:
- Race condition nomor antrian (FO concurrent submit)
- Status transition consistency (cross-role)
- Database lock contention

Target Fase 2:
- 0 deadlock
- 0 duplicate nomor antrean (verify via SQL post-test)
- p95 < 1500ms semua endpoint (lebih longgar dari Fase 1 karena concurrent)
- Error rate < 1%
"""

import os
import random
import re
import time
from typing import Optional

from locust import HttpUser, task, between, events


# =============================================================================
# Konfigurasi
# =============================================================================
LOGIN_FO = ("fo_test", "fo123")
LOGIN_DOKTER = ("dokter_a", "dokter123")
LOGIN_KASIR = ("kasir_test", "kasir123")

# Speed mode — bisa di-override via env STRESS_SPEED:
#   fast    = wait 3-6s per user (untuk smoke 1-2 menit)
#   normal  = wait 24-108s per user (per roadmap, untuk 30m run real)
SPEED_MODE = os.getenv("STRESS_SPEED", "fast").lower()
if SPEED_MODE == "normal":
    FO_WAIT = (24, 36)         # 30s ±20%
    DOKTER_WAIT = (48, 72)     # 60s ±20%
    KASIR_WAIT = (72, 108)     # 90s ±20%
else:
    FO_WAIT = (3, 6)
    DOKTER_WAIT = (4, 8)
    KASIR_WAIT = (6, 10)

# Stats globals untuk custom assertion
_REGISTRATION_COUNTER = 0
_REGISTRATION_LOCK_ERRORS = 0


# =============================================================================
# Helpers
# =============================================================================
def get_csrf_from_html(html: str) -> str:
    """Extract CSRF token from form HTML (cek 2 urutan attr)."""
    m = re.search(r'name=["\']csrf_token["\']\s+value=["\']([^"\']+)["\']', html)
    if m:
        return m.group(1)
    m = re.search(r'value=["\']([^"\']+)["\']\s+name=["\']csrf_token["\']', html)
    if m:
        return m.group(1)
    return ""


def login_user(client, username: str, password: str) -> bool:
    """Login + populate session cookie. Returns True kalau sukses."""
    r = client.get("/web/login", name="GET /web/login")
    if r.status_code != 200:
        return False
    csrf = get_csrf_from_html(r.text)
    r = client.post(
        "/web/login",
        data={"username": username, "password": password, "csrf_token": csrf},
        allow_redirects=False,
        name="POST /web/login",
    )
    return r.status_code in (302, 303)


# Random Indonesian-ish nama untuk FO registrasi
NAMA_DEPAN_M = ["Adi", "Budi", "Cahyo", "Doni", "Eka", "Fadli", "Gani", "Heru"]
NAMA_DEPAN_F = ["Ani", "Beta", "Cinta", "Dini", "Eva", "Fitri", "Gita", "Hani"]
NAMA_BELAKANG = ["Pratama", "Wijaya", "Santoso", "Hartono", "Susilo", "Wibowo"]


def random_pasien_payload(prefix: str = "STRESS") -> dict:
    """Generate payload pendaftaran pasien dengan minimal field."""
    is_male = random.random() < 0.5
    nama_depan = random.choice(NAMA_DEPAN_M if is_male else NAMA_DEPAN_F)
    nama_belakang = random.choice(NAMA_BELAKANG)
    # Unique nama via timestamp+rand → hindari collision di concurrent run
    suffix = f"{int(time.time() * 1000) % 1000000:06d}"
    nama = f"{prefix} {nama_depan} {nama_belakang} {suffix}"
    return {
        "nama": nama,
        "jenis_kelamin": "L" if is_male else "P",
        "tgl_lahir": "1990-01-15",
        "tipe_membership": "REGULAR",
        "status_verifikasi": "VERIFIED",
        # No alergi, no penyakit kronis — minimal payload
    }


# =============================================================================
# User Classes
# =============================================================================
class FOUser(HttpUser):
    """FO — daftar pasien tiap interval (config via STRESS_SPEED env)."""

    wait_time = between(*FO_WAIT)
    weight = 1  # 1 instance

    def on_start(self):
        if not login_user(self.client, *LOGIN_FO):
            self.environment.runner.quit()
            raise Exception("FO login failed")

    @task(3)
    def daftar_pasien_baru(self):
        """POST registrasi pasien baru — write path utama untuk uji race."""
        global _REGISTRATION_COUNTER, _REGISTRATION_LOCK_ERRORS
        # Get fresh CSRF
        r = self.client.get("/web/pendaftaran-pasien", name="GET /pendaftaran-pasien")
        if r.status_code != 200:
            return
        csrf = get_csrf_from_html(r.text)
        payload = random_pasien_payload("FO")
        payload["csrf_token"] = csrf

        with self.client.post(
            "/web/pendaftaran-pasien",
            data=payload,
            allow_redirects=False,
            name="POST /pendaftaran-pasien",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 302, 303):
                _REGISTRATION_COUNTER += 1
                r.success()
            else:
                _REGISTRATION_LOCK_ERRORS += 1
                r.failure(f"FO daftar gagal: {r.status_code} — {r.text[:100]}")

    @task(2)
    def lihat_antrian_hari_ini(self):
        self.client.get("/web/kunjungan", name="GET /kunjungan")

    @task(1)
    def cari_pasien(self):
        q = random.choice(["And", "Sari", "Dewi", "Pratama", ""])
        url = "/web/pasien" + (f"?q={q}" if q else "")
        self.client.get(url, name="GET /pasien?q=*")


class DokterUser(HttpUser):
    """Dokter — cek antrian + detail tiap interval (config via STRESS_SPEED env)."""

    wait_time = between(*DOKTER_WAIT)
    weight = 1

    def on_start(self):
        if not login_user(self.client, *LOGIN_DOKTER):
            self.environment.runner.quit()
            raise Exception("Dokter login failed")

    @task(3)
    def cek_antrian(self):
        self.client.get("/web/dokter/antrian", name="GET /dokter/antrian")
        self.client.get("/web/dokter/antrian/list", name="GET /dokter/antrian/list")

    @task(2)
    def cari_pasien(self):
        self.client.get("/web/pasien", name="GET /pasien")

    @task(1)
    def dashboard(self):
        self.client.get("/web/dashboard", name="GET /dashboard")


class KasirUser(HttpUser):
    """Kasir — cek antrian + proses bayar tiap interval (config via STRESS_SPEED env)."""

    wait_time = between(*KASIR_WAIT)
    weight = 1

    def on_start(self):
        if not login_user(self.client, *LOGIN_KASIR):
            self.environment.runner.quit()
            raise Exception("Kasir login failed")

    @task(3)
    def cek_antrian(self):
        self.client.get("/web/kasir/antrian", name="GET /kasir/antrian")
        self.client.get("/web/kasir/antrian/list", name="GET /kasir/antrian/list")

    @task(1)
    def dashboard(self):
        self.client.get("/web/dashboard", name="GET /dashboard")


# =============================================================================
# Custom event handlers — output post-test summary
# =============================================================================
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("=" * 70)
    print("STRESS TEST FASE 2 — Concurrent Ringan (3 User)")
    print("=" * 70)
    print(f"Target: {environment.host}")
    print(f"User classes: FOUser(1) + DokterUser(1) + KasirUser(1)")
    print(f"Speed mode: {SPEED_MODE.upper()}")
    print(f"Wait times: FO {FO_WAIT[0]}-{FO_WAIT[1]}s, Dokter {DOKTER_WAIT[0]}-{DOKTER_WAIT[1]}s, Kasir {KASIR_WAIT[0]}-{KASIR_WAIT[1]}s")
    print("=" * 70)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    print("\n" + "=" * 70)
    print("FASE 2 SUMMARY")
    print("=" * 70)
    print(f"FO registrations attempted: {_REGISTRATION_COUNTER + _REGISTRATION_LOCK_ERRORS}")
    print(f"  - Success: {_REGISTRATION_COUNTER}")
    print(f"  - Failed:  {_REGISTRATION_LOCK_ERRORS}")
    if _REGISTRATION_LOCK_ERRORS > 0:
        print("  ⚠️  Ada registrasi gagal — cek log untuk detail.")
        print("     Bisa jadi: lock contention, duplicate constraint, atau bug lain.")
    print()
    print("POST-TEST VERIFICATION (jalankan manual setelah test selesai):")
    print()
    print("# 1. Cek duplicate nomor antrean (HARUSNYA 0 row):")
    print("sudo mysql db_sehati_test -e \"")
    print("  SELECT tgl_kunjungan, nomor_antrean, COUNT(*) as cnt")
    print("  FROM kunjungan")
    print("  GROUP BY tgl_kunjungan, nomor_antrean")
    print("  HAVING cnt > 1;\"")
    print()
    print("# 2. Cek pasien yang ter-create dari stress test:")
    print("sudo mysql db_sehati_test -e \"")
    print("  SELECT COUNT(*) FROM pasien WHERE nama LIKE 'STRESS %' OR nama LIKE 'FO %';\"")
    print()
    print("# 3. Cek audit log untuk anomali:")
    print("sudo mysql db_sehati_test -e \"")
    print("  SELECT aksi, COUNT(*) FROM audit_log")
    print("  WHERE created_at > DATE_SUB(NOW(), INTERVAL 1 HOUR)")
    print("  GROUP BY aksi ORDER BY 2 DESC;\"")
    print("=" * 70)
