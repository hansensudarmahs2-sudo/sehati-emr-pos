# No. RM Omnicare (sistem lama) — Sehati sebagai sumber nomor

Disetujui dr. Hansen 2026-10-07. Dikerjakan & diuji di desktop hari yang sama.
Migrasi `20261007_0100` (satu kolom + unique index, tanpa mengubah data).

## 1. Masalah

1. Klinik **input ganda**: pasien didaftarkan di Sehati (emr.joderma.id) DAN di Omnicare.
2. Nomor RM Omnicare **diketik manual** — tidak ada yang memberi nomor berikutnya.
3. Persiapan **migrasi data lama** (Jemur `JJ-`, Citraland `JC-`) ke Sehati.

## 2. Keputusan dr. Hansen

| Pertanyaan | Keputusan |
|---|---|
| Satu pasien bisa punya nomor di dua cabang? | **Tidak.** Satu pasien satu nomor (JJ- atau JC-); keduanya terakses di Omnicare dan Sehati, tidak ada pasien ganda. |
| Dari mana staf tahu nomor berikutnya? | **Sehati = sumber.** Staf melihat Cari Pasien, mendaftarkan dengan nomor berikutnya, lalu memasukkan ke Omnicare. |
| Nomor tertinggi ditampilkan terpisah? | **Ya** (lihat §3, jebakan urutan). |
| Panjang angka | Hari ini 4 digit (Jemur 81xx, Citraland 20xx), bersiap 5 digit. |
| Halaman salin | Copy-paste manual; data diri harus mudah dilihat & diblok. Isi: identitas, kontak, sumber referensi. |
| 33 pasien yang sudah ada di mini PC | **Diabaikan** — dirapikan dr. Hansen sendiri lewat desktop. Migrasi tidak mengisi apa pun. |

## 3. Keputusan bentuk (dan apa yang rusak kalau diubah)

- **Nama kolom `no_rm_omnicare`, BUKAN `no_rm_lama`.** Tabel `pasien` sudah punya
  `nomor_ktp_lama` = "NIK yang dilepas saat nonaktif". Satu kata, dua arti di tabel yang
  sama = jebakan CLAUDE.md §4.1. Label layar tetap "No. RM Omnicare (lama)".
- **Bentuk baku tanpa nol depan** (`JJ-08123` → `JJ-8123`), huruf besar, spasi dibuang.
  Tanpa itu nomor yang sama diketik dua gaya lolos dari unique index (pelajaran NIK).
  Kosong / `-` / `0` → NULL (MySQL mengizinkan banyak NULL di unique index, bukan "").
  Bentuk lain **ditolak** (beda dengan NIK yang lunak): nomor ini mencocokkan dua sistem.
  Satu sumber: `app/core/no_rm_omnicare.py`.
- **"Tertinggi" dibandingkan sebagai ANGKA**, bukan teks. Sebagai teks `JJ-8199` >
  `JJ-10000` — tepat saat nomor menyentuh 5 digit, Sehati akan menunjuk nomor yang salah
  dan staf membagikan nomor ganda. `PasienRepository.rm_omnicare_tertinggi`.
- **Daftar "10 pasien terbaru" ≠ nomor terakhir.** Daftar itu urutan PENDAFTARAN di
  Sehati; pasien lama yang datang lagi (JJ-0012) ikut di atas. Nomor terakhir SELALU
  dibaca dari baris "No. RM Omnicare tertinggi" (`_rm_omnicare_tertinggi.html`, dipakai di
  Cari Pasien, pendaftaran, edit, halaman Omnicare).
- **UNIQUE di migrasi DAN di model** (`Pasien.__table_args__`) — Temuan 34.
  Bentrok saat dua pendaftaran bersamaan dikenali per NAMA indeks
  (`ux_pasien_no_rm_omnicare`), bukan `except IntegrityError` generik.
- **Pasien NONAKTIF tetap memegang nomornya** (dipensiunkan, seperti `no_rm`). Kalau
  dilepas seperti NIK, "tertinggi" bisa turun dan nomor yang sudah terpakai di Omnicare
  dibagikan lagi. Pesan penolakan menyebut "NONAKTIF" dan menyarankan Gabungkan Pasien.
- **Penggabungan memindahkan nomor** ke pasien yang bertahan (duplikat dikosongkan &
  di-flush dulu, kalau tidak unique index menolak). **Dua nomor berbeda menolak
  penggabungan** — sistem tidak menebak nomor mana yang dipakai di Omnicare.
- **Edit: isian kosong = HAPUS nomor** (beda dengan isian lain, yang kosongnya berarti
  "tidak diubah"). Nomor salah ketik harus bisa dikosongkan.
- **Halaman `/web/pasien/{id}/omnicare`** menampilkan NIK LENGKAP (detail menyamarkannya),
  jadi pagarnya = form edit pasien (FO/Admin/Owner/Superadmin) dan setiap pembukaan
  dicatat `log_view`. Teks polos besar + satu kotak "Semua sekaligus".
- **Ekspor:** nomor ini pengenal orang → masuk `KOLOM_TERLARANG` paket klinis. Ekspor
  Finance memilih kolom satu per satu, jadi tidak ikut.
- **41 halaman lain** (nota, kasir, laporan) tetap hanya RM Sehati.

## 4. Uji

`tests/integration/test_no_rm_omnicare.py` — 26 test. Dua arah: lima suntikan kesalahan
(banding teks, nol depan tak dibuang, gabung tak memindahkan, pagar dua nomor dilepas,
pasien lain tak dicek) masing-masing membuat test gagal.

## 5. Belum / di luar cakupan

- Mengisi nomor 33 pasien yang sudah ada (dr. Hansen, manual).
- Migrasi data lama JJ-/JC- (rancangan terpisah — `EMR_INTEGRASI_MULTISITE_DESIGN.md`).
- Daftar "pasien terbaru" di dev berisi pasien `BKT-…` sisa `test_booking_service`
  (masalah lama, CLAUDE.md §8 "Kecil").
