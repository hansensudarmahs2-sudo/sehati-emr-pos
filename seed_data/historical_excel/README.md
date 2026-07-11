# Historical Excel Import

Folder ini berisi file Excel format **"RINCIAN KOMISI"** dari sistem klinik lama
yang akan di-import sebagai dummy/historical data ke database Sehati Clinic.

## File yang ada di sini

- `Maret 2026.xlsx` — 590 rows, ~190 fakturs
- `April 2026.xlsx` — 691 rows, ~190 fakturs
- `Mei 2026.xlsx`   — 772 rows, ~190 fakturs

**Total:** ~2.035 data rows → ~569 kunjungan + ~386 pasien.

## Cara import (3 step)

### Step 1 — Dry-run preview (no DB write)

```bash
cd sehati_clinic/
source .venv/bin/activate   # kalau pakai virtualenv

python ../seed_data/import_excel_historical.py --dry-run
```

Output: jumlah pasien/treatment/produk/faktur + sample 3 faktur pertama.
Belum touch DB sama sekali. Aman.

### Step 2 — Test dengan 5 faktur saja

```bash
python ../seed_data/import_excel_historical.py --limit-faktur 5 --yes
```

Import 5 faktur pertama saja → cek di UI apakah data masuk benar
(login Owner → Pasien search, Reports Omzet Bulanan, dll).

### Step 3 — Full import (semua faktur)

```bash
python ../seed_data/import_excel_historical.py
```

Akan minta konfirmasi `[y/N]` sebelum write. Estimasi durasi ~1-2 menit
untuk 569 faktur.

## Idempotent — re-run aman

Script track imported faktur via marker di field `keluhan_utama`:
`[LEGACY-IMPORT] #26030025`. Kalau script jalan ulang, faktur yang
sudah ada akan di-skip otomatis.

## Decisions yang locked (5 Juni 2026)

| # | Decision |
|---|----------|
| Role dokter | Pakai user OWNER existing |
| Master treatment/produk | Auto-create dari distinct Excel items |
| Stok awal produk | 1000 unit |
| Konsultasi Kulit | → SOAP (`pemeriksaan_klinis`) saja |
| Status historical | kunjungan=COMPLETED, transaksi LUNAS implisit, bayar=CASH |
| Pasien fields kosong | nomor_ktp/alamat/tgl_lahir/no_hp → NULL (tidak ada di Excel) |

## Rollback (kalau perlu)

Tidak ada built-in rollback. Kalau Bapak mau hapus historical:

```sql
-- HATI-HATI! Jalankan di DB development dulu untuk test.
DELETE FROM transaksi_pembayaran WHERE id_transaksi IN (
    SELECT id_transaksi FROM transaksi_kasir WHERE id_kunjungan IN (
        SELECT id_kunjungan FROM kunjungan
        WHERE keluhan_utama LIKE '[LEGACY-IMPORT]%'
    )
);
DELETE FROM transaksi_kasir WHERE id_kunjungan IN (
    SELECT id_kunjungan FROM kunjungan WHERE keluhan_utama LIKE '[LEGACY-IMPORT]%'
);
DELETE FROM kunjungan_resep WHERE id_kunjungan IN (
    SELECT id_kunjungan FROM kunjungan WHERE keluhan_utama LIKE '[LEGACY-IMPORT]%'
);
DELETE FROM kunjungan_tindakan WHERE id_kunjungan IN (
    SELECT id_kunjungan FROM kunjungan WHERE keluhan_utama LIKE '[LEGACY-IMPORT]%'
);
DELETE FROM pemeriksaan_klinis WHERE id_kunjungan IN (
    SELECT id_kunjungan FROM kunjungan WHERE keluhan_utama LIKE '[LEGACY-IMPORT]%'
);
DELETE FROM kunjungan WHERE keluhan_utama LIKE '[LEGACY-IMPORT]%';

-- Master treatment + produk yang auto-created → biarkan, atau hapus manual via UI.
```

Backup DB sebelum jalankan rollback.
