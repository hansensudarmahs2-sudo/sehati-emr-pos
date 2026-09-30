# DESAIN #51 — Halaman SOAP basi menghapus data yang lahir sesudahnya

Tanggal: 2026-09-30. Status: **SELESAI & teruji** — 11/11 pemeriksa otomatis
(`scripts/cek_soap_basi.py`) + uji ujung-ke-ujung di UI oleh dr. Hansen (langkah 1–5 lolos).

## 1. Gejala

Simpan SOAP dari halaman yang sudah basi (tab lama, tablet lain, dokter lain) **menghapus
racikan PENDING dan diagnosa yang dibuat belakangan**, tanpa peringatan apa pun.

Gejala sampingan yang sudah tercatat sejak 2026-09-21: **ID racikan PENDING berubah setiap
kali SOAP disimpan.** Itu bukan keanehan terpisah — itu sidik jari dari sebabnya.

## 2. Sebab

Saat halaman SOAP dimuat, tiap racikan tersimpan dirender menjadi kartu dengan **token acak
baru** (`uuid4().hex[:10]` di `dokter.py::_racik_prefill`). Tautan ke
`id_kunjungan_racikan` **hilang di situ**. Karena kartu tidak lagi tahu ia berasal dari
baris mana, satu-satunya cara menyimpan adalah **hapus semua lalu tulis ulang** dari apa
yang kebetulan ada di layar.

Halaman basi punya kartu lebih sedikit. Maka "tulis ulang" berarti "hapus yang tidak
kulihat" — termasuk yang lahir setelah halaman itu dimuat.

## 3. Hasil pemeriksaan ketiga blok (2026-09-30)

| Blok | Perilaku simpan | Kelas bug ini? |
|---|---|---|
| **Racikan** (`RacikanService.save_kunjungan_racikan`) | `DELETE` semua baris **PENDING** → tulis ulang | **Ya** |
| **Diagnosa** (`DiagnosaService.save_kunjungan_diagnosa`) | `DELETE` **SEMUA** baris kunjungan, **tanpa saringan status apa pun** → tulis ulang | **Ya, lebih parah** |
| **Resep produk** (`PemeriksaanService`) | Hanya `INSERT`, tidak pernah menghapus | **Tidak** |

**Diagnosa lebih rawan daripada racikan.** Racikan setidaknya melindungi baris
DIBAYAR/BATAL/DITUNDA. Diagnosa tidak punya pengaman sama sekali. Tidak menyangkut uang,
tapi ini rekam medis — diagnosa yang hilang tidak meninggalkan jejak bahwa ia pernah ada.

**Resep produk aman dari kelas bug ini**, justru karena tidak pernah menghapus. Tapi itu
memunculkan pertanyaan BERBEDA yang **belum diverifikasi**: apakah menyimpan SOAP dua kali
menggandakan baris resep? Sengaja **tidak** dicampur ke #51 — pertanyaannya beda (duplikat,
bukan hilang) dan pemecahannya kemungkinan beda juga. Dicatat sebagai pemeriksaan terpisah.

## 4. Rancangan — tanpa migrasi, tanpa ubah skema

Prinsipnya: **jangan menghapus apa yang tidak pernah kamu lihat.**

1. **Kartu membawa identitasnya.** Tiap kartu racikan hasil prefill menyimpan
   `id_kunjungan_racikan` asalnya di field tersembunyi; kartu baru mengirim nilai kosong.
   Hal yang sama untuk chip diagnosa (`id_kunjungan_diagnosa`).
2. **Form membawa daftar apa yang terlihat saat halaman dimuat** — `racik_loaded_ids` dan
   `dx_loaded_ids`.
3. **Saat simpan:**
   - `dikirim` = id yang dibawa kartu (yang tidak kosong)
   - **yang dihapus = `loaded_ids − dikirim`** → hanya yang memang dibuang dokter di layar ini
   - baris di DB yang **tidak ada di `loaded_ids`** → lahir setelah halaman dimuat →
     **JANGAN DISENTUH**
   - kartu ber-id → **perbarui** baris itu (id head dipertahankan)
   - kartu tanpa id → sisipkan baru
4. **Beri tahu, jangan diam.** Kalau ada baris asing yang dipertahankan, dokter diberi
   pesan setelah simpan: "N racikan/diagnosa yang dibuat di tempat lain dipertahankan."
   Menyelamatkan data diam-diam tetap membingungkan kalau dokter mengira layarnya adalah
   kebenaran.

**Pagar lama TIDAK dicabut.** Baris DIBAYAR/BATAL/DITUNDA tetap tak boleh disentuh
(alasannya di `DESAIN_RESEP_LUAR_APOTEK.md` §12 dan komentar `dokter.py`).

## 5. Manfaat sampingan

ID racikan PENDING berhenti berubah tiap simpan. Jejak audit jadi masuk akal: satu racikan
= satu baris dengan satu identitas sepanjang hidupnya, bukan baris baru tiap kali dokter
menekan Simpan.

## 6. Yang harus diperiksa saat membangun

- `dokter.py::_racik_prefill` — sumber hilangnya identitas.
- `RacikanService.save_kunjungan_racikan` — jangan sampai pagar PENDING-saja ikut rusak
  saat logikanya diganti. **R8 bergantung padanya**: baris DITUNDA selamat justru karena
  saringan itu.
- `DiagnosaService.save_kunjungan_diagnosa` — tambahkan konsep `loaded_ids` yang sekarang
  sama sekali tidak ada.
- Mode "Ubah Konsul" memakai jalur simpan yang sama — uji di kedua mode.

## 7. Uji terima

1. Buka SOAP di dua tab. Tab A tambah racikan X, simpan. Tab B (dibuka sebelum X ada)
   simpan → **X harus tetap ada**, dan dokter diberi tahu.
2. Sama untuk diagnosa.
3. Dokter menghapus racikan/diagnosa di layar lalu simpan → **benar-benar terhapus**
   (jangan sampai perbaikan ini membuat penghapusan yang sah jadi mustahil).
4. Simpan dua kali tanpa perubahan → **ID racikan TIDAK berubah**, jumlah baris tetap.
5. Racikan DIBAYAR/DITUNDA/BATAL tetap tak tersentuh di semua skenario di atas.

## 8. Pemetaan tabrakan lain — diperiksa 2026-09-30

dr. Hansen bertanya apakah pola Sehati mencegah tabrakan kasir-vs-dokter yang **nyata
terjadi** di Omnicare: dokter menyunting SOAP sementara kasir menginput transaksi, lalu
salah satu input hilang.

Diperiksa di kode, bukan disimpulkan:

| Skenario | Sehati | Bukti |
|---|---|---|
| Kasir menimpa anamnesa dokter | **Mustahil** | `kasir_service` & `routes/kasir.py` **nol** referensi ke `pemeriksaan_klinis` |
| Dokter menghapus input kasir | **Mustahil** | `pemeriksaan_service` **tidak punya satu pun** operasi hapus; racikan DIBAYAR dipagari |
| Dokter kedua menimpa dokter pertama | **Ditolak 403** | `pemeriksaan_service.py:116` — hard block assign FO (Owner exempt) |
| Racikan/diagnosa hilang karena halaman basi | **Ditutup oleh #51** | dokumen ini |

**Sebabnya arsitektural.** Omnicare tampak menyimpan satu kunjungan sebagai satu rekaman
utuh, jadi siapa pun yang menekan Simpan menimpa seluruh isinya — yang terakhir menang.
Sehati menulis **per blok ke tabel terpisah** dengan pemilik masing-masing. Kasir secara
harfiah tidak punya jalan menulis anamnesa. Karena itu Sehati tidak butuh tombol "tarik
data terbaru" yang justru menghilangkan input pihak lain.

**Catatan koreksi diri:** saya sempat mengangkat "dua dokter bisa saling menimpa teks
SOAP" sebagai celah terbuka. **Salah** — dr. Hansen sudah mengujinya dan pagar 403 itu
memang ada; saya mengangkatnya sebelum memeriksa. Pola kesalahan yang sama berulang
sepanjang sesi ini: **menyimpulkan sebelum membuka kodenya.**

**Sisa yang benar-benar terbuka (sempit, sengaja tidak dikerjakan sekarang):**
- **Satu dokter, dua layar** (tablet + desktop). Pagar 403 membandingkan *siapa dokternya*,
  bukan *layar mana*, jadi teks anamnesa masih yang-terakhir-menang. Baru relevan kalau
  alur mobile perawat/dokter di backlog dibangun.
- **Owner bisa override** pagar assign — disengaja, tapi berarti Owner yang menyimpan dari
  layar basi bisa menimpa.

## 9. Duplikat resep — DIPERIKSA & AMAN (2026-09-30)

Pertanyaan yang saya buka sendiri: resep hanya INSERT, tidak pernah dihapus — apakah
menyimpan SOAP dua kali menggandakannya? **Tidak.** Dua lapis melindunginya:

1. **POST-Redirect-GET.** Rute simpan mengembalikan 303 ke `/web/dokter/antrian`. Back
   tidak mengulang POST; ia kembali ke form lewat GET yang dirender ulang.
2. **`<div id="resep-rows">` selalu KOSONG.** Baris resep hanya lahir saat dokter menekan
   "+ Tambah Resep" di sesi halaman itu. Blok "Resep sebelumnya" punya NOL input — murni
   tampilan. Halaman yang dimuat ulang tidak membawa baris resep untuk dikirim.

Diuji dr. Hansen di dua tab (satu incognito): simpan → Back → simpan ulang, dan dua tab
simpan hampir bersamaan. **Tidak ada duplikat.**

Sisa yang tidak tercakup uji itu: klik-ganda sangat cepat dalam SATU tab yang berisi baris
resep. Sempit; penutupnya remeh (nonaktifkan tombol saat submit). Belum dikerjakan.

## 10. Catatan cara kerja — untuk sesi berikutnya

Sepanjang 2026-09-30 saya **tiga kali** mengangkat risiko sebelum memeriksanya, dan
ketiganya dipatahkan dr. Hansen dengan pengujian: (a) pagar "tagihan kosong" saya sebut
salah — ternyata benar; (b) "dua dokter bisa saling menimpa teks SOAP" — ternyata sudah
dipagari 403 di `pemeriksaan_service.py:116`; (c) "kirim-ganda menggandakan resep" —
ternyata dicegah POST-Redirect-GET.

Polanya sama: membaca satu bagian kode, melihat sesuatu yang BISA salah, lalu
melaporkannya seolah MEMANG salah. **Periksa dulu, baru bicara.** Ini disiplin yang sama
yang dituliskan di dokumen-dokumen ini untuk orang lain.
