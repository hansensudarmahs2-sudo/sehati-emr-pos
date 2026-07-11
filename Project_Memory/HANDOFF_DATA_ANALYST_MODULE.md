# Handoff — Modul Data Analyst (Sumber Data Mentah dari Sehati eMR-POS)

**Dibuat:** 2026-07-07 · **Untuk:** modul/agent Data Analyst (terpisah dari Sehati).
**Terkait:** `WARNA_ANTRIAN_FO_DESIGN.md`, `KESTABILAN_OPERASIONAL_EMRPOS.md`, `RawDataExport/` (Owner Raw Data Export / C2), Data Dictionary di `/web/export/dictionary.md|json`.

---

## 0. Prinsip arsitektur (KUNCI)

**Sehati eMR-POS = PENYEDIA RAW DATA saja.** Tidak ada agregasi, penilaian, atau interpretasi di Sehati. Seluruh perangkuman/perhitungan (insiden merah, dwell-time, pola bolak-balik, spike racikan, korelasi kongesti) = **tanggung jawab modul Data Analyst**. Interpretasi hasil = dibaca owner sendiri dan/atau bahan diskusi dengan **council AI**. Sehati **tidak** menambah tabel olahan untuk ini.

Konsekuensi: dokumen ini = spec bagaimana Data Analyst **menurunkan** metrik dari raw data Sehati; bukan permintaan fitur ke Sehati (kecuali 2 gap raw-data di §6).

---

## 1. Cara akses raw data

- **Owner Raw Data Export** (`/web/export`, owner-only): paket dataset CSV/JSON (weekly/monthly/custom range), opsi `mask_pii` untuk PII saat kirim ke pihak ke-3/AI.
- Data dictionary: `/web/export/dictionary.md` (naratif) & `.json` (programatik).
- Dataset kunci untuk analisis kongesti: `staff_activity_raw` (audit_log), `transactions_header_raw`, `transactions_detail_raw`, `transaction_items_raw`, `visits_raw`, `treatments_raw`, `membership_raw`.

---

## 2. Sumber sinyal (di mana datanya)

| Sinyal | Sumber | Field kunci |
|---|---|---|
| Transisi status antrian | `audit_log` (via `staff_activity_raw`) | `aksi`, `id_target`(=id_kunjungan), `waktu`, `id_staf`, **`status_lama`/`status_baru`** (from/to, kini diekspor) |
| Treatment mulai/selesai | `audit_log` aksi `TINDAKAN_START`/`TINDAKAN_END` + kolom `kunjungan.waktu_mulai`/`waktu_selesai` | `waktu`, `id_staf`(pelaksana), `id_kunjungan` |
| Pembayaran | `transactions_*` | `waktu_bayar`, item, `id_produk`, qty |
| Racikan | item transaksi + master produk | flag/kode racik pada produk (sudah ada di kode produk) |
| Staf bertugas | `master_staf.waktu_mulai_shift` + kasir closing | shift per staf |
| Ambang warna (definisi tunggal) | konvensi Sehati | Konsul/Treatment (kuning≥20, merah≥30); Bayar (kuning≥6, merah≥11 → 10 mnt masih kuning); **Obat tidak diwarnai** |

---

## 3. Taksonomi event transisi (PENTING — aksi tidak seragam)

Perpindahan status kunjungan tersebar di beberapa `aksi` audit_log, bukan satu label. Data Analyst harus memetakan semuanya sebagai "transisi":

| `aksi` | Arti | Status baru (di `data_baru`) |
|---|---|---|
| `STATUS_UPDATE` | ubah status oleh FO / dokter | eksplisit di `data_baru.status_antrian` |
| `TINDAKAN_START` | perawat/dokter mulai tindakan | ON_TREATMENT |
| `TINDAKAN_END` | selesai tindakan | ANTRI_BAYAR / lanjut |
| `SERIES_USE_SESSION` | tebus sesi series | ANTRI_TREATMENT |
| `VOID_KUNJUNGAN_FORWARD` | void transaksi → tutup kunjungan | COMPLETED |
| (create) `log_create` kunjungan | pendaftaran / beli-produk / membership | status awal (mis. ANTRI_KONSULTASI / ANTRI_BAYAR) |

**Entry ke tahap** juga tersedia langsung dari `kunjungan.waktu_masuk_status` (kolom baru: waktu masuk status SAAT INI) + `tgl_kunjungan` (masuk antrian). Untuk histori penuh, gunakan deretan event audit di atas.

---

## 4. Resep derivasi (dikerjakan di Data Analyst)

### 4.1 Wait-time & insiden merah (rekonstruksi retroaktif)
1. Bangun timeline `(id_kunjungan, status, waktu)` dari event transisi (§3).
2. Untuk waktu t: pasien di tahap S = yang transisi terakhirnya masuk S dan belum keluar. `wait = t − waktu_masuk_S`.
3. `max_wait(tahap) = max` atas pasien tahap itu. **Insiden merah** = periode `max_wait ≥ ambang_merah(tahap)` (§2). Rekam mulai/selesai/durasi/puncak/jumlah pasien. (Warna di UI Sehati hanya real-time; sejarahnya tersirat di transisi → tak perlu di-log live.)

### 4.2 Dwell-time per tahap
`durasi = waktu_keluar − waktu_masuk` (transisi berturut per kunjungan). Agregasi p50/p90 per tahap/jam/hari.

### 4.3 Dokter bolak-balik (hipotesis)
Untuk `id_staf` dokter: deret `TINDAKAN_END → (STATUS_UPDATE→KONSULTASI / TINDAKAN_START)` dalam Δ pendek (mis. <5 mnt), berulang → tandai pola bolak-balik. Hitung frekuensi & pasien terkait.

### 4.4 Spike racikan
`transaksi.waktu_bayar` + item racik (kode produk) + qty → deteksi lonjakan per jendela (mis. rolling 10 mnt). Contoh: 17:00 (2 racik) + 17:03 (3 racik) = spike peracikan.

### 4.5 Cross-check kongesti (akar masalah → keputusan scaling)
Korelasikan insiden merah dengan: volume kunjungan harian (anomali), dwell-time, bolak-balik dokter, spike racikan, dan **staf bertugas saat itu (KONTEKS, bukan tudingan individu)**. Kongesti persisten yang bukan mesin/individu ⇒ sinyal kapasitas/**scaling-up** + minta feedback staf. **Gangguan POS/EDC** tidak terekam sistem (manual) → dikonfirmasi via follow-up ke staf yang bertugas (di sinilah nilai "tahu siapa bertugas").

---

## 5. Kualitas data & konvensi

- **Timezone WIB** (DEC-080) untuk field waktu korektif/tampilan; sebagian ekspor UTC (self-consistent).
- **VOID dikecualikan** dari agregasi uang (`status_transaksi='BAYAR'`).
- **`id_kunjungan`** = kunci join lintas dataset (audit ↔ transaksi ↔ treatment).
- Ambang warna = definisi tunggal (§2) agar rekonstruksi insiden konsisten dengan UI.

---

## 6. GAP raw-data yang Sehati HARUS sediakan (agar analisis mungkin)

> Ini satu-satunya perubahan sisi Sehati; tetap konsisten "Sehati = penyedia raw data".

1. **Export `staff_activity_raw` belum menyertakan `data_lama`/`data_baru`.** Saat ini kolomnya: id_log, waktu, id_staf, nama_staf, role, aksi, tabel_target, id_target, status_aksi, keterangan — **tanpa payload from/to**. Akibat: transisi diketahui KAPAN & OLEH SIAPA, tapi **status tujuannya hilang** → dwell-time/insiden tak terekonstruksi. **✅ SELESAI 2026-07-07:** ditambahkan `status_lama`, `status_baru` (terparse, PII-free) + `data_lama`, `data_baru` (redaksi saat mask_pii).
2. **Kelengkapan audit transisi (verifikasi).** Mayoritas jalur teraudit (FO `STATUS_UPDATE`, dokter `STATUS_UPDATE`, treatment `TINDAKAN_START/END`, series `SERIES_USE_SESSION`, void `VOID_KUNJUNGAN_FORWARD`, create `log_create`). **Perlu dipastikan** jalur **pembayaran normal → (ANTRI_OBAT / COMPLETED)** juga menulis audit status (bukan hanya audit transaksi). Bila ada jalur yang lolos, rekonstruksi punya lubang.

(Detail temuan pengecekan kelengkapan → catatan terpisah `CEK_KELENGKAPAN_AUDIT_TRANSISI.md`.)

---

## 7. Batas tegas

- Sehati **tidak** menghitung insiden/dwell/bolak-balik/spike. Semua agregasi & interpretasi = Data Analyst → owner/council AI.
- Council AI = mitra interpretasi & pemetaan kecurigaan kongesti; keputusan SDM/scaling di tangan owner.
