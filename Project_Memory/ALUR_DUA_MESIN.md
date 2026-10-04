# ALUR DUA MESIN — desktop ⇄ laptop, GitHub sebagai penghubung

**Dibuat:** 2026-10-04 · **Keputusan dr. Hansen:** laptop hanya sementara; pekerjaan
utama di desktop.

Dokumen ini menjawab satu pertanyaan: *apa yang boleh dikerjakan di mesin mana, dan
bagaimana keduanya tetap sinkron tanpa saling menimpa.*

---

## 1. Peran tiap mesin — ini aturan, bukan saran

| Mesin | Boleh | TIDAK boleh |
|---|---|---|
| **Desktop** (`/mnt/e/Claude/Projects/sehati-emr-pos`) | Segalanya. Sumber kebenaran. **Satu-satunya yang deploy ke mini PC.** | — |
| **Laptop** (`~/JoDerma/sehati-emr-pos`) | Tulis kode · smoke test UI lokal · baca/diskusi | **Deploy ke mini PC.** Jangan pernah jalankan `push-ke-minipc.sh` dari sini |
| **Mini PC** (`/srv/sehati`) | Produksi. Hanya menerima rsync dari desktop | Jangan pernah dipakai mengedit kode |

**Kenapa deploy hanya dari desktop:** `deploy/push-ke-minipc.sh` memakai
`rsync --checksum --delete`. `--delete` berarti apa pun yang ada di mini PC tapi tidak
ada di mesin pengirim akan **dihapus**. Dua mesin pengirim = dua pendapat soal "apa yang
seharusnya ada di sana", dan yang kalah kehilangan berkas tanpa peringatan. Satu pengirim
menghilangkan seluruh kelas masalah itu.

---

## 2. Apa yang dibawa git, apa yang tidak

Git membawa **kode**, bukan **keadaan mesin**. Yang tidak ikut, dan harus disiapkan
sendiri di tiap mesin:

| Tidak ikut git | Kenapa | Akibatnya di laptop |
|---|---|---|
| `sehati_clinic/.env` | rahasia (`.gitignore`) | Buat sendiri, nilainya BEDA dari desktop |
| `.venv/` | path absolut baked-in | Di laptop tidak dipakai — aplikasi jalan di container |
| **Database MySQL** | server, bukan berkas proyek | **Data tidak sync sama sekali** |
| `uploads/`, `media/` | foto pasien = PHI | Logo klinik dll tidak ikut |
| `.git/hooks/` | git tidak melacak folder itu | Gerbang PHI harus dipasang ulang (§6) |
| `exports/`, `clinical_pack/` | PHI / paket klinis | Tidak pernah pindah mesin |

Yang **ikut** git dan sering dikhawatirkan padahal aman: `app/web/static/css/app.css`
(hasil kompilasi Tailwind) **terlacak**, jadi tampilan tidak perlu dikompilasi ulang per
mesin. Seluruh migrasi Alembic ikut, jadi perubahan skema **berikutnya** tersinkron lewat
`alembic upgrade head` — bukan lewat menyalin database.

⚠ Tapi **membangun skema dari NOL tidak bisa lewat Alembic** — lihat §7. Itu temuan
2026-10-04 dan dampaknya lebih luas daripada urusan laptop.

---

## 3. Alur harian

**Mulai kerja**, di mesin mana pun, sebelum menyentuh apa pun:

```bash
git pull --ff-only
```

`--ff-only` disengaja. Kalau ia **menolak**, itu tanda ada commit di sisi lain yang belum
Anda ambil — berhenti dan lihat dulu. Tanpa `--ff-only`, git akan membuat merge commit
yang tidak Anda rencanakan, dan di proyek satu orang itu hampir selalu berarti ada
pekerjaan yang terlupakan di mesin lain.

**Selesai kerja** — jangan tinggalkan commit yang belum di-push:

```bash
git push
```

**Aturan praktis:** mesin yang Anda tinggalkan harus selalu dalam keadaan `git status`
bersih dan sudah ter-push. Kalau tidak, mesin berikutnya mulai dari dasar yang salah.

---

## 4. Database tidak sync — konsekuensinya

Desktop tersisa 5 pasien dummy sejak 18 September. Laptop punya database **sendiri**.
Pasien yang Anda daftarkan di laptop tidak ada di desktop, dan sebaliknya.

Untuk sekarang itu tidak masalah — sistem masih uji coba internal dengan pasien dummy.
Tapi artinya:

- **Smoke test yang butuh data historis harus di desktop atau mini PC.** Termasuk yang
  masih menunggu di backlog: tebus resep 3 mode, racikan di tebus resep,
  sisakan-untuk-nanti.
- **Smoke test UI di laptop** = login, navigasi, render halaman, kelas Tailwind, alur
  yang bisa dibuat dari nol. Itu memang tugas laptop menurut keputusan dr. Hansen.

**Jangan menyalin dump database antar mesin** untuk "menyamakan data". Walau isinya dummy
hari ini, itu kebiasaan yang bertentangan dengan aturan privasi proyek, dan dump mudah
tertinggal di disk lalu ikut `git add -A`. Pelajaran 2026-09-30: 17 dump SQL (13,1 MB)
ditemukan terlacak di repo.

---

## 5. Runtime laptop = Docker, identik produksi

**Masalahnya:** laptop ini Ubuntu 26.04 dengan Python sistem **3.14**, sedangkan produksi
`python:3.11-slim`. `python3.11` tidak tersedia di apt Ubuntu 26.04. Selisih tiga versi
membuat smoke test di laptop tidak bisa dipercaya — bug bisa muncul hanya di satu sisi.

**Keputusan:** aplikasi di laptop jalan **di dalam container**, memakai
`docker-compose.yml` yang sama dengan mini PC plus satu berkas override khusus laptop.
Python 3.11 dan MySQL 8.0 persis seperti di klinik. Tidak ada MySQL atau Python yang
perlu dipasang di laptop.

**Konsekuensi yang mudah terlewat:** semua perintah yang menyentuh Python atau DB harus
dijalankan **di dalam container**, bukan di shell laptop. Pemeriksa di CLAUDE.md §5,
`alembic`, `mysql` — semuanya. Dijalankan di shell laptop, mereka memakai Python 3.14
tanpa dependensi dan akan gagal dengan pesan yang menyesatkan.

```bash
# BENAR di laptop
docker compose exec sehati-app python -m scripts.cek_nik
docker compose exec sehati-db mysql -uroot -p"$DB_ROOT_PASSWORD" db_sehati

# SALAH di laptop (ini cara desktop)
python -m scripts.cek_nik
mysql -e "SQL"
```

### Kenapa override-nya BUKAN `docker-compose.override.yml`

Compose memuat `docker-compose.override.yml` **otomatis** kalau berkas itu ada di folder
yang sama. Berkas itu akan ikut git, lalu ikut ter-`rsync` ke mini PC — ia **tidak ada**
di daftar `KECUALI` pada `push-ke-minipc.sh`. Hasilnya: stack produksi klinik diam-diam
jalan dengan `uvicorn --reload` dan bind-mount kode yang tidak ada di sana.

Karena itu berkasnya bernama **`deploy/compose.laptop.yml`** — nama yang Compose
**tidak** muat otomatis. Ia hanya aktif kalau disebut eksplisit dengan `-f`. Berkas itu
juga ditambahkan ke daftar `KECUALI` rsync sebagai lapis kedua.

---

## 6. Jebakan yang sudah menggigit

### 6.1 Gerbang PHI terpasang tapi MATI

`scripts/cek_phi_tracked.sh` ter-commit dengan mode `100644` (tidak executable). Git
**melewati hook yang tidak executable** — ia mencetak satu baris *hint* kecil, tapi
**commit-nya tetap jalan**.

Terbukti dua arah (2026-10-04, repo uji): dengan mode `644`, berkas bernama
`data_pasien.csv` berisi kolom `nama_pasien,nomor_ktp` **berhasil ter-commit**. Setelah
`chmod +x`, commit yang sama ditolak.

Jadi memasang hook butuh **dua** langkah, bukan satu:

```bash
ln -sf ../../scripts/cek_phi_tracked.sh .git/hooks/pre-commit
chmod +x scripts/cek_phi_tracked.sh
```

Verifikasi, jangan diasumsikan — harus ada `x`:

```bash
ls -l scripts/cek_phi_tracked.sh    # -rwxrwxr-x
```

⚠ **Mode `100644` itu ada di repo, bukan hanya di satu klon.** Sampai perubahan mode
ini di-commit, setiap klon baru memasang gerbang yang mati dengan cara yang sama —
termasuk klon di desktop dan mini PC. Periksa di sana.

### 6.2 Alembic bisa jadi dua kepala

Kalau laptop dan desktop sama-sama membuat migrasi baru dari head yang sama, Alembic
punya dua kepala dan harus di-merge manual. **Satu mesin saja per migrasi**, dan push
sebelum mesin lain mulai. Head per 2026-10-04: `20260930_0200`.

### 6.3 `git checkout` mengubah mtime seluruh pohon

Itu persis kondisi yang membuat `--checksum` wajib di `push-ke-minipc.sh`. Jangan pernah
melepas flag itu. Alasan historisnya (riwayat git ditulis ulang 2026-09-27) sekarang
punya sebab kedua: setiap `git pull` di desktop juga menyentuh mtime.

### 6.4 Remote `core` tidak ada di klon laptop

Backlog §8 menyebut "push ke `origin` + `core`". Klon laptop hanya punya `origin`. Kalau
`core` adalah cadangan di desktop, **push dari laptop tidak mengisi cadangan itu** —
desktop yang harus melakukannya. Periksa dengan `git remote -v` di desktop.

---

## 7. ⚠ Alembic TIDAK bisa membangun database dari nol

**Ditemukan 2026-10-04 saat menyiapkan laptop.** `alembic upgrade head` di database
kosong **GAGAL** pada migrasi kedua:

```
Running upgrade -> 0000_baseline, baseline: existing schema dari manual SQL migrations
Running upgrade 0000_baseline -> 20260527_1700, add updated_at to kunjungan_antropometri
ProgrammingError: (1146, "Table 'db_sehati.kunjungan_antropometri' doesn't exist")
```

**Sebabnya:** `0000_baseline` adalah **marker kosong** — `upgrade()`-nya `pass`. Ia
mengasumsikan skema sudah ada, dibuat oleh `migrations_sql/001_fix_kritis.sql` s/d
`004_audit_log.sql`. Berkas-berkas itu **tidak pernah ada di repo**: `migrations_sql/`
mulai dari `009`, dan seluruhnya hanya memuat 4 `CREATE TABLE`.

**Artinya skema 57 tabel itu tidak ada di mana pun dalam repo.** Ia hanya ada di:
MySQL desktop yang hidup · volume Docker mini PC · backup terenkripsi · dan
`deploy/schema_only.sql` yang **gitignored** dan di-generate dari DB hidup.

Ini bukan hanya soal laptop. **Instalasi klinik baru tidak mungkin dari repo saja**, dan
pemulihan bencana bergantung sepenuhnya pada backup terenkripsi — repo tidak bisa
membangun ulang skemanya.

**Jalan keluar yang dipakai di laptop:** model ORM ternyata **lengkap** — 57
`__tablename__` di `app/db/models/`, persis sama dengan 57 tabel di CLAUDE.md §8. Jadi
skema dibuat dari model, lalu Alembic ditandai ke head:

```python
Base.metadata.create_all(engine)    # 57 tabel
```
```bash
alembic stamp head                  # -> 20260930_0200
```

⚠ **`create_all` bukan pengganti migrasi.** Ia membuat skema menurut model *hari ini*,
tanpa melewati riwayat migrasi. Kolom yang pernah ditambahkan lewat SQL mentah dan tidak
pernah masuk model **tidak akan ada**. Untuk DB smoke-test laptop itu cukup; untuk
produksi **tidak boleh**.

**Belum diputuskan (butuh dr. Hansen):** apakah `deploy/schema_only.sql` sebaiknya
di-commit (berhenti gitignore) supaya repo bisa membangun dari nol. Isinya skema saja,
tanpa data — tapi nama tabel/kolom klinis ikut terbaca.

---

## 8. Setup laptop dari nol — urutan yang TERBUKTI jalan

Jalankan satu per satu, tunggu hasilnya (CLAUDE.md §1.2).

```bash
# 1. Klon
git clone https://github.com/hansensudarmahs2-sudo/sehati-emr-pos.git .

# 2. Gerbang PHI — DUA langkah (§6.1)
ln -sf ../../scripts/cek_phi_tracked.sh .git/hooks/pre-commit
chmod +x scripts/cek_phi_tracked.sh
bash scripts/cek_phi_tracked.sh                    # harus "BERSIH"

# 3. .env laptop (JANGAN salin dari desktop — sandinya beda)
cd sehati_clinic && cp .env.example .env
#    sunting: DB_HOST=sehati-db, DB_PASSWORD=<acak>, JWT_SECRET_KEY=<acak ≥32 char>
#    TAMBAHKAN (tidak ada di .env.example, dibaca docker-compose.yml):
#      DB_ROOT_PASSWORD=<acak>
#      SEHATI_CLINICAL_DROP_HOST=<folder di luar repo>

# 4. Nyalakan (build pertama ~3 menit)
docker compose -f docker-compose.yml -f deploy/compose.laptop.yml up -d --build
#    sehati-app akan GAGAL di sini — itu normal, lihat §7.

# 5. Bangun skema dari model, lalu tandai Alembic
docker compose -f docker-compose.yml -f deploy/compose.laptop.yml \
  run --rm --entrypoint python sehati-app -c \
  "import app.db.models; from app.db.base import Base; \
   from sqlalchemy import create_engine; import os; \
   Base.metadata.create_all(create_engine(f\"mysql+pymysql://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}@{os.environ['DB_HOST']}:3306/{os.environ['DB_NAME']}\"))"
docker compose -f docker-compose.yml -f deploy/compose.laptop.yml \
  run --rm --entrypoint alembic sehati-app stamp head
docker compose -f docker-compose.yml -f deploy/compose.laptop.yml up -d sehati-app

# 6. Seed — URUTAN PENTING. wipe_and_seed_topikal men-TRUNCATE 57 tabel,
#    jadi ia HARUS duluan. Ia juga yang membuat user pertama.
docker compose ... exec -T sehati-app python -m scripts.wipe_and_seed_topikal \
    --yes WIPE --admin-user hansen --admin-pass '<acak>' --admin-pin '<6 digit>' \
    --admin-name 'dr. Hansen Sudarma' --nama-klinik 'JoDerma' \
    --csv '../seed_data/LIST PRODUK TOPIKAL - Produk Topikal.csv'
docker compose ... exec -T sehati-app python -m scripts.seed_treatment \
    --csv '../seed_data/LIST TINDAKAN - joderma FINAL.csv'
docker compose ... exec -T sehati-app python -m scripts.seed_diagnosa \
    --csv '../seed_data/ref_diagnosa_seed.csv'
#    SQL seed (opsional, untuk apotek/racikan):
docker compose ... exec -T sehati-db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD"' \
    < ../seed_data/obat_minum_seed.sql
```

**Hasil yang diharapkan:** 57 tabel · 80 produk topikal · 74 obat minum · 128 tindakan ·
72 diagnosa · 4 formula racikan · 1 Superadmin · 37 halaman nav semua 200.

### Catatan yang menghemat waktu

- **`python -m scripts.x`, bukan `python scripts/x.py`.** Yang kedua gagal dengan
  `ModuleNotFoundError: No module named 'app'` — menjalankan berkas menaruh
  `/app/scripts` di `sys.path`, bukan `/app`.
- **Akun awal BUKAN celah yang hilang.** `deploy/README-DOCKER-MINIPC.md` §6 hanya
  menulis "via seed / CLI" tanpa menyebut skripnya; pembuatnya adalah
  `wipe_and_seed_topikal.py`, yang namanya tidak memberi petunjuk bahwa ia juga membuat
  Superadmin. Tidak perlu skrip baru.
- **Sandi dev dicatat di `sehati_clinic/.env`** sebagai baris komentar di akhir
  (`# DEV_ADMIN_USER/PASS/PIN`). `.env` gitignored, jadi tidak pernah ikut git.
- **Matikan dengan `down`, TANPA `-v`.** `-v` menghapus volume = database laptop hilang.
- **Edit template/CSS tampak langsung** (bind-mount + Jinja cek mtime). Edit `.py` perlu
  `docker compose ... restart sehati-app` (~3 detik).

---

## 9. Ringkasan aturan

1. **Deploy ke mini PC hanya dari desktop.** Tanpa pengecualian.
2. **Laptop = kode + smoke test UI lokal.** Bukan uji alur yang butuh data historis.
3. `git pull --ff-only` sebelum mulai, `git push` sebelum berhenti.
4. **Tinggalkan mesin dengan `git status` bersih dan sudah ter-push.**
5. **Jangan salin database atau `.env` antar mesin.** Tiap mesin punya sendiri.
6. **Satu mesin saja per migrasi Alembic.**
7. Di laptop, perintah Python/DB jalan **di dalam container**.
8. Gerbang PHI = `ln -sf` **dan** `chmod +x`. Verifikasi ada `x`.
9. `docker compose down` **tanpa `-v`**.
