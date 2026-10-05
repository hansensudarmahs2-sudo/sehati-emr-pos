# DESAIN — T27: nota dari yang DITAGIH, tindakan kuota sebagai benefit prabayar

Status: **DIKERJAKAN 2026-10-05** (desktop; `tests/integration/test_nota_snapshot.py`, 5 test; sesi series Rp 0 ikut dibingkai "Paket series (prabayar)") · **DISETUJUI dr. Hansen 2026-10-05** — §5 setuju semua: tampilan 3b ("Benefit <tier> (prabayar) · nilai normal"), penanda "direkonstruksi" untuk transaksi lama, versi pendek di thermal.
Asal: `AUDIT_ALUR_UANG_2026-10-04.md` Temuan 27 + §"VERIFIKASI DESKTOP".

## 1. Masalah (dibaca dari kode)

`PrintService.prepare_nota_context`:

| | Sumber sekarang |
|---|---|
| Baris tindakan | `MasterTreatment.harga` — **harga hari ini** |
| Baris obat | `MasterProduk.harga_jual` — **harga hari ini** |
| Baris racikan | `TransaksiDetailRacikan` — snapshot ✓ |
| Total | `transaksi_kasir.total_tagihan` |
| Pemilihan baris | per `id_kunjungan`, bukan per `id_transaksi` |

Akibat: (a) tindakan kuota tercetak **Rp 500.000 dengan total Rp 0**, ditambal baris
"Benefit Member −Rp 500.000"; (b) nota cetak-ulang berubah kalau harga master naik;
(c) dugaan: pada split billing satu nota bisa memuat baris transaksi lain.

## 2. Arah yang diusulkan dr. Hansen

Tindakan kuota dibingkai sebagai **hak yang sudah dibayar di muka**, bukan diskon.

## 3. Rancangan

### 3a. Baris dari snapshot transaksi ini

| Lini | Sumber baru | Kunci |
|---|---|---|
| Tindakan | `transaksi_detail_tindakan` (`harga_satuan`, `diskon_item`, `subtotal`) | `id_transaksi` |
| Obat | `transaksi_detail_produk` (`harga_satuan`, `subtotal`) | `id_transaksi` |
| Racikan | `transaksi_detail_racikan` (tetap) | — |

Memilih per `id_transaksi` sekaligus menutup dugaan (c).

### 3b. Tindakan kuota

```
Basic Treatment                      1×        Rp 0
   ↳ Benefit VVIP (prabayar) · nilai normal Rp 500.000
─────────────────────────────────────────────────────
Subtotal                                       Rp 0
TOTAL                                          Rp 0

Nilai benefit membership terpakai hari ini:  Rp 500.000
```

- Baris yang DITAGIH menunjukkan Rp 0 — angka yang benar-benar dibayar.
- Baris "Benefit Member −Rp X" di blok total **dihapus**: tidak ada lagi yang dikurangi.
- "Nilai normal" diambil dari harga master **saat cetak** dan diberi label "nilai
  normal" — informasi, bukan tagihan. (Snapshot harga normal tidak disimpan saat bayar;
  menyimpannya butuh kolom baru → di luar rancangan ini.)
- Ringkasan "nilai benefit terpakai" di bawah TOTAL, sebagai pengingat manfaat member.
- Bagian "Benefit Terpakai" (tier + periode) yang sudah ada tetap dipakai.

### 3c. Transaksi LAMA tanpa snapshot

`transaksi_detail_tindakan` baru ditulis sejak F3 (kerja 4 Okt) — **belum ada di mini
PC**. Jadi SEMUA transaksi klinik yang sudah ada tidak punya baris itu.

Usul: kalau transaksi tidak punya snapshot tindakan, nota memakai cara lama (harga
master, per kunjungan) **dan menandainya**: *"Rincian direkonstruksi dari harga saat
ini — transaksi sebelum <tanggal deploy>."* Nota tidak pernah diam-diam mencampur dua
sumber tanpa keterangan.

Obat sudah punya snapshot sejak lama (`transaksi_detail_produk`), jadi fallback hanya
untuk tindakan.

### 3d. Total tetap dari transaksi

`TOTAL` = `total_tagihan` (− refund, sejak T32). Karena baris kini dari snapshot yang
sama dengan yang membentuk total, **jumlah baris − diskon = TOTAL** — pemeriksa baru
menjaga kesamaan itu (dua arah).

## 4. Tanpa migrasi

## 5. Pertanyaan untuk dr. Hansen

1. Tampilan 3b (Rp 0 + "nilai normal" + ringkasan benefit) — setuju, atau ada kata
   yang lebih pas untuk pasien ("ditanggung paket", "prabayar", "benefit")?
2. Transaksi lama: tandai "direkonstruksi" (3c) — setuju?
3. Thermal 58mm sempit: baris "↳ Benefit…" dipendekkan jadi "↳ Benefit VVIP · normal 500.000"?

## 6. Uji yang direncanakan (dua arah)

- Tindakan kuota: lama → baris 500.000 / total 0; baru → baris 0, nilai normal tertulis.
- Harga master dinaikkan 2× sesudah bayar: lama → baris nota berubah; baru → tetap.
- Transaksi tanpa snapshot: tercetak dengan penanda "direkonstruksi".
- Jumlah baris − diskon = TOTAL untuk semua transaksi ber-snapshot di DB dev.
