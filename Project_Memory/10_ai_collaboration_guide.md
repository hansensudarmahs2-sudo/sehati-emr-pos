# AI Collaboration Guide

> Cara AI lain (OpenAI, Ollama, atau AI baru) berinteraksi dengan project ini.

---

## Konteks: Multi-AI Setup

**Setup dr. Hansen:**

```
┌──────────────────┐
│   dr. Hansen     │  (Product Designer & User Tester)
│   Domain Expert  │
└────────┬─────────┘
         │
         │ supervise & feedback
         │
   ┌─────┴─────────────────────────────────────────┐
   │                                                │
   ▼                                                ▼
┌────────────────────┐                  ┌─────────────────────────┐
│  Claude (active)   │  ◄─── review ────│  OpenAI GPT (reviewer) │
│  Lead Developer    │                  │  Independent QA        │
│  Implement code    │                  │  Catch blind spots     │
└────────────────────┘                  └─────────────────────────┘
   │
   │ ▲
   │ │
   ▼ │ review (privacy-sensitive)
┌─────────────────────────┐
│  Ollama (local AI)      │
│  On-device review       │
│  For sensitive data     │
└─────────────────────────┘
```

**Filosofi:** Setiap AI punya bias training yang berbeda. Multi-AI review **bukan duplication**, tapi **complement**.

---

## Untuk Claude (Active Developer)

**Saya yang sedang mengembangkan project ini.** Tanggung jawab:

1. **Tulis kode** sesuai standar (`05_coding_style.md`) dan business logic (`06_business_logic.md`).
2. **Refactor bertahap** kode dokter dari `../Current python code main_api.txt`.
3. **Lapor ke dr. Hansen** progress per chunk + tunggu konfirmasi sebelum lanjut.
4. **Update `Project_Memory/`** saat ada perubahan signifikan (keputusan teknis, schema change, dll).
5. **Buat code untuk di-review** oleh AI lain — kasih komentar jelas, hindari "smart" code yang sulit di-audit.

### Kalau ada konflik antara saya & AI reviewer

1. Baca review-nya seriously (asumsi mereka punya valid point).
2. Kalau setuju — implement fix.
3. Kalau tidak setuju — diskusi dengan dr. Hansen. **Domain expert yang putuskan.**
4. Document keputusan di `11_decisions_log.md`.

---

## Untuk OpenAI GPT (Independent Reviewer)

**Tanggung jawab Anda:** Independent code review, catch blind spot, validate architecture decision.

### Apa yang harus Anda lakukan

1. **Baca dokumen ini berurutan:**
   - `01_project_overview.md` (5 menit) — konteks bisnis.
   - `02_architecture.md` (10 menit) — struktur kode.
   - `06_business_logic.md` (15 menit) — aturan klinik dr. Hansen.
   - `07_known_issues.md` (5 menit) — apa yang sudah saya tahu.
2. **Review code** di `../sehati_clinic/app/` dengan lens:
   - **Logic correctness** — apakah implementasi benar-benar match business rules?
   - **Security** — apakah ada vulnerability yang missed?
   - **Performance** — ada N+1 query? Race condition?
   - **Maintainability** — apakah pemula bisa baca kode ini?
3. **Output review dalam format ini** (supaya dr. Hansen mudah baca):

```markdown
# Code Review by OpenAI GPT
Date: YYYY-MM-DD
Module reviewed: app/services/pasien_service.py

## Critical Issues (must fix sebelum production)
- [Issue 1] ...

## Important (sebaiknya fix di Phase 1)
- [Issue 1] ...

## Suggestions (optional improvement)
- [Suggestion 1] ...

## Things I confirm look correct
- ...

## Questions for dr. Hansen
- ...
```

### Apa yang TIDAK perlu Anda lakukan

❌ Jangan langsung rewrite kode — kasih saran, biar Claude yang implement (single source of authority untuk kode).
❌ Jangan suggest tech stack change tanpa alasan kuat (dr. Hansen sudah commit ke FastAPI + HTMX).
❌ Jangan minta data sensitif (password, JWT secret, dll) — itu di Ollama review aja.
❌ Jangan ubah business logic tanpa konfirmasi dr. Hansen.

### Apa yang saya minta khusus

Saya (Claude) punya beberapa **blind spot known**:

1. **Race conditions** — saya cenderung optimistic. Mohon Anda strict di concurrent access patterns.
2. **Edge cases di datetime/timezone** — saya kadang skip handling for testing. Mohon cek timezone Asia/Jakarta consistency.
3. **Bias toward fewer files** — saya cenderung group multiple class di 1 file. Mohon comment kalau menurut Anda file harus di-split.
4. **Bahasa Indonesia error messages** — saya English-native. Mohon cek apakah pesan error natural dalam bahasa Indonesia.

---

## Untuk Ollama (Local Privacy-Sensitive Review)

**Tanggung jawab Anda:** Review yang sensitif (mengandung PII pasien sample, security config, dll) tanpa data leave dr. Hansen's machine.

### Use Case Spesifik

1. **Audit kode security** — `app/core/security.py`, `app/core/deps.py`. Cek bcrypt config, JWT secret handling, RBAC implementation.

2. **Review data handling** — kapanpun ada PII (nomor KTP, alamat, tanggal lahir pasien). Apakah ada accidental logging atau exposure?

3. **Test data review** — fixture pytest yang mungkin ada hardcoded credentials.

4. **Validate prompts AI** — di Phase 3 saat ada Gemini integration, prompt yang akan dikirim mungkin contain PII. Audit prompt construction.

### Output Format (Sama dengan OpenAI)

Pakai template di section OpenAI di atas.

---

## Untuk AI Baru / Unknown

Bila Anda AI yang baru pertama kali touch project ini dan tidak yakin role Anda:

1. **Default behavior: jadi reviewer, BUKAN developer.** Kasih saran, jangan langsung edit kode.
2. **Identify yourself.** Bilang dokter "saya GPT-4 / Claude Sonnet / Llama / dll" supaya dia track contribution.
3. **Baca `01_project_overview.md` & `06_business_logic.md` minimum.**
4. **Tanya scope review.** Misalnya: "Saya akan review module X. Boleh konfirmasi scope?"

---

## Files yang Hanya Boleh Diubah oleh Claude

Untuk konsistensi, hanya **Claude (active developer)** yang boleh edit:

- `../sehati_clinic/app/**` — semua kode aplikasi
- `../sehati_clinic/tests/**` — test
- `../sehati_clinic/migrations/**` — Alembic migrations
- `../sehati_clinic/pyproject.toml` — dependencies
- `../migrations/sql/**` — file SQL legacy

**AI lain hanya boleh:**
- Read & analyze code
- Tulis review document terpisah (jangan edit Project_Memory langsung)
- Suggest changes via Pull Request style: text dengan "diff" annotation

---

## Files yang Boleh Diubah Multi-AI

- `Project_Memory/07_known_issues.md` — append bugs found
- `Project_Memory/11_decisions_log.md` — append keputusan baru
- Document review baru (`Project_Memory/reviews/openai_review_YYYY-MM-DD.md`, dll)

---

## Konflik Resolution

Bila 2 AI saran berbeda:

1. **dr. Hansen yang putuskan** (domain expert).
2. Document keputusan di `11_decisions_log.md` dengan **alasan**.
3. Update `Project_Memory/` files affected.

---

## Versi Konteks (Versioning)

`Project_Memory/` ini akan ter-track di git. Setiap commit di project ini akan reflect state context saat itu.

Bila Anda AI baru reading di masa depan, **selalu cek `git log`** untuk lihat update terakhir:

```bash
git log --oneline -- Project_Memory/
```

---

## Sample Workflow Multi-AI

### Scenario: Review Module Pasien Service

**Day 1 (Claude):**
- Implement `app/services/pasien_service.py`
- Tulis test di `tests/unit/test_pasien_service.py`
- Commit ke git
- Update `Project_Memory/07_known_issues.md` jika ada gaps

**Day 2 (OpenAI Review):**
- Read `Project_Memory/06_business_logic.md` & `02_architecture.md`
- Open `app/services/pasien_service.py`
- Cross-reference logic dengan business rules
- Write review di `Project_Memory/reviews/openai_pasien_service_2026-05-20.md`
- Highlight 2 critical issues + 3 suggestions

**Day 3 (Ollama Review):**
- Read PII handling di `pasien_service.register_pasien_baru`
- Audit apakah nomor_ktp ter-log atau ter-expose somewhere
- Write review di `Project_Memory/reviews/ollama_pasien_service_2026-05-21.md`

**Day 4 (dr. Hansen + Claude):**
- dr. Hansen baca 2 review
- Konfirmasi mana yang valid untuk fix
- Claude implement fix
- Update `Project_Memory/11_decisions_log.md`

---

## Sample Review Document Template

Saved at `Project_Memory/reviews/<ai_name>_<scope>_<YYYY-MM-DD>.md`:

```markdown
# Code Review: <Scope>

**Reviewer:** OpenAI GPT-4 / Ollama Llama 3 / etc
**Date:** 2026-05-20
**Files reviewed:** app/services/pasien_service.py
**Time spent:** ~30 minutes

---

## Summary
2 critical, 3 important, 5 suggestions

## 🔴 Critical Issues

### C1. Race condition di generate_next_no_rm()
**Location:** `pasien_repo.py:55-85`
**Issue:** FOR UPDATE lock cuma SELECT terakhir. Kalau 2 transaksi parallel SELECT same row before either INSERT, both akan dapat next_counter sama.
**Suggestion:** Pakai dedicated counter table dengan FOR UPDATE, atau pakai `INSERT ... ON DUPLICATE KEY UPDATE`.
**Severity:** High (kemungkinan kolisi rendah tapi possible)

### C2. ...

## 🟡 Important Issues

### I1. Tidak ada validation untuk format `nomor_ktp`
...

## 🟢 Suggestions

### S1. Extract magic number `50` (default limit search) ke constant
...

## ✓ Looks Correct

- 1 transaksi atomik implementation di register_pasien_baru
- Soft delete pattern untuk alergi
- Repository / Service separation

## Questions for dr. Hansen

1. Apakah saya benar bahwa pasien tanpa tanggal lahir tidak bisa hitung BMI? Bagaimana di UI?
2. ...
```

---

## How to Onboard AI Baru ke Conversation Saya (Claude)

Bila dokter mau libatkan AI baru (misal Claude di sesi berikutnya yang fresh, atau AI lain) ke development active:

1. Bilang ke AI tersebut: **"Baca Project_Memory/00_README.md sampai 11_decisions_log.md sebelum touch code."**
2. Berikan context spesifik: "Kita sedang di Phase X, Minggu Y, sedang kerjakan module Z."
3. AI baru harus konfirmasi pahami konteks sebelum eksekusi.

Saya (Claude saat ini) komit untuk update Project_Memory tiap ada milestone penting supaya konteks fresh untuk AI berikutnya.
