# Integrasi EMR Multi-Situs (JoDerma) — Perencanaan / Design Note

Status: **PERENCANAAN saja. Belum ada kode/skema yang diubah.** Read-only analysis.
Ditulis: 2026-09-09. Pemicu: backup EMR dr. Yohanes (Klinik Dryn) di-share sebagai contoh.
Konteks ekosistem JoDerma: beberapa klinik dengan sistem EMR berbeda-beda perlu "nyambung".

Situs & sistem yang diketahui:
- **Dryn** (dr. Yohanes) — EMR berbasis Laravel/MySQL. Dump sudah ada (contoh nyata).
- **Sehati eMR-POS** — sistem sendiri (FastAPI+MySQL, terstruktur, sedang menuju go-live).
- **Jemursari** — pakai **Omnicare** (vendor pihak ketiga). **Format belum didapat.**

> Catatan PHI: file `Medis Backup.sql` = data medis ±13.6k pasien klinik lain. JANGAN commit ke
> git/GitHub atau taruh di folder tersinkron. Simpan terpisah, akses terbatas. Semua kerja
> integrasi harus di lingkungan terpisah dari Sehati produksi.

---

## 1. Temuan dari backup Dryn (dasar perencanaan)

Aplikasi Laravel/MySQL. 10 tabel; inti klinis = `pasien` + `rm`. Volume: ±13.591 pasien, ±12.453 rekam medis.

Karakter yang menentukan strategi integrasi:
- **Datar & teks-bebas.** `rm` menyimpan SOAP sebagai kolom teks: `ku, subjektif, objektif, lab, hasil,
  plans, diagnosis, resep, jumlah, aturan, dokter`.
- **Tanpa kode standar.** `diagnosis` = varchar bebas (bukan ICD-10). `dokter` = nama teks.
- **Resep tak terstruktur.** `resep`/`jumlah`/`aturan` = 3 kolom teks paralel (bukan line-item).
  Delimiter perlu dikonfirmasi saat bangun adapter (hindari buka PHI sampai perlu).
- **Relasi lemah.** `rm.idpasien` = varchar (bukan FK int). Nama pasien diduplikasi ke `rm`.
- **Skema tak konsisten dalam 1 sistem.** Ada tabel kedua `pos` (mirip `rm` tapi kolom beda:
  `anamnesis`/`pxfisik` terpisah, `idpasien`/`dokter` int) — ~24 baris. Bukti nyata: bahkan satu
  vendor pun bisa punya >1 bentuk data.
- **Billing minimal.** `obat`/`lab` master kecil (harga/stok); tak ada tabel transaksi/pembayaran.
- **Identitas.** `norm` (No.RM unik) + `no_bpjs`; tak ada NIK. Kontak `hp`, `alamat`.
- Soft-delete `deleted` + `created_time/updated_time` di semua tabel.

Pelajaran umum: **tiap situs = skema sendiri, sering datar, uncoded, identitas beda.** Ini masalah
inti yang harus diselesaikan arsitektur, bukan ditambal per-kasus.

---

## 2. Keputusan arsitektur inti: HUB kanonik + adapter (bukan pairwise)

Integrasi langsung antar-sistem (A↔B↔C) meledak secara kombinatorik (n sistem → n²/2 pemetaan) dan
rapuh. Pola yang dipakai:

```
  Dryn ──adapter──┐
  Sehati ─adapter─┼──►  MODEL KANONIK (HUB / data lake)  ──► View terpadu / Analitik / Council AI
  Omnicare adapter┘         (Pasien, Encounter, Dx, Obat)
```

- **Model kanonik**: satu skema perantara netral (tak meniru sistem mana pun).
- **Adapter per-sumber**: extract → transform → map ke kanonik. Tambah sumber baru = tambah 1 adapter,
  hub tak berubah.
- **Read-only satu arah dulu** (situs → hub). Sinkron dua-arah / migrasi = fase jauh kemudian.

### Arah integrasi — DUA keputusan yang harus dikunci dulu (lihat §8)
- **A. Federasi vs Migrasi.** Federasi = tiap klinik tetap pakai sistemnya, hub menyatukan untuk
  lihat/analitik. Migrasi = semua pindah ke Sehati. → Rekomendasi: **federasi (hub read-only) dulu.**
- **B. Tujuan hub.** Analitik/Council AI lintas-klinik? atau "unified patient view" klinis? atau
  keduanya? → Menentukan kedalaman normalisasi (analitik boleh kasar; klinis wajib akurat).

---

## 3. Skema kanonik v0 (draft — belum dibuat, hanya rancangan)

Netral, ber-sumber-jejak, menyimpan mentah + hasil normalisasi.

- **`c_patient`**: `patient_uid` (dibuat hub), `source_system`, `source_patient_id`, `norm`, `nik`,
  `bpjs`, `nama`, `tgl_lahir`, `jenis_kelamin`, `hp`, `alamat`, `alergi_raw`, `created/updated_src`,
  `match_status`, `match_confidence`.
- **`c_encounter`**: `encounter_uid`, `patient_uid`, `source_system`, `source_encounter_id`, `tanggal`,
  `dokter_raw`, `keluhan_utama`, `subjektif`, `objektif`, `assessment_raw`, `plan`, `source_row_json`
  (simpan baris asli utuh untuk audit/reproses).
- **`c_diagnosis`**: `encounter_uid`, `teks_asli`, `icd10_code` (nullable), `confidence`, `coder`
  (manual/auto/none).
- **`c_medication_line`**: `encounter_uid`, `obat_teks`, `obat_master_id` (nullable), `jumlah`,
  `satuan`, `aturan`, `parsed_ok` (bool).
- **`c_observation`** (lab/vital): `encounter_uid`, `nama`, `nilai`, `satuan`, `teks_asli`.
- **`c_identity_link`**: `patient_uid` ↔ (`source_system`, `source_patient_id`), `method`
  (deterministic/probabilistic/manual), `confidence`, `verified_by`, `verified_at`.
- **`c_source_registry` / `c_adapter_run`**: catat tiap sumber + tiap batch ingest (kapan, berapa baris,
  error) → observability & idempotensi.

Prinsip: **selalu simpan `source_row_json`** (mentah) supaya normalisasi bisa diulang saat aturan
mapping membaik, tanpa minta ulang data ke situs.

---

## 4. Peta field: Dryn → Kanonik → Sehati (draft awal)

| Dryn | Kanonik | Sehati (rujukan) | Catatan transform |
|---|---|---|---|
| `pasien.norm` | `c_patient.norm` | `pasien.no_rm` | kunci identitas per-sumber |
| `pasien.no_bpjs` | `c_patient.bpjs` | (belum ada) | kandidat kunci lintas-situs |
| `pasien.nama` | `c_patient.nama` | `pasien.nama` | normalisasi kapitalisasi/gelar |
| `pasien.tgl_lhr` | `tgl_lahir` | `tgl_lahir` | langsung |
| `pasien.jk` | `jenis_kelamin` | `jenis_kelamin` | map "L/P" vs enum Sehati |
| `pasien.hp`,`alamat` | `hp`,`alamat` | `nomor_telepon`,`alamat` | langsung |
| `pasien.alergi` (teks) | `alergi_raw` | `pasien_alergi` (terstruktur) | perlu NLP/parse ringan |
| `rm.ku` | `keluhan_utama` | `keluhan_utama` | langsung |
| `rm.subjektif`+`objektif` | `subjektif`/`objektif` | SOAP anamnesa/pemeriksaan | langsung-ish |
| `rm.diagnosis` (teks) | `c_diagnosis.teks_asli` | `diagnosa` | **butuh mapping ICD-10** |
| `rm.resep`/`jumlah`/`aturan` | `c_medication_line[]` | `kunjungan_resep` | parse paralel + match master obat |
| `rm.lab`/`hasil` | `c_observation[]` | (lab modul) | parse teks |
| `rm.dokter` (nama) | `dokter_raw` | `master_staf` | match by nama (fuzzy) |

Gap inti: **Dryn teks-bebas & uncoded → Sehati terstruktur.** Integrasi = *normalisasi + enrichment*,
bukan copy. Bagian tersulit & butuh review manusia: **diagnosis→ICD** dan **resep→line-item + master obat**.

---

## 5. Patient identity matching (tak ada ID global)

Bertingkat, dari paling pasti ke paling ragu:
1. **Deterministik dalam-sumber**: `norm` unik per sistem.
2. **Deterministik lintas-sumber**: `bpjs`/`nik` bila ada & valid.
3. **Probabilistik**: normalisasi `nama` + `tgl_lahir` + `jenis_kelamin` (+ `hp`) → skor kemiripan.
4. **Antrian review manual** untuk skor ambigu — jangan auto-merge pasien saat ragu (risiko klinis).

Simpan semua keputusan di `c_identity_link` (bisa di-audit & dibatalkan). Prinsip: **lebih baik dua
record terpisah daripada salah-gabung** dua orang.

---

## 6. Omnicare (Jemursari) — slot kosong

Belum ada format. Yang perlu diminta ke vendor/klinik SEBELUM bisa bikin adapter:
- Contoh **export** (dump DB / CSV / API sample) — de-identifikasi bila mungkin.
- **Kamus data / skema** (daftar tabel+kolom) atau dokumentasi API + metode auth.
- Kebijakan: apakah boleh export berkala (file-drop) atau harus via API.

Begitu formatnya datang → cukup tulis **1 adapter Omnicare→kanonik**; hub & adapter lain tak berubah.

---

## 7. Tata kelola, keamanan & legal (WAJIB sebelum data mengalir)

- **Persetujuan/legal antar-entitas**: data pasien pindah antar badan usaha butuh dasar hukum +
  consent + perjanjian pemrosesan data. Ini gerbang non-teknis.
- **Lingkungan terpisah**: hub bukan di server Sehati produksi. DB & akses sendiri, least-privilege.
- **PHI hygiene**: jangan pernah commit dump ke git; enkripsi at-rest untuk hub; audit akses.
- **Satu arah dulu**: situs → hub (read-only). Tak ada write-back ke sistem sumber di fase awal.
- **Minimisasi**: untuk tujuan analitik/Council AI, pertimbangkan **pseudonimisasi** (hash identitas)
  sehingga hub analitik tak menyimpan PII penuh.

---

## 8. Keputusan terbuka (perlu jawaban dr. Hansen)

1. **Federasi atau migrasi?** (rekomendasi: federasi/hub read-only dulu).
2. **Tujuan hub**: analitik & Council AI lintas-klinik, atau unified patient view klinis, atau keduanya?
3. **Kanonik dari nol atau adopsi standar** (mis. subset FHIR: Patient/Encounter/Condition/MedicationRequest)?
   FHIR = interoperable & masa depan-proof, tapi lebih berat. Kanonik-sendiri = cepat, cukup untuk analitik.
4. **Reuse kontrak raw-data-export Sehati + pipeline Data Analyst** sebagai fondasi kanonik? (hemat kerja).
5. **Cakupan data**: semua riwayat historis, atau hanya sejak tanggal tertentu?

---

## 9. Roadmap bertahap (usulan; belum dieksekusi)

- **F0 — Discovery & legal** (sekarang): kunci keputusan §8; minta format Omnicare; dasar legal/consent;
  konfirmasi delimiter kolom resep Dryn (analisis PHI-aware, terbatas).
- **F1 — Rancang kanonik v0 + hub** (design/DDL saja, lingkungan terpisah).
- **F2 — Adapter Dryn** (sumber terbesar & sudah ada dump) → uji ke hub, ukur kualitas data.
- **F3 — Adapter Sehati** (reuse export contract) → hub.
- **F4 — Identity matching + dedupe** lintas-sumber + antrian review.
- **F5 — Adapter Omnicare** (setelah format didapat).
- **F6 — Hilir**: unified view / analitik / feed Council AI (+ mapping ICD & master-obat bila perlu klinis).

Estimasi kasar: F1–F2 = fokus utama; sisanya bergantung ketersediaan format Omnicare + keputusan §8.

---

## 10. Ringkas
Backup Dryn mengonfirmasi pola yang harus diantisipasi: **skema beragam, datar, uncoded, identitas
tak seragam**. Jawabannya **hub kanonik + adapter per-sumber + identity-matching**, read-only satu arah,
di lingkungan terpisah, dengan gerbang legal/consent lebih dulu. Dokumen ini perencanaan; langkah nyata
menunggu keputusan §8 (terutama federasi-vs-migrasi & format Omnicare).
