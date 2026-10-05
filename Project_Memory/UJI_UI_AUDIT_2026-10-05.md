# Uji UI — semua perbaikan audit alur uang (cabang `laptop/audit-alur-uang-putaran-21`)

Untuk dr. Hansen, di **desktop** (http://localhost:8001), SEBELUM deploy ke mini PC
(CLAUDE.md §1.1). Setiap butir punya **bukti di DB** lewat `scripts/jejak_uji_ui.py`.

## Cara mencatat — dua perintah per kelompok

⚠ **Harus di WSL, bukan PowerShell.** Di PowerShell, `python` adalah Python Windows yang
tidak mengenal proyek ini ("No module named scripts.jejak_uji_ui"). Dan di WSL perintahnya
`python3`.

Sekali per jendela terminal:

```bash
wsl
cd /mnt/e/Claude/Projects/sehati-emr-pos/sehati_clinic
source .venv/bin/activate
```

Lalu, untuk setiap kelompok uji:

```bash
python3 -m scripts.jejak_uji_ui --mulai      # 1. SEBELUM menguji
python3 -m scripts.jejak_uji_ui              # 2. SESUDAHNYA — laporan + [OK]/[GAGAL]
```

Atau langsung dari PowerShell tanpa masuk WSL (satu baris):

```bash
wsl -e bash -lc "cd /mnt/e/Claude/Projects/sehati-emr-pos/sehati_clinic && source .venv/bin/activate && python3 -m scripts.jejak_uji_ui"
```

Laporan tersimpan di `sehati_clinic/uji_ui_log/jejak_<waktu>.md` (diabaikan git), bisa
dibuka dari Windows di `E:\Claude\Projects\sehati-emr-pos\sehati_clinic\uji_ui_log\`.
Isi kolom **Hasil** di tabel bawah dengan ✅ / ❌ + catatan singkat, lalu commit dokumen ini.
Kolom **Jejak §** menunjuk bagian laporan yang membuktikan butir itu.

⚠ **Keadaan awal DB dev (2026-10-05):** jejak §6 sudah ❌ — 3 komisi AKTIF (Rp 4.712)
atas transaksi #5 yang di-VOID 21 Sep lewat `force_past_day_void` SEBELUM diperbaiki.
Itu bukan akibat uji Anda; itu bukti Temuan 3/11 nyata di data, dan kemungkinan ada juga
di mini PC. Jangan dibersihkan sebelum diputuskan (menyentuh uang staf).

## Persiapan

| | |
|---|---|
| Akun | `hansen` (Superadmin, ber-PIN) · `kasir` · `admin` · (`petugas_fo` tidak dipakai di kelompok A — FO tidak berhak membayar) |
| PIN kedua | **Setel PIN untuk `admin`** (menu Staf). Refund hari lampau butuh penyetuju ≠ pemroses; di dev hanya `hansen` yang ber-PIN |
| Pasien uji | `SEED-001/002/003` (SEED-003 sudah ANTRI_BAYAR hari ini) — jangan pakai pasien sungguhan |
| Obat tertunda | 20 item hari lampau sudah ada di **Obat Tertunda** |

---

## A. Kasir & uang — paling penting

| ID | Temuan | Langkah di UI | Yang harus terlihat | Jejak § | Hasil |
|---|---|---|---|---|---|
| U01 | T28 | Login `kasir` → **Tutup Kasir** → Buka Kasir, modal Rp 200.000 | Laci terbuka; keterangan "Laci tanggal …" | 4 | |
| U02 | T28 | Login `hansen` (Superadmin) atau `admin` — **bukan** yang membuka laci — → bayar tagihan SEED-003. (FO **tidak** berhak membayar: menu kasir hanya Kasir/Admin/Owner/Superadmin — koreksi 2026-10-05) | — | 2 | |
| U03 | T28 | Kembali sebagai `kasir` → **Tutup Kasir** (jangan tutup dulu) | Pembayaran oleh `hansen`/`admin` **ikut** di expected; tabel **Rincian per petugas** memuat namanya | 4, 5 | |
| U04 | T28 | Sebagai `admin` coba **Buka Kasir** | **Ditolak**: "Laci masih terbuka: sesi #… tanggal …" | 4 | |
| U05 | T32 | **Obat Tertunda** → pilih satu item → isi alasan → **✗ Batal** TANPA PIN | **Ditolak**: "…butuh persetujuan PIN Admin/Superadmin/Owner" | 3 | |
| U06 | T32 | Ulangi, pilih penyetuju `hansen`, PIN **salah** | Ditolak "PIN penyetuju salah…" | 1, 3 | |
| U07 | T32 | Login `hansen`, proses refund dan pilih **diri sendiri** sebagai penyetuju | `hansen` **tidak ada** di daftar penyetuju (disaring) | — | |
| U08 | T32 | Sebagai `kasir`: penyetuju `hansen` + PIN benar | Berhasil "…dibukukan hari ini" | 3 | |
| U09 | T32 | Catat dulu **Laporan → Omzet** tanggal transaksi asal item itu, lalu sesudah U08 buka lagi | Omzet tanggal **asal TIDAK berubah**; omzet **hari ini** turun sebesar refund ("refund hari ini") | 5 | |
| U10 | T32 | Cetak ulang nota transaksi asal | Baris "↩ Dikembalikan", TOTAL bersih, **kembalian tidak membesar** | — | |
| U11 | T32 | Coba **void** transaksi asal itu | **Ditolak**: "sudah ada 1 refund … uang keluar dua kali" | 1 | |
| U12 | T28 | **Tutup Kasir**: isi counted sesuai expected → Tutup | Selisih 0; slip Z menulis **Dibuka:** kasir, **Ditutup:** (yang menutup) | 4 | |
| U13 | T28 | Sesudah tutup, bayar satu transaksi lagi → buka slip Z sesi tadi | Slip memuat **"! MASUK SESUDAH TUTUP"**; angka tutup **tidak berubah** | 4 | |
| U14 | T28 | Coba **Buka Kasir** lagi hari ini | **Ditolak**: "sudah pernah dibuka dan ditutup" | 4 | |
| U15 | T28 | *(hari lain)* bayar SEBELUM menekan Buka Kasir, lalu buka | Kotak kuning **"pembayaran masuk SEBELUM kasir dibuka"**, tetap dihitung | 4 | |
| U16 | T1 | Transaksi yang obatnya sudah **DISERAHKAN** → coba void | **Ditolak**: "…item SUDAH DISERAHKAN…" | 1 | |
| U17 | T3/T5 | Sebagai `admin`: **force void** transaksi kemarin (yang komisinya ada, tanpa obat diserahkan) | Berhasil; jejak §6 **tidak bertambah** komisi AKTIF atas VOID | 6 | |

## B. Nota (T27)

| ID | Langkah di UI | Yang harus terlihat | Jejak § | Hasil |
|---|---|---|---|---|
| U18 | Bayar kunjungan BARU yang berisi tindakan → cetak nota A5 & thermal | Baris tindakan = harga yang ditagih; **tanpa** tanda "direkonstruksi" | 2 ("punya snapshot tindakan") | |
| U19 | Cetak ulang nota lama berisi tindakan (mis. #24) | Tanda kecil **"Rincian direkonstruksi dari harga saat ini"** | — | |
| U20 | *(perlu pasien bermembership berkuota)* tindakan kuota → nota | Baris **Rp 0** + "↳ Benefit VIP (prabayar) · nilai normal Rp …"; thermal versi pendek; **tidak ada** baris "Benefit Member −Rp" | 2 | |

## C. Apotek

| ID | Temuan | Langkah di UI | Yang harus terlihat | Jejak § | Hasil |
|---|---|---|---|---|---|
| U21 | T29 | Buat lot ber-ED **lewat** (penerimaan/opname dengan ED kemarin) untuk satu obat → buka resep yang memakai obat itu di **Apotek** | Batch FEFO **merah** + "⚠ KEDALUWARSA"; tombol serah tetap bisa | 7 | |
| U22 | T30 | Serahkan obat yang stoknya **kurang**, lalu void transaksinya (hari sama) | Tidak ada lot `VOID-RETURN` baru berisi barang yang tak pernah keluar | 7 | |
| U23 | T20 | **Opname** → approve, **klik dua kali cepat** | Hanya **1** lot/penyesuaian; cache = lot | 1, 7 | |
| U24 | T20 | **Retur** → approve, klik dua kali cepat | Audit approve **1** kali | 1 | |

## D. Klinis & membership (kerja laptop 4 Okt — belum pernah diuji di UI desktop)

| ID | Langkah di UI | Yang harus terlihat | Hasil |
|---|---|---|---|
| U25 | Login dokter → **Dashboard** | Tidak error; daftar tindakan selesai **berisi** | |
| U26 | Pasien SEED-001 → **Timeline antropometri** | Tidak error; grafik berat badan tidak datar | |
| U27 | Tulis SOAP untuk 2–3 kunjungan berbeda di HARI yang sama → **Riwayat** pasien | Muncul **2–3 entri**, bukan luruh jadi satu | |
| U28 | **Pasien → Membership** (pasien bermembership) | Nomor aktivasi tertaut ke nota **pasien yang sama**; tak ada tautan "None" | |
| U29 | **Kasir → Cari Transaksi** | Transaksi membership tidak memunculkan tautan `/None` | |

## E. Tampilan, keamanan, ekspor

| ID | Langkah | Yang harus terlihat | Hasil |
|---|---|---|---|
| U30 | Telusuri Kasir, Apotek, Laporan, Dashboard | Semua tombol/badge **berwarna** (Tailwind dikompilasi ulang 4 Okt) | |
| U31 | Buka DevTools (F12) → Console, pakai halaman di atas | **Tidak ada** pesan "Content Security Policy" | |
| U32 | **Finance Export** hari ini → `daily_operational_summary` | Kolom **`total_refund`**; `total_omzet` = laporan omzet | |
| U33 | **Clinical Export** (Tahap B) | 5 berkas baru ikut; paket terenkripsi (butuh `BACKUP_RECIPIENT` di desktop) | |

## F. Pengamatan — temuan yang SENGAJA belum diperbaiki (lihat saja, jangan dianggap gagal)

| ID | Temuan | Yang akan terlihat |
|---|---|---|
| P1 | T31 | Ketik bayar Rp 100.000 untuk tagihan Rp 90.000 → kembalian Rp 10.000 tampil besar, tapi tutup kasir menghitung Rp 100.000 masuk |
| P2 | T14 | Membership → kotak UPGRADE tidak menyebut sisa hari yang hangus |
| P3 | T33 | Jejak §2: `doc_number=NULL` pada setiap transaksi baru (Finance ditunda) |
| P4 | T21 | Laporan Kinerja Dokter: "Estimasi Omzet" memakai harga penuh untuk tindakan kuota |

---

## Hasil per sesi uji

| Tanggal | Penguji | Butir | Laporan jejak | Catatan |
|---|---|---|---|---|
| | | | | |
