# Review Kode `Current python code main_api.txt`

> Review oleh: Claude (lead programmer)
> Tanggal: 27 April 2026
> Total baris kode: 1.892
> Total endpoint: 27 (login, logout, FO ×6, Kasir ×5, Dokter ×6, Ruang Tindakan ×6, Apotek ×4)

---

## Ringkasan eksekutif (TL;DR)

**Kabar baik:** Logika bisnis kode dokter Hansen **sudah matang dan dipikirkan dengan baik**. Banyak detail klinik yang biasanya dilewatkan programmer pemula sudah dokter tangani — anchor shift kasir, bulletproof double-charge prevention, otorisasi PIN untuk upsell, soft delete medical record, AMC + UoM untuk suggested order. Saya akui ini effort yang serius.

**Kabar yang harus dokter tahu:** Ada **3 masalah security kritis** yang harus diperbaiki sebelum kode ini dipakai dengan data pasien sungguhan. Ada juga **masalah arsitektur** (file 1.892 baris dalam satu file) yang akan menyulitkan pemeliharaan di bulan-bulan ke depan.

**Strategi saya:** Kita **TIDAK buang kode dokter**. Kita **refactor bertahap** — pindahkan logika bisnis dokter ke struktur layered yang sudah saya usulkan di `02_STRUKTUR_PROGRAM.md`, sambil perbaiki masalah security & bug.

---

## 🔴 Masalah KRITIS (harus diperbaiki minggu 1-2)

### K1. Password disimpan plaintext di database

```python
# Line 36-37
sql = "SELECT * FROM master_staf WHERE username = %s AND password_hash = %s AND is_active = 1"
cursor.execute(sql, (request.username, request.password))
```

**Masalah:** Kolom namanya `password_hash` tapi yang dibandingkan adalah password plaintext. Ini berarti DB sehati saat ini menyimpan password apa adanya, bukan hash.

**Risiko:** Kalau DB bocor (backup hilang, hacker masuk), semua password staff langsung terbaca. Ini melanggar standar minimum keamanan untuk aplikasi yang menyimpan data medis (HIPAA, UU PDP Indonesia).

**Solusi:** Pakai bcrypt. Saya akan tulis:
```python
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def hash_password(password):
    return pwd_context.hash(password)
```

**Migrasi:** Saya akan buat script untuk hash semua password yang ada sekarang. Staff tidak perlu reset, tapi sebaiknya diumumkan dan staff ganti password sekali setelah migrasi.

---

### K2. Otentikasi pakai `id_staf` di body request — bisa di-spoof

```python
# Line 161-167
def verifikasi_fo(cursor, id_staf):
    cursor.execute("""
        SELECT role FROM master_staf 
        WHERE id_staf = %s AND is_logged_in = 1 AND token_expired_at > NOW()
    """, (id_staf,))
```

**Masalah:** Setiap endpoint terima `id_staf` di body request, lalu cek apakah staf itu sedang login. Tapi **tidak ada tanda tangan / JWT** — siapa saja yang tahu ID staf bisa pura-pura jadi staf itu.

**Skenario serangan sederhana:**
1. Anyone sniffing network tahu `id_staf=5` adalah dokter Hansen.
2. Mereka kirim request `POST /dokter/input_medis` dengan `id_staf_dokter=5`.
3. Backend cek "id 5 login? token aktif?" → ya → eksekusi.
4. Pasien orang lain dapat catatan medis salah.

**Solusi:** Implementasi JWT.
- Login → backend kirim **JWT signed** dengan payload `{id_staf, role, exp}`.
- Setiap request berikut bawa header `Authorization: Bearer <token>`.
- Backend verifikasi signature → kalau valid, tahu siapa user. Tidak perlu lagi `id_staf` di body.

Logika "anchor shift" dokter (`waktu_mulai_shift`) tetap dipertahankan — itu bagus untuk laporan kasir.

---

### K3. `end_treatment` didefinisikan 2× — endpoint pertama jadi dead code

```python
# Line 1347 → versi pertama (tanpa potong stok)
@app.post("/ruang_tindakan/end")
def end_treatment(request: EndTreatmentRequest):
    # ... versi sederhana

# Line 1470 → versi kedua (dengan auto potong stok BHP)
@app.post("/ruang_tindakan/end")
def end_treatment(request: EndTreatmentRequest):
    # ... versi enterprise
```

**Masalah:** FastAPI tidak error saat ada 2 endpoint sama path & method. Tapi **yang dipakai hanya yang terakhir di-define**. Versi pertama (line 1347-1390) **tidak pernah dipanggil** — dead code yang membingungkan.

**Solusi:** Hapus versi pertama. Saat refactor ke service layer, hanya satu `treatment_service.end_treatment()` yang dipakai.

---

### K4. `transaksi_detail_produk` di-insert dengan `harga_satuan = 0, subtotal = 0`

```python
# Line 710
sql_detail = "INSERT INTO transaksi_detail_produk (id_transaksi, id_produk, qty, harga_satuan, subtotal) VALUES (%s, %s, %s, 0, 0)"
```

**Masalah:** Saat eksekusi pembayaran, detail produk disimpan dengan harga 0. Konsekuensi:
- Laporan penjualan produk per item tidak akurat (semua produk seakan gratis).
- Audit transaksi tidak match (`SUM(detail.subtotal) ≠ transaksi_kasir.total_tagihan`).
- Reprint struk akan menampilkan harga 0.

**Solusi:** Saat insert ke `transaksi_detail_produk`, JOIN ke `master_produk` untuk ambil `harga_jual`, hitung `subtotal = qty × harga_jual`. Kalau ada diskon item, simpan juga.

---

### K5. Tidak ada `try/except` untuk rollback transaksi

Semua endpoint pakai pola:
```python
conn = koneksi_db()
try:
    with conn.cursor() as cursor:
        # eksekusi N query
        conn.commit()
        return {...}
finally:
    conn.close()
```

**Masalah:** Kalau exception terjadi di tengah-tengah (misal query ke-3 dari 5 gagal):
- Tidak ada `rollback()` dipanggil — query 1-2 yang sudah `execute` akan ter-commit otomatis saat connection close (tergantung autocommit mode pymysql, **biasanya iya**).
- Hasilnya: data partial — pasien terdaftar tapi alergi tidak ter-input, atau resep masuk tapi status kunjungan tidak update.

**Solusi:** Wrap dengan try/except eksplisit:
```python
conn = koneksi_db()
try:
    with conn.cursor() as cursor:
        # ...
        conn.commit()
        return {...}
except Exception as e:
    conn.rollback()
    raise
finally:
    conn.close()
```

Dengan SQLAlchemy nanti, ini di-handle otomatis via context manager `Session.begin()`.

---

## 🟡 Masalah PENTING (harus diperbaiki Phase 1)

### P1. Asumsi `id_produk == id_bahan` — fragile coupling

```python
# Line 1633 (apotek/detail)
LEFT JOIN inventory_stok inv ON mp.id_produk = inv.id_bahan

# Line 1684 (serahkan_obat)
SELECT stok_gudang_utama FROM inventory_stok WHERE id_bahan = %s
# parameter: id_produk dari kunjungan_resep
```

**Masalah:** Kode mengasumsikan id_produk di `master_produk` sama dengan id_bahan di `inventory_stok`. Ini bekerja sekarang karena dokter manual sinkronkan ID, tapi:
- Tambah produk baru tanpa tambah bahan → JOIN akan gagal.
- Hapus bahan tanpa hapus produk → JOIN akan gagal.
- Tidak ada FK yang enforce ini di DB.

**Solusi:** Di refactor inventory:
- Pisahkan tegas: `master_produk` (yang dijual via POS) dan `inventory_stok` (bahan klinik).
- Tambah kolom mapping eksplisit, misal `master_produk.id_bahan_terkait` (nullable FK ke `inventory_stok`). Kalau produk juga jadi bahan klinik, isi mapping. Kalau cuma dijual, biarkan NULL.
- Service `inventory_service` punya method `get_stok_by_produk(id_produk)` yang abstraksi mapping ini.

---

### P2. Diskon membership hard-coded (10%, 20%)

```python
# Line 610-614
if kunjungan['tipe_membership'] == 'VIP':
    persen_diskon = 10 
elif kunjungan['tipe_membership'] == 'VVIP':
    persen_diskon = 20 
```

**Masalah:** Kalau dokter mau ubah diskon (misal VIP jadi 15%), harus edit kode + redeploy. Bisnis owner akan minta saya ubah ini, padahal seharusnya bisa diubah di admin panel.

**Solusi:** Bikin tabel `master_membership` (sudah saya catat di `01_ANALISA_DATABASE.md` poin #6). Service `membership_service.get_diskon(tier)` baca dari DB.

---

### P3. Diskon hanya untuk tindakan, tidak untuk produk

```python
# Line 616
nominal_diskon = int(total_tindakan * (persen_diskon / 100))
```

**Masalah:** Sesuai dokumentasi alur (`Tables_in_db_sehati.txt` baris 361-362): *"membership... tidak ada diskon khusus untuk produk tapi ada system untuk delivery to their doorstep"* — jadi memang diskon hanya untuk tindakan. **Logikanya benar**, tapi:
- Kalau nanti owner mau diskon produk juga (Black Friday, cuci gudang), harus ubah kode.

**Solusi:** Sambil bikin `master_membership`, tambah field `diskon_treatment_persen` dan `diskon_produk_persen` terpisah. Default produk = 0 saat ini.

---

### P4. `pemeriksaan_klinis` tidak punya `saran_treatment`/`saran_produk` field di-fill

Saat dokter input_medis, `pemeriksaan_klinis` di-insert dengan `anamnesa, pemeriksaan_fisik, diagnosa` saja. Tapi kolom `saran_treatment` dan `saran_produk` di skema DB ada — kosong selalu.

**Pertanyaan dokter:** Kolom ini buat apa? Apakah dokter mau tulis text bebas saran treatment selain yang masuk ke keranjang? Atau redundant dan bisa dihapus?

---

### P5. `pasien_rencana_treatment` insert pakai nama, bukan `id_treatment`

```python
# Line 1108
cursor.execute(sql_rencana_series, (request.id_pasien, sesi, nama_treatment_db))
```

**Masalah:** Dokter pilih `id_treatment` dari frontend, kode lookup nama, lalu insert nama (string). Sesuai analisa DB poin #2 — denormalisasi.

**Solusi:** Setelah migrasi `pasien_rencana_treatment` tambah `id_treatment INT FK`, ubah insert pakai ID. Nama tetap disimpan untuk backward compat (snapshot saat plan dibuat — kalau treatment di-rename, history rencana tetap akurat).

---

### P6. Stok bisa minus (tidak diblok)

```python
# Line 1524, 1694, 1769
stok_baru = stok_sekarang - qty_dipakai  # tidak ada cek minus
```

**Masalah:** Kalau perawat eksekusi tindakan tapi bahan habis (race condition atau salah input), stok jadi minus. Komentar dokter di line 1767-1768: *"toh ini akan tercatat di log audit"* — ini valid keputusan bisnis (operasional jangan diblok), tapi:
- Tidak ada warning ke user.
- Tidak ada laporan stok minus untuk dokter monitor.

**Solusi:**
- Tetap izinkan minus (sesuai keputusan dokter).
- Tapi kasih warning di response: `"warning": "Stok bahan X minus 2 unit"`.
- Buat endpoint `/admin/laporan/stok_minus` untuk monitor.

---

### P7. `verifikasi_dokter`, `verifikasi_perawat`, `verifikasi_apoteker` tidak ada

Hanya `verifikasi_fo` dan `verifikasi_kasir` yang di-implement. Endpoint dokter, perawat (ruang tindakan), apoteker — tidak ada cek role.

```python
# Line 871 — komentar dokter
# Opsional: Bisa tambahkan verifikasi_dokter(cursor, id_staf) jika perlu
```

**Konsekuensi:** Siapa saja yang tahu URL dan format request bisa input medis sebagai dokter. Ini bocor sekali.

**Solusi:** Saat refactor ke JWT, semua endpoint punya dependency `role_required(["Dokter"])` otomatis. Tidak perlu manual lagi.

---

### P8. `id_kunjungan_eksekusi` di `pasien_rencana_treatment` tidak pernah di-update

Saat pasien datang lagi untuk treatment series ke-2, kunjungan baru dibuat tapi `pasien_rencana_treatment.id_kunjungan_eksekusi` tetap NULL. Akibatnya:
- Tidak bisa track sesi mana sudah dilakukan.
- `status` rencana selalu PENDING.

**Solusi:** Saat FO check-in pasien yang punya rencana series aktif, sistem tampilkan rencana yang available. Saat rencana dipilih, update `id_kunjungan_eksekusi` dan `status`.

---

### P9. Iterasi resep (`pasien_resep_iterasi`) tidak tersentuh

Tabel ini ada di skema DB tapi tidak ada satu pun endpoint yang baca/tulis ke sini.

**Sesuai dokumentasi alur:** *"membeli produk bebas. mengikuti iterasi produk... krim malam, krim steroid harus ada iterasi dari dokter"*.

**Implikasi:** Fitur "pasien beli produk tanpa konsultasi" belum jalan. Perlu masuk ke roadmap Phase 1.

---

### P10. CORS belum di-config

Saat frontend dibikin (entah di port lain atau domain lain), browser akan blok request karena CORS. Belum ada `app.add_middleware(CORSMiddleware, ...)`.

**Solusi:** Tambah di `app/main.py` saat refactor. Whitelist domain frontend.

---

## 🟢 Yang BAGUS dari kode dokter (highlight + saya pertahankan)

### B1. Anchor shift kasir (`waktu_mulai_shift`)

```python
# Line 45-47
SET ... waktu_mulai_shift = IF(DATE(waktu_mulai_shift) = CURDATE(), waktu_mulai_shift, NOW())
```

Cerdas! Login ulang di hari yang sama tidak reset shift — dokter pikir kasus "kasir keluar sebentar lalu login lagi". Saya pertahankan logika ini di service layer.

### B2. Bulletproof double-charge prevention

```python
# Line 567-584 (kasir/tagihan)
cursor.execute("SELECT id_transaksi, total_tagihan, waktu_bayar FROM transaksi_kasir WHERE id_kunjungan = %s", (id_kunjungan,))
cek_lunas = cursor.fetchone()
if cek_lunas:
    return {... "TAGIHAN SUDAH LUNAS" ...}
```

Bagus — pencegahan kasir tidak sengaja charge ulang pasien yang sudah bayar. Ini sering dilewatkan di POS pemula.

### B3. Smart trigger setelah end treatment

```python
# Line 1380-1382
SELECT COUNT(*) ... WHERE status_tindakan IN ('PENDING', 'PROSES')
if sisa == 0:
    UPDATE kunjungan SET status_antrian = 'ANTRI_BAYAR'
```

Auto-pindah pasien ke ANTRI_BAYAR kalau semua tindakan di kunjungan itu sudah selesai. UX flow yang halus.

### B4. PIN otorisasi untuk upsell terbatas

```python
# Line 1427-1436
if is_restricted == 1:
    if not request.id_staf_otorisasi or not request.pin_otorisasi:
        raise HTTPException(...)
    # cek PIN dokter
```

Reuse `master_treatment.butuh_otorisasi` flag untuk gate upsell perawat. Pakai PIN (bukan password ulang) — bagus untuk UX di ruang tindakan iPad.

### B5. Auto potong stok BHP saat end treatment + log history

```python
# Line 1505-1542
SELECT id_bahan, qty FROM treatment_komponen WHERE id_treatment = %s AND kategori = 'BAHAN'
# ... loop, FOR UPDATE, potong stok, write history
```

Lengkap dan benar. Pakai `FOR UPDATE` untuk concurrency. History log lengkap dengan referensi & keterangan.

### B6. Kalkulasi klinis (BMI + Body Fat Pollock 3-site)

```python
# Line 853-866
def hitung_body_fat_pollock(jk, usia, sum_skinfold):
    if jk.upper() == 'L':
        body_density = 1.10938 - (0.0008267 * sum_skinfold) + ...
```

Formula Jackson-Pollock + Siri equation **benar** sesuai literatur. Saya verifikasi:
- Pria: density = 1.10938 − 0.0008267×Σ + 0.0000016×Σ² − 0.0002574×age ✓
- Wanita: density = 1.0994921 − 0.0009929×Σ + 0.0000023×Σ² − 0.0001392×age ✓
- Body fat % = 495/density − 450 (Siri) ✓

Saya pertahankan, hanya pindah ke `app/core/kalkulasi_klinis.py`.

### B7. Kalkulator suggested order (AMC + UoM)

```python
# Line 1805-1891
amc = total_pakai_3_bln / 3.0  # Average Monthly Consumption
if amc > 50: kategori = "FAST MOVING", buffer 2 bulan
else: kategori = "SLOW MOVING", buffer 1 bulan
saran_beli_po = math.ceil(kekurangan_terkecil / rasio)
```

**Sangat bagus.** Kebanyakan apoteker pemula tidak pakai AMC, mereka order pakai feeling. Logika UoM (`rasio_konversi`) untuk konversi ke satuan pembelian juga jarang ada. Saya akan pertahankan dan sempurnakan dengan parameter `lead_time` (berapa hari supplier deliver).

### B8. Soft delete untuk medical record (alergi)

```python
# Line 1188 — hapus_alergi pakai is_active = 0
```

Tepat sekali untuk EMR. Komentar dokter: *"Di dunia medis (EMR), kita haram menghapus data fisik"* — saya setuju 100%.

### B9. Split payment ready

```python
# Line 527 — class PembayaranItem (list of metode_bayar + nominal)
# Line 700-703 — loop insert ke transaksi_pembayaran
```

Pembayaran bisa split (sebagian tunai, sebagian QRIS, dll). Sudah ready dari awal. Bagus.

### B10. Auto-generate `no_rm`

```python
# Line 199
no_rm_baru = datetime.now().strftime("RM-%y%m%d-%H%M%S")
```

Format human-readable: `RM-260427-153045` = RM tanggal 27 April 2026 jam 15:30:45. Sederhana, kolisi mustahil (kecuali 2 pasien daftar di detik yang sama). OK untuk MVP — kalau klinik tumbuh, bisa diganti UUID atau sequence.

---

## Pertanyaan tambahan dari kode (di luar yang sudah ada di analisa DB)

11. **`kunjungan_resep.id_produk` vs apotek `id_bahan`** — apakah dokter ingin satu master atau dua? (poin P1).
12. **`pemeriksaan_klinis.saran_treatment` & `saran_produk`** — buat apa? (poin P4).
13. **Antrian apotek hanya cek `status_antrian = 'ANTRI_OBAT'`** — siapa yang set status ini? Saat ini di `eksekusi_pembayaran` set ke `'AMBIL_PRODUK'`, tidak ada yang set `'ANTRI_OBAT'`. Apakah `AMBIL_PRODUK == ANTRI_OBAT`? Atau memang ada gap?
14. **PIN dokter** — saat ini di-store plaintext di `master_staf.pin`. Mau di-hash juga seperti password?
15. **`kunjungan_foto`** — modul foto belum di-implement sama sekali. Phase berapa?

---

## Rekomendasi strategi refactor

**JANGAN rewrite from scratch.** Itu akan buang 1.892 baris business logic yang sudah teruji di kepala dokter.

**Strategi: Strangler Pattern (refactor bertahap)**

1. **Minggu 1-2:** Setup struktur folder baru. Tulis models & repositories untuk SEMUA tabel. **Belum ubah endpoint apa pun** — kode lama masih jalan.

2. **Minggu 3-4:** Pindahkan logika 1 modul per minggu ke service layer. Endpoint baru di `app/api/v1/...` yang call service. Endpoint LAMA di `main_api.py` masih ada — frontend bertahap pindah.
   - Minggu 3: Auth + FO module (paling kritis security)
   - Minggu 4: Dokter + Perawat module

3. **Minggu 5-6:**
   - Minggu 5: Kasir + Apotek module
   - Minggu 6: Admin (master CRUD), Owner dashboard

4. **Minggu 7:** Buang `main_api.py` lama. Build frontend HTMX/Jinja minimal untuk staf (FO, kasir, dokter punya UI sendiri).

5. **Minggu 8:** Testing real di klinik (dokter pakai sambil saya monitor bug). Polish UI/UX. Backup & deployment.

Detail per minggu di `03_WORK_PLAN.md`.

---

## Kesimpulan

Kode dokter Hansen adalah **fondasi yang kuat**, tapi **bukan production-ready** karena 5 masalah kritis (security & bug). Setelah refactor, sistem ini akan punya:

- Logika bisnis dokter yang sudah teruji ✓ (kita pertahankan)
- Arsitektur layered yang mudah dipelihara ✓ (kita refactor)
- Security yang patut untuk data medis ✓ (kita perbaiki)
- Frontend yang staf bisa pakai ✓ (kita build di minggu 7)

Saya yakin **2 bulan cukup** untuk refactor + frontend + testing real, asal kita disiplin per-minggu dan dokter konsisten kasih feedback.
