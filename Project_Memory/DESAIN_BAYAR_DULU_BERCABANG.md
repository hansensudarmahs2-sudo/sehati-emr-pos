# Rancangan — Bayar dulu, tindakan & obat urutan bebas

Status: **DISETUJUI dr. Hansen 2026-10-15** (ditulis 2026-10-15). **TAHAP 1 SELESAI 2026-10-21** (dev; commit fe62830..8367784 + T1-8, 8 task, `RENCANA_BAYAR_DULU_TAHAP1.md`;
belum di mini PC). Tahap 2 (menagih tindakan yang belum selesai) belum dikerjakan.
Penyempurnaan selama pengerjaan: klarifikasi §3.2 (Ruling 6 & 7: transaksi VOID tetap berarti kasir sudah
menangani; "tidak disentuh" hanya bila tanpa SOAP, isi, dan transaksi), §3.3 (Ruling 10: antrian perawat juga
menampilkan label KONSULTASI — pintu ke form upsell). Lihat DEC-101.
Asal: Audit T4-4 (`AUDIT_MENDALAM_2026-10-13.md`). Disetujui per bagian dalam percakapan
2026-10-15; dokumen ini merangkumnya untuk dibaca utuh sebelum rencana pengerjaan ditulis.

⚠ **Membalik DEC-050** ("Opsi A multi-status concurrent" ditolak karena melanggar aturan satu
status). Keputusan baru: satu kunjungan boleh ditangani perawat dan apotek bersamaan; status
kunjungan menjadi RINGKASAN, bukan penentu antrian. DEC-015 (ON_TREATMENT → COMPLETED tanpa
kasir) menjadi tidak perlu — lihat §3.3.

---

## 1. Tujuan

Kata dr. Hansen: *"sistem yang tidak rigid tapi tetap terstruktur dan aman."* Pembayaran
boleh terjadi sesudah tindakan (SOP biasa) **atau** sesudah konsultasi; keduanya sah dan
frekuensinya bervariasi.

- Pasien selesai konsultasi boleh membayar tindakan + obat lebih dulu.
- Sesudah bayar, tindakan dan ambil obat boleh urutan bebas.
- Kunjungan baru selesai bila tidak ada lagi yang menggantung.
- Obat lupa diambil → apotek menyerahkan belakangan (obat tertunda — sudah ada).
- Tindakan lunas tapi tidak dikerjakan → **hak pasien** (dipakai di kunjungan lain) atau
  **uang kembali** per tindakan dengan PIN. Ditandai PETUGAS, bukan otomatis.
- Tindakan yang ditolak pasien → tombol **Batalkan**.
- Hak pasien berlaku **6 bulan**.

**Ukuran berhasil:** tidak ada satu pun tindakan/obat yang "hilang dari layar" karena status
kunjungan; alur biasa (tindakan → kasir → obat) bekerja persis seperti sekarang; setiap rupiah
yang masuk punya pasangan: dikerjakan, menjadi hak, atau dikembalikan.

## 2. Keadaan sekarang (dipetakan dari kode 2026-10-15)

- Kasir hanya menagih tindakan **SELESAI** (`kasir_repo.get_tindakan_selesai_for_billing`);
  susulan = SELESAI dengan `waktu_selesai > waktu_bayar` terakhir.
- Bayar → `ANTRI_OBAT` / `COMPLETED` tanpa melihat tindakan PENDING/PROSES (T4-4).
- Layar perawat hanya `KONSULTASI / ANTRI_TREATMENT / ON_TREATMENT`; apotek hanya `ANTRI_OBAT`;
  kasir hanya `ANTRI_BAYAR` — semuanya hari ini.
- `end_tindakan` → `ANTRI_BAYAR` tanpa syarat, walau sudah lunas.
- Upsell PRODUK memindahkan kunjungan ke `ON_TREATMENT` tanpa tindakan aktif → tak ada yang
  memajukannya (ditemukan saat pemetaan).
- Komisi tindakan dicatat saat BAYAR untuk tindakan yang SELESAI saat itu; basis harga master;
  tindakan Rp 0 (kuota/series) tetap berkomisi.
- Tidak ada pembatalan satu tindakan; status tindakan hanya PENDING/PROSES/SELESAI.
- Tidak ada konsep piutang maupun refund per tindakan.
- Sekitar 10 penulis `status_antrian` otomatis, masing-masing dengan aturannya sendiri
  (pemeriksaan_service, treatment_service ×2, upsell_service, series_service, kasir_service bayar
  & void cascade, apotek_service serah & tunda, kunjungan_service, booking_service).

## 3. Rancangan

### 3.1 Data — migrasi kecil, HANYA menambah

| Perubahan | Isi | Gunanya |
|---|---|---|
| `kunjungan_tindakan.id_transaksi` | INT NULL, FK `transaksi_kasir`, indeks | "dibayar oleh transaksi X" — sejajar resep & racikan (T2-2) |
| `kunjungan_tindakan.status_tindakan` | + `BATAL` | tombol Batalkan |
| `pasien_rencana_treatment.sumber_rencana` | + `PRABAYAR` | hak pasien |
| `transaksi_refund.id_kunjungan_tindakan` | INT NULL, FK | uang kembali per tindakan |

**Backfill `id_transaksi` tindakan** (sekali, di migrasi):
1. Tindakan yang muncul di `transaksi_detail_tindakan` milik transaksi BAYAR → transaksi itu.
2. Tindakan SELESAI tanpa snapshot (data pra-F3) → transaksi BAYAR paling awal dengan
   `waktu_bayar >= waktu_selesai` di kunjungan yang sama (aturan cutoff kasir; sama dengan
   backfill resep T2-2).
3. Sisanya NULL. Migrasi mencetak jumlah tiap kelompok; tindakan SELESAI di kunjungan yang
   punya transaksi BAYAR tapi tetap NULL dilaporkan (harus 0 — kalau tidak, berhenti dan periksa).

### 3.2 Status kunjungan = ringkasan

Satu fungsi, satu modul: `app/services/_status_kunjungan.py` →
`hitung_ulang_status(db, id_kunjungan)`. **Semua** penulis otomatis memanggilnya, tidak ada
yang menulis status sendiri lagi (kecuali BATAL dan transisi pra-SOAP).

Kunjungan **menggantung** bila ada salah satu:
- (T) tindakan `PENDING` / `PROSES`;
- (K) item belum ditagih: tindakan tanpa `id_transaksi` yang BISA ditagih (tahap 1: `SELESAI`;
  mulai tahap 2: semua yang bukan BATAL), resep/racikan `PENDING`;
- (O) obat lunas belum diserahkan (resep/racikan `DIBAYAR`) — KECUALI kunjungan di jalur obat
  tertunda (`tgl_janji_kirim` terisi), yang memang sengaja ditutup (perilaku sekarang dipertahankan).

Tidak menggantung → `COMPLETED`. Menggantung → label untuk FO, urutan prioritas:
`ON_TREATMENT` (ada PROSES) › `ANTRI_TREATMENT` (ada PENDING) › `ANTRI_BAYAR` (K) › `ANTRI_OBAT` (O).
Label hanya untuk tampilan dan penghitung dashboard; ANTRIAN TIDAK membacanya (§3.3).

Tidak disentuh fungsi ini: `ANTRI_KONSULTASI`, `KONSULTASI` (sebelum SOAP pertama), `BATAL`.

Dipanggil sesudah: simpan SOAP, upsell, mulai/selesai/batalkan tindakan, pakai sesi series,
bayar, void (kedua jalur), serah obat (penuh/sebagian), obat tertunda, refund obat/tindakan,
simpan sebagai hak. Satu pemeriksa (`scripts/cek_status_kunjungan.py`) membandingkan status
tersimpan dengan hasil fungsi untuk semua kunjungan hari ini — harus 0 selisih.

**Ubah status manual (dropdown FO):** tinggal transisi pra-SOAP
(`ANTRI_KONSULTASI → KONSULTASI`) dan `BATAL` (dengan pagar T2-5). Transisi maju lainnya
(termasuk DEC-015 `ON_TREATMENT → COMPLETED`) dihapus — kunjungan Rp 0 (kuota/series) kini
cukup "dibayar" Rp 0 di kasir (DEC-049 sudah mendukung), jadi jalan pintas itu tak diperlukan.
⚠ Ini mengubah kebiasaan FO — lihat §6 pertanyaan 2.

### 3.3 Antrian membaca isi

| Meja | Syarat (kunjungan hari ini, bukan BATAL) |
|---|---|
| Perawat | punya tindakan `PENDING`/`PROSES` |
| Apotek | punya resep/racikan `DIBAYAR` belum diserahkan (daftar obat tertunda tetap terpisah, seperti sekarang) |
| Kasir | punya item belum ditagih (K) |
| Dokter | tidak berubah (membaca label) |

Satu pasien boleh tampil di dua meja sekaligus. **Tutup kasir** tetap menolak selama ada
kunjungan hari itu yang menggantung — tindakan lunas yang belum dikerjakan harus ditandai
(hak / uang kembali) lebih dulu, sesuai keputusan "petugas menandai".

**Sidik halaman tagihan (anti halaman basi):** halaman tagihan menyisipkan daftar id item yang
ditampilkan. Saat Bayar, server menghitung ulang tagihan (T4-1: sudah membaca data segar);
bila daftarnya berbeda, pembayaran DITAHAN dan halaman dimuat ulang dengan pesan "tagihan
berubah — ada item baru dari dokter/perawat". Berlaku untuk tindakan, resep, dan racikan.

### 3.4 Tagih tindakan yang belum dikerjakan (prabayar)

- Tagihan memuat tindakan bukan BATAL tanpa `id_transaksi` — **apa pun statusnya**. Harga,
  diskon member, kuota, harga paket series dikunci saat itu ke `transaksi_detail_tindakan`
  (snapshot yang sudah ada).
- Ada tindakan belum SELESAI di tagihan → kotak KUNING "Tindakan berikut belum dikerjakan —
  dibayar di muka" + centang wajib. Tanpa centang, server menolak (layar bukan pagar).
- Bayar → `id_transaksi` diisi untuk tindakan YANG DITAGIH (berdasarkan id, pola T4-1).
- Susulan kini = "tindakan tanpa `id_transaksi`" — perbandingan jam (`waktu_selesai > cutoff`)
  untuk tindakan DIHAPUS (sumber bug detik-yang-sama, dan tindakan yang selesai di detik bayar).
- Nota: baris tindakan prabayar diberi keterangan "dibayar di muka".
- Batas 2 transaksi per kunjungan (DEC-051) tetap.

### 3.5 Komisi & BHP

- **Satu aturan:** komisi tindakan dicatat saat tindakan itu SUDAH DIBAYAR **dan** SUDAH SELESAI
  — mana pun yang terakhir.
  - Bayar sesudah selesai → saat bayar (`catat_komisi_transaksi`, seperti sekarang).
  - Selesai sesudah bayar → saat perawat menekan Selesai (`end_tindakan`), `id_transaksi` =
    transaksi pembayarnya, `tanggal` = tanggal selesai.
  - Anti-dobel per `id_ref` AKTIF yang sudah ada tetap dipakai.
- Komisi saat bayar hanya untuk tindakan milik transaksi itu (kini bisa, karena `id_transaksi`).
- BHP tetap dipotong saat selesai (tidak berubah).

### 3.6 Tombol Batalkan tindakan

- Hanya tindakan `PENDING`. `PROSES`/`SELESAI` tidak bisa (§7 CLAUDE.md: void hanya untuk yang
  belum dikerjakan). Dokter, perawat, admin. Alasan wajib → audit log.
- **Belum dibayar** → `BATAL`; kuota member dikembalikan (`decrement_kuota_terpakai`); sesi
  series yang dijadwalkan ke tindakan ini → `PENDING`; series yang LAHIR dari tindakan ini dan
  sesi 1-nya belum dibayar → `CANCELLED` (aturan sama dengan `_bereskan_batal` T2-5 — dipakai
  ulang, bukan ditulis ulang).
- **Sudah dibayar** → bukan batal biasa. Dua tombol:
  - **Simpan sebagai hak pasien** → tindakan `BATAL`, lahir `pasien_rencana_treatment`
    (`sumber_rencana=PRABAYAR`, `status=PENDING`, `id_referensi_sumber=id_kunjungan_tindakan`,
    `tgl_target_akhir = tanggal bayar + 6 bulan`).
  - **Kembalikan uang** → `transaksi_refund` (`id_kunjungan_tindakan`, nilai =
    `transaksi_detail_tindakan.subtotal` bersih yang dibayar), PIN Admin/Superadmin/Owner ≠
    pemroses (pagar T32 dipakai ulang), dibukukan di TANGGAL REFUND lewat `_refund_bukuan`,
    masuk hitungan laci. Tindakan → `BATAL`.
  - Komisi: tindakan prabayar yang belum dikerjakan belum berkomisi → tidak ada yang dibatalkan.

### 3.7 Hak pasien (PRABAYAR)

- Tampil di "Pakai Sesi" seperti series. Dipakai di kunjungan lain → tindakan baru dengan
  `id_rencana`; **harga Rp 0 selalu** (`_compute_charge`: sumber PRABAYAR dikecualikan dari aturan
  "sesi 1 = harga paket"). Pagar "sesi 1 series sudah lunas" tidak berlaku untuk PRABAYAR.
- Komisi saat dipakai: seperti sesi series Rp 0 sekarang (basis harga master).
- Lewat `tgl_target_akhir` → tidak ditawarkan lagi dan tidak bisa direfund (hangus). Omzet
  tidak berubah — uangnya sudah dibukukan saat dibayar.
- Sebelum hangus, bisa direfund (PIN, aturan sama dengan §3.6). Rencana → `CANCELLED`.
- Daftar "hak tindakan belum dipakai" (pasien, tindakan, nilai, batas) untuk Finance — layar
  laporan sederhana; tidak masuk ekspor Finance sampai diminta.

### 3.8 Void & laporan

- Pagar void "tindakan sudah selesai" tetap. Void transaksi prabayar: `id_transaksi` tindakan
  yang belum dikerjakan dilepas (kembali "belum ditagih"), kuota/series/komisi mengikuti aturan
  void sekarang. Void ditolak bila tindakan transaksi itu sudah jadi hak atau direfund (pola
  `_pagari_void_sudah_refund`).
- Omzet = tanggal bayar (tidak berubah). Refund per tindakan = tanggal refund, lewat
  `_refund_bukuan` — **tidak ada rumus uang baru**.
- Laporan klinis/tindakan yang menghitung `status_tindakan = SELESAI`: tidak berubah (BATAL
  memang tidak dihitung). Laporan yang menghitung "semua tindakan" diperiksa satu per satu di
  tahap 3 (pertanyaan §4.1 CLAUDE.md: BATAL dihitung atau tidak?).

## 4. Tahapan

Setiap tahap: test (gagal di kode lama bila menutup cacat) → kode → suite + smoke → uji layar
dr. Hansen di desktop → commit & push. Deploy ke mini PC per tahap, di luar 12.00–22.00.

| Tahap | Isi | Perilaku yang terlihat |
|---|---|---|
| **1** | Migrasi §3.1 + backfill · bayar mengisi `id_transaksi` tindakan (yang ditagih, masih hanya SELESAI) & susulan tindakan = tanpa `id_transaksi` · `_status_kunjungan` + semua penulis · antrian membaca isi · sidik halaman tagihan · pemeriksa status | Alur biasa sama persis. **T4-4 tertutup**: bayar saat ada tindakan belum selesai → kunjungan tetap di layar perawat, selesai → kembali ke kasir sebagai susulan. Halaman tagihan basi ditahan. |
| **2** | Tagih tindakan prabayar + kotak kuning + komisi saat selesai + keterangan nota | Bayar dulu sungguh bisa; perawat & apotek bersamaan |
| **3** | Tombol Batalkan (belum dibayar) | Tindakan yang ditolak pasien bisa dibuang, kuota/series kembali |
| **4** | Simpan sebagai hak · refund per tindakan · Pakai Sesi PRABAYAR · daftar hak untuk Finance | Lingkaran uang tertutup |

## 5. Risiko & cara menjaganya

- **Penulis status yang terlewat** (pola §4.1 "dua penulis") → pemeriksa `cek_status_kunjungan`
  + test per penulis; grep `status_antrian =` / `update_status(` harus hanya berisi fungsi
  ringkasan, BATAL, dan pra-SOAP.
- **Laporan/dashboard yang membaca label** → label tetap ditulis, jadi pembaca lama tetap jalan;
  hanya antrian yang pindah membaca isi.
- **Data lama** → backfill §3.1 dengan hitungan; trial run, tapi pemeriksa harus 0.
- **Deploy tahap 1 mengubah antrian semua meja sekaligus** → uji layar lengkap (FO, dokter,
  perawat, kasir, apotek, tutup kasir) sebelum deploy.

## 6. Pertanyaan — DIJAWAB dr. Hansen 2026-10-15

Jawaban: (1) **dari tanggal bayar**; (2) **setuju** dropdown dipangkas; (3) **setuju** dokter,
perawat, admin (+ kasir untuk Kembalikan uang dengan PIN). Pertanyaan aslinya:

1. **Batas 6 bulan dihitung dari mana?** Rancangan ini: dari **tanggal bayar** (uangnya masuk).
   Alternatif: dari tanggal disimpan sebagai hak.
2. **Dropdown ubah status FO dipangkas** jadi hanya pra-SOAP dan BATAL (§3.2). FO tidak lagi
   bisa memajukan status manual (mis. menandai COMPLETED). Setuju?
3. **Siapa boleh menekan Batalkan / Simpan sebagai hak?** Rancangan: dokter, perawat, admin
   (dan kasir untuk "Kembalikan uang", dengan PIN). Perlu dipersempit?
