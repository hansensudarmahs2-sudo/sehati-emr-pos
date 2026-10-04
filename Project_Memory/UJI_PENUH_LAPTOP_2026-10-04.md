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
