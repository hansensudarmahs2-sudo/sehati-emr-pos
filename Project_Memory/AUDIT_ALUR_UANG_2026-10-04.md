# Audit alur uang — 2026-10-04 (putaran 1)

Dijalankan dari laptop. Fokus putaran ini: **pengecualian VOID di agregasi uang**.
Temuan utama dibuktikan dengan **menjalankannya**, bukan dengan membaca kode.

---

## TEMUAN 1 — 🔴 Laporan racikan & apoteker menghitung barang dari transaksi yang DI-VOID

**Statusnya: terbukti, bukan dugaan.**

### Skenario yang terjadi

1. Pasien bayar → racikan `DIBAYAR`
2. Apoteker menyerahkan → racikan `DISERAHKAN`, `waktu_serah` terisi
3. Kasir mem-void transaksi → **DITERIMA**, transaksi jadi `VOID`
4. Racikan **tetap `DISERAHKAN`**
5. Laporan omzet mengecualikan transaksi itu (`status_transaksi='BAYAR'`)
6. **Laporan racikan tetap menghitungnya**

Dibuktikan di laptop dengan racikan Rp 225.000:

```
status transaksi : VOID
status racikan   : DISERAHKAN
laporan racikan  : AUDIT Racik Void  batch=1  nominal=225000.0
```

Dua laporan berbeda pendapat tentang uang yang sama. Yang satu bilang transaksi itu
tidak ada; yang lain memasukkannya sebagai omzet terserahkan.

### Kenapa bisa lolos — tiga hal yang masing-masing benar sendiri

1. **Cascade void hanya menangani `DIBAYAR` → `BATAL`.**
   `_cascade_void_kunjungan` (`kasir_service.py:1879`) mencocokkan resep dan racikan
   berstatus `DIBAYAR`. Barang yang sudah `DISERAHKAN` tidak cocok, jadi tidak disentuh.
   Itu masuk akal — barangnya memang sudah keluar, tidak bisa "dibatalkan".

2. **Pagar void hanya menjaga TINDAKAN.**
   `_pagari_void_tindakan_selesai` menolak void kalau ada tindakan `SELESAI`, dengan
   alasan yang ditulis panjang: *"bahan sudah terpakai, komisi sudah layak, kuota member
   sudah terpakai"*. Alasan yang sama persis berlaku untuk racikan/resep yang sudah
   diserahkan — **tapi pagarnya tidak mencakup keduanya.** Tidak ada pagar lain di
   seluruh jalur void.

3. **Laporan menghitung dari status item, bukan dari status transaksi.**
   Keduanya hanya menyaring `status_item == 'DISERAHKAN'` + rentang `waktu_serah`,
   tanpa join ke `transaksi_kasir`:
   - racikan: `reports_service.py:1424` (`head_ids`)
   - resep:   `reports_service.py:1294` (`id_resep_serah`)

Masing-masing keputusan itu benar di tempatnya. Yang salah adalah **tidak ada yang
memeriksa ketiganya sekaligus** — persis pola CLAUDE.md §4.1: *satu hal, dua penulis.*

### Dampak

Laporan racikan, top-produk, dan apoteker-dispensed **melebih-lebihkan** sebesar nilai
barang yang diserahkan sebelum transaksinya di-void. Tidak ada error, tidak ada
peringatan. Selisihnya baru terlihat kalau ada yang membandingkan laporan omzet dengan
laporan apotek — dan tidak ada yang rutin melakukannya.

⚠ Berapa sering ini terjadi di klinik **belum diukur** — butuh query di mesin produksi:

```sql
SELECT COUNT(*), SUM(kr.total)
FROM kunjungan_racikan kr
JOIN transaksi_kasir t ON t.id_kunjungan = kr.id_kunjungan
WHERE kr.status_item = 'DISERAHKAN' AND t.status_transaksi = 'VOID';
```

### Tiga pilihan perbaikan — butuh keputusan dr. Hansen

| Opsi | Apa yang dilakukan | Pertimbangan |
|---|---|---|
| **A. Perluas pagar void** (disarankan) | Tolak void kalau ada resep/racikan sudah `DISERAHKAN`, sejajar dengan pagar tindakan `SELESAI` | **Paling konsisten dengan aturan dr. Hansen** (CLAUDE.md §7): *void hanya untuk yang belum selesai dikerjakan*. Barang yang sudah keluar = pekerjaan selesai. Mengubah perilaku kasir: void yang selama ini diterima akan ditolak |
| B. Laporan join ke status transaksi | Laporan mengecualikan item yang transaksinya VOID | Angka laporan langsung benar tanpa mengubah perilaku kasir. Tapi barangnya **memang keluar** dari stok — laporan apotek jadi tidak mencerminkan apa yang benar-benar diserahkan |
| C. Cascade `DISERAHKAN` → `BATAL` | Void membatalkan juga yang sudah diserahkan | **Tidak disarankan** — menulis kebohongan ke rekam: barangnya sudah di tangan pasien |

Opsi A dan B menjawab pertanyaan yang berbeda, dan jawabannya tergantung apa arti
laporan apotek: *"berapa yang keluar dari stok"* (B salah) atau *"berapa yang terjual"*
(B benar). Itu keputusan dr. Hansen, bukan keputusan teknis.

---

## TEMUAN 2 — 🟡 Helper `only_bayar()` dari DEC-079 tidak pernah dibuat

DEC-079 (A1, 2026-06-29) menetapkan: *"Bikin 1 helper bersama `only_bayar()` supaya tak
terulang."*

**Helper itu tidak ada.** Penyaringan VOID tersebar sebagai **16 penulisan inline**
`status_transaksi == "BAYAR"`, dengan literal string, bukan `StatusTransaksiEnum`.

Duplikasi yang helper itu dimaksudkan untuk mencegah, ada. Dan Temuan 1 adalah bentuk
kegagalan yang sama persis dengan yang dikhawatirkan DEC-079 — hanya saja ia muncul di
tabel klinis, tempat yang tidak terpikir saat itu.

Tidak mendesak diperbaiki sendirian; layak digabung kalau Opsi B dipilih.

---

## Yang DIPERIKSA dan ternyata BERSIH

Dicatat supaya tidak diperiksa ulang.

| Area | Hasil |
|---|---|
| `rekap_harian_service.py` | **Bersih.** 6 query uangnya semua dibungkus `_bayar_today()` yang menyaring `status_transaksi == 'BAYAR'` |
| Cascade void → racikan | **Ada** (Cascade 1b). Dugaan awal saya bahwa racikan terlewat ternyata **salah** — ia ditangani sejajar resep |
| `faktur_calc.py`, `pengadaan.py` | Uang ke **distributor**, bukan transaksi pasien. VOID tidak berlaku |
| Perhitungan diskon saat bayar | Bukan agregasi riwayat; sudah diverifikasi terpisah saat F3 |

---

## Catatan metode

Pemindai otomatis saya melaporkan **32 agregasi uang "tanpa penyaring VOID"**. Setelah
diperiksa satu per satu, **mayoritas positif palsu** — helper penyaring berada di luar
jendela 14 baris yang saya pakai, atau konteksnya memang bukan uang pasien.

Angka mentah dari pemindaian seperti ini **tidak boleh dilaporkan sebagai temuan**.
Yang bernilai hanya yang sudah dibuka satu per satu — dan dari 32, yang benar-benar
bermasalah adalah **satu**, yang justru tidak terdeteksi pemindai (karena ia bukan soal
VOID di query uang, melainkan soal tiga lapisan yang tidak saling memeriksa).

---

## Data uji yang ditinggal di laptop

`kunjungan_racikan` bernama **"AUDIT Racik Void"** (Rp 225.000, `DISERAHKAN`) dengan
transaksi ber-status `VOID` sengaja **dibiarkan** di DB laptop sebagai kasus reproduksi.
Jangan dipakai di mesin lain.

---

## Putaran berikutnya (belum dikerjakan)

1. Refund per item & `transaksi_refund` — apakah ikut dikecualikan dari omzet?
2. `komisi_ledger` — apakah komisi ikut ditarik saat void, dan apa yang terjadi kalau
   periode payroll sudah ditutup (F2 menyebut clawback belum ada)
3. Kuota membership — `_revert_kuota_per_tindakan` saat void
4. Decimal vs float di jalur uang (A9 menyelesaikan 3 loop; sisanya belum disapu)
