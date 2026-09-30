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

### 4.5 Rincian kolom (nama diambil dari model, bukan dikarang)

Semua berkas memakai `pid` sebagai kunci pasien. `kid` = pseudonim kunjungan (boleh
`id_kunjungan` apa adanya — ia tidak mengidentifikasi orang di luar sistem, tapi
seragamkan penamaannya).

**`clinical_pasien_profil`** ← `pasien`
`pid`, `umur_tahun` (turunan dari `tgl_lahir`, **tgl_lahir TIDAK ikut**),
`kelompok_umur`, `jenis_kelamin`, `tipe_membership`, `sumber_referensi`
❌ tidak ikut: `nama`, `no_rm`, `nomor_ktp`, `alamat`, `nomor_telepon`,
`email_address`, `no_member`

**`clinical_visits`** ← `kunjungan`
`kid`, `pid`, `tgl_kunjungan`, `jenis_kunjungan`, `status_antrian`,
`sumber_pendaftaran`, `keluhan_utama`, `tgl_kontrol_selanjutnya`, `catatan_kontrol`,
`nama_dokter_assigned`
⚠ `keluhan_utama` dan `catatan_kontrol` adalah **teks bebas** — ikut membuat paket ini
rahasia, sama seperti `clinical_soap`.
❌ tidak ikut: `peresep_luar_nama`, `peresep_luar_asal` (nama dokter LUAR klinik —
pihak ketiga, tidak dibutuhkan analisis)

**`clinical_soap`** ← `pemeriksaan_klinis`
`kid`, `pid`, `nama_dokter`, `anamnesa`, `pemeriksaan_fisik`, `diagnosa`,
`saran_treatment`, `saran_produk`, `status_soap`, `waktu_konsultasi`, `created_at`
⚠ Hanya baris `status_soap='FINAL'`. Draf apoteker yang belum disetujui dokter
**bukan rekam medis** — mengirimnya ke analisis berarti menganalisis sesuatu yang
belum divalidasi siapa pun.

**`clinical_diagnosa`** ← `kunjungan_diagnosa` ⭐ *belum ada di ekspor*
`kid`, `pid`, `sistem_snapshot` (ICD10/ESTETIK), `kode_snapshot`, `nama_snapshot`,
`is_primer`, `urutan`

**`clinical_tindakan`** ← `kunjungan_tindakan`
`kid`, `pid`, `nama_treatment`, `status_tindakan`, `waktu_mulai`, `waktu_selesai`,
`nama_staf_pelaksana`, `nama_dokter_pelaksana`, `nama_perawat_pelaksana`
Model memang punya **tiga** kolom pelaksana terpisah (`id_staf_pelaksana`,
`id_dokter_pelaksana`, `id_perawat_pelaksana`) — persis yang diminta dr. Hansen.

**`clinical_resep`** ← `kunjungan_resep`
`kid`, `pid`, `nama_produk`, `kode_produk`, `golongan`, `qty`, `aturan_pakai`,
`status_item`, `nama_peresep` (dari `id_staf_input`), `waktu_serah`
❌ tidak ikut: harga, nominal — itu ranah `finance_pack`

**`clinical_racikan`** ← `kunjungan_racikan` + `kunjungan_racikan_bahan` ⭐ *belum ada*
`kid`, `pid`, `nama_snapshot`, `jenis_racik`, `jumlah_unit`, `aturan_pakai`,
`status_item`, dan per bahan: `nama_bahan`, `dosis_per_unit`, `satuan_dosis`,
`dipakai`, `satuan_dipakai`
❌ tidak ikut: `subtotal_bahan`, `biaya_racik`, `total`

**`clinical_followup`** ← `followup` ⭐ *belum ada*
`pid`, `kid`, `jenis`, `due_date`, `status` (PENDING/CONFIRMED/RESCHEDULED/
NO_ANSWER/CANCELLED), `waktu_handle`, `catatan`, `nama_staf_handler`
Inilah jejak yang menjawab "pasien kembali atau hilang".

### 4.6 ⚠ Pseudonim WAJIB mengikuti penggabungan pasien

`pasien` punya kolom **`digabung_ke_id_pasien`**. Kalau `pid` diberikan per baris pasien
apa adanya, **satu orang yang pernah tercatat dua kali akan muncul sebagai dua pasien
berbeda** di seluruh analisis — kasus berulangnya terpecah, riwayat kontrolnya terputus,
dan tidak ada gejala apa pun bahwa itu terjadi.

Aturan: telusuri `digabung_ke_id_pasien` sampai ujungnya, lalu berikan `pid` milik
**pasien yang bertahan**. Ini juga berarti paket klinis harus dibangun **setelah**
penggabungan pasien ganda dibereskan (kembar 217/218 di backlog), atau setidaknya
menyadari bahwa data sebelum penggabungan akan terpecah.

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
