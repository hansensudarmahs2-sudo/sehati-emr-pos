# Dead-code Sweep — Analisis (2026-07-08)

Metode: analyzer AST (semua def di app/, hitung referensi lintas app/+tests/+scripts/+migrations/),
lalu vet manual tiap kandidat lintas seluruh repo termasuk template .html/.md/.yml (kecuali .venv).
Analyzer mengecualikan: dunder, endpoint (@router/@app), event-listener/validator, dan nama yang
muncul di string literal atau __all__.

Keputusan dr. Hansen 2026-07-08: **TIDAK menghapus apa pun sesi ini** — dokumen ini = catatan.

## 19 kandidat 0-referensi (terverifikasi kode + template + docs)

### KEEP — jangan hapus (7)
- `count_transaksi_for_kunjungan` (kasir_repo:160) — FLOW-D reopen cap (intent, TODO KEEP).
- `get_for_update` (master_produk_repo:30) — SELECT FOR UPDATE, anti-race (KEEP).
- `add_stok` (master_produk_repo:90) — restock concurrency (KEEP).
- `is_session_valid` (staf model:58) — session-security; calon dipakai modul Absensi/work-session.
- `invalidate` (ttl_cache:72) — bagian API cache (pelengkap get_or_set/reset_stats/set_enabled).
- `kuota_sisa` (membership model:176) — property natural (kuota_total - kuota_terpakai).
- `files_added` (zip_packer:109) — bagian API ZipPacker.

### ⚠ INVESTIGASI TERPISAH — jangan sentuh (1)
- `_create_pending_membership_history_if_needed` (pasien_service:71) — **tak pernah dipanggil.**
  Docstring #362D: seharusnya membuat PENDING pasien_membership_history SAAT PENDAFTARAN untuk tier
  non-REGULAR. Yang membuat history di membership_service:300 = jalur BAYAR/AKTIVASI (beda). Artinya
  history PENDING saat daftar kemungkinan **TIDAK tersambung** → bisa jadi bug fitur, bukan dead code.
  AKSI: putuskan — (a) WIRE ulang ke alur pendaftaran pasien, atau (b) konfirmasi memang di-drop lalu hapus.

### Aman dihapus — benar-benar mati (11) [BELUM dihapus, menunggu keputusan]
Sangat aman (private/superseded):
- `_redact` (export_service:41), `is_range_warning` (export_service:1391), `get_current_user_data` (auth_service:146)
Repo accessor tak terpakai (aman; sebagian "API rapi"):
- `get_by_nomor` (opname_repo:39), `get_stok_sistem_produk` (opname_repo:156)
- `get_alergi_aktif` (pasien_repo:134), `get_penyakit_kronis_aktif` (pasien_repo:160)
- `get_by_nomor_po` (pemesanan_repo:40), `get_item_by_id` (pemesanan_repo:44)
- `list_antrian_hari_ini` (kunjungan_repo:48), `list_antropometri_timeline` (kunjungan_repo:286)

Catatan metode: name-clash dicek — ke-19 nama unik antar-def app/, jadi 0-ref = benar-benar tak dirujuk.
Risiko sisa yang sudah dimitigasi: dynamic-dispatch (string), Jinja template, __all__ export — semua nihil.
