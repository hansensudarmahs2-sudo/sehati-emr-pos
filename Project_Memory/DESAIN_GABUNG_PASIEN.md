# DESAIN — Penggabungan pasien ganda

Tanggal: 2026-09-30. Status: **rancangan, belum dibangun.** Langkah 2 dari
`RENCANA_KERJA_2026-09-30.md`.

---

## 1. Keadaan nyata (diperiksa, bukan diasumsikan)

**Tidak ada data yang perlu diperbaiki sekarang.** Kueri ke `db_sehati`:

- tidak ada pasien dengan `digabung_ke_id_pasien` terisi
- tidak ada pasien nonaktif
- **pasien 217 & 218 sudah tidak ada** — ikut terhapus saat DB di-wipe 18 September

Catatan backlog "kembar 217/218" karena itu **kedaluwarsa**. Yang dibangun adalah
**kemampuannya**, sebelum data pasien asli masuk — dan itu waktu terbaik, karena menguji
penggabungan pada data dummy tidak bisa merusak apa pun.

## 2. Yang SUDAH ada

`AuditPasienService` (#18) punya `scan()`, `dismiss()`, `nonaktifkan()`, `aktifkan()`.
`nonaktifkan(digabung_ke=...)` sudah berpagar baik: menolak menunjuk diri sendiri,
menolak tujuan yang juga nonaktif, mewajibkan alasan, mencatat jumlah riwayat ke audit,
dan bisa dibatalkan.

**⚠ Yang TIDAK dilakukannya: memindahkan apa pun.** `digabung_ke_id_pasien` hanya
penanda, dan **tidak ada satu pun query yang membacanya** (diperiksa: hanya
`audit_pasien_service` yang menyentuhnya, untuk mengisi/menghapus/menampilkan).

Jadi penggabungan yang ada sekarang **kosmetik**: riwayat pasien tetap terpecah di setiap
layar dan setiap laporan.

## 3. Keputusan dr. Hansen (2026-09-30)

### 3.1 Riwayat DIPINDAHKAN ke pasien yang bertahan

Bukan "penanda diikuti saat membaca". Baris di-UPDATE menunjuk pasien yang bertahan,
sehingga seluruh layar dan laporan langsung benar tanpa menyisir puluhan query.

⚠ **Konsekuensi yang diterima:** baris historis ditulis ulang. Nota lama yang sudah
tercetak memuat nama pasien duplikat tidak lagi cocok dengan datanya. Karena itu
`audit_log` **wajib** memuat jejak lengkap: id asal, id tujuan, dan jumlah baris per
tabel — itu satu-satunya bukti bahwa data pernah berada di identitas lain.

### 3.2 Membership ganda → TOLAK, selesaikan manual

Kalau KEDUA pasien punya membership aktif atau sisa kuota, penggabungan **ditolak**
dengan pesan jelas. Tidak menjumlahkan kuota (bisa menciptakan nilai yang tak pernah
dibayar), tidak melepas begitu saja (pasien kehilangan yang sudah dibayar).

Keputusan itu diambil orang, bukan aturan otomatis.

## 4. Daftar tabel — INI adalah spesifikasinya

Dari `information_schema`, bukan dari model (model bisa tertinggal). **13 tabel**
dipindahkan:

| Tabel | Kolom |
|---|---|
| `kunjungan` | `id_pasien` |
| `pemeriksaan_klinis` | `id_pasien` |
| **`transaksi_kasir`** | **`id_pasien`** ⚠ |
| `komisi_ledger` | `id_pasien` |
| `followup` | `id_pasien` |
| `jadwal_booking` | `id_pasien` |
| `kunjungan_foto` | `id_pasien` |
| `pasien_alergi` | `id_pasien` |
| `pasien_penyakit_kronis` | `id_pasien` |
| `pasien_rencana_treatment` | `id_pasien` |
| `pasien_resep_iterasi` | `id_pasien` |
| `pasien_membership_history` | `id_pasien` |
| `pasien_membership_kuota` | `id_pasien` |

Ditangani terpisah: `pasien_duplikat_dismiss` (`id_pasien_a`, `id_pasien_b`).

### ⚠ Dua jebakan

**`transaksi_kasir` menyimpan `id_pasien` SENDIRI**, di samping `id_kunjungan`.
Memindahkan `kunjungan` saja **tidak cukup** — transaksinya akan tetap menunjuk pasien
lama. Pola "satu data di dua tempat" yang sudah berulang kali menggigit proyek ini
(`_produk_stok_sudah_dipotong`, draf SOAP, `id_resep_asal`). Kalau terlewat: rekam medis
menyatu tapi laporan keuangan per pasien tetap terpecah, **tanpa gejala**.

**`pasien_duplikat_dismiss`** memuat pasangan yang pernah "diabaikan". Setelah pasangan
itu digabung, catatannya tidak bermakna lagi — dan kalau dibiarkan, pasangan yang sudah
digabung bisa muncul kembali sebagai kandidat duplikat. Hapus/tandai saat penggabungan.

**Daftar ini harus diverifikasi ULANG dari `information_schema` setiap kali ada migrasi
yang menambah tabel ber-`id_pasien`.** Menambah tabel baru tanpa memperbarui penggabungan
= sepotong riwayat tertinggal diam-diam. Pemeriksa otomatis wajib membandingkan daftar
kode dengan `information_schema` dan GAGAL kalau ada yang belum terdaftar.

## 5. Alur yang diusulkan

1. Pilih pasien **yang bertahan** dan pasien **duplikat** (dari layar audit #18)
2. Pagar: keduanya bukan pasien yang sama · duplikat masih aktif · tujuan masih aktif ·
   **tidak keduanya punya membership/kuota aktif**
3. Tampilkan **pratinjau**: berapa baris per tabel akan dipindahkan — dilihat dulu
   sebelum ditekan, seperti dry-run rsync
4. Dalam SATU transaksi: UPDATE 13 tabel → bereskan `pasien_duplikat_dismiss` →
   set `is_active=0`, `digabung_ke_id_pasien`, `nonaktif_alasan`, `id_staf_nonaktif`,
   lepas `nomor_ktp` (simpan ke `nomor_ktp_lama` — mekanisme ini sudah ada)
5. `audit_log`: id asal, id tujuan, jumlah baris per tabel, aktor, waktu
6. `no_rm` duplikat **tetap tersimpan** di baris pasien nonaktif — ia tercetak di nota
   lama dan harus bisa ditelusuri

## 6. SATU ARAH — dan jaring pengamannya di kertas

[Keputusan dr. Hansen 2026-09-30] *"tidak perlu ada jalan pulang, one way street. setiap
penggabungan pasien akan ada pencatatan manual dengan kertas dan pena. baik dari id,
transaksi id, nomor nota."*

Penggabungan **tidak bisa dibatalkan** oleh sistem. Salah gabung diperbaiki manual lewat
database. `aktifkan()` yang ada hanya mengembalikan status pasien, **tidak** memindahkan
baris kembali — dan memang tidak akan dibuat begitu.

### ⚠ KEWAJIBAN UI yang lahir dari keputusan ini

Karena pengamannya catatan kertas, **layar penggabungan WAJIB menampilkan angka-angka
yang harus disalin SEBELUM tombol ditekan**, dalam bentuk yang mudah dibaca dan disalin:

- `id_pasien` asal & tujuan, beserta `no_rm` keduanya
- daftar **id transaksi** yang akan berpindah
- daftar **nomor nota** yang terkait
- pratinjau jumlah baris per tabel

Setelah penggabungan, jejaknya sudah pindah. **Kalau angka-angka itu tidak ditampilkan di
muka, SOP kertas mustahil dijalankan dan satu-satunya jaring pengaman hilang.** Ini
kewajiban, bukan tambahan — memperlakukannya sebagai "nanti saja" berarti membangun
operasi tak-berbalik tanpa pengaman apa pun.

Lihat juga memori proyek `sehati-sop-offline`.

## 6b. Yang belum diputuskan

- Siapa yang boleh menggabungkan? Usulan: Owner/Superadmin saja — lebih ketat daripada
  nonaktifkan biasa, justru karena tidak bisa dibatalkan.
- Apakah `UNIQUE INDEX ux_pasien_nomor_ktp` dipasang di migrasi yang sama atau terpisah.
  ⚠ Index itu akan **menolak NIK kosong ganda** kalau tidak memakai NULL — periksa
  bagaimana NIK kosong disimpan sekarang sebelum memasangnya.

## 7. Uji terima

1. Gabungkan dua pasien dummy berriwayat → semua 13 tabel ikut pindah, jumlahnya cocok
   dengan pratinjau
2. Riwayat pasien yang bertahan memuat kunjungan dari kedua identitas
3. Laporan keuangan per pasien juga menyatu (bukti `transaksi_kasir.id_pasien` ikut)
4. Pasangan yang sudah digabung **tidak muncul lagi** di hasil scan duplikat
5. Dua pasien bermembership aktif → **ditolak** dengan pesan jelas
6. `audit_log` memuat jumlah baris per tabel
7. Pemeriksa otomatis GAGAL kalau ada tabel ber-`id_pasien` yang tidak terdaftar di kode
8. **Layar pratinjau menampilkan id pasien, id transaksi, dan nomor nota** — bisa disalin
   ke catatan kertas sebelum tombol ditekan (lihat §6)
