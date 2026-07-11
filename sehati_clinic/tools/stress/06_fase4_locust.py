"""
Stress Test — Fase 4 Stress di Atas Batas (15 User via Locust)

Tujuan: identifikasi bottleneck, baseline maximum capacity production.

USAGE:
    # Quick smoke 2 menit:
    locust -f tools/stress/06_fase4_locust.py \\
        --host http://127.0.0.1:8001 \\
        --users 15 --spawn-rate 2 \\
        --run-time 2m --headless \\
        --csv outputs/stress_fase4_quick \\
        --html outputs/stress_fase4_quick.html

    # Full 30 menit:
    STRESS_SPEED=normal locust -f tools/stress/06_fase4_locust.py \\
        --host http://127.0.0.1:8001 \\
        --users 15 --spawn-rate 1 \\
        --run-time 30m --headless \\
        --csv outputs/stress_fase4_full \\
        --html outputs/stress_fase4_full.html

User profiles (15 total per roadmap + Owner monitor):
- 2 FO       — daftar pasien baru + buat antrian (test atomic counter concurrent)
- 3 Dokter   — dokter_a + dokter_b + dokter_a (3rd reuse): cek antrian scoped
- 4 Perawat  — cek ruang tindakan + cek umum (highest read pressure)
- 3 Kasir    — cek antrian + view tagihan
- 2 Apoteker — cek antrian apotek + suggested order (superadmin login)
- 1 Owner    — monitor dashboard + reports (background watcher)

Test focus:
- 2 FO concurrent buat-antrian → SIMULTAN nomor_antrean race
- 12 read users → DB pool exhaustion test (pool_size=10, max_overflow=20 = cap 30)
- Login burst saat spawn 15 user → bcrypt CPU contention test

Target Fase 4:
- 0 deadlock
- 0 duplicate nomor_antrean
- p95 < 3000ms semua endpoint (relaxed dari Fase 3 karena heavy load)
- Error rate < 5%
- Identify mana endpoint yang DEGRADE paling cepat (= bottleneck candidate)
"""

import os
import random
import re
import time

from locust import HttpUser, task, between, events


# =============================================================================
# Konfigurasi
# =============================================================================
LOGIN_FO = ("fo_test", "fo123")
LOGIN_DOKTER_A = ("dokter_a", "dokter123")
LOGIN_DOKTER_B = ("dokter_b", "dokter123")
LOGIN_PERAWAT = ("perawat_test", "perawat123")
LOGIN_KASIR = ("kasir_test", "kasir123")
LOGIN_APOTEK = ("superadmin", "admin123")  # reuse — seed tidak punya apoteker dedicated
LOGIN_OWNER = ("superadmin", "admin123")

SPEED_MODE = os.getenv("STRESS_SPEED", "fast").lower()
if SPEED_MODE == "normal":
    FO_WAIT = (24, 36)
    DOKTER_WAIT = (48, 72)
    PERAWAT_WAIT = (48, 72)
    KASIR_WAIT = (72, 108)
    APOTEK_WAIT = (60, 90)
    OWNER_WAIT = (90, 120)
else:
    # Fast — lebih agresif dari Fase 3 untuk stress maximum
    FO_WAIT = (2, 5)
    DOKTER_WAIT = (3, 6)
    PERAWAT_WAIT = (3, 6)
    KASIR_WAIT = (4, 7)
    APOTEK_WAIT = (4, 7)
    OWNER_WAIT = (5, 10)

# Counters
_FO_REGISTER_OK = 0
_FO_REGISTER_FAIL = 0
_FO_ANTRIAN_OK = 0
_FO_ANTRIAN_FAIL = 0


# =============================================================================
# Helpers
# =============================================================================
def get_csrf_from_html(html: str) -> str:
    m = re.search(r'name=["\']csrf_token["\']\s+value=["\']([^"\']+)["\']', html)
    if m:
        return m.group(1)
    m = re.search(r'value=["\']([^"\']+)["\']\s+name=["\']csrf_token["\']', html)
    if m:
        return m.group(1)
    return ""


def login_user(client, username: str, password: str) -> bool:
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


NAMA_M = ["Adi", "Budi", "Cahyo", "Doni", "Eka", "Fadli", "Gani", "Heru"]
NAMA_F = ["Ani", "Beta", "Cinta", "Dini", "Eva", "Fitri", "Gita", "Hani"]
NAMA_BELAKANG = ["Pratama", "Wijaya", "Santoso", "Hartono", "Susilo", "Wibowo"]


def random_pasien_payload(prefix: str = "F4") -> dict:
    is_male = random.random() < 0.5
    nama = (
        f"{prefix} {random.choice(NAMA_M if is_male else NAMA_F)} "
        f"{random.choice(NAMA_BELAKANG)} {int(time.time() * 1_000_000) % 10_000_000:07d}"
    )
    return {
        "nama": nama,
        "jenis_kelamin": "L" if is_male else "P",
        "tgl_lahir": "1990-01-15",
        "tipe_membership": "REGULAR",
        "status_verifikasi": "VERIFIED",
    }


# =============================================================================
# User Classes
# =============================================================================
class FOUser(HttpUser):
    """FO — daftar + buat antrian. 2 instance untuk test nomor_antrean race."""
    wait_time = between(*FO_WAIT)
    fixed_count = 2

    def on_start(self):
        if not login_user(self.client, *LOGIN_FO):
            self.environment.runner.quit()
            raise Exception("FO login failed")

    @task(2)
    def register_pasien_baru(self):
        global _FO_REGISTER_OK, _FO_REGISTER_FAIL
        r = self.client.get("/web/pendaftaran-pasien", name="GET /pendaftaran-pasien")
        if r.status_code != 200:
            return
        csrf = get_csrf_from_html(r.text)
        payload = random_pasien_payload("F4REG")
        payload["csrf_token"] = csrf
        with self.client.post(
            "/web/pendaftaran-pasien",
            data=payload,
            allow_redirects=False,
            name="POST /pendaftaran-pasien",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 302, 303):
                _FO_REGISTER_OK += 1
                r.success()
            else:
                _FO_REGISTER_FAIL += 1
                r.failure(f"register fail: {r.status_code}")

    @task(5)
    def buat_antrian_existing(self):
        """Highest weight — stress nomor_antrean atomic counter with 2 FO concurrent."""
        global _FO_ANTRIAN_OK, _FO_ANTRIAN_FAIL
        id_pasien = random.randint(1, 100)
        csrf = self.client.cookies.get("sehati_csrf") or ""
        if not csrf:
            self.client.get("/web/pendaftaran-pasien", name="GET /pendaftaran-pasien (csrf)")
            csrf = self.client.cookies.get("sehati_csrf") or ""
        with self.client.post(
            f"/web/pasien/{id_pasien}/buat-antrian",
            data={
                "status_antrian": "ANTRI_KONSULTASI",
                "keluhan_utama": "Fase 4 stress",
                "csrf_token": csrf,
            },
            allow_redirects=False,
            name="POST /pasien/{id}/buat-antrian",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 302, 303):
                _FO_ANTRIAN_OK += 1
                r.success()
            else:
                _FO_ANTRIAN_FAIL += 1
                r.failure(f"buat-antrian fail: {r.status_code}")

    @task(1)
    def cari_pasien(self):
        q = random.choice(["F4", "Pratama", ""])
        url = "/web/pasien" + (f"?q={q}" if q else "")
        self.client.get(url, name="GET /pasien?q=*")


class _DokterBase(HttpUser):
    abstract = True
    wait_time = between(*DOKTER_WAIT)
    USERNAME = ""
    PASSWORD = ""

    def on_start(self):
        if not login_user(self.client, self.USERNAME, self.PASSWORD):
            self.environment.runner.quit()
            raise Exception(f"Dokter {self.USERNAME} login failed")

    @task(5)
    def cek_antrian(self):
        self.client.get("/web/dokter/antrian", name="GET /dokter/antrian")
        self.client.get("/web/dokter/antrian/list", name="GET /dokter/antrian/list")

    @task(2)
    def cari_pasien(self):
        q = random.choice(["F4REG", "Pratama", ""])
        url = "/web/pasien" + (f"?q={q}" if q else "")
        self.client.get(url, name="GET /pasien?q=* (dokter)")

    @task(1)
    def dashboard(self):
        self.client.get("/web/dashboard", name="GET /dashboard")


class DokterAUser(_DokterBase):
    USERNAME, PASSWORD = LOGIN_DOKTER_A
    fixed_count = 1


class DokterBUser(_DokterBase):
    USERNAME, PASSWORD = LOGIN_DOKTER_B
    fixed_count = 1


class DokterCUser(_DokterBase):
    """Dokter C reuse credentials dokter_a (separate session)."""
    USERNAME, PASSWORD = LOGIN_DOKTER_A
    fixed_count = 1


class PerawatUser(HttpUser):
    """4 instance — heavy read pressure di ruang tindakan."""
    wait_time = between(*PERAWAT_WAIT)
    fixed_count = 4

    def on_start(self):
        if not login_user(self.client, *LOGIN_PERAWAT):
            self.environment.runner.quit()
            raise Exception("Perawat login failed")

    @task(4)
    def cek_ruang_tindakan(self):
        self.client.get("/web/ruang-tindakan/antrian", name="GET /ruang-tindakan/antrian")
        self.client.get("/web/ruang-tindakan/antrian/list", name="GET /ruang-tindakan/antrian/list")

    @task(2)
    def cek_antrian_umum(self):
        self.client.get("/web/kunjungan", name="GET /kunjungan (perawat)")


class KasirUser(HttpUser):
    """3 instance — concurrent kasir read."""
    wait_time = between(*KASIR_WAIT)
    fixed_count = 3

    def on_start(self):
        if not login_user(self.client, *LOGIN_KASIR):
            self.environment.runner.quit()
            raise Exception("Kasir login failed")

    @task(4)
    def cek_antrian_kasir(self):
        self.client.get("/web/kasir/antrian", name="GET /kasir/antrian")
        self.client.get("/web/kasir/antrian/list", name="GET /kasir/antrian/list")

    @task(1)
    def cari_pasien(self):
        self.client.get("/web/pasien", name="GET /pasien (kasir)")


class ApotekUser(HttpUser):
    wait_time = between(*APOTEK_WAIT)
    fixed_count = 2

    def on_start(self):
        if not login_user(self.client, *LOGIN_APOTEK):
            self.environment.runner.quit()
            raise Exception("Apotek login failed")

    @task(4)
    def cek_apotek(self):
        self.client.get("/web/apotek", name="GET /apotek")

    @task(1)
    def suggested_order(self):
        self.client.get("/web/apotek/suggested-order", name="GET /apotek/suggested-order")


class OwnerMonitorUser(HttpUser):
    """Owner background — buka dashboard + reports berkala (real klinik scenario)."""
    wait_time = between(*OWNER_WAIT)
    fixed_count = 1

    def on_start(self):
        if not login_user(self.client, *LOGIN_OWNER):
            self.environment.runner.quit()
            raise Exception("Owner login failed")

    @task(3)
    def dashboard(self):
        self.client.get("/web/dashboard", name="GET /dashboard (owner)")

    @task(2)
    def reports_omzet(self):
        self.client.get("/web/reports/omzet", name="GET /reports/omzet")

    @task(2)
    def reports_kinerja(self):
        self.client.get("/web/reports/kinerja-dokter", name="GET /reports/kinerja-dokter")

    @task(1)
    def reports_audit(self):
        self.client.get("/web/reports/audit-log", name="GET /reports/audit-log")


# =============================================================================
# Event hooks
# =============================================================================
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("=" * 70)
    print("STRESS TEST FASE 4 — Maximum Capacity (15 User)")
    print("=" * 70)
    print(f"Target: {environment.host}")
    print(f"Profiles: FO(2) + Dokter A+B+C(3) + Perawat(4) + Kasir(3) + Apotek(2) + Owner(1) = 15")
    print(f"Speed mode: {SPEED_MODE.upper()}")
    print(f"DB pool config: pool_size=10, max_overflow=20 (cap 30 concurrent)")
    print("=" * 70)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    print("\n" + "=" * 70)
    print("FASE 4 CUSTOM COUNTERS")
    print("=" * 70)
    total_reg = _FO_REGISTER_OK + _FO_REGISTER_FAIL
    total_ant = _FO_ANTRIAN_OK + _FO_ANTRIAN_FAIL
    reg_rate = (_FO_REGISTER_OK / total_reg * 100) if total_reg else 0
    ant_rate = (_FO_ANTRIAN_OK / total_ant * 100) if total_ant else 0
    print(f"FO register pasien:  OK={_FO_REGISTER_OK}, FAIL={_FO_REGISTER_FAIL} ({reg_rate:.1f}% success)")
    print(f"FO buat-antrian:     OK={_FO_ANTRIAN_OK}, FAIL={_FO_ANTRIAN_FAIL} ({ant_rate:.1f}% success)")
    print()
    print("POST-TEST SQL VERIFICATION (critical untuk Fase 4):")
    print()
    print("# 1. Cek duplicate nomor antrean (HARUSNYA 0 row — paling kritis):")
    print('sudo mysql db_sehati_test -e "')
    print('  SELECT tgl_kunjungan, nomor_antrean, COUNT(*) as cnt')
    print('  FROM kunjungan')
    print('  GROUP BY tgl_kunjungan, nomor_antrean')
    print('  HAVING cnt > 1;"')
    print()
    print("# 2. Cek total + unique nomor:")
    print('sudo mysql db_sehati_test -e "')
    print('  SELECT MIN(nomor_antrean) AS min_n, MAX(nomor_antrean) AS max_n,')
    print('         COUNT(DISTINCT nomor_antrean) AS unique_n, COUNT(*) AS total_n')
    print('  FROM kunjungan WHERE DATE(tgl_kunjungan) = CURDATE();"')
    print()
    print("# 3. Cek pasien yang dibuat di test ini:")
    print('sudo mysql db_sehati_test -e "')
    print("  SELECT COUNT(*) AS f4_pasien FROM pasien WHERE nama LIKE 'F4%';\"")
    print("=" * 70)
