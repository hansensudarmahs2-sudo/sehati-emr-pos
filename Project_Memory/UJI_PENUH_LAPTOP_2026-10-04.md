# Uji penuh di laptop — 2026-10-04

**Permintaan dr. Hansen: "jangan terhubung mini PC dulu, full test dalam laptop saja."**
Mini PC TIDAK disentuh sama sekali.

---

## 1. Kenapa "108 lulus" sebelumnya bukan hijau

Suite melaporkan **108 lulus / 32 dilewati**. Terlihat hijau. Tapi **31 dari 32 yang
dilewati punya satu sebab yang sama**: login gagal 401.

```
Login gagal (401): {"detail":"Username atau password salah."}
```

Yang dilewati itu bukan test pinggiran — ia **seluruh lapisan endpoint HTTP**:
`test_pasien_endpoints`, `test_kunjungan_endpoints`, `test_dokter_endpoints`,
`test_antropometri_endpoints`, `test_auth_endpoints`. Jadi selama ini setiap kali
dilaporkan "suite hijau di laptop", lapisan route/RBAC **tidak pernah dijalankan sekali
pun**. Itu pelajaran tentang cara membaca angka, bukan tentang kodenya: `pytest.skip`
berwarna sama dengan lulus di ringkasan.

Penyebabnya: `conftest.py` default ke `dokter_andi` / `password123`, dan di laptop
**hanya ada satu akun** — `hansen` (Superadmin), akun dr. Hansen sendiri.

### Yang dikerjakan supaya bisa jalan

| | |
|---|---|
| Akun uji | `uji_owner` (Owner) dan `uji_dokter` (Dokter) — **dibuat baru**; akun `hansen` tidak disentuh |
| Sandi | dibuat acak, disimpan di `.env` laptop (`.env` tidak pernah masuk repo — §6), tidak pernah ditampilkan |
| Data seed | `tools/seed_test_scenarios.py` → SEED-001/002/003 |

**Kenapa perannya Owner.** Tidak ada satu peran biasa yang memenuhi semua test:
registrasi pasien menuntut FO/Admin/Superadmin/Owner, sementara input medis menuntut
Dokter/Owner/Superadmin. Yang memenuhi keduanya hanya Owner atau Superadmin. ⚠
Konsekuensinya jujur: dengan akun Owner, **RBAC hampir tidak teruji** — test ini menguji
perilaku endpoint, bukan batas hak akses. Endpoint yang terlalu longgar tidak akan
tertangkap di sini.

Skrip seed menuntut DUA peran sekaligus (FO/Admin/Owner **dan** Dokter), itu sebabnya
ada dua akun.

### Hasilnya

| | Sebelum | Sesudah |
|---|---|---|
| Lulus | 108 | **137** |
| Dilewati | 32 | **1** |
| Gagal | 0 | **2** |

Satu yang masih dilewati: `test_komisi_report` butuh ≥2 staf — sekarang sudah ada 3,
tapi ia melewat karena alasan lain; tidak diselidiki.

---

## 2. DUA CACAT NYATA yang ditemukan — keduanya error 500

Keduanya muncul dari test yang **belum pernah berjalan sekali pun**. Bukan soal bentuk
data seed; keduanya `AttributeError` di dalam kode.

### 2a. `antropometri_service.py:239` memanggil metode yang tidak ada

```python
rows = self.kunjungan_repo.list_antropometri_pasien(id_pasien, limit=limit)
```

`list_antropometri_pasien` **tidak ada di mana pun** — bukan di
`KunjunganRepository`, bukan di kelas lain. Satu-satunya kemunculannya di seluruh repo
adalah panggilan ini.

Endpoint yang mati: `GET /api/v1/antropometri/pasien/{id_pasien}/timeline`
(grafik tracking antropometri).

### 2b. `pemeriksaan_repo.py:246` `get_treatment_selesai` salah TIGA nama kolom

```python
KunjunganTindakan.id_pasien      # tidak ada — hanya lewat id_kunjungan
KunjunganTindakan.status         # yang ada: status_tindakan
KunjunganTindakan.tgl_selesai    # yang ada: waktu_selesai
```

Kolom `KunjunganTindakan` yang sebenarnya: `id_kunjungan_tindakan, id_kunjungan,
id_treatment, status_tindakan, id_staf_pelaksana, id_dokter_pelaksana,
id_perawat_pelaksana, id_kuota_member, id_rencana, waktu_mulai, waktu_selesai`.

Seluruh fungsi ditulis terhadap model yang tidak pernah ada — ia **tidak mungkin pernah
berhasil**. Dipanggil `pemeriksaan_service.py:456` (`get_summary_pasien`), jadi endpoint
"Dashboard dokter saat konsultasi — 4 cardbox" (`dokter.py:112`) **selalu** 500.

⚠ **Koreksi dalam sesi ini:** saya sempat menyatakan fungsi ini tidak punya pemanggil
(grep saya keliru). Itu salah, dan membalik tingkat keparahannya — ini bukan kode mati,
ini endpoint hidup yang selalu gagal.

### Seberapa parah

Keduanya **tidak dipakai UI klinik**. Penelusuran `href`/`fetch` di 127 template:
nol rujukan ke `/api/v1/dokter/*` maupun `/api/v1/antropometri/*`. Jadi staf klinik tidak
menabraknya hari ini — itu juga sebabnya tidak ada yang pernah melaporkannya. Yang rusak
adalah permukaan API: siapa pun yang menyambungkannya nanti (atau modul analisis) dapat
500.

**Belum diperbaiki — menunggu keputusan dr. Hansen.** 2b hanya perlu tiga nama kolom
diperbaiki plus JOIN ke `kunjungan` untuk menjangkau pasien. 2a lebih dari tambal: perlu
metode repository baru, dan itu keputusan desain (timeline mengembalikan apa).

---

## 3. `pasien_pseudonim` tidak terdaftar di registry penggabungan pasien

`cek_gabung_pasien` bagian A **GAGAL**:

```
✗ BELUM TERDAFTAR (riwayat akan tertinggal diam-diam): pasien_pseudonim
  -> tambahkan ke TABEL_PINDAH, atau ke TABEL_DIKECUALIKAN beserta ALASANNYA
```

Tabel itu punya `id_pasien` tapi tidak ada di `TABEL_PINDAH` maupun
`TABEL_DIKECUALIKAN` (`audit_pasien_service.py:50-75`). Ia ditambahkan migrasi
`20260930_0200` — registrinya tidak ikut diperbarui. Pola §4.1: tabel baru, mekanisme
lama tidak diberi tahu.

### ⚠ Jebakannya justru di saran pemeriksa itu sendiri

Pemeriksa menawarkan dua pilihan, dan **pilihan pertama akan merusak**.
`clinical_export_service.pid_gabung()` membaca `pasien_pseudonim` untuk **kedua sisi**
penggabungan:

```python
dasar = {id_pasien: pid for ... "SELECT id_pasien, pid FROM pasien_pseudonim"}
...
lama      = dasar.get(int(r[0]))                      # pasien yang KALAH
bertahan  = dasar.get(gabung.get(int(r[0]), int(r[1])))
if lama and bertahan: rows.append({...})
```

Kalau barisnya DIPINDAHKAN saat penggabungan, `dasar.get(id_lama)` jadi `None`, barisnya
dilewati, dan **peta `pid_lama → pid_bertahan` hilang diam-diam**. Itu tepat berkas yang
dibuat supaya analis tidak melihat "satu pasien menghilang, pasien lain tiba-tiba
bertambah riwayat" dan menyimpulkan drop case palsu.

Jadi jawabannya: **`TABEL_DIKECUALIKAN`, dengan alasan bahwa barisnya WAJIB tetap di
tempat karena `pid_gabung` membaca kedua sisi.** Siapa pun yang membaca keluhan pemeriksa
ini dan "merapikannya" ke `TABEL_PINDAH` akan merusak jejak penggabungan ekspor klinis —
tanpa error.

**Belum diperbaiki** (perbaikannya ~5 baris, tanpa skema) — menunggu keputusan.

---

## 4. Tiga pemeriksa TIDAK BISA jalan di laptop — dan pagar itu benar

| Pemeriksa | Keadaan |
|---|---|
| `cek_top_diagnosa` | ⛔ diblokir seluruhnya |
| `cek_gabung_pasien` | bagian B–F diblokir (A jalan, dan A-lah yang menemukan §3) |
| `cek_clinical_pack` | bagian C–H diblokir — **16 lulus dari ~49** |

Sebabnya satu: ketiganya MEMBUAT dan MENGGABUNGKAN pasien uji, dan penggabungan tidak
bisa dibatalkan. Pagarnya menolak jalan kalau nama DB tidak memuat `dev`/`test`:

```
⛔ BERHENTI. Database 'db_sehati' punya 51 pasien dan namanya tidak memuat 'dev'/'test'.
```

**DB laptop bernama `db_sehati` — sama persis dengan produksi.** Jadi laptop, yang
seluruh gunanya adalah ruang coba-coba, diperlakukan sebagai produksi oleh pemeriksanya
sendiri.

⚠ **Jangan lepaskan pagarnya** (§5 melarang eksplisit). Jalan keluar yang benar adalah
**menamai DB laptop berbeda**, mis. `db_sehati_dev`. Itu membuka ~33 pemeriksaan yang
sekarang tidak pernah jalan. Biayanya: DB laptop harus dibangun ulang, dan §8
mengingatkan `create_all()` **kehilangan indeks UNIQUE** — jadi perlu dipikirkan, bukan
dikerjakan sambil lalu. **Menunggu keputusan dr. Hansen.**

---

## 5. Satu pemeriksa berteriak serigala

`cek_laporan_racikan` melaporkan **✗ "Bahan racikan MENEMPEL ke baris produk —
0 produk memuat pemakaian racikan"**.

Itu bukan cacat aplikasi. Di DB laptop, **setiap** baris `kunjungan_racikan_bahan`
punya `id_produk` KOSONG — bahannya non-inventori (`id_bahan`). Tidak ada bahan bertipe
produk sama sekali, jadi tidak ada yang bisa menempel. Datanya tidak mampu menguji itu.

Pemeriksa yang sama sudah punya konsep "dilewati" dan memakainya untuk dua uji lain di
bagian itu — tapi untuk yang ini ia melaporkan GAGAL. Pola yang sama dengan pemeriksa
urutan pid di `DESAIN_CLINICAL_PACK_TAHAP_B.md` §7: pemeriksa yang sering salah melatih
orang mengabaikannya.

Saya **tidak** bisa menyatakan jalur `qty_racikan` benar — ia hanya belum teruji di sini.

---

## 6. Pemeriksa baru: `cek_smoke_web.py` — 1235 halaman, 1 rusak

Karena login akhirnya bekerja, UI web bisa disapu sungguhan (itu guna laptop menurut §2).

Pemeriksa ini **menelusuri `href`**, bukan daftar route — introspeksi `app.routes`
ternyata tidak dapat diandalkan di sini (route `/web` tidak muncul walau requestnya
berhasil 200). Menelusuri tautan justru lebih berguna: yang diuji adalah apa yang
benar-benar bisa diklik, **termasuk tautan yang dirakit dari variabel template**.

```
1235 halaman dibuka · 1234 OK · 1 BERMASALAH
  ✗ 422  /web/kasir/tagihan/None
```

### Sebabnya, dan kenapa ini soal uang

`transaksi_kasir.id_kunjungan` **boleh NULL**, dan transaksi `jenis_transaksi =
MEMBERSHIP` memang tidak terikat kunjungan. Tiga template merender tautannya tanpa
memeriksa itu:

| Template | Baris |
|---|---|
| `reports_void.html` | 117 |
| `kasir_cari_transaksi.html` | 101, 106 |

Di DB laptop ada **3 transaksi MEMBERSHIP berstatus VOID** dengan `id_kunjungan NULL`.
Artinya di **laporan void** — tempat orang mencari uang yang dibatalkan — barisnya muncul
dengan tautan yang pasti error. Orang yang sedang mengaudit uang void mengklik, dan dapat
halaman error 422.

Perbaikannya kecil: jangan render tautannya kalau `it.id_kunjungan` kosong.
**Belum diperbaiki — menunggu keputusan.**

⚠ Smoke ini jalan sebagai **Owner**. Akun berperan sempit akan membuka lebih sedikit
halaman — bukan menemukan lebih sedikit masalah.

---

## 7. Yang BERSIH

| Pemeriksa | Hasil |
|---|---|
| `cek_phi_tracked.sh` | BERSIH — tidak ada PHI dilacak git |
| `cek_nik` | 8 lulus, 0 gagal |
| `cek_finance_pack` | 5 lulus, 0 gagal |
| `cek_tunda_item` | 5 lulus, 0 gagal |
| `cek_tebus_resep` | 5/5 pagar benar |
| `cek_serah_tanpa_lot` (Temuan 30) | 0 temuan, 3 tidak dapat dinilai |
| `cek_clinical_pack` bagian A–B | 16 lulus, 0 gagal |
| `cek_kelas_tailwind` | **0 kelas WARNA/LATAR hilang** (213 nama komponen lain) — kategori yang berbahaya bersih, sesuai §4.2 |
| `cek_soap_basi` | dilewati — tidak ada produk yang cocok untuk uji |

---

## 8. Yang MASIH tidak bisa diuji di laptop

| Apa | Kenapa |
|---|---|
| Ekspor paket klinis ujung-ke-ujung | `BACKUP_RECIPIENT` hanya ada di desktop (§6) |
| 3 pemeriksa di §4 | pagar nama DB — lihat §4 |
| Jalur `qty_racikan` di laporan | tidak ada bahan racikan bertipe produk di DB laptop |
| RBAC / batas hak akses | smoke & suite jalan sebagai Owner — lihat §1 |
| Apa pun tentang keadaan klinik sungguhan | laptop tidak punya data klinik |

---

## 9. Catatan: data uji yang DITINGGAL di laptop

Sengaja, supaya uji ini bisa diulang:

- akun `uji_owner` (Owner) dan `uji_dokter` (Dokter) — sandi di `.env`
- pasien `SEED-001/002/003` (bersihkan: `python ../tools/seed_test_scenarios.py --cleanup`)
- pasien `A-T901/A-T902` (Tahap B)

⚠ Juga ditemukan **44 pasien sisa "Booking Test VIP/VVIP"** (22 pasang) yang menumpuk
dari test booking berulang — test itu tidak membersihkan datanya. Belum dibersihkan;
bukan bagian dari permintaan ini, tapi itu sebabnya DB laptop punya 51 pasien dan
karenanya memicu pagar di §4.

---

# Perbaikan dua cacat 500 — 2026-10-04

Atas permintaan dr. Hansen. Keduanya diperbaiki; keduanya dibuktikan mengembalikan
**data nyata**, bukan sekadar berhenti 500.

## 1. `list_antropometri_pasien` → metodenya sudah ada dengan nama lain

Dugaan awal saya di §2a — "perlu metode repository baru, dan itu keputusan desain" —
**salah**. Metodenya sudah lama ada:

| | |
|---|---|
| Dipanggil service | `list_antropometri_pasien` ← tidak ada di mana pun |
| Yang benar-benar ada | `kunjungan_repo.list_antropometri_timeline` (baris 306) |

Tanda tangan `(id_pasien, limit=50)`, kembalian `list[KunjunganAntropometri]`, urut
`created_at DESC`, JOIN lewat `Kunjungan` — **cocok persis** dengan yang dibutuhkan
`get_timeline`. Dan ia **tidak punya satu pemakai pun**: ditulis, tidak pernah
disambungkan. Dua sisi dengan dua nama — CLAUDE.md §4.1 dalam bentuk paling sederhana.

Jadi perbaikannya **satu nama**, bukan metode baru. Pelajarannya: sebelum menulis
fungsi yang "hilang", cari dulu apakah ia ada dengan nama lain.

## 2. `get_treatment_selesai` → EMPAT kesalahan, bukan tiga

§2b menyebut tiga nama kolom salah. Setelah diperiksa lebih jauh, ada **empat**, dan
yang keempat yang paling halus:

| Ditulis | Kenyataannya |
|---|---|
| `KunjunganTindakan.id_pasien` | tidak ada — pasien hanya lewat `kunjungan` |
| `KunjunganTindakan.status` | namanya `status_tindakan` |
| `KunjunganTindakan.tgl_selesai` | namanya `waktu_selesai` |
| **`== "COMPLETED"`** | **enumnya `PENDING`/`PROSES`/`SELESAI`** — "COMPLETED" tidak akan pernah cocok |

Yang keempat adalah jebakan §4.5: seandainya tiga nama kolomnya benar, fungsi ini akan
**berjalan tanpa error dan selalu mengembalikan daftar kosong** — cardbox-nya kosong
tanpa ada yang tahu kenapa. Nama kolom yang salah justru menyelamatkan: ia berteriak.

**Arity-nya juga salah.** Pemanggil membongkar TIGA nilai (`for tindakan, tr, kj in
treatment_rows`) dan memakai `kj.tgl_kunjungan`; repo mengembalikan 2-tuple. Perbaikannya
mencerminkan `get_produk_dibeli` yang bersebelahan — dua cardbox tetangga tidak boleh
memakai sumber tanggal berbeda.

## Bukti, bukan hanya "tidak crash"

```
GET /api/v1/antropometri/pasien/348/timeline -> 200
   total baris: 3
     BB=65.0 TB=160.0 BMI=25.4
     BB=64.2 TB=160.0 BMI=25.1
     BB=63.5 TB=160.0 BMI=24.8

GET /api/v1/dokter/pasien/348/summary -> 200
   cardbox treatment SELESAI: 3 baris
     2026-09-27  Basic Treatment
     2026-09-20  Basic Treatment
     2026-09-13  Basic Treatment
```

Suite: **138 lulus** (dari 137), 1 gagal, 1 dilewati.

---

# TEMUAN BARU — `created_at` dipakai sebagai TANGGAL KLINIS

Satu test masih gagal, dan sebabnya **bukan** kedua cacat di atas. Ini hal ketiga yang
berbeda, ditemukan justru karena endpointnya akhirnya hidup.

`test_summary_pasien_seed_sari_has_soap_history` menuntut ≥3 SOAP. DB **punya** 3:

| id_pemeriksaan | kunjungan | tgl_kunjungan | created_at |
|---|---|---|---|
| 26 | 267 | 2026-09-13 | 2026-10-04 |
| 27 | 268 | 2026-09-20 | 2026-10-04 |
| 28 | 269 | 2026-09-27 | 2026-10-04 |

Tiga **kunjungan berbeda**, tapi endpoint mengembalikan **1**. Penyebabnya fitur yang
disengaja di `get_riwayat_soap` (baris 194-197):

> *"DEDUPE per tanggal: kalau ada multiple SOAP di hari yang sama (mis. dokter Ubah
> Konsul beberapa kali), hanya ambil yang TERBARU."*

Niatnya benar. Kuncinya yang salah: ia memakai tanggal **`created_at`** — kapan
catatannya DITULIS — bukan kunjungan mana yang dicatat. Akibatnya dua hal yang sangat
berbeda diperlakukan sama:

| Yang dimaksud | Yang juga kena |
|---|---|
| 3× "Ubah Konsul" untuk SATU kunjungan → tampil 1 (benar) | SOAP untuk TIGA kunjungan berbeda yang ditulis di hari yang sama → tampil 1 (**salah**) |

Kapan ini terjadi di klinik sungguhan: **dokter menyusul menulis catatan beberapa
kunjungan dalam satu sesi duduk.** Riwayat pasiennya lalu menampilkan satu entri, dan
dua kunjungan lain hilang dari pandangan dokter — tanpa error, tanpa penanda.

Kunci yang tepat adalah **per `id_kunjungan`** (SOAP terbaru per kunjungan), karena
itulah yang sebenarnya dimaksud "Ubah Konsul beberapa kali".

## Akarnya sama di tempat lain

Timeline antropometri yang baru diperbaiki memakai pola yang sama:

```python
tgl_ukur=antro.created_at
```

Buktinya di keluaran di atas: tiga pengukuran September semuanya tampil `2026-10-04`.
Untuk grafik tracking berat badan, itu berarti pengukuran yang diisi menyusul **menumpuk
di satu titik** pada sumbu waktu — grafiknya terlihat datar padahal pasiennya turun 1,5 kg.

Dan di cardbox SOAP, `tanggal=soap.created_at` juga — kartunya menampilkan kapan catatan
ditulis, bukan kapan pasien datang.

⚠ **BELUM DIPERBAIKI — menunggu keputusan dr. Hansen**, karena ini **mengubah apa yang
dilihat dokter di layar**, bukan menambal error. Tiga tempat terlibat:

| Tempat | Sekarang | Usul |
|---|---|---|
| `get_riwayat_soap` dedupe | per tanggal `created_at` | per `id_kunjungan` |
| `SoapRingkasItem.tanggal` | `created_at` | `kunjungan.tgl_kunjungan` |
| `AntropometriTimelineItem.tgl_ukur` | `created_at` | `kunjungan.tgl_kunjungan` |

Catatan jujur: `created_at` tetap berguna dan jangan dibuang — "kapan ditulis" adalah
informasi audit yang sah. Yang salah adalah memakainya **sebagai tanggal klinis**.

---

# ✅ Perbaikan `created_at` sebagai tanggal klinis — 2026-10-04

Atas permintaan dr. Hansen. **Lima berkas**, karena repositori yang diperbaiki punya
empat pemanggil — tiga di antaranya **route UI web**, jadi cacatnya memang memengaruhi
layar klinik, bukan hanya API. Itu lebih berat daripada yang saya laporkan semula.

## Yang diubah

| Berkas | Perubahan |
|---|---|
| `pemeriksaan_repo.get_riwayat_soap` | dedupe per **`id_kunjungan`** (dulu per tanggal `created_at`); urut `tgl_kunjungan DESC, created_at DESC`; mengembalikan **tiga** nilai |
| `pemeriksaan_service.get_summary_pasien` | `tanggal=kj.tgl_kunjungan` |
| `web/routes/dokter.py:304` | arity saja — layar itu mengambil tanggalnya dari sumber lain |
| `web/routes/pasien.py` ×2 | arity + `"tanggal"` dari `kj.tgl_kunjungan` |
| `kunjungan_repo.list_antropometri_timeline` | urut `tgl_kunjungan DESC`; mengembalikan `(antro, kunjungan)` |
| `antropometri_service.get_timeline` | `tgl_ukur=kunjungan.tgl_kunjungan` |

Urutan `tgl_kunjungan DESC, created_at DESC` dipilih supaya baris **pertama** tiap
kunjungan adalah SOAP terbaru untuk kunjungan itu — persis yang dimaksud dedupe. Dan
urutan luarnya kini kronologi **klinis**, bukan kronologi penulisan.

`id_kunjungan` NOT NULL di `pemeriksaan_klinis` (diperiksa di DB), jadi kunci dedupe tidak
pernah `None` dan tidak ada risiko semua baris luruh ke satu kunci.

## Yang SENGAJA tidak disentuh

`get_antropometri_terakhir` tetap memakai `updated_at`/`created_at` — **keputusan
dr. Hansen di smoke test Week 4**: yang terakhir di-EDIT yang menang, supaya koreksi row
lama muncul di header. Di sana pertanyaannya "nilai mana yang terakhir dikoreksi", bukan
"kapan diukur". Docstring-nya kini menyebut eksplisit jangan ikut diubah.

`created_at` juga tetap ada di mana-mana sebagai jejak audit. Yang salah bukan kolomnya —
yang salah memakainya sebagai tanggal klinis.

## Dibuktikan TIGA ARAH

| Arah | Hasil |
|---|---|
| Tiga kunjungan (13/20/27 Sep) yang SOAP-nya ditulis 4 Okt | **3 baris** (sebelum: 1) |
| Dedupe masih bekerja: 2 SOAP tambahan untuk SATU kunjungan | tetap **1 baris per kunjungan**, dan yang terpilih **"Ubah Konsul ke-2"** = TERBARU |
| `tgl_ukur` antropometri lewat endpoint | tiga tanggal September **berbeda**, bukan 2026-10-04 |

Arah kedua yang terpenting: ia membuktikan perbaikan ini **tidak membuang** fitur yang
memang diinginkan. Tanpa arah itu, saya hanya membuktikan dedupe-nya mati.

### Nilai praktisnya terlihat di arah ketiga

```
tgl_ukur=2026-09-27  BB=63.5  BMI=24.8
tgl_ukur=2026-09-20  BB=64.2  BMI=25.1
tgl_ukur=2026-09-13  BB=65.0  BMI=25.4
```

Tren **65,0 → 64,2 → 63,5 kg** — turun 1,5 kg dalam dua minggu. Sebelum perbaikan ketiga
titik ini menumpuk di satu tanggal, jadi grafiknya terlihat **datar**.

### Diverifikasi juga di layar sungguhnya

| Halaman | Tanggal September tampil | Tanggal 4 Oktober tampil |
|---|---|---|
| `/web/pasien/{id}` | 13, 20, 27 September | **tidak ada** |
| `/web/pasien/{id}/riwayat` | 13, 20, 27 September | **tidak ada** |

## Hasil uji

| | |
|---|---|
| Suite | **139 lulus / 0 gagal / 1 dilewati** — hijau penuh untuk pertama kalinya |
| `cek_smoke_web` | 1273 halaman · 1272 OK · 1 bermasalah (`/web/kasir/tagihan/None`, temuan terpisah §6 yang belum diminta diperbaiki) |

---

# ✅ Perbaikan tautan `/web/kasir/tagihan/None` — 2026-10-04

Atas permintaan dr. Hansen. Menyapu **semua** titik yang merakit URL halaman tagihan
lebih dulu, bukan hanya yang ditemukan smoke — dan sapuan itu menemukan sesuatu yang
jauh lebih serius daripada tautan 422.

## 🔴 Temuan saat memperbaiki: rekam tagihan PASIEN LAIN terbuka

`pasien_membership.html:364` memasukkan **`id_transaksi`** ke URL yang parameternya
**`id_kunjungan`**:

```html
<a href="/web/kasir/tagihan/{{ h.id_transaksi_aktivasi }}">#{{ h.id_transaksi_aktivasi }}</a>
```

Itu bukan masalah `None` — itu **penomoran yang salah sama sekali**. Dua urutan id yang
berbeda, dan nomornya bertabrakan:

| `id_transaksi_aktivasi` | membership milik | kunjungan bernomor sama | pemilik kunjungan itu |
|---|---|---|---|
| 1 | pasien **2** | kunjungan 1 | pasien **1** |
| 50 | pasien **2** | kunjungan 50 | pasien **41** |

Dibuktikan ujung ke ujung lewat UI sungguhan dengan login nyata — dari halaman
membership **A-T902**:

```
klik /web/kasir/tagihan/1  -> 200 · halaman menampilkan A-T901
klik /web/kasir/tagihan/50 -> 200 · halaman menampilkan BKT-1791088098-591
```

Keduanya **status 200**, halaman tagihan yang tampak normal, untuk orang yang salah.
Tanpa error, tanpa peringatan. Satu klik biasa dari halaman pasien membuka rekam
keuangan pasien lain — ini wilayah §6, bukan sekadar tautan rusak.

⚠ **Smoke saya melewatkannya** karena ia hanya memeriksa kode status, dan `200` bisa
berarti SALAH. Itu kelemahan pemeriksa saya, bukan kebetulan.

### Kenapa diperbaiki jadi teks biasa, bukan tautan yang benar

Tujuan yang benar ber-kunci transaksi **ada**: `/web/kasir/nota/{id_transaksi}/cetak`.
Tapi ia menuntut `require_kasir_role`, sedangkan halaman membership sengaja boleh
dilihat **semua peran** (FO, kasir, dokter, owner). Menautkannya berarti dokter dan
perawat menabrak 403 — itu keputusan hak akses, bukan perbaikan bug, jadi bukan porsi
saya. Nomor transaksinya tetap tampil (`#50`, `#1`), hanya tidak bisa diklik.

**Pilihan untuk dr. Hansen:** tautkan ke nota dan tampilkan tautannya hanya untuk peran
Kasir/Admin/Owner. Sekitar 4 baris. Sampai itu diputuskan, nomor saja sudah cukup untuk
rujukan silang dan tidak membocorkan apa pun.

## Tiga titik `None` yang diperbaiki

| Tempat | Dulu | Sekarang |
|---|---|---|
| `reports_void.html:117` | nomor transaksi selalu jadi tautan | tautan hanya kalau ada `id_kunjungan`; kalau tidak, teks kelabu + tooltip |
| `kasir_cari_transaksi.html:101` | tombol **Detail** selalu muncul | tombol hanya kalau ada kunjungan; kalau tidak, `—` |
| `kasir_cari_transaksi.html:106` | tombol **⚡ Force Void** | ikut dipagari |
| `web/routes/kasir.py` | `can_force_void` tidak memeriksa `id_kunjungan` | ikut disyaratkan |

Yang terakhir diperbaiki **di sumbernya**, bukan hanya di template: flag itu dulu
mengaku "boleh force void" untuk transaksi yang jalur UI-nya tidak ada. Hari ini
tombolnya belum muncul karena `days_past = 0`; **besok akan muncul**. Jadi ia bug laten,
bukan bug yang sudah terlihat.

⚠ Catatan jujur: kemampuan force-void-nya sendiri **ADA** di server —
`POST /kasir/transaksi/{id_transaksi}/void` dan `.../force-void`, ber-kunci transaksi.
Yang belum ada hanya halaman UI untuk memanggilnya. Jadi transaksi membership **belum
bisa di-void dari layar** sampai halaman itu ada. Dicatat, bukan dikerjakan.

## Pemeriksa diperkuat — dan ini pelajarannya

`cek_smoke_web.py` sekarang mencari segmen URL kosong (`None`/`undefined`/`null`)
**langsung di HTML**, bukan dengan mengikuti tautannya. Bedanya penting: ia tetap
melaporkan walau tautannya membalas 200, dan ia **menyebut halaman mana yang
merendernya** — informasi yang justru dibutuhkan untuk memperbaiki, dan yang versi
kode-status tidak pernah berikan.

Diuji dua arah:

| | Hasil |
|---|---|
| Dengan perbaikan | 1291 halaman · **0 bermasalah · 0 segmen kosong** |
| Perbaikan dilepas (`git stash`) | **1 bermasalah + 1 segmen kosong**, berikut asalnya: `dirender di: /web/kasir/cari-transaksi` |

⚠ Yang **tidak** bisa ditangkap crawler mana pun: id yang salah JENIS tapi benar
bentuknya — persis kasus membership di atas. Itu hanya tertangkap dengan membaca
template. **Jangan percaya "0 bermasalah" sebagai bukti bahwa semua tautan menunjuk ke
rekam yang BENAR.** Peringatan itu kini ada di docstring pemeriksanya.

## Hasil uji

| | |
|---|---|
| Suite | **139 lulus / 0 gagal / 1 dilewati** |
| `cek_smoke_web` | **1291 halaman · 1291 OK · 0 bermasalah** — bersih sepenuhnya, pertama kali |
| `cek_kelas_tailwind` | 3 template yang disunting: 0 kelas hilang (§4.2) |

---

# ✅ Tautan nota aktivasi membership, dipagari peran Kasir — 2026-10-04

Keputusan dr. Hansen. Nomor transaksi aktivasi di halaman membership kini **tertaut ke
nota** (`/web/kasir/nota/{id_transaksi}/cetak?paper=a5`, tab baru), bukan lagi teks mati.

## Nota memang tujuan yang benar — diverifikasi, bukan diasumsikan

`print_service.py:93` sudah menangani kasus ini dengan sengaja:

> *"M2/M3: transaksi MEMBERSHIP (id_kunjungan NULL) -> pasien via trx.id_pasien"*

JOIN ke `kunjungan` di sana memang `isouter=True`. Jadi nota sanggup menampilkan
transaksi membership yang tidak terikat kunjungan — berbeda dari halaman tagihan yang
mustahil.

## DUA pagar, dan keduanya perlu

### 1. Pagar PERAN — `can_lihat_nota = require_kasir_role(user)`

Halaman membership sengaja boleh dilihat **semua peran**, sedangkan nota menuntut
Kasir/Admin/Owner/Superadmin. Tanpa pagar ini dokter & perawat akan menabrak 403 setiap
kali mengklik. Mereka tetap melihat nomornya sebagai teks untuk rujukan silang.

### 2. Pagar DATA — `trx_milik_pasien`

Ini yang tidak diminta tapi harus ada, dan alasannya ketemu justru saat mengerjakan ini.
Di data laptop ada baris `pasien_membership_history` milik **pasien 2** yang
`id_transaksi_aktivasi`-nya menunjuk **transaksi pasien 1**:

| trx | pemilik membership | pasien di transaksi | jenis |
|---|---|---|---|
| 1 | pasien **2** | pasien **1** (A-T901) | KLINIS |
| 50 | pasien 2 | pasien 2 (A-T902) | MEMBERSHIP ✓ |

Nota ber-kunci `id_transaksi` dan **tidak tahu** dari halaman pasien mana ia dibuka —
ia tidak bisa memverifikasi apa pun. Jadi tanpa pagar data, tautan baru ini akan
mengulang kebocoran yang baru saja ditutup, hanya lewat pintu lain.

Route kini mengumpulkan transaksi yang memang milik pasien itu (satu query, dua jalur
karena `transaksi_kasir` punya `id_pasien` SENDIRI di samping `id_kunjungan` — §4.1), dan
template hanya menautkan yang ada di himpunan itu.

⚠ **Baris trx 1 itu sampah data uji, bukan cacat kode.** Penulisnya benar:
`membership_service.py:508` menetapkan `hist.id_transaksi_aktivasi = trx.id_transaksi`
dari transaksi yang baru dibuat untuk pasien itu sendiri. Jadi pagar data ini jaring
pengaman terhadap data yang seharusnya tidak ada — bukan tambalan untuk alur yang rusak.
**Perlu diperiksa di mini PC** apakah ada baris semacam itu di data sungguhan:

```sql
SELECT h.id_history, h.id_pasien AS pemilik, t.id_pasien AS pasien_di_transaksi
  FROM pasien_membership_history h
  JOIN transaksi_kasir t ON t.id_transaksi = h.id_transaksi_aktivasi
  LEFT JOIN kunjungan k ON k.id_kunjungan = t.id_kunjungan
 WHERE h.id_transaksi_aktivasi IS NOT NULL
   AND h.id_pasien NOT IN (COALESCE(t.id_pasien, 0), COALESCE(k.id_pasien, 0));
```

## Diverifikasi TIGA ARAH

| Arah | Hasil |
|---|---|
| Peran Kasir, trx **50** (memang milik pasien 2) | **tertaut** → nota 200, menampilkan **A-T902** = orang yang BENAR |
| Peran Kasir, trx **1** (milik pasien 1) | **teks biasa** — pagar data menyala |
| Peran **Dokter** | halaman tetap terbuka, semua nomor teks biasa, **nol** tautan nota (tidak ada jebakan 403) |

Arah kedua yang paling berarti: ia membuktikan pagar datanya benar-benar bekerja, bukan
hanya ada di kode.

## Hasil uji

| | |
|---|---|
| Suite | **139 lulus / 0 gagal / 1 dilewati** |
| `cek_smoke_web` | **1310 halaman · 1310 OK · 0 bermasalah · 0 segmen kosong** |
| `cek_kelas_tailwind` | `pasien_membership.html`: 0 kelas hilang |
