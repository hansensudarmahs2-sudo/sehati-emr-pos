# Desain Modul Diagnosa (ICD-10 + Estetik Internal) + Auto-fill Paket

Status: **DRAFT — menunggu persetujuan dr. Hansen** (design-first, belum ada koding).
Tanggal: 2026-09-18. Mencakup task #24–#27.

## Keputusan yang sudah dikunci
1. **Sumber ICD**: WHO ICD-10, **subset dermatologi/estetik** (bukan ICD-10-CM US, bukan full). Alasan: relevan, ringan, kompatibel SatuSehat. Bisa ditambah bertahap.
2. **Mapping ICD → tindakan/produk**: **kurasi manual → paket auto-isi**. Pilih diagnosa → baris tindakan & resep terisi otomatis, dokter tetap bisa edit/hapus sebelum simpan.
3. **Diagnosa estetik internal**: **kamus kode sendiri (JD-xxx)** + paket sendiri, default kontrol 2 minggu.
4. **Jumlah diagnosa/kunjungan**: **banyak** (1 primer + beberapa sekunder). Butuh tabel anak.

## Kondisi sekarang (yang diubah)
- SOAP disimpan di `pemeriksaan_klinis`; diagnosa = **1 kolom teks bebas** (`diagnosa` Text).
- `kunjungan` sudah punya `tgl_kontrol_selanjutnya` + `catatan_kontrol`.
- Baris tindakan/resep sudah pakai partial HTMX (`_tindakan_row.html`, `_resep_row.html`) — akan dipakai ulang untuk auto-fill paket.
- **Non-destruktif**: kolom `diagnosa` teks lama **dipertahankan** sebagai "diagnosa naratif" (opsional). Diagnosa terstruktur pindah ke tabel baru.

---

## Skema DB baru (3 tabel)

### 1) `ref_diagnosa` — kamus diagnosa (ICD + estetik jadi satu, dibedakan `sistem`)
| kolom | tipe | catatan |
|---|---|---|
| id_diagnosa | PK int | |
| sistem | enum('ICD10','ESTETIK') | pembeda sumber |
| kode | varchar(20) | mis. `L70.0`, `JD-001` (unik per sistem) |
| nama | varchar(255) | nama Indonesia (yang tampil) |
| nama_en | varchar(255) null | nama Inggris asli (ICD, utk SatuSehat/klaim) |
| kategori | varchar(100) null | grup, mis. "Akne", "Hiperpigmentasi" |
| default_kontrol_hari | int | default kontrol; ICD=7, estetik=14, bisa override per kode |
| is_active | bool | |
| catatan | text null | |

Satu tabel + `sistem` → pencarian diagnosa bisa lintas ICD & estetik sekaligus, mapping paket seragam.

### 2) `diagnosa_paket_item` — isi "paket" per diagnosa (1 diagnosa → N item)
| kolom | tipe | catatan |
|---|---|---|
| id | PK | |
| id_diagnosa | FK → ref_diagnosa | |
| tipe_item | enum('TREATMENT','PRODUK') | |
| id_treatment | FK null | jika TREATMENT |
| id_produk | FK null | jika PRODUK |
| qty_default | decimal | default 1 |
| aturan_pakai_default | varchar(100) null | utk produk (auto-fill resep) |
| urutan | int | urut tampil |
| catatan | varchar(200) null | |

### 3) `kunjungan_diagnosa` — diagnosa tercatat per kunjungan (multi, primer/sekunder)
| kolom | tipe | catatan |
|---|---|---|
| id | PK | |
| id_kunjungan | FK → kunjungan | |
| id_diagnosa | FK → ref_diagnosa (null) | null = fallback teks bebas |
| sistem_snapshot | varchar(10) | snapshot |
| kode_snapshot | varchar(20) | snapshot (tahan rename master) |
| nama_snapshot | varchar(255) | snapshot |
| is_primer | bool | tepat satu primer per kunjungan |
| urutan | int | |
| catatan | varchar(255) null | |
| created_at | timestamp | |

Pola **snapshot** konsisten dengan PO/retur (rekam medis tahan terhadap perubahan master di kemudian hari).

---

## Alur SOAP (task #24 + #25 + #27)

1. **Diagnosa picker (autocomplete / "suggestion shadow")**
   - Kotak ketik di bagian Assessment. Ketik kode atau nama → dropdown menampilkan hasil dari `ref_diagnosa` (ICD + estetik), dengan badge sistem (`ICD10` / `Estetik`).
   - Endpoint HTMX: `GET /web/dokter/_diagnosa-search?q=...` → daftar hasil.
   - Pilih → ditambahkan sebagai **chip/baris diagnosa** pada kunjungan; toggle Primer/Sekunder (default pertama = primer).
   - Boleh beberapa diagnosa. Teks bebas tetap tersedia untuk kasus tak ada di kamus.

2. **Auto-fill tanggal kontrol (task #27)**
   - Saat diagnosa **primer** dipilih, `tgl_kontrol_selanjutnya` di-prefill = hari ini + `default_kontrol_hari` (ICD 7 hr, estetik 14 hr, atau override per kode).
   - Hanya prefill bila field belum diisi/diubah manual (tidak menimpa input dokter).

3. **Auto-fill paket tindakan & produk (task #25)**
   - Saat diagnosa dipilih, sistem memanggil `GET /web/dokter/_paket-diagnosa/{id_diagnosa}` → mengembalikan baris `_tindakan_row.html` & `_resep_row.html` **ter-prefill** (treatment/produk, qty, aturan pakai) untuk di-append ke section Tindakan/Resep.
   - Dokter **review → edit/hapus** sebelum simpan. Tidak ada yang terkirim tanpa konfirmasi simpan.
   - Anti-dobel: kalau paket item sudah ada di daftar, tidak digandakan (opsional: tandai/skip).

---

## Master Admin (yang perlu dibuat)
- **Master Diagnosa** (`/web/master/diagnosa`): CRUD `ref_diagnosa` — tambah/edit diagnosa, set kategori & `default_kontrol_hari`, aktif/nonaktif. Filter per sistem.
- **Editor Paket** (di halaman edit diagnosa): kelola `diagnosa_paket_item` — tambah treatment/produk + qty + aturan pakai default.
- Role: Superadmin/Owner/Dokter (sesuaikan dengan `require_master_data_role`).

## Data awal (seed)
- **ICD-10 subset derma/estetik** (~150–250 kode kurasi): chapter L (akne L70, melasma/hiperpigmentasi L81, dermatitis L20–L30, urtikaria L50, psoriasis L40, rosacea L71, vitiligo L80, alopecia L63–L65, keratosis seboroik L82, dll) + beberapa kode umum (mis. veruka B07). Nama Indonesia + nama_en.
  - Tool ICD-10-CM yang ada dipakai sebagai **referensi bantu** untuk deskripsi kode kategori yang sama; nilai final disimpan sebagai **WHO ICD-10** agar bersih untuk SatuSehat.
- **Estetik JD-xxx**: daftar awal dari dr. Hansen (mis. JD-001 "Peremajaan kulit", JD-002 "Rejuvenasi pori", dst) + paket masing-masing. *(butuh input daftarmu)*
- Seed berupa CSV + script (pola sama seperti seed produk/treatment), reusable desktop → mini PC.

## SatuSehat (relevansi ke depan)
Karena kode disimpan sebagai **WHO ICD-10** + `nama_en`, saat integrasi SatuSehat nanti tinggal memetakan `kode` ke resource Condition (ICD-10) — tidak perlu migrasi ulang. Estetik JD-xxx tidak dikirim ke SatuSehat (internal saja).

---

## Rencana build bertahap (tiap fase: uji desktop → deploy mini PC → commit)
- **Fase A — Skema & seed**: model + migration 3 tabel; seed ICD subset + estetik awal. *(butuh persetujuan sebelum mulai)*
- **Fase B — Master Diagnosa + Editor Paket**: CRUD kamus & paket.
- **Fase C — SOAP diagnosa picker**: autocomplete multi-diagnosa primer/sekunder + auto-fill tgl kontrol.
- **Fase D — Auto-fill paket**: diagnosa → prefill tindakan/resep.
- **Fase E — Rapikan cetak/laporan**: tampilkan diagnosa terstruktur di cetak SOAP & laporan; catatan kesiapan SatuSehat.

## Yang masih perlu darimu (sebelum Fase A)
1. **Daftar estetik JD-xxx awal** + paketnya (bisa menyusul; Fase A bisa jalan dengan ICD dulu).
2. Konfirmasi **default kontrol**: ICD 7 hari, estetik 14 hari — dipakai sebagai default global, tetap bisa override per kode. OK?
3. Apakah **teks diagnosa bebas lama** cukup dijadikan "naratif opsional" (rekomendasi), atau mau dihapus dari form?
