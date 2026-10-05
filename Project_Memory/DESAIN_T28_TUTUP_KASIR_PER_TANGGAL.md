# DESAIN — T28: tutup kasir per tanggal + peringatan uang di luar jendela shift

Status: **DIKERJAKAN 2026-10-05** (desktop; `tests/integration/test_tutup_kasir_per_laci.py`, 6 test) · **DISETUJUI dr. Hansen 2026-10-05** — jawaban §5: (1) **SATU laci** → rancangan 3a; (2) sesi kedua di hari yang sama DITOLAK; (3) uang sesudah tutup cukup diperingatkan, angka tutup kasir tidak diubah.
Asal: `AUDIT_ALUR_UANG_2026-10-04.md` Temuan 28.

## 1. Keputusan yang sudah ada

- Uang di luar jam shift **tetap dihitung** → hitung per **tanggal**, plus **peringatan**.
- Klinik hanya punya **satu shift kasir per hari** (dr. Hansen 2026-10-05).

## 2. Keadaan sekarang (dibaca dari kode)

`kasir_closing_service._penjualan_per_metode`:

```
WHERE transaksi_kasir.id_staf_kasir = <kasir pemilik sesi>
  AND waktu_bayar >= shift_mulai            -- tanpa batas atas
  AND status_transaksi = 'BAYAR'
```

Jadi hitungan tutup kasir **per ORANG** dan **sejak jam buka**. Dua celah:

| Celah | Akibat |
|---|---|
| **Jam** (Temuan 28) | Bayar sebelum `buka_kasir` ditekan, atau sesudah tutup → tidak masuk sesi mana pun. Uangnya ada di laci → muncul sebagai selisih lebih yang tak bisa dijelaskan |
| **Orang** (baru terlihat 2026-10-05) | Pembayaran yang diproses staf yang **tidak membuka sesi sendiri** tidak masuk hitungan siapa pun. Yang berhak membayar: Kasir, **Admin, Owner, Superadmin** (`KASIR_ROLES`). Di DB dev 21 transaksi diproses `hansen` (Superadmin). ⚠ **KOREKSI:** rancangan awal menyebut "petugas FO (4)" — keliru. Keempat transaksi itu ditulis langsung oleh skrip seed/test (`id_staf_kasir = FO`), melewati pagar peran; FO **tidak** berhak membayar lewat UI. Celahnya tetap nyata lewat Admin/Owner/Superadmin |

`proses_bayar` tidak menuntut sesi terbuka (by design: jangan blokir antrian).

## 3. Rancangan

### 3a. Satu sesi per laci per hari (kalau §5 jawaban "satu laci")

- Expected = **semua** pembayaran `BAYAR` dengan `DATE(waktu_bayar) = tanggal sesi`,
  **siapa pun yang memprosesnya**, dikurangi refund ber-`tgl_refund` di tanggal itu
  (lewat `_refund_bukuan`, sama dengan laporan omzet sejak T32).
- Tampilan tutup kasir menambah **rincian per petugas** (siapa memproses berapa) —
  supaya selisih tetap bisa ditelusuri ke orang, walau lacinya satu.
- `buka_kasir` menolak sesi kedua di **tanggal yang sama** (bukan hanya per orang).
  ⚠ Ini mengubah perilaku: hari ini dua orang bisa membuka sesi masing-masing.

### 3b. Peringatan jendela

Saat preview & tutup: daftar pembayaran (dan refund) di tanggal itu yang
`waktu_bayar < shift_mulai` — "masuk sebelum kasir dibuka". Ditampilkan sebagai
kotak kuning berisi jam, nomor transaksi, petugas, nominal. **Tetap dihitung**;
peringatan hanya menjelaskan, tidak memblokir.

(Pembayaran sesudah tutup di hari yang sama: masuk tanggal itu tapi sesinya sudah
CLOSED. Usul: halaman Tutup Kasir menampilkan "ada Rp X masuk SESUDAH ditutup" pada
sesi yang sudah CLOSED, dan laporan closing harian memuatnya. Angka tutup kasir yang
sudah ditandatangani **tidak diubah** — sejalan dengan prinsip T32.)

### 3c. Tutup kasir lewat tengah malam

Dengan satu shift per hari jarang terjadi, tapi mungkin (lupa tutup). Usul: tanggal
sesi = `DATE(shift_mulai)`; menutup sesi kemarin tetap menghitung **tanggal kemarin**
saja, dan halaman memperingatkan "sesi tanggal X belum ditutup" saat membuka kasir
hari berikutnya.

## 4. Tanpa migrasi

Semua dari kolom yang sudah ada (`shift_mulai`, `waktu_bayar`, `tgl_refund`,
`id_staf_kasir`). `detail_metode` (JSON) menampung rincian per petugas.

## 5. Pertanyaan untuk dr. Hansen

1. **Laci kasir di klinik satu atau lebih?** Kalau satu (dan FO/Owner/Admin juga
   memproses bayar dari laci yang sama) → rancangan 3a. Kalau tiap petugas pegang
   laci/rekening sendiri → tetap per orang, hanya celah jam yang ditambal.
2. Setuju `buka_kasir` ditolak kalau hari itu sudah ada sesi (siapa pun yang membuka)?
3. Pembayaran sesudah kasir ditutup: cukup ditampilkan sebagai peringatan pada sesi
   yang sudah tutup (angkanya tidak diubah) — setuju?

## 6. Uji yang direncanakan (dua arah)

- Bayar 12:38 sebelum `buka_kasir` 13:38 → kode lama: tidak terhitung; baru: terhitung
  + muncul di peringatan.
- Bayar diproses petugas FO, sesi dibuka kasir → lama: tidak terhitung; baru: terhitung
  di rincian petugas FO.
- Refund hari ini atas transaksi kemarin → mengurangi expected hari ini.
- Sesi kedua di hari yang sama → ditolak.
- Selisih = 0 pada skenario normal (tidak ada peringatan palsu).
