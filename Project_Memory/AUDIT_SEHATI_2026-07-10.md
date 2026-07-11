# AUDIT SEHATI eMR-POS — 2026-07-10 (read-only, tanpa perubahan kode)

Audit menyeluruh via review langsung core auth/config/session + 3 agen paralel (kontrol akses,
korektnitas keuangan/inventory, keamanan SQL/data-layer). Disilangkan dengan audit sebelumnya
(`AUDIT_SEHATI_2026-06-29.md`, `AUDIT_ASVS_SEHATI_2026-07-03.md` + catatan tindak lanjut).
**Tidak ada file aplikasi yang diubah.** Ini daftar temuan + prioritas.

## Ringkasan eksekutif

Postur Sehati tetap **solid untuk MVP** dan jauh di atas rata-rata aplikasi buatan sendiri: auth benar
(role di-fetch dari DB tiap request), CSRF full coverage jalur web, SQL ter-parameterisasi (nihil injection),
bcrypt cost 12, rate-limit login bertingkat, guard boot produksi menolak JWT secret lemah, cookie
`HttpOnly`+`SameSite`+`Secure` config-driven, locking `SELECT FOR UPDATE` di banyak jalur stok.

**Temuan terpenting kali ini BUKAN di keamanan — tapi di integritas keuangan/inventory.** Audit-audit
sebelumnya fokus ASVS/keamanan dan tidak memeriksa jalur uang secara mendalam. Dua bug korektnitas baru
(P0) di jalur void-stok dan double-payment, plus beberapa gap rekonsiliasi. Untuk sistem yang memegang kas,
komisi, dan stok obat, ini lebih penting daripada sisa item hardening keamanan.

Dua temuan keamanan baru (XSS tersimpan via `| safe`, CSV formula injection) **tidak tertangkap audit ASVS**
— bahkan bertentangan dengan kesimpulan §5.2.x audit itu (yang menyatakan autoescape mencegah XSS-tersimpan).

Catatan lama masih terbuka: **Finance API tanpa auth (P1-5 lama)** dan **rollback session di helper membership
(P1-2 lama)** belum ditutup. Test jalur uang (P1-4 lama) masih belum lengkap — C1/C2 di bawah sebagian akibatnya.

---

## 🔴 P0 — Wajib dibenahi sebelum andalkan angka stok/uang

**P0-1. Void "reverse stok" menambah inventory untuk barang yang belum pernah keluar (overstate stok).**
`kasir_service.py:959-1030` (`_reverse_stok_per_item`), dipanggil dari `void_transaksi:1178` + `force_past_day_void:1298`.
Terverifikasi: `proses_bayar` (`kasir_service.py:505-732`) **tidak** memotong `stok_terkini` — potong stok baru terjadi
saat serah obat di apotek (`apotek_service.serahkan_obat:158-162`). Tapi `_reverse_stok_per_item` tanpa syarat
**menambah** qty ke `produk.stok_terkini` (l.984-986) dan ke lot (l.996-1007) untuk tiap item yang dichecklist
operator, tanpa cek apakah barang pernah diserahkan.
Skenario normal: bayar di kasir → status `ANTRI_OBAT` (obat belum diserah, stok masih utuh) → void same-day
dengan item dicentang → `stok_terkini` + lot dikredit qty yang tak pernah dipotong. **Inventory overstated senyap.**
Fix: gate reversal pada "apakah resep benar-benar sudah diserahkan/dispensed" (mis. hanya reverse kalau
detail sudah menembus tahap serah), atau catat lot-terpakai per `transaksi_detail_produk` saat dispense.

**STATUS: INTERIM GUARD SELESAI (2026-07-10).** `_reverse_stok_per_item` sekarang skip reverse kalau
`transaksi.id_kunjungan` kosong ATAU `kunjungan.status_antrian != "COMPLETED"` (helper
`_produk_stok_sudah_dipotong`, `kasir_service.py`). Dasar: stok produk HANYA dipotong saat serah obat
(`serahkan_obat` men-transisi `ANTRI_OBAT -> COMPLETED`; satu-satunya jalur potong stok produk). Terverifikasi
tak ada jalur walk-in tanpa-kunjungan di produksi (proses_bayar 404 tanpa kunjungan). Tes gerbang:
`test_repro_P0_1_void_stock_inflation.py` (ANTRI_OBAT→no-op; COMPLETED→reverse sah); tes lot lama
(`test_void_return_lot`, `test_kasir_void_exclusion::test_void_reverse_stok`) diperbarui pakai kunjungan
COMPLETED. Full suite hijau (84 passed / 31 skipped / 1 xfailed).

**STATUS LANJUTAN: FIX PENUH LOT-PROVENANCE SELESAI (2026-07-10)** — sekaligus menutup H2/P1-2:
- Migrasi `20260710_2200`: tabel `kunjungan_lot_terpakai(id_kunjungan, id_produk, id_lot, qty, reversed_at)`
  + index `ix_klt_kunjungan_produk`. Model `KunjunganLotTerpakai`.
- `serahkan_obat._simpan_lot_terpakai`: merekam tiap lot FEFO yang dipotong saat serah.
- `_reverse_stok_per_item`: kini mengembalikan qty ke **lot ASLI** (ED asli terjaga, FEFO benar) via jejak
  itu, menandai `reversed_at` (anti double-restore). Fallback ke lot pilihan operator lalu 'VOID-RETURN'
  HANYA untuk transaksi legacy tanpa jejak → tes lot lama tetap hijau.
Gerbang: `test_repro_H2_lot_provenance.py` (reader: restore ke lot asli, no VOID-RETURN, jejak reversed;
writer: serah menulis jejak). Full suite 87 passed / 31 skipped.
**Batas coverage:** seperti proses_bayar, `serahkan_obat` `commit()` sendiri → wiring end-to-end serah tak
diuji otomatis (writer & reader diuji terpisah; wiring 1 baris terverifikasi review + boot).

**P0-2. Race double-payment / double-komisi (TOCTOU, tanpa lock, tanpa unique constraint).**
`kasir_service.py:511-575` + `transaksi.py:10-11`.
Terverifikasi: guard "sudah lunas" hanya baca non-locking (`get_transaksi_for_kunjungan` = `SELECT ... LIMIT 1`,
`kasir_repo.py:146-158`), dan `transaksi_kasir.id_kunjungan` = FK nullable **tanpa unique constraint**.
Dua `proses_bayar` konkuren untuk `id_kunjungan` sama sama-sama lolos cek → transaksi ganda, omzet/shift ganda,
**baris komisi ledger ganda**. Alur reopen/split-billing (FLOW-D) menjadikan billing berulang pada 1 kunjungan
jalur first-class, memperlebar window.
Fix (REVISI setelah klarifikasi domain 2026-07-10 — **split/partial billing NYATA**, jadi unique pada
`id_kunjungan` SALAH karena mematahkan split yang sah):
1. PRIMER: `SELECT ... FOR UPDATE` pada baris `kunjungan` di awal `proses_bayar` + re-check di bawah lock
   → serialisasi submit konkuren tanpa melarang split.
2. BACKSTOP DB: kolom **idempotency key unik** (`transaksi_kasir.idempotency_key`) diisi per-submit dari klien
   → UNIQUE menolak SUBMIT IDENTIK yang diulang (double-click/retry/race), sambil membiarkan split (item/key beda).
Yang salah = "submit pembayaran yang SAMA diproses dua kali", bukan ">1 BAYAR per kunjungan".

**STATUS: SELESAI (2026-07-10).** Terpasang:
- Migrasi `20260710_2100` (chain dari `20260707_0400`): kolom `transaksi_kasir.idempotency_key VARCHAR(64) NULL`
  + UNIQUE index `uq_transaksi_kasir_idempotency_key` (NULL boleh duplikat). Downgrade↔upgrade round-trip OK.
- Model: `TransaksiKasir.idempotency_key`.
- `proses_bayar`: `kunjungan_repo.get_by_id_for_update` (`SELECT ... FOR UPDATE`) di awal → serialisasi submit
  konkuren; set `idempotency_key` dari token form; `except IntegrityError` → HTTP 409 ramah (bukan 500, tanpa
  transaksi/komisi ganda).
- Web: token per-render (`secrets.token_urlsafe`) di GET `/web/kasir/tagihan/{id}`, hidden input di KEDUA form
  Bayar; POST meneruskannya ke `BayarRequest.idempotency_key`. Split billing = render baru = token baru.
- Backup DB pra-migrasi: `backups/backup_20260710_211257.zip`.
Gerbang: `tests/integration/test_repro_P0_2_double_payment.py` (2 passed — key sama ditolak; NULL & key beda boleh).
Full suite 85 passed / 31 skipped / 0 fail; app import OK.
**Verifikasi jalur 409 (terkontrol, end-to-end, 2026-07-10):** sentinel `idempotency_key` di-commit lalu
`proses_bayar` dipanggil dgn key sama pada kunjungan billable → **ditolak 409** ("sudah diproses"), **0** transaksi
baru persisted, sentinel dibersihkan (skrip verify di scratchpad, exit 0). Jadi lock + key + `IntegrityError→409`
terbukti jalan, bukan cuma review kode. **Batas coverage tersisa:** happy-path `proses_bayar` tak punya test
otomatis di suite (commit internal → tak non-destruktif). Smoke manual opsional: double-click "Bayar" → 1 transaksi
+ pesan "sudah diproses" di klik kedua; split-bill (render ulang) → tetap boleh.

*Status: TERKONFIRMASI REPRO LANGSUNG DI DB (2026-07-10).* Bukan lagi "pending repro". Test repro
non-destruktif (rollback) ada di:
- `tests/integration/test_repro_P0_1_void_stock_inflation.py` — hasil: stok `10 -> 13.0`
  (`UPDATE master_produk SET stok_terkini=13.0`) untuk item yang tak pernah dispensed. Test kontras
  (item sudah dispensed, `7 -> 10`) LULUS → melokalisasi defect tepat pada absennya gate "sudah dispensed?".
  Jejak run yang sama juga memunculkan lot `batch_no='VOID-RETURN', tgl_ed=NULL, qty_sisa=3` → **P1-2 (H2)
  ikut terkonfirmasi di jalur yang sama**.
- `tests/integration/test_repro_P0_2_double_payment.py` — hasil: dua `INSERT ... status='BAYAR', id_kunjungan=1`
  lolos flush tanpa IntegrityError → tak ada unique constraint.

Keduanya pakai `@pytest.mark.xfail(strict=True)`: XFAIL selama bug ada, XPASS→FAIL saat fix dipasang
(jadi regression guard). Jalankan: `.venv/bin/pytest tests/integration/test_repro_P0_*.py -rxX -v`
(tambah `--runxfail` untuk lihat detail assertion).

---

## 🟠 P1 — Tinggi (korektnitas / keandalan / keamanan)

**P1-1. Pembayaran dan potong-stok bukan satu unit atomik.** Revenue + komisi + aktivasi membership commit di
`KasirService.proses_bayar`; deplesi stok/lot commit terpisah di `ApotekService.serahkan_obat`. Kalau pasien bayar
tapi tak ambil obat, revenue+komisi tercatat sedangkan stok tak pernah berkurang → COGS/inventory divergen permanen.
`serahkan_obat` juga **mengabaikan `shortfall`** dari `consume_fefo` (`apotek_service.py:161-167`) dan
`update_stok_produk` mengizinkan negatif (`apotek_repo.py:119-134`), jadi `stok_terkini` vs `Σ qty_sisa` bisa
diam-diam beda saat lot kurang. (Stok negatif memang kebijakan sengaja — `apotek_service.py:5-8` — tapi divergensi
senyap cache vs lot tidak.)

**KLARIFIKASI + SAFEGUARD (2026-07-10, dr. Hansen):** Model potong-stok-saat-serah adalah **desain yang benar**
untuk apotek (stok turun saat obat keluar fisik / di-keep untuk pasien). Yang tersisa = **rekonsiliasi**: jangan
ada kunjungan tersangkut di status antri. Diverifikasi bahwa `tutup_kasir` **dulu tak punya** guard antrian sama
sekali. Ditambahkan **HARD BLOCK**: `tutup_kasir` menolak (400) kalau masih ada kunjungan hari ini di status
non-terminal (semua kecuali COMPLETED/BATAL) — helper `_pending_antrian_hari_ini` (`kasir_closing_service.py`).
Kasir harus menyelesaikan (bayar/serah) atau FO ubah status yang tersangkut dulu. Gerbang:
`tests/integration/test_tutup_kasir_block_antri.py` (3 passed). Cakupan: klinik-wide, per hari (`tgl_kunjungan`=hari ini).
**Peringatan proaktif (SELESAI):** halaman preview Tutup Kasir (`GET /web/kasir/tutup` + `kasir_tutup.html`) kini
menampilkan banner kuning berisi daftar pasien yang masih antri (per status, label ramah) + tombol "Tutup Kasir"
**disabled** saat ada antri — defense-in-depth di atas hard block server. Terverifikasi via render (banner muncul saat
ada antri, hilang saat bersih; tombol disabled/enabled sesuai). Escape hatch: `kunjungan_service.ubah_status`
(`:309`, allowlist transisi mis. `ANTRI_OBAT→{COMPLETED,BATAL}`) ada untuk kasus pasien tersangkut.
**P1-2. Void mengembalikan stok ke lot fabrikasi → provenance ED hilang.** *(TERKONFIRMASI di jejak repro P0-1,
2026-07-10; **SUDAH DIPERBAIKI** lewat fix penuh lot-provenance — lihat STATUS di P0-1: kini restore ke lot ASLI
via `kunjungan_lot_terpakai`.)* `_reverse_stok_per_item:1001-1010`:
kalau operator tak pilih batch (jalur UI default per `test_void_return_lot.py::test_void_fallback_lot_retur_baru`),
dibuat lot `batch_no="VOID-RETURN", tgl_ed=None`. Karena FEFO menaruh `tgl_ed IS NULL` **paling belakang**
(`inventory_lot_service.py:37-39`), barang retur yang sebenarnya punya ED nyata terparkir di belakang dan bisa
tak pernah terpilih — lubang integritas kadaluarsa/FEFO.

**P1-3. Bypass rate-limit login via spoof `X-Forwarded-For`.** `rate_limit.py:39-45` mempercayai nilai XFF pertama
tanpa syarat. Kalau app terekspos tanpa proxy tepercaya yang meng-overwrite XFF, penyerang yang merotasi header
dapat bucket baru tiap request → proteksi brute-force runtuh. Audit ASVS menilai anti-brute-force ✅ dan melewatkan ini.
Fix: hormati XFF hanya dari IP proxy dikenal; selain itu pakai `request.client.host`.

**P1-4. XSS tersimpan via `json.dumps | safe` di blok `<script>` (BARU — tak tertangkap ASVS §5.2.x).**
`retur_form.html:53,59`, `opname_form.html:159`, `pemesanan_form.html:155`. `json.dumps` Python **tidak** meng-escape
`<`/`/`, lalu nilai dilewatkan `| safe`. Nilai master-data berisi `</script>...` keluar dari blok JSON; lebih parah,
`retur_form.html:59` merangkai `l.label` langsung ke `innerHTML` tanpa escape (DOM XSS). XSS-tersimpan terautentikasi
(role penulis master-data). Fix: `json.dumps(..., ...).replace('<','\\u003c')` (atau `|tojson`) + escape saat rangkai innerHTML.

**STATUS: SELESAI (2026-07-10).** (A) Helper `script_json` (`_shared.py`) escape `<`/`>`/`&` (+ U+2028/2029) →
dipakai ganti `json.dumps` di 3 route (`opname`, `retur`, `pengadaan`), template tetap `| safe` tapi string sudah aman.
(B) DOM XSS: tambah `esc()` di JS `opname_form.html` & `retur_form.html`, membungkus `p.kode/p.nama`/`l.label`
sebelum masuk `innerHTML`. Gerbang: `tests/unit/test_script_json.py` (4, termasuk bukti pola `<script>` tak bisa
breakout). Batas: sisi JS `esc()` diverifikasi review (tak ada engine JS di suite).

**P1-5. CSV formula injection di export.** `core/csv_writer.py` (`_to_csv_safe` l.15-32) pakai `QUOTE_ALL` (escape
delimiter) tapi tak menetralkan awalan `= + - @ \t \r`. Field teks-bebas klinis (`keluhan_utama`, `anamnesa`,
`nama_pasien`) mengalir ke paket CSV Owner/Finance (`export_service.py`, `finance_export_batch.py`); nilai seperti
`=cmd|'/C calc'!A1` dieksekusi saat dibuka di Excel/Sheets. Fix: prefix `'` untuk nilai berawalan karakter tsb.

**STATUS: SELESAI (2026-07-10).** `csv_writer._to_csv_safe` kini prefix `'` untuk **teks** yang diawali `= + - @`
(atau tab/CR) — hanya di cabang `str`, jadi angka (Decimal/int/float negatif) tetap utuh. Semua export CSV lewat
`dict_list_to_csv_bytes` (export_service, finance_export_batch, reports, export routes) → satu titik perbaikan.
Gerbang: `tests/unit/test_csv_writer.py` (4: rumus dinetralkan, teks normal utuh, angka negatif utuh, output CSV aman).

---

## 🟡 P2 — Sedang (hardening / maintainability)

- **P2-1. Math komisi pakai `float`.** `master_produk_service.py:43-101`, `master_treatment_service.py:41-113`,
  disimpan ke `komisi_nominal DECIMAL(12,2)` (`komisi_service.py:83-132`). Kolom DB membulatkan saat store, tapi
  layer akuntansi seharusnya `Decimal` seperti `faktur_calc.py` yang sudah benar. (Basis komisi = harga master,
  bukan harga tertagih/diskon — terdokumentasi, tapi berarti komisi dibayar atas revenue yang diskon/kuota bisa kurangi.)
- **P2-2. Kuantitas disimpan `Float`, diakumulasi read-modify-write.** `stok_lot.qty_sisa/qty_masuk`,
  `produk.stok_terkini`, `inventory_stok.*`, `transaksi_detail_produk.qty`. Ditambal `_EPS=1e-6`
  (`inventory_lot_service.py:80-84`), tapi logika `<= _EPS → HABIS` bisa salah-klasifikasi lot / sisakan dust.
  Item hitungan bulat → `Integer`; item pecahan (ml) → `DECIMAL`.
- **P2-3. Tabel/kolom line-item Finance dibaca tapi tak pernah ditulis.** `transaksi_detail_tindakan` tak pernah
  di-instansiasi; `transaksi_detail_produk.diskon_item`/`hpp_satuan` tak pernah di-assign di `proses_bayar` — padahal
  `export_service.py:534-605` menyeleksinya untuk margin/COGS. Rekonsiliasi margin per-baris di jembatan Finance
  mustahil dengan data sekarang. Revenue tindakan hanya ada sebagai string `rincian_tagihan` (`kasir_service.py:562-567`).
- **P2-4. Finance API router sepenuhnya tanpa auth** (`api/v1/finance.py`, di-mount mentah `main.py:116`, CSRF-exempt).
  Aman HANYA karena semua endpoint data `501`. **Sudah diflag P1-5 audit 2026-06-29 + V13.2.1 ASVS — masih terbuka.**
  WAJIB pasang `Depends(role_required(...))` di PR yang sama saat modul diimplementasi.
- **P2-5. Rollback session bersama di helper membership.** `membership_service.py:475-477`
  (`revert_active_to_pending`) memanggil `self.db.rollback()` di tengah `void_transaksi` (dipanggil
  `kasir_service.py:1188`). Sama kelasnya dengan **P1-2 audit 2026-06-29 — masih terbuka.** Fix: `begin_nested()`/savepoint.
- **P2-6. Tenant-scoping belum ada.** Belum ada kolom/filter `klinik_id`. Aman selama 1-klinik, tapi runtuh saat
  arsitektur multi-klinik/multi-tenant mendarat (sudah dicatat sebagai risiko naik-prioritas di catatan tindak lanjut
  ASVS). Siapkan scope per-klinik SEBELUM data membesar.

---

## 🟢 P3 — Rendah (kebersihan / keputusan eksplisit)

- **Baca PHI hanya di-gate login, tanpa batas role** (`web/routes/pasien.py:161,349`): tiap staf terautentikasi
  (termasuk Kasir/Apoteker) bisa buka rekam penuh pasien mana pun. Konsisten dengan model 1-klinik, tapi ini
  keputusan PHI yang layak dicatat eksplisit (kompensasi: akses-baca sudah teraudit sejak 2026-07-07).
- **Apoteker bisa approve retur pembelian** via `require_purchasing_view_role` (`retur.py:161`) sementara approve/cancel
  PO + approve opname pakai gate lebih ketat — granularitas privilege tak konsisten (inventory saja).
- **Tak ada paksa ganti password saat login pertama**; min password user baru = 8, tanpa complexity/breach check
  (selaras keputusan "adopsi bertahap").
- **~255 blok `except Exception`** — banyak sengaja "graceful degradation", tapi pola ini bisa menutupi kegagalan nyata.
- **Kebersihan file / higiene data:** `.env` hidup (JWT secret nyata, password DB default lemah `Klinik123!`) dan
  **backup SQL/ZIP berisi PHI** berada di dalam folder proyek. Aman lokal, tapi kalau folder disinkron/dibagikan → PHI bocor.
  Artefak zip nyasar di root (`ziFKtzj6`, `backups/zi59spHF`), monolit legacy 83 KB (`Current python code main_api.txt`),
  `sehati_clinic_template.zip` 0-byte, dua `.docx` manual nyaris identik.
- **`_create_pending_membership_history_if_needed`** (`pasien_service.py:71`) tak pernah dipanggil — `DEAD_CODE_SWEEP`
  penulis sendiri menandainya kemungkinan fitur tak ter-wire (history PENDING saat daftar mungkin tak tersambung), bukan dead code. Perlu diputuskan.

---

## Yang sudah BENAR (lulus audit)

- **`faktur_calc.py`**: murni `Decimal`, diskon seragam **sebelum** PPN, harga/unit `ROUND_HALF_UP` ke rupiah utuh,
  `extra_diskon = S·(1+t) − Y` merekonsiliasi header ke total tertagih persis. Kasus surcharge (`d<0`) tertangani.
- **Urutan FEFO** (`inventory_lot_service.py:37-44`): `tgl_ed NULLS LAST, tgl_ed ASC, tgl_masuk ASC, id_lot ASC` — benar.
- **VOID di-exclude dari agregasi uang** (shift rekap, closing preview, omzet filter `status_transaksi='BAYAR'`) —
  P0-1 audit 2026-06-29 (DEC-079) terkonfirmasi sudah tertutup.
- **Reversal komisi saat void** (`komisi_service.py:147-163`) + anti-double-count tindakan (`:71-78`).
- **Potong BHP tindakan** pakai `SELECT ... FOR UPDATE` (`inventory_repo.py:25-37`).
- **Nihil SQL injection**: satu-satunya `text()` (`pasien_repo.py:105`) pakai bound param `:prefix`. SQL tak di-log di produksi
  (`session.py:20`). Engine/pool sehat (`pool_pre_ping`, `pool_recycle=280`).
- **Auth**: role dari DB tiap request, cookie `HttpOnly`/`SameSite=lax`/`Secure` config-driven, logout terpusat via
  `is_logged_in`, guard boot produksi (config.py:104-129), tak ada IDOR di model 1-klinik.
- **Dependensi mutakhir**: `python-jose 3.5.0` (menutup CVE lama), fastapi/sqlalchemy/pydantic terbaru.

## Rekomendasi urutan tindak lanjut

1. **P0-1 + P0-2** (overstate stok void & double-payment) — bug uang/stok hidup. Sekalian lengkapi test jalur uang
   (P1-4 lama masih relevan): tulis repro C1/C2.
2. **P1-1 + P2-3** — ikat potong-stok ke transaksi bayar, atau persist snapshot line-item + COGS yang modul Finance harapkan.
3. **P1-4 + P1-5** (XSS `|safe` & CSV injection) — dua vektor yang audit ASVS lewatkan.
4. **P1-3** (XFF) sebelum ekspos non-LAN.
5. **P2-6** (tenant-scoping `klinik_id`) SEBELUM migrasi multi-klinik, bukan sesudah.
6. Tutup utang lama: **P2-4** (guard Finance) & **P2-5** (rollback membership).
7. **P3** kebersihan kapan saja.
