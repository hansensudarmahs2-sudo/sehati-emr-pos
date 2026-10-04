# F7 — Dead-code sweep 2026-10-04 (REPORT-ONLY, nol dihapus)

Menggantikan `DEAD_CODE_SWEEP_2026-07-08.md` (19 kandidat, 0 dihapus) sebagai daftar
yang berlaku. Dijalankan dari laptop terhadap `sehati_clinic/app/`.

**Tidak ada yang dihapus.** Backlog F7 memang menetapkan *report-only; periksa niat +
test per fungsi, jangan hapus buta*. Penghapusan menunggu persetujuan dr. Hansen.

---

## 1. Caranya — dan dua kali saya salah sebelum angkanya bisa dipercaya

Analisis pertama melaporkan **245 fungsi tak terpakai**. Hampir semuanya **route handler
FastAPI**, yang memang tidak pernah dipanggil namanya — ia didaftarkan lewat dekorator
`@router.get(...)`. Daftar sebesar itu tidak bisa dipakai siapa pun; ia hanya melatih
orang menutupnya.

Analisis kedua, setelah menyaring fungsi berdekorator (route, `field_validator`,
`property`, `event.listens_for`, dsb), melaporkan **0**. Juga salah: penghitungan
pemakaian ikut membaca berkas `.md`, sehingga fungsi mati yang **disebut di dokumen
desain** terlihat seperti terpakai.

Yang ketiga baru benar: saring dekorator, **dan** hitung pemakaian hanya di **kode**
(`.py`, `.html`, `.js`, `.sh`) — dokumen yang menyebut sebuah nama bukan pemakaian.

Hasil: **637 fungsi non-handler → 14 tanpa pemakai di kode.** Angka itu cocok dengan
perkiraan "~13" yang dicatat A11 pada Juli, jadi dua perhitungan yang terpisah setahun
sampai ke tempat yang sama.

⚠ Keterbatasan yang jujur: analisis ini **statis**. Fungsi yang dipanggil lewat
`getattr`, nama string, atau dari luar repo tidak akan terlihat terpakai. Karena itu
daftar ini adalah **kandidat**, bukan vonis.

---

## 2. Empat belas kandidat

### A. SUDAH DIPUTUSKAN **KEEP** (A11, 2026-07-02) — jangan dibahas lagi

| Fungsi | Berkas | Alasan keep |
|---|---|---|
| `count_transaksi_for_kunjungan` | `repositories/kasir_repo.py:218` | niat reopen FLOW-D |
| `get_for_update` | `repositories/master_produk_repo.py:30` | `SELECT … FOR UPDATE`, anti race condition |
| `add_stok` | `repositories/master_produk_repo.py:92` | pasangan `get_for_update` untuk restock |

### B. KANDIDAT HAPUS — niatnya sudah mati, terdokumentasi

| Fungsi | Berkas | Temuan |
|---|---|---|
| **`create_kunjungan_billing`** | `services/membership_service.py:793` | **Yatim dari fitur yang sengaja di-drop.** Lihat §3 |

### C. PERLU DIPUTUSKAN — kemungkinan besar sisa, tapi niatnya tidak tercatat

| Fungsi | Berkas | Catatan |
|---|---|---|
| `_redact` | `services/export_service.py:55` | Helper redaksi. Saudaranya `_mask_text` DIPAKAI, yang ini tidak. Lihat §4 |
| `get_current_user_data` | `services/auth_service.py:146` | "data user yang aman dikirim ke client" — mungkin digantikan `get_user_from_cookie` |
| `get_alergi_aktif` | `repositories/pasien_repo.py:169` | tanpa docstring |
| `get_penyakit_kronis_aktif` | `repositories/pasien_repo.py:195` | tanpa docstring |
| `list_antrian_hari_ini` | `repositories/kunjungan_repo.py:63` | mungkin digantikan query antrian per-peran |
| `list_antropometri_timeline` | `repositories/kunjungan_repo.py:306` | modul antropometri masih menunggu konektor — **mungkin disengaja untuk nanti** |
| `get_by_nomor` | `repositories/opname_repo.py:39` | tanpa docstring |
| `get_stok_sistem_produk` | `repositories/opname_repo.py:156` | "untuk lokasi RETAIL" |
| `get_by_nomor_po` | `repositories/pemesanan_repo.py:40` | tanpa docstring |
| `get_item_by_id` | `repositories/pemesanan_repo.py:44` | tanpa docstring |

**Pola yang terlihat:** 8 dari 10 di kelompok C adalah **method repository**. Itu lapisan
yang memang sering ditulis lengkap (CRUD penuh) sebelum service-nya butuh semuanya.
Sebagian besar kemungkinan bukan "mati" melainkan "belum dipakai" — dan menghapusnya
berarti menulisnya lagi nanti.

---

## 3. F5 ternyata dikerjakan separuh

Backlog F5 menyebut `_create_pending_membership_history_if_needed` "tak tersambung;
diputuskan: buang atau sambungkan".

**Fungsi itu sudah TIDAK ADA.** Ia ada di commit pertama (`dfd74ce`,
`services/pasien_service.py`) dan dihapus di `a5d7fb6` ("drop #362D"). Jadi F5 sudah
dijawab: **dibuang**.

Tapi fitur yang di-drop itu meninggalkan **dua** yatim, dan hanya satu yang dibersihkan.
Yang kedua masih ada:

```
services/membership_service.py:793  create_kunjungan_billing()
    "Buat kunjungan minimal status ANTRI_BAYAR untuk pasien dengan pending membership."
```

Route yang dulu memanggilnya, `pasien_membership_create_billing`
(`web/routes/pasien.py:1294`), sekarang **no-op yang disengaja** — komentarnya sendiri
berbunyi: *"M2: TIDAK lagi membuat kunjungan kosong … Route dipertahankan sebagai no-op
(kompat tombol/bookmark lama)"*. Ia hanya me-redirect dengan pesan.

Jadi `create_kunjungan_billing` bukan "mungkin mati" — ia **bagian service dari alur yang
sudah dicabut**, dan menghapusnya menyelesaikan pembersihan yang berhenti di tengah.
Ini bukan penghapusan buta: niatnya tercatat di komentar route dan di commit `a5d7fb6`.

**Menunggu persetujuan dr. Hansen untuk dihapus.**

---

## 4. `_redact` — dicatat sebagai temuan, bukan kesimpulan

`services/export_service.py` punya dua helper penyamaran:

```python
_mask_text(value, mask, prefix="PASIEN_HASH")   # DIPAKAI
_redact(value, mask, replacement="(redacted)")  # TIDAK dipakai di mana pun
```

Menganggurnya `_redact` **tidak** otomatis berarti ada kolom yang seharusnya diredaksi
tapi lolos — bisa saja kebutuhannya tidak pernah muncul. Apakah sebuah kolom perlu
diredaksi adalah keputusan desain ekspor, dan itu tidak bisa disimpulkan dari helper
yang tidak terpakai.

Yang bisa dikatakan dengan pasti: **ada mekanisme redaksi yang tersedia dan tidak pernah
dipanggil.** Layak dilihat sekali oleh dr. Hansen bersama daftar kolom ekspor, lalu
diputuskan dipakai atau dibuang.

---

## 5. Rekomendasi

1. **Hapus `create_kunjungan_billing`** — niatnya mati dan terdokumentasi (§3).
2. **Tinjau `_redact`** bersama daftar kolom ekspor — ini satu-satunya kandidat yang
   menyentuh privasi (§4).
3. **Biarkan 10 method repository** sampai ada alasan menyentuhnya. Menghapus CRUD yang
   "belum dipakai" hanya memindahkan pekerjaan ke masa depan, dan risikonya tidak
   sebanding — tidak ada test yang menjaga lapisan itu.
4. **Jangan jadikan ini daftar berkala.** Analisis statis di kodebase yang memakai
   dekorator dan HTMX menghasilkan positif palsu lebih cepat daripada temuan nyata;
   butuh tiga kali perbaikan metode hanya untuk sampai ke 14 nama ini.
