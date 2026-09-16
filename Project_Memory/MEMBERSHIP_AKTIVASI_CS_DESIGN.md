# Aktivasi Membership via CS + Nomor Member — Design Note

Status: **PERENCANAAN. Belum ngoding.** Divalidasi arah oleh dr. Hansen 2026-09-16.
Terkait: #362D (drop method usang), P2-5 (revert saat void). Bangun SETELAH: Obat Tertunda, P2-5, drop #362D.

## 1. Perilaku SEKARANG (hasil telusur kode)
1. Set/renew tier di `membership_service` → buat baris `pasien_membership_history` **PENDING**
   (`is_active=False`, `id_transaksi_aktivasi=NULL`). `pasien.tipe_membership` BELUM diubah (FIX-362E-A).
2. `proses_bayar` menemukan pending → menagih biaya aktivasi → saat bayar: set `id_transaksi_aktivasi`,
   `is_active=True`, update `pasien.tipe_membership`, buat kuota. **= AKTIF OTOMATIS SAAT BAYAR.**
3. Diskon dibaca dari `pasien.tipe_membership` (live) → kunjungan berikут dapat benefit (same-day OK).
4. Void transaksi yang mengaktifkan → `revert_active_to_pending` (lihat P2-5).
- Data live: 15 history, semua `pernah_aktif` (jalur ini berjalan). Nomor member: **tidak ada**.
- `pasien_service._create_pending_membership_history_if_needed` = **usang/duplikat → DROP** (#362D).

## 2. Perubahan yang diinginkan (model dr. Hansen)
Bayar **TIDAK** langsung aktif → status "sudah dibayar, menunggu aktivasi" → **CS mengaktifkan** manual.
Alasan: kontrol manusia, verifikasi identitas/kartu, cegah salah-aktivasi.

## 3. Model status baru (disambiguasi)
Sekarang status disimpulkan dari kombinasi `is_active` + `id_transaksi_aktivasi` — dan kombinasi
`is_active=False + id_transaksi NOT NULL` SUDAH dipakai untuk EXPIRED/CANCELLED. Menambah state
"paid-awaiting-activation" akan bentrok. **Rekomendasi: tambah kolom eksplisit
`status_aktivasi`** (enum) di `pasien_membership_history`:
- `PENDING` — tier di-set, belum bayar (`id_transaksi_aktivasi=NULL`).
- `PAID` *(BARU)* — sudah bayar, menunggu aktivasi CS (`id_transaksi_aktivasi` terisi, `is_active=False`).
- `ACTIVE` — diaktifkan CS (`is_active=True`, `id_staf_aktivasi` + `tgl_aktif` terisi).
- `EXPIRED` / `CANCELLED` — akhir hidup.
`is_active` tetap dipertahankan sebagai boolean cepat (ACTIVE⇔True), tapi sumber-kebenaran = `status_aktivasi`.

## 4. Alur baru
1. Set tier → PENDING (seperti sekarang).
2. `proses_bayar` bayar aktivasi → set `id_transaksi_aktivasi` + `status_aktivasi=PAID`.
   **JANGAN** set `is_active`, **jangan** ubah `pasien.tipe_membership`, **jangan** buat kuota dulu.
3. **Aksi CS "Aktifkan Membership"** (dari worklist/detail pasien) → `status_aktivasi=ACTIVE`,
   `is_active=True`, `id_staf_aktivasi`, `tgl_aktif=hari ini`, `tgl_expired` dihitung dari tgl aktivasi,
   buat kuota, set `pasien.tipe_membership`, assign **nomor member** (bila belum). Audit `id_staf`.
4. Benefit berlaku setelah CS aktivasi (same-day tetap bisa: aktivasi sebelum kunjungan berikut).

## 5. Nomor Member (baru)
- Kolom `no_member` (unik, human-facing) — untuk kartu fisik & pencarian cepat.
- **Kapan diberikan:** saat CS aktivasi (nomor hanya untuk member yang benar-benar aktif). *(alternatif: saat PAID)*
- **Format:** sekuensial + prefix. Untuk 1 cabang: mis. `M-000123`. Saat multi-cabang (P2-6/Path A):
  bisa pakai prefix cabang (mis. `JJ-M-000123`) — selaraskan dengan keputusan prefix P2-6.
- Simpan di mana: `pasien` (satu no_member per pasien) atau di history? **Rekomendasi: di `pasien`**
  (1 pasien = 1 nomor member seumur hidup, walau renew berkali-kali).

## 6. Interaksi dengan item lain
- **#362D:** method usang tetap **di-drop**; pending dibuat lewat `membership_service` (tak berubah).
- **P2-5 (void):** void saat PAID → balik ke PENDING (batalkan tagihan). Void saat ACTIVE →
  `revert_active_to_pending` (fix savepoint P2-5 tetap diperlukan). Perlu tangani void di state PAID juga.
- **Same-day:** tak berubah secara teknis (diskon dari `pasien.tipe_membership`); hanya bergeser
  pemicunya dari "bayar" ke "CS aktivasi".

## 7. Perubahan data
- `pasien_membership_history.status_aktivasi` (enum) — migrasi + backfill (existing aktif → ACTIVE,
  existing pending → PENDING).
- `pasien.no_member` (varchar unik, nullable).
- 1–2 migrasi Alembic kecil (chain dari head terkini).

## 8. UI / peran
- **Worklist "Membership Menunggu Aktivasi"** (status PAID) → tombol "Aktifkan".
- Bisa sekalian muncul di notifikasi (pola sama Obat Tertunda) supaya CS tak lupa.
- **Siapa boleh mengaktifkan?** Sistem tak punya role "CS" — kandidat = **FO / Kasir / Admin / Owner /
  Superadmin**. (KEPUTUSAN TERBUKA.)

## 9. Keputusan terbuka (perlu dr. Hansen)
1. **`tgl_aktif`/`tgl_expired` di-anchor ke tgl AKTIVASI (rekomendasi) atau tgl BAYAR?**
2. **Nomor member:** format final + diberikan saat PAID atau ACTIVE? disimpan di `pasien` (rekomendasi)?
3. **Role yang boleh aktivasi** = FO? (atau FO+Kasir+Admin+Owner/Superadmin)
4. **Kuota** dibuat saat aktivasi (rekomendasi) — konfirmasi.
5. Perlukah batas waktu "PAID tapi tak kunjung diaktifkan" (auto-warning, mirip Obat Tertunda)?

## 10. Rencana build (nanti, setelah 3 item prioritas)
- M1. Migrasi `status_aktivasi` + `no_member` + backfill. Model + enum.
- M2. Ubah `proses_bayar`: bayar → PAID (tak auto-aktif). Sesuaikan display tier.
- M3. Aksi CS "Aktifkan" (service + route + tombol) → ACTIVE + kuota + no_member + audit.
- M4. Worklist "Menunggu Aktivasi" + notifikasi. Tangani void di state PAID (nyambung P2-5).
- M5. Verifikasi: py_compile + jinja + test (set→bayar→PAID→aktifkan→benefit; void di PAID & ACTIVE) + smoke.
