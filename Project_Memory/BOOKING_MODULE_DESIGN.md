# RANCANGAN MODUL BOOKING — Sehati eMR-POS

**Disusun:** 2026-06-29 · status RANCANGAN (belum coding; perlu approval dr. Hansen).
**Referensi:** mockup dr. Hansen (kalender bulan + per-tanggal tombol Booking/Details), TODO_SEHATI §D.

## 1. Tujuan & Prinsip
- **Manual booking schedule** oleh staf klinik (belum ada self-booking pasien via web).
- **MEMBERSHIP-ONLY**: hanya pasien membership yang boleh booking; non-member ditolak.
- **Deposit/DP = PARKIR**, tapi siapkan **kerangka siap-bayar** (kolom reserved) untuk masa depan
  (mis. booking berbayar saat dijual ke klinik lain).
- **Kalender bulanan** (default) + Day/Week; tiap tanggal: daftar top-3 booking, tombol **Booking**
  (dropdown tambah/edit/hapus) + tombol **Details**. Tombol **New Booking** global.
- **Tone warna ikut app** (slate/emerald/blue/amber). **Timezone WIB** (konsisten A4/DEC-080).

## 2. Reuse & Perluasan Data (yang SUDAH ada)
Tabel `jadwal_booking` sudah ada: `id_booking, id_pasien, tgl_rencana(date), jam_rencana(time),
sumber_pendaftaran, status_booking, id_booking_lama, created_at`.
`StatusBookingEnum` = BOOKED / CONFIRMED / RESCHEDULED / CANCELLED / CHECKED_IN. `kunjungan.id_booking` (FK) sudah ada.

**Tambahan kolom (migrasi kecil):**
- `id_staf_dokter_dituju` (int nullable, FK master_staf) — dokter yang dituju (opsional).
- `keluhan_utama` (str nullable) — alasan booking.
- `catatan` (text nullable).
- `id_staf_input` (int nullable, FK master_staf) — pembuat/pengubah (audit).
- `updated_at` (timestamp).
- **RESERVED (siap-bayar, PARKIR — tidak dipakai sekarang):** `biaya_booking` (DECIMAL nullable),
  `status_pembayaran_booking` (str nullable: NONE/DP/LUNAS). Disiapkan agar aktivasi booking-berbayar
  nanti tanpa migrasi ulang.

## 3. Aturan Bisnis
- **Gate membership:** hanya `pasien.tipe_membership ∈ {VIP, VVIP}` (REGULAR ditolak dengan pesan jelas).
  **[TERKUNCI: VIP + VVIP; REGULAR ditolak]**
- **Lifecycle status:**
  `BOOKED` → `CONFIRMED` → (hari-H) `CHECKED_IN`. Cabang: `RESCHEDULED` (buat booking baru, isi
  `id_booking_lama`), `CANCELLED`.
- **Check-in** (hari-H): staf klik Check-in → **pilih target: ANTRI_KONSULTASI atau ANTRI_TREATMENT**
  (Tindakan = untuk series / member yang punya kuota tindakan) → buat `Kunjungan`, set `kunjungan.id_booking`,
  `booking.status = CHECKED_IN`, `sumber_pendaftaran` diturunkan. Menyambung ke alur antrian yang ada. **[TERKUNCI]**
- **Overlap/slot:** manual, jam bebas (boleh overlap; informational, bukan hard-block). **[TERKUNCI: bebas]**
- **Role kelola booking:** FO + Admin + Owner + Superadmin **+ Kasir** (kasir = cadangan saat FO sibuk, prioritas kedua). **[TERKUNCI]**
- **Timezone:** WIB (`datetime.now()`), batas hari 00:00–23:59.

## 4. UI (mengikuti mockup, tone app)
**Menu nav baru:** "📅 Booking / Jadwal" → halaman kalender.
- **Header:** judul bulan + `<`/`>` + **Today** + toggle **Day/Week/Month** + tombol **New Booking** (emerald).
- **Grid bulanan** (Sen–Min). Tiap sel tanggal:
  - **Top-3 booking**: `[✓] Nama (jam)` + badge status (Confirmed=biru, Booked=slate, Checked-in=emerald,
    Cancelled=merah, Rescheduled=amber). "+N lainnya" bila >3.
  - Tombol kecil **Booking** → dropdown: **+ Tambah** / **✎ Edit** / **🗑 Hapus**.
  - Tombol **Details** → panel/halaman semua booking hari itu.
- **Details per hari:** daftar semua booking + aksi per baris (Confirm, Reschedule, Check-in→[Konsultasi/Tindakan], Cancel, Edit).
- **Form Tambah/Edit:** cari pasien (**wajib membership**), tanggal, jam, dokter dituju (opsional),
  keluhan, catatan.
- **Day/Week view:** timeline per jam — **FASE 2**; **Fase 1 = Month view** (TERKUNCI).

## 5. Alur (state machine ringkas)
```
[Buat] BOOKED --confirm--> CONFIRMED --hari-H check-in--> CHECKED_IN --> Kunjungan (ANTRI_KONSULTASI)
   |                            |
   +--reschedule--> (booking baru, id_booking_lama=old) 
   +--cancel--> CANCELLED
```

## 6. Kerangka Siap-Bayar (PARKIR — tidak dibangun sekarang)
- Kolom `biaya_booking` + `status_pembayaran_booking` disiapkan tapi tak dipakai.
- Saat diaktifkan nanti: booking berbayar → buat tagihan (reuse `KasirService`), DP via `transaksi_kasir`.
  Tidak ada logika pembayaran booking di fase ini.

## 7. Breakdown Implementasi (bertahap, SETELAH approval)
1. **DB**: migrasi extend `jadwal_booking` + update model.
2. **Service `BookingService`**: list per bulan/tanggal, create/edit/cancel/reschedule/confirm/check-in,
   gate membership, audit.
3. **Route + template**: kalender bulan + per-day dropdown + Details + form. Menu + role.
4. **Integrasi check-in → Kunjungan** (reuse KunjunganService/Repo).
5. **Test**: gate membership tolak REGULAR; check-in buat kunjungan + link id_booking; reschedule link lama.
6. **Housekeeping**: DEC + roadmap.

## 8. Keputusan (TERKUNCI 2026-06-29)
1. Membership = **VIP + VVIP** (REGULAR ditolak).
2. Role kelola = **FO + Kasir + Admin + Owner + Superadmin** (Kasir prioritas kedua / cadangan).
3. Check-in = staf pilih **ANTRI_KONSULTASI** atau **ANTRI_TREATMENT** (tindakan utk series/member ber-kuota).
4. Overlap jam = **bebas** (manual, informational).
5. Fase 1 = **Month view**; Day/Week = Fase 2.

---
*Rancangan direview dulu; implementasi menyusul per breakdown §7 setelah open questions dijawab.*
