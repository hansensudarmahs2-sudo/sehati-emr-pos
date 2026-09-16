# Obat Tertunda (Pending Delivery) — Design Note

Status: **PERENCANAAN. Belum ngoding.** Menyelesaikan P1-1 (bayar & potong-stok tak atomik)
untuk skenario nyata: pasien bayar hari ini, obat dikirim/diambil besok.
Divalidasi dr. Hansen 2026-09-16. Bangun setelah approve, bertahap.

## 1. Keputusan terkunci
- **Opsi A** — TIDAK menambah status kunjungan baru. Kunjungan tetap ke `COMPLETED`;
  "obat belum diserah" dilacak lewat `kunjungan_resep.status_item = PENDING` (SUDAH ADA).
- **Aksi "Tunda serah"** ada di **apotek** (tahap ANTRI_OBAT). Memilih Tunda **WAJIB isi
  tanggal kirim/ambil** (`tgl_janji_kirim`) + opsional catatan/alamat. Efek: kunjungan →
  `COMPLETED` (kasir bisa Tutup Kasir), resep `status_item` tetap PENDING, **stok BELUM dipotong**.
- **Serah menyusul:** izinkan `serahkan_obat` saat kunjungan sudah `COMPLETED` selama masih ada
  resep PENDING (sekarang hanya boleh saat ANTRI_OBAT). Saat serah → potong stok FEFO +
  `status_item=DISERAH` + audit `id_staf`.
- **Notifikasi (anti-fatigue, tahap awal 2 lapis saja — NO banner):**
  1. **Kartu alert di dashboard** "⚠ N obat belum diserahkan/dikirim" (pola kartu existing).
  2. **Ikon Notifikasi di header kanan-atas** (samping nama/role) dengan **bubble merah + angka**
     bila ada hal penting; klik → dropdown ringkas + link ke worklist. Tahap awal isinya =
     Obat Tertunda; strukturnya dibuat extensible (bisa tambah jenis notif lain nanti).
- **Peran yang melihat notif + worklist:** FO, Kasir, Apotek, Owner, Superadmin, **Admin** (=manager).
- **Sub-fix C** (dikerjakan sekalian): `serahkan_obat` jangan abaikan *shortfall* `consume_fefo`
  (lot kurang → warning/blok, bukan diam); `update_stok_produk` jangan izinkan negatif tanpa alert.

## 2. Perubahan data (minim)
- `kunjungan.tgl_janji_kirim` (Date, nullable) — janji kirim/ambil.
- `kunjungan.catatan_kirim` (String, nullable, opsional) — alamat/kurir/catatan.
- Reuse `kunjungan_resep.status_item` (PENDING/DISERAH/DIBATAL) sebagai sumber kebenaran.
- 1 migrasi Alembic kecil (chain dari head `20260710_2200`). Tak ada enum status baru.

## 3. Definisi & query
- **Obat Tertunda** = kunjungan `COMPLETED` yang punya ≥1 resep `status_item=PENDING`.
- **Jatuh tempo / overdue** = `tgl_janji_kirim <= hari ini`.
- Count untuk badge/kartu = jumlah kunjungan tertunda (atau item). Dihitung di
  `build_shell_context` (sudah ada pola `badge_counts`) — cache ringan.

## 4. Worklist "Obat Tertunda"
Halaman list (pola mirip Follow-up): kolom pasien (No.RM+nama), obat/resep, tgl bayar,
`tgl_janji_kirim` (+ tanda overdue), catatan/alamat, tombol **"Serahkan / Tandai Terkirim"**
(jalankan serah → potong stok + status_item DISERAH + audit) dan **"Ubah tgl kirim"** (reschedule).
Filter: semua / jatuh tempo hari ini / terlewat.

## 5. Alur ringkas
1. Apotek di ANTRI_OBAT: pilih **Serahkan sekarang** (seperti biasa) ATAU **Tunda serah** (wajib tgl).
2. Tunda → kunjungan COMPLETED, resep PENDING, tgl_janji_kirim terisi. Kasir bisa Tutup Kasir.
3. Login berikutnya (FO/Kasir/Apotek/Owner/Superadmin/Admin): kartu dashboard + bubble notif muncul.
4. Saat obat dikirim/diambil: buka worklist → "Serahkan/Tandai Terkirim" → stok terpotong, item DISERAH,
   hilang dari daftar tertunda.

## 6. Edge case / catatan
- **Partial:** status_item per-item → sebagian diserah, sebagian tunda = didukung alami.
- **Batal/refund item tertunda:** lewat jalur void/refund existing → `status_item=DIBATAL`, keluar dari daftar.
- **Reservasi stok:** stok TIDAK dipotong saat Tunda (dipotong saat serah) — sama seperti alur normal
  sekarang; artinya secara teoretis stok bisa habis sebelum kirim. Ini perilaku existing, bukan baru;
  kalau perlu "reservasi" → bahas terpisah (di luar scope v1).
- **Overdue lama:** worklist + kartu tetap menampilkan sampai dibereskan (tidak auto-hilang).

## 7. Rencana build bertahap (usulan; setelah approve)
- G1. Migrasi `kunjungan.tgl_janji_kirim` (+catatan_kirim) + model. Verifikasi.
- G2. Aksi "Tunda serah" di apotek (wajib tgl) + izinkan `serahkan_obat` pasca-COMPLETED. + sub-fix C.
- G3. Service query "obat tertunda" + count (build_shell_context).
- G4. Kartu dashboard + ikon Notifikasi header (bubble+angka) + dropdown.
- G5. Halaman worklist "Obat Tertunda" + tombol serah/reschedule + menu (6 role).
- G6. Verifikasi py_compile + jinja + test regresi (repro: bayar→tunda→tutup kasir OK→serah besok→stok turun) + smoke.

## 8. Verifikasi kunci
- Tutup Kasir TIDAK terblok saat ada obat tertunda (kunjungan sudah COMPLETED).
- Serah pasca-COMPLETED memotong stok FEFO benar + audit.
- Count notif akurat & hilang setelah diserah.

---
## BUILD LOG — 2026-09-16 (G1–G6 selesai; smoke live pending)
Penyesuaian dari desain: penanda "tertunda" = **`kunjungan.tgl_janji_kirim IS NOT NULL`** (bukan status resep;
tak ada status "DISERAH" — enum resep hanya PENDING/BATAL/DIBAYAR). Marker dibersihkan saat serah.
- G1: migrasi `20260916_0100` + kolom `tgl_janji_kirim`, `catatan_kirim` (model kunjungan). Head tunggal.
- G2: `apotek_service.tunda_serah_obat` + serah boleh pasca-COMPLETED (obat tertunda) + clear marker;
  route `/apotek/kunjungan/{id}/tunda-serah` + panel "Tunda serah" di apotek_detail_resep.html.
- G3: `_shared.build_shell_context` +count `obat_tertunda{total,overdue}` (cache 30s) + `can_obat_tertunda`;
  `apotek_service.list_obat_tertunda()`.
- G4: kartu dashboard "Obat belum diserahkan/dikirim" + **ikon 🔔 Notifikasi (bubble+angka) di header** (2-lapis, no banner).
- G5: halaman worklist `/web/obat-tertunda` (route obat_tertunda.py) + template + menu 6 role (Owner/Superadmin/Admin/Kasir/FO/Apoteker).
  Aksi: Serahkan (potong stok) + Ubah tgl.
- Sub-fix C: `serahkan_obat` surface **shortfall FEFO & stok-negatif sebagai WARNING** (audit + pesan), tak blok
  (hormati filosofi "stok boleh minus").
- G6: compileall OK, semua template jinja OK, router+menu OK. **Smoke live (WSL) belum dijalankan.**

SMOKE (WSL, dari /mnt/e/.../sehati_clinic): daftar→bayar obat→di apotek pilih "Tunda serah" (isi tgl)→
kunjungan COMPLETED→kasir bisa Tutup Kasir→cek kartu dashboard + 🔔 badge→buka /web/obat-tertunda→"Serahkan"→
stok terpotong & item keluar daftar. Test regresi otomatis menyusul (butuh DB).
