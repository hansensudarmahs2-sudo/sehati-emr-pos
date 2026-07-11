# 02 — Backend Layer Checklist

**Layer:** Python / FastAPI / SQLAlchemy
**Cadence:** Weekly (automated via `scripts/audit_gaps.py` + manual review)
**Reference:** `00_PROTOCOL.md`

---

## Tujuan

Pastikan backend code:
1. **Parse-able** (tidak ada syntax error tersembunyi)
2. **Transaction-disciplined** (router never commits — DEC-030)
3. **Audit-covered** (semua operasi mutating ter-log)
4. **No silent failure** (tidak ada bare `except: pass`)
5. **No hardcoded secrets**

---

## Checklist (otomatis)

| # | Check | Severity kalau fail | Cara |
|---|-------|---------------------|------|
| BE-01 | Semua `.py` lulus AST parse | 🔴 CRITICAL | Python compile check |
| BE-02 | Tidak ada `db.commit()` di `app/web/routes/` atau `app/api/v1/` | 🟠 HIGH | Grep — DEC-030 violation |
| BE-03 | Service yang mutating tapi tidak panggil `AuditService` | 🟠 HIGH | Grep service files vs audit calls |
| BE-04 | Bare `except: pass` atau `except Exception: pass` | 🟡 MEDIUM | Silent failure risk |
| BE-05 | Hardcoded JWT secret atau password di kode (bukan dari config) | 🔴 CRITICAL | Grep "secret\|jwt_secret" outside config/env |
| BE-06 | `TODO` / `FIXME` / `XXX` comments yang umur > 30 hari | 🟢 LOW | Tracking debt |
| BE-07 | Import dari `app.db.session.Base` (harusnya `app.db.base.Base`) | 🟠 HIGH | Lesson learned dari bug pengadaan.py |
| BE-08 | Route file punya `Body(...)` tanpa schema Pydantic | 🟡 MEDIUM | Type safety |

---

## Checklist (manual)

- [ ] **Migration alignment** — apakah ada model baru di `app/db/models/` yang belum punya migration SQL di `migrations/sql/`?
- [ ] **Schema vs Model alignment** — apakah ada perbedaan antara field di Pydantic schemas vs ORM models?
- [ ] **Dependency versions** — `pip list --outdated` ada package penting yang outdated?
- [ ] **Test suite** — kalau ada `tests/`, jalankan `pytest` dan cek pass rate

---

## Cara menjalankan

```bash
cd /path/to/sehati_clinic
python ../Project_Memory/HealthCheck/scripts/audit_gaps.py
```

---

## Glossary

- **Service-owned transaction** (DEC-030): Service di `app/services/` yang melakukan commit ke DB. Router (`app/web/routes/`, `app/api/v1/`) **tidak boleh** call `db.commit()` langsung. Alasan: konsistensi atomicity, mudah test.

- **Audit-covered**: Setiap method service yang melakukan INSERT/UPDATE/DELETE harus panggil `AuditService(db).log_action(...)` dengan params lengkap (actor, aksi, tabel_target, id_target, keterangan). Alasan: traceability + compliance.

- **Bare except**: `except: pass` atau `except Exception: pass` tanpa logging/handling. Bahaya karena bug ter-swallow diam-diam.

---

## Kalau ada finding

1. CRITICAL/HIGH → langsung ke `07_known_issues.md` tag `[health-check-backend]`
2. Kalau pattern di banyak file → buat refactor task di `08_roadmap.md`
3. Update `11_decisions_log.md` kalau ada keputusan struktural
