"""
Stress Test — Fase 3 Realistic Peak (7 User via Locust)

Tujuan: simulasi peak hour klinik dengan workflow lebih realistic.

USAGE:
    # Pastikan test uvicorn :8001 + seed sudah jalan + locust installed.

    # Quick smoke 2 menit:
    locust -f tools/stress/05_fase3_locust.py \\
        --host http://127.0.0.1:8001 \\
        --users 7 --spawn-rate 1 \\
        --run-time 2m --headless \\
        --csv outputs/stress_fase3_quick \\
        --html outputs/stress_fase3_quick.html

    # Full run 30 menit (per roadmap):
    STRESS_SPEED=normal locust -f tools/stress/05_fase3_locust.py \\
        --host http://127.0.0.1:8001 \\
        --users 7 --spawn-rate 1 \\
        --run-time 30m --headless \\
        --csv outputs/stress_fase3_full \\
        --html outputs/stress_fase3_full.html

User profiles (7 total per roadmap):
- 1 FO       — daftar pasien baru + buat antrian existing pasien (write-heavy)
- 2 Dokter   — dokter_a + dokter_b: cek antrian scoped + cek pasien
- 2 Perawat  — cek antrian ruang tindakan
- 1 Kasir    — cek antrian + view tagihan
- 1 Apoteker — cek antrian apotek + suggested order

Critical scenarios:
- FO concurrent register + buat-antrian → test nomor_antrean atomic
- Dokter A & B both pull antrian → test scoping per dokter (SOAP-GUARD #321)
- Kasir + Apoteker pull simultaneous → test status_antrian race

Target Fase 3:
- 0 deadlock
- 0 duplicate nomor_antrean (post-test SQL verify)
- p95 < 2000ms semua endpoint (lebih longgar dari Fase 2)
- Error rate < 2%

Catatan SOAP-GUARD race test:
Race condition 2 dokter Ubah Konsul pasien sama TIDAK natural occur karena
SOAP-GUARD scoping → setelah Dokter A submit SOAP, kunjungan hilang dari
antrian Dokter B. Untuk test race ini perlu manual: dr. Hansen open 2
browser tab login beda dokter, klik Ubah Konsul same pasien.
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
LOGIN_DOKTER_A = ("dokter_a", "dokter123")
LOGIN_DOKTER_B = ("dokter_b", "dokter123")
LOGIN_PERAWAT = ("perawat_test", "perawat123")
LOGIN_KASIR = ("kasir_test", "kasir123")
# Apoteker — seed tidak punya apoteker, pakai superadmin (Owner has full access)
LOGIN_APOTEK = ("superadmin", "admin123")

# Speed mode override via env STRESS_SPEED:
#   fast    = wait 3-8s per user (smoke 1-2 menit)
#   normal  = wait 24-108s per user (per roadmap, 30m run real)
SPEED_MODE = os.getenv("STRESS_SPEED", "fast").lower()
if SPEED_MODE == "normal":
    FO_WAIT = (24, 36)
    DOKTER_WAIT = (48, 72)
    PERAWAT_WAIT = (48, 72)
    KASIR_WAIT = (72, 108)
    APOTEK_WAIT = (48, 72)
else:
    FO_WAIT = (3, 6)
    DOKTER_WAIT = (4, 8)
    PERAWAT_WAIT = (5, 9)
    KASIR_WAIT = (6, 10)
    APOTEK_WAIT = (5, 9)

# Stats counter
_FO_REGISTER_OK = 0
_FO_REGISTER_FAIL = 0
_FO_ANTRIAN_OK = 0
_FO_ANTRIAN_FAIL = 0
_NOMOR_ANTRIAN_COLLECTED = []  # untuk cek duplicate post-test


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


NAMA_M = ["Adi", "Budi", "Cahyo", "Doni", "Eka", "Fadli", "Gani", "Heru", "Iwan", "Joko"]
NAMA_F = ["Ani", "Beta", "Cinta", "Dini", "Eva", "Fitri", "Gita", "Hani", "Indah", "Juli"]
NAMA_BELAKANG = ["Pratama", "Wijaya", "Santoso", "Hartono", "Susilo", "Wibowo", "Kusuma"]


def random_pasien_payload(prefix: str = "F3") -> dict:
    is_male = random.random() < 0.5
    nama = (
        f"{prefix} {random.choice(NAMA_M if is_male else NAMA_F)} "
        f"{random.choice(NAMA_BELAKANG)} {int(time.time() * 1000) % 1_000_000:06d}"
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
    """FO — daftar pasien baru + buat antrian existing (write-heavy)."""

    wait_time = between(*FO_WAIT)
    weight = 1
    fixed_count = 1  # exactly 1 instance

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
        payload = random_pasien_payload("F3REG")
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

    @task(4)
    def buat_antrian_existing_pasien(self):
        """POST /pasien/{id}/buat-antrian — test nomor_antrean atomic counter."""
        global _FO_ANTRIAN_OK, _FO_ANTRIAN_FAIL
        # Pick random pasien dari seed (id_pasien 1-100)
        id_pasien = random.randint(1, 100)
        # CSRF token: baca dari cookie 'sehati_csrf' (set by middleware after GET).
        # Form field 'csrf_token' value harus match cookie value (double-submit pattern).
        csrf = self.client.cookies.get("sehati_csrf") or ""
        if not csrf:
            # Trigger cookie set via GET ke pendaftaran page (yang punya form CSRF)
            r = self.client.get("/web/pendaftaran-pasien", name="GET /pendaftaran-pasien (csrf bootstrap)")
            csrf = self.client.cookies.get("sehati_csrf") or ""
        with self.client.post(
            f"/web/pasien/{id_pasien}/buat-antrian",
            data={
                "status_antrian": "ANTRI_KONSULTASI",
                "keluhan_utama": "Stress test concurrent",
                "csrf_token": csrf,
            },
            allow_redirects=False,
            name="POST /pasien/{id}/buat-antrian",
            catch_response=True,
        ) as r:
            if r.status_code in (302, 303):
                # Parse redirect URL untuk extract nomor_antrean
                loc = r.headers.get("location", "")
                m = re.search(r"nomor\+#(\d+)", loc)
                if m:
                    _NOMOR_ANTRIAN_COLLECTED.append(int(m.group(1)))
                _FO_ANTRIAN_OK += 1
                r.success()
            elif r.status_code in (200,):
                # Mungkin "duplikat kunjungan hari ini" — itu OK behavior
                _FO_ANTRIAN_OK += 1
                r.success()
            else:
                _FO_ANTRIAN_FAIL += 1
                r.failure(f"buat-antrian fail: {r.status_code}")

    @task(2)
    def cari_pasien(self):
        q = random.choice(["And", "Sari", "Dewi", ""])
        url = "/web/pasien" + (f"?q={q}" if q else "")
        self.client.get(url, name="GET /pasien?q=*")

    @task(1)
    def lihat_antrian_hari_ini(self):
        self.client.get("/web/kunjungan", name="GET /kunjungan")


class _DokterBase(HttpUser):
    """Base untuk Dokter A & B — beda credentials saja."""
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
        q = random.choice(["F3REG", "Pratama", "Sari", ""])
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


class PerawatUser(HttpUser):
    wait_time = between(*PERAWAT_WAIT)
    fixed_count = 2

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
    wait_time = between(*KASIR_WAIT)
    fixed_count = 1

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
    fixed_count = 1

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


# =============================================================================
# Event hooks
# =============================================================================
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("=" * 70)
    print("STRESS TEST FASE 3 — Realistic Peak (7 User)")
    print("=" * 70)
    print(f"Target: {environment.host}")
    print(f"Profiles: FO(1) + Dokter A(1) + Dokter B(1) + Perawat(2) + Kasir(1) + Apotek(1)")
    print(f"Speed mode: {SPEED_MODE.upper()}")
    print(f"Wait times (s): FO {FO_WAIT}, Dokter {DOKTER_WAIT}, Perawat {PERAWAT_WAIT}, Kasir {KASIR_WAIT}, Apotek {APOTEK_WAIT}")
    print("=" * 70)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    print("\n" + "=" * 70)
    print("FASE 3 CUSTOM COUNTERS")
    print("=" * 70)
    print(f"FO register pasien:      OK={_FO_REGISTER_OK}, FAIL={_FO_REGISTER_FAIL}")
    print(f"FO buat-antrian:         OK={_FO_ANTRIAN_OK}, FAIL={_FO_ANTRIAN_FAIL}")
    print(f"Nomor antrean collected: {len(_NOMOR_ANTRIAN_COLLECTED)} sampel")
    if _NOMOR_ANTRIAN_COLLECTED:
        n_unique = len(set(_NOMOR_ANTRIAN_COLLECTED))
        print(f"  Unique values:        {n_unique}")
        print(f"  Sample first 10:      {_NOMOR_ANTRIAN_COLLECTED[:10]}")
        if n_unique < len(_NOMOR_ANTRIAN_COLLECTED):
            print("  WARNING: ada duplikat nomor antrean (race condition detected)")
    print()
    print("POST-TEST SQL VERIFICATION:")
    print()
    print("# 1. Cek duplicate nomor antrean (HARUSNYA 0 row):")
    print('sudo mysql db_sehati_test -e "')
    print('  SELECT tgl_kunjungan, nomor_antrean, COUNT(*) as cnt')
    print('  FROM kunjungan')
    print('  GROUP BY tgl_kunjungan, nomor_antrean')
    print('  HAVING cnt > 1;"')
    print()
    print("# 2. Cek pasien & kunjungan baru:")
    print('sudo mysql db_sehati_test -e "')
    print("  SELECT COUNT(*) AS pasien_baru FROM pasien WHERE nama LIKE 'F3%';")
    print("  SELECT COUNT(*) AS kunjungan_baru FROM kunjungan WHERE DATE(tgl_kunjungan) = CURDATE();\"")
    print()
    print("# 3. Status distribution kunjungan:")
    print('sudo mysql db_sehati_test -e "')
    print('  SELECT status_antrian, COUNT(*) FROM kunjungan')
    print('  WHERE DATE(tgl_kunjungan) = CURDATE()')
    print('  GROUP BY status_antrian ORDER BY 2 DESC;"')
    print("=" * 70)
