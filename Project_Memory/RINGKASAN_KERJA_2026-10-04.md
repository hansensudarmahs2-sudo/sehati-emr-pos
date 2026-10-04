# Ringkasan kerja 4 Oktober 2026 — dikerjakan dari LAPTOP

Satu halaman untuk menjawab tiga pertanyaan: **apa yang terjadi hari ini**, **apa yang
harus diputuskan dr. Hansen**, dan **apa yang hanya bisa dikerjakan di mini PC**.

Rinciannya ada di tiga dokumen lain; halaman ini indeksnya, bukan penggantinya:

| Dokumen | Isi |
|---|---|
| `AUDIT_ALUR_UANG_2026-10-04.md` | 18 putaran audit, 30 temuan, berikut buktinya |
| `UJI_PENUH_LAPTOP_2026-10-04.md` | uji penuh di laptop + 4 perbaikan sesudahnya |
| `ALUR_DUA_MESIN.md` | aturan laptop ⇄ desktop ⇄ mini PC |

---

## 1. Keadaan cabang — `main` TIDAK disentuh

Keputusan dr. Hansen: **jangan merge ke main, tetap di cabang.** Dipatuhi.

| | |
|---|---|
| `main` ada di | `304b58c` "Audit alur uang #1" |
| Cabang kerja terakhir | `laptop/perbaiki-tautan-tagihan-none` (`e153aad`) |
| Jarak | **29 commit** di atas `main` |
| Bentuk | **satu rantai lurus** — diverifikasi: setiap cabang lain adalah leluhur cabang terakhir |

⚠ **Artinya menggabungkan nanti cukup SATU cabang**, bukan 29. Diverifikasi dengan
`git merge-base --is-ancestor` untuk semua 29 cabang lokal — tidak ada satu pun yang
punya commit di luar rantai. Jadi tidak ada pekerjaan yang akan tertinggal kalau hanya
cabang terakhir yang diambil.

```bash
# memeriksa ulang klaim itu kapan saja
git log --oneline main..laptop/perbaiki-tautan-tagihan-none | wc -l     # -> 29
```

---

## 2. Buku besar temuan — 30 temuan, 9 selesai, 21 terbuka

| Status | Temuan |
|---|---|
| ✅ **Kode diperbaiki** (9) | 1 · 3 · 5 · 6 · 15 · 17 · 19 · 20 · 30 |
| 🔴 Terbuka, berat (8) | 11 · 13 · 18 · 23 · 24 · 27 · 28 · 29 |
| 🟡 Terbuka, sedang (13) | 2 · 4 · 7 · 8 · 9 · 10 · 12 · 14 · 16 · 21 · 22 · 25 · 26 |

⚠ **Temuan 3 selesai di KODE tapi BELUM di DATA.** Jalur `force_past_day_void` sekarang
membatalkan komisi, tapi baris yang terlanjur rusak sebelum perbaikan masih ada — dan
Temuan 11 **membuktikan baris semacam itu ikut TERBAYAR**. Jadi ini uang yang sudah
keluar, bukan kerapian data.

⚠ **Tiga temuan butuh MIGRASI**, jadi tidak bisa dari laptop: **16** (indeks unik kuota),
**25** (`UNIQUE(id_distributor, nomor_faktur)`), **13** (`nilai_mutasi`/`hpp_satuan`).

---

## 3. Yang diperbaiki hari ini

Semua dibuktikan dengan **menjalankan kodenya**, dan sebagian besar **dua arah** —
dibuktikan juga GAGAL tanpa perbaikan.

| # | Apa | Bukti |
|---|---|---|
| 1 | **Temuan 30** — void tidak lagi menciptakan barang fantom | 3 skenario; kode lama membuat **10 dan 6 unit fantom**, kode baru 0 |
| 2 | **Dua cacat 500** — timeline antropometri & dashboard dokter | keduanya kini 200 **dengan data**, bukan sekadar tidak crash |
| 3 | **`created_at` sebagai tanggal klinis** | 3 kunjungan yang dulu luruh jadi 1 kini tampil 3; dedupe tetap bekerja |
| 4 | **Tautan tagihan rusak + kebocoran lintas pasien** | tautan `None` hilang; nota aktivasi tertaut dengan DUA pagar |

### Yang paling perlu diketahui dari keempatnya

**Temuan 30.** `DISERAHKAN` punya dua arti: bagi apoteker "obat di tangan pasien", bagi
penjaga void "lot sudah keluar". Penyerahan dengan stok kurang **berhasil** (stok minus
sengaja diizinkan) lalu void **menciptakan** lot `VOID-RETURN` berisi barang yang tak
pernah ada — dan FEFO membagikannya. Filosofi "jangan blokir operasional" tidak disentuh;
yang diperbaiki jejaknya.

**Dua cacat 500.** Keduanya `AttributeError` yang **tidak pernah teruji**, karena 31 test
selalu dilewati (lihat §5). Yang kedua punya **empat** kesalahan dalam satu fungsi, dan
yang keempat paling halus: `== "COMPLETED"` padahal enumnya `SELESAI` — kalau tiga nama
kolomnya benar, fungsi itu akan jalan tanpa error dan **selalu mengembalikan kosong**.

**`created_at`.** Dedupe riwayat SOAP memakai tanggal PENULISAN, bukan kunjungan. Dokter
yang menyusul menulis catatan beberapa kunjungan dalam satu sesi kehilangan kunjungan
dari riwayat — tanpa error. Akar sama membuat grafik berat badan **terlihat datar**
padahal pasien turun 1,5 kg.

**Kebocoran lintas pasien.** `id_transaksi` dimasukkan ke URL ber-parameter
`id_kunjungan`. Nomornya bertabrakan, dan halaman membership **A-T902** membuka tagihan
**A-T901** dan **BKT-1791088098-591** — rekam keuangan orang lain, status **200**, tanpa
error, satu klik biasa. Ini wilayah §6.

---

## 4. HARUS dijalankan di mini PC — tiga query deteksi

Laptop tidak punya data klinik, jadi "0 temuan" di sini **tidak mengatakan apa pun**
tentang keadaan klinik. Ketiganya hanya MEMBACA.

### 4a. Komisi & membership yang rusak sebelum perbaikan (Temuan 3/5/11) — **uang**
Query ada di `AUDIT_ALUR_UANG_2026-10-04.md` Temuan 5. Yang dicari: transaksi `VOID`
yang komisinya masih `AKTIF`, dan membership yang masih `ACTIVE` atas pembayaran VOID.

### 4b. Obat `DISERAHKAN` yang lotnya tak pernah keluar (Temuan 30)
```bash
cd /srv/sehati && docker compose exec sehati-app python -m scripts.cek_serah_tanpa_lot
```
Tiap baris yang muncul menanyakan satu hal: pasiennya **menerima** obatnya (berarti
lot/opname yang salah) atau **tidak** (berarti ada kewajiban belum dipenuhi, sementara
uangnya sudah diterima).

### 4c. Membership yang menunjuk transaksi pasien LAIN
```sql
SELECT h.id_history, h.id_pasien AS pemilik, t.id_pasien AS pasien_di_transaksi
  FROM pasien_membership_history h
  JOIN transaksi_kasir t ON t.id_transaksi = h.id_transaksi_aktivasi
  LEFT JOIN kunjungan k ON k.id_kunjungan = t.id_kunjungan
 WHERE h.id_transaksi_aktivasi IS NOT NULL
   AND h.id_pasien NOT IN (COALESCE(t.id_pasien, 0), COALESCE(k.id_pasien, 0));
```
Di laptop ada satu baris semacam itu. Penulisnya benar (`membership_service.py:508`), jadi
kemungkinan sampah data uji — **tapi harus diperiksa**, karena akibatnya nota orang lain.

### Juga menunggu di mini PC (bukan query)
- **HSTS** dinyalakan di `.env` — mulai `SECURITY_HSTS_MAX_AGE=86400`, jangan 1 tahun
  (`S1_CSP_HSTS.md` §3). **Di luar jam operasional** (§1.4).
- **Ekspor paket klinis Tahap B ujung-ke-ujung** — butuh `BACKUP_RECIPIENT` (desktop).
- **`APP_ENV`/`APP_DEBUG`** — periksa `grep -E "^APP_ENV|^APP_DEBUG" /srv/sehati/.env`.
  Kalau `development`/`true`, maka SQL masuk log (termasuk nama & NIK pasien), traceback
  terekspos, dan pagar produksi (`JWT_SECRET_KEY` lemah) **tidak pernah berjalan**.
  Belum terverifikasi; mini PC tidak disentuh hari ini.

---

## 5. Pelajaran metode — ini yang paling mahal untuk dilupakan

### "Suite hijau" menyembunyikan sepertiga suite
Laporan **108 lulus / 32 dilewati** terlihat hijau. **31 dari 32 yang dilewati sebabnya
sama: login 401** — dan yang dilewati itu SELURUH lapisan endpoint HTTP. Ringkasan pytest
memberi warna sama untuk "dilewati" dan "lulus". Begitu login dipasang: **139 lulus**, dan
**dua cacat 500 langsung muncul**.

> Angka yang harus dibaca bukan "berapa yang lulus", tapi **"berapa yang dilewati, dan
> kenapa"**.

### Kode status 200 bukan bukti kebenaran
Smoke UI pertama memeriksa kode status saja. Ia menemukan tautan `None` (422) tapi
**melewatkan kebocoran lintas pasien**, yang membalas **200** sambil menampilkan rekam
orang lain. Pemeriksanya kini juga memeriksa HTML-nya. Tapi batasnya tetap ada: **id yang
salah JENIS tapi benar BENTUKNYA tidak bisa ditangkap crawler mana pun** — itu hanya
tertangkap dengan membaca template.

### Pemeriksa yang sering salah akan diabaikan
`cek_laporan_racikan` melaporkan GAGAL padahal data laptop tidak mampu mengujinya. Pola
sama dengan pemeriksa urutan pid (`DESAIN_CLINICAL_PACK_TAHAP_B.md` §7). Pemeriksa wajib
bisa berkata **"TIDAK DAPAT DIUJI"**, bukan hanya lulus/gagal.

### Cari dulu sebelum menulis yang "hilang"
Saya menyatakan `list_antropometri_pasien` perlu metode repository BARU dan itu keputusan
desain. **Salah** — metodenya sudah ada dengan nama lain (`list_antropometri_timeline`),
cocok persis, dan belum punya satu pemakai pun. Perbaikannya satu nama.

### Periksa sebelum menuduh (§1.5), termasuk menuduh data
Saya hampir menyalahkan data seed saat dashboard dokter hanya mengembalikan 1 SOAP. DB
ternyata punya 3 — yang salah dedupe-nya. Dan sebaliknya: saya sempat menyatakan
`get_treatment_selesai` tidak punya pemanggil (grep saya keliru); ia punya, dan itu
membalik tingkat keparahannya dari kode mati jadi endpoint hidup yang selalu 500.

---

## 6. Keadaan laptop — data uji yang DITINGGAL dengan sengaja

Supaya uji hari ini bisa diulang:

| Apa | Catatan |
|---|---|
| Akun `uji_owner` (Owner), `uji_dokter` (Dokter) | sandi acak di `.env` laptop; akun `hansen` tidak disentuh |
| `TEST_USERNAME` / `TEST_PASSWORD` di `.env` | `.env` tidak pernah masuk repo (§6) |
| Pasien `SEED-001/002/003` | bersihkan: `python ../tools/seed_test_scenarios.py --cleanup` |
| Pasien `A-T901/A-T902` | data uji Tahap B |

⚠ Juga ada **44 pasien sisa "Booking Test"** (22 pasang) yang menumpuk dari test booking
berulang — test itu tidak membersihkan datanya. Itu sebabnya DB laptop punya 51 pasien,
dan karenanya **tiga pemeriksa menolak jalan** (pagar "DB bukan dev/test"). Belum
dibersihkan.

⚠ **Tiga pemeriksa tidak bisa jalan di laptop** karena DB-nya bernama `db_sehati`, sama
dengan produksi: `cek_top_diagnosa` (seluruhnya), `cek_gabung_pasien` (B–F),
`cek_clinical_pack` (C–H, 16 dari ~49). Pagarnya BENAR dan **jangan dilepas**; jalan
keluarnya menamai DB laptop berbeda — perlu keputusan, karena membangun ulang DB lewat
`create_all()` **kehilangan indeks UNIQUE** (Temuan 18).

---

## 7. Keadaan uji per akhir hari

| | |
|---|---|
| Suite | **139 lulus / 0 gagal / 1 dilewati** — hijau penuh, pertama kali |
| `cek_smoke_web` | **1310 halaman · 1310 OK · 0 bermasalah · 0 segmen kosong** |
| `cek_kelas_tailwind` | **0 kelas WARNA/LATAR hilang** (kategori yang berbahaya) |
| `cek_phi_tracked` | BERSIH |
| `cek_nik` · `cek_finance_pack` · `cek_tunda_item` · `cek_tebus_resep` · `cek_serah_tanpa_lot` | semua lulus |

---

## 8. Antrean keputusan — diurutkan menurut uang, bukan menurut mudahnya

1. **Jalankan 3 query §4 di mini PC.** Dua di antaranya tentang uang yang sudah keluar.
2. **Temuan 11/3 — bersihkan baris komisi & membership yang rusak.** Terbukti terbayar.
3. **Temuan 27 — nota dari harga MASTER.** Tindakan kuota mencetak baris Rp 500.000
   dengan total Rp 0; snapshot yang benar sudah ada di `transaksi_detail_*`.
4. **Temuan 28 — uang di luar jam shift** tidak masuk hitungan shift mana pun.
5. **Temuan 29 — FEFO menyodorkan lot KEDALUWARSA** lebih dulu.
6. **Temuan 24 — `user_agent` mentah** bisa melumpuhkan pengguna (satu header 314 huruf).
7. **Tiga migrasi** (16, 25, 13) — hanya dari desktop.
8. Sisanya 🟡.

⚠ **Catatan yang sudah saya sampaikan dua kali dan saya ulangi di sini:** antrean
keputusan (21 temuan terbuka) sekarang lebih panjang daripada nilai putaran audit
berikutnya. Audit yang temuannya menumpuk tanpa diputuskan berhenti menjadi audit dan
mulai menjadi daftar yang diabaikan — persis pola yang berulang kali ditemukan dokumen
audit itu sendiri.
