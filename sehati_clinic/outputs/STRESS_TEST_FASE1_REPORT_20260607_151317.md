# Stress Test Fase 1 — Smoke Test Report

**Tanggal**: 2026-06-07 15:13:17 WIB
**Target**: http://127.0.0.1:8001
**User**: superadmin (Owner)
**Durasi total**: 1.4 detik
**Total request**: 55
**Throughput**: 38.3 req/s
**Total error**: 11 (20.00% kalau total > 0)

## Verdict

⚠️ **REVIEW NEEDED** — beberapa endpoint melewati target atau ada error.

**Endpoint dengan error:**
- Antrian FO Hari Ini: 2 error (100.0%)
- Antrian Apotek: 2 error (100.0%)
- Antrian Perawat: 2 error (100.0%)
- Master Staf List: 4 error (100.0%)

## Phase 1 — READ Endpoints (per endpoint)

| Endpoint | N | min | p50 | p95 | p99 | max | mean | err | status codes |
|----------|---|-----|-----|-----|-----|-----|------|-----|--------------|
| Master Produk List | 5 | 8.5 | 9.5 | 58.5 | 58.5 | 58.5 | 22.7 | 0 | 200:5 |
| Reports Audit Log | 3 | 9.7 | 9.7 | 33.4 | 33.4 | 33.4 | 17.6 | 0 | 200:3 |
| Antrian Dokter HTML | 2 | 5.8 | 27.1 | 27.1 | 27.1 | 27.1 | 16.5 | 0 | 200:2 |
| Reports Omzet | 5 | 8.4 | 8.7 | 26.2 | 26.2 | 26.2 | 12.2 | 0 | 200:5 |
| Settings Klinik | 3 | 6.8 | 6.9 | 23.3 | 23.3 | 23.3 | 12.3 | 0 | 200:3 |
| Reports Kinerja Dokter | 1 | 22.7 | 22.7 | 22.7 | 22.7 | 22.7 | 22.7 | 0 | 200:1 |
| Reports Top Treatment | 4 | 7.4 | 8.2 | 21.7 | 21.7 | 21.7 | 11.2 | 0 | 200:4 |
| Pasien Search (kosong) | 5 | 6.2 | 6.3 | 20.1 | 20.1 | 20.1 | 9.2 | 0 | 200:5 |
| Antrian Kasir | 3 | 6.2 | 6.5 | 19.8 | 19.8 | 19.8 | 10.9 | 0 | 200:3 |
| Master Treatment List | 2 | 7.4 | 18.3 | 18.3 | 18.3 | 18.3 | 12.8 | 0 | 200:2 |
| Dashboard | 2 | 13.9 | 14.7 | 14.7 | 14.7 | 14.7 | 14.3 | 0 | 200:2 |
| Reports Landing | 3 | 6.2 | 6.9 | 14.5 | 14.5 | 14.5 | 9.2 | 0 | 200:3 |
| Pasien Search (q=Sari) | 2 | 5.8 | 6.2 | 6.2 | 6.2 | 6.2 | 6.0 | 0 | 200:2 |
| Antrian Perawat | 2 | 0.7 | 1.4 | 1.4 | 1.4 | 1.4 | 1.0 | 2 | 404:2 |
| Antrian Apotek | 2 | 1.1 | 1.3 | 1.3 | 1.3 | 1.3 | 1.2 | 2 | 404:2 |
| Master Staf List | 4 | 0.8 | 1.1 | 1.3 | 1.3 | 1.3 | 1.1 | 4 | 404:4 |
| Antrian FO Hari Ini | 2 | 1.0 | 1.2 | 1.2 | 1.2 | 1.2 | 1.1 | 2 | 404:2 |

## Phase 2 — WRITE Smoke (GET form pages)

| Metric | Value |
|--------|-------|
| n | 5 |
| min_ms | 1.4 |
| p50_ms | 6.6 |
| p95_ms | 13.6 |
| p99_ms | 13.6 |
| max_ms | 13.6 |
| mean_ms | 7.0 |
| errors | 1 |
| status codes | 200:4, 404:1 |

## Catatan

- Test ini hanya measure **single-user sequential**. Tidak detect race condition / lock contention.
- Untuk write path (SOAP save, payment), butuh Fase 2 dengan Locust (multi-user concurrent).
- Endpoint Pasien Search dengan filter mungkin lebih lambat karena LIKE query — itu expected.
- Reports endpoints mungkin lebih lambat karena aggregation — wajar kalau p95 ~500-800ms.
