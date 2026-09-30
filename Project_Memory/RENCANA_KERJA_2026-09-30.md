# RENCANA KERJA — disusun 2026-09-30

Dikerjakan **satu per satu**, dengan urutan yang mempertimbangkan ketergantungan antar
tugas. Uji di desktop dulu, baru deploy ke mini PC. Yang mengubah skema **wajib minta
persetujuan dr. Hansen** sebelum dieksekusi.

Status mesin saat ini: desktop & mini PC **sejajar**, alembic head `20260927_0100`.
Masih uji coba internal dengan pasien dummy — belum ada database pasien asli.

---

## Urutan

### ⬛ 1. Keluarkan `medical_soap_raw` dari `finance_pack`

**Kenapa pertama:** paling murah, paling langsung mengurangi paparan. SOAP medis sekarang
ikut keluar setiap hari di dalam paket bernama "finance".

**Sudah diverifikasi:** modul Finance **tidak pernah** membaca berkas ini — nol referensi
di kode `finance-ai`, dan ia memang sudah ada di `FINGERPRINT_EXCLUDE`. Mengeluarkannya
tidak merusak jurnal apa pun.

- Tanpa migrasi · tanpa risiko uang · bisa selesai dalam satu langkah
- Periksa juga: siapa yang boleh menjalankan ekspor finance sekarang

### ⬛ 2. Penggabungan pasien ganda + `UNIQUE INDEX` KTP

**Kenapa sebelum clinical pack:** `pasien.digabung_ke_id_pasien` menentukan pseudonim.
Kalau paket klinis dibuat sebelum penggabungan beres, satu orang yang tercatat dua kali
akan muncul sebagai **dua pasien berbeda** — kasus berulangnya terpecah, riwayat
kontrolnya terputus, dan **tidak ada gejala apa pun** bahwa itu terjadi.

- Kembar 217/218 dibereskan dulu, baru pasang `ux_pasien_nomor_ktp`
- **Perlu desain terpisah** — penggabungan menyentuh kunjungan, transaksi, komisi
- ⚠ Migrasi (unique index) → **minta persetujuan**

### ⬛ 3. Clinical pack ber-PII-mask

Desain lengkap: `DESAIN_CLINICAL_PACK_PII_MASK.md` (8 berkas, rincian kolom sudah ada).

Mencakup sekaligus tabel yang **belum pernah ikut ekspor**: `kunjungan_diagnosa`,
`followup`, `kunjungan_racikan`, alergi, penyakit kronis, antropometri.

- Pakai ulang pola file-drop + `smart_export` milik jembatan Finance — jangan bikin baru
- ⚠ Migrasi (tabel peta pseudonim) → **minta persetujuan**
- Pagar PHI untuk peta pseudonim **sudah dipasang lebih dulu** (2026-09-30)

### ⬛ 4. Laporan kasus terbanyak (top diagnosa)

Operasional, di dalam Sehati — untuk dilihat harian, bukan analisis mendalam.

- Data siap di `kunjungan_diagnosa` · **tanpa migrasi**
- Dipisah: medis (ICD10) & estetik (JD-xxx)
- **Perlu diputuskan saat mulai:** hitung semua diagnosa atau hanya yang primer

### ⬛ 5. Combo obat (AB Reguler / Premium)

Desain: `DESAIN_APOTEK_BATCH_DAN_COMBO.md` §B. Dipakai harian untuk GO.

- Harga grup berdiri sendiri — **jangan pernah dihitung ulang dari isinya**
- Nota satu baris → combo semua-atau-tidak (R8, void, refund berlaku seluruhnya)
- Komisi dari harga grup, satu kali
- ⚠ Migrasi (`master_combo`, `kunjungan_combo`) → **minta persetujuan**

### ⬛ 6. Konversi batch (SR/SR2/SRO)

Desain: `DESAIN_APOTEK_BATCH_DAN_COMBO.md` §A.

**Sesudah combo** karena lebih banyak yang bisa salah diam-diam: HPP, lot, ED — dan
salahnya baru ketahuan berbulan-bulan kemudian lewat laporan margin.

- Jangan paksakan mesin racikan (`kunjungan_racikan` butuh `id_kunjungan`)
- HPP hasil wajib dihitung; ED wajib diisi saat batch selesai
- ⚠ Migrasi (`produksi_batch`) → **minta persetujuan**

### ⬛ 7. S1 — CSP + HSTS header

Item keamanan termurah yang menganggur. Dulu menunggu HTTPS; HTTPS Tailscale sudah ada.

- Tanpa migrasi · bagian dari gerbang #33–36, tapi bisa dicicil sekarang

---

## Sesudah itu (belum dijadwalkan)

**Perbaikan:** F3 snapshot line-item Finance · banner "Mode Ubah Konsul" menyesatkan
**Keamanan (gerbang):** S2 pip-audit Docker · S3 least-privilege DB · S4 LUKS ·
S5 kebijakan password · S6 2FA · S7 guard finance API · S8 batas peran baca PHI
**Fitur:** F1 antrian kontekstual · F2 komisi fase 2 · F4 absensi · F6 tenant-scoping ·
F7 dead-code · F8 booking
**Rapi-rapi:** A7 berkas usang · D1 panduan deploy usang · D3 tuning MySQL
**Kecil:** pengaman klik-ganda tombol Simpan SOAP (celah sempit, sudah diuji aman untuk
Back & dua tab)

---

## Gerbang — BUKAN antrean

**Hardening #33–36 dan daftar S1–S8 bukan nomor urut.** Seluruhnya harus tuntas
**sebelum data pasien asli masuk**, bukan "setelah tugas nomor sekian". Keputusan
dr. Hansen, ditegaskan berulang. S1 masuk urutan di atas hanya karena kebetulan murah
dan sudah bisa dikerjakan.

---

## Cara kerja yang dipegang

- Uji di desktop dulu, baru deploy ke mini PC
- Perintah CLI satu per satu, dengan validasi — jangan diborong
- rsync ke mini PC **wajib `--dry-run --checksum`** lebih dulu
  (riwayat git ditulis ulang 2026-09-29 → waktu-ubah semua berkas berubah; tanpa
  `--checksum` seluruh pohon terlihat "berubah" dan dry-run kehilangan gunanya)
- Desain dulu untuk modul besar; **persetujuan sebelum ubah skema**
- Backup mini PC sebelum deploy yang memuat migrasi
- **Periksa dulu, baru bicara** — jangan melaporkan risiko yang belum diuji
