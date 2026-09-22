# Desain — Penyerahan Obat PER ITEM di Apotek (Task #54)

**Dibuat:** 2026-09-22 · **Status:** menunggu persetujuan dr. Hansen
**Asal temuan:** uji coba nyata 2026-09-21 — "produk lain tersedia kecuali fungasol tablet…
menurut saya per item ada tombol serahkan, yang tidak ditekan bisa kita buat untuk
diselesaikan nanti (ditunda)."

---

## 1. Masalah

Hari ini penyerahan apotek bersifat **semua-atau-tidak**. Satu tombol memotong stok seluruh
item DIBAYAR sekaligus, dan tombol itu **dinonaktifkan** kalau ada satu saja item yang stoknya
kurang (`apotek_detail_resep.html:196`). Artinya: satu tablet kosong menyandera seluruh resep.
Pasien pulang tanpa obat apa pun, padahal 4 dari 5 item tersedia.

Jalan keluar yang ada sekarang hanya "tunda semua" (`tunda_serah_obat`) — sama saja.

## 2. Keputusan dr. Hansen (2026-09-22)

| # | Pertanyaan | Keputusan |
|---|---|---|
| 1 | Status kunjungan saat serah sebagian | **COMPLETED**, sisa masuk modul Obat Tertunda yang sudah ada (penjadwalan + notif + warning dashboard sudah jalan) |
| 2 | Racikan bisa diserahkan sebagian? | **Tidak** — all-or-nothing per racikan. Racikan sudah jadi satu wadah |
| 3 | Tanggal kirim untuk sisa | **Wajib diisi saat itu juga**, di layar yang sama |
| 4 | Penanda item sudah diserahkan | **Status baru `DISERAHKAN`** (bukan kolom tersirat) |
| 5 | Item tertunda yang dibatalkan | **Refund tunai per item**, tercatat sebagai refund parsial |

## 3. Yang akan pecah kalau ini dibangun naif — WAJIB ikut diperbaiki

Ini bagian terpenting dari desain. Semuanya bug **uang** atau **stok**.

### 3a. Void/reverse stok akan mengembalikan stok yang belum pernah dipotong
`KasirService._produk_stok_sudah_dipotong` (`kasir_service.py:1010-1022`) memakai
`status_antrian == "COMPLETED"` sebagai proksi "stok sudah dipotong". Dengan serah parsial,
kunjungan menjadi COMPLETED padahal sebagian item belum terpotong. Void lalu mengembalikan
stok item yang tidak pernah keluar → **stok kelebihan, senyap**.

Perbaikan: ganti proksi menjadi pertanyaan per item — `status_item == 'DISERAHKAN'`.

### 3b. Jejak lot tidak tahu item mana
`kunjungan_lot_terpakai` hanya menyimpan `(id_kunjungan, id_produk, id_lot, qty)`
(`stok_lot.py:67-95`). Kalau satu produk muncul di **dua baris resep**, tidak ada cara
membedakan baris mana yang sudah diserahkan. Reverse per item jadi ambigu.

Perbaikan: tambah `id_resep` dan `id_kunjungan_racikan` (keduanya nullable) ke tabel jejak.

### 3c. `tgl_janji_kirim = None` tanpa syarat
`apotek_service.py:383` selalu mengosongkan tanggal janji. Dengan serah parsial, sisa item
langsung hilang dari daftar tertunda. Perbaikan: hanya dikosongkan kalau **tidak ada sisa**.

### 3d. `tunda_serah_obat` menolak kunjungan COMPLETED
Guard `:225` hanya menerima `ANTRI_OBAT`. Setelah serah parsial pertama, kunjungan sudah
COMPLETED → penundaan sisa ditolak. Perbaikan: terima juga COMPLETED yang masih punya item
DIBAYAR.

### 3e. Laporan apoteker akan over-count
`reports_service.py:857-900` merekonstruksi item dari audit `SERAH_OBAT` lalu menarik
**semua** resep DIBAYAR kunjungan itu. Dengan dua kali serah, `kunjungan_to_apoteker` (dict
ber-key `id_kunjungan`) menimpa event pertama → apoteker pertama kehilangan kreditnya, dan
jumlah item dihitung ganda. Perbaikan: audit menyimpan daftar id item; laporan membaca
`status_item='DISERAHKAN'` + siapa yang menyerahkan per item.

### 3f. Antrian apotek kehilangan kunjungan parsial
`apotek_repo.list_antrian_obat:35-71` hanya melihat kunjungan `ANTRI_OBAT`. Kunjungan dengan
serah parsial sudah COMPLETED → hilang dari antrian. Ini **benar** (sisanya ada di daftar
Obat Tertunda), tapi harus disadari, bukan kebetulan.

### 3g. Gate UI terbalik
Tombol serah dinonaktifkan kalau `semua_stok_cukup` False — justru itu kasus utama serah
parsial. Gate harus pindah ke **per baris**: baris yang stoknya kurang tidak bisa dicentang.

## 4. Perubahan data

**Migrasi baru** (revision setelah `20260921_0300`):

1. `kunjungan_resep.status_item` — tambah nilai enum `DISERAHKAN`
   (`PENDING / BATAL / DIBAYAR / DISERAHKAN`).
2. `kunjungan_resep` — tambah `waktu_serah` (DateTime, null) + `id_staf_serah` (FK staf, null).
   Untuk laporan apoteker per item dan telusur.
3. `kunjungan_racikan` — kolom `status_item` sudah `String(20)`, **tidak perlu migrasi**;
   cukup tambah nilai `DISERAHKAN` + dua kolom yang sama (`waktu_serah`, `id_staf_serah`).
4. `kunjungan_lot_terpakai` — tambah `id_resep` (null) dan `id_kunjungan_racikan` (null),
   supaya reverse stok bisa per item. Baris lama tetap NULL = jejak lama (tetap dibaca
   dengan cara lama; tidak ada data produksi, hanya dummy).

Semua idempoten dan inspector-guarded seperti migrasi sebelumnya.

**Status item setelah perubahan:**

```
PENDING  →  DIBAYAR  →  DISERAHKAN
               ↓
             BATAL (refund per item)
```

## 5. Perubahan kode

| Lapis | File | Perubahan |
|---|---|---|
| Enum | `app/db/models/_enums.py:109` | tambah `DISERAHKAN` |
| Model | `kunjungan.py:173`, `racikan.py:110`, `stok_lot.py:67` | kolom baru |
| Repo | `apotek_repo.py:107,139` | parameter `only_ids` pada dua fungsi pengambil item |
| Repo | `apotek_repo.py:35` | antrian: hitung juga kunjungan COMPLETED yang masih punya item DIBAYAR? **TIDAK** — biarkan di Obat Tertunda saja |
| Service | `apotek_service.py:263 serahkan_obat` | terima daftar item; loop sudah per item; status kunjungan hanya COMPLETED bila tak ada sisa; `tgl_janji_kirim` hanya dikosongkan bila tak ada sisa; tulis `DISERAHKAN` + `waktu_serah` + `id_staf_serah`; audit memuat daftar id item |
| Service | `apotek_service.py:209 tunda_serah_obat` | terima kunjungan COMPLETED yang masih punya item DIBAYAR |
| Service | `apotek_service.py:174 list_obat_tertunda` | sudah memfilter `DIBAYAR` → otomatis benar setelah item terserah ganti status |
| Service | `kasir_service.py:1010,1024` | `_produk_stok_sudah_dipotong` per item; `_reverse_stok_per_item` memakai jejak lot ber-`id_resep` |
| Service | `reports_service.py:857,1198` | laporan apoteker baca status item + `id_staf_serah`, bukan rekonstruksi dari audit |
| Schema | `apotek.py:104` | `SerahkanObatRequest` + `id_resep[]`, `id_kunjungan_racikan[]`, `tgl_janji_kirim_sisa`; kosong = semua (back-compat API v1) |
| Route | `apotek.py:205`, `obat_tertunda.py:61` | jadi `async`, baca `request.form()` |
| Template | `apotek_detail_resep.html`, `obat_tertunda_list.html` | checkbox per baris (default tercentang bila stok cukup), baris stok kurang tidak bisa dicentang + diberi alasan, field tanggal kirim sisa muncul otomatis bila ada yang tidak tercentang |

**Refund per item (bagian D)** — dipisah jadi langkah tersendiri di akhir, karena menyentuh
kasir dan komisi:
- Tombol "Batalkan item" di daftar Obat Tertunda → item `BATAL`, stok **tidak** dipotong.
- Catat refund parsial pada transaksi (nilai item + porsi diskonnya).
- Komisi baris terkait → `VOID` (pakai `KomisiLedger.id_ref` yang sudah ada).
- Audit `BATAL_ITEM_TERTUNDA`.

## 6. Urutan kerja

| Langkah | Isi | Bisa diuji sendiri |
|---|---|---|
| **A** | Migrasi + enum + kolom baru | `alembic upgrade`, cek schema |
| **B** | Jejak lot per item + perbaiki `_produk_stok_sudah_dipotong` & reverse | void lama harus tetap benar |
| **C** | Service `serahkan_obat` per item + `tunda_serah_obat` terima COMPLETED | via DB |
| **D** | UI checkbox + tanggal kirim sisa (apotek & obat tertunda) | **uji di desktop** |
| **E** | Laporan apoteker per item | bandingkan angka sebelum/sesudah |
| **F** | Refund per item (batal item tertunda) | **uji di desktop** |

## 7. Uji terima

1. Resep 5 item, 1 stok kosong → centang 4, isi tanggal kirim → stok terpotong **hanya 4**,
   kunjungan COMPLETED, 1 item tersisa muncul di Obat Tertunda dengan tanggalnya.
2. Racikan dengan 1 bahan kosong → racikan **tidak bisa** dicentang, alasannya terbaca.
3. Serah sisa keesokan hari → stok item terakhir terpotong, `tgl_janji_kirim` kosong,
   kunjungan hilang dari daftar tertunda.
4. **Void setelah serah parsial** → stok yang kembali **hanya** item yang sudah diserahkan,
   kembali ke lot aslinya. Item yang belum diserahkan tidak menambah stok.
5. Dua apoteker berbeda menyerahkan pada dua kesempatan → laporan mencatat **masing-masing**
   item ke apotekernya, tidak saling menimpa, tidak dihitung ganda.
6. Batalkan item tertunda → stok tidak berubah, uang kembali, komisi baris itu VOID,
   komisi item yang sudah diserahkan **tetap**.

## 8. Catatan

- Tidak ada data pasien asli saat ini (masih uji coba dummy di klinik) → migrasi aman.
- Gerbang hardening (#33–#36) tetap berlaku sebelum data asli masuk.
- Langkah B adalah perbaikan bug **stok** yang sudah ada nilainya sendiri, terlepas dari #54.
