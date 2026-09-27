# Desain — Apotek sebagai Kanal Penebusan Resep (menggantikan framing lama task #41)

**Dibuat:** 2026-09-25 · **Status:** menunggu persetujuan dr. Hansen
**Asal:** konteks dr. Hansen 2026-09-25 — apoteker menerima resep dari luar; resep hasil
konsultasi online dokter internal; dan resep internal yang tidak ditebus hari itu lalu
ditebus belakangan. "Ini juga bagian dari apoteker."

---

## 1. Ini mengubah arti #41

#41 semula dicatat sebagai masalah **peta peran**. Yang sebenarnya dibutuhkan:
**apotek menjadi kanal penebusan resep tersendiri**, dengan tiga asal resep yang
berbeda perlakuan komisinya.

| Asal resep | Peresep | Komisi dokter | Catatan medis |
|---|---|---|---|
| **RESEP_LUAR** | dokter di luar klinik | **tidak ada** | tidak ada (di luar wewenang klinik) |
| **RESEP_ONLINE** | dokter internal, konsultasi jarak jauh | **ada** | apoteker menyusun draf, dokter menyetujui (§5b) |
| **TEBUS_LANJUT** | dokter internal, dari kunjungan lama | **ada**, ke peresep asli | sudah ada di kunjungan asal |

## 2. Keputusan dr. Hansen

| # | Pertanyaan | Keputusan |
|---|---|---|
| 1 | Pembeli wajib pasien terdaftar? | **Ya**, boleh data ringkas |
| 2 | Identitas peresep luar | **Nama + asal klinik**, diketik bebas, WAJIB |
| 3 | Komisi resep luar | **Tidak ada** |
| 4 | Masuk riwayat pasien? | **Ya** |
| 5 | Penerima pembayaran | **Tetap kasir**; apoteker TIDAK diberi akses kasir |
| 6 | Kunjungan kedua di hari sama | **Boleh** untuk penebusan resep |
| 7 | SOAP untuk resep online | **Apoteker menyusun draf dari chat, dokter menyetujui jadi SOAP miliknya** (ide dr. Hansen, §5b) |
| 10 | Obat keluar sebelum dokter menyetujui? | **Boleh** — keputusan meresepkan sudah dibuat dokter lewat chat; SOAP adalah pencatatan yang menyusul, bukan izin yang ditunggu |
| 11 | Dokter tidak setuju isi draf | **Sunting lalu setujui versinya sendiri**; catatan apoteker tetap tersimpan sebagai asal-usul |
| 8 | Masa berlaku resep belum ditebus | **30 hari** → diperingatkan, **tetap boleh** dilanjutkan |
| 9 | Tebus sebagian | **Boleh**, sisanya tetap bisa ditebus kemudian |

## 3. Temuan pemetaan yang menentukan bentuk desain

**Pakai ulang `KunjunganService.beli_produk_lengkap` (`kunjungan_service.py:427`).** Ia
sudah menghasilkan bentuk yang tepat: 1 `kunjungan` lahir `ANTRI_BAYAR` (tanpa SOAP,
tanpa dokter) + N `kunjungan_resep`. Hilirnya — kasir → apotek → potong stok FEFO →
COMPLETED, termasuk obat tertunda dan serah per item — sudah lengkap dan teruji.

**Transaksi berdiri sendiri (pola MEMBERSHIP, `id_kunjungan=NULL`) akan GAGAL** memenuhi
keputusan #4: `pasien_repo.get_riwayat_produk_terbayar:299` INNER JOIN ke `kunjungan`.

**Lubang lama yang ikut tertutup**: tidak ada kolom yang membedakan kunjungan konsultasi
dari beli-produk-saja. Pembedanya cuma `"flow": "BELI_PRODUK_ONLY"` di **JSON audit log**
(`kunjungan_service.py:522`) — tidak bisa di-query untuk UI maupun laporan.

**Kenapa TEBUS_LANJUT tidak boleh "menghidupkan kembali" kunjungan lama** (ini yang
sempat saya pertimbangkan lalu tolak): antrian kasir dan apotek menyaring **hari ini**
(`apotek_repo.list_antrian_obat:35`). Kunjungan lama yang diaktifkan ulang tidak akan
pernah muncul di layar siapa pun. Pendapatannya sendiri aman — laporan memakai
`waktu_bayar`, bukan tanggal kunjungan — tapi operasionalnya buntu. Karena itu penebusan
membuat **kunjungan BARU yang menunjuk ke kunjungan asal**.

## 4. Perubahan data

**Migrasi baru** (`revises = 20260922_0400`):

Pada **`kunjungan`**:
- `jenis_kunjungan` String(20) NOT NULL default `'KLINIS'`
  → `KLINIS` · `RESEP_LUAR` · `RESEP_ONLINE` · `TEBUS_LANJUT`
- `peresep_luar_nama` String(100) null · `peresep_luar_asal` String(150) null
- `id_kunjungan_asal` int null, FK ke `kunjungan` — diisi saat TEBUS_LANJUT

Pada **`kunjungan_resep`**:
- `id_resep_asal` int null, FK ke `kunjungan_resep` — baris salinan menunjuk baris asalnya

Peresep luar diletakkan di `kunjungan`, bukan `kunjungan_resep`: satu lembar resep
berlaku untuk semua obat di dalamnya.

**Tidak ada kolom "sudah ditebus"** di baris asal. Statusnya diturunkan dari keberadaan
salinan: sebuah baris PENDING sudah ditebus bila ada baris lain yang `id_resep_asal`-nya
menunjuk ke dia. Satu sumber kebenaran, tidak ada dua penanda yang bisa berselisih.

**Tidak ada kolom "SOAP belum lengkap"**: diturunkan dari `jenis_kunjungan ==
'RESEP_ONLINE'` **dan** tidak ada baris `pemeriksaan_klinis`. Penanda turunan tidak bisa
basi.

## 5. Tiga alur di satu layar

Apoteker membuka **`/web/apotek/tebus-resep`**, memilih pasien, lalu memilih asal resep:

**Resep luar** → isi nama peresep + asal klinik (wajib) → pilih obat → simpan.
Komisi **dilewati secara eksplisit**.

**Resep online (dokter internal)** → pilih dokter dari daftar staf → pilih obat → simpan.
`id_staf_dokter_assigned` diisi dokter itu, sehingga aturan komisi produk yang sudah ada
bekerja sendiri tanpa kode baru. Kalau dokter belum membuat SOAP, kunjungan itu muncul di
daftar **"Resep online menunggu SOAP"** supaya tidak terlupakan selamanya — inilah harga
dari keputusan #7, dan ia harus terlihat.

**Tebus lanjut** → sistem menampilkan resep PENDING milik pasien dari kunjungan-kunjungan
lama yang **belum pernah ditebus**, dengan umurnya. Apoteker mencentang yang ditebus hari
ini. Yang tidak dicentang tetap tersedia untuk ditebus lain kali.
- Resep lebih tua dari **30 hari** diberi peringatan mencolok + anjuran konsultasi ulang,
  tapi **tetap bisa** dicentang.
- Komisi jatuh ke **peresep asli** (`id_staf_dokter_assigned` kunjungan asal, atau penulis
  SOAP pertamanya — fallback yang sama dengan task #52), bukan ke apoteker.

## 5b. Draf SOAP oleh apoteker → disetujui dokter

Ide dr. Hansen, menggantikan daftar "menunggu SOAP" versi saya. Bedanya mendasar: daftar
tadi **pasif** — ia hanya menagih, dan kemungkinan besar menumpuk. Ini **aktif** — bahannya
sudah disiapkan, dokter tinggal membaca dan memutuskan.

**Alurnya**: apoteker menyalin inti percakapan (chat/konsultasi online) ke draf SOAP →
kunjungan muncul di antrian dokter yang bersangkutan → dokter membaca, **menyunting bila
perlu**, lalu menekan **"Setujui & jadikan SOAP saya"** → tersimpan sebagai SOAP miliknya.

**Draf hidup di `pemeriksaan_klinis` yang sama**, bukan tabel terpisah. `id_staf_dokter`
sudah nullable, jadi draf = baris dengan dokter masih kosong. Begitu disetujui, ia otomatis
ikut ke riwayat, resume medis, dan tautan diagnosa — semuanya sudah jalan, tidak ada yang
perlu dibangun ulang.

Kolom baru di `pemeriksaan_klinis`:
- `status_soap` String(20) NOT NULL default `'FINAL'` → `DRAFT_APOTEK` · `FINAL`
- `id_staf_penyusun` int null, FK staf — apoteker yang menyusun draf
- `waktu_konsultasi` DateTime null — **kapan percakapannya terjadi**
- `waktu_disetujui` DateTime null — kapan dokter menyetujui

### Tiga hal yang sengaja tidak disederhanakan

**Jejak apoteker TIDAK dihapus.** Tanggung jawab memang pindah ke dokter yang
menyetujui, tapi catatannya tetap menyatakan "disusun dari catatan apoteker X, disetujui
dr. Y". Bukan untuk mengurangi tanggung jawab dokter — justru sebaliknya: kalau kelak
ditanya, rantainya jelas dan dokter bisa menunjukkan atas dasar apa dia menyetujui.
Menghapus asal-usulnya membuat catatan itu tampak seperti pemeriksaan langsung.

**Tanggal tidak boleh berbohong.** `waktu_konsultasi` dan `waktu_disetujui` disimpan
terpisah. SOAP yang disetujui tiga hari kemudian tidak boleh terbaca seolah pemeriksaan
terjadi hari itu — ada yang akan membaca rekam medis ini setahun lagi.

**Kata kerjanya menyatakan tanggung jawab.** Tombolnya berbunyi "Setujui & jadikan SOAP
saya", bukan "Tambahkan", dan isinya bisa disunting sebelum disimpan. Satu tombol adalah
kemudahan yang membuat fitur ini benar-benar terpakai — dan kemudahan yang sama membuat
orang menyetujui tanpa membaca. Yang bisa dilakukan desain hanyalah memastikan dia tahu
sedang mengambil tanggung jawab, bukan sedang menyalin data.

### ⚠ Bahaya implementasi: draf mencemari query SOAP yang sudah ada

Menaruh draf di `pemeriksaan_klinis` itu elegan, TAPI setiap query yang sudah ada terhadap
tabel itu kini bisa ikut menarik draf yang belum disetujui. **Semua harus disaring ke
`status_soap='FINAL'`** kecuali memang sengaja ingin melihat draf. Yang wajib diperiksa
satu per satu: riwayat SOAP pasien · resume medis cetak · laporan kinerja dokter ·
`komisi_service` fallback penulis SOAP pertama (`komisi_service.py:76-85` — ia sudah
menyaring `id_staf_dokter is_not(None)` sehingga draf aman, tapi jangan bergantung pada
kebetulan itu; saring eksplisit) · `_build_soap_ctx` di `dokter.py`.

Pola kegagalannya persis seperti `_produk_stok_sudah_dipotong` pada task #54: satu tabel
dipakai dua arti, dan query lama masih mengira artinya cuma satu.

## 6. Perubahan kode

| Lapis | Berkas | Perubahan |
|---|---|---|
| Model | `app/db/models/kunjungan.py` | 4 kolom baru (3 di `kunjungan`, 1 di `kunjungan_resep`) |
| Service | `kunjungan_service.py:427` | parameter `jenis_kunjungan`, `peresep_nama`, `peresep_asal`, `id_dokter`, `id_kunjungan_asal`, `resep_asal_ids`; tanda tangan lama tetap kompatibel |
| Service | `kunjungan_service.py:452` duplicate guard | dikecualikan untuk tiga jenis penebusan |
| Service | **baru** `ApotekService.list_resep_belum_ditebus(id_pasien)` | resep PENDING dari kunjungan lama yang belum punya salinan, + umur hari |
| Service | `kasir_service.py:761` | **guard komisi eksplisit**: lewati hanya bila `RESEP_LUAR` |
| Route | `app/web/routes/apotek.py` | `GET/POST /web/apotek/tebus-resep`, gate `require_apoteker_role` |
| Model | `app/db/models/kunjungan.py` `PemeriksaanKlinis` | 4 kolom draf SOAP (§5b) |
| Route | `app/web/routes/dokter.py` | antrian draf SOAP + aksi "Setujui & jadikan SOAP saya" |
| **Sapu** | semua query `pemeriksaan_klinis` | saring `status_soap='FINAL'` — lihat peringatan §5b |
| Template | `apotek_tebus_resep.html` | tiga mode dalam satu layar |
| Template | `pasien_riwayat.html` | badge asal resep + "ditebus pada …" untuk baris yang sudah disalin |
| Template | `_kasir_antrian_content.html` | label antrian bayar per jenis |

**JANGAN** melonggarkan `require_antrian_mgmt_role` di `pasien.py:637,701` — itu memberi
apoteker akses ke seluruh modul pasien.

### Kenapa guard komisi dibuat eksplisit

Sekarang komisi resep luar akan nol **secara kebetulan**, karena `komisi_service.py:71-86`
butuh dokter internal. Tapi kebetulan itu rapuh: task #52 baru saja menambahkan fallback ke
penulis SOAP pertama. Satu fallback baru lagi bisa membuat komisi mengalir ke dokter yang
tidak meresepkan apa pun. Aturannya harus dinyatakan, bukan disimpulkan.

## 7. Urutan kerja

| Langkah | Isi | Uji |
|---|---|---|
| **R1** | Migrasi + model 4 kolom | `alembic upgrade`, cek schema |
| **R2** | `beli_produk_lengkap` terima jenis/peresep/dokter/asal; duplicate guard dikecualikan | via DB |
| **R3** | Guard komisi eksplisit | bayar resep luar → `komisi_ledger` kosong; resep online → terisi |
| **R4** | `list_resep_belum_ditebus` + penanda salinan | via DB, termasuk anti-tebus-ganda |
| **R5** | Layar apoteker tiga mode | **uji desktop** |
| **R6** | Draf SOAP apoteker + antrian dokter + tombol setujui; **sapu semua query `pemeriksaan_klinis`** | **uji desktop** |
| **R7** | Badge riwayat + label kasir + asal-usul SOAP di resume medis | **uji desktop** |
| **R8** | "Sisakan untuk nanti" di kasir — lihat §11 | **uji desktop** |

## 8. Uji terima

1. **Resep luar**: tanpa nama peresep → ditolak. Dengan nama → kunjungan `RESEP_LUAR`,
   setelah dibayar `komisi_ledger` **kosong**.
2. **Resep online**: pilih dokter internal → setelah dibayar, komisi produk **terisi atas
   nama dokter itu**, dengan aturan komisi tiap produk seperti biasa.
3. **Draf SOAP**: apoteker menulis draf → muncul di antrian dokter yang dipilih → dokter
   menyunting satu kalimat lalu menekan "Setujui & jadikan SOAP saya" → tersimpan sebagai
   SOAP dokter itu, **dengan nama apoteker penyusun masih terbaca** dan dua waktu
   (konsultasi & persetujuan) tercatat terpisah.
3b. Draf yang **belum** disetujui **tidak** muncul di: riwayat SOAP pasien, resume medis
   cetak, laporan kinerja dokter, maupun sebagai dasar komisi. Ini yang paling mudah
   terlewat — periksa satu per satu, jangan diasumsikan.
4. **Tebus lanjut**: resep PENDING dari kunjungan 3 hari lalu muncul; centang 1 dari 3 item
   → hanya 1 yang ditagih. Dua sisanya **masih muncul** di penebusan berikutnya.
5. Item yang sudah ditebus **tidak muncul lagi** — coba tebus dua kali, tidak bisa.
6. Resep berumur 45 hari → muncul dengan peringatan, **tetap bisa** ditebus.
7. Komisi tebus lanjut jatuh ke **peresep asli**, bukan apoteker, bukan kosong.
8. Pasien yang pagi berkonsultasi tetap bisa menebus resep luar siang harinya.
9. Riwayat pasien menampilkan asal resep, dan baris yang sudah ditebus menyatakan kapan.
10. Apoteker **tidak** bisa membuka kasir maupun modul pasien lainnya.

## 9. Yang sengaja TIDAK dibangun

- **Apoteker menerima pembayaran** — keputusan #5.
- **Master dokter luar** — nama diketik bebas; bisa menyusul tanpa mengubah bentuk data.
- **Foto lembar resep / tangkapan layar chat — TIDAK PERLU, dan ini bukan kelalaian.**
  [Penjelasan dr. Hansen 2026-09-25] Lembar resep fisik **diarsipkan apotek secara offline**;
  itu memang diwajibkan Dinas Kesehatan dan BPOM. Lapis buktinya sudah ada di luar sistem,
  jadi menduplikasinya di dalam sistem hanya menambah alur unggah dan penyimpanan tanpa
  menambah kekuatan bukti. Untuk tebus lanjut / tebus sebagian, SOAP-nya bahkan sudah ada
  di EMR sejak kunjungan aslinya.
- **Nomor arsip resep fisik** — sempat diusulkan supaya lembar fisik bisa ditunjuk langsung
  saat pemeriksaan (bukan disisir). Keputusan dr. Hansen: **belum perlu**; penomoran arsip
  diurus terpisah, penautan bisa menyusul kalau ternyata dibutuhkan saat pemeriksaan.
- **Pembedaan OTC vs obat keras** — semua resep luar wajib peresep, tanpa kecuali.
- ~~**Racikan lewat jalur ini**~~ — **DIBATALKAN 2026-09-27, lihat §12.**
  Alasan lama: "racikan ad-hoc oleh apoteker tanpa resep dokter adalah persoalan
  medikolegal tersendiri." Itu benar, tapi **bukan kasus yang ada di klinik**.

## 12. R9 — Input racikan di layar tebus resep (2026-09-27, dibangun)

dr. Hansen: *"ada satu yang mengganjal. saat tebus obat luar, seharusnya ada input racikan"*.

**Kenapa pengecualian §9 salah.** Saya menimbang skenario "apoteker mengarang racikan
sendiri" — itu memang belum diputuskan. Yang sebenarnya terjadi: **dokter luar menulis
racikan di lembar resepnya**, apoteker hanya **menyalin**. Peresepnya tercatat
(`peresep_luar_nama` / `id_dokter` untuk resep online), lembar fisiknya diarsipkan apotek.
Jadi tidak ada wewenang baru yang diberikan — yang ada justru resep sah yang tidak bisa
dilayani sistem.

**Bentuknya: mesin racikan yang sudah ada, dipakai ulang — bukan disalin.**
Sebelum menyambungkan, dua blok logika dipindahkan dari `routes/dokter.py` ke
`RacikanService` supaya tidak ada dua salinan yang pelan-pelan berbeda:

| Dipindah ke service | Isinya |
|---|---|
| `RacikanService.parse_form_racikan(form)` | isian kartu → `racikan_list` untuk disimpan |
| `RacikanService.parse_card_form(form, token)` | satu kartu → `(cur, bahan_rows)` untuk hitung ulang |
| `RacikanService.build_card_ctx(token, cur, bahan_rows, endpoint=…)` | context render kartu |

Alasannya bukan kerapian: **di kode inilah dulu lahir tiga bug token** (kartu tertukar
identitas karena token dibaca dari body, kartu ke-2 lahir dari cache dengan token kartu
ke-1, KRIM dikalikan 15). Dua salinan berarti dua kali membayar utang itu.

`_racik_card.html` kini menerima `racik_endpoint`; dokter dan apotek punya rute
hitung-ulang sendiri karena **penjaga perannya berbeda** (`require_apoteker_role`),
tapi kartunya satu berkas:

- `GET  /web/apotek/_racik-card`   → `Cache-Control: no-store` (wajib, alasan di atas)
- `POST /web/apotek/_racik-hitung` → token dari **query param**, bukan body (wajib)

**Resep boleh berisi racikan SAJA.** Resep luar bisa berupa kapsul racikan tanpa obat
paten. `beli_produk_lengkap` dulu menolak `produk_list` kosong, jadi ditambah
`izinkan_tanpa_produk` — dipakai HANYA kalau ada racikan. Rute memeriksa
"tidak ada produk **dan** tidak ada racikan" → ditolak, supaya tidak lahir kunjungan
tanpa tagihan yang menyumbat antrian kasir. Kasir sudah menagih racikan dari
`kunjungan_racikan` secara terpisah, jadi tidak ada kode tagihan baru.

**Kalau racikan gagal disimpan padahal kunjungan sudah jadi**, apoteker diberi pesan
eksplisit berisi nomor kunjungan dan diminta void lalu ulangi — bukan didiamkan. Menelan
error di sini berarti pasien membayar tagihan yang kurang.

**Bug saat uji coba: racikan lenyap tanpa error.** Kunjungan dan obat tersimpan, racikan
tidak, tagihan kurang, tidak ada pesan apa pun. Sebabnya: `save_kunjungan_racikan` hanya
**FLUSH**, tidak commit — di alur SOAP dokter commit-nya menumpang penyimpanan SOAP
sesudahnya. Di alur apotek tidak ada yang menyusul. **Pola berulang yang sama lagi:** satu
fungsi dipakai dua pemanggil dengan asumsi transaksi yang berbeda. Kalau nanti ada
pemanggil ketiga `save_kunjungan_racikan`, periksa dulu siapa yang commit.

**Yang BELUM dibangun (sadar, bukan lupa):** `TEBUS_LANJUT` tidak menyalin racikan dari
kunjungan lama — ia hanya menyalin baris `kunjungan_resep`. Racikan hidup di tabel
`kunjungan_racikan` yang belum punya penanda asal (`id_kunjungan_racikan_asal`), jadi
anti-tebus-ganda-nya belum ada. Kartunya karena itu **disembunyikan dan dikosongkan**
saat mode resep lama dipilih, dan server pun mengabaikannya — supaya tidak ada isian
yang diam-diam hilang. Kalau nanti dibutuhkan, polanya sama dengan `id_resep_asal`.

## 11. R8 — "Beli separuh di kasir" (ditemukan 2026-09-27, belum dibangun)

Ditemukan saat dr. Hansen bertanya "di mana saya bisa gunakan tebus resep sebagian?".
Jawabannya membuka lubang: yang sudah dibangun menangani **"pasien pulang tanpa membayar
sama sekali, lalu kembali"** — BUKAN **"beli separuh di meja kasir"**. Keduanya terdengar
mirip tapi terjadi di tempat dan waktu berbeda, dan yang kedua jauh lebih sering.

**Keadaan sekarang**: kasir menagih SEMUA item PENDING kunjungan sekaligus. Satu-satunya
tindakan per item adalah `void_item_resep` → `BATAL`, **permanen**. Jadi untuk pasien yang
mau dua dari lima obat, kasir hanya punya dua pilihan dan keduanya salah: menagih semuanya,
atau membatalkan sisanya selamanya.

**Yang kurang**: di layar tagihan kasir, tiap item butuh pilihan **"sisakan untuk nanti"** —
dikeluarkan dari tagihan hari ini tapi TIDAK dibatalkan, sehingga otomatis muncul di daftar
"Tebus resep lama" yang sudah jadi.

**Arah**: status baru `DITUNDA` pada `kunjungan_resep.status_item` (enum sudah pernah
ditambah untuk `DISERAHKAN`, polanya sama — MySQL perlu MODIFY COLUMN dengan daftar
lengkap). `get_tagihan` hanya mengambil PENDING → DITUNDA otomatis keluar dari tagihan.
`list_resep_belum_ditebus` perlu menerima PENDING **dan** DITUNDA.
⚠ Seperti biasa: setiap query yang mengasumsikan "PENDING = belum dibayar" harus ditinjau,
karena kini ada dua status yang berarti belum dibayar.

**Keputusan dr. Hansen 2026-09-27**: kerjakan **setelah R6–R7**, supaya modul yang sekarang
utuh dulu.

## 10. Risiko yang disadari

**Obat keluar sebelum dokter menyetujui** (keputusan #10). Dasarnya masuk akal: keputusan
meresepkan sudah dibuat dokter lewat chat, dan SOAP hanya pencatatan yang menyusul. Tapi
kalau dokter kemudian menyanggah isi draf, obatnya sudah terlanjur diserahkan. Peredamnya
adalah draf itu sendiri — ia memaksa apoteker menuliskan apa yang dia pahami dari
percakapan, dan dokter membacanya. Selisih paham muncul di layar, bukan di ingatan.

**Antrian draf yang menumpuk** tetap jadi tanda bahaya. Kalau dokter jarang menyetujui,
artinya obat keras keluar dengan rekam medis yang tidak pernah rampung — persis lubang
yang mekanisme ini dibuat untuk menutup. Yang perlu dipantau bukan lagi "apakah SOAP ada",
melainkan **berapa lama draf menunggu**. Kalau umurnya rutin berhari-hari, keputusan #10
sebaiknya ditinjau ulang.

**Bukti percakapan tidak disimpan di sistem — dan itu disengaja.** Draf berisi tafsiran
apoteker atas chat, bukan chat itu sendiri. Lapis buktinya ada di **arsip fisik apotek**
(wajib Dinkes/BPOM), bukan di EMR. Yang perlu diingat: ini berarti sistem dan arsip harus
tetap sejalan — kalau apotek berhenti mengarsipkan, lubangnya kembali terbuka tanpa ada
gejala apa pun di layar. **Kesinambungan arsip fisik adalah asumsi desain ini**, bukan hal
yang dijamin oleh kode.
