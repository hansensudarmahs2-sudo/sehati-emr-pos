# Cek Kelengkapan Audit Transisi Status Kunjungan

**Tanggal:** 2026-07-07 · Pendamping `HANDOFF_DATA_ANALYST_MODULE.md` §6.
**Tujuan:** memastikan setiap perpindahan `status_antrian` meninggalkan jejak audit (from→to, waktu, siapa), agar Data Analyst bisa merekonstruksi timeline. **Metode:** telusuri semua mutasi `kunjungan.status_antrian` + jalur pembayaran.

---

## Temuan — semua jalur transisi TERAUDIT (with from→to) ✅

| Jalur / event | Lokasi | `aksi` | from/to (`data_lama`/`data_baru`) |
|---|---|---|---|
| FO ubah status | `kunjungan_service.ubah_status` | `STATUS_UPDATE` / `BATAL` | ✅ eksplisit |
| Dokter (SOAP → tahap) | `pemeriksaan_service:399` | `STATUS_UPDATE` | ✅ |
| Mulai/selesai tindakan | `treatment_service:220/331` | `TINDAKAN_START` / `TINDAKAN_END` (+ `STATUS_UPDATE`) | ✅ |
| Tebus sesi series → ANTRI_TREATMENT | `series_service:199` | `SERIES_USE_SESSION` | ✅ |
| **Bayar → ANTRI_OBAT / COMPLETED** | `kasir_service:602–628` | `log` (data_lama/baru) | ✅ (dulu terlewat grep karena assign via variabel) |
| Void transaksi → COMPLETED | `kasir_service:1078` | `VOID_KUNJUNGAN_FORWARD` | ✅ |
| Buat kunjungan (daftar / beli-produk / membership) | `pasien/kunjungan:489/membership:539` | `log_create` | status awal tercatat |

**Kesimpulan in-DB:** histori transisi **LENGKAP** di `audit_log` — setiap perpindahan tahap ada stempel waktu + `id_staf` + status from/to. Tidak ada jalur transisi yang lolos.

Catatan: `aksi` **tidak seragam** (STATUS_UPDATE, TINDAKAN_*, SERIES_USE_SESSION, VOID_KUNJUNGAN_FORWARD, log_create). Data Analyst harus memetakan semuanya sebagai "transisi" (taksonomi di handoff §3).

---

## Satu-satunya GAP: EXPORT membuang payload from/to ❌

`export_service.export_staff_activity_raw` mengekspor: `id_log, waktu, id_staf, nama_staf, role, aksi, tabel_target, id_target, status_aksi, keterangan` — **TANPA `data_lama`/`data_baru`**.

Akibat: di raw export, transisi diketahui KAPAN & OLEH SIAPA, tapi **status tujuannya hilang** → dwell-time & insiden merah tak terekonstruksi hilir, padahal datanya ADA di DB.

**Rekomendasi (perubahan kecil, sisi Sehati):** tambahkan `data_lama` & `data_baru` (JSON) — atau kolom terparse `status_lama`/`status_baru` — ke dataset `staff_activity_raw` (`export_service` + `_export_columns` default_columns). Setelah itu raw data cukup untuk seluruh derivasi di handoff §4.

> ✅ SELESAI 2026-07-07: `staff_activity_raw` kini mengekspor `status_lama`, `status_baru` (PII-free) + `data_lama`, `data_baru` (redaksi saat mask_pii). Unit-test parsing hijau. In-DB audit + export kini sama-sama lengkap.
