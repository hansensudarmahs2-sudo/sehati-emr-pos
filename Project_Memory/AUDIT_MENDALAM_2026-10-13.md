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
| 2 | Klinis: antrian → SOAP → diagnosa → tindakan → resep/racikan → draf apoteker | belum |
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
