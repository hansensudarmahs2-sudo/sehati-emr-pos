# Aktivasi Membership via CS + Nomor Member — Design Note

Status: **PERENCANAAN. Belum ngoding.** Divalidasi arah oleh dr. Hansen 2026-09-16.
Terkait: #362D (drop method usang), P2-5 (revert saat void). Bangun SETELAH: Obat Tertunda, P2-5, drop #362D.

## 1. Perilaku SEKARANG (hasil telusur kode)
1. Set/renew tier di `membership_service` → buat baris `pasien_membership_history` **PENDING**
   (`is_active=False`, `id_transaksi_aktivasi=NULL`). `pasien.tipe_membership` BELUM diubah (FIX-362E-A).
2. `proses_bayar` menemukan pending → menagih biaya aktivasi → saat bayar: set `id_transaksi_aktivasi`,
   `is_active=True`, update `pasien.tipe_membership`, buat kuota. **= AKTIF OTOMATIS SAAT BAYAR.**
3. Diskon dibaca dari `pasien.tipe_membership` (live) → kunjungan berikут dapat benefit (same-day OK).
4. Void transaksi yang mengaktifkan → `revert_active_to_pending` (lihat P2-5).
- Data live: 15 history, semua `pernah_aktif` (jalur ini berjalan). Nomor member: **tidak ada**.
- `pasien_service._create_pending_membership_history_if_needed` = **usang/duplikat → DROP** (#362D).

## 2. Perubahan yang diinginkan (model dr. Hansen)
Bayar **TIDAK** langsung aktif → status "sudah dibayar, menunggu aktivasi" → **CS mengaktifkan** manual.
Alasan: kontrol manusia, verifikasi identitas/kartu, cegah salah-aktivasi.

## 3. Model status baru (disambiguasi)
Sekarang status disimpulkan dari kombinasi `is_active` + `id_transaksi_aktivasi` — dan kombinasi
`is_active=False + id_transaksi NOT NULL` SUDAH dipakai untuk EXPIRED/CANCELLED. Menambah state
"paid-awaiting-activation" akan bentrok. **Rekomendasi: tambah kolom eksplisit
`status_aktivasi`** (enum) di `pasien_membership_history`:
- `PENDING` — tier di-set, belum bayar (`id_transaksi_aktivasi=NULL`).
- `PAID` *(BARU)* — sudah bayar, menunggu aktivasi CS (`id_transaksi_aktivasi` terisi, `is_active=False`).
- `ACTIVE` — diaktifkan CS (`is_active=True`, `id_staf_aktivasi` + `tgl_aktif` terisi).
- `EXPIRED` / `CANCELLED` — akhir hidup.
`is_active` tetap dipertahankan sebagai boolean cepat (ACTIVE⇔True), tapi sumber-kebenaran = `status_aktivasi`.

## 4. Alur baru
1. Set tier → PENDING (seperti sekarang).
2. `proses_bayar` bayar aktivasi → set `id_transaksi_aktivasi` + `status_aktivasi=PAID`.
   **JANGAN** set `is_active`, **jangan** ubah `pasien.tipe_membership`, **jangan** buat kuota dulu.
3. **Aksi CS "Aktifkan Membership"** (dari worklist/detail pasien) → `status_aktivasi=ACTIVE`,
   `is_active=True`, `id_staf_aktivasi`, `tgl_aktif=hari ini`, `tgl_expired` dihitung dari tgl aktivasi,
   buat kuota, set `pasien.tipe_membership`, assign **nomor member** (bila belum). Audit `id_staf`.
4. Benefit berlaku setelah CS aktivasi (same-day tetap bisa: aktivasi sebelum kunjungan berikut).

## 5. Nomor Member (baru)
- Kolom `no_member` (unik, human-facing) — untuk kartu fisik & pencarian cepat.
- **Kapan diberikan:** saat CS aktivasi (nomor hanya untuk member yang benar-benar aktif). *(alternatif: saat PAID)*
- **Format:** sekuensial + prefix. Untuk 1 cabang: mis. `M-000123`. Saat multi-cabang (P2-6/Path A):
  bisa pakai prefix cabang (mis. `JJ-M-000123`) — selaraskan dengan keputusan prefix P2-6.
- Simpan di mana: `pasien` (satu no_member per pasien) atau di history? **Rekomendasi: di `pasien`**
  (1 pasien = 1 nomor member seumur hidup, walau renew berkali-kali).

## 6. Interaksi dengan item lain
- **#362D:** method usang tetap **di-drop**; pending dibuat lewat `membership_service` (tak berubah).
- **P2-5 (void):** void saat PAID → balik ke PENDING (batalkan tagihan). Void saat ACTIVE →
  `revert_active_to_pending` (fix savepoint P2-5 tetap diperlukan). Perlu tangani void di state PAID juga.
- **Same-day:** tak berubah secara teknis (diskon dari `pasien.tipe_membership`); hanya bergeser
  pemicunya dari "bayar" ke "CS aktivasi".

## 7. Perubahan data
- `pasien_membership_history.status_aktivasi` (enum) — migrasi + backfill (existing aktif → ACTIVE,
  existing pending → PENDING).
- `pasien.no_member` (varchar unik, nullable).
- 1–2 migrasi Alembic kecil (chain dari head terkini).

## 8. UI / peran
- **Worklist "Membership Menunggu Aktivasi"** (status PAID) → tombol "Aktifkan".
- Bisa sekalian muncul di notifikasi (pola sama Obat Tertunda) supaya CS tak lupa.
- **Siapa boleh mengaktifkan?** Sistem tak punya role "CS" — kandidat = **FO / Kasir / Admin / Owner /
  Superadmin**. (KEPUTUSAN TERBUKA.)

## 9. Keputusan TERKUNCI (dr. Hansen, 2026-09-16)
1. **Masa berlaku** (`tgl_aktif`/`tgl_expired`) di-anchor ke **tgl AKTIVASI** (bukan tgl bayar).
2. **Nomor member** diberikan **saat ACTIVE**; format **`M-000123`** (sekuensial; nanti bisa prefix cabang saat multi-cabang); disimpan di **`pasien.no_member`** (unik, 1 pasien 1 nomor seumur hidup).
3. **Role yang boleh mengaktifkan** = **FO + Kasir + Admin + Owner + Superadmin**.
4. **Kuota treatment dibuat saat AKTIVASI** (bukan saat bayar).
5. **Ada peringatan "PAID belum diaktifkan"** = worklist **"Menunggu Aktivasi"** + badge/notifikasi (pola Obat Tertunda).

## 10. Rencana build (nanti, setelah 3 item prioritas)
- M1. Migrasi `status_aktivasi` + `no_member` + backfill. Model + enum.
- M2. Ubah `proses_bayar`: bayar → PAID (tak auto-aktif). Sesuaikan display tier.
- M3. Aksi CS "Aktifkan" (service + route + tombol) → ACTIVE + kuota + no_member + audit.
- M4. Worklist "Menunggu Aktivasi" + notifikasi. Tangani void di state PAID (nyambung P2-5).
- M5. Verifikasi: py_compile + jinja + test (set→bayar→PAID→aktifkan→benefit; void di PAID & ACTIVE) + smoke.

---
## BUILD LOG
- **M1 — DONE 2026-09-16 (live).** Enum `StatusAktivasiEnum` + kolom `pasien_membership_history.status_aktivasi`
  (default PENDING) + `pasien.no_member` (unik). Migrasi `20260916_0200` (backfill: 15 existing → ACTIVE).
  Head migrasi = `20260916_0200`. Perilaku BELUM berubah (pay masih auto-aktif) — status_aktivasi belum dibaca kode.
- **M2–M5 — PENDING** (sesi berikutnya): proses_bayar→PAID; aksi CS "Aktifkan" (ACTIVE+kuota+no_member `M-000123`+audit);
  worklist "Menunggu Aktivasi" + badge; tangani void di PAID; test+smoke.
  Keputusan sudah terkunci di §9. Role aktivasi: FO/Kasir/Admin/Owner/Superadmin. tgl_aktif=tgl aktivasi. Kuota saat aktivasi.

---
## 11. REVISI M2 — ISOLASI TRANSAKSI MEMBERSHIP (TERKUNCI, dr. Hansen 2026-09-17)

**Temuan pemicu:** `subtotal_aktivasi` saat ini MENEMPEL di transaksi klinis (kolom
`transaksi_kasir.subtotal_aktivasi_membership` + `id_membership_aktivasi_pending`) →
membership "terseret" saat bayar produk. Akibatnya koreksi membership memaksa **void
transaksi gabungan yang ikut membalik STOK** → frekuensi void membengkak (flaw utama).

**Keputusan terkunci:**
1. **Membership = transaksi_kasir SENDIRI**: `id_kunjungan=NULL`, `jenis_transaksi=MEMBERSHIP`.
   **Cabut `subtotal_aktivasi` dari `get_tagihan`/`proses_bayar`** — tagihan klinis tak lagi
   memuat membership. (Isolasi void = pemisahan BARIS transaksi, bukan pemisahan kunjungan.)
2. **Bayar → PAID** (tak auto-aktif; jangan set `is_active`/`tipe_membership`/kuota). **CS "Aktifkan"**
   → ACTIVE + kuota + `no_member` `M-000123` + `tgl_aktif` + audit (sesuai §9).
3. **TANPA blok keras.** Sebagai gantinya: saat membuat tagihan produk/tindakan sementara pasien
   punya membership PENDING/PAID (belum ACTIVE) → **WARNING**: "Membership belum diaktifkan — harga
   tanpa diskon member." Sistem TETAP mengizinkan lanjut. Produk dibuat dulu → harga **tanpa diskon
   member** (member belum aktif); membership menyusul bebas. Urutan (aktifkan dulu utk diskon
   same-day) = **tanggung jawab SOP/training operator**, bukan dipaksa sistem.
4. **Void per-transaksi (isolasi):** void membership → hanya membership (STOK AMAN); void produk →
   hanya stok. Saat void membership yang **menurunkan status aktif** → **WARNING** bila ada transaksi
   same-day yang memakai diskon member (TIDAK auto-adjust; kasir yang putuskan). Flaw diskon-menggantung
   itu sempit: hanya aktivasi-PERTAMA + void same-day; **renewal tak terpengaruh** (status tetap aktif).
5. **Antrian kasir:** bedakan label "Membership (aktivasi/renewal)" vs "Klinis" (cegah salah/dobel bayar).

**Lingkup:** M2 kini = **refaktor alur tagihan** (memisah membership dari tagihan klinis), bukan sekadar
ubah status → PAID. Semua §9 tetap berlaku. Status: TERKUNCI, siap dibangun (belum ngoding).

## BUILD LOG M2 (mulai 2026-09-17)
- **M2a DONE (belum deploy):** migrasi `20260917_0200_transaksi_pasien_jenis` — `transaksi_kasir` + `id_pasien` (FK pasien, nullable, index) + `jenis_transaksi` (KLINIS default / MEMBERSHIP). Backfill: id_pasien dari kunjungan, jenis lama=KLINIS. Model transaksi.py diupdate. Head migrasi = `20260917_0200`.
- **M2b DONE (belum deploy):** `membership_service.bayar_membership(id_history, pembayaran, id_staf_kasir, ...)` → buat TransaksiKasir(id_kunjungan=NULL, id_pasien, jenis=MEMBERSHIP, id_membership_aktivasi, nominal) + pembayaran + set `status_aktivasi=PAID`, `id_transaksi_aktivasi`. TIDAK set is_active/tipe_membership/kuota (aktivasi=CS/M3). Audit MEMBERSHIP_PAID. Guard: hanya PENDING yg bisa dibayar.
- **SISA M2 (belum):** M2c antrian kasir tampilkan membership PENDING + layar/route "Bayar Membership" → panggil bayar_membership. M2d cabut subtotal_aktivasi dari get_tagihan + hapus blok aktivasi dari proses_bayar + set jenis/id_pasien di transaksi klinis. M2e audit query laporan/rekap/void utk transaksi id_kunjungan=NULL (jangan hilang/errof) + tangani void transaksi MEMBERSHIP (PAID→PENDING, no stok). LALU M3 (aktivasi CS) sebelum DEPLOY (M2 sendiri = membership mentok di PAID).

- **M2c DONE (belum deploy):** antrian kasir menampilkan seksi "Membership — Menunggu Pembayaran" (dari `list_membership_pending`, schema `MembershipPendingItem`, `AntrianKasirResponse.membership_pending`). Layar `kasir_bayar_membership.html` + route `GET/POST /kasir/membership/{id_history}/bayar` → panggil `bayar_membership`. Sukses → redirect antrian dgn flash "MENUNGGU AKTIVASI CS".
- **M2d DONE (belum deploy):** `get_tagihan` TIDAK lagi query pending membership / tambah subtotal_aktivasi (selalu 0/None). `proses_bayar`: transaksi klinis kini set `jenis=KLINIS` + `id_pasien`, TANPA id_membership_aktivasi; blok aktivasi membership (77 baris) DIHAPUS. Template `kasir_tagihan.html` baris aktivasi auto-hilang (sudah ber-`{% if >0 %}`).
- **M2e DONE (belum deploy):** void transaksi MEMBERSHIP → `revert_paid_to_pending` (PAID→PENDING, no stok); `revert_active_to_pending` juga reset `status_aktivasi=PENDING`. `list_riwayat_bayar_hari_ini` outer-join kunjungan + pasien via `transaksi.id_pasien` (backfill) → transaksi membership muncul di riwayat (label MEMBERSHIP, tanpa link tagihan/nota). Rekap kas sudah ikut membership (join via TransaksiPembayaran, bukan kunjungan). 
- **PENTING sebelum DEPLOY:** M2 tanpa M3 = membership bisa dibayar (PAID) tapi BELUM bisa diaktifkan (mentok PAID). Aktivasi lama (auto saat bayar) sudah dicabut. Jadi: uji M2 boleh (isolasi/PAID/void), tapi aktivasi penuh menunggu M3. JANGAN anggap regресi — memang berurutan.

- **M2f DONE (belum deploy) — temuan uji desktop:** membuat membership pending dulu ikut bikin kunjungan kosong ANTRI_BAYAR (route `create-billing` / `create_kunjungan_billing`, pola lama) → muncul baris klinis REGULAR 0/0 di kasir + memblok beli-produk dgn alasan salah. Fix: (1) tombol "Buat Tagihan Sekarang" DIHAPUS dari `pasien_membership.html`; route `/membership/create-billing` dinetralkan (no-op redirect, tak buat kunjungan). Pending otomatis muncul di kasir seksi Membership (M2c). (2) beli-produk GET: warning LUNAK bila pasien punya membership PENDING/PAID ("produk tanpa diskon member sampai diaktifkan") — tidak memblok. `create_kunjungan_billing` di membership_service kini dead-code (biarkan). Verifikasi compile+jinja OK.

## BUILD LOG M3 (2026-09-17, belum deploy)
- **M3a:** `get_status_pasien` kini query `paid_hist` (status_aktivasi=PAID) + kunci `paid` di dict; `status_label` history pakai `status_aktivasi` (PAID tampil PAID, bukan EXPIRED). Memperbaiki bug tampilan "EXPIRED" utk membership yg baru dibayar.
- **M3b:** `membership_service.activate_membership(id_history, actor)` — guard hanya PAID; anchor masa berlaku ke tgl aktivasi (durasi_bulan*30; RENEWAL carry-over dari prev active); deactivate history aktif lain (replace); set pasien.tipe_membership; assign `no_member` via `_generate_no_member()` (format `M-000123` sekuensial, backstop UNIQUE); buat kuota (reuse `KasirService._create_kuota_from_benefit`, local import cegah circular); audit MEMBERSHIP_ACTIVATE.
- **M3c:** route `POST /pasien/{id}/membership/{id_history}/aktifkan` (role require_antrian_mgmt_role) → activate_membership → flash "AKTIF. Nomor member: M-...".
- **M3d:** kartu "Menunggu Aktivasi (Sudah Dibayar)" + tombol Aktifkan di `pasien_membership.html` (muncul saat status_data.paid).
- **SISA:** M4 worklist "Menunggu Aktivasi" + badge/notifikasi (pola Obat Tertunda) — opsional. Lalu deploy M2+M3(+M4) bersama + M5 test. Catatan: role aktivasi saat ini = require_antrian_mgmt_role (cek apakah sudah termasuk Kasir sesuai §9; kalau belum, sesuaikan).

## FIX TIER-BEBAS (2026-09-17, belum deploy) — temuan uji M3
Bug: tier custom "Platinum" (master_membership) tak ada di `MembershipTierEnum` (REGULAR/VIP/VVIP) → saat aktivasi `pasien.tipe_membership` gagal di-set (ValueError, stay REGULAR) → "Tier saat ini REGULAR" + diskon 0.
Fix (dr. Hansen pilih: perlu nama tier bebas):
- `get_diskon_for_pasien` kini baca dari **history ACTIVE** (join master_membership), BUKAN enum → diskon jalan utk tier apa pun.
- `pasien.tipe_membership` ENUM → **VARCHAR(20)** (migrasi `20260917_0300`). Bisa simpan nama tier bebas.
- Model pasien.py String(20); schema response `tipe_membership: Optional[str]` (pasien.py x2, kunjungan.py x1); register simpan `.value`; `activate_membership` set `pasien.tipe_membership = tier.nama_tier`; revert (2x) set string `target_tier` (drop `MembershipTierEnum(...)` yg bisa ValueError).
- Helper display existing `x.value if hasattr else str(x)` sudah menangani string → aman.
- CATATAN: member yang SUDAH diaktifkan SEBELUM fix (mis. Hansen Platinum) punya cache tipe_membership stale=REGULAR (diskon tetap jalan dari history). Sync opsional via re-aktivasi / UPDATE. Uji baru: pakai patient fresh.
- SISA UX (permintaan user): setelah bayar membership → sediakan cetak NOTA membership + shortcut "Kelola/Aktifkan" (khusus transaksi MEMBERSHIP). Belum dibuat (M4/polish).
Head migrasi kini = `20260917_0300`.

## FIX TIER-BEBAS lanjutan (2026-09-17) — buka kunci nama tier
Temuan uji: form Master Membership "Nama Tier" masih `<select>` REGULAR/VIP/VVIP + service `create_tier`/`update_tier` menolak nama non-enum (`_VALID_TIER_NAMES`). Fix:
- `master_membership_service.create_tier`+`update_tier`: buang cek `_VALID_TIER_NAMES`, preserve case (drop `.upper()`), hanya larang "REGULAR". 
- `master_membership_form.html`: `<select>` → `<input type=text>` bebas.
Terbukti: Juli Nugroho (fresh) → aktivasi tier "silver" sukses ubah pasien jadi member silver (fix aktivasi+string bekerja).
CATATAN cache lama: member yg diaktifkan SEBELUM fix (Hana) tetap tipe_membership stale; diskon tetap benar (dari history). Opsi sync sekali: `UPDATE pasien p JOIN pasien_membership_history h ON h.id_pasien=p.id_pasien AND h.is_active=1 JOIN master_membership m ON m.id_membership=h.id_membership SET p.tipe_membership=m.nama_tier;` (belum dijalankan). 
SISA UX: nota membership + shortcut aktivasi setelah bayar (permintaan user) — belum.

## UX pasca-bayar membership (2026-09-17) — nota + shortcut aktivasi
Permintaan user terpenuhi:
- `print_service.prepare_nota_context` dipatch: pasien fallback via `trx.id_pasien` (transaksi MEMBERSHIP id_kunjungan NULL) + baris item "Aktivasi Membership <tier>" (dari id_membership_aktivasi + nominal). Nota A5/thermal existing kini benar utk membership.
- Bayar membership (POST) → redirect ke halaman sukses baru `GET /web/kasir/membership/sukses/{id_transaksi}` (template `kasir_bayar_membership_sukses.html`): tombol Cetak Nota A5/Thermal + shortcut "Aktifkan/Kelola Membership" (ke /web/pasien/{id}/membership) + Kembali Antrian.

## BUILD LOG M4 (2026-09-17, belum deploy) — worklist + badge
- `membership_service`: `list_awaiting_activation()` + `count_awaiting_activation()` (status_aktivasi=PAID).
- Route baru `app/web/routes/membership_aktivasi.py` → `GET /web/membership-aktivasi` (worklist) + template `membership_aktivasi_list.html` (tabel PAID + tombol Aktifkan → POST ke route aktivasi existing `?next=/web/membership-aktivasi`). Registered di router.py.
- Route aktivasi (`pasien_membership_aktifkan`) kini honor `?next=` (kembali ke worklist) + guard diperluas ke Kasir (§9: FO+Kasir+Admin+Owner+Superadmin).
- `_shared.build_shell_context`: `membership_aktivasi.total` (cache 30s) + `can_membership_aktivasi` (Owner/Superadmin/Admin/Kasir/FO).
- `_app.html`: badge header 🎖️ + count. `dashboard.html`: kartu alert. `menu.py`: MENU_MEMBERSHIP_AKTIVASI di 5 role.
- Tanpa migrasi baru (head tetap 20260917_0300).
- SISA: M5 test/smoke + DEPLOY (rsync + up --build) M2+M3+M4 ke mini PC.

## STATUS 2026-09-17: M2+M3+M4 TERVALIDASI DI DESKTOP (belum deploy)
Fix terakhir M4: dashboard handler (auth.py) bangun ctx sendiri → tambah `membership_aktivasi`+`can_membership_aktivasi` manual (badge+kartu kini muncul di dashboard juga). Semua fitur Membership CS jalan di desktop (dev DB head 20260917_0300).
SISA: M5 regresi (pytest) + DEPLOY ke mini PC (rsync + up --build; migrasi 0200+0300 jalan otomatis di live) + smoke test live. Migrasi live saat ini di 0100; deploy ini naikkan ke 0300.
