"""
Rate limiting login — in-memory, per-IP, dependency-free (C2 mitigation).

Filosofi (DEC-070 #4): lindungi dari brute-force TANPA mengganggu operasional
klinik. JADI:
- Hitung HANYA percobaan GAGAL (login sukses reset counter) → staf yang salah
  ketik 1-2x tidak terdampak.
- Per-IP, BUKAN per-akun → tidak ada "account lockout" yang mengunci staf.
- Ambang longgar + window pendek auto-reset.

A12 (DEC-082): cooldown BERTINGKAT (cascade). Blokir pertama singkat (1 menit),
naik tiap blokir berulang (2, 3, 4, … menit) sampai cap. Ramah untuk salah-ketik
sesekali, makin menyulitkan brute-force yang gigih. Strike direset setelah periode
bersih (tanpa blokir baru) atau saat login sukses.

Catatan: in-memory = per-proses. Cukup untuk deployment single-worker uvicorn.
Kalau scale ke multi-worker/multi-instance nanti, pindah ke Redis (strike juga).
"""
from __future__ import annotations

import threading
import time

# Konfigurasi (sengaja longgar untuk lingkungan klinik tepercaya)
WINDOW_SECONDS = 600            # jendela pengamatan gagal: 10 menit
MAX_FAILURES = 10              # gagal per IP dalam window sebelum di-rem
COOLDOWN_STEP_SECONDS = 60     # A12: +1 menit tiap tingkat blokir (1,2,3,4,…)
COOLDOWN_MAX_SECONDS = 1800    # cap cooldown: 30 menit
STRIKE_RESET_SECONDS = 3600    # reset tingkat setelah 1 jam tanpa blokir baru
COOLDOWN_SECONDS = COOLDOWN_STEP_SECONDS  # alias kompat (base cooldown)

_failures: dict[str, list[float]] = {}
_blocked_until: dict[str, float] = {}
_strikes: dict[str, int] = {}          # A12: jumlah blokir berulang per IP
_last_block_at: dict[str, float] = {}  # untuk reset strike setelah bersih
_lock = threading.Lock()


def get_client_ip(request) -> str:
    """Ambil IP klien. Hormati X-Forwarded-For kalau di belakang nginx/proxy."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    client = getattr(request, "client", None)
    return client.host if client else "unknown"


def _maybe_reset_strikes(ip: str, now: float) -> None:
    """Reset tingkat kalau sudah lama sejak blokir terakhir. Panggil dalam _lock."""
    lb = _last_block_at.get(ip)
    if lb is not None and (now - lb) > STRIKE_RESET_SECONDS:
        _strikes.pop(ip, None)
        _last_block_at.pop(ip, None)


def _cooldown_for(strike: int) -> int:
    """Durasi cooldown (detik) untuk tingkat ke-`strike` (1,2,3,…), di-cap."""
    return min(COOLDOWN_STEP_SECONDS * max(1, strike), COOLDOWN_MAX_SECONDS)


def check_login_allowed(ip: str) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds).

    allowed=False kalau IP sedang dalam cooldown karena terlalu banyak gagal.
    """
    now = time.time()
    with _lock:
        blocked = _blocked_until.get(ip)
        if blocked is not None:
            if now < blocked:
                return False, int(blocked - now) + 1
            # cooldown habis — bersihkan blokir + window (strike SENGAJA dipertahankan
            # supaya blokir berikutnya lebih panjang; auto-reset via STRIKE_RESET).
            _blocked_until.pop(ip, None)
            _failures.pop(ip, None)
        _maybe_reset_strikes(ip, now)
        return True, 0


def record_login_failure(ip: str) -> None:
    """Catat 1 kegagalan login. Aktifkan cooldown BERTINGKAT kalau lewat ambang."""
    now = time.time()
    with _lock:
        _maybe_reset_strikes(ip, now)
        arr = [t for t in _failures.get(ip, []) if now - t < WINDOW_SECONDS]
        arr.append(now)
        _failures[ip] = arr
        if len(arr) >= MAX_FAILURES:
            strike = _strikes.get(ip, 0) + 1
            _strikes[ip] = strike
            _last_block_at[ip] = now
            _blocked_until[ip] = now + _cooldown_for(strike)
            _failures.pop(ip, None)  # blokir aktif → window direset untuk ronde berikut


def clear_login_attempts(ip: str) -> None:
    """Reset semua state untuk IP (dipanggil saat login sukses) → clean slate."""
    with _lock:
        _failures.pop(ip, None)
        _blocked_until.pop(ip, None)
        _strikes.pop(ip, None)
        _last_block_at.pop(ip, None)


__all__ = [
    "get_client_ip",
    "check_login_allowed",
    "record_login_failure",
    "clear_login_attempts",
    "WINDOW_SECONDS",
    "MAX_FAILURES",
    "COOLDOWN_SECONDS",
    "COOLDOWN_STEP_SECONDS",
    "COOLDOWN_MAX_SECONDS",
    "STRIKE_RESET_SECONDS",
]
