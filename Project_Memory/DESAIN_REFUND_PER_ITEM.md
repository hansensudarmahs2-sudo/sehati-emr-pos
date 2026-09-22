# Desain — Refund PER ITEM untuk Obat Tertunda yang Dibatalkan (Task #54 langkah F)

**Dibuat:** 2026-09-22 · **Prasyarat:** #54 A–E sudah live (head `20260922_0100`)
**Asal:** keputusan dr. Hansen 2026-09-22 — "item tertunda yang dibatalkan → kembali tunai,
catat sebagai refund per item".

---

## 1. Masalah

Obat yang sudah **DIBAYAR** tapi ditunda kadang tidak pernah datang (distributor kosong,
barang discontinue). Sekarang satu-satunya jalan adalah **void seluruh transaksi** lalu
input ulang — yang merusak riwayat dan komisi untuk item yang sudah benar-benar diserahkan.

`void_item_resep` (`kasir_service.py:796`) tidak bisa dipakai: ia hanya menerima item
`PENDING`, yaitu yang **belum dibayar**. Item DIBAYAR ditolak. Itu lubang yang ditutup di sini.

## 2. Temuan penting dari pemetaan kode (2026-09-22)

| Temuan | Konsekuensi |
|---|---|
| Tabel **`transaksi_refund` SUDAH ADA** sejak migrasi `20260706_0400`, **belum pernah ditulis** | Refund harus menulis ke situ, bukan tabel baru |
| Ekspor Finance `15_refunds_raw.csv` (`export_service.py:613`) **sudah membacanya** | Begitu diisi, laporan Finance langsung hidup |
| 12 titik agregasi uang di 8 file hanya menyaring `status_transaksi='BAYAR'` dan menjumlah `total_tagihan` | Refund yang tidak menyentuh header = **omzet kelebihan senyap** |
| `transaksi_detail_produk.diskon_item` **tidak pernah diisi** `proses_bayar` (selalu 0) | Refund `subtotal` mentah = mengembalikan LEBIH dari yang dibayar pasien member |
| `transaksi_detail_racikan.diskon_item` **diisi** (`kasir_service.py:675-690`) | Racikan aman, `subtotal`-nya sudah net |
| `void_transaksi` (`:1440`) tidak tahu ada refund | Void sesudah refund = uang kembali dua kali |
| Tutup kasir hitung laci dari `transaksi_pembayaran.nominal` (`kasir_closing_service.py:75`) | Uang refund tunai keluar tanpa terlihat → laci selisih |
| `komisi_ledger.id_ref` untuk PRODUK **fallback ke `id_produk`** kalau `id_resep` None (`komisi_service.py:150`) | Void komisi per item bisa salah sasaran pada data lama |

## 3. Keputusan dr. Hansen (2026-09-22)

| # | Pertanyaan | Keputusan |
|---|---|---|
| 1 | Refund tercermin di omzet bagaimana | **Kurangi `total_tagihan` header**. 12 titik agregasi langsung benar tanpa disentuh — tidak ada query yang bisa terlewat. Konsekuensi yang diterima: nota cetak ulang perlu penanda "sudah direfund" |
| 2 | Nilai refund item produk | **Pro-rata diskon header**, DAN mulai isi `diskon_item` saat bayar supaya ke depan tersimpan (sekalian menutup lubang data margin Finance) |
| 3 | Refund tunai & tutup kasir | **Masuk hitungan laci** pada tanggal refund |

## 4. Aturan yang dipagari

- Hanya item **DIBAYAR** yang boleh direfund. `DISERAHKAN` **tidak** — obatnya sudah di
  tangan pasien; itu urusan retur, bukan refund. `PENDING` juga tidak (belum dibayar,
  pakai `void_item_resep`). `BATAL` tidak (sudah dibatalkan).
- Stok **tidak** disentuh sama sekali. Item yang direfund memang belum pernah dipotong —
  dijamin oleh status `DIBAYAR` (bukan `DISERAHKAN`) sejak langkah A–B.
- Racikan **all-or-nothing**, konsisten dengan penyerahan.
- Transaksi harus `status_transaksi='BAYAR'`. Transaksi VOID tidak bisa direfund.
- **Idempotency**: satu item hanya bisa direfund sekali. Dijaga oleh status item yang
  berubah ke BATAL + guard baris refund yang sudah ada untuk item itu.
- **Void sesudah refund**: `void_transaksi` dan `force_past_day_void` harus mengurangi
  nilai yang SUDAH direfund dari perhitungannya, atau menolak kalau ambigu. Tanpa guard
  ini, uang kembali dua kali.

## 5. Perubahan data

**Migrasi baru** (`revises = 20260922_0100`):

`transaksi_refund` + kolom:
- `id_resep` (int, null, FK `kunjungan_resep`) — refund item resep
- `id_kunjungan_racikan` (int, null, FK `kunjungan_racikan`) — refund item racikan
- `jenis_refund` (varchar 20, default `'ITEM'`) — membedakan dari refund tingkat transaksi
  yang mungkin dibangun Finance kelak
- index pada kedua kolom item

Tepat satu dari `id_resep` / `id_kunjungan_racikan` terisi untuk `jenis_refund='ITEM'`.
Keduanya NULL berarti refund tingkat transaksi (belum dipakai).

Tidak ada kolom baru di `transaksi_kasir` — `total_tagihan` yang sudah ada yang dikurangi,
dan `updated_at` sudah auto-bump untuk sinkronisasi Finance.

## 6. Urutan kerja

| Langkah | Isi | Uji |
|---|---|---|
| **F1** | Migrasi kolom item di `transaksi_refund` | `alembic upgrade`, cek schema |
| **F2** | `proses_bayar` mulai mengisi `diskon_item` produk (pro-rata diskon header) | bayar transaksi ber-diskon, cek Σ `diskon_item` == `nominal_diskon` header |
| **F3** | `KomisiService.void_komisi_item(id_transaksi, sumber, id_ref)` | via DB |
| **F4** | `KasirService.refund_item(...)`: guard → hitung net → insert `TransaksiRefund` → item BATAL → kurangi `total_tagihan` → void komisi item → audit `REFUND_ITEM` | via DB |
| **F5** | Guard dua arah di `void_transaksi` + `force_past_day_void` (kurangi nilai yang sudah direfund) | void setelah refund |
| **F6** | Tutup kasir: kurangi refund tunai tanggal itu dari expected laci | rekap shift |
| **F7** | UI tombol "Batalkan item" di daftar Obat Tertunda + konfirmasi menyebut **nama item dan nominalnya** | **uji desktop** |
| **F8** | Nota cetak: penanda "SEBAGIAN DIREFUND" + daftar item yang direfund | cetak ulang nota |
| **F9** | `export_refunds_raw` + `_export_columns` tambah kolom item | jalankan ekspor |

## 7. Uji terima

1. Transaksi ber-diskon member, obat ditunda, satu item dibatalkan → nilai refund **sama
   dengan yang dibayar pasien untuk item itu** (bukan harga penuh).
2. `total_tagihan` header berkurang sebesar nilai refund; omzet harian dan KPI dashboard
   ikut turun **tanpa** query-nya diubah.
3. Item jadi `BATAL`; stok **tidak berubah** sama sekali.
4. Komisi baris item itu jadi `VOID`; komisi item lain di transaksi yang sama **tetap AKTIF**.
5. Refund tunai → expected laci tutup kasir hari itu berkurang sebesar nilai refund.
6. Void transaksi **sesudah** refund item → uang tidak dikembalikan dua kali.
7. Coba refund item `DISERAHKAN` → ditolak dengan alasan yang terbaca.
8. Coba refund item yang sama dua kali → ditolak.
9. `15_refunds_raw.csv` memuat baris refund lengkap dengan item-nya.

## 8. Risiko yang disadari

- **Mengubah `total_tagihan` melanggar sifat snapshot transaksi.** Diterima secara sadar
  karena alternatifnya (mengubah 9 file laporan) menyisakan celah senyap. Kompensasinya:
  nota cetak wajib memberi penanda (F8), dan `transaksi_refund` menyimpan jejak nilai asli.
- **`komisi_ledger.id_ref` ambigu untuk PRODUK lama** — void komisi per item bisa tidak
  kena pada baris yang tersimpan dengan `id_produk`. Data produksi belum ada, jadi tidak
  ada kerusakan historis; tapi jangan berasumsi fungsi ini akurat untuk baris lama.
- Refund untuk **tindakan** tidak dibangun di sini. Hanya resep & racikan.
