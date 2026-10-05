# DESAIN — Retur dari pasien (obat/produk yang SUDAH diserahkan)

Status: **DIBANGUN 2026-10-05** (desktop, 5 tahap; migrasi `20261006_0100` hanya di DB dev; `tests/integration/test_retur_pasien.py` 19 test). Keputusan §10–§12, migrasi §13. Uji UI: `UJI_UI_AUDIT_2026-10-05.md` kelompok G.
Modul baru + butuh migrasi → wajib persetujuan (CLAUDE.md §1.3).

## 1. Kenapa perlu

Ditemukan saat uji UI 2026-10-05 (U16). Void atas transaksi yang obatnya sudah
`DISERAHKAN` **ditolak** — benar, keputusan Opsi A 2026-10-04 (void hanya untuk yang belum
selesai). Pesan penolakannya menyuruh *"pakai jalur retur/refund"*, tapi **jalur itu tidak
ada** (diperiksa di kode):

| Jalur | Untuk apa | Obat SUDAH diserahkan? |
|---|---|---|
| Void | seluruh transaksi | ❌ ditolak (Opsi A) |
| Refund obat tertunda (`refund_item_tertunda`) | item DIBAYAR, **belum** diserahkan | ❌ ditolak ("ditangani lewat retur") |
| Retur (menu Pengadaan) | retur **ke distributor** | ❌ bukan dari pasien |

Akibatnya hari ini: pasien mengembalikan obat → kasir **tidak punya jalan apa pun**. Uang
dikembalikan di luar sistem → laci selisih, laporan tidak tahu.

## 2. Dua kejadian, dua gerak uang (dr. Hansen 2026-10-05)

| | **A. Kembalikan uang** | **B. Tukar dengan produk lain** |
|---|---|---|
| Contoh | pasien tidak puas, minta uang kembali | pasien tidak cocok, minta produk serupa / senilai |
| Uang | keluar sebesar nilai retur | hanya **selisih**: pasien bayar tambahan, klinik kembalikan sisa, atau nol |
| Barang keluar | — | produk pengganti (stok terpotong FEFO) |

## 3. Nilai retur

= nilai **BERSIH** yang dibayar pasien untuk item itu (subtotal − porsi diskonnya), dari
snapshot `transaksi_detail_produk` — rumus yang SAMA dengan `refund_item_tertunda`, bukan
harga master hari ini. Retur sebagian qty → proporsional per unit.

## 4. Pembukuan — memakai jalur T32, bukan jalur baru

**A. Kembalikan uang** = refund biasa: baris `transaksi_refund` (jenis `RETUR`), dibukukan di
**hari retur** lewat `_refund_bukuan` (laporan, tutup kasir, ekspor otomatis benar); header
transaksi asal tidak disentuh; PIN Admin/Superadmin/Owner kalau transaksi asal hari lampau;
void transaksi asal sesudahnya ditolak (pagar T32 sudah ada).

**B. Tukar** = refund X + penjualan Y, dihubungkan:

```
retur X (nilai bersih 150.000)    → transaksi_refund  metode 'TUKAR'   −150.000
pengganti Y (harga 200.000)       → transaksi_kasir   jenis 'TUKAR'    +200.000
                                     pembayaran: 'TUKAR' 150.000 + TUNAI 50.000 (selisih)
```

- Omzet hari itu bergerak **+50.000** (= selisih) — benar secara ekonomi.
- Laci hanya melihat **TUNAI 50.000** — benar secara fisik. Metode `TUKAR` saling meniadakan
  (+150.000 −150.000) dan tidak masuk hitungan laci.
- Kalau Y lebih murah: pembayaran 'TUKAR' sebesar Y, sisa X dikembalikan tunai/transfer
  sebagai refund biasa.
- Transaksi pengganti menempel ke **kunjungan yang sama** → riwayat & nota tetap utuh.

⚠ §4.1 di CLAUDE.md: metode `TUKAR` adalah nilai VARCHAR baru. Semua pembaca per-metode
(tutup kasir, laporan omzet per metode, ekspor) harus diperiksa satu per satu sebelum
dikerjakan — tutup kasir hanya mengulang `METODE_KANONIK`, jadi `TUKAR` tidak masuk laci
(diinginkan), tapi laporan omzet per metode akan menampilkannya sebagai baris bernilai ~0.

## 5. Stok barang yang dikembalikan — keputusan per retur

| Pilihan | Gerak stok | Kapan |
|---|---|---|
| **Kembali ke stok** | qty kembali ke **lot asalnya** (dilacak dari `kunjungan_lot_terpakai`, ED terjaga) — sama dengan pemulihan void per-item | kemasan tersegel, layak jual |
| **Tidak kembali** (rusak/dibuka) | tidak ada — barangnya sudah keluar | dicatat sebagai **kerugian** di baris retur (nilai HPP lot) |

⚠ **Pertanyaan klinis/regulasi untuk dr. Hansen (§8.3):** praktik kefarmasian umumnya
**tidak** menyerahkan ulang obat yang sudah keluar dari apotek (penyimpanannya di tangan
pasien tak terjamin). Usul default: **obat (oral/injeksi/racikan) TIDAK kembali stok**;
produk retail/kosmetik **tersegel** boleh. Racikan **tidak pernah** kembali stok.

## 6. "Produk sejenis" (skenario B)

Diperiksa di DB dev: `golongan` terlalu kasar (TOPIKAL ESTETIK = 44 produk beragam; 30
produk tanpa golongan), `kandungan` teks bebas yang tak seragam ("Aciclovir" vs
"Acyclovir"; 30 kosong). **Tidak bisa dipakai sebagai pengelompokan yang menolak/
mengizinkan.**

Usul bertahap:
1. **Versi 1 — tanpa grouping:** petugas memilih produk pengganti APA PUN; layar
   **mengurutkan** saran dari golongan & kandungan yang sama di atas. Karena pembukuan
   memakai **selisih nilai**, produk apa pun aman secara uang. Tanpa migrasi grouping.
2. **Versi 2 — kalau perlu dibatasi:** kolom baru `kelompok_tukar` di master produk, diisi
   manual (kurasi) → pengganti dibatasi ke kelompok yang sama. Butuh migrasi + entri data.

## 7. Bentuk teknis (ringkas)

- Tabel baru **`retur_pasien`** (migrasi): id, id_transaksi_asal, id_resep / id_kunjungan_racikan,
  qty, nilai, jenis (`REFUND`/`TUKAR`), alasan (kode + teks), stok_kembali (bool),
  nilai_kerugian, id_refund, id_transaksi_pengganti, id_staf, id_staf_otorisasi, waktu.
  Kenapa bukan cukup `transaksi_refund`: retur sebagian qty (beberapa kali per item),
  keputusan stok, dan tautan ke transaksi pengganti — tak punya tempat di sana; dan
  `refund_item_tertunda` menolak item yang pernah direfund (anti-dobel) per id_resep.
- Pagar: hanya item `DISERAHKAN`; qty ≤ qty diserahkan − qty sudah diretur; dikunci baris
  (`with_for_update`) — pelajaran Temuan 15/19/20.
- Komisi: item retur → komisinya dibatalkan proporsional; pengganti → komisi baru (§8.4).
- UI: **Kasir → Cari Transaksi → transaksi → "↩ Retur dari pasien"** per item. Peran kasir.
  Nota retur tercetak.
- Pesan penolakan void diganti menunjuk menu ini.

## 8. Pertanyaan untuk dr. Hansen

1. **Retur sebagian qty** (beli 3, kembalikan 1) — perlu, atau cukup seluruh item?
2. **Batas waktu** retur (mis. maks 7 hari sejak serah) — perlu?
3. **Stok kembali:** setuju default §5 (obat & racikan tidak kembali; retail tersegel boleh,
   dipilih petugas)? Atau siapa yang memutuskan per kasus — apoteker?
4. **Komisi:** item yang diretur → komisi dokter dibatalkan? Produk pengganti → komisi
   dokter baru?
5. **Produk sejenis:** mulai Versi 1 (bebas pilih, diurutkan saran) dulu?
6. **Pengganti lebih murah:** sisa nilai dikembalikan tunai, atau boleh disimpan sebagai
   **saldo/deposit** pasien? (Deposit = konsep baru, saran: TIDAK di versi pertama.)
7. **Alasan "reaksi obat/alergi"** — perlu otomatis menandai alergi di rekam medis pasien,
   atau cukup dicatat di retur? (Saran: dicatat di retur + peringatan ke dokter, bukan
   menulis rekam medis otomatis.)

## 9. Sementara modul ini belum ada

Pesan penolakan void (`_pagari_void_item_diserahkan`) **menyesatkan** — menyuruh ke jalur
yang tidak ada. Usul segera (kecil, tanpa migrasi): ganti jadi *"Obat sudah di tangan pasien.
Pengembalian dari pasien belum ada di sistem — hubungi Owner; jangan kembalikan uang dari
laci tanpa catatan."*

---

## 10. Keputusan dr. Hansen 2026-10-05 (menjawab §8)

| # | Keputusan | Akibat pada rancangan |
|---|---|---|
| 1 | **Retur sebagian boleh, dengan otorisasi Admin/Owner** | Retur sebagian qty menuntut PIN Admin/Superadmin/Owner (penyetuju ≠ pemroses, pola T32). Retur seluruh item hari yang sama: kasir sendiri; hari lampau: PIN (T32) |
| 2 | **Batas waktu 7 hari** sejak obat diserahkan (`waktu_serah`) | Lewat 7 hari → ditolak di server, pesan menyebut tanggal serah |
| 3 | **Komisi:** dibatalkan bila uang dikembalikan; **TIDAK** dibatalkan bila ditukar produk senilai | Refund → `void_komisi_item` (proporsional untuk retur sebagian). Tukar → komisi item asal tetap; produk pengganti **tidak** menghasilkan komisi baru (supaya satu penjualan tidak berkomisi dua kali) |
| 4 | **Pengganti lebih murah: sisa TIDAK dikembalikan, TIDAK jadi saldo** — tapi Finance harus diberi tanda khusus | Lihat 10a |
| 5 | **Alergi** → pakai pola draf SOAP apoteker (tebus resep online) yang disetujui dokter | Lihat 10b |

### 10a. Sisa nilai yang hangus — apa artinya di jurnal

Contoh: retur X yang dibayar Rp 150.000, ditukar Y seharga Rp 100.000, sisa Rp 50.000 tidak
dikembalikan.

Secara kas: **tidak ada uang yang bergerak** — klinik menerima Rp 150.000 di hari jual dan
tidak mengembalikan apa pun. Jadi pembukuannya:

```
retur X   → transaksi_refund  metode 'TUKAR'  −100.000   (hanya senilai Y)
ganti Y   → transaksi_kasir   jenis  'TUKAR'  +100.000   bayar 'TUKAR' 100.000
sisa      → TIDAK ada baris uang; Rp 50.000 tetap sebagai pendapatan dari penjualan X
```

Omzet hari tukar bergerak **0**; laci bergerak **0**. Rp 50.000 itu sudah tercatat sebagai
pendapatan saat X dijual — tidak perlu jurnal tambahan, tapi akuntan perlu TAHU bahwa
sebagian penjualan X kini "berganti barang" dan sisanya hangus. Untuk itu baris
`retur_pasien` menyimpan **`nilai_hangus`** (Rp 50.000) dan ikut diekspor ke paket Finance
sebagai dataset/kolom tersendiri dengan penjelasan di kamus data. Dalam bahasa akuntansi:
sisa itu tetap **pendapatan penjualan** (tidak dipindah ke "pendapatan lain-lain") — keputusan
reklasifikasi diserahkan ke Finance, Sehati hanya menandainya (CLAUDE.md §7: Sehati tidak
menganalisa).

Kalau Y LEBIH MAHAL: pasien membayar selisih (TUNAI/transfer) — masuk laci dan omzet; tidak
ada yang hangus.

### 10b. Alergi — draf SOAP, tapi di KUNJUNGAN BARU

Pola yang ada (`apotek.py` ±336, `dokter.py` ±92): baris `pemeriksaan_klinis` status
`DRAFT_APOTEK`, dokter KOSONG; dokter peresep menyunting & menyetujui → `FINAL` miliknya.

⚠ **Draf TIDAK boleh menempel ke kunjungan asal.** `get_riwayat_soap` menampilkan SATU SOAP
FINAL terbaru per `id_kunjungan` (perbaikan `created_at` 2026-10-04). Draf alergi yang
disetujui di kunjungan asal akan **menggantikan** SOAP konsultasi aslinya di riwayat —
catatan konsultasi hilang dari pandangan tanpa error. (Di DB dev sudah ada kunjungan dengan
4–12 baris pemeriksaan, jadi bentuk itu nyata.)

Usul: retur beralasan alergi membuat **kunjungan baru** `jenis_kunjungan='RETUR_PASIEN'`,
status langsung `COMPLETED`, tanpa tagihan, `id_staf_dokter_assigned` = dokter peresep asal,
berisi draf SOAP (obat apa, kapan diserahkan, keluhan pasien). Dokter menyetujui di menu
**Draf SOAP** seperti biasa. ⚠ DIUBAH 2026-10-05 — lihat §12: saat dokter menyetujui,
alergi DITAMBAHKAN OTOMATIS ke data pasien.
⚠ `jenis_kunjungan` VARCHAR → nilai baru. Pembaca yang menghitung kunjungan (rekap harian
"pasien berkunjung", laporan, ekspor visits_raw, paket klinis) harus diperiksa satu per
satu (§4.1): kunjungan retur sebaiknya TIDAK dihitung sebagai kunjungan klinis.

## 11. Pertanyaan tersisa

1. **Tukar dengan produk LEBIH MAHAL** (pasien bayar selisih): komisi produk asal tetap
   (keputusan 3) — apakah **selisihnya** menghasilkan komisi untuk dokter? Usul: **tidak**,
   supaya aturannya sederhana ("tukar tidak pernah menambah komisi").
2. **Kunjungan retur (10b) dihitung sebagai kunjungan?** Usul: **tidak** di rekap/laporan
   kunjungan, tapi tetap muncul di riwayat pasien (karena berisi catatan alergi).

## 12. Jawaban §11 + tambahan (dr. Hansen 2026-10-05)

| # | Keputusan |
|---|---|
| 11.1 | Tukar dengan produk lebih mahal: selisihnya **TIDAK** menghasilkan komisi. Aturan tunggal: **penukaran tidak pernah menambah komisi** |
| 11.2 | Kunjungan retur **TIDAK** dihitung sebagai kunjungan di rekap/laporan; tetap tampil di riwayat pasien |
| baru | **Alergi otomatis:** saat dokter MENYETUJUI draf retur-alergi, riwayat alergi pasien (`pasien_alergi`, bagian data diri pasien) **ditambahkan otomatis** |

### 12a. Bentuk alergi otomatis

Hanya pada persetujuan draf di kunjungan `jenis_kunjungan='RETUR_PASIEN'` beralasan alergi
(BUKAN pada draf tebus resep online biasa — jalurnya sama, artinya tidak).

Layar persetujuan draf untuk kasus ini menampilkan, di samping kolom SOAP biasa:

| Kolom `pasien_alergi` | Diisi dari | Dokter bisa ubah? |
|---|---|---|
| `alergen` | `kandungan` produk yang diretur (fallback `nama_produk`), dipotong ke 100 huruf (lebar kolom — pelajaran T24) | ✅ wajib dicek: kandungan di master tidak seragam ("Aciclovir"/"Acyclovir") |
| `gejala` | keluhan yang ditulis petugas saat retur | ✅ |
| `tingkat_keparahan` | **dokter WAJIB memilih** Ringan/Sedang/Berat — tidak ada nilai bawaan | ✅ (wajib) |
| `id_staf` | dokter yang menyetujui | — |

- Persetujuan draf + penambahan alergi dalam **satu commit**: tidak boleh ada SOAP FINAL
  tanpa alerginya, atau sebaliknya.
- Kalau alergen yang sama (perbandingan tanpa beda huruf besar/kecil) **sudah aktif** untuk
  pasien itu → tidak ditambah dobel; gejala baru ditambahkan ke catatan audit.
- Audit: `ALERGI_DARI_RETUR` (id pasien, alergen, id retur, dokter).
- Kenapa dokter tetap menyetujui dulu, bukan otomatis saat retur: keluhan pasien belum tentu
  alergi (bisa efek samping biasa, atau salah pakai). Catatan alergi ikut menghalangi resep
  berikutnya — yang menulisnya harus dokter, bukan kasir.

---

## 13. RANCANGAN MIGRASI — menunggu persetujuan dr. Hansen (CLAUDE.md §1.3)

Satu revisi alembic, `20261006_0100_retur_pasien`. **Jinak:** dua tabel BARU + satu nilai
ENUM baru di akhir daftar. Tidak mengubah satu baris data pun; tidak mengubah kolom lama.

### 13a. Tabel `retur_pasien` — satu baris per kejadian retur

| Kolom | Tipe | Isi / alasan |
|---|---|---|
| `id_retur` | INT PK auto | |
| `nomor_retur` | VARCHAR(30) **UNIQUE**, NOT NULL | `RPS-YYYY-MM-` + LPAD(id_retur,6) — diturunkan dari PK saat INSERT (pelajaran T33: nomor dokumen yang dibuat tapi tak pernah diisi; dan T34: jangan dari COUNT/MAX) |
| `id_transaksi_asal` | INT FK transaksi_kasir, NOT NULL | transaksi tempat obat dibeli |
| `id_resep` | INT FK kunjungan_resep, NULL | tepat SATU dari dua kolom ini terisi — dijaga **CHECK** di DB, bukan hanya di kode |
| `id_kunjungan_racikan` | INT FK kunjungan_racikan, NULL | racikan: seluruh item saja (racikan all-or-nothing) |
| `qty` | DECIMAL(10,2) NOT NULL, CHECK > 0 | jumlah yang dikembalikan |
| `is_sebagian` | BOOL NOT NULL | qty < qty diserahkan → butuh PIN (keputusan 1) |
| `waktu_serah_asal` | DATETIME NOT NULL | snapshot `waktu_serah` — bukti aturan 7 hari saat retur dibuat |
| `jenis` | **ENUM**('REFUND','TUKAR') NOT NULL | ENUM, bukan VARCHAR: VARCHAR menerima nilai ngawur diam-diam (§4.5) |
| `alasan_kode` | **ENUM**('TIDAK_PUAS','ALERGI','EFEK_SAMPING','SALAH_PRODUK','RUSAK','LAINNYA') NOT NULL | `ALERGI` memicu kunjungan retur + draf SOAP |
| `alasan_teks` | TEXT NOT NULL | keluhan pasien (jadi isi draf SOAP & `gejala` alergi) |
| `nilai_retur` | DECIMAL(12,2) NOT NULL | nilai BERSIH yang dibayar (proporsional qty) |
| `stok_kembali` | BOOL NOT NULL | keputusan per retur (§5) |
| `nilai_kerugian` | DECIMAL(12,2) NOT NULL DEFAULT 0 | HPP lot bila TIDAK kembali stok — dasar laporan susut |
| `id_refund` | INT FK transaksi_refund, NULL | REFUND: refund penuh · TUKAR: refund ber-metode TUKAR |
| `id_transaksi_pengganti` | INT FK transaksi_kasir, NULL | hanya TUKAR |
| `nilai_pengganti` | DECIMAL(12,2) NULL | harga produk pengganti |
| `selisih_dibayar` | DECIMAL(12,2) NOT NULL DEFAULT 0 | pengganti lebih mahal → dibayar pasien |
| `nilai_hangus` | DECIMAL(12,2) NOT NULL DEFAULT 0 | pengganti lebih murah → sisa tak dikembalikan (keputusan 4) — **ikut ekspor Finance** |
| `id_kunjungan_retur` | INT FK kunjungan, NULL | hanya ALERGI (kunjungan `RETUR_PASIEN`) |
| `id_alergi` | INT FK pasien_alergi, NULL | diisi saat dokter menyetujui draf (§12a) |
| `id_staf` | INT FK master_staf, NOT NULL | pemroses |
| `id_staf_otorisasi` | INT FK master_staf, NULL | penyetuju PIN (sebagian / hari lampau); ≠ `id_staf` dijaga di kode |
| `created_at` | TIMESTAMP default now | |

Indeks: `id_transaksi_asal`, `id_resep`, `id_kunjungan_racikan`, `created_at`.

⚠ **SENGAJA tanpa kolom `id_pasien`.** `cek_gabung_pasien` GAGAL kalau ada tabel ber-`id_pasien`
yang tak terdaftar di penggabungan pasien (13 tabel), dan setiap tabel baru di daftar itu
menambah satu tempat yang bisa terlupa (§4.1 — `transaksi_kasir.id_pasien` adalah contohnya).
Pasien selalu bisa ditelusuri lewat `id_transaksi_asal`.

### 13b. Tabel `retur_pasien_lot` — lot tempat barang dikembalikan

| Kolom | Tipe | |
|---|---|---|
| `id` | INT PK | |
| `id_retur` | INT FK retur_pasien NOT NULL | |
| `id_lot` | INT FK stok_lot NOT NULL | lot ASAL dari `kunjungan_lot_terpakai` (ED terjaga) |
| `qty` | DECIMAL(10,2) NOT NULL, CHECK > 0 | |

Hanya terisi bila `stok_kembali = 1`. Kenapa tabel anak: satu item bisa diserahkan dari
**dua lot** (FEFO memotong lot hampir habis lalu lot berikutnya); retur sebagian harus tahu
lot mana yang menerima berapa. Kolom tunggal `id_lot` di induk tidak bisa menyatakannya.

### 13c. ENUM `inventory_history.jenis_mutasi` + `'RETUR_PASIEN'`

Sekarang: `TINDAKAN, PENJUALAN, RESTOCK, EXPIRED, RUSAK, PENYESUAIAN`. Ditambah di AKHIR
(ALTER yang hanya menambah nilai di akhir tidak menyentuh data). Supaya barang yang kembali
dari pasien bisa dibedakan dari restock distributor di riwayat stok — pelajaran Temuan 13
(mutasi yang tak bisa dibedakan = laporan susut yang tak bisa disusun).

### 13d. Yang TIDAK butuh migrasi (VARCHAR yang sudah ada — dicatat supaya diperiksa)

| Kolom | Nilai baru | Pembaca yang wajib diperiksa saat membangun (§4.1) |
|---|---|---|
| `transaksi_refund.jenis_refund` | `RETUR` | ekspor refunds_raw + kamus data |
| `transaksi_refund.metode_refund` / `transaksi_pembayaran.metode_bayar` | `TUKAR` | tutup kasir (hanya `METODE_KANONIK` → TUKAR tak masuk laci, diinginkan), laporan omzet per metode, rekap owner, ekspor, `_refund_bukuan.refund_per_metode` |
| `transaksi_kasir.jenis_transaksi` | `TUKAR` | laporan yang memfilter/menghitung jenis transaksi, nota |
| `kunjungan.jenis_kunjungan` | `RETUR_PASIEN` | rekap "pasien berkunjung", laporan kunjungan, visits_raw, paket klinis, antrian (kunjungan langsung COMPLETED) — keputusan 11.2: TIDAK dihitung |

### 13e. Downgrade

DROP `retur_pasien_lot`, DROP `retur_pasien`, kembalikan ENUM — **ditolak** kalau sudah ada
baris `inventory_history` ber-jenis `RETUR_PASIEN` atau baris `retur_pasien` (downgrade tidak
boleh menghapus jejak uang diam-diam; pola penolakan seperti `20260930_0200`).

### 13f. Uji migrasi (sebelum dipakai)

upgrade → `cek_gabung_pasien` tetap lulus (tidak ada tabel ber-id_pasien baru) → CHECK
menolak baris dengan id_resep DAN id_kunjungan_racikan terisi / qty ≤ 0 → downgrade bersih
pada DB tanpa retur → upgrade ulang.

## 14. Catatan pembangunan (2026-10-05)

- **Rumus nilai bersih** dipindah ke `KasirService.trx_dan_nilai_bersih` — dipakai refund obat
  tertunda DAN retur. Satu rumus uang.
- **Pencarian transaksi asal diperbaiki**: dulu "transaksi BAYAR terbaru di kunjungan"; sesudah
  ada transaksi TUKAR di kunjungan yang sama itu salah transaksi. Kini: transaksi yang MEMUAT
  produk itu, dibayar sesudah resep ditulis, paling awal (fallback tanpa syarat waktu).
- **Nota transaksi TUKAR** selalu dari snapshot sendiri — tanpa itu, kunjungan asal pra-F3
  membuat nota pengganti mencetak seluruh tindakan & obat kunjungan asal.
- **Kunjungan RETUR_PASIEN** disaring lewat `app/services/_jenis_kunjungan.py` di KPI
  dashboard (3), rekap owner (2), ekspor ringkasan; `visits_raw` kini memuat `jenis_kunjungan`.
- **Komisi retur sebagian** = baris koreksi NEGATIF bertanggal hari retur (baris asli tak diubah).
- **Daftar penyetuju PIN** satu fungsi: `kasir_service.daftar_penyetuju_refund`.

### Belum dikerjakan (dicatat jujur)
- ~~**Laporan apotek** masih menghitung item yang SUDAH diretur~~ — **SELESAI 2026-10-05**
  (keputusan dr. Hansen): dua laporan, dua arti.
  - *Rekap penyerahan per apoteker* = catatan KERJA → tetap dihitung, baris diberi penanda
    `qty_diretur` + `nomor_retur` (layar & CSV).
  - *Top produk* = dasar belanja stok → BERSIH: retur penuh keluar dari qty/kejadian/kunjungan,
    sebagian dikurangi qty-nya, racikan yang diretur (selalu utuh) keluar dari bahan & peringkat.
    Dikurangkan di periode PENYERAHAN asli (bukan periode retur) → tak pernah minus; laporan
    bulan lalu bisa bergeser ≤ 7 hari sesudah tutup bulan. Pengganti TUKAR tetap dihitung.
  - Satu sumber: `ReportsService._retur_per_item`. Test: `test_laporan_apotek_*` (4, dua arah).
- **Nominal Top produk memakai harga MASTER hari ini**, bukan harga yang ditagih (pola sebelum
  T27). Bukan akibat retur; ditemukan saat mengerjakan butir di atas. Belum dikerjakan.
- **Laporan susut / kerugian retur** (`nilai_kerugian`) belum punya layar; datanya tersimpan.
- Satu produk pengganti per retur di layar (layanan menerima beberapa).
- Uji otomatis route persetujuan draf dokter (menulis DB sungguhan) → diuji manual U40–U41.
