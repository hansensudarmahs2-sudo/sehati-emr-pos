# Design Note — Antrian: 2 Jalur (Konsultasi bernomor + Treatment berjam), Skip, Cetak Thermal

**Status:** 🟠 DESIGN (belum kode). **Diperbarui:** 2026-07-07 (klarifikasi dr. Hansen).
**Asal:** `raw_idea_070726.md` #2/#3. **Terkait:** Booking (DEC-083), KESTABILAN (landing/QR ≥6 bln).

> Ternyata #2 bukan "cetak nomor" belaka, tapi **model orkestrasi antrian**. Cetak thermal = langkah terakhir yang mudah di atas model ini.

---

## 0. RUANG LINGKUP — EMR vs OFFLINE (kunci, dr. Hansen 2026-07-07)

**Di dalam EMR, nomor antrian = label bantu yang DECOUPLED — tidak terkait state apa pun.** Alur klinis/POS digerakkan `status_antrian`, BUKAN urutan nomor. Nomor yang di-skip **tidak mengubah apa pun** di EMR.

Konsekuensi:
- **Software (EMR) hanya perlu:** generate nomor (sudah ada) + **cetak thermal**. Titik.
- **Semua orkestrasi (skip/call 2×/forfeit >1 jam/reservasi bed/konfirmasi hari-H/treatment-berjam) = MANAJEMEN OFFLINE oleh FO** (timekeeper + flow + waiting-room manager). Ini **SOP manusia**, bukan state machine software. §2–§4 di bawah = **dokumentasi SOP FO**, bukan spesifikasi build.
- **NA-L1 (state-machine skip) TIDAK dibangun.** Bila kelak ingin mendigitalkan bantuan FO (papan panggil dsb.), baru dipertimbangkan — di luar scope awal.

**Jadi build #2 = cetak thermal saja (kecil).**

---

## 1. Konsep dasar

**Tipe booking:** berbayar / tidak berbayar · dan konsultasi / treatment.
**Fase awal generalisasi:** semua booking (paid/unpaid) **wajib KONFIRMASI hari-H** untuk mendapat token antrian. Tak konfirmasi = tak dapat token. (Beda paid/unpaid ditunda.)

**DUA JALUR, dua jenis token — ini menyelesaikan kebingungan "dua nomor":**

| Jalur | Token | Urutan |
|---|---|---|
| **Konsultasi** | **NOMOR** (FIFO) | dilayani via call + skip |
| **Treatment** | **JAM (slot)**, TANPA nomor | dijadwalkan per waktu + kapasitas bed |

Nomor **≠ urutan dilayani** — hanya identitas. Booking nomor 1 yang telat bisa masuk setelah nomor 6.

---

## 2. Jalur KONSULTASI (bernomor)

**Pemberian nomor:**
- Walk-in konsultasi → nomor saat daftar.
- Booking konsultasi → nomor **hanya setelah konfirmasi hari-H**. Unconfirmed → tak dapat nomor.

**Serving = call + skip (raw_idea #3), dipicu oleh FO:**
- Nomor baru tetap **berurutan** (#2, #3, #4…). Nomor yang **di-skip** masuk "antrian retry".
- **Di setiap batas layanan** (sebelum memanggil nomor baru berikutnya): FO **retry nomor yang di-skip 2× call** dulu (urut nomor). Hadir → dilayani; tidak → tetap di antrian retry, lanjut ke nomor baru berikutnya.
- **Gugur (forfeit) by default** bila nomor yang di-skip belum datang **>1 jam** (sejak pertama di-skip) DAN tak ada konfirmasi / balasan dari tim FO → keluar dari antrian retry.

Contoh: #1 (booking) 2×call tak hadir → **skip** → layani #2 → #2 selesai → retry **#1** 2×call tak hadir → layani #3 → #3 selesai → retry **#1** 2×call → … sampai #1 datang atau gugur (>1 jam). Nomor baru terus berjalan; #1 selalu dicoba lebih dulu tiap batas.

---

## 3. Jalur TREATMENT (berbasis jam, tanpa nomor)

- **Kapasitas:** 4 bed. **1 bed di-reserve** untuk booking treatment (membership). Walk-in / approved-series pakai **3 bed**.
- **Booking treatment** = slot **jam** (bukan nomor). Butuh konfirmasi hari-H.
- **Aturan bed reserved (interpretasi — konfirmasi):** bed reserved ditahan untuk booking dengan **grace 15 menit** dari jam janji. Bila booking telat **>15 menit**, bed **dilepas** ke walk-in/series yang menunggu (agar bed tak idle). Bila 3 bed walk-in penuh, pasien treatment ke-4 menunggu **sampai ada bed free**.

---

## 4. Pasien bisa di DUA jalur

Mis. konsultasi dulu (dapat nomor) → dokter menyetujui tindakan → masuk jalur treatment (slot jam). Jadi "dua antrian" = **satu nomor (konsul) + satu slot jam (treatment)**, bukan dua nomor.

---

## 5. Cetak thermal (mudah, reuse infra)

Infra sudah ada (`PrintService` pola A5/thermal, `print/*_thermal.html`, auto-print, `_audit_print`).
- **Konsultasi:** cetak **NOMOR** saat nomor diberikan (daftar walk-in / konfirmasi booking).
- **Treatment:** cetak **JAM slot** (bukan nomor).
- Isi: klinik + tanggal · NOMOR/JAM (besar) · nama (boleh nama depan) · jalur (Konsul/Treatment). Field token disiapkan (QR fase publik nanti). **PII minimal**, tanpa data medis.
- **NON-BLOCKING:** printer gagal ≠ gagal daftar; ada cetak-ulang.

---

## 6. Data/state yang dibutuhkan (indikatif)

- Per kunjungan: **jalur** (KONSUL/TREATMENT), **nomor** (konsul saja), link booking, **status konfirmasi hari-H**, **hitungan call**, **skip count**, **status gugur**, jam-slot (treatment).
- Sudah ada: `nomor_antrean`, `status_antrian`, `id_booking`, tabel `jadwal_booking` (kolom RESERVED, DEC-083).
- Baru: mekanisme call/skip/forfeit + kapasitas bed + grace 15 menit (treatment).

---

## 7. Rencana build (software)

**Hanya satu lapisan yang jadi software (sisanya SOP offline / ditunda):**
- **NA-PRINT — Cetak thermal (satu-satunya build EMR):** `PrintService.prepare_antrian_context` + `print/antrian_thermal.html` + route cetak + tombol di FO (auto-print opsional). Konsul = cetak NOMOR; (treatment biasanya pakai jam janji — opsional dicetak). Non-blocking (printer gagal ≠ gagal daftar) + audit. Kecil, reuse infra.
- **Ditunda ≥6 bln live:** QR di slip + landing publik tracking (cache + rate-limit).
- **Bukan software (SOP FO offline):** skip/call/forfeit, reservasi bed + grace 15 mnt, konfirmasi booking hari-H, treatment berjam. Didokumentasikan di §2–§4 sebagai acuan SOP; digitalisasi = pertimbangan jauh, di luar scope.

---

## 8. Keputusan TERKUNCI (dr. Hansen 2026-07-07)

1. Treatment **murni jam**, tanpa nomor. ✅
2. Bed reserved: grace 15 menit; telat >15 mnt → dilepas ke walk-in; kalau penuh, tunggu bed free. *(interpretasi — konfirmasi)*
3. Semua booking (paid/unpaid) **konfirmasi hari-H** untuk dapat token. ✅
4. Skip: 2× call → skip → **retry 2× di tiap batas layanan (sebelum nomor baru), urut nomor** → **gugur bila >1 jam tanpa konfirmasi**. Nomor baru tetap berurutan. ✅
5. **Pemicu Panggil/Skip = FO** (FO = timekeeper + flow manager + waiting-room manager). ✅
6. Kapasitas bed (4) + reserved (1) = **config per klinik**. ✅

## 9. Terbuka (kecil, bisa diputus saat build)

- Titik acuan "1 jam" forfeit: dari **pertama di-skip** (asumsi sekarang) vs dari jam janji booking.
- Semua ambang (grace 15 mnt, forfeit 60 mnt, jumlah call 2×) sebaiknya **config** agar mudah dikalibrasi.

*Status: DESIGN-ONLY. Modul orkestrasi antrian; cetak thermal = lapisan terakhir.*
