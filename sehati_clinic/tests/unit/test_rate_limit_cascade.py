"""
A12 (DEC-082) — unit test cooldown login BERTINGKAT (cascade).
Murni in-memory (tanpa DB). Pakai clock palsu via monkeypatch.

Run: .venv/bin/pytest tests/unit/test_rate_limit_cascade.py -v
"""
import pytest

from app.core import rate_limit as rl


class _Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def time(self):
        return self.t


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(rl, "time", c)
    return c


def _block(ip):
    for _ in range(rl.MAX_FAILURES):
        rl.record_login_failure(ip)
    return rl.check_login_allowed(ip)


def test_cascade_escalates(clock):
    ip = "10.0.0.1"
    rl.clear_login_attempts(ip)
    a, r = _block(ip)
    assert not a and 55 <= r <= 61          # tingkat 1 ≈ 1 menit
    clock.t += r + 1
    assert rl.check_login_allowed(ip)[0]
    a, r = _block(ip)
    assert not a and 115 <= r <= 121        # tingkat 2 ≈ 2 menit
    clock.t += r + 1
    assert rl.check_login_allowed(ip)[0]
    a, r = _block(ip)
    assert not a and 175 <= r <= 181        # tingkat 3 ≈ 3 menit
    rl.clear_login_attempts(ip)


def test_strike_reset_after_clean(clock):
    ip = "10.0.0.2"
    rl.clear_login_attempts(ip)
    a, r = _block(ip)
    assert not a
    clock.t += r + 1
    assert rl.check_login_allowed(ip)[0]
    a, r = _block(ip)
    assert not a and 115 <= r <= 121        # tingkat 2
    # lewati cooldown + periode bersih → tingkat reset
    clock.t += r + 1 + rl.STRIKE_RESET_SECONDS + 10
    assert rl.check_login_allowed(ip)[0]
    a, r = _block(ip)
    assert not a and 55 <= r <= 61          # kembali ke tingkat 1
    rl.clear_login_attempts(ip)


def test_lenient_below_threshold(clock):
    ip = "10.0.0.3"
    rl.clear_login_attempts(ip)
    for _ in range(rl.MAX_FAILURES - 1):
        rl.record_login_failure(ip)
    assert rl.check_login_allowed(ip)[0]    # 9x gagal belum memblokir
    rl.clear_login_attempts(ip)


def test_success_clears_state(clock):
    ip = "10.0.0.4"
    rl.clear_login_attempts(ip)
    a, _ = _block(ip)
    assert not a
    rl.clear_login_attempts(ip)             # login sukses
    assert rl.check_login_allowed(ip)[0]
