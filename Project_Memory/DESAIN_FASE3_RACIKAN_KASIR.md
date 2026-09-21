# Desain Fase 3 Racikan — Kasir, Apotek, Stok Bahan

Status: **DISETUJUI (keputusan bisnis), BELUM DIBANGUN**
Tanggal: 2026-09-21
Prasyarat: Fase 1 (Formula + kalkulator) & Fase 2 (Kartu Racik di SOAP, snapshot harga) sudah live, head `20260921_0200`.

---

## 1. Masalah yang diselesaikan

Setelah Fase 2, dokter bisa membuat racikan dan harganya terkunci di `kunjungan_racikan` / `kunjungan_racikan_bahan`. Tetapi:

- **Kasir tidak pernah membacanya** → racikan tidak masuk tagihan. Pasien tidak tertagih.
- **Apotek tidak pernah memotong stok bahannya** → stok bahan racikan tidak pernah berkurang.
- Akibatnya **task #40 (matikan 4 produk RACIKAN flat `OBM-068..071`) belum boleh jalan.** Gerbangnya adalah Fase 3 ini, bukan Fase 2 seperti tertulis sebelumnya.

## 2. Keputusan dr. Hansen (2026-09-21)

| Topik | Keputusan | Konsekuensi |
|---|---|---|
| **Diskon member** | Berlaku untuk **seluruh total racikan** (bahan **dan** ongkos racik) | Ongkos racik ikut terdiskon. Margin jasa tergerus untuk member — diterima demi konsistensi di mata pasien. Dipakai bucket `persen_produk`. |
| **Komisi dokter** | **Dari bahan saja**, memakai `komisi_dokter_tipe/value` tiap produk bahan | Sama persis dengan resep biasa. Ongkos racik TIDAK masuk dasar komisi. |
| **Edit SOAP pasca-bayar** | Racikan berstatus `DIBAYAR` **dikunci** | Tidak bisa diubah/dihapus dokter. Dokter hanya boleh menambah racikan baru → jadi tagihan tambahan (FLOW-D Part B). |

## 3. Bug & lubang yang WAJIB dipagari lebih dulu

### 3a. Replace-all menghapus racikan yang sudah dibayar — RISIKO TAGIH GANDA
`racikan_service.save_kunjungan_racikan` menghapus **semua** racikan kunjungan lalu menulis ulang. Kalau dokter menyunting SOAP setelah pasien bayar, racikan yang sudah `DIBAYAR` ikut terhapus dan lahir lagi sebagai baris `PENDING` baru → tertagih dua kali, dan jejak transaksi lamanya putus.

**Perbaikan**: `save_kunjungan_racikan` hanya boleh menghapus baris berstatus `PENDING`. Baris `DIBAYAR`/`BATAL` dipertahankan apa adanya, dan kartu racik di SOAP merendernya **read-only** (tanpa field input, tanpa tombol hapus).

### 3b. Kunjungan racikan-saja tidak pernah masuk antrian apotek
`proses_bayar` menentukan status berikutnya hanya dari jumlah resep produk yang ter-update. Kunjungan yang isinya racikan saja langsung `COMPLETED` → tidak pernah diserahkan, stok bahan tidak pernah keluar.

**Perbaikan**: status berikutnya = `ANTRI_OBAT` bila **(resep produk DIBAYAR > 0) ATAU (racikan DIBAYAR > 0)**.

### 3c. Mismatch checkbox reverse stok (sudah ada sebelum racikan)
Modal force-void mengirim `id_resep`, sementara `_reverse_stok_per_item` memfilter `TransaksiDetailProduk.id_detail`. Menambah racikan ke daftar yang sama akan memperparah.

**Perbaikan**: beri namespace pada nilai checkbox (`PRD:<id_detail>` / `RCK:<id_kunjungan_racikan>`) dan parse di service.

### 3d. `transaksi_detail_produk.id_produk` NOT NULL
Racikan tidak punya satu `id_produk`. **Jangan** memaksakan racikan ke tabel ini — akan merusak reverse stok, suggested order, riwayat pasien, dan export.

**Perbaikan**: tabel detail sendiri, `transaksi_detail_racikan` (lihat §4).

### 3e. Proxy "stok sudah dipotong" memakai `status_antrian == COMPLETED`
Dengan dua jalur serah (produk & racikan) proxy ini bisa salah. **Perbaikan**: andalkan jejak `kunjungan_lot_terpakai` per item, bukan status kunjungan.

### 3f. `KunjunganRacikanBahan.id_produk` nullable
Kode pemotongan stok harus mentolerir NULL (bahan non-inventori) — lewati, jangan error.

## 4. Skema baru (migrasi `20260921_0300`)

`transaksi_detail_racikan` — snapshot baris tagihan racikan, supaya nota & reprint tidak bergantung pada tabel sumber yang bisa berubah:

| Kolom | Tipe | Catatan |
|---|---|---|
| `id_detail_racikan` | INT PK | |
| `id_transaksi` | FK transaksi_kasir | |
| `id_kunjungan_racikan` | FK kunjungan_racikan | |
| `nama_snapshot` | VARCHAR(100) | |
| `jenis_racik` | VARCHAR(20) | |
| `jumlah_unit` | INT | |
| `subtotal_bahan` | DECIMAL(12,2) | |
| `biaya_racik` | DECIMAL(12,2) | |
| `diskon_item` | DECIMAL(12,2) | diskon member yang benar-benar dikenakan |
| `subtotal` | DECIMAL(12,2) | total setelah diskon |
| `void_reverse_stok` | BOOLEAN | sejajar `transaksi_detail_produk` |

Ditambah kolom `id_transaksi` (nullable, FK) di `kunjungan_racikan` supaya jejak "racikan ini ditagih di transaksi mana" bisa ditelusuri dua arah.

## 5. Titik sisip (urut kerja)

1. **Guard replace-all** — `racikan_service.save_kunjungan_racikan`: hanya hapus `PENDING`.
2. **SOAP read-only** — `dokter_soap_form.html`: racikan `DIBAYAR` tampil sebagai ringkasan terkunci, bukan kartu yang bisa disunting.
3. **Migrasi `20260921_0300`** — `transaksi_detail_racikan` + `kunjungan_racikan.id_transaksi`.
4. **Schema** — `RincianRacikan` + `rincian_racikan` di `TagihanResponse`, `subtotal_racikan` di `RingkasanBiaya`.
5. **Repo** — `get_racikan_pending_for_billing`, `mark_racikan_dibayar`.
6. **`get_tagihan`** — kumpulkan racikan; deteksi item baru pakai `created_at > cutoff`; diskon `persen_produk` dikenakan ke **total racikan**.
7. **`proses_bayar`** — tulis `transaksi_detail_racikan`, tandai `DIBAYAR`, perbaiki penentuan `ANTRI_OBAT`.
8. **Komisi** — loop terpisah atas bahan racikan (bukan `rincian_produk`, yang tidak punya `id_produk`).
9. **Apotek** — antrian & detail resep menyertakan racikan; `serahkan_obat` memotong stok tiap bahan (FEFO + `_simpan_lot_terpakai`); obat-tertunda mengenali kunjungan racikan-saja.
10. **Void** — cascade racikan `DIBAYAR`→`BATAL`; reverse stok bahan dari `kunjungan_racikan_bahan.dipakai` + jejak lot.
11. **UI** — kartu "⚗️ Racikan" di `kasir_tagihan.html` (tiru blok produk), baris ringkasan, checkbox reverse ber-namespace.
12. **Nota** — tipe item `"RCK"` di `print_service`.
13. **SETELAH semua live & teruji** — task #40: nonaktifkan `OBM-068..071`.

## 6. Yang TIDAK dikerjakan di Fase 3

- Etiket racikan (label tempel) — terpisah, menyusul.
- PPN: kolom `dpp/ppn/is_kena_ppn` tetap dormant; tidak ada pajak per item di mana pun saat ini.
- Kasir menambah item sendiri — task #41, ditunda atas keputusan dr. Hansen.

## 7. Uji terima (desktop dulu, lalu mini PC)

1. Kunjungan **racikan saja** → bayar → masuk `ANTRI_OBAT` → serah → stok tiap bahan berkurang sesuai `dipakai` → `COMPLETED`.
2. Kunjungan **campuran** (tindakan + resep + racikan) → tiga kelompok tampil di kasir, total benar.
3. **Pasien member** → diskon kena ke seluruh total racikan.
4. **Komisi dokter** tercatat per bahan, ongkos racik tidak ikut.
5. **Edit SOAP pasca-bayar** → racikan lama terkunci; racikan baru muncul sebagai tagihan tambahan, yang lama tidak tertagih ulang.
6. **Void** → stok bahan kembali, racikan jadi `BATAL`.
7. Nota cetak menampilkan racikan beserta ongkos raciknya.
