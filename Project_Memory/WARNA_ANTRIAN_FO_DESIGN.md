# Design Note — Warna Antrian (Wait-Time) di Layar FO

**Status:** 🟠 DESIGN-ONLY (belum kode). **Dibuat:** 2026-07-07 · diskusi dr. Hansen.
**Asal:** `raw_idea_070726.md` #1 (dipertegas). **Terkait:** `KESTABILAN_OPERASIONAL_EMRPOS.md` (fitur ber-poll → entry checklist).

Tujuan: FO cepat melihat tahap antrian mana yang mulai lama menunggu, lewat warna berbasis **pasien terlama** — mengurangi komplain "diserobot"/menunggu tanpa kabar.

---

## 1. Lingkup

- **Hanya layar FO** ("Antrian Hari Ini", `/web/kunjungan/list`, fragment `_antrian_content.html`). Tidak di dokter/perawat/kasir.
- Fase awal: **Antri Konsultasi** saja (ambang lain menyusul per-tahap bila perlu).

## 2. Aturan warna (Antri Konsultasi)

Berdasarkan **MAX waktu tunggu** (pasien TERLAMA di tahap itu, bukan rata-rata):
- `0–19 menit` → **hijau**
- `20–29 menit` → **kuning**
- `≥30 menit` → **merah**

Contoh: pasien X antri 8 mnt, pasien Y antri 15 mnt → MAX=15 → **hijau**. 6 menit kemudian MAX=21 → **kuning**.

Tampilkan juga angka eksplisit: **"Terlama: N mnt"** (aksesibilitas + presisi, bukan warna saja).

## 3. Sumber data & hitungan

- Waktu tunggu = `now − kunjungan.created_at` untuk pasien berstatus `ANTRI_KONSULTASI`.
- **`created_at` = saat pasien masuk antrian HARI INI** — valid untuk walk-in DAN booking, karena **check-in booking MEMBUAT baris Kunjungan baru saat check-in** (`booking_service.check_in`). Jadi tak ada jebakan "booking 3 hari lalu → menunggu 4320 menit".
- Warna tahap = fungsi dari **MAX** durasi pasien `ANTRI_KONSULTASI`.
- Dihitung atas data yang **sudah diambil** untuk layar FO → **tanpa query tambahan**.

## 4. Kenapa viable (beban ~nol)

- Layar FO = kunjungan yang **sengaja TIDAK di-cache** (fragment ada form+CSRF) → warna selalu **real-time**, dihitung ulang tiap poll 10 detik. Transisi hijau→kuning muncul dalam ≤10 detik setelah menembus ambang. Tidak perlu timer khusus.
- FO = 1 station → dampak beban nihil. Kebetulan pas: warna butuh fresh, layar ini memang uncached.

## 5. WAJIB dibereskan — konsistensi timezone

`created_at` = TIMESTAMP DB (kemungkinan basis UTC); `datetime.now()` app = WIB. Mengurangkan mentah → meleset 7 jam → semua salah warna (langsung merah / negatif).

**Solusi:** hitung durasi **di SQL** `TIMESTAMPDIFF(MINUTE, created_at, NOW())` (tz-konsisten dalam DB), ATAU pastikan kedua sisi basis waktu sama sebelum dikurangkan. Nyambung ke pelajaran DEC-080 (timezone). **Uji dengan data waktu nyata sebelum rilis.**

## 6. Keputusan desain & edge case

- **Ambang = config** (mulai konsultasi 20/30). Tahap lain (Antri Treatment/Bayar/Obat) bisa punya ambang sendiri nanti; untuk itu perlu timestamp "masuk tahap" (untuk tahap lanjutan, `updated_at` = perkiraan kasar karena bump tiap UPDATE; idealnya timestamp transisi eksplisit — di luar fase awal).
- Tahap "sedang dilayani" (`KONSULTASI`) **dikecualikan** — itu in-progress, bukan menunggu.
- Antrian tahap kosong → **netral** (tanpa warna).
- Perlu ekspos `created_at` (atau `wait_minutes` terhitung) per item di response antrian FO agar template bisa menghitung/menampilkan.
- Warna = pembawa info fungsional, bukan dekorasi (prinsip raw_idea).
- Opsional (nice-to-have): tick per-detik di klien agar angka menit bergerak halus antar-poll. Recompute 10 detik sudah cukup untuk warna → tidak wajib.

## 7. Entry checklist kestabilan (lolos)

- [x] Tidak menambah query (hitung atas data yang sudah diambil).
- [x] Tidak menyentuh jalur keputusan (murni tampilan).
- [x] Real-time by design (layar FO uncached) — tak ada isu basi.
- [x] FO-only, 1 station → beban nihil.
- [x] Uji timezone dengan data waktu nyata — LULUS 2026-07-07 (live: merah, terlama 54 mnt = masuk akal, tidak meleset).

---

## 8. Status implementasi (2026-07-07) — SUDAH dibangun

- **Handler** `app/web/routes/kunjungan.py`: konstanta `KONSUL_WAIT_YELLOW_MIN=20`/`RED_MIN=30` + helper `_konsul_wait(items)` (MAX menit ANTRI_KONSULTASI → band warna, clamp negatif/None/>24j) → inject `konsul_wait` ke context `/kunjungan/list`.
- **Timestamp dipakai = `tgl_kunjungan`** (DateTime, tanpa konversi UTC — lebih bersih dari created_at). tz: `datetime.now()` vs `tgl_kunjungan` basis sama (mesin tunggal, DEC-080).
- **Template** `_antrian_content.html`: kartu Antri Konsultasi pakai **inline-style** (border/bg/fg dari `konsul_wait`) + baris "Terlama: N mnt". B-028 safe.
- **Unit test hijau** (8 skenario): contoh 8/15→hijau, +6→21 kuning, batas 19/20/29/30, exclude non-konsultasi, kosong→netral, negatif→clamp, >24j→abaikan.
- Layar FO tidak di-cache → warna real-time tiap poll 10s.

**Live-verified 2026-07-07:** layar FO menampilkan merah, terlama 54 menit — angka masuk akal, tz benar. ✅ SELESAI.

---

*Status: DESIGN-ONLY. Fitur murah & risiko rendah — kandidat fitur kecil pertama, sebelum/berdampingan dengan nomor antrian internal.*

---

## 9. Perluasan multi-tahap (final, 2026-07-07)

FO = timekeeper alur penuh → semua kartu tahap di layar FO diberi warna, **kecuali obat**.

### Ambang final (yellow_min, red_min)

| Tahap | Hijau | Kuning | Merah | Timestamp acuan |
|---|---|---|---|---|
| Antri Konsultasi | <20 | 20–29 | ≥30 | `tgl_kunjungan` (≈ masuk konsultasi) |
| Antri Treatment | <20 | 20–29 | ≥30 | `waktu_masuk_status` |
| Antri Bayar | <6 | 6–10 | >10 | `waktu_masuk_status` |
| **Antri Obat** | **TIDAK diwarnai (ditunda)** | | | — |

Bayar sengaja ketat: merah = sinyal SDM/throughput → FO panggil manajer atau bantu sendiri.

### Kenapa Antri Obat ditunda (bukan sekadar kalibrasi)

Konsultasi & treatment punya status "sedang dilayani" (KONSULTASI, ON_TREATMENT) yang **dikecualikan** dari hitungan tunggu. **Antri Obat tidak punya padanan "sedang diracik"** → pasien yang obat/krim-nya sedang aktif diracik tetap berstatus ANTRI_OBAT → akan tampil merah palsu, dan bisa menekan apoteker terburu-buru pada tugas keselamatan. Jadi diwarnai hanya setelah ada cara membedakan *menunggu* vs *sedang disiapkan*:
- (opsi) tambah status/flag "sedang disiapkan" (mirror ON_TREATMENT) yang dikecualikan, ATAU
- warnai hanya resep non-racik (butuh flag racik di resep).
Sampai itu ada → **obat tidak diwarnai** (hindari alarm palsu).

### Skema teknis: `waktu_masuk_status`

`Kunjungan` tidak punya `updated_at`, jadi wait tahap-lanjutan butuh timestamp "masuk tahap":
- **Kolom baru** `kunjungan.waktu_masuk_status` (DateTime, `server_default = current_timestamp`) → baris baru otomatis terisi = waktu masuk (ANTRI_KONSULTASI).
- **Event listener** SQLAlchemy pada `Kunjungan.status_antrian` (`set`) → stempel `waktu_masuk_status = now()` setiap status BERUBAH (transisi antar-tahap), di mana pun servisnya. Dijaga: lewati set pertama (init/load) & set tak berubah → failure mode aman (under-stamp → fallback, bukan salah stempel).
- **Migrasi** defensif: add kolom + backfill `COALESCE(tgl_kunjungan, created_at, NOW())` untuk baris in-flight (kira-kira; self-heal saat transisi berikutnya).
- Handler pakai `waktu_masuk_status` (fallback `tgl_kunjungan` bila null). Konsultasi tetap akurat via fallback.
- Ambang = config per-status (mudah diubah). Obat tak terdaftar → tak diwarnai.

Beban: tetap ~nol (satu query FO yang sama, MAX per-tahap di memori, FO 1 station uncached).

*Status: DIIMPLEMENTASIKAN 2026-07-07 (lihat §10 setelah eksekusi).*

---

## 10. Status implementasi multi-tahap (2026-07-07) — SUDAH dibangun

- **Model** `kunjungan.py`: kolom `waktu_masuk_status` (server_default now) + **event listener** stempel saat `status_antrian` berubah (guard: lewati init/load & set tak berubah).
- **Migrasi** `20260707_0200_kunjungan_waktu_masuk_status` (head baru, defensif + backfill COALESCE(tgl_kunjungan,created_at,NOW())).
- **Schema+service**: `waktu_masuk_status` diekspos di `KunjunganAntrianItem` + di-pass di `lihat_antrian_hari_ini`.
- **Handler** `_stage_waits()` (ambang per-status config) + context `stage_waits`. **Template**: kartu Konsultasi/Treatment/Bayar berwarna + "Terlama: N mnt". Obat tetap.
- **Ambang final terpakai**: Konsul/Treatment (20,30); **Bayar (6,11)** → 10 mnt masih kuning, 11 mnt merah (sesuai ">10 merah"). Obat tidak diwarnai.
- **Unit test hijau**: batas bayar 5/6/10/11, treatment 19/20/29/30, MAX per-tahap, fallback tgl_kunjungan, obat excluded, kosong→netral. Alembic single-head.

**Perlu live:** `alembic upgrade head` (kolom baru) → cek layar FO. KHUSUS verifikasi **Treatment & Bayar** menit-nya masuk akal (event listener stempel transisi = satu-satunya bagian yang belum teruji runtime; failure mode aman → fallback).
