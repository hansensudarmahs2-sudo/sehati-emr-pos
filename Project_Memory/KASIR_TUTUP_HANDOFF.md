═══════════════════════════════════════════════════════════
SESSION HANDOFF — Tutup Kasir / Rekonsiliasi + Rekap Harian
Disusun: 2026-06-26 · enhancement kasir PRA-DEPLOYMENT
═══════════════════════════════════════════════════════════

## ROLE
Claude = lead programmer Sehati eMR-POS. dr. Hansen = dokter pemilik (non-programmer),
Bahasa Indonesia casual. Workspace: `E:\Claude\Projects\sehati-emr-pos\sehati_clinic`.

## LATAR BELAKANG (gap yang ditemukan)
Audit kasir: Sehati sudah hebat untuk **pencatatan otomatis** (tagihan auto dari kunjungan,
split payment, void, rekap shift) — separuh pekerjaan kasir hilang. **TAPI titik lemah:
penutupan kasir akhir hari.** Sehati menampilkan total SISTEM per metode (`rekap_shift`),
tapi BELUM ada workflow mencocokkan dengan **uang fisik** + catat **selisih** + simpan
**closing record**. Itu persis pain point kasir nyata dr. Hansen.

## KEPUTUSAN (dikunci dr. Hansen)
- **PRIORITAS = Tutup Kasir / Rekonsiliasi** (Kasir-1). Dikerjakan sebelum deployment.
- **Rekap Harian Analitik** (Kasir-2) = pelengkap untuk analisa; menyusul.
- **DP/deposit booking = PARKIR.** Visi: booking hanya untuk pasien MEMBERSHIP (membership
  sudah ada di Sehati). Alur booking-membership + DP = future, belum diputuskan diberlakukan.
- **Retail/WA sale = sudah tercover** via FO-kasir "Beli Produk" (buat antrian tanpa konsul).
  Yang kurang hanya pelaporannya → masuk Kasir-2.

## YANG SUDAH ADA (REUSE — jangan bangun ulang)
- `KasirService.rekap_shift(id_staf_kasir)` → total per metode (`RekapPerMetode`: metode_bayar,
  jumlah_transaksi, total_nominal) + total_omzet, sejak `master_staf.waktu_mulai_shift`.
- Report `ReportsService.rekap_kasir_shift` + `/web/reports/rekap-kasir` (per kasir).
- Metode bayar kanonik: TUNAI / QRIS / DEBIT / KREDIT / TRANSFER.
- **BELUM ADA** model shift/closing → ini greenfield.

═══════════════════════════════════════════════════════════
## KASIR-1 — TUTUP KASIR / REKONSILIASI (prioritas)
═══════════════════════════════════════════════════════════
### Konsep
Di akhir shift, kasir "tutup kasir": sistem tampilkan **harapan** (dari rekap), kasir input
**hitungan fisik** per metode, sistem hitung **selisih**, simpan **closing record** untuk audit owner.

### Data model baru (migrasi)
`kasir_closing` (header):
- id_closing PK · id_staf_kasir FK · shift_mulai (=waktu_mulai_shift) · shift_tutup (=now)
- modal_awal (Decimal, default 0 — kas awal laci/float)
- total_expected · total_counted · total_selisih (Decimal)
- catatan (text — wajib bila selisih ≠ 0) · status (CLOSED) · created_at · id_staf_input

`kasir_closing_metode` (detail per metode) — ATAU JSON column:
- id_closing FK · metode_bayar · expected (sistem) · counted (fisik) · selisih (counted-expected)

### Alur
1. Kasir → halaman **"Tutup Kasir"**.
2. Sistem hitung **expected per metode** (reuse logic `rekap_shift`) untuk shift kasir ini.
3. Tampilkan per metode: **Expected (sistem) | Counted (input) | Selisih (auto live)**.
   + input **modal_awal** (untuk tunai).
4. Kasir isi counted + catatan → submit.
5. Simpan closing record + hitung selisih total.
6. Konfirmasi + opsi **cetak slip tutup kasir (Z-report) — TRANSIEN, tidak disimpan PDF**
   (konsisten filosofi storage).
7. Owner: **"Laporan Tutup Kasir"** — daftar closing + selisih, sorot over/short.

### Matematika rekonsiliasi (PENTING — agar benar)
- **TUNAI:** expected_laci = modal_awal + penjualan_tunai_sistem. selisih = counted − expected_laci.
  Tampilkan juga **setoran tunai** = counted − modal_awal (porsi penjualan yang disetor).
- **Non-tunai (QRIS/DEBIT/KREDIT/TRANSFER):** expected = total sistem; counted = laporan
  settlement mesin/bank; selisih = counted − expected. (Tanpa modal awal.)
- Void sudah otomatis terpotong dari expected (status berubah) — konfirmasi rekap exclude VOID.

### Catatan desain (putuskan saat build)
- **Definisi shift:** sekarang informal (anchor login `waktu_mulai_shift`). Phase 1 boleh pakai
  anchor itu + input modal saat tutup. Opsional "Buka Kasir" eksplisit (set modal di awal) =
  lebih rapi tapi tambahan kerja → boleh Phase 1.5.
- **Multi-kasir/hari:** closing per kasir-shift. 2 kasir = 2 closing. Owner lihat semua.
- Detail per metode: tabel detail (query-friendly) vs JSON column — pilih saat build.

═══════════════════════════════════════════════════════════
## KASIR-2 — REKAP HARIAN ANALITIK (pelengkap, menyusul)
═══════════════════════════════════════════════════════════
Untuk analisa kemudian hari. Sebagian sudah ada (Omzet Bulanan per metode, Rekap Kasir Shift).
Yang **baru** ditambah:
- Konsolidasi **harian**: jumlah pasien berkunjung + jumlah transaksi (termasuk **pembelian
  tanpa konsultasi**/beli-produk) + per metode (**jumlah transaksi + nilai rupiah**).
- Dimensi **single vs split payment** (count) — belum ada di report manapun.
- (Walk-in vs WA tidak dibedakan — asumsi sama, sesuai dr. Hansen.)
Bisa jadi 1 halaman "Rekap Harian Kasir" atau widget di dashboard owner.

═══════════════════════════════════════════════════════════
## OUT OF SCOPE / PARKIR
═══════════════════════════════════════════════════════════
- **DP/deposit booking** → tunggu keputusan visi booking-membership. Future.
- **Buka Kasir eksplisit dengan modal** → boleh Phase 1.5 kalau mau formal.
- PDF closing disimpan di DB → TIDAK (transien, cetak saja).

═══════════════════════════════════════════════════════════
## START SEQUENCE
═══════════════════════════════════════════════════════════
1. Baca `kasir_service.py` (rekap_shift, proses_bayar), `kasir_repo.py`
   (aggregate_pembayaran_shift), schema `kasir.py` (RekapPerMetode), report rekap-kasir.
2. Breakdown Kasir-1: migrasi model → service `tutup_kasir()` + `get_closing_preview()` →
   route + template form → laporan owner. Tunjukkan → minta approval dr. Hansen.
3. Implement (patch-script/heredoc; verify bash py_compile/jinja/null-byte). B-013 sudah
   hilang di E: tapi tetap hati-hati di file besar.
4. Test: simulasi bayar beberapa metode → tutup kasir → cek selisih benar → cek laporan owner.
5. Housekeeping (roadmap + decisions DEC baru).

## URUTAN DENGAN PEKERJAAN LAIN (pra-deployment)
Kandidat pra-deployment, urut saran: **(1) Tutup Kasir** [pain point nyata] → (2) Paket
Keamanan #37-40 → (3) Konektor DermAI / Antropometri [paralel, lintas-proyek] → (4) Deployment.
Tutup Kasir layak duluan karena langsung dipakai harian + melengkapi alur kasir sebelum go-live.

Mulai dengan baca modul kasir, lalu breakdown Kasir-1 → tunggu approval dr. Hansen sebelum coding.
═══════════════════════════════════════════════════════════


═══════════════════════════════════════════════════════════
## STATUS: ✅ COMPLETE (2026-06-27) — ref DEC-075
Semua langkah 1-7 selesai + di-test manual dr. Hansen. Bug data-expected (100x),
UX separator ribuan, filter button, default tanggal, B-025 (__all__) sudah fixed.
═══════════════════════════════════════════════════════════
