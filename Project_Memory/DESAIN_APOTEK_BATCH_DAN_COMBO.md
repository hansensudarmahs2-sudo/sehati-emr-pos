# DESAIN — Konversi batch & Combo obat (apotek)

Tanggal: 2026-09-30. Status: **rancangan, BELUM dibangun.** Konteks dari dr. Hansen
berdasarkan praktik apotek yang sedang berjalan.

> Ditulis selagi konteksnya segar, sebelum pindah ke Claude Code. Dua modul BARU yang
> menyentuh **stok dan uang** sekaligus — bukan perbaikan. Jangan dibangun tanpa
> persetujuan ulang dr. Hansen atas rancangan ini.

---

## A. KONVERSI BATCH — apoteker memproduksi stok siap jual

### A.1 Apa yang sebenarnya terjadi

[dr. Hansen] *"mereka meracik formularium obat racik seperti sr sr2 dan sro dalam batch
besar yaitu 100 capsul. jadi apoteker input terpisah atau mereka sebut konversi. stok
produk bahan berkurang tapi tidak ada transaksi dan tab sr-sr2-sro bertambah di stok dan
ready to sell."*

Ini **produksi**, bukan penjualan. Beberapa produk masuk, satu produk keluar. Tidak ada
pasien, tidak ada kunjungan, tidak ada transaksi kasir.

**Bedanya dengan racikan yang sudah ada:** racikan per-resep dibuat untuk SATU pasien,
harganya dikunci di kunjungan, stoknya dipotong saat diserahkan. Konversi batch tidak
punya pasien sama sekali — hasilnya masuk gudang sebagai produk biasa yang bisa dijual
berkali-kali ke siapa pun.

**Jangan memaksakan mesin racikan untuk ini.** `kunjungan_racikan` bergantung pada
`id_kunjungan` yang NOT NULL. Memalsukan kunjungan demi memuat produksi akan mencemari
antrian, laporan, dan komisi — pola "satu tabel dua arti" yang sudah berulang kali
menggigit proyek ini.

### A.2 Bentuk data (usulan)

Tabel baru, sejajar dengan pengadaan — bukan turunan kunjungan:

- `produksi_batch` — id, `id_produk_hasil`, `qty_hasil`, `tgl_produksi`, `id_staf`,
  `ed_hasil`, `catatan`, `status` (DRAFT/SELESAI/BATAL), `hpp_per_unit` (snapshot)
- `produksi_batch_bahan` — id, `id_batch`, `id_produk`, `qty_dipakai`, `id_lot`,
  `hpp_satuan` (snapshot), `subtotal`

**HPP hasil = jumlah HPP bahan ÷ qty hasil.** Ini satu-satunya cara margin SR terbaca
benar saat dijual. Kalau HPP hasil tidak dihitung, laporan margin akan menampilkan SR
sebagai untung 100% — angka yang salah dan meyakinkan.

**Bahan dipotong FEFO**, jejaknya di `id_lot` — pola yang sama dengan
`kunjungan_lot_terpakai`.

**Hasil masuk sebagai LOT BARU** pada `id_produk_hasil`, bukan sekadar menambah
`stok_terkini`. Tanpa lot, ED tidak bisa dilacak dan laporan ED akan melewatkannya.

### A.3 Keputusan dr. Hansen

**ED hasil batch: APOTEKER MENGISI SENDIRI.** Alasannya sah — beyond-use date racikan
mengikuti pedoman farmasi, bukan sekadar ED bahan tercepat.

⚠ **Konsekuensi yang harus ditangani, bukan diabaikan:** kalau kolom ED dibiarkan
opsional, stok hasil produksi bisa lahir tanpa ED dan lolos dari laporan kedaluwarsa.
**ED WAJIB diisi saat batch diselesaikan** — bukan boleh kosong. Kalau apoteker tidak
tahu, itu percakapan SOP, bukan alasan membiarkan kolomnya kosong.

Saran tambahan (perlu persetujuan): tampilkan ED bahan tercepat sebagai **ancar-ancar di
layar**, dan beri peringatan — bukan penolakan — kalau apoteker mengisi ED lebih panjang
daripada bahan tercepat.

### A.4 Yang belum diputuskan

- Apakah batch perlu disetujui dokter/Owner, atau apoteker berwenang penuh?
- Apakah batch bisa dibatalkan setelah selesai (stok hasil sudah terjual sebagian)?
- Formularium baru oleh apoteker — dr. Hansen menyebut *"mungkin ke depannya bisa tambah
  formularium khusus oleh apoteker"*. Siapa yang boleh membuat resep formularium baru?

---

## B. COMBO OBAT — grup dijual dengan harga sendiri

### B.1 Apa yang sebenarnya terjadi

[dr. Hansen] *"ada grup obat yang dijadikan penjualan… saat dokter menambahkan combo ini
maka stok berkurang tapi nilainya mengikuti nilai grup obat itu."*

Dua combo untuk GO:

| Combo | Isi | Harga grup |
|---|---|---|
| **AB Reguler** | 4 azithromycin, 10 cefixime, 10 doxicor, 10 exaflam | **Rp 490.000** |
| **AB Premium** | zibramax, nucef, interdoxin, gofex | **Rp 980.000** |

Harga satuan Reguler kalau dijual eceran: azithro 5.000/butir, cefixime 3.000, doxicor
7.500, exaflam 3.000 → **Rp 155.000**.

### B.2 ATURAN INTI — harga grup BERDIRI SENDIRI

Rp 490.000 vs Rp 155.000: harga grup **tiga kali lipat** harga eceran.

[dr. Hansen 2026-09-30] *"jadi harga grup lebih mahal dari satuan pada kasus ini. tapi
pada kasus lain bisa saja kita manfaatkan untuk lebih murah sebagai bagian dari
bundling."*

**Jadi harga grup BUKAN turunan harga satuan — bukan diskon, bukan markup persentase.**
Ia angka tersendiri yang disetel di master grup. **JANGAN PERNAH menghitungnya ulang dari
isinya**, ke arah mana pun. Kalau nanti ada yang melaporkan "harga combo tidak sama
dengan jumlah isinya" sebagai bug — tunjuk paragraf ini.

### B.3 Keputusan dr. Hansen

**Nota: SATU BARIS "Combo AB Reguler" Rp 490.000.** Isinya tidak dirinci di nota.

⚠ **Konsekuensi yang harus disadari:** combo jadi **semua-atau-tidak sama sekali**. Tidak
ada cara memecah harganya, jadi:
- **R8 "sisakan untuk nanti" TIDAK berlaku per-isi combo.** Yang bisa ditunda adalah
  seluruh combo.
- Void/refund juga seluruh combo.
- Kalau pasien menolak satu obat di dalamnya, jalurnya adalah **tidak memakai combo** dan
  meresepkan satuan — bukan memecah combo.

**Komisi: dari HARGA GRUP, satu kali.** Combo diperlakukan sebagai satu produk untuk
komisi, dengan persen/nominal yang disetel di grup itu sendiri.

⚠ **Jangan menjumlahkan komisi tiap obat di dalamnya.** Karena harga grup berbeda jauh
dari jumlah satuan, komisi per-item akan menghasilkan angka yang tidak sebanding dengan
uang yang benar-benar masuk.

### B.4 Bentuk data (usulan)

- `master_combo` — id, nama, `harga_jual`, `komisi_persen`/`komisi_nominal`, `is_active`
- `master_combo_item` — id, `id_combo`, `id_produk`, `qty`
- `kunjungan_combo` — snapshot saat diresepkan: `nama_snapshot`, `harga_snapshot`,
  `status_item` (pola sama dengan `kunjungan_racikan`), `id_transaksi`, `waktu_serah`,
  `id_staf_serah`
- `kunjungan_combo_item` — snapshot isi + `id_lot` yang terpakai

**Harga di-SNAPSHOT saat diresepkan**, sama seperti racikan. Harga combo berubah besok
tidak boleh mengubah nota lama.

**Stok tetap dipotong per item**, FEFO, dengan jejak lot.

### B.5 Yang belum diputuskan

- Apakah combo boleh diresepkan apoteker lewat layar tebus resep, atau dokter saja?
- HPP combo untuk margin (F3): jumlah HPP item — perlu dipastikan saat modul Finance jalan
- Apakah stok tidak cukup untuk satu item membatalkan seluruh combo? (usulan: ya, blokir
  dengan pesan jelas — combo tidak bisa diserahkan separuh)

---

## C. Titik singgung dengan yang sudah ada

| Yang sudah ada | Harus ditinjau |
|---|---|
| **R8 DITUNDA** | Combo tidak bisa dipecah → hanya seluruh combo yang bisa ditunda |
| **Laporan top produk** | Combo & hasil batch: satuan lagi-lagi berbeda. Ikuti pola racikan — kolom terpisah, jangan dilebur |
| **Laporan apoteker** | Konversi batch BUKAN penyerahan ke pasien — jangan dicampur ke laporan dispensed |
| **Komisi** | Combo satu kali dari harga grup; hasil batch dijual sebagai produk biasa → komisi produk biasa |
| **FEFO & lot** | Dua jalur baru yang memotong stok: produksi batch (bahan) dan combo (item) |
| **#51 halaman basi** | Kalau combo ikut disimpan dari SOAP, ia butuh perlakuan `loaded_ids` yang sama |

---

## D. Urutan yang disarankan

1. **Combo lebih dulu.** Aturannya lebih sederhana (satu harga, satu baris, satu komisi),
   dan langsung dipakai harian untuk GO.
2. **Konversi batch menyusul.** Ia menyentuh HPP, lot, dan ED — lebih banyak yang bisa
   salah diam-diam, dan salahnya baru ketahuan berbulan-bulan kemudian lewat laporan
   margin.

**Keduanya butuh migrasi skema → minta persetujuan dr. Hansen sebelum dieksekusi.**
