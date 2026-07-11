# Stress Test Fase 1 — Smoke Test Report

**Tanggal**: 2026-06-07 15:16:16 WIB
**Target**: http://127.0.0.1:8001
**User**: superadmin (Owner)
**Durasi total**: 1.1 detik
**Total request**: 55
**Throughput**: 49.3 req/s
**Total error**: 0 (0.00% kalau total > 0)

## Verdict

✅ **PASS** — Semua endpoint p95 < 1000ms, 0 error. Lanjut Fase 2.

## Phase 1 — READ Endpoints (per endpoint)

| Endpoint | N | min | p50 | p95 | p99 | max | mean | err | status codes |
|----------|---|-----|-----|-----|-----|-----|------|-----|--------------|
| Master Staf List | 3 | 7.0 | 7.8 | 22.9 | 22.9 | 22.9 | 12.6 | 0 | 200:3 |
| Antrian Apotek | 2 | 7.1 | 20.4 | 20.4 | 20.4 | 20.4 | 13.7 | 0 | 200:2 |
| Antrian FO Hari Ini | 5 | 6.1 | 6.5 | 19.9 | 19.9 | 19.9 | 9.2 | 0 | 200:5 |
| Dashboard | 3 | 14.4 | 15.3 | 15.9 | 15.9 | 15.9 | 15.2 | 0 | 200:3 |
| Master Produk List | 3 | 9.1 | 9.7 | 9.9 | 9.9 | 9.9 | 9.6 | 0 | 200:3 |
| Reports Omzet | 5 | 7.9 | 9.4 | 9.8 | 9.8 | 9.8 | 9.1 | 0 | 200:5 |
| Reports Kinerja Dokter | 3 | 8.5 | 9.0 | 9.4 | 9.4 | 9.4 | 9.0 | 0 | 200:3 |
| Reports Top Treatment | 5 | 7.8 | 8.5 | 8.7 | 8.7 | 8.7 | 8.3 | 0 | 200:5 |
| Master Treatment List | 3 | 7.2 | 8.3 | 8.7 | 8.7 | 8.7 | 8.1 | 0 | 200:3 |
| Settings Klinik | 3 | 6.6 | 7.4 | 7.6 | 7.6 | 7.6 | 7.2 | 0 | 200:3 |
| Antrian Kasir | 4 | 5.7 | 7.3 | 7.4 | 7.4 | 7.4 | 6.7 | 0 | 200:4 |
| Pasien Search (kosong) | 2 | 6.3 | 7.0 | 7.0 | 7.0 | 7.0 | 6.7 | 0 | 200:2 |
| Reports Landing | 3 | 6.4 | 6.7 | 6.9 | 6.9 | 6.9 | 6.6 | 0 | 200:3 |
| Pasien Search (q=And) | 3 | 6.2 | 6.3 | 6.6 | 6.6 | 6.6 | 6.4 | 0 | 200:3 |
| Pasien Search (q=Sari) | 1 | 6.6 | 6.6 | 6.6 | 6.6 | 6.6 | 6.6 | 0 | 200:1 |
| Antrian Dokter HTML | 2 | 5.3 | 6.1 | 6.1 | 6.1 | 6.1 | 5.7 | 0 | 200:2 |

## Phase 2 — WRITE Smoke (GET form pages)

| Metric | Value |
|--------|-------|
| n | 5 |
| min_ms | 6.8 |
| p50_ms | 7.6 |
| p95_ms | 7.8 |
| p99_ms | 7.8 |
| max_ms | 7.8 |
| mean_ms | 7.4 |
| errors | 0 |
| status codes | 200:5 |

## Catatan

- Test ini hanya measure **single-user sequential**. Tidak detect race condition / lock contention.
- Untuk write path (SOAP save, payment), butuh Fase 2 dengan Locust (multi-user concurrent).
- Endpoint Pasien Search dengan filter mungkin lebih lambat karena LIKE query — itu expected.
- Reports endpoints mungkin lebih lambat karena aggregation — wajar kalau p95 ~500-800ms.
