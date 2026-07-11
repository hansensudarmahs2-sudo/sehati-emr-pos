# Session Workflow — Closing & Handoff Pattern

**Created**: 2026-06-12 malam  
**Status**: Standar tetap untuk semua sesi ke depan  
**Origin**: Diskusi dr. Hansen + Claude tentang B-013 cumulative context mitigation

---

## Tujuan

Memastikan transisi antar-sesi clean, context tidak terbawa berat, dan task berikutnya dimulai dengan fokus optimal.

---

## 3-Step Closing Workflow

### Step 1 — Housekeeping (Claude execute)
Saat user signal "closing sesi" atau task milestone selesai:

1. Update `08_roadmap.md` — append section sesi ini (yang diselesaikan + stats + outstanding)
2. Update `11_decisions_log.md` — kalau ada decision arsitektural baru (DEC-XXX)
3. Update `07_known_issues.md` — kalau ada bug pattern baru atau B-013 observation
4. Verify semua file: AST Python + Jinja templates clean

### Step 2 — List Pending Tasks (Claude execute)
Setelah housekeeping, Claude tampilkan:

```
📋 Pending Tasks (Berikutnya)

🟡 P2 — [task title 1]
   Effort: ~30m. Files: [list].
   Outline: [1-2 baris deskripsi]

🟢 P3 — [task title 2]
   Effort: ~1 sesi. Files: [list].
   Outline: [1-2 baris deskripsi]

🔵 P4 — [task title 3]
   Status: Blocked / Future / Tunggu external

Mana yang Bapak pilih untuk sesi berikutnya?
```

### Step 3 — User Pick + Claude Generate Handoff
User reply dengan task pilihan (e.g., *"P2 yang void cascade"* atau *"bukan keduanya, saya mau X"*).

Claude generate **handoff prompt** dalam format:

```
═══════════════════════════════════════════════════════════
SESSION HANDOFF — [Project Name]
From: [YYYY-MM-DD sesi sebelumnya] → To: Sesi berikutnya
═══════════════════════════════════════════════════════════

ROLE
[Singkat: siapa Claude, ke siapa, gaya bahasa]

PROJECT
- Stack: [tech stack]
- Folder: [absolute path]

READ FIRST (mandatory)
1. [MD file 1] → [section spesifik]
2. [MD file 2] → [DEC ID]
3. [MD file 3] → [section]

TASK HARI INI: [task title]
[1-2 paragraph deskripsi]

ACCEPTANCE CRITERIA
- [criterion 1]
- [criterion 2]
- [test case spesifik]

TARGET FILES (kemungkinan)
- [file 1]
- [file 2]

WORKING PATTERN
- [B-013 mitigations]
- [verify pattern]

EFFORT ESTIMATE: [time]

START SEQUENCE
1. Read MD references
2. Recon target files
3. Breakdown task + minta approval
4. Implement
5. Verify + housekeeping

Mulai dengan baca MD references, lalu kasih breakdown task → 
tunggu approval Bapak sebelum coding.
═══════════════════════════════════════════════════════════
```

User copy prompt ini → paste ke chat baru besok (atau sebagai soft-reset di chat yang sama).

---

## Cara Pakai Handoff Prompt

### Opsi A — Real New Chat (PREFERRED kalau Cowork support)
1. Klik **+ New Chat** di Cowork (atau `Ctrl+N`)
2. Pastikan project folder masih ke-select ("sehati-emr-pos")
3. Paste handoff prompt
4. Enter

**Pros**: Context benar-benar fresh = strike rate hampir 0.

### Opsi B — Soft Reset (kalau tidak bisa new chat)
1. Tetap di chat yang sama
2. Paste handoff prompt
3. Saya akan treat as fresh agent (re-read MD files)

**Pros**: Tetap bisa lanjut tanpa interrupt.  
**Cons**: Context lama masih di background, strike rate sedikit lebih tinggi dari Opsi A.

---

## Kapan Closing Sesi?

Indikator user perlu closing:
- 1 milestone besar selesai (e.g., Phase 2 done)
- Sesi sudah > 2 jam aktif kerja
- Strike rate mulai naik (>2 strikes berturut-turut)
- User mau istirahat / break makan / besok lanjut

Indikator Claude initiate closing suggestion:
- Task list section "in_progress" sudah kosong
- 3+ feature/fix selesai dalam 1 sesi
- Project_Memory perlu update (banyak undocumented decisions)

---

## Example: Penerapan untuk Sesi 2026-06-12 Malam

Sesi ini selesai dengan:
- ✅ #362 Phase 2 (P2-#1/#2/#3 + FIX) complete
- ✅ LOG-1 audit + NOTA-C nota complete
- ✅ Housekeeping 3 MD files complete

Pending tasks untuk sesi berikutnya: (sees `08_roadmap.md` section terakhir)
1. 🟡 P2 — Void Cascade decrement_kuota_terpakai (~30m)
2. 🟢 P3 — DEC-065 Phase 1 prasyarat (~1-2 sesi)
3. 🔵 P4 — #366 Finance Viewer Phase 1 (blocked: tunggu akuntan)

User pick → handoff prompt generated → done.

---

## Notes

- File ini "evergreen" — jangan dihapus, update kalau workflow berubah
- Prefix `_` (underscore) menandakan ini file meta-workflow, bukan project data
- Reference dari `08_roadmap.md` kalau ada perubahan workflow
