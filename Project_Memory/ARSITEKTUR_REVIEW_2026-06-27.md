═══════════════════════════════════════════════════════════
REVIEW ARSITEKTUR SEHATI eMR-POS — 2026-06-27
Audit kode aktual (3 agent paralel) · "different perspective"
═══════════════════════════════════════════════════════════

## VERDICT
Grade **B+**. Arsitektur disiplin (layering bersih, otorisasi kuat, efisiensi sehat).
Risiko utama = **concurrency**, dan jadi LEBIH penting karena pindah dari "1 laptop"
ke "server LAN banyak client" (banyak device FO/kasir bersamaan) → race yang dulu
teoretis kini bisa nyata. PRIORITAS pra-deploy bergeser ke concurrency, bukan fitur.

═══════════════════════════════════════════════════════════
## 1. RACE / CONCURRENCY (paling penting)
═══════════════════════════════════════════════════════════
### SUDAH AMAN (terkunci benar)
- Nomor RM: `pasien_repo.py:107` FOR UPDATE + unique constraint pada no_rm. ✓
- Stok apotek: `apotek_repo.py:115` get_produk_for_update (with_for_update). ✓
- Nomor PO / opname: `pemesanan_repo.py:78`, `opname_repo.py:55` FOR UPDATE. ✓
- Dobel-bayar: `kasir_service.py:511` guard sudah_lunas (cek id_transaksi_existing). ✓
  (catatan: ada jendela TOCTOU < 1ms — risiko LOW; fix sejati = unique conditional index)
- Dobel-void: `kasir_service.py:1107` guard status != VOID. ✓
- Session per-request bersih (`db/session.py` get_db), commit/rollback eksplisit di service,
  tidak ada commit di tengah operasi (no partial write). Pool: pool_pre_ping + pool_recycle=280.

### BELUM AMAN (2 lubang nyata) → FIX PRA-DEPLOY
🔴 **Nomor antrian** `kunjungan_repo.py:31` `get_nomor_antrian_berikutnya`
   = MAX(nomor_antrean)+1 TANPA lock & TANPA unique constraint.
   2 FO daftar bersamaan (multi-device) → nomor antrian KEMBAR. Risiko HIGH di LAN.
   FIX: unique constraint (DATE(tgl_kunjungan), nomor_antrean) ATAU FOR UPDATE lock.
   → Task #43.
🟡 **Kuota membership** `membership_service.py` increment/decrement_kuota_terpakai
   = read-modify-write Python (BUKAN atomik). 2 kasir proses member sama → lost update
   (kuota harusnya −2, malah −1). Risiko MEDIUM.
   FIX: UPDATE ... SET kuota_terpakai = kuota_terpakai + 1 WHERE kuota_total > kuota_terpakai.
   → Task #44.

═══════════════════════════════════════════════════════════
## 2. OVER-CACHING
═══════════════════════════════════════════════════════════
- ⚠️ `get_settings()` @lru_cache (`config.py:92`) → ubah `.env` (mis. rm_clinic_prefix)
  BARU jalan setelah RESTART server. Bukan bug; catat di runbook deployment.
- Sisanya bersih: rate-limit in-memory (sengaja), Jinja normal, TIDAK ada HTTP cache
  (benar untuk data medis — tak ada risiko data basi), tidak ada Redis/memcached (cukup utk MVP).

═══════════════════════════════════════════════════════════
## 3. EFISIENSI WEBAPP — SEHAT
═══════════════════════════════════════════════════════════
- Tidak ada N+1: list antrian `kunjungan_repo.py` pakai JOIN sekali jalan (Kunjungan+Pasien+Dokter).
- Pasien get_by_id: selectinload opsional (caller yang kontrol).
- Pool config benar: pool_recycle=280 < wait_timeout MySQL → anti "MySQL gone away".
- Semua report agregasi + dibatasi rentang tanggal (no unbounded fetch).

═══════════════════════════════════════════════════════════
## 4. OVERLAP / DUPLIKASI — BERSIH
═══════════════════════════════════════════════════════════
- Layering rapi: route → service → repo. TIDAK ada route query DB langsung.
- Role check TERPUSAT di `_shared.py` (tier hierarkis Owner>Superadmin>Admin>Operational).
- Hitung tagihan SATU sumber `get_tagihan`; pembayaran re-fetch server-side (anti-tamper).
- Pembuatan kunjungan dijaga guard "sudah ada di antrian hari ini".
- Transisi status pakai `_VALID_TRANSITIONS` terpusat. Tidak ada file _OLD / dead code.
- ⚠️ CATATAN: `metode_bayar` = VARCHAR bebas TANPA enum → akar masalah "CASH vs Tunai".
  Variasi ejaan → metode terpisah di report. FIX: enum + validasi schema. → Task #45.

═══════════════════════════════════════════════════════════
## 5. KEAMANAN
═══════════════════════════════════════════════════════════
- Otorisasi KUAT: tier hierarkis + can_edit_role_of / can_promote_to_role (anti eskalasi).
- Rate-limit login sudah ada (#28 done). Query text() generator pakai bound param (aman SQLi).
- SISA: paket #37-40 (JWT tampering, SQLi field input, session fixation, mass-assignment)
  belum dijalankan — sudah di plan pra-launch.

═══════════════════════════════════════════════════════════
## 6. USER-FRIENDLY
═══════════════════════════════════════════════════════════
- Sudah dibereskan: format Rp (#30), label tombol wizard (#31), role enum leak (#29).
- Sisa polish #34 (a11y label + overflow tabel) = post-launch, tidak menghalangi.

═══════════════════════════════════════════════════════════
## TINDAK LANJUT (3 fix ditambah ke todo pra-deploy)
═══════════════════════════════════════════════════════════
- #43 🔴 Nomor antrian anti-duplikat
- #44 🟡 Kuota membership atomic update
- #45 🟡 Enum metode_bayar
Setara penting dengan paket keamanan #37-40. Murah dikerjakan, mahal kalau dilewat.
Tutup Kasir (#41) tetap jalan, tapi 3 fix ini diutamakan sebelum LAN multi-client go-live.

CATATAN: sesi ini ANALISA SAJA — tidak ada kode disentuh.
═══════════════════════════════════════════════════════════
