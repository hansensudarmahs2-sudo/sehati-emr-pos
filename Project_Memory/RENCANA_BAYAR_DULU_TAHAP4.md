# Bayar Dulu — Tahap 4: Hak Pasien & Uang Kembali per Tindakan — Rencana

Status: **RANCANGAN** (ditulis 2026-10-28, sesi cloud). **P1–P4 DIJAWAB dr. Hansen 2026-10-28**
— semua sesuai usulan: (P1) Rp 0 → kuota/sesi dikembalikan; (P2) sesi 1 paket: hak = sesi 1
dipakai lagi tanpa ditagih ulang, refund penuh hanya bila belum ada sesi lain terpakai;
(P3) PIN refund hanya untuk transaksi hari lampau (sama dengan T32); (P4) layar void diberi
baris "tindakan prabayar akan dilepas". **TAHAP 4 SELESAI (T4-1..T4-6) 2026-10-28** di cabang
`claude/hopeful-pasteur-172ozo` (sesi cloud). Berikutnya: uji layar dr. Hansen (U77–U83) → `main` →
deploy tahap 1+2+4 bersama. Lihat `HANDOFF_2026-10-28.md`. Spek induk: `DESAIN_BAYAR_DULU_BERCABANG.md` §3.6 (cabang "sudah
dibayar"), §3.7, §3.8 — disetujui 2026-10-15. Dokumen ini memetakan spek itu ke kode yang ada
hari ini dan menandai tempat spek tidak cukup (§2, butir P1–P4).

**Tujuan:** tindakan yang sudah dibayar di muka lalu tidak dikerjakan punya jalan keluar —
**Simpan sebagai hak** (dipakai di kunjungan lain, maks 6 bulan dari tanggal bayar) atau
**Kembalikan uang** (PIN). Setelah tahap ini, tahap 1+2+4 boleh di-deploy bersama.

## 1. Yang sudah ada (diperiksa di kode, 2026-10-28)

| Butuh | Sudah ada? | Di mana |
|---|---|---|
| `pasien_rencana_treatment.sumber_rencana = 'PRABAYAR'` | ✅ | migrasi `20261021_0100` |
| `transaksi_refund.id_kunjungan_tindakan` (FK + indeks) | ✅ | migrasi `20261021_0100`, model `TransaksiRefund` |
| Status tindakan `BATAL` | ✅ | migrasi `20261021_0100` |
| Status rencana `EXPIRED` | ✅ (enum ada, tak ada penulis) | `StatusRencanaTreatmentEnum` |
| Nilai bersih tindakan yang dibayar | ✅ `transaksi_detail_tindakan.subtotal` sudah BERSIH (harga − porsi diskon) | `proses_bayar` |
| Pagar PIN penyetuju ≠ pemroses | ✅ `_otorisasi_refund_lampau` + `daftar_penyetuju_refund` | `kasir_service.py` |
| Pembukuan refund di tanggal refund | ✅ `_refund_bukuan` (membaca semua `transaksi_refund`, tanpa saring jenis) | |
| Void ditolak bila sudah ada refund | ✅ `_pagari_void_sudah_refund` (kedua jalur) | |
| Pengembalian kuota / sesi series | ✅ `_batal_tindakan.kembalikan_kuota` / `kembalikan_sesi` | |
| Tutup kasir menolak kunjungan yang menggantung | ✅ `_pending_antrian_hari_ini` | |

**→ Tahap 4 TANPA migrasi skema.** Satu nilai baru di kolom VARCHAR: `jenis_refund = 'TINDAKAN'`
(lihat T4-3; CLAUDE.md §4.5 — VARCHAR menerima apa pun, jadi nilainya dijaga test).

## 2. Celah di spek yang ketemu saat memetakan — perlu keputusan

**P1. Tindakan yang dibayar Rp 0 (kuota member / sesi 2..N series) lalu ditolak.** Spek §3.6
hanya membahas tindakan berharga. Usul: tombol yang sama ("Simpan sebagai hak"), tapi hasilnya
**kuota/sesi itu dikembalikan** (pakai `_batal_tindakan`, aturan yang sama dengan Batalkan) —
bukan hak PRABAYAR baru. Kuota & series sudah merupakan hak dengan batasnya sendiri; hak
PRABAYAR bernilai Rp 0 hanya menggandakannya. "Kembalikan uang" tidak ditawarkan (nilainya 0).

**P2. Sesi 1 series (pembawa harga PAKET, mis. 6 × Rp 500.000) dibayar lalu ditolak.**
- *Simpan sebagai hak* → sesi 1 kembali `PENDING`, bisa dipakai lewat "Pakai Sesi". ⚠ Hari ini
  `_compute_charge` menagih harga paket LAGI untuk tindakan apa pun yang menunjuk sesi 1 —
  aturannya harus ditambah: "sesi 1 yang sudah pernah lunas → Rp 0".
- *Kembalikan uang* → hanya bila **belum ada sesi lain** dari series itu yang dipakai; nilainya
  seluruh paket, series dibatalkan. Bila sudah ada sesi terpakai → ditolak dengan pesan
  "simpan sebagai hak" (menghitung refund sebagian paket = rumus uang baru, di luar spek).

**P3. PIN untuk Kembalikan uang: SELALU, atau hanya transaksi hari lampau?** Spek 2026-10-15
menulis "dengan PIN" tanpa batas hari. Refund obat tertunda (T32) hanya meminta PIN untuk
transaksi hari lampau — hari yang sama cukup kasir sendiri. Usul: **ikuti T32** (satu aturan
untuk semua refund per item), tapi ini keputusan dr. Hansen.

**P4. (dari handoff tahap 2, belum dijawab)** Layar konfirmasi void belum memberi tahu kasir
bahwa tindakan prabayar yang belum dikerjakan akan "dilepas" (kembali belum ditagih). Usul:
tambah satu baris di `peringatan_void` — kecil, ikut T4-4.

## 3. Keputusan rancangan yang saya ambil (bukan pertanyaan — koreksi bila keliru)

- **Rencana PRABAYAR ditulis `id_kunjungan_pembuat = NULL`**, asalnya lewat
  `id_referensi_sumber = id_kunjungan_tindakan` (tindakan → kunjungan & transaksi). Kenapa:
  `_series.py` mengelompokkan series per (pasien, treatment, kunjungan pembuat). Kalau hak diberi
  kunjungan pembuat yang sama dengan series dokter treatment yang sama, ia terbaca sebagai "sesi 1
  series berikutnya" — memotong series dokter itu dan mengubah harga paketnya (pola §4.1 "satu
  hal, dua arti"). Dengan NULL, `_series` dan `_pagari_sesi_1_lunas` otomatis tidak menyentuhnya.
- **`_compute_charge`: sumber PRABAYAR → Rp 0 SELALU** (spek §3.7). Wajib eksplisit: rencana
  hak ber-`urutan_sesi = 1`, dan aturan sekarang akan menagihnya sebagai harga paket.
- **Kedaluwarsa dihitung dari tanggal, tidak ada penulis `EXPIRED`.** `tgl_target_akhir` =
  tanggal bayar + 6 bulan; lewat itu → tidak tampil di "Pakai Sesi", ditolak `use_session`, dan
  tidak bisa direfund. Tidak ada cron (sesuai gaya proyek: tak ada job latar untuk status).
  Pagar tanggal HANYA untuk PRABAYAR — `tgl_target_akhir` series dokter tidak mulai ditegakkan.
- **Hanya tindakan `PENDING`** yang bisa jadi hak / direfund (CLAUDE.md §7). `PROSES` →
  selesaikan dulu.
- **Peran**: Simpan sebagai hak = `require_perawat_role` (Perawat, Dokter, Admin, Owner,
  Superadmin — sama dengan tombol Batalkan, spek §6 jawaban 3). Kembalikan uang = peran yang
  boleh membayar di kasir (Kasir, Admin, Owner, Superadmin); penyetuju PIN =
  `_ROLES_PENYETUJU_REFUND`. Himpunan role yang SUDAH ada dipakai apa adanya — tidak ada yang baru.
- **Komisi**: tindakan prabayar yang belum dikerjakan belum berkomisi (tahap 2) → hak/refund
  tidak membatalkan komisi apa pun. Hak yang dipakai → komisi seperti sesi series Rp 0 sekarang.
- **Ekspor Finance**: `refunds_raw` ditambah kolom `id_kunjungan_tindakan` + deskripsi
  `jenis_refund='TINDAKAN'`. Tanpa itu refund tindakan tampak seperti refund transaksi utuh —
  persis pola "kolom jembatan" yang sudah dua kali menggigit (Temuan 13/33). Daftar hak belum
  dipakai **tidak** masuk ekspor (spek §3.7: "sampai diminta").

## 4. Tugas

Setiap tugas: test dulu (yang menutup cacat harus GAGAL di kode lama) → kode → suite → commit.
Test baru di `tests/integration/test_bayar_dulu_tahap4.py`.

### T4-1 Simpan sebagai hak
> **SELESAI 2026-10-28 (cloud).** `TreatmentService.simpan_sebagai_hak` + `tambah_bulan`, route
> `POST /web/ruang-tindakan/tindakan/{id}/simpan-hak`, tombol "↪ Simpan sebagai hak" (hanya untuk
> PENDING ber-`id_transaksi`; Batalkan tetap hanya untuk yang belum dibayar). 20 test baru di
> `test_bayar_dulu_tahap4.py` — 20/20 GAGAL di kode lama, lulus di kode baru. Suite 484 lulus,
> 17 dilewati, 0 gagal (MySQL 8 di Docker, login uji). Layar diperiksa lewat TestClient (bukan
> uji layar dr. Hansen).
> Penyimpangan kecil dari teks di bawah, disengaja: (1) sesi series TIDAK lewat
> `bereskan_satu_tindakan` — di sana sesi 1 yang lahir di kunjungan ini membatalkan SELURUH
> series (benar sebelum bayar, salah sesudahnya); dipakai `kembalikan_kuota`/`kembalikan_sesi`
> langsung. (2) Sesi yang tidak `SCHEDULED` (data ganjil) → 409 sebelum menulis apa pun, bukan
> BATAL yang menghapus hak tanpa pengganti. (3) `id_transaksi` tindakan TIDAK dikosongkan (jejak
> pembayar; nilai hak dibaca dari snapshot).
> ✅ (Ditutup T4-2.) ~~**Sampai T4-2 selesai, hak belum benar saat DIPAKAI:**~~ sesi 1 paket yang kembali PENDING lalu
> dipakai lewat "Pakai Sesi" masih ditagih harga paket lagi, dan hak PRABAYAR masih ditagih harga
> treatment (`_compute_charge` belum kenal keduanya). Itu isi T4-2 — jangan deploy di antaranya.
**Berkas:** `treatment_service.py` (`simpan_sebagai_hak`), `_batal_tindakan.py` (dipakai ulang),
`web/routes/perawat.py` + `perawat_tindakan.html` (tombol untuk tindakan PENDING ber-`id_transaksi`;
pesan `batalkan_tindakan` untuk yang sudah dibayar diganti menunjuk tombol ini).
- Urutan kunci sama dengan Batalkan: baca-segar → kunjungan → tindakan. Syarat: `PENDING`,
  `id_transaksi` terisi, transaksinya `BAYAR`, alasan wajib.
- Tindakan berharga → `BATAL` + rencana PRABAYAR (`status=PENDING`, `urutan_sesi=1`,
  `id_referensi_sumber`, `tgl_target_akhir = tgl bayar + 6 bulan`, nama snapshot).
- Kuota / sesi series → P1/P2 (dijawab 2026-10-28: kuota/sesi dikembalikan). `hitung_ulang_status` + audit `TINDAKAN_JADI_HAK`.
- Test: hak lahir dengan batas yang benar; kunjungan jadi COMPLETED (bila tak ada sisa lain);
  tutup kasir tidak lagi terhalang; kuota tidak dikembalikan dua kali (hak lalu Batal kunjungan);
  tindakan belum dibayar / PROSES / SELESAI ditolak.

### T4-2 Memakai hak
> **SELESAI 2026-10-28 (cloud).** Modul baru `app/services/_hak_prabayar.py` = SATU definisi
> (`adalah_hak`, `berlaku`, `sisa_hari`, `nilai`, `sesi1_pernah_lunas`) — T4-3/T4-5 wajib
> memakainya. `_compute_charge`: hak PRABAYAR dan sesi 1 yang pernah lunas → Rp 0 (sebelum
> aturan harga paket). `list_active_for_pasien`: hak = satu baris per rencana (`jenis="HAK"`,
> `nilai`, `berlaku_sampai`, `sisa_hari`), kedaluwarsa disembunyikan; `use_session` + rute
> "daftar + pakai sesi" menolak kedaluwarsa (rute menolak SEBELUM membuat kunjungan). Layar:
> kartu hak di detail pasien ("↪ Pakai Hak"), "↪ Hak — … (s/d tgl)" di daftar pasien.
> Tambahan di luar teks rencana, keduanya disengaja: (1) nota menulis "Hak prabayar" untuk hak
> yang dipakai (dulu akan tertulis "Paket series"); (2) **celah gabungan T4-1+T4-2 ditutup**:
> sesi 1 lunas → hak → dipakai lagi di kunjungan PEMBUAT yang sama → Batalkan membatalkan
> SELURUH series (`bereskan_satu_tindakan`). Terbukti test merah dulu, lalu diperbaiki.
> 11 test baru (6 gagal di kode lama; 3 pembanding lulus di keduanya; 2 test celah Batalkan).
> Suite 495 lulus / 17 dilewati / 0 gagal; `cek_smoke_web` 614 halaman 0 bermasalah;
> `cek_status_kunjungan --hari 30` 0 selisih. Layar dicek lewat TestClient, bukan uji layar.
**Berkas:** `kasir_service.py` (`_compute_charge`), `series_service.py` (`list_active_for_pasien`,
`use_session`), `pasien_detail.html`.
- `_compute_charge` WAJIB juga mengenali **sesi 1 yang sudah pernah lunas** (tindakan BATAL lain
  ber-`id_transaksi` BAYAR menunjuk rencana yang sama) → Rp 0 (P2; hasil T4-1).
- Hak tampil per rencana (bukan digabung per treatment) dengan nilai & batas; kedaluwarsa
  disembunyikan; `use_session` menolak yang kedaluwarsa (kunci baris sudah ada, Temuan 19).
- Test: dipakai → tagihan Rp 0, komisi tercatat saat dibayar Rp 0 & selesai; kedaluwarsa ditolak;
  hak dan series dokter treatment yang sama di kunjungan yang sama tidak saling mengubah harga
  (test penutup cacat untuk keputusan `id_kunjungan_pembuat = NULL`).

### T4-3 Kembalikan uang per tindakan
> **SELESAI 2026-10-28 (cloud).** `KasirService.refund_tindakan` (tiga asal: A tindakan PENDING
> lunas · B hak PRABAYAR · **C sesi 1 paket yang sudah jadi hak** — C tidak tertulis di bawah tapi
> tanpa itu hak sesi 1 dari T4-1 tak punya jalan uang kembali), `_syarat_refund_tindakan` (SATU
> pemeriksaan, dipakai juga `tindakan_bisa_direfund` untuk layar), route
> `POST /web/kasir/refund-tindakan` (peran kasir; `kembali` hanya path `/web/…`), kotak
> "↩ Tindakan dibayar, belum dikerjakan" di halaman tagihan (dari server, tampil di mode apa pun —
> mode susulan tidak memuat item lunas), label "refund tindakan" di kotak Pengembalian.
> Refund SELALU ditambatkan ke tindakan PEMBAYAR (`id_kunjungan_tindakan`) — anti-dobel satu
> jangkar untuk A/B/C. Rp 0 (kuota, sesi 2..N, tindakan yang memakai hak) ditolak dengan petunjuk
> "Simpan sebagai hak". Sesi 1 paket: hanya bila tak ada sesi lain SCHEDULED/DONE.
> 20 test baru, 20/20 gagal di kode lama. Suite 515 lulus / 17 dilewati / 0 gagal;
> `jejak_uji_ui` 18 lulus 0 gagal (skenario refund hari ini + hak hari lampau ber-PIN);
> `cek_smoke_web` 647 halaman 0 bermasalah; `cek_finance_pack` 5/5; `cek_status_kunjungan` 0.
> Belum: ekspor `refunds_raw.id_kunjungan_tindakan` + deskripsi jenis TINDAKAN (T4-5, sesuai
> rencana) — sampai itu, Finance melihat refund TINDAKAN tanpa jangkar tindakannya.
> Catatan terbuka (tidak diubah): pesan sukses `refund_item_tertunda` punya cacat format yang
> sama ("(TUNAI). dibukukan") — kosmetik, dibiarkan.
**Berkas:** `kasir_service.py` (`refund_tindakan`), route kasir, `kasir_tagihan.html` (kotak di
halaman tagihan untuk tindakan PENDING yang sudah dibayar).
- Satu fungsi untuk dua asal: tindakan PENDING ber-`id_transaksi`, ATAU hak PRABAYAR `PENDING`
  belum kedaluwarsa (tindakan asalnya lewat `id_referensi_sumber`).
- Nilai = `transaksi_detail_tindakan.subtotal` transaksi itu (tak ada rumus baru). Anti-dobel
  `FOR UPDATE` per `id_kunjungan_tindakan`. `metode_sah`. PIN menurut P3. `jenis_refund='TINDAKAN'`.
  Header transaksi TIDAK disentuh (T32). Tindakan → `BATAL` / rencana → `CANCELLED`.
  `hitung_ulang_status` + audit `REFUND_TINDAKAN`.
- Test: nilai = subtotal bersih (dengan diskon member/kepala); laporan omzet hari refund
  berkurang, hari bayar tidak; tutup kasir menghitungnya keluar dari laci; refund dua kali
  ditolak; hak yang sudah dipakai / kedaluwarsa ditolak; `jejak_uji_ui` invarian uang tetap hijau.

### T4-4 Pagar void
> **SELESAI 2026-10-28 (cloud).** `_pagari_void_tindakan_jadi_hak` di KEDUA jalur void (sesudah
> `_pagari_void_sudah_refund`): tindakan `id_transaksi == trx` + `BATAL` = "dibatalkan SESUDAH
> dibayar" (T4-1/T4-3 tidak mengosongkan `id_transaksi`; BATAL yang tak pernah dibayar selalu
> NULL). Lingkup per transaksi: hak dari T1 tidak menghalangi void susulan T2. P4:
> `peringatan_void` kini memuat `tindakan_dilepas` (tanpa kunci baris — halaman GET) dan
> `tindakan_jadi_hak`; potongan `_peringatan_void_tindakan.html` dipakai modal void hari ini
> (sukses bayar) DAN modal force-void (halaman tagihan, yang dulu tak punya peringatan apa pun).
> 13 test baru (10 gagal di kode lama: 3 bentuk × 3 jalur + peringatan; 3 pembanding lulus di
> keduanya). Suite 528 lulus / 17 dilewati / 0 gagal; `cek_smoke_web` 669 halaman 0 bermasalah;
> `cek_status_kunjungan` 0 selisih.
**Berkas:** `kasir_service.py` (pagar baru di KEDUA jalur void + `peringatan_void` bila P4 disetujui).
- Tolak void bila ada tindakan dalam lingkupnya yang `BATAL` sesudah dibayar (jadi hak, atau
  kuota/sesinya dikembalikan). Refund sudah tertutup `_pagari_void_sudah_refund`.
  Tanpa pagar ini: void mengeluarkan uangnya dari omzet, sementara hak gratisnya tetap ada.
- Test di kedua jalur (`void_transaksi`, `force_past_day_void` + PIN).

### T4-5 Daftar hak untuk Finance + ekspor
> **SELESAI 2026-10-28 (cloud).** `_hak_prabayar.daftar_belum_dipakai` (jenis `HAK` dan
> `SESI_1_PAKET` — asal C; hangus hanya bila diminta) → halaman `GET /web/kasir/hak-tindakan`
> (menu "↪ Hak Tindakan" untuk Owner/Superadmin/Admin/Kasir; peran `require_kasir_role`, bukan
> `REPORTS_ROLES`): total nilai yang berlaku, baris merah ≤ 30 hari, tombol "↩ Kembalikan uang"
> per baris → route refund T4-3 (kolom PIN bila tanggal bayar lampau). Ekspor: `refunds_raw`
> + kolom `id_kunjungan_tindakan`, deskripsi `jenis_refund` memuat TINDAKAN. Test baru menjaga
> kolom ekspor `refunds_raw` == kamus data (urutan & nama) — pemeriksa yang tak ada saat
> Temuan 33. 5 test baru, 5/5 gagal di kode lama. Suite 533 lulus / 17 dilewati / 0 gagal;
> `cek_finance_pack` 5/5; `cek_smoke_web` 696 halaman 0 bermasalah.
> ⚠ `Project_Memory/RawDataExport/01_DATA_DICTIONARY.md` SUDAH BASI sebelum ini (tak memuat
> `jenis_refund` sejak #54-F) dan skrip regenerasinya tidak ada di repo — tidak disentuh.
> Kamus yang berlaku = `_export_columns.py` (ikut ZIP & `/web/export/dictionary.*`).
**Berkas:** layar laporan sederhana "Hak tindakan belum dipakai" (pasien, tindakan, nilai, tgl
bayar, batas, sisa hari) dengan tombol Kembalikan uang per baris (memanggil T4-3);
`export_service.py` + `_export_columns.py` (`id_kunjungan_tindakan`, deskripsi jenis TINDAKAN).
- Peran: Kasir/Admin/Owner/Superadmin — himpunan sendiri, BUKAN `REPORTS_ROLES` (§4.1: laporan
  ini memuat uang yang masih menjadi kewajiban klinik).
- Kelas Tailwind hanya yang sudah ada (`scripts/cek_kelas_tailwind.py`).

### T4-6 Pemeriksa + dokumentasi
> **SELESAI 2026-10-28 (cloud).** `scripts/cek_tindakan_lunas_batal.py` — aturannya lebih tepat
> daripada "TEPAT SATU pasangan" di bawah: hak yang kemudian direfund punya DUA jejak sah (rencana
> PRABAYAR CANCELLED + refund). Aturan akhir: audit `TINDAKAN_JADI_HAK` 0/1; bentuk HAK ⇔ tepat 1
> rencana PRABAYAR; refund ≤ 1 dan tidak pernah untuk KUOTA; tanpa audit → tepat 1 refund; plus
> arah balik (refund/hak menunjuk tindakan BATAL yang dibayar transaksi itu). Dua arah: 6 test.
> Dokumentasi: CLAUDE.md §4.1/§5/§8, DESAIN status, UJI_UI U77–U83, `HANDOFF_2026-10-28.md`.
> Hasil pemeriksa & dua kegagalan test artefak (jam/data) di handoff §3.
- Pemeriksa baru `scripts/cek_tindakan_lunas_batal.py` (HANYA membaca): setiap tindakan `BATAL`
  ber-`id_transaksi` di transaksi BAYAR harus punya TEPAT SATU pasangan — rencana PRABAYAR,
  refund TINDAKAN, atau audit kuota/sesi kembali. Ini wujud "setiap rupiah punya pasangan"
  (spek §1). Diuji dua arah (lulus di data benar, gagal saat pasangan dihapus).
- CLAUDE.md §4.1 (baris status ringkasan: tahap 4), DESAIN status, UJI_UI U77+ (hak, pakai hak,
  refund tindakan hari ini & lampau, void ditolak), handoff.
- Suite, `cek_status_kunjungan --hari 30`, `cek_finance_pack`, `jejak_uji_ui`, `cek_smoke_web`.

## 5. Sesudah tahap 4

Tahap 1+2+4 siap deploy bersama — **setelah** uji layar dr. Hansen di desktop (U53–U62 tahap
sebelumnya juga belum diuji layar), backup, di luar 12.00–22.00, `cek_status_kunjungan` di mini
PC sebelum & sesudah.
