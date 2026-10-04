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

## TEMUAN 5 — ✅ DIPERBAIKI — dulu: `force_past_day_void` kehilangan 3 langkah

> **Keputusan dr. Hansen 2026-10-04: perbaiki ketiganya.** Ditambahkan ke
> `force_past_day_void`: `revert_active_to_pending`, `revert_paid_to_pending`, dan
> `void_komisi_transaksi` — sejajar `void_transaksi`. Hasil rollback membership ikut
> dicatat di jejak audit (`membership_history_reverted`), karena tanpa angka itu jejaknya
> tidak bisa membuktikan rollback benar terjadi.
>
> **Bukti sesudah perbaikan**, lewat `force_past_day_void` sungguhan:
>
> ```
> 1. KOMISI            : AKTIF  -> VOID      OK
> 2. MEMBERSHIP PAID   : PAID   -> PENDING   OK
> 3. MEMBERSHIP ACTIVE : ACTIVE -> PENDING   OK
> ```
>
> Jalur harian diuji ulang (tidak boleh rusak): `trx VOID | komisi VOID`.
> Regresi `test_kasir_void_exclusion` tetap 4 lulus / 1 gagal pra-ada. 37 halaman 200.
>
> Diff pemanggilan diulang **tanpa saringan kata kunci** — saringan di putaran 3 bisa
> melewatkan langkah yang namanya tidak mengandung kata kunci itu. Sesudah perbaikan,
> satu-satunya yang berbeda tinggal `_is_same_calendar_day_utc7`, dan itu memang
> pemeriksaan hari-sama yang tidak berlaku di jalur hari-lampau.

### ⚠ KODE SUDAH DIPERBAIKI, BARIS YANG TERLANJUR RUSAK BELUM

Perbaikan ini **tidak menyentuh data yang sudah telanjur salah**. Di mesin produksi
mungkin ada membership yang masih PAID/ACTIVE dan komisi yang masih AKTIF atas transaksi
yang sudah di-VOID lewat jalur lama. **Jalankan di mini PC:**

```sql
-- Membership masih PAID/ACTIVE padahal transaksinya VOID
SELECT h.id_history, h.id_pasien, m.nama_tier, h.status_aktivasi, h.is_active,
       h.id_transaksi_aktivasi
FROM pasien_membership_history h
JOIN transaksi_kasir t ON t.id_transaksi = h.id_transaksi_aktivasi
JOIN master_membership m ON m.id_membership = h.id_membership
WHERE t.status_transaksi = 'VOID' AND h.status_aktivasi IN ('PAID','ACTIVE');

-- Komisi masih AKTIF padahal transaksinya VOID
SELECT k.id_komisi, k.id_transaksi, k.sumber, k.komisi_nominal, k.status
FROM komisi_ledger k
JOIN transaksi_kasir t ON t.id_transaksi = k.id_transaksi
WHERE t.status_transaksi = 'VOID' AND k.status = 'AKTIF';
```

Kedua query diuji di laptop dan menemukan tepat 3 baris rusak — sisa dari uji
**pra-perbaikan** saya sendiri. Itu sekaligus bukti bahwa kerusakannya bertahan di DB,
bukan hanya di jalannya kode.

Pembersihannya **belum diputuskan**: menurunkan membership yang terlanjur ACTIVE berarti
mencabut tier dari pasien yang mungkin sudah memakai diskonnya; menarik komisi yang
sudah dibayar berarti menagih staf. Keduanya keputusan dr. Hansen, bukan `UPDATE` massal.

**Uraian di bawah adalah keadaan SEBELUM perbaikan.**

### Dulu: `force_past_day_void` = `void_transaksi` dikurangi tiga langkah

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

---

# PUTARAN 4 — ekspor Finance, tutup kasir, stok saat void

---

## TEMUAN 6 — ✅ DIPERBAIKI — kamus data ekspor bisa membuat analis mengurangi VOID DUA KALI

Angkanya **benar**; **deskripsinya** yang menyesatkan — dan untuk paket yang kontraknya
adalah kamus data, itu cukup untuk menghasilkan laporan yang salah di sisi penerima.

Kamus data punya dua jenis dataset:

| Jenis | Isi kamus | Kenyataan di kode |
|---|---|---|
| **Mentah** (`transaksi_raw`) | Kolom `status_transaksi` ber-peringatan tegas: *"untuk omzet filter status='BAYAR'; VOID JANGAN dihitung sebagai penjualan"* | Benar — analis memang harus menyaring sendiri |
| **Agregat** (`daily_operational_summary`) | *"Sum total_tagihan transaksi_kasir di tanggal ini (Rp)."* — **tanpa menyebut VOID** | Kode **SUDAH** menyaring (`status_transaksi == 'BAYAR'`, komentar `# A1: exclude VOID`) |

Analis yang menuruti peringatan di dataset mentah lalu menerapkannya ke dataset agregat
akan **mengurangi VOID dua kali**, dan melaporkan omzet **terlalu kecil**. Arah salahnya
spesifik dan bisa diprediksi.

**Diperbaiki:** tiga deskripsi (`total_omzet`, `total_diskon`, `jumlah_transaksi`)
sekarang menyatakan secara eksplisit bahwa VOID **sudah** dikecualikan, berikut
peringatan untuk tidak menguranginya lagi. Tidak ada angka yang berubah.

---

## Yang DIPERIKSA di putaran 4 dan ternyata BERSIH

### Ekspor Finance vs laporan layar — COCOK PERSIS

Sisa yang tertunda dari putaran 3. Diuji untuk 2026-10-04 dengan tiga cara berbeda:

```
SQL langsung (BAYAR) : 6 trx | 8.676.790,14
Rekap layar          : 6 trx | 8.676.790,14
Ekspor Finance       : 6 trx | 8.676.790,14
```

Ketiganya sepakat, termasuk transaksi MEMBERSHIP yang `id_kunjungan`-nya NULL.

### Tutup kasir — snapshot beku, dan itu BENAR

`kasir_closing` menyimpan `total_expected`, `total_counted`, `total_selisih`, dan
`detail_metode` (JSON) **pada saat tutup**. Void yang terjadi belakangan **tidak**
mengubahnya — dan itu memang seharusnya: uang fisiknya sudah dihitung malam itu.
Mengubah angka tutup kasir surut akan membuat petugas disalahkan atas selisih yang
tidak pernah ada di lacinya.

Konsekuensinya — `SUM(closing.total_counted)` lintas hari **tidak akan sama** dengan
omzet, kalau ada void menyusul. Itu bukan kesalahan; keduanya mengukur hal berbeda
(uang terhitung vs pendapatan bersih).

Dan jalur rekonsiliasinya **sudah ada**: transaksi punya penanda `late_void` (TRUE hanya
kalau `days_past > 0`), dan **Laporan Void menampilkan `late_void_count`**. Jadi void
yang terjadi setelah shift ditutup bisa dilihat, bukan tersembunyi.

---

## Observasi, BUKAN temuan — `lot_map` hanya ada di satu jalur void

`void_transaksi` meneruskan `lot_map` ke `_reverse_stok_per_item`;
`force_past_day_void` tidak, dan route-nya juga tidak mengumpulkannya.

Saya **tidak** menyebutnya cacat: docstring `_reverse_stok_per_item` menyatakan
perilakunya secara eksplisit — *"Kalau batch tak dipilih → buat lot 'VOID-RETURN' baru"*.
Itu fallback yang terdefinisi, dan untuk void hari lampau bisa dibilang **lebih aman**:
stoknya kembali dengan penanda "dari transaksi lampau yang dibatalkan", bukan diam-diam
bercampur ke batch asal yang mungkin sudah habis atau kedaluwarsa.

**Pertanyaan untuk dr. Hansen, bukan untuk saya:** apakah jalur force-void sebaiknya ikut
menawarkan dropdown pilih-batch demi jejak QC yang setara? Itu keputusan produk.

⚠ Catatan: kalau kasir tidak mencentang item apa pun, `_reverse_stok_per_item` keluar
lebih awal dan **tidak ada stok yang dikembalikan sama sekali**. Itu juga disengaja —
barang rusak tidak boleh kembali ke stok.

---

---

# PUTARAN 5 — pengadaan (uang KELUAR ke distributor)

Jalur uang keluar belum pernah diaudit utuh; putaran 1 hanya memastikan ia tidak bocor
ke laporan omzet pasien.

---

## TEMUAN 7 — 🟡 Yang DIUJI tidak dipakai; yang DIPAKAI tidak diuji

`app/services/faktur_calc.py` adalah modul yang ditulis rapi: murni Decimal, tanpa
dependensi DB, berdokumentasi rumus, dan punya unit test sendiri
(`tests/unit/test_faktur_calc.py`). Saya uji-properti dengan 20.000 faktur acak —
**rekonsiliasinya nol meleset.**

**Tapi produksi tidak pernah memanggilnya.** Perhitungan faktur yang benar-benar
berjalan ada **inline di route** (`app/web/routes/pengadaan.py:862–880`), dan memakai
**model yang berbeda**:

| | `faktur_calc` (tidak dipakai) | Route (live) |
|---|---|---|
| Penggerak | Total ditagih Y → turunkan harga per item | **Harga terima per item** (bisa diedit) → turunkan total |
| Arah | Diskon TERBALIK | Maju |
| Unit test | **Ada** | **Tidak ada** |

Komentar di route menyatakannya eksplisit: *"Faktur digerakkan oleh HARGA TERIMA per
item (source of truth; editable)"*. Jadi `faktur_calc` adalah model **lama yang
tergantikan**, bukan bug — sama kategorinya dengan `create_kunjungan_billing`.

**Akibatnya yang perlu disadari:** suite test memberi rasa aman yang keliru untuk area
ini. Yang lulus test adalah rumus yang tidak dipakai; rumus yang menentukan berapa
klinik membayar distributor tidak punya unit test sendiri (hanya tersentuh tidak sengaja
oleh `test_stok_lot.py`).

**Saran:** ekstrak perhitungan inline di route ke fungsi murni — lalu salah satu dari:
hapus `faktur_calc` (tergantikan), atau jadikan ia rumah bagi kedua model. Keputusan
dr. Hansen. Saya tidak menyentuhnya.

### ⚠ Koreksi atas klaim saya sendiri

Saya sempat menulis bahwa `faktur_calc` **"tidak pernah diimpor di mana pun"**. Itu
**salah**: ia diimpor oleh unit test-nya. Saya men-grep hanya folder `app/` lalu
menyatakan kesimpulan tanpa menyebut batasan itu. Yang benar: **tidak dipanggil kode
produksi**, dan itu klaim yang berbeda.

---

## TEMUAN 8 — 🟡 Subtotal PO memakai float — tapi hanya menggigit kuantitas pecahan

`pemesanan_service.py:169` menghitung `subtotal = float(harga_satuan) * float(qty_dipesan)`
dan menyimpannya ke kolom `DECIMAL(14,2)`. Tetangganya, `faktur_calc`, sengaja ditulis
"murni Decimal" — dua pendekatan berbeda di satu modul pengadaan.

⚠ Lebih dalam dari itu: **`pemesanan_item.qty_dipesan` bertipe `float` DI DATABASE**,
bukan DECIMAL. Jadi kuantitasnya sudah biner sebelum dikalikan.

**Diukur**, 200.000 kombinasi acak per kelompok:

| Kuantitas | Meleset |
|---|---|
| **Bulat** (produk: box, strip, pcs) | **0 dari 200.000 — nol** |
| **Pecahan** (bahan: gram, ml) | **762 dari 200.000 (0,38%)**, masing-masing 1 sen |

Jadi dampaknya **terbatas pada pemesanan bahan dengan kuantitas pecahan**. Untuk produk
yang dipesan per satuan utuh, float di sini persis. Lebih sempit daripada temuan komisi
(Temuan 4) yang 2,43%.

Prioritas rendah. Angkanya pun **estimasi PO**, bukan uang yang dibayar — yang dibayar
dihitung ulang saat faktur, dan jalur itu memakai Decimal.

---

## Yang DIPERIKSA di putaran 5 dan ternyata BERSIH

| Area | Hasil |
|---|---|
| **Penerimaan parsial** | **BERSIH.** `received` dibangun HANYA dari item yang qty-nya diisi di form penerimaan — qty **diterima**, bukan qty dipesan. Klinik tidak membayar barang yang tidak datang |
| **Rekonsiliasi faktur** | Diuji-properti 20.000 faktur acak: `subtotal_setelah_diskon × (1+PPN) − extra_diskon == total_ditagih` **persis, nol meleset**. ⚠ Tapi itu menguji `faktur_calc` yang TIDAK DIPAKAI (Temuan 7) |
| **`diskon_persen` faktur** | **BERSIH.** Hanya untuk tampilan di cetakan, dan rupiah yang ditampilkan adalah selisih sebenarnya (`subtotal_order − subtotal_setelah_diskon`), **bukan** dihitung ulang dari persentase. Tidak ada risiko hitung-ulang |
| **Harga terima per item** | Decimal sejak dibaca dari form; `float` hanya sebagai perantara string→angka, lalu `Decimal(str(...))` yang memulihkan nilainya |

---

## TEMUAN METODE — sapuan kode mati saya sendiri punya dua titik buta

Ditemukan saat putaran ini, dan berlaku surut ke `DEAD_CODE_SWEEP_2026-10-04.md`:

1. **`__all__` menggelembungkan hitungan.** Nama yang terdaftar di `__all__` muncul dua
   kali (definisi + daftar), sehingga lolos dari syarat "pemakaian ≤ jumlah definisi".
   Itu sebabnya `hitung_dari_total` tidak pernah muncul di daftar 14.
2. **Memberi penanda pada kode mati membuatnya tampak hidup.** Komentar yang saya
   tambahkan sendiri di `membership_service.py` menyebut `create_kunjungan_billing`,
   dan itu cukup membuatnya **hilang** dari sapuan berikutnya.

Sapuan diulang dengan blok `__all__` dibuang: **14 → 16 kandidat**. Tiga nama baru
muncul, dua di antaranya di `_shared.py`:

```
session_expired                      app/web/routes/_shared.py:503
user_can_purchase_bahan              app/web/routes/_shared.py:407
user_can_purchase_produk_cabin_alat  app/web/routes/_shared.py:415
```

⚠ `session_expired` justru salah satu helper yang A8/DEC-084 buat sebagai bentuk baku —
kalau ia benar tidak terpakai, itu pertanda helper bakunya tidak diadopsi. Belum
diselidiki.

**Pelajarannya:** sapuan berbasis hitung-nama rapuh terhadap hal-hal yang bukan
pemakaian (daftar ekspor, komentar, dokumen). Daftar mana pun darinya adalah
**kandidat**, bukan vonis — dan itu sebabnya aturan "jangan hapus buta" benar.

---

---

# PUTARAN 6 — retur ke distributor + helper A8 yang tak teradopsi

---

## TEMUAN 9 — 🟡 Nilai refund retur diketik tanpa pembanding apa pun

Nota retur punya dua jenis penyelesaian, dan keduanya mengisi kolom yang sama:

| Jenis | `total_nilai` diisi dari | Artinya |
|---|---|---|
| **TUKAR_BARANG** | **dihitung** `Σ Decimal(harga) × Decimal(qty)` barang pengganti | nilai barang yang DITERIMA |
| **REFUND** | **diketik operator** di form | uang yang DIKREDIT distributor |

Untuk REFUND, formnya hanya kotak angka kosong berplaceholder *"mis. 500000"* —
**tidak ada nilai pembanding yang ditampilkan.** Bagian TUKAR justru menampilkan qty
dan harga per item.

Datanya **ada**: `retur_produk_item` menyimpan `qty` dan `harga_terima` (snapshot dari
lot). Tapi tidak pernah dijumlahkan, tidak ditampilkan, dan tidak dibandingkan. Salah
ketik satu angka nol lolos tanpa perlawanan dan langsung tercetak di nota.

**Dampaknya hari ini terbatas** — `total_nilai` tidak diagregasi di mana pun; ia hanya
muncul di cetakan nota. Tapi backlog memindahkan AP/hutang faktur ke **modul Finance**,
dan begitu modul itu dibangun, angka inilah yang jadi dasar piutang ke distributor.

**Saran:** tampilkan `Σ qty × harga_terima` sebagai nilai acuan di sisi form REFUND —
tidak memaksa harus sama (distributor memang bisa mengkredit beda), hanya memberi
operator sesuatu untuk dibandingkan.

### Satu kolom, dua arti — belum menggigit, tapi perangkapnya sudah terpasang

`total_nilai` berarti *uang diterima* pada REFUND dan *nilai barang diterima* pada TUKAR.
Hari ini tidak ada yang menjumlahkannya lintas jenis, jadi belum ada laporan yang salah.
Tapi siapa pun yang nanti menulis `SUM(total_nilai)` untuk modul Finance akan menjumlah
dua hal yang berbeda. Pola CLAUDE.md §4.1 persis, terpasang menunggu.

---

## TEMUAN 10 — 🟡 Bentuk baku A8/DEC-084 tidak teradopsi, dan `web_guard` punya cacat laten

A8/DEC-084 (2026-07-02) membuat empat helper bersama supaya bentuk 403 dan
sesi-habis dibakukan. Kenyataannya:

| Helper | Dipakai? |
|---|---|
| `login_redirect` | ✓ dipakai |
| `forbidden` | ✓ dipakai |
| **`session_expired`** | **nol** |
| **`web_guard`** | **nol** — dua "pemanggilan" yang terlihat adalah definisinya sendiri dan contoh di dalam docstring-nya |

Sementara itu ada **288 pemanggilan `get_user_from_cookie` langsung** di route.
DEC-084 memang menetapkan migrasi ~180 call-site sebagai **bertahap** ("route baru wajib
pakai; legacy migrasi saat disentuh"), jadi ini bukan pelanggaran — tapi setelah 3 bulan,
adopsinya **nol**, termasuk di route baru.

### Cacat laten di helper-nya sendiri

`web_guard` menerima `partial: bool` dan memakainya untuk `forbidden(partial=partial)` —
tapi cabang **sesi habis** mengembalikan `login_redirect()` **tanpa melihat `partial`**:

```python
user = get_user_from_cookie(request, db)
if user is None:
    return None, login_redirect()        # <- 303 redirect, partial DIABAIKAN
if role_check is not None and not role_check(user):
    return None, forbidden(partial=partial)
```

Untuk fragmen HTMX, 303 ke `/web/login` membuat **halaman login utuh di-swap ke dalam
panel kecil**. Itu persis yang `session_expired(partial=True)` ditulis untuk cegah — ia
mengembalikan 401 + fragmen pesan singkat — dan ia **tidak pernah dipanggil**.

Dampaknya **nol hari ini** (tidak ada yang memakai `web_guard`). Tapi cacat ini akan
**ikut membesar seiring adopsi**: setiap route partial yang bermigrasi mewarisinya.

**Perbaikannya dua baris** — ganti `login_redirect()` dengan
`session_expired(partial=partial)` saat `partial=True`. Saya tidak menyentuhnya:
menunggu keputusan dr. Hansen, sekalian dengan apakah migrasi A8 diteruskan atau
helpernya dibuang.

---

## Yang DIPERIKSA di putaran 6 dan ternyata BERSIH

| Area | Hasil |
|---|---|
| **Total retur TUKAR** | **BERSIH.** `Decimal(str(harga)) * Decimal(str(qty))`, murni Decimal |
| **`total_nilai` hilir** | Hanya dipakai untuk **cetakan nota**. Tidak diagregasi di laporan mana pun |
| **`ttl_cache.invalidate` menganggur** | **Tidak berisiko.** Saya curiga cache antrian bisa basi tanpa invalidasi — diperiksa: `ANTRIAN_TTL = 12 detik`, dan ada `clear()` manual di halaman cache-stats. Basi maksimal 12 detik |

---

## TEMUAN METODE (lanjutan) — titik buta KETIGA, lalu metodenya diganti

Putaran 5 menemukan dua titik buta sapuan kode mati (`__all__`, komentar). Putaran 6
menemukan yang **ketiga: contoh di dalam docstring.** `web_guard` muncul di docstring-nya
sendiri, dan itu cukup membuatnya lolos dari sapuan berbasis hitung-teks.

Ketiganya satu akar: **hitung-teks tidak bisa membedakan pemakaian dari penyebutan.**
Metodenya diganti:

| Metode | Hasil | Masalah |
|---|---|---|
| Hitung-teks | 14 → 16 | **Menggelembung** — `__all__`, komentar, docstring dihitung sebagai pemakaian |
| AST saja (`Name`/`Attribute` Load) | 36 | **Mengempis** — semua `export_*_raw` salah tertuduh; dipanggil `getattr(svc, nama)` dari registry |
| **AST + literal string (kecuali isi `__all__`) + template** | **20** | metode yang dipakai sekarang |

Yang terakhir menangani keduanya: panggilan nyata lewat AST, dispatch dinamis lewat
literal string, dan `__all__` dikecualikan agar daftar ekspor tidak menyelamatkan kode
mati. `export_*_raw` tidak lagi salah tertuduh.

**Enam nama baru** yang tiga metode sebelumnya lewatkan: `create_kunjungan_billing`,
`get_draf_apotek`, `invalidate`, `session_expired`, `web_guard`,
`user_can_purchase_bahan`/`_produk_cabin_alat`.

⚠ Daftar 20 ini **tetap kandidat, bukan vonis**. Tiga kali metodenya diperbaiki dan tiga
kali angkanya berubah — itu sendiri alasan kenapa "jangan hapus buta" benar.

---

---

# PUTARAN 7 — laporan komisi & stock opname

---

## TEMUAN 11 — 🔴 BUKTI: baris komisi yang rusak IKUT TERBAYAR

Bukan temuan baru melainkan **demonstrasi** akibat Temuan 5. Saya kejar sampai ke angka
payroll, karena "mungkin ada baris rusak" dan "baris rusak terbayarkan" adalah dua
pernyataan yang sangat berbeda bobotnya.

Isi `komisi_ledger` di laptop sesudah perbaikan putaran 3:

```
trx=45  trx_status=VOID  PRODUK  komisi=AKTIF  5000.00   <- rusak (void PRA-perbaikan)
trx=46  trx_status=VOID  PRODUK  komisi=VOID   5000.00   <- benar (void_transaksi)
trx=51  trx_status=VOID  PRODUK  komisi=VOID   5000.00   <- benar (force void, SESUDAH)
trx=63  trx_status=VOID  PRODUK  komisi=VOID   3750.00   <- benar
```

Laporan komisi Oktober:

```
per_staf[0] = {'nama_staf': 'dr. Hansen Sudarma', 'produk': 5000.0, 'total': 5000.0}
```

**Rp 5.000 itu persis baris trx=45** — komisi atas transaksi yang sudah di-VOID, masuk
utuh ke angka payroll.

Laporannya **tidak salah**: `komisi_report_service` menyaring `status == 'AKTIF'` dan
memakai Decimal, dengan dokumentasi yang menyebutkannya. Yang salah adalah **barisnya**,
dan barisnya salah karena bug `force_past_day_void` yang sudah diperbaiki — tapi
perbaikan kode tidak menyentuh baris yang terlanjur dibuat.

**Konsekuensinya langsung:** setiap baris rusak di mini PC = komisi yang dibayarkan atas
penjualan yang dibatalkan. Query deteksinya ada di Temuan 5. Menjalankannya bukan lagi
sekadar kehati-hatian.

---

## TEMUAN 12 — 🟡 Nilai rupiah selisih stok opname tidak pernah dicatat

`stock_opname.total_selisih_value` bertipe `DECIMAL(14,2)`, diekspos di schema dan di
dua route (`float(op.total_selisih_value) if op.total_selisih_value else None`), dan
repo-nya punya parameter untuk mengisinya.

**Tidak ada yang pernah mengisinya.** `approve_opname` memanggil `update_status()` tanpa
`total_selisih_value`; jalur reject juga tidak. Kolomnya selalu NULL.

Kelas yang sama dengan **F3** (`transaksi_detail_tindakan` yang tak pernah ditulis):
kolom uang yang ada, terdokumentasi, dan tidak pernah terisi.

Akibatnya: **klinik tidak bisa menyatakan kerugian stok dalam rupiah.** Selisih
KUANTITAS tercatat (`total_selisih_qty` masuk audit log), tapi nilainya tidak. Dan
`reports_service` **tidak menyebut opname sama sekali** — tidak ada laporan susut stok.

### Yang meringankan, dan ini penting

Berbeda dari F3, di sini datanya **masih bisa dihitung ulang kemudian**:
`stock_opname_item` menyimpan `selisih` **dan** `id_lot`, dan `stok_lot` menyimpan
`harga_terima`. Jadi nilai rupiah setiap opname lampau bisa direkonstruksi.

**Ini celah kemampuan, bukan kehilangan data** — dan karena itu tidak mendesak seperti
F3 dulu. Yang perlu diputuskan: apakah nilainya dihitung saat approve (ke depan), atau
cukup dihitung di laporan saat dibutuhkan.

---

## Yang DIPERIKSA di putaran 7 dan ternyata BERSIH

| Area | Hasil |
|---|---|
| **Laporan komisi** | **BERSIH.** `komisi_report_service` menyaring `status == 'AKTIF'`, agregasi Decimal (A9), dan docstring-nya menyatakan keduanya: *"Hanya status AKTIF (VOID dikecualikan). Agregasi pakai Decimal (A9), convert float di boundary."* |
| **Perbaikan putaran 3 sampai ke laporan** | **YA.** Tiga transaksi yang di-void SESUDAH perbaikan komisinya VOID dan tidak muncul di laporan; hanya baris pra-perbaikan yang tersisa |
| **Penerapan selisih stok opname** | Qty variance dihitung per item dengan snapshot `qty_sistem`, dicatat ke `inventory_history`, dan `total_selisih_qty` masuk audit log |

---

---

# PUTARAN 8 — nilai pergerakan stok & membership upgrade

---

## TEMUAN 13 — 🔴 Kolom nilai di `inventory_history` tak pernah diisi, TAPI diekspor ke Finance

Lebih berat dari Temuan 12, karena ada **tiga lapis** dan lapis ketiganya membuat klaim
positif:

| Lapis | Keadaan |
|---|---|
| **Penulis** | `InventoryRepository.add_history()` **tidak punya parameter** untuk `hpp_satuan` maupun `nilai_mutasi`; konstruktor `InventoryHistory(...)` di dalamnya tidak menyebut keduanya |
| **Ekspor** | `export_service.py:712–713` **mengekspor kedua kolom itu** ke paket Finance |
| **Kamus data** | Menjelaskannya seolah berisi: *"Snapshot cost per unit saat mutasi (produk HPP / bahan harga_modal). M-FIN-3."* dan *"Nilai mutasi = qty_perubahan × hpp_satuan (Rp). **Menilai PENYESUAIAN/WRITE_OFF/RETUR**."* |

Jadi Finance menerima dua kolom yang **selalu NULL**, dengan kamus yang memberi tahu
bahwa kolom itulah penilai write-off dan penyesuaian. Analis yang membangun laporan susut
stok dari sana akan mendapat kosong — dan kamusnya tidak memberi alasan untuk curiga.

**Dibuktikan**, bukan disimpulkan dari pembacaan kode:

```
add_history(jenis=PENYESUAIAN, qty_perubahan=-3, stok_akhir=97, ...)
baris ditulis : ('PENYESUAIAN', -3.0, 97.0, None, None)
hpp_satuan    : None
nilai_mutasi  : None
```

Penanda **M-FIN-3** di kamus menandakan ini milestone Finance yang direncanakan lalu
tidak pernah diselesaikan.

⚠ Berbeda dari Temuan 12, di sini nilainya **TIDAK selalu bisa direkonstruksi**:
`inventory_history` tidak menyimpan `id_lot`, jadi harga perolehan pada saat mutasi tidak
bisa dipastikan untuk mutasi lampau. Untuk produk masih bisa didekati dari
`master_produk.hpp_per_unit` **sekarang**, tapi itu harga hari ini, bukan harga saat
mutasi — persis masalah snapshot yang sama dengan nama tindakan di Tahap B.

**Ini kehilangan data, bukan sekadar celah kemampuan.**

---

## TEMUAN 14 — 🟡 UPGRADE membership menghanguskan sisa hari, dan UI-nya diam

Aturannya **disengaja dan terdokumentasi di kode**:

```python
# UPGRADE/ACTIVATION tetap reset (start fresh)
if action_upper == "RENEWAL" and active_now is not None:
    base_date = max(active_now.tgl_expired, today)   # carry-over
else:
    tgl_expired_baru = today + timedelta(days=durasi_days)
    tgl_aktif_baru = today                            # RESET
harga_bayar = float(tier.harga_aktivasi or 0)         # HARGA PENUH
```

Jadi pasien yang upgrade membayar **harga penuh tier baru** dan **kehilangan seluruh
sisa hari** tier lama. Itu keputusan bisnis dr. Hansen, bukan cacat.

**Yang menjadi temuan adalah pengungkapannya.** Di halaman yang sama, berdampingan:

| Kotak | Teks |
|---|---|
| RENEWAL | *"Extend tier yang sama. **Carry-over** — sisa hari tidak hilang."* |
| UPGRADE | *"⬆ Upgrade Tier"* + dropdown tier + harga. **Tidak ada keterangan apa pun** |

UI menjelaskan kasus yang menguntungkan dan **diam pada yang merugikan**, bersebelahan.
CS yang membaca keduanya mendapat gambaran yang timpang.

Besarnya nyata: pasien VIP dengan sisa 300 hari dari 360 yang upgrade ke VVIP
menghanguskan ±83% nilai membership berjalannya — pada harga tier Rp 5.000.000 itu
sekitar Rp 4,2 juta — tanpa satu kalimat pun di layar.

**Saran:** satu baris di kotak UPGRADE, menampilkan sisa hari yang akan hangus (datanya
sudah ada — halaman itu sudah menampilkan "Sisa hari:" di bagian atas). Bukan mengubah
aturannya; hanya mengatakannya.

---

## Yang DIPERIKSA di putaran 8 dan ternyata BERSIH

| Area | Hasil |
|---|---|
| **Carry-over RENEWAL** | **BERSIH.** `base_date = max(active_now.tgl_expired, today)` dan `tgl_aktif` dipertahankan — tidak ada hari hilang. Alasannya tercatat (#362F, #362B-A), dan catatannya ikut ditulis ke `history.catatan` |
| **Stok dipotong saat SERAH, bukan saat bayar** | Terverifikasi: void sesudah bayar (tanpa serah) tidak mengembalikan stok, karena memang belum pernah dipotong. `_reverse_stok_per_item` menjaganya lewat `_produk_stok_sudah_dipotong()` |
| **Pencatatan pergerakan stok** | `inventory_history` mencatat jenis, qty, stok akhir, referensi, pelaku, dan waktu. Yang hilang hanya dimensi **nilai** (Temuan 13) |

---

---

# PUTARAN 9 — kuota membership (tindakan gratis)

Kuota = tindakan yang diberikan **gratis**. Setiap slot yang bocor adalah pendapatan
yang hilang tanpa jejak.

---

## TEMUAN 17 — ✅ SELESAI (putaran 10) — enam test merah, kini **96 lulus / 0 gagal**

> **Hasil triase:** lima dari enam adalah **fixture usang**, bukan kode rusak. Yang
> keenam adalah **artefak skema laptop saya sendiri** — bukan cacat produksi.
>
> ```
> sebelum : 6 failed, 48 passed
> sesudah : 96 passed, 32 skipped, 0 failed
> ```

### ⚠ KOREKSI atas klaim saya di putaran 9

Saya menulis bahwa kegagalan ini **"bukan pula kondisi data laptop"**, dengan alasan
test menyiapkan datanya sendiri. Itu **salah untuk satu test**: saya memeriksa *data*
dan lupa memeriksa **skema**.

DB laptop dibangun lewat `Base.metadata.create_all()` dari **model**, bukan dari
migrasi. `test_repro_P0_2_double_payment` menguji bahwa kunci idempotensi ganda ditolak
`UNIQUE` — dan indeks itu **hanya dibuat oleh migrasi**
(`20260710_2100_transaksi_idempotency_key.py`). Model-nya bahkan berkomentar
*"UNIQUE via index uq_transaksi_kasir_idempotency_key"* tapi mendeklarasikan kolomnya
**tanpa** `unique=True`.

Dibuktikan: setelah indeks itu dipasang manual, test **langsung lulus**.

### Lima lainnya: fixture dari dunia PRA-#54

Semua lima gejalanya sama — pengembalian stok/lot menghasilkan nol. Sebabnya satu:

Fixture-nya menyetel `kunjungan.status_antrian = "COMPLETED"` dan mengandalkan tebakan
lama *"COMPLETED = obat sudah diserah"*. **Task #54 (2026-09-22) mencabut tebakan itu**,
dan `_produk_stok_sudah_dipotong` menjelaskan kenapa di docstring-nya sendiri: sejak
serah-per-item, kunjungan bisa COMPLETED sementara itemnya belum diserahkan sama
sekali — *"memakainya akan mengembalikan stok yang tidak pernah keluar"*.

Penilaiannya kini lewat `_mode_per_item`, yang menuntut **jejak nyata**: resep atau
racikan berstatus `DISERAHKAN`.

**Dibuktikan dengan menjalankan skenario yang sama dua kali:**

```
A. tanpa resep DISERAHKAN (seperti fixture lama):
   dikembalikan=0  lot.qty_sisa=0.0     <- test mengharapkan 3
B. dengan resep DISERAHKAN qty=3 (pasca-#54):
   dikembalikan=1  lot.qty_sisa=3.0  lot.status=AKTIF
```

Jadi **kodenya benar**; jawaban 0 pada kasus A justru yang betul, karena memang tidak
ada yang pernah diserahkan. Fixture-nya yang tidak pernah ikut diperbarui saat #54.

**Perbaikannya:** tambahkan bukti penyerahan ke fixture, dengan komentar yang
menjelaskan kenapa — supaya tidak dikembalikan ke bentuk lama.

⚠ **Suite menangkap kesalahan saya sendiri.** Versi pertama menambahkan bukti ke
`_setup` P0-1 tanpa syarat, sehingga test pasangannya — *"obat BELUM diserah tidak
menambah stok"* — ikut lulus padahal tidak lagi menguji apa pun. Buktinya dibuat
**bersyarat** pada `status_kunjungan`, memetakan tebakan lama ke bukti baru tanpa
mengubah maksud kedua test. Itu persis tugas penjaga, dan ia bekerja.

### Opsi A ternyata TIDAK berpengaruh

Kekhawatiran saya di putaran 9 — bahwa Opsi A mengubah premis `P0_1` — **tidak
terbukti**. Keempat berkas memanggil `_reverse_stok_per_item` **langsung**, bukan lewat
`void_transaksi`. Jadi pagar Opsi A tidak pernah terlewati, dan tidak ada test yang
perlu diputuskan ulang.

---

## TEMUAN 18 — 🔴 Skema laptop KEHILANGAN 26 indeks yang dibuat migrasi

Terungkap saat menelusuri Temuan 17, dan dampaknya melampaui test.

`Base.metadata.create_all()` membuat **tabel dan kolom** dari model, tapi tidak
membuat apa pun yang hanya ada di migrasi. Perbandingan indeks:

```
indeks yang dibuat migrasi : 29
hilang di DB laptop        : 26
```

Mayoritas indeks performa (`ix_lot_*`, `ix_komisi_*`) — tidak mengubah perilaku. Tapi
**dua di antaranya UNIQUE**, dan UNIQUE adalah aturan bisnis:

| Indeks | Menjaga |
|---|---|
| `ux_pasien_no_member` | nomor member tidak ganda |
| `ux_dismiss_pasangan` | pasangan duplikat pasien tidak di-dismiss dua kali |

Ditambah `uq_transaksi_kasir_idempotency_key` (pembayaran ganda) yang memicu Temuan 17.

**Artinya laptop MENERIMA data yang produksi TOLAK.** Setiap smoke test di sini
berjalan di atas aturan yang lebih longgar daripada klinik.

⚠ Satu yang terlihat hilang ternyata **tidak**: `ux_pasien_nomor_ktp` tidak ada
**namanya**, tapi `nomor_ktp` sudah unik lewat `unique=True` di model. Beda nama, bukan
beda perilaku — diperiksa, bukan diasumsikan.

**Ditangani:** ketiga indeks unik dipasang manual di DB laptop; suite kembali 96 lulus.
Sisanya indeks performa, dibiarkan.

**Ini mengoreksi `ALUR_DUA_MESIN.md` §7**, yang menyebut `create_all` "cukup untuk DB
smoke-test laptop". Itu meremehkan: ia cukup untuk **bentuk** data, tidak untuk
**aturannya**.

---

## TEMUAN 17 (uraian awal, sebelum triase)

Ditemukan saat menjalankan suite penuh untuk memverifikasi perbaikan Temuan 15.
Sebelumnya saya hanya menjalankan satu berkas test dan melihat satu kegagalan.

```
FAILED test_kasir_void_exclusion.py::test_void_reverse_stok
FAILED test_repro_H2_lot_provenance.py::test_void_reverse_ke_lot_asli_bukan_void_return
FAILED test_repro_P0_1_void_stock_inflation.py::test_void_reverse_pada_obat_sudah_diserah_mengembalikan_stok
FAILED test_repro_P0_2_double_payment.py::test_idempotency_key_sama_ditolak_split_dgn_key_beda_boleh
FAILED test_void_return_lot.py::test_void_return_ke_lot_pilihan
FAILED test_void_return_lot.py::test_void_fallback_lot_retur_baru
6 failed, 48 passed, 32 skipped
```

**Bukan akibat perubahan saya.** Dibuktikan dua kali: dengan `git stash` (tanpa
perubahan kuota) dan dengan `kasir_service.py` versi **`main`** (tanpa Opsi A maupun
tiga rollback) — **enam kegagalan yang sama persis, nama yang sama.**

**Bukan pula kondisi data laptop.** Test menyiapkan datanya sendiri, dan assertion-nya
tentang perilaku:

```
assert float(produk.stok_terkini) == stok_awal
AssertionError: Untuk obat yang sudah diserah, reverse mengembalikan stok ke semula
assert 7.0 == 10
```

Stok seharusnya kembali ke 10, hasilnya tetap 7 — pengembaliannya tidak terjadi.

### Kenapa ini berat

Tiga dari enam adalah **`test_repro_*`** — test yang ditulis khusus untuk mereproduksi
bug yang pernah terjadi, supaya tidak kembali:

| Test | Menjaga apa |
|---|---|
| `P0_1_void_stock_inflation` | stok menggelembung saat void |
| `P0_2_double_payment` | pembayaran ganda (idempotency key) |
| `H2_lot_provenance` | stok kembali ke lot ASAL, bukan lot VOID-RETURN — jejak QC |

**Penjaga yang merah tidak menjaga apa pun.** Dan ketiganya menjaga persis wilayah yang
diaudit dokumen ini: uang, stok, dan jejak lot.

### ⚠ Interaksi dengan Opsi A yang perlu diputuskan

`P0_1` menguji skenario "void obat yang SUDAH DISERAH mengembalikan stok". **Opsi A
sekarang MENOLAK void itu sejak awal.** Jadi setelah Opsi A, skenario yang di-test itu
tidak lagi bisa terjadi lewat jalur normal.

Artinya test tersebut perlu **diputuskan**, bukan sekadar diperbaiki: apakah ia masih
relevan, atau harus ditulis ulang untuk menguji bahwa void-nya **ditolak**? Itu
keputusan dr. Hansen, bukan keputusan teknis.

⚠ **Saya tidak menyelidiki akar masing-masing kegagalan.** Enam test di empat berkas,
dan tiga di antaranya menyentuh jalur lot/stok yang belum saya audit. Itu pekerjaan
tersendiri — dicatat jujur sebagai belum dikerjakan, bukan dilewatkan.

**Ini membalik urutan prioritas:** memperbaiki temuan baru sementara penjaga yang ada
sedang merah adalah membangun di atas lantai yang belum diperiksa.

---

## TEMUAN 15 — ✅ DIPERBAIKI — dulu: `increment_kuota_terpakai` mengaku "Atomic" tapi tidak mengunci

**Didemonstrasikan**, bukan disimpulkan dari pembacaan kode.

Docstring-nya berbunyi *"Atomic increment kuota_terpakai. Return True kalau sukses
(sisa > 0)."* Kenyataannya:

```python
kuota = self.db.get(_PMK, id_kuota)        # ambil biasa, TANPA with_for_update()
sisa = kuota.kuota_total - kuota.kuota_terpakai
if sisa <= 0: return False
kuota.kuota_terpakai = terpakai_lama + 1   # baca-ubah-tulis di Python
```

Dua sesi terpisah, kuota `total=1 terpakai=0`:

```
sesi A baca terpakai = 0 | sesi B baca terpakai = 0
sesi A increment -> True
sesi B increment -> True
akhir di DB     : terpakai=1 dari total=1
```

**Dua tindakan gratis diizinkan dari kuota yang hanya satu**, dan DB hanya mencatat
satu terpakai. Satu tindakan diberikan cuma-cuma **tanpa jejak sama sekali** — tidak di
kuota, tidak di laporan.

### Kenapa ini bukan sekadar teori

1. **Tidak ada CHECK constraint** `kuota_terpakai <= kuota_total` di DB — tidak ada
   jaring pengaman di lapis bawah.
2. **Proyek SUDAH punya polanya dan memakainya** — `apotek_repo.get_produk_for_update()`
   dan `inventory_repo.get_stok_for_update()` keduanya `with_for_update()`, dan
   `proses_bayar` mengunci baris kunjungan dengan alasan tertulis (P0-2) untuk
   menyerialkan submit bersamaan.
3. Jadi **stok dilindungi kunci baris, kuota tidak** — padahal keduanya sumber daya
   habis-pakai bernilai uang.

### ✅ Perbaikan 2026-10-04 — dan kembarannya ikut diperbaiki

`increment_kuota_terpakai` **dan** `decrement_kuota_terpakai` kini mengambil barisnya
dengan `select(...).with_for_update()`, pola yang sama persis dengan
`apotek_repo.get_produk_for_update()`.

**Kenapa decrement ikut, padahal tidak masuk Temuan 15:** ia punya baca-ubah-tulis yang
identik. `max(0, ...)` hanya mencegah nilai NEGATIF — bukan kehilangan pembaruan. Dua
void bersamaan sama-sama membaca `terpakai=2` dan sama-sama menulis `1`, padahal
seharusnya `0`: **pasien kehilangan satu slot yang sudah ia bayar.** Cermin Temuan 15,
merugikan sisi sebaliknya. Memperbaiki satu saja akan meninggalkan kembarannya — pola
yang paling sering ditemukan audit ini.

**Diuji dua arah, dengan thread sungguhan yang menahan transaksi 0,4 detik:**

| Uji | Sebelum | Sesudah |
|---|---|---|
| Dua increment bersamaan, kuota=1 | A=True **B=True** → 2 tindakan gratis | A=True **B=False** → 1 |
| Pemakaian berurutan, kuota=3 | — | ke-1,2,3 True · ke-4 **False** |
| Dua decrement bersamaan, terpakai=3 | — | **terpakai=1** (3−2), tidak ada yang hilang |

⚠ **Catatan metode:** uji decrement sempat melaporkan `terpakai=3` — seolah tidak ada
decrement yang tercatat. Itu **artefak uji saya**: sesi pembaca memegang snapshot
transaksi lama (InnoDB REPEATABLE READ). Dibaca dengan sesi baru, hasilnya benar.
Kalau saya laporkan apa adanya, itu akan jadi temuan palsu.

Regresi: suite integrasi **6 gagal / 48 lulus — identik dengan baseline** (lihat
Temuan 17; keenamnya pra-ada di `main`). 37 halaman tetap 200.

### Pemicunya nyata di klinik

Dua staf menandai tindakan "Selesai" untuk pasien yang sama pada saat berdekatan.
Jarang, tapi bukan hipotetis — dan `_revert_kuota_per_tindakan` saat void menambah
peluang baca-ubah-tulis bersamaan.

**Perbaikannya ada di rak sendiri:** ganti `self.db.get(...)` dengan query
`with_for_update()`, persis seperti dua repo yang sudah melakukannya.

⚠ Catatan: `decrement_kuota_terpakai` **aman di sisi bawah** — ia memakai
`max(0, terpakai_lama - 1)`, jadi tidak bisa negatif.

---

## TEMUAN 16 — 🟡 Tidak ada indeks unik di tabel kuota; baris bulan bisa kembar

`get_or_create_kuota_for_treatment` melakukan **lazy-create**: *"Untuk BULANAN:
lazy-create row untuk bulan target (default = today)."*

Indeks di `pasien_membership_kuota`:

```
PRIMARY                 unik    (id_kuota)
id_pasien               biasa
id_treatment            biasa
id_membership_history   biasa
```

**Tidak ada indeks unik** pada kombinasi `(id_pasien, id_treatment, bulan_periode)`.
Jadi dua panggilan bersamaan dapat sama-sama tidak menemukan baris bulan itu dan
sama-sama menyisipkan → **dua baris kuota untuk bulan yang sama**.

Dampaknya lebih besar dari Temuan 15: yang digandakan bukan satu slot melainkan
**seluruh jatah bulanan**. Dan duplikatnya senyap — tidak ada yang menandainya.

⚠ **Ini belum saya demonstrasikan** — kesimpulan dari struktur (lazy-create tanpa
indeks unik), bukan dari menjalankannya. Saya membedakannya dari Temuan 15 yang
memang dijalankan.

**Perbaikannya butuh migrasi** (`UNIQUE INDEX`), jadi harus dikerjakan di desktop —
dan perlu dibersihkan dulu kalau sudah ada duplikat:

```sql
SELECT id_pasien, id_treatment, bulan_periode, COUNT(*) n
FROM pasien_membership_kuota
WHERE periode_kuota = 'BULANAN'
GROUP BY id_pasien, id_treatment, bulan_periode
HAVING n > 1;
```

---

## Yang DIPERIKSA di putaran 9 dan ternyata BERSIH

| Area | Hasil |
|---|---|
| **Pagar atas kuota** | `sisa <= 0 → return False`. Dalam pemakaian berurutan, kuota tidak bisa dilampaui |
| **Pagar bawah decrement** | `max(0, terpakai_lama - 1)` — tidak bisa negatif |
| **Reset bulanan** | Baris BARU per bulan (lazy-create), bukan reset di tempat. Sisa tidak terakumulasi — cocok dengan keterangan di layar: *"kuota reset setiap awal bulan, sisa tidak akumulasi"* |
| **Audit kuota** | `increment`/`decrement` menulis audit `KUOTA_PAKAI` dengan nilai lama→baru saat `actor_id_staf` disediakan |

---

---

# PUTARAN 11 — hak prabayar & jalur persetujuan

---

## TEMUAN 19 — ✅ DIPERBAIKI — dulu: `use_session` bocor, 2 tindakan Rp 0 dari 1 hak

> **Keputusan dr. Hansen 2026-10-04: perbaiki.** `use_session` kini mengambil barisnya
> dengan `select(...).with_for_update()`, pola yang sama dengan perbaikan kuota.
>
> **Diuji dua arah**, thread sungguhan yang menahan transaksi 0,4 detik:
>
> | Uji | Sebelum | Sesudah |
> |---|---|---|
> | Dua permintaan bersamaan | A=OK **B=OK** → **2** tindakan | A=OK **B=TOLAK** → **1** |
> | Berurutan, lalu diulang | — | ke-1 OK · ke-2 **TOLAK** · 1 tindakan · status SCHEDULED |
>
> Suite 96 lulus / 0 gagal · 37 halaman 200.
>
> **Kembarannya diperiksa, dan tidak perlu diperbaiki.** Satu-satunya tempat lain yang
> mengubah `rencana.status` adalah `_cancel_series_sesi_pending` (→ CANCELLED saat
> void). Itu **idempoten**: dua void bersamaan menghasilkan status akhir yang sama.
> Diperiksa, bukan diasumsikan — karena "satu diperbaiki, saudaranya terlupa" adalah
> pola yang paling sering ditemukan audit ini.

**Uraian di bawah adalah keadaan SEBELUM perbaikan.**

### Dulu: `use_session` bocor

Bentuknya **identik** dengan Temuan 15, di modul lain. `series_service.use_session`:

```python
rencana = self.db.get(PasienRencanaTreatment, id_rencana)   # tanpa kunci
if status_v != "PENDING": raise HTTPException(...)          # cek
...
self.db.add(tindakan)                                       # buat tindakan Rp 0
rencana.status = StatusRencanaTreatmentEnum.SCHEDULED       # ubah
```

Docstring-nya sendiri menyatakan konsekuensi uangnya: *"Kasir akan charge **Rp 0** untuk
sesi ini (karena id_rencana set + urutan_sesi > 1)."*

**Didemonstrasikan** dengan dua thread, satu rencana berstatus PENDING:

```
A -> OK
B -> OK
kunjungan_tindakan dibuat dari rencana ini: 2   (harus 1)
status rencana: SCHEDULED
```

**Dua tindakan gratis dari satu hak sesi.** Hak yang sudah dibayar sekali ditebus dua
kali, dan rencananya tetap tercatat terpakai sekali.

Perbaikannya sama persis dengan Temuan 15: `select(...).with_for_update()`.

---

## TEMUAN 20 — ✅ DIPERBAIKI — dulu: pagar approve jebol di bawah konkurensi

> **Keputusan dr. Hansen: perbaiki.** Baris header dikunci sebelum statusnya diperiksa,
> di **tiga** titik:
>
> | Titik | Cara |
> |---|---|
> | `opname.approve` | `repo.get_by_id_for_update()` (baru) |
> | `opname.reject` | `repo.get_by_id_for_update()` — **kembarannya**, lihat di bawah |
> | `retur.approve_retur` | `select(...).with_for_update()` |
>
> **Kenapa `reject` ikut dikunci**, padahal Temuan 20 hanya menyebut approve: ia juga
> bertransisi KELUAR dari DRAFT. Kalau approve dan reject berlomba, keduanya lolos
> pagar — stoknya diterapkan oleh approve sementara statusnya berakhir REJECTED.
> Pola "satu diperbaiki, saudaranya terlupa" sudah **tiga kali** menggigit audit ini
> (`force_past_day_void`, `decrement_kuota_terpakai`, dan sekarang ini); kali ini
> diperiksa lebih dulu.
>
> **Diuji dua arah, dan kali ini LOT DAN CACHE diperiksa sekaligus** — karena pada
> demonstrasi saya sempat menyimpulkan "aman" hanya dari cache:
>
> | Uji | Sebelum | Sesudah |
> |---|---|---|
> | Dua approve opname bersamaan | **2 lot** (qty 10) · cache 5 · **berselisih** · audit 2 | **1 lot** · qty 5 · cache 5 · **cocok** · audit 1 |
> | Dua approve retur bersamaan | lot 7 · **audit 2** (disetujui 2×) | lot 7 · **audit 1** |
> | Berurutan: approve lalu ulangi | — | ke-1 OK · ke-2 **TOLAK** (opname & retur) |
> | Reject lalu ulangi | — | ke-1 OK → REJECTED · ke-2 **TOLAK** |
>
> Suite 96 lulus / 0 gagal · 37 halaman 200.
>
> ⚠ **Dua kali skrip uji saya sendiri yang salah**, bukan kodenya — tanda tangan
> `reject()` dan nama field `StockOpnameRejectRequest.alasan`. Keduanya sempat
> menghasilkan "PERIKSA" yang kalau diterima mentah akan jadi temuan palsu.

**Uraian di bawah adalah keadaan SEBELUM perbaikan.**

### Dulu: didemonstrasikan, dan hasilnya BUKAN yang saya duga

> **Prediksi saya di putaran 11 SALAH untuk keduanya, dan untuk `opname` saya sempat
> salah DUA KALI.** Rinciannya di bawah; saya menuliskannya karena cara temuan ini
> meleset lebih berguna daripada temuan itu sendiri.

### Hasil demonstrasi

| Jalur | Prediksi putaran 11 | Kenyataan |
|---|---|---|
| `retur.approve_retur` | lot terpotong dua kali | **Pagar jebol, tapi stok NET BENAR** — kehilangan pembaruan, bukan pemotongan ganda |
| `opname.approve` | selisih diterapkan dua kali | **Selisih MEMANG diterapkan dua kali** — tapi lewat mekanisme lain, dan akibatnya lebih halus |

### `approve_retur` — pagar jebol, aritmetikanya menutupi

```
A membaca: retur=DRAFT lot=10.0
B membaca: retur=DRAFT lot=10.0
A -> OK
B -> OK

lot akhir     : 7.0        (benar untuk SATU approve; dua kali potong = 4)
audit APPROVE : 2          <- retur disetujui DUA KALI
```

Pagarnya **benar-benar jebol**: keduanya membaca `DRAFT`, keduanya lolos, dua entri
audit tertulis, dan `id_staf_approver` tertimpa. Tapi stoknya **net benar**, karena
keduanya menghitung `10 − 3 = 7` dari snapshot yang sama lalu menulis angka yang sama.
Itu **kehilangan pembaruan**, bukan pemotongan ganda.

⚠ **Benarnya KEBETULAN.** Ia bergantung pada aritmetika absolut (`lot.qty_sisa = sisa -
qty`). Siapa pun yang kelak mengubahnya jadi relatif (`-=`) akan memperkenalkan
pemotongan ganda **tanpa menyentuh pagarnya**, dan tidak ada yang akan menyadari —
karena pagarnya terlihat ada.

### `opname.approve` — dua lot, dan buku berselisih dengan cache

Percobaan pertama saya menyimpulkan **"aman"** karena `stok_terkini` berakhir di 5 (benar).
Itu **salah**: saya hanya melihat cache, dan filter nama batch saya meleset. Dengan
melihat lot-nya langsung:

```
lot 210  qty_masuk=5  qty_sisa=5  AKTIF
lot 211  qty_masuk=5  qty_sisa=5  AKTIF    -> total lot = 10
stok_terkini : 5.0                          -> cache    = 5
audit opname : 2
```

**Selisih diterapkan dua kali: dua lot dibuat.** Tapi `stok_terkini` tetap 5, karena
tiap thread menghitung ulang `SUM(qty_sisa)` dari snapshot-nya sendiri dan sama-sama
menulis 5 — kehilangan pembaruan di cache.

Hasilnya **buku lot dan cache stok berselisih**: lot bilang 10, cache bilang 5.

Itu lebih berbahaya daripada penggandaan yang terlihat. FEFO membaca **lot**; laporan
dan tagihan membaca **cache**. Selisihnya tidak memicu error apa pun dan baru muncul
sebagai keanehan stok berminggu-minggu kemudian — persis kelas masalah yang
`test_repro_P0_1_void_stock_inflation` ditulis untuk menjaga.

⚠ Catatan: `opname.approve` **memang** memanggil `get_produk_for_update()` — jadi
baris produknya dikunci. Yang tidak dikunci adalah **baris opname-nya**, dan kunci
produk tidak menghalangi pembuatan lot kedua.

### Kesimpulan yang bisa dipertanggungjawabkan

Pagar `status != DRAFT` **tidak berlaku di bawah konkurensi** pada kedua jalur — itu
terbukti, dua kali, dengan dua entri audit sebagai bukti. Yang berbeda hanya seberapa
terlihat akibatnya:

- `retur` : tertutupi oleh aritmetika absolut — **risiko laten**
- `opname`: **nyata sekarang** — lot ganda, cache berselisih

Perbaikannya sama untuk keduanya: kunci baris header (`select(...).with_for_update()`)
sebelum memeriksa statusnya, persis seperti kuota (Temuan 15) dan sesi series
(Temuan 19).

**Tidak saya kerjakan** — ini mengubah stok, dan dua kali dalam satu putaran saya salah
menebak perilakunya. Keputusan dr. Hansen.

---

## TEMUAN 20 (uraian awal putaran 11, sebelum didemonstrasikan)

Dua jalur "setujui sekali, lalu ubah stok" berbentuk sama:

| Fungsi | Pola | Kalau ganda |
|---|---|---|
| `retur_service.approve_retur` | `db.get` → cek `status != 'DRAFT'` → `lot.qty_sisa = sisa - qty` | **lot terpotong dua kali** |
| `opname_service.approve` | `db.get` → cek `status != DRAFT` → terapkan selisih ke stok | **selisih diterapkan dua kali** |

### Kontras yang menjelaskan kenapa ini terlewat

`proses_bayar` punya **DUA** lapis perlindungan submit-ganda:

```
kasir_service.py:605  self.kunjungan_repo.get_by_id_for_update(...)   <- kunci baris
kasir_service.py:662  idempotency_key=payload.idempotency_key         <- P0-2 backstop
```

**Pembayaran dilindungi dua kali; persetujuan tidak dilindungi sama sekali.** Padahal
keduanya sama-sama aksi sekali-klik yang mengubah angka, dan keduanya bisa ter-submit
ganda oleh klik ganda atau retry jaringan.

⚠ **BELUM saya demonstrasikan** — kesimpulan dari struktur, sama seperti Temuan 16.
Saya membedakannya dari Temuan 19 yang memang dijalankan.

---

## Pola yang mulai terlihat setelah tiga temuan sejenis

| Sumber daya | Dilindungi kunci baris? |
|---|---|
| Stok produk (`apotek_repo`, `inventory_repo`) | ✅ `with_for_update()` |
| Pembayaran (`proses_bayar`) | ✅ kunci baris **+** kunci idempotensi |
| **Kuota membership** | ❌ → diperbaiki putaran 10 |
| **Sesi series** | ❌ Temuan 19 |
| **Persetujuan retur / opname** | ❌ Temuan 20 |

Proyek ini mengunci **barang** dan **uang**, tapi tidak mengunci **hak** dan
**persetujuan**. Ketiganya sama-sama bernilai uang; hanya dua yang pertama yang terasa
seperti uang saat kodenya ditulis.

---

## Catatan metode

Pemindai berpola "db.get → cek → ubah status" menemukan **28 fungsi**. Mayoritas positif
palsu — beberapa hanya membaca, beberapa tidak menyentuh hak atau stok. **Angka 28 itu
tidak saya laporkan sebagai temuan**; hanya tiga yang dibuka satu per satu dan
dipertanggungjawabkan. Itu pelajaran yang sudah dua kali dicatat dokumen ini dan ketiga
kalinya ditegakkan.

---

---

# PUTARAN 12 — ekonomi tindakan gratis (kuota membership)

---

## ✅ DEC-088 Opsi A TERVERIFIKASI — dan angkanya baru sekarang terlihat

DEC-088 menetapkan: *komisi tindakan gratis (series/kuota) **tetap dibayar***. Diuji
dengan tindakan berkuota sungguhan sampai ke kasir:

| | |
|---|---|
| Ditagih ke pasien | **Rp 0** (kuota) |
| Komisi dokter | **Rp 180.000** `AKTIF` |
| BHP terpakai | Rp 100.000 |
| Harga master tindakan | Rp 500.000 |

Keputusannya terpenuhi. Komisi dihitung dari **harga master**
(`hitung_komisi_treatment`, komentar: *"basis harga master"*), bukan dari yang ditagih,
jadi tindakan Rp 0 tetap menghasilkan komisi penuh.

**Yang baru terlihat: klinik mengeluarkan Rp 280.000 untuk satu tindakan kuota**
(BHP 100.000 + komisi 180.000), dengan pendapatan Rp 0.

Angka itu **tidak bisa dilihat sebelum perbaikan F3** — transaksi berkuota tidak
meninggalkan baris `transaksi_detail_tindakan` sama sekali.

### Konsekuensi F3 yang baru ketahuan sekarang

`export_service.export_transaction_items_raw` punya query **khusus**
`TransaksiDetailTindakan` (`stmt_t`, baris ±590). Karena tabel itu tidak pernah ditulis,
ekspor Finance selama ini mengirim rincian **produk dan racikan** tapi **nol baris
tindakan** — lini terbesar di klinik dermatologi — dan tidak ada apa pun di keluarannya
yang menandakan ketiadaan itu.

Jadi F3 bukan sekadar "mulai menulis tabel": ia **menghidupkan kembali ekspor Finance
yang diam-diam mengirim kosong**.

---

## TEMUAN 21 — 🟡 "Estimasi Omzet" menampilkan harga penuh untuk tindakan yang gratis

Dua laporan menghitung omzet dari `SUM(master_treatment.harga)`, bukan dari yang
benar-benar ditagih:

| Laporan | Fungsi |
|---|---|
| Kinerja Dokter | `reports_service.kinerja_dokter` |
| Top Treatment | `reports_service.top_treatment` |

**Labelnya jujur** — kolomnya bernama **"Estimasi Omzet"** di kedua halaman, dan
docstring `top_treatment` menyebut *"estimasi, sebelum diskon membership"*. Dugaan awal
saya bahwa labelnya menyesatkan **salah**; saya periksa sampai ke template.

**Tapi tidak ada satu kalimat pun** di kedua halaman yang menjelaskan apa yang
dikecualikan. (Hitungan "ada catatan" pada pemeriksaan pertama saya ternyata hanya
menghitung kata "estimasi" termasuk nama variabel — koreksi atas langkah saya sendiri.)

Dan dengan angka putaran ini, selisihnya bukan sekadar "estimasi":

```
Estimasi Omzet menampilkan : Rp 500.000   (harga master)
Klinik benar-benar terima  : Rp 0
Klinik benar-benar keluar  : Rp 280.000   (BHP + komisi)
```

Untuk dokter yang banyak mengerjakan tindakan kuota, angka itu tidak hanya
melebih-lebihkan — **tandanya bisa terbalik**. "Estimasi" tidak menyampaikan itu.

**Saran:** satu kalimat di kedua halaman, misalnya *"Dihitung dari harga master ×
jumlah. Belum dikurangi diskon membership, dan tindakan berkuota dihitung harga penuh
meski ditagih Rp 0."* Tidak mengubah angkanya; hanya mengatakannya.

---

## TEMUAN 22 — 🟡 Tidak ada laporan ekonomi membership

Klinik menjual tier seharga **Rp 5.000.000**, dan tidak ada satu pun laporan yang
menunjukkan berapa biaya kuota yang dipakai pemegangnya. `reports_service` tidak
menyebut kuota atau membership sama sekali kecuali satu komentar.

Pertanyaan yang tidak bisa dijawab sistem hari ini:

- Berapa tindakan kuota yang sudah ditebus tier ini?
- Berapa BHP + komisi yang keluar karenanya?
- Pada tebusan ke berapa sebuah tier berhenti menguntungkan?

**Datanya kini LENGKAP** — `transaksi_detail_tindakan` (BHP + harga, berkat F3),
`komisi_ledger` (komisi per tindakan), `pasien_membership_kuota` (kuota terpakai).
Yang belum ada hanyalah yang menjumlahkannya.

Ini **celah kemampuan, bukan cacat** — tapi ia menyentuh keputusan harga tier, yang
nilainya jauh lebih besar daripada kebanyakan temuan di dokumen ini.

---

---

# PUTARAN 13 — integritas jejak audit

Jejak audit adalah tulang punggung bukti di dokumen ini — beberapa temuan bersandar pada
hitungan `audit_log` ("audit 2 = disetujui dua kali"). Kalau jejaknya rapuh, buktinya
ikut rapuh.

---

## TEMUAN 23 — 🔴 "Audit gagal tidak memblokir bisnis" — DIBUKTIKAN TIDAK BERLAKU

`AuditService.log()` menelan semua exception, dengan alasan yang ditulis di
docstring-nya sendiri:

> *"Tidak commit — caller yang manage transaction. Kalau gagal, log error tapi tidak
> raise (audit failure tidak boleh block business)."*

**Niatnya benar. Hasilnya kebalikannya.**

```
1. produk dibuat (belum commit)
2. audit.log() -> None            (gagal, ditelan sesuai desain)
3. commit bisnis -> GAGAL: PendingRollbackError
   produk tersimpan di DB: 0
```

Sebabnya: `log()` memakai **sesi yang sama** dengan aksi bisnis. Saat `flush()`-nya
gagal, SQLAlchemy menandai sesi itu perlu rollback. Menelan exception lalu lanjut
membuat `commit()` milik caller gagal dengan `PendingRollbackError`.

**Menelannya justru MEMPERSULIT diagnosis, bukan mengamankan.** Tanpa `try/except`,
error aslinya (`Data too long for column 'user_agent'`) akan muncul langsung dan
menunjuk penyebabnya. Dengan `try/except`, yang muncul adalah pesan tentang **sesi** —
yang tidak menyebut audit sama sekali.

Posisi sekarang adalah yang terburuk dari dua pilihan: ia **tidak** melindungi bisnis,
**dan** menyembunyikan sebabnya.

---

## TEMUAN 24 — 🔴 `user_agent` disimpan mentah ke `varchar(255)` — satu header bisa melumpuhkan pengguna

`audit_service.py:58`:

```python
user_agent = request.headers.get("user-agent")    # tanpa pemotongan
```

Kolomnya `varchar(255)`. **Tidak ada pemotongan di mana pun** — `aksi` (varchar 50) dan
`endpoint` (varchar 255) juga tidak.

Diuji dengan User-Agent 314 karakter:

```
User-Agent panjang: 314 karakter (kolom = varchar 255)
  1. produk dibuat (belum commit)
  2. audit.log() -> None
  3. commit -> GAGAL: PendingRollbackError
  produk tersimpan: 0
```

**Akibatnya: pengguna yang browsernya mengirim UA > 255 karakter akan mendapati SETIAP
aksi ber-audit GAGAL** — dan pesan errornya tidak menyebut User-Agent sama sekali.

UA sepanjang itu bukan hal eksotis: perangkat lunak keamanan korporat yang menyuntikkan
token, sebagian browser bawaan OEM Android, dan alat bantu aksesibilitas semuanya
pernah menghasilkannya.

⚠ **Berlaku di produksi, bukan artefak laptop.** `@@sql_mode` memuat
`STRICT_TRANS_TABLES`, dan mini PC memakai image `mysql:8.0` yang sama — jadi MySQL
**menolak**, bukan memotong diam-diam. (Diperiksa karena Temuan 18 mengajarkan untuk
tidak menganggap skema laptop setara produksi.)

### Perbaikan yang disarankan — dua bagian, dan keduanya perlu

1. **Potong setiap masukan ke lebar kolomnya** (`[:255]`, `[:50]`). Menutup kelas
   masalahnya, bukan satu kasusnya.
2. **Putuskan posisi soal kegagalan audit**, karena yang sekarang di tengah dan
   merugikan di kedua sisi:
   - *Audit benar-benar tidak boleh memblokir bisnis* → tulis audit di **sesi
     terpisah**, sehingga kegagalannya tidak pernah menyentuh transaksi bisnis; atau
   - *Audit itu wajib* → **jangan ditelan**, biarkan error aslinya muncul.

   Yang tidak boleh adalah yang berlaku sekarang: ditelan, tapi tetap merusak.

**Tidak saya kerjakan** — pilihan antara (a) dan (b) adalah keputusan tentang apa arti
jejak audit bagi klinik, bukan keputusan teknis. Untuk rekam medis, "boleh ada aksi
tanpa jejak" dan "aksi berhenti kalau jejaknya gagal" adalah dua kebijakan yang sangat
berbeda.

---

## Yang DIPERIKSA di putaran 13 dan ternyata BERSIH

| Area | Hasil |
|---|---|
| **`audit_log` append-only di aplikasi** | **BERSIH.** Tidak ada satu pun kode yang `UPDATE` atau `DELETE` `audit_log`. Pencarian menyeluruh di `app/` |
| **Kegagalan audit terlihat?** | Tercatat ke logger aplikasi pada level `ERROR` dengan `exc_info`. Jadi jejaknya ada — **di log aplikasi**, bukan di layar klinik |

⚠ Catatan: S3 di backlog meminta `GRANT` yang membuat `audit_log` hanya bisa
`INSERT`/`SELECT` di tingkat **database**. Putaran ini hanya memeriksa tingkat
**aplikasi**; GRANT-nya belum dipasang dan masih terbuka.

---

---

# PUTARAN 14 — PPN & penomoran dokumen

---

## TEMUAN 25 — 🟡 Nomor faktur distributor tidak unik — duplikat TERBUKTI diterima

Empat dari lima nomor dokumen dijaga `UNIQUE` di database:

| Dokumen | Kolom | Dijaga? |
|---|---|---|
| Transaksi kasir | `doc_number` | ✅ UNIK |
| Retur | `nomor_retur` | ✅ UNIK |
| Stock opname | `nomor_opname` | ✅ UNIK |
| Pemesanan (PO) | `nomor_po` | ✅ UNIK |
| **Faktur penerimaan** | **`nomor_faktur`** | ❌ **tidak ada indeks sama sekali** |

Tidak ada indeksnya di model maupun di migrasi mana pun, dan **tidak ada pemeriksaan
duplikat di kode**. Dibuktikan:

```sql
INSERT INTO faktur_penerimaan (nomor_faktur, tgl_faktur, id_pemesanan)
VALUES ('INV-DUP-001', CURDATE(), @po), ('INV-DUP-001', CURDATE(), @po);

faktur_nomor_SAMA_po_SAMA: 2
```

Satu faktur distributor yang sama bisa dicatat **dua kali**. Akibatnya barang tercatat
diterima dua kali, dan begitu modul Finance (AP/hutang faktur) dibangun, klinik bisa
**membayar faktur yang sama dua kali**.

### ⚠ Jangan dipasang UNIQUE global

`nomor_faktur` datang dari **distributor**, bukan dibuat Sehati. Dua distributor berbeda
bisa sah-sah saja memakai nomor yang sama. Indeks yang benar adalah
**`UNIQUE (id_distributor, nomor_faktur)`**, bukan `UNIQUE (nomor_faktur)`.

Itu mungkin alasan kenapa indeksnya tidak pernah dipasang — yang mudah justru yang
salah. Tapi akibatnya tetap: tidak ada penjagaan sama sekali.

**Butuh migrasi**, jadi harus dikerjakan di desktop. Bersihkan duplikat lebih dulu:

```sql
SELECT id_distributor, nomor_faktur, COUNT(*) n
FROM faktur_penerimaan
WHERE nomor_faktur IS NOT NULL AND nomor_faktur <> ''
GROUP BY id_distributor, nomor_faktur HAVING n > 1;
```

---

## TEMUAN 26 — 🟡 "Aktif saat PKP" menyiratkan tombol yang belum ada

`transaksi_kasir` punya kolom `ppn` dan `is_kena_ppn`, dan kamus data menjelaskannya
**dengan jujur**:

> *"PPN keluaran (Rp). **0 untuk non-PKP (KLN). Aktif saat PKP.**"*

Isinya memang 0 untuk seluruh 19 transaksi, dan itu **benar** — klinik belum PKP.

**Kontras dengan Temuan 13** layak dicatat: di sana kamus mengklaim `nilai_mutasi`
*"menilai PENYESUAIAN/WRITE_OFF/RETUR"* padahal kolomnya selalu NULL. Di sini kamusnya
menyatakan keadaan sebenarnya. Jadi Temuan 13 adalah **kelalaian**, bukan kebiasaan.

**Yang perlu diluruskan:** frasa *"Aktif saat PKP"* menyiratkan sakelar. Tidak ada:

- **tidak ada setelan PKP** di `config.py` maupun `master_klinik_config`
- **tidak ada kode** di `kasir_service.py` yang menghitung PPN

Jadi menjadi PKP menuntut **pengembangan** — setelan, perhitungan di `proses_bayar`, dan
penulisan kedua kolom itu — bukan sekadar mengubah konfigurasi. Siapa pun yang membaca
kamus dan merencanakan transisi PKP akan salah memperkirakan usahanya.

---

## Yang DIPERIKSA di putaran 14 dan ternyata BERSIH

| Area | Hasil |
|---|---|
| **PPN tidak ditagihkan ke pasien** | **BERSIH dan konsisten.** `RingkasanBiaya` tidak punya field pajak, dan `hitung_komisi_treatment` memperlakukan pajak sebagai **beban klinik** (`laba_bersih = laba_kotor − pajak`). Artinya harga bersifat SUDAH TERMASUK pajak — model yang koheren, bukan pajak yang terlupa |
| **Empat nomor dokumen lain** | Semua ber-`UNIQUE` di database |

---

---

# PUTARAN 15 — nota cetak: harga master vs yang benar-benar dibayar

---

## TEMUAN 27 — 🔴 Nota dicetak dari HARGA MASTER, bukan dari yang ditagih

`PrintService.prepare_nota_context()` membangun baris nota dengan menggabungkan
`KunjunganTindakan → MasterTreatment.harga` dan `KunjunganResep → MasterProduk.harga_jual`
(`print_service.py:136` dan `:198`). **Totalnya** diambil dari
`transaksi_kasir.total_tagihan`.

Jadi satu lembar nota memuat **dua sumber kebenaran yang berbeda**: barisnya dari harga
hari ini, totalnya dari transaksi saat itu.

### Bukti 1 — harga berubah, nota lama ikut berubah

```
nota SEBELUM : Basic Treatment Rp 500.000   | total nota 2.790,14
harga master DINAIKKAN 2x
nota SESUDAH : Basic Treatment Rp 1.000.000 | total nota 2.790,14
```

Baris berubah, total tidak. Nota cetak-ulang menampilkan angka yang **tidak pernah
disetujui pasien**.

### Bukti 2 — terjadi SETIAP HARI, tanpa perubahan harga apa pun

Transaksi 311, pasien membership dengan tindakan berkuota:

```
snapshot tersimpan : harga_satuan = 0,00 · subtotal = 0,00 · total = 0,00
yang DICETAK       : "Basic Treatment — Rp 500.000"
total di nota      : Rp 0
```

**Nota yang diserahkan ke pasien memuat baris Rp 500.000 dan total Rp 0** — saling
bertentangan di kertas yang sama. Ini bukan skenario hipotetis: setiap tindakan kuota
dan setiap diskon membership mencetak nota seperti ini **hari ini**.

Kalau maksudnya menunjukkan penghematan member, itu wajar — tapi harus **ditulis
sebagai itu** (*"Harga normal Rp 500.000 — ditanggung membership"*), bukan disajikan
sebagai angka yang ditagih.

### Datanya untuk memperbaiki SUDAH ADA

| Lini | Snapshot | Sejak |
|---|---|---|
| Produk | `transaksi_detail_produk.harga_satuan`, `diskon_item`, `subtotal` | lama |
| Racikan | `transaksi_detail_racikan.nama_snapshot`, `subtotal` | Fase 3 |
| **Tindakan** | `transaksi_detail_tindakan.harga_satuan`, `diskon_item`, `subtotal` | **F3, 2026-10-04** |

⚠ **Transaksi SEBELUM perbaikan F3 tidak punya baris `transaksi_detail_tindakan`.**
Jadi perbaikan nota butuh fallback ke harga master untuk transaksi lama — dan idealnya
penanda bahwa angkanya rekonstruksi, bukan snapshot.

Ini juga alasan kenapa perbaikan ini tidak bisa sekadar "ganti sumber datanya": ia
harus menangani dua generasi data sekaligus.

**Tidak saya kerjakan** — nota adalah dokumen yang diserahkan ke pasien, dan
keputusan apa yang dicetak untuk tindakan kuota (Rp 0, atau harga normal dengan
keterangan) adalah keputusan dr. Hansen, bukan keputusan teknis.

### Kenapa ini mungkin yang paling terlihat dari seluruh audit

Dua puluh enam temuan sebelumnya hidup di laporan, ekspor, dan basis data. **Yang ini
tercetak di kertas dan diberikan ke pasien.**

---

## Catatan kejujuran tentang bukti di atas

Ketidakcocokan `1.300.000` vs `2.790,14` pada transaksi 3 sebagian **akibat data uji
saya sendiri** — harga tindakan itu saya ubah di putaran 1 untuk menguji pembulatan,
lalu saya kembalikan. Yang membuktikan cacatnya bukan angka itu, melainkan **uji
penggandaan** (baris berubah, total tidak) dan **transaksi 311** (data bersih, dibuat
lewat alur kasir sungguhan).

---

---

# PUTARAN 16 — tutup kasir: modal awal, selisih, dan celah antar-shift

---

## TEMUAN 28 — 🔴 Uang yang masuk di luar jam shift tidak masuk hitungan shift mana pun

Dua fakta yang masing-masing wajar, bertemu jadi celah:

1. **`proses_bayar` TIDAK menuntut sesi kasir terbuka.** Pembayaran bisa diproses
   kapan saja, tanpa `buka_kasir`.
2. **Rekonsiliasi shift menyaring `waktu_bayar >= shift_mulai`** saja — tidak ada
   batas atas, dan tidak ada yang menangkap uang di luar jendela mana pun.

Dibuktikan dengan rentang waktu nyata:

```
pembayaran Rp 250.000 TUNAI pukul 12:38
   (setelah shift A ditutup 11:38, sebelum shift B dibuka 13:38)

shift A (mulai 10:38) melihat TUNAI : 250.000
   └ tapi shift A sudah DITUTUP 11:38 — angkanya dibekukan sebelum uang ini ada
shift B (mulai 13:38) melihat TUNAI : 0

>>> Rp 250.000 tidak masuk hitungan shift mana pun
```

### Akibatnya

Omzetnya **benar** — transaksinya tercatat dan masuk laporan. Yang rusak adalah
**rekonsiliasi laci**:

- Uangnya **ada fisik** di laci, tapi `expected` shift B tidak memuatnya
- Jadi ia muncul sebagai **selisih lebih yang tidak bisa dijelaskan** saat shift B
  dihitung — dan `tutup_kasir` **mewajibkan catatan** kalau selisih ≠ 0
- Petugas shift B diminta menjelaskan uang yang bukan dari shift-nya

### Skenario yang paling mungkin bukan yang saya uji

Saya menguji "bayar setelah tutup". Yang lebih sering terjadi justru kebalikannya:
**kasir mulai melayani sebelum membuka sesi**. Pagi hari, pasien pertama sudah datang,
pembayaran diproses, dan `buka_kasir` baru ditekan setelahnya — maka `shift_mulai`
jatuh SESUDAH pembayaran itu, dan uangnya hilang dari hitungan dengan cara yang sama.

Di klinik yang sibuk, itu bukan kelalaian langka; itu urutan yang wajar.

### Tiga arah perbaikan — pilihannya keputusan dr. Hansen

| Opsi | Konsekuensi |
|---|---|
| **A. Wajibkan sesi terbuka untuk menerima pembayaran** | Paling tegas, dan menutup kedua arah. Tapi memblokir kasir yang lupa membuka — di tengah antrian pasien |
| **B. Hitung per TANGGAL, bukan per `shift_mulai`** | Tidak memblokir siapa pun; semua uang hari itu masuk hitungan. Tapi kabur kalau satu hari punya dua shift |
| **C. Peringatkan saat tutup** kalau ada pembayaran di luar jendela shift mana pun | Tidak mengubah alur, hanya memunculkan yang tersembunyi. Paling murah, tapi tetap menuntut orang membacanya |

Saya tidak memilih: A memblokir orang di depan pasien, dan itu keputusan operasional
klinik, bukan keputusan teknis.

---

## Yang DIPERIKSA di putaran 16 dan ternyata BERSIH

| Area | Hasil |
|---|---|
| **`modal_awal` tidak bisa diubah** | **BERSIH.** Hanya ditulis di `buka_kasir`; tidak ada satu pun jalur yang memperbaruinya. Jadi selisih laci tidak bisa disembunyikan dengan menyesuaikan modal |
| **Aritmetika selisih** | `total_selisih = total_counted − total_expected`, dihitung ulang **saat tutup** (bukan dari angka basi), dan `expected` TUNAI = `modal_awal + penjualan_tunai` |
| **Catatan wajib saat selisih** | Ada. `tutup_kasir` menolak kalau `total_selisih != 0` tanpa catatan |
| **Hard block pasien antri** | Ada (2026-07-10). Tutup kasir ditolak kalau masih ada pasien belum selesai hari ini |
| **VOID dikecualikan** | Sudah diverifikasi putaran 1 (`_bayar_today`) dan putaran 2 (refund tidak dobel-kurang) |

---

---

# PUTARAN 17 — FEFO & stok kedaluwarsa

---

## TEMUAN 29 — 🔴 FEFO memilih lot KEDALUWARSA lebih dulu

Query FEFO (`inventory_lot_service.py:28–43`) menyaring hanya `qty_sisa > 0`, lokasi,
tipe item, dan produk/bahan. **Tidak ada penyaring tanggal kedaluwarsa, dan tidak ada
penyaring status.**

Karena urutannya "ED terdekat keluar dulu", lot yang **sudah lewat** ED justru berada di
urutan paling atas — ED-nya paling awal.

Dibuktikan dengan dua lot:

```
tersedia:
   KEDALUWARSA  ED 2026-08-05  (lewat 60 hari)
   MASIH-BAIK   ED 2027-10-04

FEFO memilih: KEDALUWARSA, 10 unit
```

### ⚠ Pengamanannya ADA, tapi semuanya bertumpu pada manusia

Saya periksa hulunya sebelum menyebut ini bahaya, dan gambarannya tidak sesederhana
"sistem menyerahkan obat kedaluwarsa":

| Lapis | Ada? | Sifat |
|---|---|---|
| FEFO mengecualikan yang kedaluwarsa | ❌ | — |
| **Apoteker melihat batch + ED di layar sebelum serah** | ✅ | `apotek_detail_resep.html` menampilkan *"Batch (FEFO): 10× BATCH-X · ED 01/01/27"* |
| Laporan ED memuat yang sudah lewat | ✅ | Tanpa batas bawah, diurut ED menaik — yang kedaluwarsa muncul **paling atas** |
| Write-off ber-alasan `EXPIRED` | ✅ | Manual |
| **Peringatan/badge aktif** | ❌ | Tidak ada di dashboard maupun menu — apoteker harus **ingat membuka** laporannya |

Jadi yang berdiri antara stok kedaluwarsa dan pasien adalah **seorang apoteker yang
membaca tanggal di layar**. Itu kendali yang nyata — apoteker memang terlatih memeriksa
ED. Tapi ia juga **satu-satunya kendali yang otomatis**, dan otomasinya justru
**bekerja melawannya**: sistem menyodorkan lot kedaluwarsa lebih dulu, setiap kali.

Nuansa kecil yang memperberat: layarnya menampilkan ED sebagai tanggal biasa
(`05/08/26`), **tanpa menandainya sudah lewat**. Yang diminta dari apoteker adalah
menghitung tanggal, bukan membaca peringatan.

### Perbaikan yang disarankan

Tambahkan `StokLot.tgl_ed >= today` (atau `tgl_ed IS NULL`) ke `conds` FEFO, sehingga
lot kedaluwarsa tidak pernah disodorkan otomatis.

⚠ **Konsekuensinya perlu diputuskan:** kalau satu-satunya stok yang ada sudah
kedaluwarsa, pengecualian itu menghasilkan **shortfall** — penyerahan terhenti. Secara
klinis itu jawaban yang benar, tapi ia memblokir apotek di depan pasien, jadi keputusan
dr. Hansen.

Perbaikan paling murah yang tidak memblokir siapa pun: **tandai merah di layar** kalau
`tgl_ed < today`. Mengubah "membaca tanggal" jadi "membaca peringatan", tanpa menyentuh
alur.

---

## Yang DIPERIKSA di putaran 17 dan ternyata BERSIH

| Area | Hasil |
|---|---|
| **Urutan FEFO** | **BERSIH dan persis sesuai CLAUDE.md.** `tgl_ed.is_(None)` sebagai kunci PERTAMA membuat lot tanpa ED jatuh **terakhir** — bukan pertama seperti perilaku bawaan MySQL untuk NULL. Lalu `tgl_ed ASC → tgl_masuk ASC → id_lot ASC`. Dugaan awal saya bahwa "NULL last" tidak terimplementasi **salah** |
| **Jejak lot yang keluar** | `batch_terpakai` merekam batch + ED yang dipotong saat serah (P-L5), dan ikut ditulis ke keterangan audit |
| **`kedaluwarsa` di apotek_service** | Diperiksa: itu tentang **umur RESEP** (`MAX_UMUR_RESEP_HARI`), bukan ED lot. Dua hal berbeda dengan nama mirip — tidak tertukar |

---

## TEMUAN 30 — 🔴 `DISERAHKAN` dipakai sebagai bukti "stok sudah dipotong", padahal bisa terpasang tanpa satu lot pun keluar

**Putaran 18 — obat tertunda.** Dibuktikan dengan menjalankan layanannya, bukan membacanya.

### Yang sebenarnya terjadi

Obat yang **sudah dibayar** tidak dicadangkan stoknya. Itu konsisten dengan keputusan
klinik ("stok diizinkan minus — operasional jangan diblok", `apotek_repo.py:193`) dan
**bukan** cacatnya. Cacatnya ada di akibat yang tidak terlihat siapa pun.

Satu lot berisi 10 unit, batch `UJI-P18-B1`:

| Langkah | cache `stok_terkini` | `SUM(qty_sisa)` lot | baris `kunjungan_lot_terpakai` |
|---|---|---|---|
| keadaan awal | 10 | 10 | 0 |
| A bayar 10, obatnya ditunda 3 hari | **10** | 10 | 0 |
| B bayar 10 dan langsung diserahkan | 0 | 0 | **1** (sah) |
| A kembali menagih obat yang sudah dibayar | **−10** | **0** | **1 — tidak bertambah** |

Tiga hal terbukti sekaligus:

1. **Tidak ada pencadangan.** Sesudah A bayar dan obatnya ditunda, `stok_terkini` tetap
   10. Petugas yang melayani B melihat 10 tersedia, tanpa petunjuk apa pun bahwa 10 di
   antaranya sudah terjual. Pencarian di seluruh kode: tidak ada konsep reservasi.
2. **Penyerahan A tidak diblokir.** Panggilan `serahkan_obat` **berhasil**, resep A
   menjadi `DISERAHKAN`, dan `stok_terkini` turun ke −10.
3. **Tidak ada lot yang keluar untuk A.** `SUM(qty_sisa)` tetap 0 dan
   `kunjungan_lot_terpakai` tidak bertambah. FEFO melaporkan `shortfall 10`.

### Kenapa ini soal uang, bukan soal gudang

`DISERAHKAN` punya **dua arti** bagi dua penulis yang berbeda — pola CLAUDE.md §4.1:

| Pembaca | Arti yang diasumsikan |
|---|---|
| Apoteker & modul apotek | "obat sudah di tangan pasien" |
| `_reverse_stok_per_item` (void) | "stok **sudah dipotong**, jadi void boleh mengembalikannya" |

Penjaga void menghitungnya lewat `_qty_diserahkan_produk`, yang menjumlahkan `qty` baris
berstatus `DISERAHKAN` (`kasir_service.py:1656-1662`). Docstring-nya menyatakan maksudnya
terang-terangan: *"hanya me-reverse kalau obat memang sudah diserah (stok sudah
dipotong) … cegah overstate senyap."* Niatnya benar; buktinya yang tidak cukup. Baris A
memenuhi syarat itu **tanpa** pernah mengurangi lot — sehingga void atas transaksi A akan
mengembalikan 10 unit yang tidak pernah keluar.

### Apa yang membersihkan jejaknya

Divergensi cache-vs-lot **tidak** permanen, dan dugaan awal saya bahwa ia permanen salah.
Dua jalur menghitung ulang cache dari lot:

| Jalur | Perilaku |
|---|---|
| `retur_service._recompute_produk_cache` | `stok_terkini = SUM(qty_sisa)` |
| `opname_service` (approve) | `stok_terkini = SUM(qty_sisa)` (baris 259-268) |

Penerimaan barang **tidak** — ia menambah (`pemesanan_service.py:441`), begitu juga
`update_stok_produk` (`apotek_repo.py:195-197`). Jadi angka −10 bertahan sampai ada
opname, lalu **hilang** terserap sebagai selisih opname. Selisih itu muncul di periode
lain, tanpa kaitan terlihat ke penjualan yang menyebabkannya.

### Yang TIDAK saya temukan (supaya tidak dilaporkan berlebihan)

- **Tidak ada laporan laba/margin sama sekali** di seluruh aplikasi. Jadi sudut "HPP tak
  tercatat → margin terlalu tinggi" **belum punya permukaan untuk salah**. Saya tidak
  melaporkannya sebagai akibat; ia menjadi relevan justru kalau Temuan 22 (laporan
  ekonomi membership) dikerjakan.
- **Tidak ada satu pun tempat yang menandai stok negatif.** Bukan di dashboard, bukan di
  `inventory_report_service`. Peringatan `shortfall_warnings` hanya muncul di pesan satu
  transaksi penyerahan dan di `keterangan` audit — hilang begitu apoteker menutup halaman.
- **Tidak ada rekonsiliasi berjadwal** `stok_terkini` vs `SUM(qty_sisa)`.

### Usul perbaikan (butuh keputusan dr. Hansen)

Tanpa mengubah filosofi "jangan blokir operasional":

1. **Catat kekurangannya sebagai keadaan, bukan sebagai pesan.** Saat `shortfall > 0`,
   tulis baris `inventory_history` bertipe tersendiri (mis. `SERAH_TANPA_LOT`). Itu
   membuat penyerahan fantom bisa dicari ulang, dan void bisa menolak mengembalikan
   qty yang lotnya tidak pernah keluar.
2. **Jangan samakan `DISERAHKAN` dengan "lot sudah dipotong".** Penjaga void sebaiknya
   membaca `kunjungan_lot_terpakai`, bukan status resep — sumber yang memang mencatat lot.
3. **Nilai kewajiban obat tertunda.** `list_obat_tertunda` menampilkan nama dan qty, tanpa
   rupiah. Uangnya sudah diterima tapi barangnya belum diserahkan; nilainya layak terlihat.
4. Pencadangan stok untuk obat yang sudah dibayar — **perubahan kebijakan**, bukan
   perbaikan bug. Dicatat sebagai pilihan, bukan rekomendasi.

### Catatan kejujuran tentang bukti

Percobaan pertama saya memakai produk uji **tanpa** baris `stok_lot`, sehingga peringatan
"lot kurang" juga muncul di kaki B — artefak setup saya, bukan temuan. Angka di tabel atas
berasal dari percobaan kedua dengan satu lot nyata berisi 10, sehingga kaki B terbukti
mengonsumsi lot secara sah dan kaki A terbukti tidak. Seluruh data uji (`UJI-P18`, 4
kunjungan) sudah dihapus; `master_produk` kini nol baris berstok negatif.

### ✅ DIPERBAIKI 2026-10-04 — void tidak lagi menciptakan barang fantom

**Yang diubah satu tempat saja:** `_reverse_stok_per_item` (`kasir_service.py`). Di skema
per-item, qty yang tidak punya jejak `kunjungan_lot_terpakai` **tidak lagi** dibuatkan lot
`VOID-RETURN` maupun dimasukkan ke lot pilihan operator.

`stok_terkini` tetap dikembalikan **penuh**, karena penyerahan juga memotongnya penuh.
Dengan begitu cache dan lot sama-sama kembali ke keadaan sebelum serah — persis:

| Keadaan saat serah | Sebelum serah | Sesudah void (perbaikan) |
|---|---|---|
| lot cukup (10 dari 10) | cache 10, lot 10 | cache 10, lot 10 ✓ |
| lot kurang (4 dari 10) | cache 4, lot 4 | cache 4, lot 4 ✓ |
| lot kosong (0 dari 10) | cache 0, lot 0 | cache 0, lot 0 ✓ |

**Filosofi klinik tidak disentuh.** Stok tetap boleh minus dan penyerahan tetap tidak
pernah diblokir. Yang diperbaiki adalah jejaknya, bukan aturannya.

#### Dibuktikan DUA ARAH

Tiga skenario dijalankan terhadap kode LAMA dan kode BARU:

| Skenario | Kode lama | Kode baru |
|---|---|---|
| Serah fantom (lot 0 dari 10) | **GAGAL** — lot `VOID-RETURN` berisi **10 unit fantom** (cache 0, lot 10) | LULUS — cache 0, lot 0 |
| Serah normal (10 dari 10) | LULUS | LULUS — pulih ke lot ASLI, ED terjaga |
| Serah sebagian (4 dari 10) | **GAGAL** — lot 10 padahal hanya 4 pernah ada → **6 unit fantom** | LULUS — cache 4, lot 4 |

Skenario normal lulus di kedua versi — itu bukti bahwa perbaikan ini **tidak merusak**
pemulihan yang sah.

#### Pemeriksa baru: `scripts/cek_serah_tanpa_lot.py`

Perbaikan di atas menghentikan kerusakan BARU. Yang sudah telanjur terjadi perlu bisa
dicari, dan dulu hanya hidup sebagai pesan sekali-lewat. Pemeriksa ini menurunkannya dari
data yang sudah ada — **tanpa kolom baru, tanpa migrasi** (kolom `inventory_history
.jenis_mutasi` adalah ENUM; menambah jenis baru butuh migrasi dan persetujuan dr. Hansen).

Ia sengaja memisahkan **yang tidak dapat dinilai**, supaya tidak berteriak serigala:
jejak gaya lama (sebelum task #54), dan produk yang memang tidak pernah punya lot. Itu
langsung terbukti berguna — 3 baris Aclam 500mg akan menjadi temuan palsu tanpanya.

Diuji dua arah: dengan dua kasus nyata di DB ia melaporkan keduanya berikut angka
`TANPA jejak lot` (10 dan 6); sesudah datanya dibersihkan ia melaporkan nihil.

⚠ **Harus dijalankan di mini PC** — laptop tidak punya data klinik sungguhan, jadi
"0 temuan" di sini tidak mengatakan apa pun tentang keadaan di klinik.

#### Temuan sampingan: fixture test bergantung pada data seed

`test_void_return_lot.py` memakai `db.query(Kunjungan).first()`, dan kunjungan itu di DB
seed ternyata sudah punya baris resep `DISERAHKAN` milik produk lain. Akibatnya
`_mode_per_item` selalu menjawab True dan bentuk "data lama" **tidak pernah benar-benar
teruji** — hasil testnya bergantung pada isi DB, bukan pada kodenya. Fixture kini membuat
kunjungannya sendiri.

Kedua test lama (`lot_pilihan`, `fallback_lot_retur_baru`) menjaga fitur **P-L6b** yang
nyata: operator memilih batch fisik yang diretur untuk telusur QC. Fitur itu tidak
dihapus — ia dipindahkan ke bentuk **data LAMA**, satu-satunya tempat ia masih berlaku.
Untuk data baru, jejak lot sudah tahu lot persisnya, yang lebih baik daripada bertanya ke
operator. Tiga test baru menjaga perilaku per-item. Suite: **108 lulus**.

#### Yang TIDAK dikerjakan, dan kenapa

| Usulan semula | Keputusan |
|---|---|
| Baris `inventory_history` bertipe `SERAH_TANPA_LOT` | **Tidak dikerjakan** — `jenis_mutasi` ENUM, butuh migrasi + persetujuan. Pemeriksa di atas memberi hasil yang sama dari data yang sudah ada |
| Nilai rupiah kewajiban obat tertunda di `list_obat_tertunda` | **Belum** — penambahan fitur, bukan perbaikan cacat. Menunggu keputusan dr. Hansen |
| Pencadangan stok untuk obat yang sudah dibayar | **Tidak** — perubahan kebijakan, bukan perbaikan bug |

**Masih perlu keputusan dr. Hansen:** jalankan `cek_serah_tanpa_lot` di mini PC. Untuk
tiap baris yang muncul, pertanyaannya adalah apakah pasiennya **menerima** obatnya
(berarti lot/opname yang salah) atau **tidak menerima** (berarti ada kewajiban yang belum
dipenuhi, dan uangnya sudah diterima).

---

## Yang DIPERIKSA di putaran 18 dan ternyata BERSIH

| Area | Hasil |
|---|---|
| **Dua arti "tertunda"** | **BERSIH — dan kerangka awal saya keliru.** `DITUNDA` = ditunda di kasir, **belum ditagih**; `DIBAYAR` tanpa `DISERAHKAN` = **sudah dibayar**, menunggu diambil. Dua konsep berbeda yang tidak tertukar di kode |
| **Pemisahan baris saat tunda di kasir** | Baris asli tetap `PENDING` (ditagih hari ini), baris baru membawa sisanya sebagai `DITUNDA`. Sengaja **tidak** memakai `id_resep_asal` — kolom itu berarti "salinan saat penebusan" (penanda anti-tebus-ganda); memakainya akan menyembunyikan baris tertunda dari `list_resep_belum_ditebus` |
| **`refund_item_tertunda`** | **BERSIH dan pagarnya lengkap.** Hanya untuk item `DIBAYAR`; `DISERAHKAN` ditolak (jalurnya retur), `PENDING` ditolak (jalurnya `void_item_resep`), `BATAL` ditolak. Stok tidak disentuh — benar, karena `DIBAYAR` menjamin stok belum dipotong. Nilai refund = **bersih** (subtotal dikurangi porsi diskonnya), bukan harga daftar |
| **Serah sebagian tanpa tanggal janji** | **BERSIH — dugaan saya salah.** Saya menduga sisa obat bisa mengendap tak terlihat karena daftar Obat Tertunda menyaring `tgl_janji_kirim IS NOT NULL`. Pagarnya ternyata ada di server, `apotek_service.py:495`, lengkap dengan syarat `kunjungan.tgl_janji_kirim is None` — bukan hanya di JavaScript template |
| **`tgl_janji_kirim` dikosongkan terlalu cepat** | **BERSIH.** Hanya dikosongkan kalau `n_sisa == 0` (baris 614). Sisa yang masih ada mempertahankan tanggal lamanya, sehingga tetap muncul — dan tampil `overdue` kalau tanggalnya sudah lewat |
| **`tunda_serah_obat` tanpa tanggal** | Ditolak eksplisit: "Tanggal janji kirim/ambil WAJIB diisi" |

⚠ **Satu celah dokumentasi, bukan cacat perilaku:** docstring `SerahkanObatRequest`
menyatakan `tgl_janji_kirim_sisa` **WAJIB**, tetapi tipenya `Optional[date] = None` tanpa
validator. Perilakunya benar karena pagarnya ada di service. Yang perlu diingat: aturan
itu hidup di **prosa**, bukan di skema — pembaca berikutnya yang memakai skema ini dari
jalur lain tidak akan mendapat pagar itu.

---

## Putaran berikutnya (belum dikerjakan)

~~1. Refund per item~~ · ~~2. komisi saat void~~ · ~~3. revert kuota~~ ·
~~4. Decimal vs float~~ — **semua selesai di putaran 2.**

~~1. Membership~~ · ~~2. Retur distributor~~ — **selesai di putaran 3.**

~~1. Ekspor Finance vs laporan layar~~ · ~~2. Tutup kasir~~ · ~~4. Stok saat void~~
— **selesai di putaran 4.**

~~4. Stock opname~~ · ~~5. Laporan komisi vs ledger~~ — **selesai di putaran 7.**

~~3. Membership upgrade/perpanjang~~ · ~~4. inventory_history~~ — **selesai di putaran 8.**

~~4. Kuota membership~~ (putaran 9) · ~~triase test merah~~ (putaran 10) ·
~~series & jalur persetujuan~~ (putaran 11).

Sisa & usulan putaran 12:
1. **F2 — konsep "periode payroll ditutup"** (desain, bukan audit).
2. **Pembersihan baris yang terlanjur rusak** — Temuan 11 membuktikan baris itu TERBAYAR.
3. **M-FIN-3** — melengkapi `hpp_satuan`/`nilai_mutasi` (Temuan 13).
4. **Kunci baris kuota + indeks unik** (Temuan 15 & 16) — yang kedua butuh migrasi.
5. Series treatment (`pasien_rencana_treatment`) & `_cancel_series_sesi_pending` —
   belum diaudit; sejenis kuota, yaitu hak yang sudah dibayar di muka.
6. Booking & deposit (F8, PARKIR) — belum ada uangnya.

⚠ **Catatan jujur:** tujuh putaran telah menghasilkan 12 temuan, dan antrean keputusan
yang menunggu dr. Hansen kini lebih panjang daripada nilai putaran berikutnya. Audit
yang temuannya menumpuk tanpa diputuskan berhenti menjadi audit dan mulai menjadi
daftar yang diabaikan — persis pola yang berulang kali ditemukan dokumen ini sendiri.
