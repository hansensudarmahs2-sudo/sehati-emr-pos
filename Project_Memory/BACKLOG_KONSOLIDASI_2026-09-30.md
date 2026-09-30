# BACKLOG KONSOLIDASI — 2026-09-30

Disusun sebelum pindah ke Claude Code. Menggabungkan `TODO_SEHATI.md` (Juli),
`BACKLOG_TERKUBUR_2026-09.md` (September), `HANDOFF_2026-09-22.md` §6, dan temuan sesi
29–30 September.

> **Dokumen lama yang MENYESATKAN kalau dibaca mentah:**
> `07_known_issues.md` terakhir diperbarui **4 Juni 2026**. Banyak isinya sudah beres
> (rate-limit, CSRF, backup otomatis, HTTPS) tapi masih tertulis terbuka. **Jangan pakai
> berkas itu sebagai daftar tugas.** Yang paling mutakhir: dokumen ini +
> `BACKLOG_TERKUBUR_2026-09.md`.

> **Tanda ❓ = perlu diverifikasi di mesin sebelum dikerjakan.** Saya menyimpulkannya dari
> dokumen, bukan dari memeriksa. Pelajaran mahal sesi ini: jangan simpulkan ketiadaan
> fitur dari catatan lama.

---

## 1. GERBANG — bukan antrean

**Hardening #33–36 dan daftar keamanan S1–S8 BUKAN nomor urut.** Keputusan dr. Hansen
(2026-09-20, ditegaskan 09-22): pengembangan fungsi jalan terus selama sistem masih uji
coba internal dengan pasien dummy. Seluruh hardening harus tuntas **sebelum data pasien
asli masuk** — bukan "setelah task nomor sekian".

Saat ini: **masih uji coba internal, belum ada database pasien asli.**

---

## 2. Perbaikan — bisa merugikan klinik

| ID | Item | Catatan |
|---|---|---|
| **#51** | **SOAP basi menghapus racikan PENDING** | Satu-satunya yang bisa menghilangkan tagihan. Ditunda atas keputusan dr. Hansen; sekarang prioritas tertinggi |
| — | **Racikan belum masuk laporan** apoteker & top-produk | Laporan menyesatkan: racikan tidak terlihat sama sekali |
| — | **Penggabungan pasien ganda** | Kembar 217/218 perlu dibersihkan, lalu pasang `UNIQUE INDEX ux_pasien_nomor_ktp`. Perlu desain terpisah |
| **F3** | Snapshot line-item Finance | `transaksi_detail_tindakan` tak pernah ditulis; `hpp_satuan` kosong. Prasyarat modul Finance untuk margin/COGS |
| — | Banner "Mode Ubah Konsul" menyesatkan untuk diagnosa | Kosmetik tapi membingungkan pengguna |

## 3. Higiene & utang teknis

| ID | Item | Catatan |
|---|---|---|
| **D2** | **Higiene folder E:** | `sehati_clinic_template/` punya `.env` + `backup_*.sql` sendiri; tumpukan `backup_*.sql` di dalam `sehati_clinic/`; `Current python code main_api.txt` (monolit legacy 83KB); artefak nyasar `ziFKtzj6`. Di LUAR git, tapi di folder tersinkron |
| **A7** | Berkas duplikat usang | `master.py.bak_restored`, `kunjungan.py.new`, berkas nyasar (`1`, `exit`, `debug_kunjungan.py`, `fix_timezone_tindakan.py`) ❓ |
| **F7** | Dead-code sweep ~13 fungsi | Report-only; periksa niat + test per fungsi, jangan hapus buta |
| **F5** | `_create_pending_membership_history_if_needed` tak tersambung | Diputuskan: buang atau sambungkan |
| **D1** | Panduan deploy lama usang | Guide systemd+nginx+Certbot sudah digantikan Docker+Tailscale. Tandai obsolete, rapikan runbook upgrade/rollback di README-DOCKER-MINIPC |
| — | `datetime.utcnow()` deprecated | Akan rusak di Python 3.14+ ❓ |

## 4. Gerbang keamanan (dipicu sebelum data pasien asli masuk)

| ID | Item | Catatan |
|---|---|---|
| **S1** | CSP + HSTS header | Dulu menunggu HTTPS; HTTPS Tailscale sudah ada → **bisa dikerjakan sekarang** |
| **S2** | pip-audit terjadwal Docker-aware | Unit systemd yang ada berbasis native (`/opt`, `User=sehati`); mini PC memakai Docker |
| **S3** | Least-privilege DB + immutability `audit_log` | GRANT app hanya INSERT/SELECT di `audit_log`; user MySQL non-root |
| **S4** | Enkripsi at-rest (LUKS) disk mini PC | Belum terverifikasi ❓ |
| **S5** | Kebijakan password ≥12 + cek bocor | Sekarang minimal 8 |
| **S6** | 2FA TOTP Owner/Superadmin | Dokter TIDAK (friction). Masih dipertimbangkan |
| **S7** | Auth guard `api/v1/finance.py` | Aman sekarang karena semua endpoint 501. **WAJIB dipasang di PR yang sama** saat modul Finance dibangun |
| **S8** | Baca PHI hanya di-gate login, tanpa batas peran | Tiap staf bisa membuka rekam penuh pasien mana pun. Perlu keputusan eksplisit dr. Hansen, dicatat |
| **B0** | `JWT_SECRET_KEY` produksi kuat | ❓ Mini PC sudah boot `APP_ENV=production` dan boot-guard A6 menolak tanpa ini — **kemungkinan besar sudah**, tapi verifikasi |
| — | Klasifikasi data PII (V1.8) | Dokumen `KLASIFIKASI_DATA_V1.8.md` ada — periksa apakah sudah lengkap ❓ |
| — | Pre-launch checklist (firewall, swap, monitoring) | |

## 5. Fitur belum dibangun

| ID | Item | Catatan |
|---|---|---|
| **F1** | +Antrian kontekstual | "Antri Tindakan" belum punya wadah tindakan prabayar/terjadwal; "Antri Bayar" belum nonaktif saat nihil tagihan. Perlu design doc |
| **F2** | Komisi Fase 2 | Skema UNCAPPED / THRESHOLD_HALF / THRESHOLD_GUARANTEED + config per dokter + clawback VOID lintas periode |
| **F4** | Modul Absensi + work-session (AT300) | Batasi akses eMR-POS di luar jam kerja. Modul besar, perlu desain |
| **F6** | Tenant-scoping `klinik_id` | Siapkan SEBELUM multi-klinik. Nyambung ke `master_klinik_config` → `master_klinik` |
| **F8** | Booking Fase 2 | Deposit/DP, reminder, booking online mandiri. PARKIR |
| **M2–M5** | Membership CS | |
| — | P-L6c: tindakan potong BHP → FEFO bahan (#62) | DITUNDA |
| — | Mobile-friendly alur foto perawat/dokter | |
| — | Filter aksi=VIEW di Audit Log Viewer | Kecil |
| — | Relabel status PO "Partial" → "Berjalan" | dr. Hansen: SKIP untuk sekarang |

## 6. Integrasi (butuh cloud/perangkat keras)

| ID | Item |
|---|---|
| **C1–C6** | Konektor DermAI + Antropometri: finalkan kontrak + `return_url`; kolom DB `is_acne`/`acne_severity`/`dermai_case_id`/`antro_assessment_id`; service konektor; tombol di SOAP; endpoint write-back penyakit kronis; config `.env` + signed-url |
| — | Konektor Finance pihak ketiga (Accurate) |
| **D3** | Tuning MySQL container (max_connections, buffer pool, wait_timeout>280s) — minor untuk skala klinik tunggal |

## 7. Parkir / jauh

- Landing page + QR nomor antrian — setelah live-run ≥6 bulan
- Rename `master_klinik_config` → `master_klinik` multi-cabang — tunggu cabang ke-2
- Queue orchestration L2–L5 = **SOP offline, bukan perangkat lunak**
- FK-L6 AP/hutang faktur → dipindah ke modul Finance

---

## 8. Menunggu dr. Hansen (bukan pekerjaan kode)

1. **Smoke test mini PC** — tebus resep 3 mode, racikan di tebus resep, sisakan-untuk-nanti.
   R8+R9 sudah live di mini PC tapi **belum pernah diuji di sana**.
2. Pasang hook gerbang PHI:
   `ln -sf ../../scripts/cek_phi_tracked.sh .git/hooks/pre-commit`
3. Push commit terakhir sesi ini ke `origin` + `core`.

---

## 9. SUDAH SELESAI — jangan dikejar lagi

Etiket racikan (pihak ketiga, ditutup) · #41 kasir/apotek tambah item (digantikan modul
apotek R1–R9) · #54 serah & refund per item · #18 audit integritas ID pasien · #7
follow-up reminder · backup terjadwal + enkripsi + salinan luar mesin · deploy mini PC
Docker+Tailscale · rate limiting · CSRF · pembersihan PHI dari riwayat git · gerbang PHI
pra-commit.

---

## 10. Urutan yang saya sarankan

1. **Smoke test mini PC** — menutup R8/R9 sebelum menumpuk pekerjaan baru
2. **#51** — satu-satunya yang bisa menghilangkan tagihan
3. **D2** higiene folder E: — murah, menutup `.env` + dump SQL yang menganggur
4. **Racikan di laporan** — laporan yang menyesatkan lebih berbahaya daripada laporan yang tidak ada
5. **S1 CSP/HSTS** — sekarang bisa karena HTTPS Tailscale sudah ada
6. Baru item besar (F1/F2/F3) sesuai kebutuhan operasional

**Semua yang mengubah skema atau konfigurasi besar: minta persetujuan dr. Hansen dulu.**
