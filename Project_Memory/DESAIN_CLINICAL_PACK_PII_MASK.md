# DESAIN — Clinical Pack ber-PII-mask untuk Oracle / Council AI

Tanggal: 2026-09-30. Status: **rancangan, BELUM dibangun.**

---

## 1. Keadaan sekarang — TIDAK ADA pengecualian privasi

Diperiksa kolom per kolom pada 15 berkas ekspor (`_export_columns.py`):

| Berkas | Yang keluar apa adanya |
|---|---|
| `visits_raw` | `no_rm`, `nama_pasien`, **`keluhan_utama`** |
| `transactions_header_raw` | `no_rm`, `nama_pasien` |
| `membership_raw` | `no_rm`, `nama_pasien` |
| `medical_soap_raw` | `anamnesa`, `pemeriksaan_fisik`, `diagnosa`, `nama_dokter`, `id_pasien` |

**Tidak ada satu pun mekanisme penyamaran.** `FINGERPRINT_EXCLUDE`
(`{staff_activity_raw, medical_soap_raw}`) **bukan pelindung privasi** — ia hanya
mencegah aktivitas login mengacaukan deteksi perubahan. Jangan disangka sebagai pagar.

Dan paket ini bernama `finance_pack`. SOAP medis sudah ikut keluar setiap hari di dalam
paket keuangan — berkas `12_medical_soap_raw.csv` yang sama, yang hampir ter-rsync ke
server dan dibersihkan dari riwayat git 2026-09-29.

---

## 2. Tujuan

Menyediakan paket **klinis** untuk alur: Sehati → `data_analyst` (dirapikan) →
**Council AI** (ada medical officer di sana). Analisis bukan urusan Sehati
([[sehati-ekosistem-analisa]]); Sehati hanya menyediakan bahan.

Isi yang dibutuhkan dr. Hansen: anamnesa, pemeriksaan fisik, diagnosa, tindakan,
peresepan, **dokter yang meresepkan**, **yang menindak**, **perawat yang menindak**.

Identitas pasien **tidak dibutuhkan** untuk analisis.

---

## 3. Keputusan dr. Hansen (2026-09-30)

### 3.1 Pseudonim BISA DIBALIK, petanya tinggal di Sehati

Tabel pemetaan `pseudonim → id_pasien` **hanya ada di Sehati**, tidak pernah ikut keluar.
Analis bekerja tanpa identitas; kalau ada temuan penting, dr. Hansen bisa melacaknya
balik lewat Sehati.

⚠ **Peta itu menjadi berkas paling sensitif di sistem** — ia satu-satunya yang
menyambungkan seluruh riwayat klinis ke orang sungguhan. Perlakukan seperti kunci
enkripsi backup: tidak ikut git (gerbang PHI sudah menangkap pola `*_map*`? **periksa dan
tambahkan polanya**), tidak ikut rsync, tidak ikut paket ekspor mana pun.

**Pseudonim WAJIB stabil lintas waktu dan lintas berkas.** Kalau pasien yang sama
mendapat pseudonim berbeda di ekspor bulan depan, seluruh analisis longitudinal
(kasus berulang, drop case) runtuh tanpa gejala. Gunakan nilai tetap yang disimpan,
bukan hash yang dihitung ulang tiap ekspor dengan salt yang bisa berubah.

### 3.2 Teks bebas dikirim APA ADANYA — paket tetap rahasia

[dr. Hansen] memilih teks utuh: bahan analisis paling kaya, dan Council AI bisa membaca
nuansanya.

⚠ **Konsekuensi yang harus dipegang, bukan dilupakan:**

Anamnesa sering memuat nama orang (*"diantar suaminya Pak Budi"*), nomor telepon, alamat.
Menyamarkan kolom tapi mengirim teks utuh berarti **identitas hanya berpindah dari kolom
ke kalimat**. Penyamaran kolom **mengurangi** paparan, tidak menghapusnya.

**Karena itu paket klinis TETAP data rahasia**, setara backup database:
- folder drop terbatas, hak akses jelas
- **tidak boleh** masuk git, cloud, atau folder tersinkron
- masuk gerbang PHI pra-commit (`scripts/cek_phi_tracked.sh`)
- sebaiknya terenkripsi saat diam, seperti backup `age`

**Jangan pernah menyebut paket ini "anonim".** Ia **pseudonim** — dan di klinik kecil,
diagnosa langka + tanggal sudah cukup untuk mengenali orang.

---

## 4. Bentuk yang diusulkan

### 4.1 Paket TERPISAH dari finance

`clinical_pack/`, bukan menumpang `finance_pack/`. Hak akses dan jalur keluar berbeda.
`medical_soap_raw` **dikeluarkan** dari finance pack — modul Finance tidak memakainya
untuk jurnal (sudah dipastikan: ia ada di `FINGERPRINT_EXCLUDE` justru karena tidak
dipakai).

### 4.2 Penyamaran terjadi SAAT MENULIS, bukan sesudahnya

Kolom identitas **tidak pernah ditulis** ke paket klinis. Bukan "ekspor lalu bersihkan" —
berkas antara yang memuat identitas tidak boleh pernah ada.

### 4.3 Isi paket klinis (usulan)

| Berkas | Isi | Pseudonim |
|---|---|---|
| `clinical_visits` | tgl, jenis kunjungan, keluhan_utama, status | `pid` (bukan `id_pasien`/`no_rm`/`nama`) |
| `clinical_soap` | anamnesa, pemeriksaan fisik, diagnosa teks, saran | `pid` + `nama_dokter` (staf, tetap) |
| `clinical_diagnosa` | **`kunjungan_diagnosa`**: sistem (ICD10/ESTETIK), kode, nama, is_primer | `pid` |
| `clinical_tindakan` | treatment, status, **pelaksana/perawat** | `pid` + nama staf |
| `clinical_resep` | produk, qty, aturan pakai, **peresep** | `pid` + nama staf |
| `clinical_racikan` | racikan + bahannya | `pid` |
| `clinical_followup` | **`followup`**: due_date, status (NO_ANSWER/CANCELLED), waktu handle | `pid` |
| `clinical_pasien_profil` | umur/kelompok umur, jenis kelamin — **tanpa** nama/RM/tgl lahir persis | `pid` |

Empat yang dicetak tebal adalah tabel yang **saat ini tidak ikut ekspor sama sekali**
(lihat [[sehati-ekosistem-analisa]]) — tanpa `kunjungan_diagnosa` dan `followup`, modul
analisis menerima narasi tanpa kode dan tanpa jejak kontrol.

**Umur, bukan tanggal lahir.** Tanggal lahir persis adalah pengidentifikasi kuat;
umur (atau kelompok umur) menjawab pertanyaan klinis yang sama dengan risiko jauh lebih
kecil.

### 4.4 Pakai ulang pola yang sudah ada

File-drop + `smart_export` sidik jari isi, seperti jembatan Finance
([[sehati-finance-bridge]]): Sehati menulis, penerima memindai sendiri, Sehati tidak
pernah dihubungi. **Jangan bangun mekanisme baru.**

---

## 5. Yang belum diputuskan

- Rentang waktu default paket klinis (bulan berjalan? sejak awal?)
- Apakah `data_analyst` menerima langsung, atau lewat folder perantara
- Siapa yang boleh menjalankan ekspor klinis (usulan: Owner/Superadmin saja — lebih ketat
  daripada ekspor finance)
- Retensi: berapa lama paket lama disimpan di folder drop sebelum dihapus

---

## 6. Sebelum dibangun

1. Tambahkan pola peta pseudonim ke `scripts/cek_phi_tracked.sh` **sebelum** tabelnya ada
   — supaya tidak ada jendela waktu ia bisa ter-commit.
2. Pastikan folder drop klinis tidak berada di bawah folder repo atau folder tersinkron.
3. Migrasi untuk tabel peta pseudonim → **minta persetujuan dr. Hansen**.
