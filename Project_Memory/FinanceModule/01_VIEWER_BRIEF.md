# Finance Viewer (Personal) — Build Brief untuk Cowork

**Status**: 🟢 APPROVED — Mode: Pure Viewer
**Decision Date**: 11 Juni 2026
**Relasi**: Turunan dari DEC-064 (Finance Module design, `00_DESIGN.md`)
**Source of Truth**: **Accurate Online** (dipakai akuntan). Modul ini BUKAN buku resmi.

---

## 🎯 Keputusan Inti

Modul finance dibangun sebagai **Pure Viewer** — alat baca pribadi dr. Hansen untuk memahami jurnal & arus kas klinik secara sederhana. **Accurate tetap buku resmi & sumber laporan pajak.** Modul tidak mengirim data ke Accurate (belum).

**Upgrade trigger ke mode Feeder**: HANYA saat akuntan/Accurate minta data spesifik untuk di-import. Sampai itu terjadi, jangan bangun exporter apa pun.

---

## ⛔ Konstitusi Modul (non-negotiable)

1. **Accurate = single source of truth.** Kalau angka modul beda dengan Accurate, Accurate yang benar.
2. **Read-only, derived-only.** Semua angka diturunkan dari transaksi Sehati. **TIDAK ADA input/jurnal manual di modul** — ini yang mencegah divergensi.
3. **Indikatif.** Setiap layar/report kasih footer: *"Angka indikatif dari data operasional Sehati. Sumber resmi & pajak: Accurate."*
4. **JANGAN bangun** (semua ini domain Accurate): e-Faktur, SPT, PPh 21, tutup buku / period lock, neraca lengkap, depresiasi aset tetap, payroll tax, **import/feeder ke Accurate (belum)**.

---

## 🔌 Sumber Data

- Tarik dari Sehati lewat **Export Pack (DEC-046)** atau endpoint finance read-only.
- Modul **tidak menulis** data finansial ke DB mana pun. Murni baca → tampilkan.

---

## 📊 3 View Minimal (cukup ini dulu)

| View | Isi | Catatan |
|------|-----|---------|
| **1. Jurnal Sederhana Harian** | Per hari: Dr/Cr ke akun yang selaras COA Accurate (Dr Kas/Bank per metode, Dr HPP, Cr Pendapatan Jasa, Cr Pendapatan Produk, Cr Persediaan, kontra Diskon) | Ini **jurnal sisi pendapatan/operasional saja** — bukan jurnal lengkap (lihat Scope Guard) |
| **2. Cashflow per Metode Bayar** | Tunai / QRIS / Debit / Transfer per hari/bulan + nilai void | Untuk rekonsiliasi setoran bank vs mesin EDC |
| **3. Ringkasan Komisi** | Komisi dokter/perawat per periode (logika DEC-060) | Accurate tidak hitung ini otomatis — murni logika klinik |

Tambahan opsional bila gampang: **view Rekonsiliasi** — "Omzet & kas modul bulan ini" sebagai checklist manual vs angka di Accurate. Fungsi utamanya: deteksi gap (transaksi belum di-input akuntan / void belum tercermin).

---

## 🧭 Aturan Alignment (biar sejalan Accurate)

1. **COA mapping = config file, bukan hardcode.** Mirror nama/nomor akun Accurate. Minta akuntan export COA dari Accurate dulu. Kalau belum tersedia → pakai placeholder + tandai akun `PENDING COA` supaya gampang ditukar nanti.
2. **Basis & timing ikut Accurate.** Konfirmasi ke akuntan: cash basis atau accrual? Kapan pendapatan series/membership diakui (saat bayar vs saat treatment)? **Default cash basis** sampai dikonfirmasi.
3. **Void = reversal.** Transaksi VOID di-balik, tidak dihitung sebagai pendapatan/komisi.
4. **HPP pakai snapshot `hpp_at_sale`** (bukan HPP master terkini) supaya COGS historis akurat.
5. **PKP atau non-PKP?** Tentukan pendapatan gross vs net PPN. Default non-PKP (gross) sampai dikonfirmasi.

---

## 🚧 Scope Guard — Yang Sehati TIDAK Tahu

Sehati hanya tahu **pendapatan + HPP/persediaan + komisi**. Biaya operasional (sewa, gaji, listrik, marketing) ada di Accurate, TIDAK di Sehati.

➡️ Konsekuensi: **modul TIDAK menampilkan laba bersih.** Hanya **pendapatan + gross margin**. Laba bersih = domain Accurate. Jangan paksa modul jadi P&L lengkap — itu akan butuh input biaya manual yang menduplikasi Accurate dan langsung melanggar prinsip derive-only.

---

## 🧱 Prasyarat di Sisi Sehati (kerjakan walau modul cuma viewer)

Ini bukan bagian viewer, tapi fondasi data bersih (dari refinement R2–R4 di `00_DESIGN.md`):

- `hpp_at_sale` snapshot saat `proses_bayar()`
- `doc_number` formal (`TRX-YYYY-MM-NNNNNN`), immutable dari pembuatan
- `updated_at` auto-bump di `transaksi_kasir`
- Item-level discount allocation (proporsional)

Tanpa ini, view jurnal & komisi modul tidak akan akurat — dan ini juga yang nanti dibutuhkan saat upgrade ke feeder.

---

## 🔼 Upgrade Path ke Feeder (NANTI — jangan dikerjakan sekarang)

Saat trigger muncul (akuntan minta data untuk Accurate):
1. Cek format import Accurate Online (template Excel / API).
2. Bikin exporter yang map dari view ke template tersebut.
3. Karena view sudah pakai mapping COA-aligned, ini **penambahan incremental**, bukan rewrite.

---

## ❓ Input Wajib dari Akuntan (sebelum mapping final dikunci)

- Cash basis atau accrual?
- Pengakuan pendapatan series & membership: kapan?
- Klinik PKP atau non-PKP?
- Export COA dari Accurate (untuk mapping config)
- Periode tutup buku: bulanan / kuartal / tahunan?

Selama jawaban belum ada, modul boleh jalan dengan **default + label PENDING** — tetap berguna untuk dr. Hansen, dan tinggal disesuaikan saat jawaban masuk.

---

## 📝 Entri untuk `11_decisions_log.md`

```markdown
### DEC-065 — Finance Viewer: Mode Pure Viewer (Accurate sebagai Source of Truth)

**Tanggal**: 11 Juni 2026
**Konteks**: Turunan DEC-064. Akuntan klinik memakai Accurate Online sebagai
buku resmi & pelaporan pajak. dr. Hansen butuh alat baca pribadi yang
sederhana untuk memahami jurnal & arus kas klinik.

**Keputusan**:
1. Finance module dibangun sebagai PURE VIEWER (read-only, derived-only dari
   data Sehati). BUKAN sistem akuntansi paralel.
2. Accurate = single source of truth. Modul indikatif, berlabel jelas.
3. Tidak ada input/jurnal manual di modul (cegah divergensi).
4. Scope: 3 view — Jurnal Sederhana Harian, Cashflow per Metode Bayar,
   Ringkasan Komisi. TIDAK menampilkan laba bersih (biaya operasional ada di
   Accurate, bukan Sehati).
5. COA mapping dibuat selaras Accurate sejak awal (config, bukan hardcode).
6. TIDAK bangun: e-Faktur, SPT, tutup buku, neraca lengkap, import ke Accurate.
7. Upgrade ke mode Feeder (export untuk import Accurate) HANYA saat akuntan/
   Accurate minta data spesifik. Sampai itu, tidak ada exporter dibangun.

**Prasyarat sisi Sehati** (tetap dikerjakan): hpp_at_sale, doc_number,
updated_at, item-level discount allocation (R2–R4 dari DEC-064).

**Alasan**: Tercepat jadi, risiko terkecil, zero duplikasi tugas akuntan,
dan secara matematis selalu rekonsiliasi dengan Accurate karena keduanya
menarik dari sumber yang sama (Sehati) dengan aturan yang sama. Custom
accounting/tax engine ditolak — bagian teregulasi (PSAK, e-Faktur, SPT)
adalah liability maintenance abadi, sudah ditangani Accurate.
```
