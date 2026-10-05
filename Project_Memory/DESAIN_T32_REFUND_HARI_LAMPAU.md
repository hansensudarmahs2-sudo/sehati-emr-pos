# DESAIN — T32: refund hari lampau (otorisasi PIN + dibukukan di hari refund)

Status: **DIKERJAKAN 2026-10-05** (desktop, cabang `laptop/audit-alur-uang-putaran-21`) ·
disetujui dr. Hansen 2026-10-05. Migrasi `20261005_0100` sudah jalan di DB dev, BELUM di mini PC.
⚠ Sebelum dipakai di klinik: Admin/Superadmin yang akan menyetujui refund WAJIB punya PIN
(menu Staf). Di DB dev hanya dr. Hansen yang ber-PIN — artinya refund yang ia proses sendiri
tidak bisa disetujui siapa pun.

Yang terpasang: `_refund_bukuan.py` (satu definisi refund-per-tanggal) dipakai omzet harian
& bulanan, rekap shift (2), rekap harian owner, KPI dashboard (2), ekspor ringkasan harian;
nota menampilkan total bersih; kamus data Finance dibalik; void ditolak bila ada refund.
Uji: `tests/integration/test_refund_hari_lampau.py` (10 test).
Jawaban §6: (1) penyetuju **TIDAK BOLEH** sama dengan pemroses refund · (2) void
**DITOLAK** kalau transaksi sudah punya refund · (3) migrasi skema + data **SETUJU**.
Asal: `AUDIT_ALUR_UANG_2026-10-04.md` Temuan 32 + §"VERIFIKASI DESKTOP".

## 1. Keputusan dr. Hansen (2026-10-05)

1. Refund atas transaksi **hari lampau** butuh otorisasi **PIN Admin/Superadmin/Owner**.
   Uangnya tetap dikembalikan ke pasien; yang dipagari administrasinya.
2. Refund **dibukukan di hari refund**. Hari asal (yang mungkin sudah tutup kasir dan
   sudah diekspor ke Finance) **tidak boleh berubah**.

## 2. Keadaan sekarang (dibaca dari kode, bukan diasumsikan)

| | |
|---|---|
| Satu-satunya jalur refund | `KasirService.refund_item_tertunda` — obat **DIBAYAR tapi belum DISERAHKAN**, per item |
| Siapa boleh | `require_kasir_role` (`routes/obat_tertunda.py:92`) — tanpa otorisasi tambahan, hari apa pun |
| Cara membukukan | **memutasi** `transaksi_kasir.total_tagihan` transaksi asal (`kasir_service.py:1394-1395`) |
| Alasan desain itu | komentar di kode: keputusan dr. Hansen dulu — *"supaya 12 titik agregasi uang otomatis benar tanpa satu pun query disentuh"* |
| Tutup kasir | **sudah benar**: refund dikurangi per metode di hari refund, diatribusikan ke pelaku refund |
| Data refund di DB dev | 2 baris (`jenis_refund='ITEM'`) |

Akibat mutasi header: omzet **hari asal** turun, hari refund tidak bergerak — kebalikan
keputusan no. 2. Jadi mutasi header **harus berhenti**, dan pengurangannya dipindah ke
saat laporan dibaca.

## 3. Rancangan

### 3a. Otorisasi PIN — pola yang SUDAH ADA (upsell)

`upsell_service.py:142-184` sudah melakukan persis ini untuk dokter. Ditiru, bukan
ditulis ulang:

- "Hari lampau" = `tanggal(trx.waktu_bayar) < hari ini` (WIB, `_now_utc7`).
- Refund hari yang **sama** tidak berubah: kasir sendiri, tanpa PIN.
- Refund hari lampau menuntut `id_staf_otorisasi` + `pin_otorisasi`; staf harus aktif,
  punya PIN, berperan `Admin`/`Superadmin`/`Owner`; PIN diverifikasi bcrypt.
- Gagal → audit `REFUND_DITOLAK_PIN` lalu 401 dengan pesan yang **tidak membedakan**
  "PIN salah" dari "staf tidak berwenang" (sama dengan upsell).
- Berhasil → penyetuju dicatat di **kolom** `transaksi_refund.id_staf_otorisasi`
  (bukan hanya di audit log) supaya laporan refund bisa menampilkan siapa menyetujui.

UI: di form refund obat tertunda, kalau transaksinya hari lampau, muncul dropdown
penyetuju + kotak PIN (pola `perawat.py:172` yang sudah memfilter staf ber-PIN).

### 3b. Pembukuan di hari refund — berhenti memutasi header

`total_tagihan` transaksi asal **tidak lagi diubah**. Omzet dihitung:

```
omzet(periode) = SUM(total_tagihan  WHERE waktu_bayar ∈ periode AND status='BAYAR')
               − SUM(nilai_refund   WHERE tgl_refund  ∈ periode AND trx asal 'BAYAR')
```

Satu helper bersama di `reports_service` (sekalian memenuhi niat DEC-079 / Temuan 2),
dipakai oleh titik-titik yang hari ini menjumlah `total_tagihan`:

| Titik | Fungsi | Perlu dikurangi refund? |
|---|---|---|
| Omzet harian | `reports_service.omzet_harian` | **Ya** |
| Omzet bulanan | `reports_service.omzet_bulanan` | **Ya** |
| Rekap harian owner | `rekap_harian_service.rekap` (2 query) | **Ya** (per pasien: lewat `trx.id_pasien`) |
| KPI dashboard | `dashboard_service` (omzet hari ini) | **Ya** |
| Ekspor Finance ringkasan | `export_daily_operational_summary` | **Ya** |
| Rekap shift | `kasir_service.rekap_shift`, `reports_service.rekap_kasir_shift` | ⚠ periksa satu per satu — tutup kasir SUDAH mengurangi refund; jangan dua kali |
| Laporan void | `get_void_report`, `_void_today_stats` | Tidak — menjumlah transaksi VOID |

⚠ Daftar ini dari `grep` atas `sum(total_tagihan)`. Sebelum dikerjakan, **setiap pembaca
`total_tagihan` dibuka satu per satu** (CLAUDE.md §4.1) — termasuk yang membaca per
baris, bukan menjumlah (ekspor `transactions_raw`, nota, riwayat kasir).

### 3c. Akibat yang harus ditangani bersamaan — bukan sesudahnya

1. **Void setelah refund.** Kalau transaksi asal di-VOID sesudah ada refund, omzetnya
   dikecualikan penuh **dan** refundnya tetap mengurangi → dikurangi dua kali.
   Usul: **void ditolak kalau transaksi sudah punya refund** — sejalan dengan aturan
   "void hanya untuk yang belum selesai"; uangnya sudah dikembalikan sebagian.
2. **Kontrak ekspor Finance berbalik.** Kamus data hari ini berkata *"Refund MENGURANGI
   total_tagihan … JANGAN dikurangkan dua kali"*. Sesudah perubahan: `transactions_raw`
   berisi nilai **bruto**, dan penerima **WAJIB** mengurangi `refunds_raw`. Kamus data
   harus diubah di commit yang sama, dan `data_analyst` perlu tahu tanggal peralihannya.
3. **Data lama.** Setiap refund yang sudah ada **sudah memutasi** header-nya. Tanpa
   pemulihan, pembacaan baru akan mengurangi refund lama **dua kali**. Migrasi data
   sekali jalan: `total_tagihan += SUM(nilai_refund)` per transaksi yang punya refund
   (deterministik; nilai lama juga tercatat di audit `REFUND_ITEM.data_lama`). ⚠ Ini
   **mengubah angka hari-hari lampau kembali ke angka saat tutup kasir** — itu justru
   tujuannya, tapi berarti ekspor ulang rentang lama akan berbeda dari yang dulu dikirim.
4. **Nota cetak ulang.** Total nota = total asal (bruto), ditambah baris
   *"Refund <tanggal> −Rp X"* dan *"Netto"*. Hari ini nota menampilkan total yang sudah
   termutasi tanpa penanda.

## 4. Butuh migrasi (persetujuan terpisah, CLAUDE.md §1.3)

| Migrasi | Isi |
|---|---|
| Skema | `transaksi_refund.id_staf_otorisasi INT NULL, FK master_staf` |
| Data | pulihkan `total_tagihan` transaksi yang punya refund (3c.3) — dengan pemeriksa sebelum/sesudah |

## 5. Alternatif yang ditimbang dan TIDAK diusulkan

**Baris penyeimbang** (transaksi `jenis_transaksi='REFUND'` bernilai negatif pada hari
refund). Kelebihannya: 12 titik agregasi tetap tidak disentuh, persis semangat keputusan
lama. Ditolak karena menciptakan "transaksi" palsu yang ikut terhitung di jumlah
transaksi, rata-rata per nota, daftar riwayat kasir, dan setiap query yang mencari
transaksi per pasien — pola §4.1 yang paling mahal di proyek ini (satu baris, dua arti).
Rancangan 3b menyentuh lebih banyak query, tapi setiap sentuhan terlihat dan teruji.

## 6. Pertanyaan untuk dr. Hansen

1. Boleh **penyetuju = orang yang sama** dengan yang memproses refund (Admin yang
   kebetulan bertugas di kasir)? Usul: **tidak** — empat mata.
2. **Void ditolak** kalau transaksi sudah punya refund (3c.1) — setuju?
3. Migrasi skema + migrasi data (§4) — setuju dikerjakan dari desktop, deploy di luar
   jam operasional?

## 7. Uji yang direncanakan (dua arah)

- Refund hari sama tanpa PIN → diterima (perilaku lama tidak rusak).
- Refund hari lampau tanpa PIN / PIN salah / PIN staf Kasir → ditolak 401, audit tercatat.
- Refund hari lampau dengan PIN Admin → diterima, `id_staf_otorisasi` terisi.
- Omzet hari asal **tidak berubah** sesudah refund; omzet hari refund **turun** sebesar nilainya.
  Diuji juga pada kode lama: harus GAGAL (hari asal berubah).
- Total periode yang mencakup kedua hari **sama** dengan sebelum perubahan.
- Void transaksi yang punya refund → ditolak.
- Migrasi data: jumlah `SUM(total_tagihan) − SUM(refund)` seluruh DB sama sebelum/sesudah.
