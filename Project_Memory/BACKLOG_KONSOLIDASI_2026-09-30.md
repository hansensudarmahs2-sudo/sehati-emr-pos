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
| ~~**#51**~~ | ~~SOAP basi menghapus racikan PENDING~~ | **SELESAI** — commit `1ee1ad0` ("halaman SOAP basi tidak lagi menghapus data yang lahir sesudahnya"), sudah di `main`. Diverifikasi 2026-10-04, bukan disimpulkan. Pemeriksanya `scripts/cek_soap_basi.py`. ⚠ Dokumen ini sempat menyebutnya "prioritas tertinggi" berbulan-bulan setelah ia beres |
| ~~—~~ | ~~Racikan belum masuk laporan apoteker & top-produk~~ | **SELESAI 2026-09-30** (`a623e07`). Terbukti nyata: Cream K, Termisil cream, Nulyn 75mg tidak pernah muncul di top produk — hanya terpakai lewat racikan. Keputusan dr. Hansen: tampilkan dua-duanya, dipisah jelas. `qty_racikan` **tidak** dilebur ke `total_qty` (satuan berbeda) |
| — | **Penggabungan pasien ganda** | **Indeks uniknya SUDAH ADA** — migrasi `20260917_0100_pasien_nik_unique.py`; `nomor_ktp` pada tabel `pasien` ber-`non_unique=0`. Diverifikasi 2026-10-04. **Sisa: bersihkan kembar 217/218** — itu data di desktop/mini PC, bukan kode |
| ~~**F3**~~ | ~~Snapshot line-item Finance~~ | **SELESAI 2026-10-04** — `proses_bayar` langkah 3c menulis `transaksi_detail_tindakan` (qty, harga_satuan, diskon_item, subtotal, `bhp_satuan` dari `master_treatment.bhp_per_pakai_nominal`). Kolomnya **`bhp_satuan`**, bukan `hpp_satuan` seperti tertulis di sini. Selisih pembulatan dititipkan ke baris terakhir sehingga `SUM(diskon_item) == nominal_diskon_treatment` persis, **tanpa mengubah total yang dibayar pasien**. ⚠ Hanya berlaku untuk transaksi BARU — transaksi lama tidak punya jejak untuk direkonstruksi |
| — | **Kanal data mentah klinis untuk Oracle/Council AI** | **Pembagian peran (dr. Hansen 2026-09-30):** Sehati eMR-POS adalah BADAN UTAMA — ia **tidak menganalisis**, tugasnya **menyediakan data mentah siap olah**. Analisis dikerjakan modul terpisah berbasis Python (**Oracle**, **Council AI**) yang terus berkembang. *"tidak perlu respon terapi. yang terpenting data mentah saja di anamnesa juga cukup."* — jadi JANGAN tambah kolom penilaian terstruktur ke EMR.<br><br>Kanal ekspor SUDAH ADA (15 berkas), SOAP teks bebas sudah termasuk. **Yang belum ikut:** `kunjungan_diagnosa` (ICD10/ESTETIK — kode untuk mengelompokkan), `followup` (jejak kontrol: NO_ANSWER/CANCELLED — untuk melihat drop case), `kunjungan_racikan`, alergi, penyakit kronis, antropometri. Tanpa dua yang pertama, modul analisis menerima **narasi tanpa kode dan tanpa jejak kontrol** — persis dua hal yang dibutuhkan untuk menilai kasus membaik atau hilang.<br><br>⚠ Sekalian **pisahkan paket klinis dari `finance_pack`**. `medical_soap_raw` sekarang menumpang paket keuangan; berkas itulah yang hampir ter-rsync ke server dan yang dibersihkan dari riwayat git 2026-09-29. Data klinis dan keuangan butuh hak akses serta jalur keluar yang berbeda. |
| — | **Laporan kasus terbanyak (top diagnosa)** | [dr. Hansen 2026-09-30] *"icd sudah ada, diagnosa internal sudah ada, yang belum ada adalah laporan kasus terbanyak baik estetik maupun medis."* Datanya SUDAH tersedia di `kunjungan_diagnosa` (`sistem_snapshot` = ICD10/ESTETIK, `kode_snapshot`, `nama_snapshot`, `is_primer`) — **tidak butuh migrasi**. Dipisah dua bagian: medis (ICD10) & estetik (JD-xxx). **Perlu diputuskan lebih dulu:** hitung SEMUA diagnosa per kunjungan, atau hanya yang `is_primer`? Pasien dengan 3 diagnosa akan terhitung 3 kali kalau semua dipakai — angkanya jadi jawaban atas pertanyaan yang berbeda |
| — | Banner "Mode Ubah Konsul" menyesatkan untuk diagnosa | Kosmetik tapi membingungkan pengguna |

## 3. Higiene & utang teknis

| ID | Item | Catatan |
|---|---|---|
| ~~**D2**~~ | ~~Higiene folder E:~~ | **SELESAI 2026-09-30 — lihat §11 di bawah.** Temuan tak terduga: monolit legacy memuat **sandi DB yang masih aktif**, ter-commit sejak commit pertama |
| ~~**A7**~~ | ~~Berkas duplikat usang~~ | **SUDAH BERES** — diperiksa 2026-10-04 di klon bersih: tak satu pun dari `master.py.bak_restored`, `kunjungan.py.new`, `1`, `exit`, `debug_kunjungan.py`, `fix_timezone_tindakan.py` ada di disk maupun di `git ls-files`. ❓ dicoret |
| **F7** | Dead-code sweep ~13 fungsi | Report-only; periksa niat + test per fungsi, jangan hapus buta |
| **F5** | `_create_pending_membership_history_if_needed` tak tersambung | Diputuskan: buang atau sambungkan |
| **D1** | Panduan deploy lama usang | Guide systemd+nginx+Certbot sudah digantikan Docker+Tailscale. Tandai obsolete, rapikan runbook upgrade/rollback di README-DOCKER-MINIPC |
| — | `datetime.utcnow()` deprecated | **❓ terjawab 2026-10-04: BELUM rusak di 3.14.** Diuji di Python 3.14.4 — masih jalan, hanya `DeprecationWarning` ("scheduled for removal in a future version"). 9 pemakaian di `sehati_clinic/`. Produksi `python:3.11-slim`, jadi tidak mendesak — tapi jadi mendesak kalau image dinaikkan. Ganti ke `datetime.now(datetime.UTC)` |

## 4. Gerbang keamanan (dipicu sebelum data pasien asli masuk)

| ID | Item | Catatan |
|---|---|---|
| ~~**S1**~~ | ~~CSP + HSTS header~~ | **SEBAGIAN BESAR SUDAH ADA sejak `adb0459`** — diperiksa 2026-10-04, bukan disimpulkan dari catatan. CSP **aktif & menegakkan** dan terbukti tidak memblokir apa pun; HSTS terpasang & terbukti jalan tapi masih mati. Sisa: nyalakan HSTS di `.env` mini PC + hapus `'unsafe-inline'`. Lihat `S1_CSP_HSTS.md` |
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

**Diperbarui 2026-10-04.** Urutan aslinya (ditulis 09-30) sudah terlampaui hampir
seluruhnya — butir 2–5 semuanya selesai. Dicatat apa adanya karena daftar yang tidak
pernah dicoret adalah bagaimana sebuah dokumen berhenti dipercaya.

| # | Butir asli | Status |
|---|---|---|
| 1 | Smoke test mini PC | ⬜ **masih terbuka** — R8/R9 live di sana tapi belum pernah diuji |
| 2 | #51 SOAP basi | ✅ `1ee1ad0` |
| 3 | D2 higiene folder E: | ✅ 2026-09-30, lihat §11 |
| 4 | Racikan di laporan | ✅ `a623e07` |
| 5 | S1 CSP/HSTS | ✅ sebagian besar sudah ada sejak `adb0459`; sisa = nyalakan HSTS di mini PC + hapus `'unsafe-inline'`. Lihat `S1_CSP_HSTS.md` |
| 6 | Item besar (F1/F2/F3) | ⬜ |

**Urutan berikutnya:**

1. **Smoke test mini PC** — satu-satunya sisa dari daftar lama, dan masih sama
   alasannya: menutup R8/R9 sebelum menumpuk pekerjaan baru.
2. **Ekspor paket klinis Tahap B ujung-ke-ujung** — kodenya selesai 2026-10-04 tapi
   ZIP + enkripsi age belum pernah dijalankan dengannya. Butuh `BACKUP_RECIPIENT`,
   jadi **harus di desktop**.
3. **F3 snapshot line-item Finance** — satu-satunya item terbuka yang **merusak data
   secara diam-diam seiring waktu**: `transaksi_detail_tindakan` tidak pernah ditulis,
   jadi setiap transaksi yang lewat hari ini tidak meninggalkan jejak line-item dan
   tidak bisa diambil kembali besok.
4. Baru item besar lain (F1/F2/F4) sesuai kebutuhan operasional.

**Semua yang mengubah skema atau konfigurasi besar: minta persetujuan dr. Hansen dulu.**

---

## 11. D2 — dikerjakan 2026-09-30

**Temuan tak terduga:** `Current python code main_api.txt` (monolit pra-refactor) memuat
`password="..."` yang **sidik jarinya cocok dengan `sehati_clinic/.env` yang sedang
berjalan** — kredensial aktif, ter-commit sejak commit pertama. Ditemukan sehari SETELAH
pembersihan PHI, karena pembersihan itu mencari data pasien, bukan kredensial.

**Keputusan dr. Hansen:** ganti sandinya, jangan tulis ulang riwayat lagi. Sandi yang
sudah diganti membuat apa pun di riwayat git tidak berguna — dan itu satu-satunya cara
yang tuntas, karena GitHub tetap menyimpan objek lama sementara dan klon lama di mesin
lain tidak bisa dijangkau.

**Yang dikerjakan:**
- Sandi MySQL desktop diganti lewat `SET PASSWORD` + perbarui `.env`. Nilainya **tidak
  pernah ditampilkan**; `MYSQL_PWD` dipakai alih-alih `-p<sandi>` supaya tidak muncul di
  daftar proses.
- Diperiksa dulu, bukan diasumsikan: **hanya `.env`** yang menyimpan nilainya. Alembic
  membacanya dinamis lewat `migrations/env.py`; berkas lain semuanya `*.example`.
- **Mini PC TIDAK terekspos.** Sidik jari sandinya dibandingkan dengan sandi lama desktop
  — berbeda. Ia dibuat sendiri saat deploy, bukan disalin. Tidak disentuh sama sekali.
- Berhenti melacak + hapus dari disk: monolit legacy, `ziFKtzj6` (ternyata arsip ZIP
  berisi salinan 221 berkas kode), `sehati_clinic_template/` (+ `.env` sendiri), dan
  **17 dump SQL (13,1 MB)**.

**⚠ Yang hilang permanen, dan itu disengaja.** Database desktop sudah di-wipe 18
September (tersisa 5 pasien sejak 18 Sep). Dump yang dihapus memuat **~424 pasien dan
~700 kunjungan Maret–Juni** — satu-satunya salinan yang tersisa. Backup harian terenkripsi
hanya melindungi mini PC, yang isinya data dummy. Saya periksa dan laporkan ini SEBELUM
penghapusan; dr. Hansen memilih tetap menghapus dengan sadar. **Jangan cari data itu
lagi — ia tidak ada.**

**Berkas SQL yang DIPERTAHANKAN** (kode, bukan dump): `migrations_sql/*.sql` (11 berkas)
dan `deploy/schema_only.sql`.

**Sisa yang belum tuntas:** hapus `sehati_clinic/.env.bak.*` setelah aplikasi terbukti
jalan dengan sandi baru — berkas itu memuat sandi lama.
