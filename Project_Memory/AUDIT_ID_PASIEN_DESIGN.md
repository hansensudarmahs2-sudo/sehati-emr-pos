# Modul Audit Integritas ID Pasien — Design Note (RENCANA / future)

Status: **RENCANA**. Dicatat 2026-09-17 atas arahan dr. Hansen. Belum dibangun.
Tujuan: bukan sekadar menambal duplikat hari ini, tapi punya **alat** untuk
menemukan varian kekeliruan identitas pasien secara berkala.

## Dua lapis perlindungan (pisahkan tegas)

### Lapis 1 — Real-time saat pendaftaran (SUDAH dibangun 2026-09-17)
Deterministik, ketat, TANPA toleransi typo (hindari false-alarm di meja FO):
- **NIK/`nomor_ktp` sama persis** (non-kosong) -> BLOK keras (tak bisa override).
- **Nama (normalisasi huruf besar/kecil, bukan typo) + jenis_kelamin + tgl_lahir sama**
  -> peringatan LUNAK (boleh lanjut dgn konfirmasi).
Lokasi: `pasien_service.find_duplicate_candidates` + UI `pendaftaran_pasien.html`.
NIK opsional (kosong=NULL) supaya anak/tanpa-KTP tetap bisa didaftarkan.

### Lapis 2 — Modul Audit Maintenance (BELUM dibangun)
Dijalankan oleh **dev/IT operational** dalam sesi maintenance (bukan FO, bukan
real-time). Menyisir SELURUH tabel `pasien` untuk kandidat duplikat/keliru,
lalu **tampilkan untuk audit MANUAL** (tidak pernah auto-merge / auto-delete).

Kriteria deteksi (kandidat, makin ke bawah makin "longgar"):
1. **NIK sama persis** (duplikat kuat).
2. **Nama sama persis + 1 field lain sama persis**: (nama+tgl_lahir), (nama+alamat),
   (nama+nomor_telepon).
3. **Kemiripan fuzzy nama** (toleran typo), mis. "budi santoso" ~ "budo santoso"
   -- pakai jarak edit (Levenshtein) / trigram similarity, ambang bisa disetel.
   Ditampilkan sebagai kandidat untuk ditinjau manusia.

Output: worklist/laporan klaster kandidat (grup pasien yang diduga sama), dengan
aksi manual: gabung (merge), koreksi, atau tandai "bukan duplikat" (dismiss).
Merge sungguhan harus memindahkan relasi (kunjungan, transaksi, membership,
alergi, penyakit) dgn hati-hati -> desain terpisah saat modul dibangun.

## Spesimen uji (sengaja dibiarkan)
Di DB live saat ini ADA 1 pasang kembar sengaja untuk mengembangkan/menguji modul:
- id 217 `A-260917-001` (1 kunjungan) & id 218 `JJ-260917-001` (0 kunjungan)
- Keduanya "Hansen Sudarma", L, 1980-10-29, NIK `3173032910800002`.
Karena kembar ini dibiarkan, **unique index DB pada `nomor_ktp` DITUNDA** (migrasi
`20260917_0100` skip-with-warning; perlindungan Lapis 1 tetap aktif). Saat modul
audit siap & data dibereskan: pasang `CREATE UNIQUE INDEX ux_pasien_nomor_ktp ON pasien(nomor_ktp);`.
