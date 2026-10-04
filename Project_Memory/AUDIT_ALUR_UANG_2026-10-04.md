# Audit alur uang — 2026-10-04 (putaran 1)

Dijalankan dari laptop. Fokus putaran ini: **pengecualian VOID di agregasi uang**.
Temuan utama dibuktikan dengan **menjalankannya**, bukan dengan membaca kode.

---

## TEMUAN 1 — ✅ DIPERBAIKI (Opsi A) — dulu: laporan apotek menghitung barang dari transaksi VOID

> **Keputusan dr. Hansen 2026-10-04: Opsi A.** Pagar void diperluas —
> `_pagari_void_item_diserahkan` menolak void kalau ada resep/racikan ber-status
> `DISERAHKAN`, sejajar pagar tindakan `SELESAI`. Terpasang di **dua** titik panggil
> jalur void. Diuji dua arah; lihat §"Bukti perbaikan" di bawah.
>
> ⚠ Ini **memperketat perilaku kasir**: void yang dulu diterima sekarang ditolak.
> Itu disengaja — yang dulu "berhasil" meninggalkan laporan yang salah. Pesan
> penolakannya mengarahkan ke jalur retur/refund.

**Uraian di bawah adalah keadaan SEBELUM perbaikan**, disimpan karena sebabnya layak
diingat — bukan karena masalahnya masih ada.

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

### Bukti perbaikan (2026-10-04)

Diuji lewat `void_transaksi` sungguhan di laptop, bukan simulasi:

| Skenario | Hasil | Status transaksi |
|---|---|---|
| Racikan masih `DIBAYAR` — void **sah** | **DITERIMA** | `VOID` |
| Racikan sudah `DISERAHKAN` | **DITOLAK** | tetap `BAYAR` |
| Resep sudah `DISERAHKAN` | **DITOLAK** | tetap `BAYAR` |

Resep dan racikan diuji **terpisah**: `kunjungan_resep.status_item` adalah ENUM
sedangkan `kunjungan_racikan.status_item` adalah VARCHAR (CLAUDE.md §4.4), jadi
jalur kodenya berbeda dan satu uji tidak membuktikan yang lain.

⚠ Satu percobaan sempat menghasilkan "DITOLAK" yang **menyesatkan** — penolakannya
datang dari validasi panjang catatan void (`minimal 5 karakter`), bukan dari pagar
baru. Diulang dengan catatan yang sah, barulah pagarnya yang menolak. Pesan penolakan
yang kebetulan muncul bukan bukti bahwa pagar bekerja.

Regresi: `tests/integration/test_kasir_void_exclusion.py` tetap 4 lulus / 1 gagal —
kegagalan yang sama sudah terbukti pra-ada (lihat commit F3).

### Tiga pilihan yang dipertimbangkan — Opsi A dipilih

| Opsi | Apa yang dilakukan | Pertimbangan |
|---|---|---|
| **A. Perluas pagar void** ← **DIPILIH** | Tolak void kalau ada resep/racikan sudah `DISERAHKAN`, sejajar dengan pagar tindakan `SELESAI` | **Paling konsisten dengan aturan dr. Hansen** (CLAUDE.md §7): *void hanya untuk yang belum selesai dikerjakan*. Barang yang sudah keluar = pekerjaan selesai. Mengubah perilaku kasir: void yang selama ini diterima akan ditolak |
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

---

# PUTARAN 2 — refund, komisi, kuota, Decimal/float

---

## TEMUAN 3 — 🔴 `force_past_day_void` TIDAK membatalkan komisi

**Terbukti dengan menjalankannya.**

Jalur void ada **dua**. Hanya satu yang membalik komisi:

| Jalur | Dipakai siapa | Transaksi | Komisi |
|---|---|---|---|
| `void_transaksi` (hari sama) | Kasir | `VOID` | **`VOID`** ✓ |
| `force_past_day_void` (s/d 7 hari) | Admin / Superadmin / Owner | `VOID` | **tetap `AKTIF`** ✗ |

Bukti di laptop, komisi produk Rp 5.000:

```
force_past_day_void:  trx BAYAR -> VOID  |  komisi AKTIF -> AKTIF   (tidak berubah)
void_transaksi     :  trx BAYAR -> VOID  |  komisi AKTIF -> VOID
```

Akibatnya staf tetap menerima komisi atas transaksi yang sudah dibatalkan dan sudah
dikeluarkan dari omzet.

### Kelupaan, atau disengaja?

**Petunjuk kuat bahwa ini kelupaan:** `force_past_day_void` mengerjakan *semua* langkah
pembersihan lain — pagar, status VOID, balik stok, cascade resep/racikan,
`_revert_kuota_per_tindakan`. **Kuota diingat di kedua jalur; komisi hanya di satu.**
Dan tidak ada satu pun komentar yang menjelaskan ketiadaannya, di kodebase yang
biasanya menjelaskan setiap keputusan.

**Petunjuk bahwa mungkin disengaja:** backlog **F2** mencatat *"detail clawback VOID
(kalau periode payroll sudah ditutup)"* sebagai Fase 2 yang DITUNDA. `force_past_day_void`
justru jalur yang menyentuh hari-hari lampau — persis tempat periode payroll bisa sudah
ditutup. Mungkin komisi sengaja tidak ditarik supaya payroll yang sudah dibayar tidak
berubah surut.

Kalau benar begitu, **itu keputusan yang tidak pernah ditulis** — dan keputusan yang
tidak ditulis tidak bisa dibedakan dari kelupaan.

### Butuh keputusan dr. Hansen

| Opsi | Konsekuensi |
|---|---|
| **A. Panggil `void_komisi_transaksi` juga di `force_past_day_void`** | Konsisten dengan jalur harian. Tapi kalau payroll periode itu sudah dibayar, komisi ditarik surut — uang yang sudah di tangan staf |
| **B. Biarkan, tapi TULIS alasannya** | Payroll aman. Konsekuensinya: komisi atas transaksi VOID tetap terbayar, dan laporan komisi tidak cocok dengan omzet |
| **C. Tarik komisi hanya kalau periode payroll belum ditutup** | Paling benar, tapi butuh konsep "periode payroll ditutup" yang **belum ada** (itu isi F2) |

Saya tidak memperbaikinya sendiri: ini mengubah uang yang terutang ke staf.

---

## TEMUAN 4 — 🟡 Perhitungan komisi memakai float, bukan Decimal

`hitung_komisi_treatment` (`master_treatment_service.py:68`) bekerja dengan `float`
dari ujung ke ujung — harga, BHP, pajak, persentase — lalu hasilnya disimpan ke kolom
`DECIMAL`. A9 sudah memperbaiki kelas masalah yang sama di 3 loop laporan; mesin komisi
belum tersentuh.

**Diukur, bukan diasumsikan.** 300.000 kombinasi harga/BHP/persen acak dalam rentang
wajar klinik:

```
selisih float vs Decimal : 7.288 dari 300.000  (2,43%)
contoh: harga=4.361.767,80  bhp=741.500,53  50%
        float   = 1.810.133,63
        Decimal = 1.810.133,64
```

**Besarnya satu sen per baris yang terkena.** Dalam rupiah itu tidak berarti apa-apa
secara operasional. Yang membuatnya layak dicatat bukan nominalnya, melainkan bahwa
proyek ini **sudah memutuskan** uang tidak dihitung dengan float (A9) — dan mesin yang
menentukan bayaran staf justru masih memakainya.

⚠ **Catatan metode yang penting:** percobaan pertama saya memakai **5 kasus pilihan
tangan** dan menemukan **nol selisih**. Kalau berhenti di situ, saya akan melaporkan
"float aman di sini" — dan itu salah. Contoh pilihan tangan tidak membuktikan apa pun
tentang floating point; yang membuktikan adalah pencarian paksa.

Prioritas rendah, perbaikan murah. Layak digabung kalau F2 (komisi Fase 2) dikerjakan.

---

## Yang DIPERIKSA di putaran 2 dan ternyata BERSIH

| Area | Hasil |
|---|---|
| **Refund vs omzet** | **BERSIH.** Dugaan awal saya salah. `proses_refund_item` langkah 6 **mengurangi `trx.total_tagihan`** dengan alasan tertulis: *"header yang dikurangi, supaya 12 titik agregasi uang otomatis benar tanpa satu pun query disentuh"*. Omzet otomatis benar |
| **Refund vs tutup kasir** | **BERSIH, tidak ada pengurangan ganda.** Tutup kasir memakai `transaksi_pembayaran` (TIDAK tersentuh refund) dikurangi refund per metode; omzet memakai `total_tagihan` yang sudah dikurangi. Dua basis berbeda, keduanya benar |
| **Revert kuota membership** | **BERSIH.** `_revert_kuota_per_tindakan` dipanggil di **kedua** jalur void |
| `float()` di service lain | Mayoritas di **batas keluaran** (cetak nota, dict tampilan) — sah menurut A9 |

---

## Catatan yang sudah terdokumentasi di kode (bukan temuan baru)

`void_komisi_item` punya peringatan di docstring-nya sendiri: untuk `sumber='PRODUK'`,
`id_ref` diisi `id_resep` dengan **fallback** ke `id_produk`. Pada baris LAMA yang
tersimpan lewat jalur fallback, pembatalan komisi saat refund **bisa tidak kena**.
Sudah ditulis di sana; dicatat di sini supaya tidak hilang.

---

---

# PUTARAN 3 — membership, retur, tutup kasir

---

## TEMUAN 5 — 🔴 `force_past_day_void` adalah `void_transaksi` DIKURANGI TIGA LANGKAH

Putaran 2 menemukan komisi tidak ditarik, dan saya mencatat dua bacaan: kelupaan, atau
sengaja demi payroll. **Putaran 3 menyelesaikan pertanyaan itu.**

Perbandingan menyeluruh kedua fungsi (bukan pencarian satu per satu):

| Langkah | `void_transaksi` | `force_past_day_void` |
|---|---|---|
| `_pagari_void_tindakan_selesai` | ✓ | ✓ |
| `_pagari_void_item_diserahkan` | ✓ | ✓ |
| `_cascade_void_kunjungan` | ✓ | ✓ |
| `_reverse_stok_per_item` | ✓ | ✓ |
| `_revert_kuota_per_tindakan` | ✓ | ✓ |
| `audit.log` | ✓ | ✓ |
| **`void_komisi_transaksi`** | ✓ | **HILANG** |
| **`revert_paid_to_pending`** | ✓ | **HILANG** |
| **`revert_active_to_pending`** | ✓ | **HILANG** |

`force_past_day_void` **tidak menambahkan satu pun langkah miliknya sendiri.** Ia
salinan yang kehilangan tepat tiga langkah, dan ketiganya sejenis: pengembalian catatan
turunan. Itu bukan keputusan payroll — kalau disengaja demi payroll, membership tidak
punya urusan ikut tertinggal.

**Bacaan "disengaja" dari putaran 2 dengan ini gugur.**

### Tiga akibatnya, semua dibuktikan dengan menjalankannya

```
1. KOMISI
   force_past_day_void : trx BAYAR -> VOID  |  komisi AKTIF -> AKTIF
   void_transaksi      : trx BAYAR -> VOID  |  komisi AKTIF -> VOID

2. MEMBERSHIP masih PAID (belum diaktifkan CS)
   force_past_day_void : trx VOID  |  history PAID,  id_trx masih menunjuk trx
   void_transaksi      : trx VOID  |  history PENDING, id_trx dikosongkan
   -> CS bisa mengaktifkannya; pasien dapat tier atas pembayaran yang dibatalkan.

3. MEMBERSHIP sudah ACTIVE — KASUS TERBURUK
   sebelum : trx BAYAR | history ACTIVE aktif=1 | pasien.tipe = VVIP
   sesudah : trx VOID  | history ACTIVE aktif=1 | pasien.tipe = VVIP
   -> Pasien MEMPERTAHANKAN diskon VVIP untuk SELURUH kunjungan berikutnya,
      atas pembayaran Rp 5.000.000 yang sudah dibatalkan.
```

Nomor 3 yang paling mahal: akibatnya tidak berhenti di satu transaksi, melainkan
menempel ke pasien dan mengurangi setiap tagihan sesudahnya.

### Perbaikannya sekarang jelas, bukan lagi pilihan

Tambahkan tiga panggilan yang hilang ke `force_past_day_void`, sejajar `void_transaksi`.
Pertimbangan payroll dari putaran 2 **tidak gugur** — kalau periode payroll sudah
ditutup, menarik komisi surut tetap persoalan nyata. Tapi itu persoalan **F2** yang
berlaku untuk KEDUA jalur, bukan alasan membiarkan `force_past_day_void` pincang.

**Tetap menunggu dr. Hansen** karena menyentuh uang staf dan status membership pasien.
Saya tidak memperbaikinya sendiri.

---

## Yang DIPERIKSA di putaran 3 dan ternyata BERSIH

| Area | Hasil |
|---|---|
| **Pendapatan membership di omzet** | **BERSIH.** Rekap harian menghitungnya: 6 transaksi, Rp 8.676.790,14 = KLINIS 3.676.790,14 + MEMBERSHIP 5.000.000. Diverifikasi dengan menjalankan `RekapHarianService.rekap()` |
| **Transaksi membership tidak terjatuh dari JOIN** | **BERSIH.** `id_kunjungan` memang NULL untuk MEMBERSHIP, tapi kedua query yang menggabungkan `TransaksiKasir` ke `Kunjungan` memakai `isouter=True` (`print_service.py:80`, `reports_service.py:774`) — disengaja |
| **Tidak ada laporan menyaring `jenis_transaksi`** | Benar, dan itu **tepat**: membership adalah pendapatan nyata. Tidak ada dobel-hitung — `subtotal_aktivasi_membership` di tagihan klinis selalu 0/None sejak M2 |
| **Retur ke distributor** | **BERSIH.** Tidak disebut sama sekali di `reports_service`, `rekap_harian_service`, maupun `kasir_closing_service` — uang ke distributor tidak bocor ke laporan omzet pasien |

---

## Belum dikerjakan dari rencana putaran 3

**Ekspor Finance vs laporan layar** — apakah 15 berkas ekspor konsisten dengan angka di
layar. Belum disentuh; butuh membandingkan isi berkas dengan query laporan satu per satu.
Dicatat jujur sebagai sisa, bukan dilewatkan diam-diam.

---

## Putaran berikutnya (belum dikerjakan)

~~1. Refund per item~~ · ~~2. komisi saat void~~ · ~~3. revert kuota~~ ·
~~4. Decimal vs float~~ — **semua selesai di putaran 2.**

~~1. Membership~~ · ~~2. Retur distributor~~ — **selesai di putaran 3.**

Sisa & usulan putaran 4:
1. **Ekspor Finance vs laporan layar** — sisa dari putaran 3
2. Tutup kasir: selisih laci, modal awal, slip cetak (baru disentuh dari sisi refund)
3. Komisi Fase 2 (F2): konsep "periode payroll ditutup" — prasyarat perbaikan Temuan 5
4. Stok: `_reverse_stok_per_item` & FEFO saat void/retur
