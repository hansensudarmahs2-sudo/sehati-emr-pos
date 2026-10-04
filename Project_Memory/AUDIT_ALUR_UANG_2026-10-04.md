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

## Putaran berikutnya (belum dikerjakan)

~~1. Refund per item~~ · ~~2. komisi saat void~~ · ~~3. revert kuota~~ ·
~~4. Decimal vs float~~ — **semua selesai di putaran 2.**

~~1. Membership~~ · ~~2. Retur distributor~~ — **selesai di putaran 3.**

~~1. Ekspor Finance vs laporan layar~~ · ~~2. Tutup kasir~~ · ~~4. Stok saat void~~
— **selesai di putaran 4.**

~~3. Retur ke distributor~~ · ~~5. helper A8/DEC-084~~ — **selesai di putaran 6.**

Sisa & usulan putaran 7:
1. **F2 — konsep "periode payroll ditutup"** (desain, bukan audit). Prasyarat agar
   penarikan komisi surut punya aturan yang jelas.
2. **Pembersihan baris yang terlanjur rusak** oleh Temuan 5 — query deteksi sudah ada,
   keputusannya belum.
3. Membership Fase 2: upgrade & perpanjang di tengah periode — proporsi harga.
4. Stock opname: selisih stok & penyesuaian nilai — jalur uang yang belum disentuh.
5. Komisi: laporan per-staf vs `komisi_ledger` — apakah angkanya cocok.
