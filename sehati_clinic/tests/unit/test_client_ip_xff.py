"""P1-3 regresi: get_client_ip tahan spoof X-Forwarded-For.

XFF hanya dipercaya bila peer = proxy tepercaya (default 127.0.0.1/::1).
Klien langsung yang mengirim XFF palsu TIDAK boleh mengubah IP yang dipakai
rate-limit (kalau bisa, brute-force protection jebol).
"""
import types
from app.core import rate_limit as rl


class _Req:
    def __init__(self, peer, xff=None):
        self.client = types.SimpleNamespace(host=peer) if peer else None
        self.headers = {"x-forwarded-for": xff} if xff else {}


def ip(peer, xff=None):
    return rl.get_client_ip(_Req(peer, xff))


def test_direct_client_spoof_xff_diabaikan():
    # penyerang langsung (bukan proxy tepercaya) kirim XFF palsu → pakai peer
    assert ip("203.0.113.9", "1.2.3.4") == "203.0.113.9"
    assert ip("203.0.113.9", "9.9.9.9") == "203.0.113.9"  # rotasi XFF tak ganti bucket


def test_behind_trusted_proxy_pakai_xff():
    assert ip("127.0.0.1", "9.9.9.9") == "9.9.9.9"


def test_behind_proxy_abaikan_xff_palsu_di_kiri():
    # nginx meng-append IP asli di kanan; kiri bisa palsu dari klien
    assert ip("127.0.0.1", "1.1.1.1, 9.9.9.9") == "9.9.9.9"


def test_direct_tanpa_xff_pakai_peer():
    assert ip("203.0.113.9") == "203.0.113.9"


def test_tanpa_client_fallback():
    assert ip(None, "1.2.3.4") == "unknown"
