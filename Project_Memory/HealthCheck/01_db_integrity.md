# 01 — DB Integrity Checklist

**Layer:** Database (MySQL)
**Cadence:** Weekly (automated via `scripts/db_integrity.py`)
**Reference:** `00_PROTOCOL.md`

---

## Tujuan

Pastikan data di MySQL **konsisten**, **lengkap**, dan **sehat**: tidak ada record yatim, tidak ada nilai yang mustahil (negatif, NULL di field wajib), constraint masih berfungsi.

---

## Checklist (otomatis)

| # | Check | Severity kalau fail | Cara |
|---|-------|---------------------|------|
| DB-01 | Stok produk negatif | 🔴 CRITICAL | `SELECT * FROM master_produk WHERE stok_terkini < 0` |
| DB-02 | Stok bahan negatif | 🔴 CRITICAL | `SELECT * FROM inventory_stok WHERE stok_terkini < 0` |
| DB-03 | Inventory_history tanpa parent (XOR violation) | 🟠 HIGH | `WHERE (id_produk IS NULL AND id_bahan IS NULL) OR (id_produk IS NOT NULL AND id_bahan IS NOT NULL)` |
| DB-04 | Master_staf tanpa password_hash | 🔴 CRITICAL | `SELECT * FROM master_staf WHERE password_hash IS NULL OR password_hash = ''` |
| DB-05 | Master_staf dengan role invalid | 🟠 HIGH | Compare distinct role vs StafRoleEnum |
| DB-06 | Kunjungan tanpa pasien (FK orphan) | 🟠 HIGH | `LEFT JOIN pasien WHERE pasien.id_pasien IS NULL` |
| DB-07 | Audit log tanpa id_staf untuk operasi mutating | 🟡 MEDIUM | `WHERE id_staf IS NULL AND aksi NOT IN ('LOGIN_FAIL', ...)` |
| DB-08 | Pemesanan_item tanpa parent pemesanan | 🟠 HIGH | LEFT JOIN check |
| DB-09 | Pemesanan_receive dengan qty > pemesanan_item.qty_dipesan | 🟠 HIGH | Aggregate query |
| DB-10 | Stock_opname_item tanpa parent opname | 🟠 HIGH | LEFT JOIN check |
| DB-11 | Transaksi_kasir tanpa kunjungan | 🟡 MEDIUM | LEFT JOIN check |
| DB-12 | Master_produk dengan stok_minimal < 0 | 🟡 MEDIUM | Data quality check |
| DB-13 | Pasien duplikat (nomor_ktp sama, beda id_pasien) | 🟡 MEDIUM | GROUP BY HAVING COUNT > 1 |
| DB-14 | Audit log entries terakhir > 7 hari (sistem tidak aktif?) | 🟡 MEDIUM | Last entry check |

---

## Checklist (manual, kalau ada waktu)

- [ ] **Database size** — apakah tumbuh wajar (tidak ada table yang tiba-tiba 10x lipat)?
- [ ] **Index health** — `SHOW INDEX FROM master_produk` — apakah index masih aktif?
- [ ] **Slow query log** — ada query yang ambil > 1 detik?
- [ ] **Connection pool** — apakah `pool_recycle=280` masih cocok atau perlu adjust?

---

## Cara menjalankan

```bash
cd /path/to/sehati_clinic
python ../Project_Memory/HealthCheck/scripts/db_integrity.py
```

Output: append ke run log saat ini, atau standalone ke `logs/YYYY-MM-DD_db_only.md`.

---

## Kalau ada finding

1. CRITICAL/HIGH → langsung tambahkan ke `07_known_issues.md` dengan tag `[health-check-db]`
2. Investigasi root cause (biasanya: race condition, missing transaction, atau bug yang lolos di-deploy)
3. Tulis decision di `11_decisions_log.md` kalau ada keputusan struktural
