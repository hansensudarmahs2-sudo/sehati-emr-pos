# Bayar Dulu — Tahap 1: Status Ringkasan & Antrian Membaca Isi — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Status kunjungan dihitung SATU fungsi dari isinya, antrian perawat/apotek/kasir membaca isi kunjungan, tindakan tahu transaksi pembayarnya, dan halaman tagihan basi ditahan — tanpa mengubah alur biasa (tindakan → kasir → obat). Menutup audit T4-4.

**Architecture:** Kolom `kunjungan_tindakan.id_transaksi` (+ backfill) membuat "belum ditagih" = `id_transaksi IS NULL`, menggantikan perbandingan jam. Modul baru `app/services/_status_kunjungan.py` menghitung status dari isi; setiap penulis status otomatis memanggilnya. Repositori antrian menyaring dengan EXISTS atas item, bukan label status.

**Tech Stack:** FastAPI · SQLAlchemy 2.0 · MySQL 8 (REPEATABLE-READ) · Alembic · Jinja2 · pytest (sesi di-rollback, `commit = flush`).

**Spec:** `Project_Memory/DESAIN_BAYAR_DULU_BERCABANG.md` (disetujui dr. Hansen 2026-10-15) — §3.1, §3.2, §3.3, tabel tahap 1 di §4.

## Global Constraints

- Uji di UI desktop dulu, baru deploy; deploy hanya di luar 12.00–22.00 WIB (CLAUDE.md §1).
- Migrasi HANYA menambah; perubahan skema sudah disetujui (§3.1 spec).
- Tahap 1 TIDAK menagih tindakan yang belum SELESAI (itu tahap 2). "Bisa ditagih" di tahap 1 = `SELESAI`.
- Uang tidak berubah: `_refund_bukuan.terhitung_omzet()` tetap satu-satunya saringan omzet.
- Pola baca-segar: operasi tulis dari route memanggil `mulai_baca_segar` sebelum kunci (`app/services/_baca_segar.py`).
- Semua test baru di `sehati_clinic/tests/integration/test_bayar_dulu_tahap1.py`, memakai fixture `db` & helper `_siapkan/_resep/_bayar/_tindakan_selesai/_trx_terakhir` dari `tests/integration/test_audit_tahap2.py`; setiap test penutup cacat harus GAGAL di kode lama (tulis dulu, jalankan, baru perbaiki).
- Jalankan dari `sehati_clinic/` di WSL: `source .venv/bin/activate && eval "$(grep -E "^TEST_(USERNAME|PASSWORD)=" .env | sed "s/^/export /")"`.
- Setiap task: commit & push ke `laptop/audit-alur-uang-putaran-21` lalu `git push origin HEAD:main && git branch -f main origin/main`. Pesan commit Bahasa Indonesia, jujur, dengan baris `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

### Klarifikasi spec §3.2 (dari pemetaan kode 2026-10-21 — konfirmasi dr. Hansen sebelum Task 3)

Konsultasi adalah item TINDAKAN biasa ("Specialist Consultation"). Kunjungan yang sudah SOAP tanpa item apa pun sekarang tetap ke kasir dan ditutup dengan tagihan Rp 0. Agar "alur biasa sama persis":
- **(K) ditambah:** sudah ada SOAP FINAL dan belum ada transaksi BAYAR sama sekali → masih menunggu kasir.
- **Tidak disentuh:** kunjungan tanpa SOAP DAN tanpa item apa pun (mis. kunjungan lanjutan series yang baru dibuat FO/booking, sebelum "Pakai Sesi") → status dibiarkan.

## Review Focus

1. Kunjungan jalur obat tertunda (`tgl_janji_kirim` terisi, sisa obat DIBAYAR) tetap COMPLETED — tidak ditarik kembali ke ANTRI_OBAT oleh fungsi ringkasan. → test di Task 3.
2. Kunjungan lanjutan series (ANTRI_TREATMENT, tanpa SOAP, tanpa item) tidak berubah jadi COMPLETED sebelum sesi dipakai. → test di Task 3.
3. Upsell PRODUK pada kunjungan ANTRI_BAYAR tidak lagi meninggalkan ON_TREATMENT tanpa tindakan aktif. → test di Task 4.
4. Pasien dengan obat lunas + tindakan PENDING tampil di layar apotek DAN perawat, dan apotek bisa menyerahkan obatnya walau label ON_TREATMENT. → test di Task 5.
5. Halaman tagihan basi: dokter menambah resep sesudah halaman dibuka → Bayar ditahan; API v1 tanpa sidik tetap jalan. → test di Task 6.

---

### Task 1: Migrasi `20261021_0100` + model

**Files:**
- Create: `sehati_clinic/migrations/versions/20261021_0100_bayar_dulu_tahap1.py`
- Modify: `sehati_clinic/app/db/models/kunjungan.py` (`KunjunganTindakan`), `sehati_clinic/app/db/models/_enums.py` (`StatusTindakanEnum`), model `PasienRencanaTreatment` (enum sumber), `sehati_clinic/app/db/models/transaksi.py` (`TransaksiRefund`)
- Test: `sehati_clinic/tests/integration/test_bayar_dulu_tahap1.py`

**Interfaces:**
- Produces: kolom `KunjunganTindakan.id_transaksi: Mapped[Optional[int]]` (FK `transaksi_kasir.id_transaksi`, indeks `ix_kt_transaksi`); `StatusTindakanEnum.BATAL = "BATAL"`; `sumber_rencana` menerima `"PRABAYAR"`; `TransaksiRefund.id_kunjungan_tindakan: Mapped[Optional[int]]` (FK).
- Produces: fungsi modul migrasi `isi_id_transaksi_tindakan(bind) -> dict` mengembalikan `{"dari_snapshot": int, "dari_cutoff": int, "tetap_null_di_kunjungan_lunas": int}`.

- [ ] **Step 1: Tulis test backfill** (impor modul migrasi lewat `importlib.util.spec_from_file_location`, pola `test_migrasi_mengisi_uang_keluar_void_lampau_lama`)
  - `test_backfill_dari_snapshot`: tindakan SELESAI ber-`transaksi_detail_tindakan` di trx BAYAR, `id_transaksi` di-set NULL lewat SQL → `isi_id_transaksi_tindakan(db.connection())` → `id_transaksi == t.id_transaksi`, `hasil["dari_snapshot"] >= 1`.
  - `test_backfill_dari_cutoff_pra_f3`: tindakan SELESAI tanpa snapshot, trx BAYAR dengan `waktu_bayar >= waktu_selesai` → terisi trx itu.
  - `test_backfill_aman_dijalankan_ulang`: panggilan kedua mengubah 0 baris.
- [ ] **Step 2: Jalankan → gagal** (`pytest tests/integration/test_bayar_dulu_tahap1.py -k backfill -q` → FAIL: berkas migrasi/kolom tidak ada).
- [ ] **Step 3: Tulis migrasi** — `down_revision = "20261016_0200"`; `ALTER TABLE ... MODIFY status_tindakan ENUM('PENDING','PROSES','SELESAI','BATAL')`; `sumber_rencana` ENUM + `'PRABAYAR'`; dua kolom FK baru; `upgrade()` memanggil `isi_id_transaksi_tindakan` lalu mencetak hitungan dan **raise** bila `tetap_null_di_kunjungan_lunas > 0` (pesan menyebut id). Urutan backfill: (1) snapshot `transaksi_detail_tindakan` di trx BAYAR; (2) SELESAI tanpa snapshot → trx BAYAR paling awal `waktu_bayar >= waktu_selesai` di kunjungan sama. `downgrade()` membalik semuanya (enum dikembalikan hanya bila tak ada baris BATAL/PRABAYAR — kalau ada, raise).
- [ ] **Step 4: Model** — tambahkan kolom & nilai enum dengan komentar "kenapa" (sejajar `kunjungan_resep.id_transaksi`, T2-2).
- [ ] **Step 5: Jalankan** `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` → tiga-tiganya OK, hitungan tercetak, `tetap_null... = 0` di dev. Test backfill PASS.
- [ ] **Step 6: Commit** — `Bayar dulu T1-1: kunjungan_tindakan.id_transaksi + BATAL + PRABAYAR (migrasi 20261021_0100)`.

### Task 2: Bayar menandai tindakan; susulan tindakan = tanpa `id_transaksi`

**Files:**
- Modify: `sehati_clinic/app/repositories/kasir_repo.py` (`get_tindakan_selesai_for_billing`, baru `mark_tindakan_dibayar`), `sehati_clinic/app/services/kasir_service.py` (`get_tagihan` blok "Detect new items", `proses_bayar` langkah 5)
- Test: `tests/integration/test_bayar_dulu_tahap1.py`

**Interfaces:**
- Consumes: kolom Task 1.
- Produces: `KasirRepository.mark_tindakan_dibayar(id_kunjungan: int, id_transaksi: int, ids: list[int]) -> int` (UPDATE `id_transaksi` hanya untuk `ids`, hanya yang `id_transaksi IS NULL`).

- [ ] **Step 1: Tulis test**
  - `test_bayar_menandai_tindakan_yang_ditagih`: tindakan SELESAI → `_bayar` → `kt.id_transaksi == _trx_terakhir(db,k).id_transaksi`.
  - `test_tindakan_selesai_di_detik_bayar_tetap_tertagih_susulan`: bayar T1, lalu tindakan SELESAI dengan `waktu_selesai = t1.waktu_bayar` (detik sama) → `get_tagihan` menagihnya (dulu hilang karena `>` cutoff).
  - `test_tindakan_lunas_tidak_ditagih_ulang`: sesudah T1, tagihan tanpa item baru → `sudah_lunas` True.
- [ ] **Step 2: Jalankan → test 1 & 2 GAGAL di kode lama.**
- [ ] **Step 3: Implementasi** — tindakan "baru" = SELESAI **dan** `id_transaksi IS NULL` (hapus saringan `waktu_selesai > cutoff` untuk tindakan; komentar: alasan sama dengan resep T4-1). Di `proses_bayar` langkah 5 panggil `mark_tindakan_dibayar(..., ids=[t.id_kunjungan_tindakan for t in tagihan.rincian_tindakan])`. Mode view-only (sudah lunas) tetap menampilkan semua tindakan SELESAI.
- [ ] **Step 4: Test PASS; jalankan juga `test_audit_tahap2.py test_audit_tahap4.py test_nota_snapshot.py` → semua PASS.**
- [ ] **Step 5: Commit** — `Bayar dulu T1-2: tindakan tahu transaksi pembayarnya; susulan tanpa perbandingan jam`.

### Task 3: Modul `_status_kunjungan`

**Files:**
- Create: `sehati_clinic/app/services/_status_kunjungan.py`
- Test: `tests/integration/test_bayar_dulu_tahap1.py`

**Interfaces:**
- Produces:
  - `ringkasan(db, id_kunjungan: int) -> dict` → `{"T_proses": bool, "T_pending": bool, "K": bool, "O": bool, "ada_isi": bool, "ada_soap": bool}`.
  - `status_seharusnya(db, id_kunjungan: int) -> str | None` → label menurut spec §3.2 + klarifikasi di atas; `None` = jangan disentuh (BATAL, atau tanpa SOAP & tanpa isi, atau masih `ANTRI_KONSULTASI`/`KONSULTASI` tanpa SOAP).
  - `hitung_ulang_status(db, id_kunjungan: int) -> str` → tulis label lewat `KunjunganRepository.update_status` bila berbeda & tidak `None`; kembalikan status akhir. Tidak commit.
- Definisi: (T) tindakan PENDING/PROSES; (K) tindakan SELESAI tanpa `id_transaksi` **atau** resep/racikan PENDING **atau** (ada SOAP FINAL dan belum ada transaksi BAYAR); (O) resep/racikan DIBAYAR **dan** `tgl_janji_kirim IS NULL`. Prioritas label: `ON_TREATMENT` › `ANTRI_TREATMENT` › `ANTRI_BAYAR` › `ANTRI_OBAT` › `COMPLETED`.

- [ ] **Step 1: Tulis test tabel** — `@pytest.mark.parametrize` atas keadaan isi → label yang diharapkan: tindakan PROSES → ON_TREATMENT; PENDING → ANTRI_TREATMENT; SELESAI belum dibayar → ANTRI_BAYAR; resep DIBAYAR belum serah → ANTRI_OBAT; semua lunas & diserahkan → COMPLETED; SOAP FINAL tanpa item & tanpa transaksi → ANTRI_BAYAR; obat DIBAYAR + `tgl_janji_kirim` → COMPLETED (Review Focus 1); tanpa SOAP & tanpa isi berstatus ANTRI_TREATMENT → `None`, status tak berubah (Review Focus 2); BATAL → `None`.
- [ ] **Step 2: Jalankan → FAIL (modul tidak ada).**
- [ ] **Step 3: Implementasi** — kueri EXISTS per kondisi; semua pembacaan biasa (pemanggil sudah memegang kunci kunjungan bila perlu).
- [ ] **Step 4: PASS.**
- [ ] **Step 5: Commit** — `Bayar dulu T1-3: satu fungsi menghitung status kunjungan dari isinya`.

### Task 4: Semua penulis status otomatis memakai `hitung_ulang_status`

**Files (penulis yang diganti — baris per 2026-10-21):**
- `app/services/pemeriksaan_service.py:351,356` (simpan SOAP; tetap tolak COMPLETED/BATAL di :105)
- `app/services/treatment_service.py:204` (mulai) dan `:334` (selesai — dulu ANTRI_BAYAR tanpa syarat)
- `app/services/upsell_service.py:248`
- `app/services/series_service.py:276`
- `app/services/kasir_service.py:948` (bayar — `_obat_lama_menunggu`/T2-1 kini tercakup (O); hapus duplikasinya) dan `:2480` (cascade void)
- `app/services/apotek_service.py:413` (obat tertunda) dan `:620` (serah)
- Tidak diubah: penulis saat MEMBUAT kunjungan (`kunjungan_service.py:678`, `membership_service.py:925`, `retur_pasien_service.py:261`, `web/routes/pasien.py:650`, `web/routes/pendaftaran.py:234`, booking) dan `ubah_status` manual (Task 7).
- Test: `tests/integration/test_bayar_dulu_tahap1.py`

**Interfaces:**
- Consumes: `hitung_ulang_status(db, id_kunjungan) -> str` (Task 3).

- [ ] **Step 1: Tulis test**
  - `test_t44_bayar_saat_tindakan_pending_tetap_di_jalur_perawat`: tindakan A SELESAI + B PENDING → `_bayar` → status `ANTRI_TREATMENT` (dulu COMPLETED); `end_tindakan(B)` → `ANTRI_BAYAR`; bayar susulan → COMPLETED. **GAGAL di kode lama.**
  - `test_selesai_tindakan_sesudah_lunas_dan_obat_menunggu`: obat DIBAYAR belum serah + tindakan susulan selesai & dibayar → ANTRI_OBAT.
  - `test_upsell_produk_tidak_meninggalkan_on_treatment` (Review Focus 3): kunjungan ANTRI_BAYAR + upsell PRODUK → `ANTRI_BAYAR`. **GAGAL di kode lama.**
  - `test_tidak_ada_penulis_status_liar`: membaca sumber (`inspect`/grep) — di `app/services` hanya `_status_kunjungan.py`, `kunjungan_service.ubah_status`/pembuat kunjungan, dan penulis BATAL yang boleh memanggil `update_status(` atau menulis `status_antrian =`. Daftar izinnya eksplisit di test.
- [ ] **Step 2: Jalankan → gagal sesuai harapan.**
- [ ] **Step 3: Ganti setiap penulis** dengan `hitung_ulang_status(self.db, id_kunjungan)`; pertahankan audit `STATUS_UPDATE` yang sudah ada (data_lama → hasil fungsi).
- [ ] **Step 4: PASS + seluruh suite** (`pytest tests/integration/ tests/unit/ -q`): hanya 5 kegagalan lama yang diketahui (3 data seed, 2 jam/data).
- [ ] **Step 5: Commit** — `Bayar dulu T1-4: semua penulis status lewat satu fungsi (T4-4 tertutup)`.

### Task 5: Antrian membaca isi

**Files:**
- Modify: `app/repositories/treatment_repo.py:130` `list_antrian_ruang_tindakan`, `app/repositories/apotek_repo.py:35` `list_antrian_obat`, `app/repositories/kasir_repo.py:42` `list_antrian_bayar`, pagar status di `app/services/apotek_service.serahkan_obat` (dulu wajib `ANTRI_OBAT`)
- Test: `tests/integration/test_bayar_dulu_tahap1.py`

**Interfaces:**
- Consumes: Task 3 (definisi T/K/O — pakai ulang ekspresinya, jangan menulis ulang kueri; ekspos `kondisi_T()`, `kondisi_K()`, `kondisi_O()` dari `_status_kunjungan` sebagai ekspresi EXISTS berkorelasi pada `Kunjungan.id_kunjungan`).

- [ ] **Step 1: Tulis test**
  - `test_pasien_tampil_di_apotek_dan_perawat_bersamaan` (Review Focus 4): resep DIBAYAR + tindakan PENDING hari ini → ada di `list_antrian_obat` DAN `list_antrian_ruang_tindakan`. **GAGAL di kode lama.**
  - `test_apotek_bisa_serah_saat_label_on_treatment`: kunjungan itu → `serahkan_obat` berhasil; status sesudahnya `ANTRI_TREATMENT`.
  - `test_antrian_kasir_dari_item_belum_ditagih`: tindakan SELESAI tanpa transaksi → ada di `list_antrian_bayar`; sesudah bayar → hilang.
  - `test_antrian_tetap_hanya_hari_ini_dan_tanpa_batal`.
- [ ] **Step 2: Jalankan → gagal.**
- [ ] **Step 3: Implementasi** — saring `tgl_kunjungan` hari ini, `status_antrian != 'BATAL'`, dan kondisi isi. Pagar serah: ada resep/racikan DIBAYAR (jalur `tgl_janji_kirim` tetap seperti sekarang).
- [ ] **Step 4: PASS + suite + `python -m scripts.cek_smoke_web` → 0 bermasalah.**
- [ ] **Step 5: Commit** — `Bayar dulu T1-5: antrian perawat/apotek/kasir membaca isi kunjungan`.

### Task 6: Sidik halaman tagihan

**Files:**
- Modify: `app/schemas/kasir.py` (`BayarRequest`), `app/services/kasir_service.py` (`proses_bayar`, fungsi baru), `app/web/routes/kasir.py` (GET tagihan & POST bayar), `app/web/templates/kasir_tagihan.html` (dua form bayar, baris ~654 & ~681)
- Test: `tests/integration/test_bayar_dulu_tahap1.py`

**Interfaces:**
- Produces: `KasirService.sidik_tagihan(tagihan: TagihanResponse) -> str` — string deterministik dari id item yang DITAGIH, mis. `"T:12,T:15|R:40|C:7"` (urut naik per jenis). `BayarRequest.sidik: Optional[str] = None`.
- Pesan tolak (409): `"Tagihan berubah sejak halaman dibuka — ada item baru dari dokter/perawat. Halaman dimuat ulang; periksa lalu bayar lagi."`

- [ ] **Step 1: Tulis test**
  - `test_sidik_beda_pembayaran_ditahan` (Review Focus 5): ambil sidik → tambah resep → `proses_bayar(sidik=lama)` → HTTPException 409, tidak ada transaksi baru.
  - `test_sidik_sama_lolos`; `test_tanpa_sidik_api_tetap_jalan` (sidik None).
  - `test_halaman_tagihan_memuat_sidik`: render lewat TestClient dengan `app.dependency_overrides[get_db]` (pola `test_layar_void_lampau_meminta_penyetuju_dan_pin`) → `name="sidik"` ada di kedua form.
- [ ] **Step 2: Jalankan → gagal.**
- [ ] **Step 3: Implementasi** — bandingkan SESUDAH `mulai_baca_segar` + kunci + `get_tagihan` (data segar, T4-1); route meneruskan field form `sidik`; redirect error memakai `_q_err`.
- [ ] **Step 4: PASS.**
- [ ] **Step 5: Commit** — `Bayar dulu T1-6: halaman tagihan basi ditahan (sidik item)`.

### Task 7: Dropdown ubah status FO dipangkas

**Files:**
- Modify: `app/services/kunjungan_service.py:38-51` `_VALID_TRANSITIONS`
- Test: `tests/integration/test_bayar_dulu_tahap1.py`; sesuaikan test T2-4 di `tests/integration/test_audit_tahap2.py` yang memakai transisi maju.

**Interfaces:**
- Produces: `_VALID_TRANSITIONS = {"ANTRI_KONSULTASI": {"KONSULTASI", "BATAL"}, "KONSULTASI": {"BATAL"}, "ANTRI_TREATMENT": {"BATAL"}, "ON_TREATMENT": {"BATAL"}, "ANTRI_BAYAR": {"BATAL"}, "ANTRI_OBAT": {"BATAL"}, "COMPLETED": set(), "BATAL": set()}` (spec §3.2 jawaban dr. Hansen 2). Pagar BATAL T2-5 tidak berubah.

- [ ] **Step 1: Tulis test** — `test_fo_tidak_bisa_memajukan_status` (parametrize: KONSULTASI→ANTRI_BAYAR, ON_TREATMENT→COMPLETED, ANTRI_OBAT→COMPLETED → ditolak 400); `test_fo_tetap_bisa_batal_dan_mulai_konsultasi`. **GAGAL di kode lama.**
- [ ] **Step 2–4: Implementasi, PASS, suite.** Dropdown sudah diturunkan dari tabel ini (T2-4) — cek render halaman antrian FO lewat smoke.
- [ ] **Step 5: Commit** — `Bayar dulu T1-7: FO hanya bisa mulai konsultasi atau membatalkan (DEC-015 dihapus)`.

### Task 8: Pemeriksa `cek_status_kunjungan` + dokumentasi

**Files:**
- Create: `sehati_clinic/scripts/cek_status_kunjungan.py`
- Modify: `CLAUDE.md` (§4.1 baris baru "status kunjungan = ringkasan", §5 tabel pemeriksa, §8 migrasi), `Project_Memory/11_decisions_log.md` (DEC baru membalik DEC-050 & menghapus DEC-015), `Project_Memory/UJI_UI_AUDIT_2026-10-05.md` (U63–U67), `Project_Memory/DESAIN_BAYAR_DULU_BERCABANG.md` (status tahap 1), `Project_Memory/AUDIT_MENDALAM_2026-10-13.md` (T4-4 ✅).

**Interfaces:**
- Consumes: `status_seharusnya(db, id)` (Task 3).
- Perilaku: HANYA membaca; untuk semua kunjungan hari ini (bukan BATAL) bandingkan `status_antrian` dengan `status_seharusnya`; cetak selisih per baris; keluar kode 1 bila ada selisih. Opsi `--tanggal YYYY-MM-DD`.

- [ ] **Step 1: Uji dua arah** — jalankan di DB dev → 0 selisih; lalu di test (sesi rollback) set satu kunjungan ke label salah dan panggil fungsi inti pemeriksa (`periksa(db, tanggal) -> list`) → 1 selisih.
- [ ] **Step 2: Dokumentasi** — U63 bayar saat tindakan PENDING (tetap di perawat → susulan); U64 pasien tampil di apotek & perawat bersamaan, obat bisa diserahkan; U65 halaman tagihan basi ditahan; U66 dropdown FO hanya Konsultasi/Batal; U67 tutup kasir tetap menolak bila ada kunjungan menggantung.
- [ ] **Step 3: Pemeriksa §5 lengkap** — suite, smoke, `cek_finance_pack`, `jejak_uji_ui` (omzet semua pembaca sepakat), `cek_serah_tanpa_lot`, `cek_tunda_item`, `cek_tebus_resep`, `cek_status_kunjungan`.
- [ ] **Step 4: Commit** — `Bayar dulu T1-8: pemeriksa status kunjungan + dokumentasi tahap 1`.

---

## Catatan pengerjaan (2026-10-21) — keputusan & sisa

Disalin dari buku catatan pengerjaan subagent sebelum dihapus. Commit: fe62830..4142a3c.

### Keputusan (Ruling)

- Ruling 1: T3 juga mengekspos `kondisi_T()`, `kondisi_K()`, `kondisi_O()` — ekspresi EXISTS berkorelasi pada `Kunjungan.id_kunjungan` — dan `ringkasan` memakainya; T5 memakai ulang, tidak menulis kueri sendiri — spec §3.3 "antrian membaca isi" dengan definisi §3.2 yang SAMA — bila salah: T5 menulis ulang definisi, dua definisi (pola §4.1).
- Ruling 2: di `test_t44` tindakan B dimulai (`start_tindakan`) sebelum `end_tindakan` — `end_tindakan` hanya menerima PROSES — bila salah: test gagal karena prasyarat, bukan cacat.
- Ruling 3: T2 tidak mengubah `get_tindakan_selesai_for_billing` (tetap semua SELESAI, dipakai view-only); "baru" disaring di `get_tagihan` dengan `id_transaksi IS NULL` — rencana menulis "Modify" repo itu, cukup komentar — bila salah: tampilan lunas kehilangan tindakan.
- Ruling 4: test T5 memakai tindakan PROSES (label ON_TREATMENT); sesudah serah status TETAP ON_TREATMENT (tindakan masih berjalan) — spec §3.2 prioritas label — bila salah: hanya ekspektasi test.
- Ruling 5: implementer hanya commit lokal; controller push ke branch & main sesudah review task bersih — kebiasaan dr. Hansen "tiap selesai commit and push" tetap, tapi kode yang belum lolos review tidak sampai main — bila salah: main tertinggal satu task.
- Ruling 6: klausa SOAP pada (K) = "sudah ada SOAP FINAL dan BELUM ADA TRANSAKSI APA PUN (status apa pun)" — transaksi VOID berarti kunjungan sudah ditangani kasir; susulan sesudah void tetap tertangkap klausa item lain — spec §1 "alur biasa bekerja persis seperti sekarang" (void kini menutup kunjungan) — bila salah: kunjungan ber-void tanpa item baru tak kembali ke kasir (sama seperti sekarang).
- Ruling 7: status_seharusnya mengembalikan None (tidak disentuh) hanya bila TANPA SOAP FINAL, TANPA isi, DAN TANPA transaksi apa pun (status apa pun); `ringkasan` mendapat kunci `ada_transaksi` — kunjungan yang pernah ditangani kasir selalu dihitung (beli produk ber-void → COMPLETED, membership legacy lunas → COMPLETED) — penyempurnaan klarifikasi §3.2 searah Ruling 6; tujuan klarifikasi (kunjungan lanjutan series yang baru dibuat tak tersentuh) tetap — bila salah: kunjungan tanpa SOAP yang pernah ber-transaksi lalu diberi isi baru dihitung ulang (memang diinginkan).
- Ruling 8: use_session pada kunjungan ANTRI_KONSULTASI tanpa SOAP tetap berlabel ANTRI_KONSULTASI (aturan pra-SOAP §3.2); antrian perawat Task 5 membaca isi (tindakan PENDING) jadi tetap tampil — bila salah: label FO tertinggal sampai SOAP.
- Ruling 9: tunda_serah_obat juga menerima kunjungan yang memenuhi kondisi_O (sama dengan himpunan yang ditampilkan antrian apotek), bukan hanya ANTRI_OBAT/COMPLETED — spec §3.3 "satu pasien boleh tampil di dua meja": meja yang menampilkan pasien harus bisa menangani obatnya (serah DAN tunda) — bila salah: tunda bisa dipakai saat tindakan masih berjalan (tidak merusak; tgl_janji_kirim tetap dipasang).
- Ruling 10: antrian perawat = kondisi_T() ATAU label status_antrian == 'KONSULTASI' (hari ini, bukan BATAL) — daftar perawat satu-satunya pintu ke form upsell; spec §1 "alur biasa bekerja persis seperti sekarang" mengalahkan tabel §3.3 untuk kasus ini — bila salah: perawat melihat pasien yang sedang konsultasi tanpa tindakan (seperti sekarang).
- Ruling 11: pemeriksa cek_status_kunjungan tetap HANYA MEMBACA (konvensi §5); perbaikan label basi di mini PC diputuskan dr. Hansen saat deploy berdasarkan keluarannya — bila salah: satu langkah manual tambahan saat deploy.
- Ruling 12: C1 → tarik cabang "belum dibayar" tombol Batalkan (spec §3.6, disetujui 2026-10-15 + jawaban 3: dokter/perawat/admin) ke tahap 1: TreatmentService.batalkan_tindakan (PENDING & id_transaksi NULL → BATAL, alasan wajib, kuota & series dibereskan pola _bereskan_batal, audit, hitung_ulang_status) + tombol di layar perawat — lebih aman daripada mengembalikan jalan pintas FO; desain sudah disetujui — bila salah: tambahan UI kecil lebih awal dari jadwal.
- Ruling 13: I1 → lingkup tindakan void = tindakan ber-id_transaksi == trx (kolom tahap 1), bukan "semua tindakan kunjungan"; kuota hanya dikembalikan untuk tindakan dalam lingkup; tindakan PENDING yang tak ditagih tetap hidup (dibatalkan lewat Ruling 12) — bila salah: data lama tanpa id_transaksi memakai jalur lama (snapshot) sebagai cadangan.
- Ruling 14 (dibuat implementer, disahkan controller): aturan pembatalan series saat void memakai lingkup id_transaksi juga untuk kunjungan bertransaksi tunggal — void konsultasi tak boleh membatalkan series yang sesi 1-nya belum ditagih transaksi itu — Ruling 13 diterapkan konsisten — bila salah: series ikut batal saat void (perilaku lama).
- Ruling 15 (dibuat implementer, disahkan controller): pagar 409 "tindakan pra-F3 tanpa snapshot" pada void multi-transaksi dihapus; migrasi 20261021_0100 mengisi id_transaksi data lama lewat cutoff — bila salah: void kunjungan lama yang tak terisi memakai cadangan snapshot.

### Sisa masalah & catatan kecil yang ditunda

- Task 1: minor (deferred): model tak mendeklarasikan indeks ix_kt_transaksi / ix_refund_kt (sejalan preseden kunjungan_resep.id_transaksi)
- Task 1: minor (deferred): tidak ada test untuk jalur abort tetap_null_di_kunjungan_lunas>0 & upgrade/downgrade
- Task 1: minor (deferred): assert >=1 pada hitungan backfill; test bergantung helper test_audit_tahap2
- Task 2: minor (deferred): tidak ada test langsung split-billing kedua (tindakan T1 tetap milik T1)
- Task 2: minor (deferred): transaksi VOID terakhir masih membuat get_tagihan mode view-only (sudah tercatat temuan ringan tahap 4)
- Task 4: minor (deferred): proses_bayar pada kunjungan obat-tertunda (tgl_janji_kirim) + obat baru dibayar → COMPLETED (dulu ANTRI_OBAT); obat baru hanya tampil di daftar Obat Tertunda
- Task 4: minor (deferred → Task 5): tindakan upsell pra-SOAP yang selesai tak terlihat kasir sampai SOAP — antrian kasir Task 5 harus membaca kondisi_K
- Task 4: minor (deferred): pemindai penulis status hanya mengenali receiver bernama "kunjungan"; tak menangkap update(Kunjungan).values(...) / SQL mentah
- Task 4: minor (deferred): docstring _cascade_void_kunjungan & nama kunjungan_advanced/VOID_KUNJUNGAN_FORWARD basi (kini bisa mundur ke ANTRI_BAYAR)
- Task 4: minor (deferred): treatment_repo.count_tindakan_aktif kini tak terpakai
- Task 4: minor (deferred): STATUS_UPDATE proses_bayar kini hanya saat berubah (deviasi kecil brief, dilaporkan)
- Task 4: minor (deferred): cascade void kini menghitung ulang status apa pun selain BATAL (kunjungan lampau COMPLETED ber-item tak tertagih bisa jadi ANTRI_BAYAR)
- Task 5: minor (deferred): badge "ANTRI_OBAT" statis di halaman detail apotek
- Task 5: minor (deferred): _count_meja tak lagi menyaring JENIS_KUNJUNGAN_BUKAN_KLINIS (kini sama dengan daftar; retur dibuat COMPLETED, dampak kecil)
- Task 6: minor (deferred): test sidik hanya memakai id resep (R), belum T/C
- Task 6: minor (deferred): pesan 409 "ada item baru" juga muncul bila item HILANG (teks diwajibkan brief)
- Task 6: minor (deferred): jalur bayar kosong menampilkan "Minimal 1 metode" alih-alih pesan sidik bila susulan menaikkan total (pembayaran tetap tertahan)
- Task 7: minor (deferred): komentar T2-5 di kunjungan_service tersambung di tengah kalimat (rapikan)
- Task 7: minor (deferred): kasir_repo.hitung_obat_dibayar_belum_serah kini tak terpakai
- Task 7: minor (deferred): ringkasan/docstring API v1 PATCH /kunjungan/{id}/status basi ("alur normal atau BATAL")
- Task 7: minor (deferred → deploy): baris lama berlabel basi tanpa event berikutnya tak punya jalan keluar manual — pemeriksa Task 8 harus dijalankan di mini PC sebelum/ sesudah deploy dan hasilnya dilaporkan ke dr. Hansen
- Task 8: minor (deferred): DEC-050 sendiri belum diberi penunjuk "dibalik oleh DEC-101"
- Task 8: minor (deferred): CLAUDE.md §8 "Ketiganya DI MINI PC" jauh dari antesedennya (keterbacaan)
- Residual (from fix report): status_seharusnya memberi ANTRI_BAYAR pada kunjungan RETUR_PASIEN ber-SOAP FINAL tanpa transaksi (dev #1017) — bila ada yang menghitung ulangnya, menahan tutup kasir. Di luar brief perbaikan.
- Residual (minor, re-review): batalkan_tindakan menghitung label sebelum mengunci kunjungan → label bisa basi bila bayar/serah bersamaan (perbaikan: kunci kunjungan sesudah kunci tindakan)
- Residual (minor, re-review): tindakan PENDING ber-id_transaksi ke trx VOID → pesan "sudah dibayar" keliru (tak terjadi di tahap 1)
- ✅ SELESAI 2026-10-21 (status_seharusnya kini mengembalikan None untuk kunjungan non-klinis; cek_status_kunjungan --hari 30 = 0 selisih) — Residual (load-bearing untuk deploy): status_seharusnya memberi ANTRI_BAYAR pada kunjungan RETUR_PASIEN ber-SOAP FINAL tanpa transaksi → bila dihitung ulang, menahan tutup kasir (dev #1017)
- Residual (forward, tahap 4): lingkup void tak mencakup paket PRABAYAR yang tak terikat tindakan sesi 1
