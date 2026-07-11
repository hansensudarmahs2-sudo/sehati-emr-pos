"""
In-process TTL cache — untuk endpoint TAMPILAN read-heavy (mis. daftar antrian).

REGULASI (lihat Project_Memory/KESTABILAN_OPERASIONAL_EMRPOS.md §9):
- HANYA untuk tampilan non-otoritatif. JANGAN untuk data keputusan/tulis
  (saldo, stok, status bayar di jalur keputusan selalu baca langsung ke DB).
- TTL pendek → basi terbatas & sembuh sendiri.
- LRU terbatas → anti memory-bloat.
- Kill-switch → bisa dimatikan seketika bila berulah (env SEHATI_CACHE_ENABLED=false / set_enabled()).
- Single-flight per-key → anti thundering-herd (hanya 1 producer jalan saat miss).
- Kunci cache DISUPLAI PEMANGGIL dan HARUS lengkap (role/id_staf/filter/klinik).
- Error/empty TIDAK di-cache (exception producer dipropagasi, tidak disimpan).

Thread-safe: route sync FastAPI berjalan di threadpool, jadi akses konkuren nyata.
Cache ini per-proses (per-worker). Untuk multi-worker, tiap worker punya salinan
sendiri dengan TTL masing-masing — dapat diterima untuk TTL pendek display-only.
"""
from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from typing import Any, Callable

# Batas & kill-switch (boleh dioverride via env saat boot)
_MAX_ENTRIES = int(os.getenv("SEHATI_CACHE_MAX_ENTRIES", "512"))
_ENABLED = os.getenv("SEHATI_CACHE_ENABLED", "true").lower() not in ("0", "false", "no", "off")

# TTL default untuk fragment antrian (detik). Di atas interval poll 10s agar poll
# beruntun 1 user saling nge-hit; basi maksimum = TTL (aman, layar sudah refresh 10s).
ANTRIAN_TTL = float(os.getenv("SEHATI_ANTRIAN_CACHE_TTL", "12"))

_lock = threading.Lock()                                   # lindungi _store & _stats
_store: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()   # key -> (expire_monotonic, value)
_keylocks: "dict[str, threading.Lock]" = {}                # single-flight per key
_keylocks_lock = threading.Lock()
_stats = {"hits": 0, "misses": 0, "evictions": 0}


def is_enabled() -> bool:
    return _ENABLED


def set_enabled(value: bool) -> None:
    """Kill-switch runtime. False → semua get_or_set langsung memanggil producer (tanpa cache)."""
    global _ENABLED
    _ENABLED = bool(value)


def stats() -> dict:
    with _lock:
        total = _stats["hits"] + _stats["misses"]
        ratio = (_stats["hits"] / total) if total else 0.0
        return {**_stats, "size": len(_store), "enabled": _ENABLED,
                "max_entries": _MAX_ENTRIES, "hit_ratio": round(ratio, 3)}


def clear() -> None:
    with _lock:
        _store.clear()


def reset_stats() -> None:
    """Nolkan counter hit/miss/eviction (untuk demo/benchmark)."""
    with _lock:
        _stats["hits"] = 0
        _stats["misses"] = 0
        _stats["evictions"] = 0


def invalidate(key: str) -> None:
    with _lock:
        _store.pop(key, None)


def _get_fresh_locked(key: str, now: float):
    """Ambil nilai segar (dipanggil di dalam _lock). Return (value,) atau None."""
    item = _store.get(key)
    if item is None:
        return None
    expire_at, value = item
    if expire_at <= now:
        _store.pop(key, None)  # kedaluwarsa → buang
        return None
    _store.move_to_end(key)    # sentuh → LRU
    return (value,)


def _key_lock(key: str) -> threading.Lock:
    with _keylocks_lock:
        kl = _keylocks.get(key)
        if kl is None:
            kl = threading.Lock()
            _keylocks[key] = kl
        return kl


def get_or_set(key: str, ttl: float, producer: Callable[[], Any]) -> Any:
    """
    Kembalikan nilai cache bila masih segar; jika tidak, panggil producer(), simpan, kembalikan.

    - Kill-switch OFF atau ttl<=0 → selalu producer() (tanpa cache).
    - Single-flight: saat miss, hanya 1 thread per-key menjalankan producer; lainnya menunggu
      lalu memakai hasilnya.
    - Exception dari producer TIDAK di-cache (dipropagasi).
    """
    if not _ENABLED or ttl <= 0:
        return producer()

    now = time.monotonic()
    with _lock:
        hit = _get_fresh_locked(key, now)
        if hit is not None:
            _stats["hits"] += 1
            return hit[0]

    # MISS → single-flight per key
    kl = _key_lock(key)
    with kl:
        # double-check: thread lain mungkin sudah mengisi selagi kita menunggu kl
        with _lock:
            hit = _get_fresh_locked(key, time.monotonic())
            if hit is not None:
                _stats["hits"] += 1
                return hit[0]

        value = producer()  # DILUAR _lock: jangan tahan lock global saat query DB

        with _lock:
            _store[key] = (time.monotonic() + ttl, value)
            _store.move_to_end(key)
            _stats["misses"] += 1
            while len(_store) > _MAX_ENTRIES:
                _store.popitem(last=False)  # evict LRU (paling lama tak dipakai)
                _stats["evictions"] += 1
        return value
