# CLAUDE.md — Sehati eMR-POS

Baca ini lebih dulu. Isinya yang dibutuhkan di 5 menit pertama; sisanya ada di
`Project_Memory/` (lihat §9).

**Apa ini:** rekam medis elektronik + kasir untuk **JoDerma**, klinik dermatologi &
venereologi di Jemur Andayani, Surabaya. Dipakai sungguhan oleh FO, dokter, perawat,
kasir, dan apoteker.

**Siapa yang Anda ajak bicara:** dr. Hansen Sudarma — dokter dan pemilik klinik,
**bukan programmer**. Ia merancang, menguji, dan memutuskan; Anda menulis kodenya.
Bahasa Indonesia, kasual. Jelaskan dampak, bukan mekanisme.

---

## 1. Aturan yang tidak boleh dilanggar

1. **Uji di UI desktop dulu, baru deploy ke mini PC.** Selalu. Tanpa pengecualian.
2. **Perintah CLI satu per satu**, tunggu hasilnya, baru lanjut. Jangan merangkai
   lima langkah dalam satu blok — kalau gagal di tengah, tidak ketahuan yang mana.
3. **Minta persetujuan sebelum mengubah skema DB atau membuat modul baru.**
   Tunjukkan rancangannya dulu.
4. **Jangan deploy saat jam operasional klinik.** `docker compose up -d --build`
   mematikan aplikasi beberapa menit; meja FO, kasir, apotek berhenti total.
   Persiapan (backup, push, rsync) aman kapan saja — hanya rebuild yang menunggu.
5. **Periksa dulu, baru bicara.** Jangan menyatakan ada bug/risiko sebelum membaca
   kodenya. Tiga klaim risiko pernah dibuat tanpa diperiksa dan ketiganya salah
   (lihat `DESAIN_51_SOAP_BASI.md` §10). Salah menuduh membuang waktu dr. Hansen
   dan menggerus kepercayaan pada peringatan yang benar.
6. **Akui kesalahan sendiri secara eksplisit.** Banyak perbaikan di proyek ini lahir
   dari kesalahan yang diakui, bukan ditutupi.

---

## 2. Menjalankan

**Dev** (WSL/Ubuntu di desktop dr. Hansen — pakai `python3`, bukan `python`):

```bash
cd /mnt/e/Claude/Projects/sehati-emr-pos/sehati_clinic
source .venv/bin/activate
uvicorn app.main:app --reload --port 8001     # http://localhost:8001
mysql -e "SQL"                                # ~/.my.cnf sudah berisi kredensial
alembic upgrade head
```

**Laptop** (workspace sementara, `~/JoDerma/sehati-emr-pos`) — **aplikasi jalan di
dalam container**, bukan venv. Ubuntu 26.04 bawaannya Python 3.14 dan `python3.11` tidak
ada di apt, sedangkan produksi `python:3.11-slim`; selisih tiga versi membuat smoke test
tak bisa dipercaya. Jadi:

```bash
cd ~/JoDerma/sehati-emr-pos/sehati_clinic
docker compose -f docker-compose.yml -f deploy/compose.laptop.yml up -d --build
docker compose exec sehati-app python -m scripts.cek_nik   # pemeriksa §5: DI DALAM container
```

⚠ Di laptop, `python -m scripts.…`, `alembic`, dan `mysql` di shell host **akan gagal**
(tidak ada dependensi, tidak ada MySQL). Selalu lewat `docker compose exec`.
⚠ **Laptop TIDAK pernah deploy ke mini PC.** Rsync hanya dari desktop — alasannya di
`Project_Memory/ALUR_DUA_MESIN.md` §1.

**Produksi** — mini PC klinik, Docker Compose:

```bash
ssh joderma-jemur@joderma-jemur               # WAJIB tulis user@host
cd /srv/sehati && docker compose up -d --build
```

Akses: `https://joderma-jemur.tail730d60.ts.net:8443` (Tailscale serve).
Entrypoint menjalankan `alembic upgrade head` otomatis saat container start.

**Deploy** (dari desktop):

```bash
./deploy/push-ke-minipc.sh            # dry-run dulu, SELALU
./deploy/push-ke-minipc.sh --jalan
```

⚠ Skrip itu memakai `rsync --checksum`. **Jangan pernah melepasnya**: riwayat git
pernah ditulis ulang (pembersihan PHI 2026-09-27) sehingga mtime seluruh pohon
berubah — tanpa `--checksum`, dry-run melaporkan semua berkas dan jadi tak berguna.

---

## 3. Tumpukan teknologi

FastAPI · SQLAlchemy 2.0 (`Mapped`/`mapped_column`) · Pydantic 2 · MySQL (pymysql) ·
Jinja2 · HTMX 1.9.12 · Alembic · Tom Select · **Tailwind DIKOMPILASI LEBIH DULU**.

Lapisan: `routes → services → repositories → models`. Logika bisnis di **service**,
bukan di route.

---

## 4. Jebakan berulang — ini yang paling mahal di proyek ini

### 4.1 Satu hal, dua arti / dua penulis

Pola yang paling sering menggigit. Selalu tanyakan: *siapa lagi yang memakai ini, dan
dengan asumsi apa?*

| Kejadian | Gejalanya |
|---|---|
| `save_kunjungan_racikan` hanya `flush()`, tidak `commit()` | Di alur dokter aman (ada commit menyusul); di alur apotek racikan **lenyap tanpa error** |
| `transaksi_kasir` punya `id_pasien` SENDIRI di samping `id_kunjungan` | Pindahkan `kunjungan` saja → rekam medis menyatu, laporan keuangan tetap terpecah, **tanpa gejala** |
| Draf SOAP apoteker vs SOAP dokter di tabel yang sama | Halaman basi menghapus data yang lebih baru |
| `_produk_stok_sudah_dipotong`, `id_resep_asal` | Sama polanya |
| `REPORTS_ROLES` dipakai ulang untuk laporan klinis | Laporan tanpa uang ikut terkunci oleh aturan yang dibuat untuk data uang |
| ~~`DISERAHKAN` dipakai sebagai bukti "stok sudah dipotong"~~ | **DIPAGARI 2026-10-04.** Dua arti untuk dua penulis: bagi apoteker `DISERAHKAN` artinya "obat di tangan pasien", bagi penjaga void artinya "lot sudah keluar, jadi boleh dikembalikan". Penyerahan dengan stok kurang **berhasil** dan memasang `DISERAHKAN` tanpa satu lot pun terpakai — lalu void **menciptakan** lot `VOID-RETURN` berisi barang yang tak pernah ada, dan FEFO membagikannya. Sekarang di skema per-item void hanya memulihkan sebanyak yang dibuktikan jejak `kunjungan_lot_terpakai`. **Stok minus tetap diizinkan — yang diperbaiki jejaknya, bukan filosofinya.** Pemeriksanya: `python -m scripts.cek_serah_tanpa_lot`. `AUDIT_ALUR_UANG_2026-10-04.md` Temuan 30 |
| **FEFO menyodorkan lot KEDALUWARSA lebih dulu** | Query FEFO tidak menyaring `tgl_ed`, dan karena "ED terdekat keluar dulu" lot yang sudah lewat ED ada di urutan PALING ATAS. Terbukti. Yang menahannya cuma apoteker yang membaca ED di layar — dan layarnya **tidak menandai** tanggal yang sudah lewat. TERBUKA — `AUDIT_ALUR_UANG_2026-10-04.md` Temuan 29 |
| **Nota dicetak dari harga MASTER, bukan yang ditagih** | `prepare_nota_context` menggabungkan ke `MasterTreatment.harga`/`MasterProduk.harga_jual` untuk BARIS, tapi mengambil TOTAL dari transaksi — dua sumber kebenaran di satu lembar. Tindakan kuota mencetak **baris Rp 500.000 dengan total Rp 0**. Snapshot-nya sudah ada di `transaksi_detail_*`. TERBUKA — `AUDIT_ALUR_UANG_2026-10-04.md` Temuan 27 |
| ~~Void diterima walau racikan/resep sudah DISERAHKAN~~ | **DIPAGARI 2026-10-04** (`_pagari_void_item_diserahkan`). Dulu: transaksi jadi VOID tapi barangnya tetap `DISERAHKAN` — laporan omzet mengecualikan, laporan apotek **tetap menghitung**. `AUDIT_ALUR_UANG_2026-10-04.md` |
| ~~`force_past_day_void` kehilangan 3 langkah rollback~~ | **DIPERBAIKI 2026-10-04.** Jalur void ADA DUA — kalau menambah langkah di satu, **periksa yang lain**. Dulu jalur kedua kehilangan `void_komisi_transaksi` + 2 revert membership, sehingga pasien mempertahankan tier VVIP atas pembayaran yang di-VOID. ⚠ **Baris yang terlanjur rusak belum dibersihkan** — query deteksinya di `AUDIT_ALUR_UANG_2026-10-04.md` Temuan 5 |
| **Hak & persetujuan tidak dikunci, barang & uang dikunci** | Proyek memakai `with_for_update()` untuk stok dan pembayaran (plus kunci idempotensi), tapi **tidak** untuk kuota membership, sesi series, maupun approve retur/opname. Akibat terbukti: **dua tindakan Rp 0 dari satu hak sesi**. **SEMUA SUDAH DIKUNCI 2026-10-04**: kuota membership, sesi series, approve+reject opname, approve retur. Dulu dua approve bersamaan lolos pagar `status != DRAFT` dan di opname menghasilkan **dua lot** sementara cache menulis angka satu-approve — buku dan cache berselisih diam-diam. **Pertanyaan yang harus ditanyakan saat menulis pagar status: apa yang terjadi kalau dua permintaan membacanya bersamaan?** — `AUDIT_ALUR_UANG_2026-10-04.md` Temuan 19–20 |

**Sebelum memakai ulang fungsi simpan mana pun: periksa siapa yang commit.**
**Sebelum memakai ulang himpunan role: periksa apakah artinya sama.**

### 4.2 Tailwind dikompilasi lebih dulu — kegagalan SENYAP

Kelas yang tidak dipakai template mana pun **tidak ada** di `static/css/app.css`.
Elemen tetap dirender, hanya tampilannya salah — tombol dengan latar hilang jadi
teks putih di atas putih, tak terlihat.

```bash
python -m scripts.cek_kelas_tailwind nama_template.html
bash deployment/build_tailwind.sh          # kompilasi ulang
```

✅ **Hanya ada SATU app.css sekarang: `sehati_clinic/static/css/app.css`.**
Dulu ada salinan kembar di `app/web/static/` yang tidak dilayani dan tidak ikut
di-build; dokumen ini dan `cek_kelas_tailwind.py` sama-sama menunjuk ke sana.
Asalnya `deployment/setup_self_host.sh`, yang mengunduh ke `app/web/static/` lalu
menambal template agar memuat dari `/static/` — dua tempat berbeda. Kembarnya
**dihapus** dan skripnya diperbaiki (2026-10-04, keputusan dr. Hansen).

✅ **Dikompilasi ulang 2026-10-04.** 467 → 526 kelas; kelas warna hilang **48 → 0**,
diverifikasi pada 37 halaman **terender** (bukan template), tempat kelas dinamis
sudah jadi nilai sebenarnya.

⚠ `dashboard.html` merakit kelas saat render (`bg-{{ st.color }}-50/30`). Scanner
Tailwind tidak bisa melihatnya — `bg-blue-50/30` dan `bg-teal-50/30` memang hilang
sampai didaftarkan di `safelist` pada `tailwind.config.js`. **Kalau menambah warna
di `dashboard_service.py`, daftarkan juga di safelist**, atau kartunya kehilangan
warna tanpa error apa pun.

### 4.3 Audit ditulis di SESI YANG SAMA dengan bisnis

`AuditService.log()` menelan semua exception — docstring-nya berkata *"audit failure
tidak boleh block business"*. **Itu tidak berlaku.** Ia memakai sesi yang sama, jadi
`flush()` yang gagal menandai sesi perlu rollback dan `commit()` milik caller gagal
dengan `PendingRollbackError` — pesan yang tidak menyebut audit sama sekali.

Terbukti 2026-10-04: **User-Agent 314 karakter** (kolom `varchar(255)`, tanpa
pemotongan) membuat pembuatan produk GAGAL. `@@sql_mode` memuat `STRICT_TRANS_TABLES`
dan mini PC memakai image MySQL yang sama — MySQL **menolak**, bukan memotong.

Jadi sebelum menambah field ke audit: **potong ke lebar kolomnya**. Dan kalau menulis
helper yang menelan exception di sesi bersama, ingat bahwa menelan tidak membuat
kegagalannya hilang — ia hanya memindahkan kemunculannya ke tempat yang membingungkan.
`AUDIT_ALUR_UANG_2026-10-04.md` Temuan 23–24.

### 4.4 `.env` tidak masuk `os.environ`

`pydantic-settings` membaca `.env` hanya untuk field yang dideklarasikan di
`Settings`. `os.getenv("APA_PUN")` **kosong di dev** padahal berhasil di mini PC
(Docker `env_file` mengisi environ container). Pakai pola `envval()` di
`clinical_export_batch.py` kalau butuh setelan di luar `Settings`.

### 4.5 Nama anggota enum ≠ nilai kolom

`GenderEnum.LAKI_LAKI = "L"`. Menulis `'PRIA'` ditolak MySQL dengan
`Data truncated` — pesan yang tidak menyebut sebabnya sama sekali.
Kolom VARCHAR lebih buruk: nilai ngawur **diterima diam-diam** dan baru bikin
laporan aneh berbulan-bulan kemudian (`status_transaksi` hanya `BAYAR`/`VOID`).

### 4.6 HTMX

Panel dinamis = **render ulang dari server**, bukan akumulasi di klien. CSS dikirim
di dalam fragmen. Fragmen "tambah kartu" wajib `Cache-Control: no-store`. Identitas
kartu lewat query param, bukan body. Rincian: `sehati-htmx-ui-gotcha` (memori) dan
`DESAIN_MODUL_RACIKAN.md`.

---

## 5. Pemeriksa — jalankan sebelum bilang "selesai"

Semua dari `sehati_clinic/`, kecuali yang pertama dari akar repo.

| Perintah | Menjaga apa |
|---|---|
| `bash scripts/cek_phi_tracked.sh` | Tidak ada berkas PHI/kunci yang dilacak git |
| `python -m scripts.cek_nik` | NIK kosong = NULL; gerbang AST jalur tulis NIK |
| `python -m scripts.cek_gabung_pasien` | 13 tabel penggabungan vs `information_schema` |
| `python -m scripts.cek_clinical_pack` | Paket klinis tidak memuat identitas; pid stabil |
| `python -m scripts.cek_paket_klinis_keluar` | **Mendekripsi paket yang BENAR-BENAR keluar** dan mengauditnya |
| `python -m scripts.cek_top_diagnosa` | Angka laporan kasus terbanyak |
| `python -m scripts.cek_finance_pack` | `medical_soap_raw` tidak ikut paket finance |
| `python -m scripts.cek_serah_tanpa_lot` | Obat `DISERAHKAN` yang lotnya tidak pernah keluar (Temuan 30) |
| `python -m scripts.cek_soap_basi` · `cek_tunda_item` · `cek_laporan_racikan` · `cek_tebus_resep` | Modul masing-masing |
| `python scripts/cek_kelas_tailwind.py` | Kelas Tailwind yang tidak ada di app.css |

**Menulis pemeriksa baru: uji DUA ARAH.** Lulus pada kode benar, **dan gagal** saat
jalur pintas palsu disisipkan. Pemeriksa yang tidak pernah dibuktikan bisa gagal
tidak membuktikan apa pun.

⚠ Beberapa pemeriksa **menulis ke DB** (membuat pasien uji, bahkan menggabungkannya).
Semuanya menolak jalan kalau nama DB bukan `dev`/`test` dan pasiennya banyak.
Jangan lepaskan pagar itu.

---

## 6. Privasi — ini klinik, bukan aplikasi biasa

- **Gerbang PHI pra-commit** = symlink `.git/hooks/pre-commit → scripts/cek_phi_tracked.sh`.
  ⚠ `.git/hooks/` **tidak ikut git**. Setelah kloning baru, pasang lagi — **DUA
  langkah, bukan satu**:
  ```bash
  ln -sf ../../scripts/cek_phi_tracked.sh .git/hooks/pre-commit
  chmod +x scripts/cek_phi_tracked.sh
  ```
  **Kenapa `chmod` ikut:** skripnya ter-commit dengan mode `100644`. Git **melewati hook
  yang tidak executable** — ia mencetak satu baris *hint*, tapi **commit-nya tetap
  jalan**. Jadi gerbangnya terpasang, path-nya benar, isinya benar, dan tidak menahan
  apa pun. Terbukti dua arah 2026-10-04: dengan `644` berkas `data_pasien.csv` berisi
  kolom `nama_pasien,nomor_ktp` lolos commit; dengan `755` ditolak.
  Verifikasi, jangan diasumsikan — harus ada `x`:
  `ls -l scripts/cek_phi_tracked.sh` → `-rwxrwxr-x`.
  ⚠ Mode `100644` itu ada **di repo**, jadi setiap klon memasang gerbang mati dengan
  cara yang sama. **Periksa di desktop dan mini PC.**
- Riwayat git pernah memuat PHI dan **sudah dibersihkan** (2026-09-27), diikuti rotasi
  password. Jangan pernah mengulang: dump SQL, folder `exports/`, `.age`, `.key`,
  `.env` tidak pernah masuk repo.
- **Paket klinis PSEUDONIM, BUKAN ANONIM.** Jangan pernah menyebutnya anonim. Teks
  bebas dikirim apa adanya dan bisa memuat nama orang di dalam kalimat.
- `pasien_pseudonim` adalah **tabel paling sensitif di sistem** — satu-satunya yang
  menyambungkan riwayat klinis di paket ekspor ke orang sungguhan.
- Backup terenkripsi `age`; kunci privat `~/sehati-backup.key` **di desktop**, bukan
  di mini PC. Cron harian 23:59 WIB.

---

## 7. Keputusan dr. Hansen yang mengikat

- **Penggabungan pasien SATU ARAH, tanpa undo.** Jaring pengamannya **catatan kertas**
  (id pasien, id transaksi, nomor nota). Karena itu layar pratinjau **wajib**
  menampilkan angka-angka itu sebelum tombol ditekan — kalau dipangkas, SOP kertasnya
  mustahil dijalankan.
- **Void hanya untuk tindakan yang belum selesai dikerjakan.**
- **Tidak boleh ada tagihan kosong** — menunda seluruh item dipagar, disarankan void.
- **Teks bebas klinis dikirim apa adanya** ke paket analisis; paketnya yang dijaga
  rahasia, bukan isinya yang disensor.
- **Sehati tidak menganalisa.** Ia menyediakan data mentah; analisis di `data_analyst`
  lalu Council AI (proyek Python terpisah).
- **Sebagian hal SENGAJA offline** (SOP kertas), bukan celah yang terlewat — baca
  memori `sehati-sop-offline` / dokumen terkait sebelum mengusulkan otomatisasi.

---

## 8. Keadaan per 1 Oktober 2026

**Sudah jalan di klinik:** pendaftaran · antrian · SOAP + diagnosa terkode (ICD-10 &
estetik internal) · tindakan · resep & racikan · apotek (termasuk tebus resep luar &
penundaan sebagian) · kasir · membership · komisi · laporan · ekspor Finance
(file-drop harian) · backup terenkripsi terjadwal.

**Migrasi terakhir:** `20260930_0200` (tabel `pasien_pseudonim`). Dev dan mini PC
sama-sama di kepala ini. 57 tabel.

**Baru selesai (2026-10-04, dari laptop):** kompilasi ulang Tailwind (48→0 kelas warna
hilang) · paket klinis Tahap B · verifikasi S1 CSP/HSTS · **F3 snapshot line-item
Finance** (`transaksi_detail_tindakan` akhirnya ditulis) · workspace laptop + gerbang PHI.

**Baru selesai (Sep 30 – Okt 1):** normalisasi NIK · penggabungan pasien sungguhan ·
paket klinis ber-pseudonim Tahap A · laporan Kasus Terbanyak · `age` di image
container + folder drop klinis.

✅ **Suite test HIJAU** (108 lulus / 0 gagal; 96 saat triase 2026-10-04). Enam test
sempat merah: lima fixture usang dari dunia pra-#54 (menyetel `COMPLETED` sebagai bukti
serah obat, padahal #54 menggantinya dengan bukti per-item), satu artefak skema laptop.

⚠ **Kalau DB dibangun dengan `create_all()` dan bukan migrasi, ia KEHILANGAN indeks
UNIQUE** — laptop menerima data yang produksi tolak. Lihat `ALUR_DUA_MESIN.md` §7 dan
`AUDIT_ALUR_UANG_2026-10-04.md` Temuan 18.

```bash
docker compose ... exec -T sehati-app python -m pytest tests/integration/ tests/unit/ -q
```

**Menunggu dikerjakan:**

| Apa | Catatan |
|---|---|
| ~~Paket klinis **Tahap B**~~ | **KODE SELESAI 2026-10-04** — 5 berkas (tindakan, resep, racikan, racikan_bahan, followup), tanpa migrasi. Pagar baru `KOLOM_UANG`. ⚠ **Belum diuji ujung-ke-ujung**: ZIP+enkripsi age butuh `BACKUP_RECIPIENT` yang hanya ada di desktop. `Project_Memory/DESAIN_CLINICAL_PACK_TAHAP_B.md` |
| Combo obat (AB Reguler/Premium) | butuh migrasi · `DESAIN_APOTEK_BATCH_DAN_COMBO.md` |
| Konversi batch (SR/SR2/SRO) | butuh migrasi · dokumen yang sama |
| S1 — CSP + HSTS | **Sebagian besar SUDAH ADA** (commit `adb0459`): CSP aktif & menegakkan, HSTS terpasang tapi mati. Sisa: nyalakan HSTS di `.env` mini PC, dan hapus `'unsafe-inline'` (89 handler inline + 275 atribut style). `Project_Memory/S1_CSP_HSTS.md` |
| ~~Kompilasi ulang Tailwind~~ | **SELESAI 2026-10-04** — 48 → 0 kelas warna hilang. §4.2 |
| NIK mentah di `audit_log` | `nonaktifkan()` & `gabungkan()` menulisnya mentah, padahal aturan proyek melarang. **Belum diubah — menunggu keputusan dr. Hansen**, bisa jadi disengaja untuk ketertelusuran. |

**⚠ Pengerasan keamanan (#33–36, S1–S8) adalah GERBANG, bukan antrean.** Ia harus
selesai **sebelum data pasien asli masuk**, bukan dikerjakan berurutan kapan sempat.
Per 1 Oktober 2026 belum ada tanggal untuk itu — tanyakan kalau mendekat.

---

## 9. Mau tahu lebih dalam

`Project_Memory/` — 80 dokumen. Yang paling sering dibutuhkan:

| Berkas | Kapan dibaca |
|---|---|
| `01_project_overview.md` · `02_architecture.md` | Orientasi awal |
| `03_database_schema.md` | Sebelum menyentuh skema |
| `05_coding_style.md` · `04_api_rules.md` | Sebelum menulis kode/route baru |
| `06_business_logic.md` | Aturan bisnis (harga, komisi, membership) |
| `07_known_issues.md` · `BACKLOG_KONSOLIDASI_2026-09-30.md` | Apa yang sudah diketahui rusak/tertunda |
| `11_decisions_log.md` | Kenapa sesuatu dibuat begitu |
| `DESAIN_*.md` | Rancangan per modul — **baca sebelum mengubah modul itu** |
| `12_smoke_test_guide.md` | Sebelum & sesudah deploy |
| `ALUR_DUA_MESIN.md` | **Kerja di laptop**, sinkron desktop⇄laptop, aturan deploy |
| `S1_CSP_HSTS.md` | Sebelum menyentuh header keamanan atau CSP |
| `DESAIN_CLINICAL_PACK_TAHAP_B.md` | Sebelum menyentuh ekspor paket klinis |
| `DEAD_CODE_SWEEP_2026-10-04.md` | Sebelum menghapus fungsi yang "kelihatan tidak dipakai" |
| `AUDIT_ALUR_UANG_2026-10-04.md` | **Sebelum menyentuh void/laporan apotek** — ada temuan terbuka |

⚠ `00_README.md` dan `10_ai_collaboration_guide.md` ditulis Juni 2026 untuk skema
multi-AI review yang sudah tidak dipakai. Masih berguna sebagai indeks, tapi
**dokumen ini (CLAUDE.md) yang berlaku** kalau keduanya berbeda.

---

## 10. Gaya kerja yang terbukti cocok

- **Rancang dulu untuk modul besar**, tunjukkan ke dr. Hansen, baru bangun.
- **Sederhana mengalahkan pintar.** Kutipan beliau setelah panel HTMX berhasil di
  iterasi kelima: *"sometimes simplicity is the answer"*. Kalau sebuah UI butuh banyak
  sinkronisasi state di klien, ganti jadi render ulang dari server.
- **Tulis alasannya di kode, bukan hanya apanya.** Komentar di repo ini sengaja
  menjelaskan *kenapa begini dan apa yang rusak kalau diubah* — itu yang menyelamatkan
  sesi berikutnya. Pertahankan kebiasaan itu.
- **Pesan commit panjang dan jujur**, termasuk kesalahan sendiri dan temuan yang belum
  dikerjakan. Riwayat git di sini adalah dokumentasi, bukan catatan administratif.
