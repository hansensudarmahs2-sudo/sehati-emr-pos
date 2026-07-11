# Klinik ABC — eMR + POS Demo

Demo mockup standalone untuk presentasi ke partner bisnis. **Tidak terhubung ke database produksi**, tidak mengganggu app utama, semua data preset in-memory.

## Quick Test (Tanpa Build EXE)

Untuk test demo sebelum di-package jadi EXE:

```bash
cd "/mnt/e/Claude/Projects/sehati-emr-pos/mockup_demo"
source ../sehati_clinic/.venv/bin/activate
python __main__.py
```

Browser otomatis terbuka ke `http://localhost:8765`. Tutup console untuk stop.

## Flow Demo (4 Halaman Highlight)

1. **Login** — pilih salah satu user (Owner / Dokter / Kasir / FO)
2. **Dashboard Owner** — stats omzet hari ini & bulan ini, chart omzet 7 hari, top treatment, kinerja dokter
3. **Antrian Hari Ini** — 5 pasien dalam antrian (Anisa, Fitri, Jasmin, Maya, Putri)
4. **Detail Pasien + SOAP** — klik salah satu pasien, lihat riwayat + form SOAP
5. **Kasir** — tagihan Jasmin Aulia (Rp 3,4 juta — Botox + Konsultasi + 2 produk)
6. **Nota cetak** — preview bisa langsung print via Ctrl+P

## Build EXE Windows (Final Package untuk Share)

### Prasyarat
- Windows 10/11 (atau WSL dengan akses Windows)
- Python 3.10+ di-install
- PyInstaller: `pip install pyinstaller`

### Langkah Build

```bash
# Di Windows PowerShell atau Command Prompt
cd "E:\Claude\Projects\sehati-emr-pos\mockup_demo"

# Install dependencies (kalau belum)
pip install fastapi uvicorn jinja2 pyinstaller

# Build EXE (output ke folder dist/)
pyinstaller build_exe.spec

# Hasil:
# dist\KlinikABC_Demo.exe  (~80MB, single file)
```

### Test EXE

```bash
cd dist
KlinikABC_Demo.exe
```

- Console window terbuka menampilkan URL
- Browser auto-launch ke localhost:8765
- Tutup console untuk stop

### Share ke Partner

Kirim 1 file `KlinikABC_Demo.exe` via:
- USB flash drive
- WeTransfer / Google Drive (~80MB)
- Email (mungkin kena limit attachment)

Partner cukup **double-click EXE** untuk jalankan. Tidak perlu install apa pun.

## Data Preset

- **3 dokter**: dr. Andi Pratama (Owner), dr. Budi Hartono, dr. Erika Sari
- **18 pasien** dengan nama Indonesia realistis + alamat Jabodetabek
- **5 pasien antrian hari ini** dengan status berbeda (ANTRI_KONSULTASI / ANTRI_TINDAKAN / ANTRI_KASIR)
- **8 treatment** + **5 produk** skincare
- **7 hari omzet** Rp 33-47 juta/hari (chart realistic)
- **Kinerja dokter minggu ini** dengan komisi per dokter
- **Riwayat SOAP** untuk pasien Anisa Rahmawati (2 entries May)

## Customisasi Branding

Edit `demo_data.py`:

```python
KLINIK = {
    "nama": "Nama Klinik Anda",
    "alamat": "Alamat lengkap...",
    "telp": "021-xxx",
    "tagline": "Tagline klinik",
}
```

Re-run / rebuild EXE setelah edit.

## Struktur Folder

```
mockup_demo/
├── __main__.py          # Entry point + browser launcher
├── main.py              # FastAPI app + 6 routes
├── demo_data.py         # Semua preset data (in-memory)
├── build_exe.spec       # PyInstaller config
├── templates/           # 6 HTML templates
│   ├── _base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── antrian.html
│   ├── pasien_detail.html
│   ├── kasir.html
│   └── nota.html
├── static/              # (empty — pakai CDN Tailwind)
└── README.md            # File ini
```

## Catatan

- Mockup ini **completely isolated** dari `sehati_clinic/app/` — aman, tidak mengganggu produksi
- Tidak ada SQLite atau MySQL — semua data hardcoded di `demo_data.py`
- Internet diperlukan saat first load (Tailwind + Chart.js dari CDN)
- Cetak nota bisa langsung dari browser via Ctrl+P

## Tip Demo ke Partner

Skenario pitch 5-menit:
1. **Login Owner** — tunjukkan multi-role system
2. **Dashboard** — highlight chart omzet & kinerja dokter (insight bisnis langsung)
3. **Antrian** — klik Jasmin Aulia (A-03)
4. **SOAP form** — pretend isi pemeriksaan singkat, klik "Lanjut ke Kasir"
5. **Kasir** — pilih TUNAI, klik Proses Pembayaran
6. **Nota** — tunjukkan layout nota bersih siap cetak

End message: *"Versi produksi punya 30+ halaman dengan pendaftaran wizard, ruang tindakan, apotek, pengadaan, hybrid commission system, dan lain-lain."*
