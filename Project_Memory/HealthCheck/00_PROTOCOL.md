# Sehati Clinic — Health Check Protocol

**Status:** Active (Lite Protocol — Phase 1)
**Owner:** dr. Hansen Sudarma
**Last reviewed:** 2026-06-05
**Cadence:** Weekly (every Monday morning)

---

## 1. Tujuan

Health Check Protocol adalah dokumen rujukan resmi untuk memastikan sistem Sehati Clinic eMR + POS tetap sehat dari sisi DB, backend, frontend, dan security secara konsisten dan terdokumentasi.

Tujuannya 3 hal:

1. **Mencegah masalah** — temukan kelemahan sebelum berdampak ke pasien atau operasional.
2. **Tracking** — punya log per check sehingga bisa lihat trend (issue bertambah atau berkurang).
3. **Accountability** — siapa yang lakukan, kapan, hasilnya apa, action item-nya apa.

Health Check ini bukan menggantikan testing per-feature atau code review. Ini adalah lapisan extra untuk hal-hal yang **biasanya luput** dari developer focus harian: data integrity, audit gaps, security compliance.

---

## 2. Severity Ladder (klasifikasi finding)

Setiap temuan diklasifikasikan dengan kategori tetap di bawah. **Jangan ubah definisi** — supaya bisa dibandingkan antar run.

| Severity | Definisi | SLA fix | Block soft launch? |
|----------|----------|---------|--------------------|
| 🔴 **CRITICAL** | Data loss, security breach, PII leak, atau system unusable | < 24 jam | Ya |
| 🟠 **HIGH** | Bisnis logic salah, audit gap, transaction discipline violation | Sprint ini (≤ 7 hari) | Ya |
| 🟡 **MEDIUM** | UX kurang ramah, kode debt yang berisiko nambah, error message tidak ramah | Sprint berikutnya (≤ 14 hari) | Tidak |
| 🟢 **LOW** | TODO comment, code duplication, dokumentasi missing | Backlog | Tidak |

**Contoh klasifikasi:**

- Stok jadi negatif setelah dispense → 🔴 CRITICAL
- `nomor_ktp` masuk ke `audit_log.keterangan` → 🔴 CRITICAL (PII leak)
- Service tidak commit transaksi (router yang commit) → 🟠 HIGH
- POST form tidak punya CSRF token → 🟠 HIGH
- Error 500 ditampilkan ke user dengan stack trace mentah → 🟡 MEDIUM
- Tombol kanan-atas kurang konsisten warnanya → 🟢 LOW

---

## 3. Cadence (jadwal rutin)

**Mingguan — setiap Senin pagi**, target 15 menit:
1. Jalankan `python scripts/run_health_check.py`
2. Output ter-save di `logs/YYYY-MM-DD_weekly.md`
3. Buka log, baca summary
4. Kalau ada CRITICAL/HIGH → langsung masuk `07_known_issues.md` dengan tag `[health-check]`

**Setelah deploy fitur besar:**
- Jalankan check ad-hoc segera setelah deploy. Output: `logs/YYYY-MM-DD_post-deploy.md`.

**Bulanan (opsional, kalau Bapak punya waktu):**
- Manual frontend per-role checklist (`03_frontend_per_role.md`) → 1-2 jam, ideal melibatkan staff klinik sebagai bonus user training.

---

## 4. Komponen Lite Protocol

| File | Tipe | Kegunaan |
|------|------|----------|
| `00_PROTOCOL.md` | Reference | Dokumen ini — konstitusi sistem check |
| `01_db_integrity.md` | Checklist | Daftar check DB layer |
| `02_backend.md` | Checklist | Daftar check backend layer |
| `03_frontend_per_role.md` | Checklist | Manual test per role (printable) |
| `04_security_pii.md` | Checklist | Security + PII + role gate matrix |
| `scripts/db_integrity.py` | Script | Auto-run DB queries |
| `scripts/audit_gaps.py` | Script | Scan kode untuk audit log gaps |
| `scripts/pii_scan.py` | Script | Scan untuk PII leak risk |
| `scripts/run_health_check.py` | Script | Master runner, gabung semua check |
| `logs/YYYY-MM-DD_*.md` | Log | Hasil per run |

---

## 5. Workflow Mingguan (15 menit)

**Senin pagi:**

```bash
cd /path/to/sehati_clinic
source .venv/bin/activate  # kalau pakai virtualenv
python ../Project_Memory/HealthCheck/scripts/run_health_check.py
```

Output otomatis:
- Stdout: ringkasan singkat (PASS/WARN/FAIL counter + critical findings)
- File: `Project_Memory/HealthCheck/logs/2026-06-DD_weekly.md` (full detail)

**Lalu:**
1. Buka log file
2. Lihat section "Critical Findings" — kalau ada, tambah ke `07_known_issues.md` dengan tag `[health-check]` dan severity
3. Lihat section "Trend" — apakah issue bertambah atau berkurang? Bagus atau bahaya?
4. Update Decisions Log (`11_decisions_log.md`) kalau ada keputusan baru karena finding ini

---

## 6. Format Log Standar

Setiap log file di `logs/` harus punya format konsisten supaya trend bisa di-track:

```markdown
# Health Check — 2026-06-DD (weekly | post-deploy | baseline)

**Run by:** [nama]
**Mode:** [Full | Lite | DB-only | dst]
**Duration:** [N] menit
**Previous run:** [link ke log sebelumnya, atau "baseline"]

## Summary
- Total checks: N
- ✓ Pass: N
- ⚠ Warning: N
- ✗ Fail: N

## Critical Findings (🔴 + 🟠)
(detail per finding)

## All Findings by Severity
(detail per finding dengan kategori)

## Trend (vs previous run)
- Critical: N (was N) [↓ improving / ↑ worsening / = stable]
- High: N (was N)
- ...

## Action Items
- [ ] [HIGH] Fix X by YYYY-MM-DD
- [ ] [MEDIUM] Refactor Y next sprint

## Notes
(observasi atau catatan bebas)
```

---

## 7. Hubungan dengan dokumen lain

Health Check Protocol **tidak menggantikan** Project Memory yang sudah ada — dia melengkapi:

- **`07_known_issues.md`** — finding CRITICAL/HIGH di-promote ke sini dengan tag `[health-check]`. Sebaliknya, kalau ada known issue yang resolved, log run berikutnya akan reflect penurunan count.
- **`08_roadmap.md`** — action item dari finding bisa masuk ke roadmap kalau scope-nya lebih dari 1 sprint.
- **`11_decisions_log.md`** — kalau finding memicu architectural decision, di-log di sini juga dengan reference ke health check log.

---

## 8. Saat Health Check Protocol di-update

Dokumen Protocol ini (`00_PROTOCOL.md`) di-update **hanya kalau** ada perubahan struktural:
- Tambah/kurang kategori check
- Ubah severity ladder (jangan dilakukan tanpa pertimbangan matang — akan mempersulit trend tracking)
- Ubah cadence
- Tambah role baru

Setiap update tulis catatan di section bawah:

### Changelog

- **2026-06-05** — Lite Protocol baseline. 5 markdown + 3 scripts. Weekly cadence. (Hansen + Claude)
