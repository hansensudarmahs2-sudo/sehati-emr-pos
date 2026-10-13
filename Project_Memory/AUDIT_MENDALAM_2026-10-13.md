# Audit mendalam — bertahap, per alur bisnis

Diminta dr. Hansen 2026-10-13: *"cek end to end lalu interaksi dengan fungsi yang lain"*.
Setiap tahap mengikuti SATU alur dari pintu masuk sampai akhir, lalu memeriksa setiap
tempat alur itu bersinggungan dengan modul lain. Setiap klaim dibuktikan dari kode, dan
yang berdampak dibuktikan lagi dengan percobaan di DB dev (sesi di-rollback) — CLAUDE.md §1.5.

⚠ Data mini PC & dev = trial run (CLAUDE.md §8). Temuan di sini tentang KODE; tidak ada
usulan membereskan data lama.

| Tahap | Alur | Status |
|---|---|---|
| 1 | Identitas pasien: daftar → cari → edit → nonaktif → gabung | **selesai 2026-10-13** |
| 2 | Klinis: antrian → SOAP → diagnosa → tindakan → resep/racikan → draf apoteker | **diaudit 2026-10-13 — menunggu keputusan perbaikan** |
| 3 | Apotek & stok: serah → lot/FEFO → retur supplier → opname → pengadaan | belum |
| 4 | Kasir & uang: tagihan → bayar → void → refund → retur → tutup kasir | belum |
| 5 | Laporan & ekspor: omzet, apotek, Finance, paket klinis | belum |
| 6 | Akses & keamanan: role, CSRF, audit log, PHI | belum |

---

## Tahap 1 — Identitas pasien

### Peta yang diperiksa

- **Pembuat pasien:** hanya `PasienService.register_pasien_baru`, dipanggil dari 3 pintu:
  form pendaftaran, apotek (tebus resep luar), API v1 `POST /pasien`. Pasien `BKT-…` di DB
  dev dibuat oleh `tests/integration/test_booking_service.py` sendiri, bukan oleh aplikasi.
- **Penulis kolom identitas:** `update_pasien_profile`, `AuditPasienService.nonaktifkan /
  aktifkan / gabungkan`. Semua lewat normalisasi NIK & No. RM Omnicare.
- **Pembuat kunjungan** (tempat identitas dipakai): `kunjungan_lama` (dipanggil antrian Cari
  Pasien, beli produk, booking check-in, API v1), `PasienService` (daftar + antri),
  `membership_service` (aktivasi), `retur_pasien_service` (kunjungan retur), satu lagi di
  `kunjungan_service:558`.
- **Tabel ber-`id_pasien`:** 15 di DB. 13 dipindah saat gabung, 3 dikecualikan ber-alasan
  (setelah perbaikan T1-A).

### T1-A ✅ DIPERBAIKI — `pasien_pseudonim` tak terdaftar di registry penggabungan

`cek_gabung_pasien` gagal di bagian A: tabel ber-`id_pasien` yang tidak ada di
`TABEL_PINDAH` maupun `TABEL_DIKECUALIKAN`. Setelah dibaca, **kodenya sudah benar** — baris
pseudonim SENGAJA tidak dipindah: `pid` tidak pernah diubah, dan duplikat dipetakan ke pasien
yang bertahan saat ekspor (`ClinicalExportService._peta_gabung`). Memindahkannya justru
merusak. Yang kurang hanya pencatatan → ditambahkan ke `TABEL_DIKECUALIKAN` dengan alasan.
`cek_gabung_pasien`: **19 lulus, 0 gagal** (sebelumnya gagal di sini = bukti arah kedua).

### T1-B ✅ DIPERBAIKI 2026-10-13 — pasien yang sudah DIGABUNG masih bisa di-booking & di-check-in

Dua penulis, dua arti (CLAUDE.md §4.1): `pasien.tipe_membership` adalah **salinan** tier.
Diskon kasir membacanya dari **riwayat** (`MembershipService.get_diskon_for_pasien`), tapi
gerbang booking (`booking_service._tier_of`) dan lencana di layar membaca **salinannya**.
Penggabungan memindahkan riwayat, tapi **tidak menyentuh salinan** — dan tidak ada satu pun
pembuat kunjungan selain apotek yang memeriksa `is_active`.

Percobaan (DB dev, di-rollback) — pasien VIP digabung ke pasien REGULAR:
1. Pasien duplikat (NONAKTIF) **muncul** di dropdown member booking (`list_members` tanpa
   saring `is_active`).
2. Booking untuk pasien itu **diterima** (`_get_pasien_membership` hanya cek tier).
3. Check-in **membuat kunjungan di ID duplikat** — riwayat terpecah lagi, persis masalah yang
   diselesaikan penggabungan. Tanpa error, tanpa gejala.
4. Pasien yang **bertahan ditolak** booking ("berstatus REGULAR") walau riwayat membership
   aktifnya sudah pindah ke sana.

Jalur lain yang juga tak memeriksa `is_active`: `kunjungan_lama` sendiri (antrian lewat URL
langsung, API v1), aktivasi membership. Halaman detail pasien NONAKTIF tampil persis seperti
pasien biasa — tanpa peringatan — dan bisa dibuka dari halaman audit ("buka rekam").

**Perbaikan (disetujui dr. Hansen 2026-10-13):**
- `app/services/_pasien_aktif.pastikan_pasien_aktif` — 409 dengan pesan yang menunjuk pasien
  yang BERTAHAN. Dipasang di `kunjungan_lama` (antrian, booking check-in, API v1),
  `beli_produk_lengkap`, dan gerbang booking. Dropdown member booking menyaring `is_active`.
- Penggabungan: kalau duplikat punya membership AKTIF, salinan tier-nya pindah ke yang
  bertahan; salinan tier duplikat **selalu dikembalikan ke REGULAR** (keputusan dr. Hansen).
  Jejak lamanya di audit `PASIEN_GABUNG` (`tier_duplikat`, `tier_bertahan`).
- Halaman detail pasien NONAKTIF: pita merah + tautan ke pasien yang bertahan.
  ⚠ Kesalahan sendiri yang tertangkap saat memeriksa ulang: `PasienResponse` tidak memuat
  `is_active`, jadi pita versi pertama TIDAK AKAN PERNAH muncul. Field ditambahkan.
- `create_kunjungan_billing` (membership) tidak dipagari: tak dipanggil dari mana pun (route-nya
  sengaja NO-OP). Kalau dihidupkan lagi, pasang `pastikan_pasien_aktif`.
- Uji: `tests/integration/test_pasien_nonaktif.py` (8). Dua arah — 7 suntikan, semuanya
  tertangkap. ⚠ Satu suntikan ("dropdown tanpa saring") awalnya LOLOS: test-nya lulus berkat
  reset tier, bukan berkat saringannya. Test diperkuat. Percobaan repro kini berhenti di 409.

### Diperiksa — BERSIH (dicatat supaya tidak diperiksa ulang)

- **Diskon kasir sesudah penggabungan:** benar — dibaca dari riwayat ACTIVE yang ikut pindah,
  bukan dari salinan tier. Kecurigaan awal saya tidak terbukti.
- **Pencarian & "pasien terbaru":** menyaring pasien nonaktif.
- **Tebus resep apotek:** menolak pasien nonaktif (`apotek.py:125`).
- **API v1 pasien & kunjungan:** setiap endpoint ber-`role_required` (rincian → tahap 6).
- **No. RM Omnicare & NIK:** satu jalur normalisasi; gabung/nonaktif sudah ditangani
  (lihat `DESAIN_NO_RM_OMNICARE.md`, `app/core/nik.py`).


---

## Tahap 2 — Alur klinis (diaudit 2026-10-13)

Metode: tiga agen pembaca (antrian+SOAP · tindakan+kuota+series · resep+racikan+apoteker)
memetakan kode dan mengusulkan kandidat; SETIAP kandidat dibuktikan ulang dari kode, dan
yang menyangkut uang/obat dibuktikan dengan percobaan memakai `proses_bayar` /
`void_transaksi` SEBENARNYA di DB dev (sesi di-rollback; skrip `repro_tahap2.py`).

### Terbukti dengan percobaan (fungsi bayar/void asli)

**T2-1 ✅ DIPERBAIKI 2026-10-13 — Obat lunas TERDAMPAR sesudah tagihan susulan.** Bayar 1 → resep DIBAYAR,
ANTRI_OBAT. Dokter menambah tindakan (status mundur ke ANTRI_TREATMENT, DEC-050), perawat
selesai, kasir menagih susulan → `proses_bayar` menentukan status dari baris PENDING yang
BARU ditandai saja (`kasir_service.py` "status_baru = ANTRI_OBAT if n_resep_updated …") →
**COMPLETED**, resep lama tetap DIBAYAR. Hasil: lunas, keluar dari antrian apotek, tak bisa
diserahkan (`apotek_service` serah menolak selain ANTRI_OBAT), stok tak pernah dipotong.

**T2-2 ✅ DIPERBAIKI 2026-10-13 — Void satu transaksi membatalkan obat transaksi LAIN di kunjungan yang sama.**
Split billing T1 (resep A) + T2 (resep B). Void T2 → **resep A milik T1 ikut BATAL**,
kunjungan COMPLETED; T1 tetap BAYAR (uangnya dihitung, obatnya tidak akan diserahkan).
Sebab: pembatal resep/racikan memilih per `id_kunjungan`, bukan per transaksi — padahal
racikan sudah menyimpan `id_transaksi`. Pola sama dengan Temuan 27 (nota per kunjungan),
yang dulu diperbaiki hanya untuk cetak.

**T2-3 ✅ DIPERBAIKI 2026-10-13 — Kunjungan BATAL masih bisa dibayar dan "hidup lagi".** `proses_bayar` tidak
memeriksa status kunjungan → kunjungan BATAL dibayar → **ANTRI_OBAT**. (Agen juga mencatat
varian bersamaan: `ubah_status` membaca tanpa kunci, jadi BATAL bisa menimpa status sesudah
pembayaran masuk.)

### Terbukti dari kode

**T2-4 ✅ DIPERBAIKI 2026-10-13 — FO bisa melewati kasir.** Menu "Ubah" antrian (role FO/Admin/Owner) menawarkan
ANTRI_BAYAR → **COMPLETED** (juga KONSULTASI → ANTRI_OBAT). Tindakan selesai, tanpa
transaksi, keluar dari antrian kasir, dan gerbang tutup kasir lolos. DEC-015 menjanjikan
validasi pra-bayar yang tak pernah dibuat. Daftar transisi juga ditulis DUA kali (route +
service, "keep in sync") — §4.1.

**T2-5 ✅ DIPERBAIKI 2026-10-13 (⚠ keputusan kebijakan DITANDAI UNTUK DITINJAU) — BATAL tidak mengembalikan apa pun.** `ubah_status` → BATAL hanya mengubah status.
Kuota membership sudah dipakai saat SOAP disimpan → **hilang**; sesi series yang sudah
SCHEDULED → **tersangkut** selamanya (hanya void yang mengembalikannya; tidak ada di daftar
"Pakai Sesi").

**T2-6 ✅ DIPERBAIKI 2026-10-13 — Sesi 2..N series bisa dipakai GRATIS walau sesi 1 (pembawa harga paket) tak
pernah ditagih.** `use_session` hanya cek rencana PENDING; harga sesi > 1 selalu Rp 0.
Contoh: series 6× dibatalkan sebelum bayar → 5 sesi tetap tersedia gratis.

**T2-7 ✅ DIPERBAIKI 2026-10-13 — Penanda "sudah ditebus" = ada salinan, APA PUN statusnya.** Salinan tebus yang
ditunda / di-void / dibatalkan membuat resep & racikan asli **hilang permanen** dari daftar
tebus (`apotek_service` `sudah_ditebus = exists(...)`). Satu kolom, dua arti (§4.1).

**T2-8 🟠 Tebus resep tanpa validasi** (racikan memvalidasi): baris resep lama disalin
tanpa cek status, salinan yang sudah ada, atau pemilik → klik ganda / dua apoteker = tebus
ganda; halaman basi bisa menyalin resep yang sudah DIBAYAR.

**T2-9 🟠 Halaman SOAP basi menggandakan racikan yang sudah dibayar/ditunda.** Kartu ber-id
racikan non-PENDING diperlakukan sebagai kartu BARU → baris PENDING kembar, ditagih lagi
sebagai susulan (`racikan_service` "perlakukan sebagai kartu baru").

**T2-10 🟡 Admin/Superadmin bisa menyetujui draf SOAP apoteker dan tercatat sebagai dokter
penulis.** Pagar "hanya dokter yang dituju" hanya berlaku untuk role DOKTER.

**T2-11 🟡 Upsell TREATMENT mengabaikan kuota membership & batas 2 transaksi** — penulis
kedua `kunjungan_tindakan` (§4.1). Pasien VIP berkuota ditagih penuh lewat upsell, Rp 0
lewat SOAP dokter. Bisa jadi kebijakan — perlu keputusan.

**T2-12 🟡 Simpan SOAP: kegagalan blok racikan/diagnosa/kontrol ditelan diam-diam.**
SOAP+resep+status sudah di-commit; blok kedua gagal → rollback, redirect normal tanpa pesan.
Pemicu nyata belum ditemukan (field dibatasi), tapi penelanannya pasti.

### Perbaikan T2-1, T2-3, T2-4 (disetujui dr. Hansen 2026-10-13)

- **T2-1:** `proses_bayar` → ANTRI_OBAT juga bila masih ada obat LAMA yang DIBAYAR tapi
  belum diserahkan (`KasirRepository.hitung_obat_dibayar_belum_serah`) — KECUALI kunjungan
  di jalur Obat Tertunda (`tgl_janji_kirim` terisi), yang sisanya sengaja DIBAYAR+COMPLETED.
- **T2-3:** `proses_bayar` menolak kunjungan BATAL, diperiksa SESUDAH kunci baris.
  `ubah_status` kini mengunci baris (`get_by_id_for_update`). Kunci itu kini membaca
  SEGAR (`populate_existing`) — tanpa itu objek di sesi tidak dibaca ulang dan pagar
  memeriksa status lama (dibuktikan oleh test).
- **T2-4:** ANTRI_BAYAR → COMPLETED dihapus dari mesin status. Dropdown "Ubah" kini
  DITURUNKAN dari `KunjunganService._VALID_TRANSITIONS` (dulu salinan "keep in sync").
- Uji: `tests/integration/test_audit_tahap2.py` (7, memakai `proses_bayar` asli). Dua arah —
  5 suntikan, semuanya tertangkap. Repro: T2-1 kini ANTRI_OBAT, T2-3 kini ditolak.
- ⚠ Masih terbuka dan SENGAJA tidak disentuh (perlu keputusan, dibahas bersama T2-5):
  ANTRI_OBAT → BATAL / COMPLETED lewat menu masih mungkin untuk kunjungan yang obatnya
  sudah lunas; ON_TREATMENT → COMPLETED tetap ada (DEC-015, keputusan terdokumentasi).

### Perbaikan T2-2 (disetujui dr. Hansen 2026-10-13) — migrasi `20261013_0100`

- Kolom `kunjungan_resep.id_transaksi` (sejajar racikan). Penulis: `mark_resep_dibayar` dan
  resep pengganti retur TUKAR. Backfill: transaksi BAYAR paling awal dengan
  `waktu_bayar >= waktu_input` (aturan cutoff susulan kasir) — DB dev: 36/36 baris lunas
  terpasang.
- `KasirService._lingkup_void(trx)`: SATU penentu item milik transaksi, dipakai KEDUA jalur
  void lewat semua pembantunya — pembatal resep/racikan, pengembalian kuota, pembatal series
  (hanya bila transaksi ini menagih SESI 1), pagar "tindakan selesai" & "obat diserahkan".
  Satu transaksi → perilaku lama utuh (aman untuk data lama). Beberapa transaksi + item
  lama tanpa penanda → 409, void TIDAK dijalankan (menolak, bukan menebak).
- Ikut terbukti & diperbaiki: tindakan SELESAI di T1 dulu MENGHALANGI void T2 yang hanya
  berisi obat; void dulu selalu memajukan kunjungan ke COMPLETED walau obat transaksi lain
  masih menunggu → kini tetap ANTRI_OBAT.
- `trx_dan_nilai_bersih` (retur/refund) kini membaca `id_transaksi` dulu; pencarian lewat
  waktu tinggal cadangan untuk baris lama.
- Uji: 6 test baru di `test_audit_tahap2.py` + 1 assert di `test_retur_pasien.py`; dua arah
  — 6 suntikan, semua tertangkap. Repro: void T2 kini hanya membatalkan resep B.
- Catatan pemeriksa (BUKAN akibat T2-2): `cek_serah_tanpa_lot` menemukan resep #860
  (pengganti retur TUKAR, 05/10 19:28) tanpa jejak lot — lot Clarolid pertama baru dibuat
  19:56. Stok minus diizinkan (filosofi klinik); data trial run → diabaikan.

### Perbaikan T2-5 — ⚠ DITINJAU dr. Hansen di akhir

dr. Hansen meminta audit diteruskan dan ditinjau di akhir; dua keputusan kebijakan berikut
diambil dari USULAN yang sudah disampaikan, BUKAN keputusan beliau:
1. **Kunjungan yang sudah dibayar tidak bisa di-BATAL** — 409 "batalkan lewat VOID
   transaksinya dulu". Ini sekaligus menutup kasus terbuka T2-4 (ANTRI_OBAT → BATAL
   menelantarkan obat lunas).
2. **Kunjungan dengan tindakan SELESAI tidak bisa di-BATAL** — "tagih lewat kasir" (sejalan
   §7 "void hanya untuk tindakan yang belum selesai").

Yang dikembalikan saat BATAL (`KunjunganService._bereskan_batal`, satu commit bersama
status): kuota membership tiap tindakan ber-kuota; sesi series yang DIJADWALKAN ke kunjungan
ini → PENDING; series yang LAHIR di kunjungan ini → CANCELLED (sesi 1 pembawa harga paket
tak pernah dibayar — menutup jalur utama T2-6). ANTRI_OBAT → COMPLETED lewat menu ditolak
bila obat lunas belum diserahkan (kecuali jalur Obat Tertunda).
Uji: 6 test (`test_audit_tahap2.py`), dua arah — 5 suntikan semua tertangkap.

### Perbaikan T2-6

`SeriesService._pagari_sesi_1_lunas` (dipanggil `use_session`): sesi 2..N series DOKTER
hanya boleh dipakai bila tindakan SESI 1 sudah masuk transaksi BAYAR (snapshot
`transaksi_detail_tindakan`); data pra-F3 → cukup ada transaksi BAYAR di kunjungan pembuat.
Tidak dipagari: sesi 1 sendiri, rencana tanpa kunjungan pembuat, rencana yang sesi 1-nya
tak ditemukan (sumber lain/data lama). Jalur BATAL sudah ditutup T2-5.
Uji: 3 test; dua arah — 3 suntikan. ⚠ Suntikan "bukti lunas mengabaikan status BAYAR"
sempat LOLOS (tak ada test sesi 1 yang transaksinya VOID) → test ditambahkan, kini tertangkap.

### Perbaikan T2-7

SATU definisi di `app/services/_tebus.py`: sudah ditebus = ada salinan yang MASIH HIDUP
(PENDING / DIBAYAR / DISERAHKAN) di kunjungan yang TIDAK dibatalkan. Dipakai daftar tebus
resep, daftar tebus racikan, dan penyalin racikan (dulu tiga potongan kode, tiga definisi
"salinan apa pun"). Salinan PENDING tetap menyembunyikan aslinya — mencegah tebus ganda.
Uji: 8 test (6 status salinan resep + 2 racikan); dua arah — 2 suntikan tertangkap.

### Kandidat — belum dibuktikan
- Series treatment sama dua kali di satu kunjungan → sesi 1 menagih jumlah gabungan.
- Void mengembalikan kuota tapi tindakannya tetap ber-`id_kuota_member` → bisa ditagih Rp 0
  sesudahnya (butuh urutan khusus).

### Diperiksa — BERSIH (dari laporan agen, tidak diperiksa ulang satu per satu)
Kunci kuota/series/serah; pagar void tindakan SELESAI; komisi anti-dobel per `id_ref`;
snapshot `transaksi_detail_tindakan` + sisa pembulatan; cutoff susulan satu jam (DB);
harga racikan terkunci; pagar SOAP basi untuk diagnosa & racikan PENDING; draf apoteker
dikecualikan dari SOAP terakhir; pagar alergi sebelum persetujuan draf.
