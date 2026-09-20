# Desain Modul Obat Racikan (Formula + Kalkulator + Kasir)

Status: **DRAFT — menunggu persetujuan dr. Hansen**. Tanggal: 2026-09-20.

## Keputusan yang sudah dikunci
1. **Pembulatan**: butir sumber dibulatkan **ke atas**, dan **pasien ditagih hasil pembulatan itu** (18,75 → 19 butir). Stok juga terpotong 19 → uang dan barang selalu konsisten.
2. **Biaya racik**: **flat per jenis racikan** (kapsul / puyer / krim), berapa pun jumlah unitnya.
3. **Template**: 4 produk RACIKAN flat yang sudah ada (Tab SR, SR 2, SRO, STR) **dikonversi jadi Formula Racikan siap pakai** — dokter tinggal mengubah dosis/jumlah unit.
4. **Kewenangan**: racikan disusun **dokter di SOAP saja**; apoteker menyiapkan, tidak mengubah.

## Prinsip inti
**Dokter menghitung sekali di SOAP, kasir tidak menghitung apa pun.** Hasil hitung di-*snapshot* ke resep (bahan, butir dipakai, harga saat itu, biaya racik, total). Kasir hanya membaca satu baris yang bisa dibuka rinciannya. Ini mengunci harga (harga bahan bisa berubah besok) dan memberi jejak audit — pola snapshot yang sama seperti PO, retur, dan diagnosa.

## Rumus
Untuk tiap bahan *i* dalam satu racikan berisi **N** unit:
```
total_mg_i = dosis_per_unit_i × N
butir_i    = total_mg_i ÷ kekuatan_sumber_i
dipakai_i  = CEIL(butir_i)                  ← ditagih & dipotong dari stok
biaya_i    = dipakai_i × harga_per_butir_i

TOTAL = Σ biaya_i + biaya_racik(jenis)
```
Contoh (Stenirol 8 mg, Rp 7.500/butir; minta 10 mg × 15 kapsul):
`150 mg ÷ 8 = 18,75 → 19 butir × 7.500 = 142.500` + biaya racik kapsul.

---

## PRASYARAT — dua hal yang harus dibereskan dulu

### A. Kekuatan sediaan belum jadi data
Angka kekuatan saat ini hanya ada di dalam *nama* ("Stenirol 8 mg"), tidak bisa dihitung mesin.
→ Tambah kolom di `master_produk`: `kekuatan_nilai` DECIMAL(10,3) + `kekuatan_satuan` VARCHAR(10) (`mg`/`ml`/`g`).
→ Backfill 74 obat minum dengan mem-parse angka dari nama, lalu **diverifikasi manual** oleh dr. Hansen (beberapa nama tidak memuat angka, mis. "Ivermectin", "Stromag", "Dermapro").

### B. Bahan yang belum ada di master
Komposisi template lama menyebut **Metcor**, yang **tidak ada** di 74 obat minum. Perlu ditambahkan (nama, kekuatan, harga) sebelum Tab SR/SR 2 bisa dikonversi. Bahan lain sudah ada: Stenirol 8/16 mg, Rydian 10 mg, Oxtin 30 mg, Triamcort 4 mg.

Catatan konversi template lama (dosis dibaca dari kolom `kandungan`):
- **Tab SR** — Stenirol 8 mg + Rydian 7 mg + Metcor 2 mg
- **Tab SR 2** — Stenirol 4 mg + Rydian 5 mg + Metcor 2 mg
- **Tab SRO** — SR + Oxtin ½ tab (= 15 mg)
- **Tab STR** — Stenirol 6 mg + Triamcort 2 mg + Rydian 7 mg

---

## Skema DB

### 1) `master_biaya_racik` — tarif flat per jenis
| kolom | tipe | catatan |
|---|---|---|
| id_biaya_racik | PK | |
| jenis_racik | varchar(20) unik | KAPSUL / PUYER / KRIM (bisa ditambah) |
| nama | varchar(50) | mis. "Racik Kapsul" |
| tarif | decimal(12,2) | flat per racikan |
| is_active | bool | |

### 2) `master_racikan` — Formula (template). Menyimpan KOMPOSISI, bukan harga.
| kolom | tipe | catatan |
|---|---|---|
| id_racikan | PK | |
| nama | varchar(100) | mis. "Tab SR" |
| jenis_racik | varchar(20) | → master_biaya_racik |
| default_jumlah_unit | int | mis. 15 |
| default_aturan_pakai | varchar(100) null | |
| catatan | text null | |
| is_active | bool | |

### 3) `master_racikan_bahan` — komposisi formula
| kolom | tipe | catatan |
|---|---|---|
| id | PK | |
| id_racikan | FK → master_racikan | |
| id_produk | FK → master_produk | bahan sumber |
| dosis_per_unit | decimal(10,3) | mg per kapsul/bungkus |
| satuan_dosis | varchar(10) | default 'mg' |
| urutan | int | |

### 4) `kunjungan_racikan` — racikan yang diresepkan (SNAPSHOT)
| kolom | tipe | catatan |
|---|---|---|
| id_kunjungan_racikan | PK | |
| id_kunjungan | FK | |
| id_racikan | FK null | null = ad-hoc |
| nama_snapshot | varchar(100) | |
| jenis_racik | varchar(20) | |
| jumlah_unit | int | N |
| aturan_pakai | varchar(100) null | |
| subtotal_bahan | decimal(12,2) | Σ biaya bahan |
| biaya_racik | decimal(12,2) | snapshot tarif |
| total | decimal(12,2) | |
| status_item | varchar(20) | ikut pola kunjungan_resep |
| created_at | timestamp | |

### 5) `kunjungan_racikan_bahan` — rincian per bahan (SNAPSHOT)
| kolom | tipe | catatan |
|---|---|---|
| id | PK | |
| id_kunjungan_racikan | FK | |
| id_produk | FK null | untuk potong stok |
| nama_snapshot | varchar(100) | |
| dosis_per_unit | decimal(10,3) | |
| kekuatan_snapshot | decimal(10,3) | mg per butir saat itu |
| butir_dipakai | decimal(10,2) | hasil CEIL |
| harga_per_butir | decimal(12,2) | snapshot |
| subtotal | decimal(12,2) | |

---

## Alur di SOAP (dokter)
Tombol **“+ Racik”** di bagian Resep → muncul **kartu racikan**:
1. **Template**: pilih Formula (mis. Tab SR) atau kosong (ad-hoc). Memilih template mengisi jenis, komposisi, dan jumlah unit default.
2. **Jenis racik** (kapsul/puyer/krim) + **jumlah unit (N)**.
3. **Tabel bahan**: cari produk → isi dosis per unit (mg). Kolom terhitung otomatis: `butir dipakai`, `harga`.
4. **Footer**: subtotal bahan + biaya racik + **TOTAL**.
5. Aturan pakai + nama racikan (untuk etiket).

**Cepatnya: pilih template → ubah N atau dosis → selesai.**

**Cara hitung ulang**: setiap perubahan memicu render ulang **seluruh kartu dari server** (`/web/dokter/_racik-hitung`), bukan hitung di JavaScript. Ini mengikuti pelajaran dari modul Smart Fill — lihat memory `sehati-htmx-ui-gotcha`: panel dinamis = *derived view* dari server, jangan sinkronisasi state di klien.

## Alur di Kasir
Tagihan menampilkan **satu baris**: `Racikan — Tab SR (15 kapsul) … Rp 162.500`, bisa di-expand jadi rincian bahan. **Tidak ada hitungan ulang.** Perlu diperiksa saat build: bentuk baris di `transaksi_detail_produk` (satu baris racikan vs pecah per bahan) — usulan: satu baris racikan, rincian tetap tersimpan di tabel snapshot.

## Stok
Saat racikan diserahkan/dibayar (ikut alur resep yang sudah ada), stok tiap **bahan sumber** dipotong sebesar `butir_dipakai` lewat FEFO `stok_lot`. Ini memperbaiki kebocoran template flat yang sekarang: Tab SR terjual tanpa memotong Stenirol/Rydian/Metcor sama sekali.

## Rencana build bertahap
- **Fase 1 — Fondasi data**: kolom `kekuatan_nilai/satuan` + backfill 74 obat (untuk diverifikasi), tabel `master_biaya_racik` + isi tarif, tambah produk Metcor.
- **Fase 2 — Master Formula Racikan**: CRUD formula + komposisi; konversi 4 template lama; nonaktifkan produk flat-nya.
- **Fase 3 — Kartu Racik di SOAP**: kalkulator server-side + snapshot ke resep.
- **Fase 4 — Kasir, stok, etiket**: tagihan + potong stok bahan + cetak.

Tiap fase: uji desktop → deploy mini PC → commit.

---

# REVISI 2026-09-20 (sore) — setelah file `LIST PRODUK JODERMA.xlsx`

## Keputusan tambahan (terkunci)
5. **Tarif biaya racik**: Kapsul **Rp 50.000**, Puyer **Rp 50.000**, Krim **Rp 0** (flat per racikan).
6. **Metcor**: ditambahkan sebagai produk, **disamakan dengan Stenirol 8 mg** (kekuatan 8 mg, harga & HPP mengikuti Stenirol).
7. **Bahan krim/topikal dihitung PRO-RATA PER GRAM**, bukan dibulatkan per kemasan:
   `harga_per_gram = harga_jual ÷ ukuran_jual` (mis. 150.000 ÷ 10 gr = 15.000/gr; pakai 5 gr → 75.000).
   → Racikan punya **dua mode**: **MG/tablet** (bulat ke atas per butir) dan **GRAM/krim** (pro-rata).
   → Konsekuensi skema: `master_produk` butuh **isi kemasan** (`isi_kemasan` DECIMAL + `satuan_isi`, mis. 10 + 'gr') sebagai penyebut.
8. **Dampak harga diterima**: konversi template lama menaikkan harga (Tab SR ±12.000 → ±19.200/kapsul untuk 15 kapsul). Harga mengikuti hitungan biaya bahan + ongkos racik.

## FASE 0 (BARU, wajib duluan) — Refresh master data dari `LIST PRODUK JODERMA.xlsx`
Data yang baru di-seed sudah ketinggalan. Yang harus di-refresh:
- **28 obat minum naik harga** (kolom "Harga Baru"): Cefixime 7.000→8.000, Cetirizine 1.000→2.000, Stenirol 8mg 8.000→8.500, Triamcort 6.000→7.000, Inclovir 31.000→35.000, dll.
- **HPP nyata**: 68/75 obat minum punya "Harga Beli"; 79/80 topikal punya "Harga Modal". Saat ini semuanya `hpp_per_unit = 0` → **komisi dokter 5% dari margin sekarang KELEBIHAN** (margin dihitung dari harga penuh). Wajib diperbaiki.
- **Golongan topikal** (kolom baru kita sudah siap): STEROID 9, ANTIBIOTIK 11, ANTIFUNGI 4, ANTIVIRUS 2, ANTIPARASIT 1, TOPIKAL ESTETIK 44, SABUN & SHAMPO 9.
- **Ukuran/isi kemasan** topikal (10 gr, 15 gr, 25 ml, 30 gr) → penyebut untuk racikan krim pro-rata.
- Tambah produk **Metcor**.

## Urutan kerja yang disepakati
1. **Deploy + commit** pekerjaan 2026-09-20 (golongan, 74 obat minum, cari kandungan, Smart Fill).
2. **Fase 0** — refresh master data di atas.
3. **Fase 1–4** modul racikan seperti rencana.

## Sisa yang perlu dari dr. Hansen
- Verifikasi hasil backfill **kekuatan sediaan** (di-parse dari nama obat; beberapa tidak memuat angka: Ivermectin, Stromag, Dermapro, dll) — akan saya siapkan daftarnya untuk dicek.
