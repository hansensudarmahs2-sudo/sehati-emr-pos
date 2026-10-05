# DESAIN — Retur dari pasien (obat/produk yang SUDAH diserahkan)

Status: **RANCANGAN LENGKAP — semua keputusan dijawab 2026-10-05 (§10–§12)**. Berikutnya: rancangan migrasi `retur_pasien` untuk disetujui (CLAUDE.md §1.3), baru dibangun · desktop
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
