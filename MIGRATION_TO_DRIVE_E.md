# Panduan Migrasi Workspace: C:\ (Documents) → E:\Claude\Projects

**Tujuan:** pindahkan proyek keluar dari Documents/OneDrive (sumber masalah null-byte/B-013) ke drive E.
**Tanggal dibuat:** 2026-06-26

---

## Prinsip & Peringatan Penting

1. **Database TIDAK ikut pindah.** Data MySQL disimpan oleh server MySQL, BUKAN di folder proyek. Aplikasi konek ke `localhost` lewat `.env`. Jadi setelah pindah, DB tetap sama — tidak perlu migrasi data DB.
2. **`.venv` JANGAN dicopy.** Folder virtual-environment (219 MB) punya path absolut yang baked-in ke lokasi lama → rusak kalau dipindah. Kita BUAT ULANG di lokasi baru (cepat).
3. **Copy pakai Windows (robocopy), BUKAN `cp` di WSL.** Menyalin antar-drive lewat WSL bisa kena null-byte lagi. Copy via Windows = aman (binary-safe).
4. **Nama folder root: hindari spasi.** Disarankan `sehati-emr-pos` (bukan "WebApp for eMR and POS"). Tidak ada kode yang mereferensi nama root, jadi aman diganti. Panduan ini pakai `sehati-emr-pos`.
5. **Jangan hapus folder lama** sampai lokasi baru terbukti jalan 100%.

> Lokasi lama : `C:\Users\USER\Documents\Claude\Projects\WebApp for eMR and POS`
> Lokasi baru : `E:\Claude\Projects\sehati-emr-pos`

---

## BAGIAN 0 — Persiapan (5 menit)

**0a. Backup DB dulu** (di terminal WSL):
```bash
cd "/mnt/c/Users/USER/Documents/Claude/Projects/WebApp for eMR and POS/sehati_clinic"
sudo mysqldump db_sehati > backups/db_pre_migrasi_$(date +%Y%m%d_%H%M%S).sql
```

**0b. Hentikan aplikasi** yang sedang jalan (di terminal tempat uvicorn jalan, tekan `Ctrl+C`).

**0c. Pastikan drive E: ada & cukup ruang** (~300 MB cukup). Folder `E:\Claude\Projects` boleh belum ada — robocopy akan membuatnya.

---

## BAGIAN 1 — Copy File (Windows PowerShell, BUKAN WSL)

Buka **PowerShell** (Start → ketik "PowerShell" → Enter). Jalankan:

```powershell
robocopy "C:\Users\USER\Documents\Claude\Projects\WebApp for eMR and POS" "E:\Claude\Projects\sehati-emr-pos" /E /XD .venv __pycache__ .pytest_cache node_modules /XF *.pyc
```

Penjelasan:
- `/E` — copy semua subfolder (termasuk yang kosong).
- `/XD ...` — KECUALIKAN folder: `.venv`, `__pycache__`, `.pytest_cache`, `node_modules`.
- `/XF *.pyc` — kecualikan file `.pyc` (cache Python).

Tunggu sampai selesai. robocopy akan menampilkan ringkasan (jumlah file disalin). Harusnya tidak ada error (angka "Failed" = 0).

---

## BAGIAN 2 — Buat Ulang Virtual Environment (WSL)

Buka terminal **WSL/Ubuntu**. Jalankan:

```bash
cd "/mnt/e/Claude/Projects/sehati-emr-pos/sehati_clinic"
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

- `python3.12 -m venv .venv` — buat virtual-env baru di lokasi baru.
- `pip install -e ".[dev]"` — pasang semua dependensi dari `pyproject.toml` (FastAPI, SQLAlchemy, dll + tools dev).

Tunggu sampai selesai (~1-3 menit, butuh internet untuk download paket).

---

## BAGIAN 3 — Verifikasi Config

```bash
# masih di folder sehati_clinic lokasi baru, venv aktif
ls -la .env                 # .env harus ADA (ikut tercopy)
cat .env | grep -E "DB_|RM_CLINIC|COOKIE"   # cek isi config inti
```

`.env` tidak punya path absolut, jadi tidak perlu diubah. Pastikan saja ada.

---

## BAGIAN 4 — Test Jalankan dari Lokasi Baru (WSL)

```bash
cd "/mnt/e/Claude/Projects/sehati-emr-pos/sehati_clinic"
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Lalu di browser buka `http://localhost:8000` → login owner1 →
- [ ] Tampilan Tailwind normal (CSS jalan dari `/static/css/app.css`)
- [ ] Dropdown searchable jalan (Tom Select)
- [ ] Antrian/HTMX jalan
- [ ] Chart laporan muncul
- [ ] Bisa buka 2-3 halaman tanpa error

Kalau semua OK, hentikan (`Ctrl+C`).

---

## BAGIAN 5 — Test Apakah B-013 (null-byte) Hilang di E:

Ini tes penentu: apakah pindah ke E: benar-benar menyelesaikan masalah.

```bash
cd "/mnt/e/Claude/Projects/sehati-emr-pos/sehati_clinic"
python3 -c "open('test_nullbyte.txt','w').write('halo dunia\n'*500)"
python3 -c "print('null bytes:', open('test_nullbyte.txt','rb').read().count(b'\x00'))"
rm test_nullbyte.txt
```

- Kalau **`null bytes: 0`** → 🎉 B-013 HILANG. E: aman, migrasi sukses.
- Kalau **null bytes > 0** → masalah drvfs masih ada di E:. Lapor ke Claude; plan B = migrasi ke WSL-native (`~/`).

---

## BAGIAN 6 — Sambungkan Cowork ke Lokasi Baru

1. Di aplikasi Cowork, pilih/ganti folder kerja ke: `E:\Claude\Projects\sehati-emr-pos`
2. Pastikan Claude bisa membaca file di lokasi baru (minta Claude `ls` folder untuk konfirmasi).

---

## BAGIAN 7 — Decommission Lokasi Lama (HANYA setelah semua di atas ✅)

1. Rename folder lama jadi penanda (jangan langsung hapus):
   `C:\...\WebApp for eMR and POS`  →  `C:\...\_OLD_WebApp for eMR and POS`
2. Pakai lokasi baru selama beberapa hari. Kalau stabil, baru hapus folder `_OLD_...`.
3. Update shortcut/kebiasaan ketik path ke lokasi baru.

---

## CHECKLIST RINGKAS

- [ ] 0a. Backup DB (`mysqldump`)
- [ ] 0b. Stop aplikasi (Ctrl+C)
- [ ] 1.  robocopy C: → E: (exclude .venv dll)
- [ ] 2.  Buat venv baru + `pip install -e ".[dev]"`
- [ ] 3.  Cek `.env` ada di lokasi baru
- [ ] 4.  uvicorn dari lokasi baru → app jalan & tampilan normal
- [ ] 5.  Tes null-byte di E: → harus 0
- [ ] 6.  Cowork pointing ke `E:\Claude\Projects\sehati-emr-pos`
- [ ] 7.  Rename folder lama jadi `_OLD_...` (hapus nanti)

---

## Catatan
- Kalau `python3.12` tidak ada di WSL, cek versi: `python3 --version`. Pakai yang ada (≥3.11), ganti `python3.12` jadi `python3`.
- Kalau `pip install` gagal karena internet di WSL, pastikan WSL punya akses internet (`ping 8.8.8.8`).
- `static/css/app.css` (Tailwind) ikut tercopy — tidak perlu build ulang. Kalau mau rebuild: `bash deployment/build_tailwind.sh`.
- DB lokasi tidak berubah → semua data pasien/transaksi tetap utuh.
