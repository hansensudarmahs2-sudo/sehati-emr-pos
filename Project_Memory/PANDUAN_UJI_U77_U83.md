# Panduan uji layar U77–U83 — Bayar dulu tahap 4 (hak pasien + uang kembali per tindakan)

Untuk dr. Hansen, di **desktop** (http://localhost:8001), cabang `claude/hopeful-pasteur-172ozo`.
Tabel ringkasnya (dan kolom **Hasil** yang diisi) tetap di `UJI_UI_AUDIT_2026-10-05.md` baris
U77–U83. Dokumen ini hanya menjabarkan **langkah klik demi klik**. Semua nama tombol, pesan, dan
menu di bawah disalin dari template/kode cabang ini (diperiksa 2026-10-29), bukan dari ingatan.

---

## 0. Apa yang diuji, dalam satu paragraf

Tindakan yang **sudah dibayar di muka** lalu **ditolak pasien** sebelum dikerjakan sekarang punya
dua jalan keluar: **↪ Simpan sebagai hak** (di ruang tindakan — dipakai di kunjungan lain, maks
6 bulan dari tanggal bayar) atau **↩ Kembalikan uang** (di kasir — uang keluar dari laci hari ini,
omzet hari bayar tidak diubah). Void transaksi yang tindakannya sudah jadi hak **ditolak**, dan
Finance mendapat daftar **Hak Tindakan** (kewajiban klinik yang belum dipakai).

## 1. Persiapan (sekali)

1. Pastikan desktop di cabang yang benar (WSL):
   ```bash
   cd /mnt/e/Claude/Projects/sehati-emr-pos
   git fetch origin claude/hopeful-pasteur-172ozo
   ```
   ```bash
   git checkout claude/hopeful-pasteur-172ozo
   ```
   ```bash
   git pull origin claude/hopeful-pasteur-172ozo
   ```
   Tahap 4 **tanpa migrasi**, jadi tidak perlu `alembic upgrade head` untuk tahap ini (kalau
   desktop belum pernah menjalankan migrasi tahap 1 `20261021_0100`, jalankan dulu).
2. Jalankan aplikasi seperti biasa (`uvicorn app.main:app --reload --port 8001`).
3. Siapkan akun yang dibutuhkan:
   | Akun | Dipakai untuk |
   |---|---|
   | Dokter | SOAP + meresepkan tindakan |
   | Perawat | Ruang Tindakan (Simpan sebagai hak) |
   | Kasir | Bayar, kembalikan uang, menu Hak Tindakan |
   | Admin/Superadmin/Owner | Force Void (U82) |
   | **Satu lagi** Admin/Superadmin/Owner **ber-PIN**, BUKAN akun yang sedang login | Penyetuju PIN di U81 |
   | FO | U83 (menu tidak boleh muncul) |
4. Siapkan **satu pasien uji** (mis. "ZZ Uji Hak") dan, untuk U78, satu pasien uji **ber-membership
   dengan kuota tindakan** + satu pasien dengan **paket series** (atau buat di layar seperti biasa).
5. Sebelum mulai, di WSL:
   ```bash
   cd /mnt/e/Claude/Projects/sehati-emr-pos/sehati_clinic && source .venv/bin/activate
   ```
   ```bash
   python3 -m scripts.jejak_uji_ui --mulai
   ```

## 2. Urutan — butuh DUA HARI

U81 menguji **transaksi kemarin** (PIN wajib). Transaksi tidak bisa dimundurkan tanggalnya dari
layar, jadi:

- **Hari 1:** U77 → U78 → U79 → U80 → U82 → U83 (bagian Kasir/FO), dan **siapkan bahan U81**
  (§U81 langkah 0).
- **Hari 2:** U81 → U83 (bagian ekspor `refunds_raw`, sesudah U80 dan U81 ada).

Kalau DB dev sudah punya transaksi kemarin dengan tindakan prabayar yang belum dikerjakan, U81
bisa dikerjakan hari 1 juga.

---

## U77 — Simpan sebagai hak (tindakan biasa, dibayar dengan harga)

**Bahan:** tindakan dibayar di muka (sama seperti U73).

1. FO daftarkan pasien uji → Dokter isi SOAP + tambahkan **satu tindakan berharga** (bukan kuota,
   bukan paket) → simpan.
2. Kasir → tagihan pasien itu → muncul kotak kuning *"Tindakan berikut belum dikerjakan — dibayar
   di muka."* → **centang** → bayar (TUNAI). Catat **nomor transaksi** dan **harga tindakan**.
3. Login Perawat → **Ruang Tindakan** → buka pasien itu.
4. **Periksa:** di kartu tindakan ada **▶ Mulai Tindakan** dan **↪ Simpan sebagai hak** (oranye),
   dengan kotak *"Alasan tidak dikerjakan (wajib)"*. Tombol **✗ Batalkan TIDAK ada**.
5. Isi alasan (≥ 5 huruf, mis. "pasien menolak hari ini") → **↪ Simpan sebagai hak** → konfirmasi OK.

**Harus terjadi:**
- Pesan hijau **"Hak tindakan disimpan — bisa dipakai di kunjungan lain."**
- Tindakan berstatus Batal.
- Kunjungan jadi **SELESAI** bila tak ada sisa lain (obat sudah diserahkan / tidak ada obat).
  Cek: **Tutup Kasir** hari ini tidak terhalang oleh kunjungan ini.

**Pembanding (wajib dilihat):** pada pasien lain yang tindakannya **belum dibayar**, kartu yang sama
hanya punya **✗ Batalkan** — tidak ada Simpan sebagai hak.

> Pasien & transaksi U77 dipakai lagi di U79 dan U82. Jangan di-void.

## U78 — Simpan sebagai hak untuk kuota membership / sesi series

Ulangi langkah U77, tapi tindakannya:

**a. Memakai kuota membership** (tagihannya Rp 0 untuk tindakan itu; tetap bayar tagihannya).
- Sesudah Simpan sebagai hak → pesan **"Kuota membership dikembalikan."**
- Buka **Detail Pasien → Kelola Membership**: sisa kuota kembali bertambah 1.
- Detail Pasien **TIDAK** menampilkan kartu "Hak prabayar" baru untuk tindakan ini.

**b. Sesi series ke-2** (pasien punya paket; pakai **🔄 Pakai Sesi 2** dari Detail Pasien, lalu bayar
kunjungannya).
- Pesan **"Sesi series dikembalikan — bisa dipakai lagi lewat 'Pakai Sesi'."**
- Detail Pasien → kartu **"Rencana Series & Hak Aktif"**: sesi itu tampil lagi; tidak ada hak
  prabayar baru.

**c. Sesi 1 paket** (paket baru, dibayar lunas di sesi 1).
- Sesi 1 kembali bisa dipakai, **sesi 2..N TIDAK batal** (masih tampil di kartu series).

## U79 — Memakai hak tanpa ditagih ulang

**Bahan:** pasien U77.

1. Buka **Detail Pasien** (sebelum didaftarkan lagi). Kartu **"🔄 Rencana Series & Hak Aktif"**
   menampilkan kartu tindakan U77 berlabel **Hak prabayar — sudah dibayar, belum dikerjakan**,
   dengan **💰 Nilai dibayar: Rp …** (= harga U77) dan **⏳ Berlaku sampai …** (6 bulan dari tanggal
   bayar) **(… hari lagi)**. Tombolnya belum ada — tertulis *"Daftarkan pasien ke antrian dulu"*.
2. **Cari Pasien** → pasien itu → **+ Antrian**: di menu muncul blok **"🔄 Lanjut Series / Hak"**
   dengan baris **"↪ Hak — <nama tindakan> (s/d dd-mm-yyyy)"**.
   (Boleh daftar lewat baris itu, ATAU daftar biasa lalu langkah 3.)
3. Kalau daftar biasa: kembali ke Detail Pasien → tombol **↪ Pakai Hak** → konfirmasi.
4. Perawat kerjakan tindakannya (Mulai → Selesai) → Kasir buka tagihan.

**Harus terjadi:**
- Baris tindakan itu **Rp 0** di tagihan.
- Cetak nota: baris itu bertuliskan **"Hak prabayar (dibayar sebelumnya)"** (thermal: "Hak prabayar").
- Sesudah dipakai, kartu hak hilang dari Detail Pasien dan dari menu **Hak Tindakan**.

**Tidak bisa dicek di layar dalam sehari:** "hak yang lewat batas tidak tampil" butuh hak berumur
> 6 bulan — sudah ditutup test otomatis; lewati, tulis "test" di kolom Hasil.

## U80 — Kembalikan uang tindakan (hari yang sama, tanpa PIN)

**Bahan:** tindakan baru yang dibayar di muka **hari ini** (ulangi langkah 1–2 U77 dengan pasien
lain atau tindakan lain). Catat **total transaksi** dan buka **Tutup Kasir** → catat angka
"seharusnya" (expected) laci.

1. Kasir → tagihan kunjungan itu (Cari Transaksi → **Detail**).
2. **Periksa:** ada kotak kuning **"↩ Tindakan dibayar, belum dikerjakan"** berisi nama tindakan,
   `#id · trx #…`, dan nilainya. **Tidak ada** kolom penyetuju/PIN (karena hari ini).
3. Isi alasan, pilih **TUNAI** → **↩ Kembalikan uang** → konfirmasi.

**Harus terjadi:**
- Pesan **"Uang … dikembalikan: Rp … (TUNAI), dibukukan hari ini."**
- Kotak **Pengembalian** di tagihan menampilkan baris berlabel refund tindakan.
- **Total transaksi TIDAK berubah** (bandingkan dengan catatan).
- **Tutup Kasir:** angka seharusnya laci **turun tepat sebesar nilai refund**.
- Tindakan hilang dari Ruang Tindakan (status Batal).

**Pembanding:** pada tagihan yang tindakannya kuota / sesi series (Rp 0), kotak yang sama
menampilkan tindakan itu **tanpa tombol**, dengan keterangan yang menyebut **"Simpan sebagai hak"**.

## U81 — Kembalikan uang hak dari transaksi KEMARIN (PIN wajib)

**0. Bahan (hari 1):** buat satu hak lagi persis seperti U77 (bayar di muka → Perawat **Simpan
sebagai hak**). Jangan dipakai, jangan direfund. Catat nama pasien & nilainya.

**Hari 2**, login **Kasir**:
1. Menu **↪ Hak Tindakan** → baris hak dari kemarin. Kolom aksi kini punya
   **— penyetuju —** dan **PIN** (latar kuning) di samping alasan & metode.
2. **Coba tanpa PIN:** browser tidak mau mengirim (kolom wajib). Itu pagar pertama, tapi server juga
   punya pagar — kalau ingin menguji yang kedua, pilih penyetuju dan isi PIN **salah**.
   → Ditolak, pesan merah di atas daftar, baris tetap ada.
3. Pilih penyetuju = **akun lain** (bukan Kasir yang login), isi PIN-nya yang benar →
   **↩ Kembalikan uang** → konfirmasi.

**Harus terjadi:**
- Pesan hijau "Uang … dikembalikan: Rp … , dibukukan hari ini."
- Baris hilang dari daftar Hak Tindakan; total nilai berlaku di atas daftar turun sebesar itu.
- Jejak (§3 di bawah) mencatat **refund hari lampau disetujui orang LAIN** = OK.

## U82 — Void ditolak bila tindakan sudah jadi hak; peringatan "dilepas"

**a. Transaksi yang tindakannya sudah jadi hak** (transaksi U77, atau hak U81 sebelum direfund):
- Login **Admin/Superadmin/Owner** → Kasir → **Cari Transaksi** → transaksi itu → **⚡ Force Void**
  (atau tombol Force Void di halaman tagihannya).
- Modal menampilkan kotak merah **"⛔ Tidak bisa di-void — N tindakan sudah disimpan sebagai hak
  pasien"**. Kalau tetap dikirim (isi alasan) → ditolak dengan pesan yang sama; status tetap BAYAR.
- Bila transaksinya dibayar hari ini, cek juga **Void Transaksi** di halaman *Pembayaran Berhasil*
  (`/web/kasir/bayar/sukses/<nomor transaksi>`): kotak merah yang sama.

**b. Transaksi prabayar biasa** (tindakan dibayar di muka, BELUM dikerjakan, BELUM jadi hak):
- Buka modal Void / Force Void → kotak kuning **"ⓘ N tindakan prabayar akan dilepas"**.
- Tidak perlu benar-benar di-void (perilaku void-nya sudah diuji di U75). Tutup modal.

## U83 — Menu Hak Tindakan: Kasir vs FO, dan ekspor Finance

**Kasir** → menu **↪ Hak Tindakan** (judul halaman "↪ Hak Tindakan Belum Dipakai"):
- Kolom: Pasien (+ No. RM), Tindakan (*Hak prabayar · tindakan #…* atau *Sesi 1 paket series
  (lunas)*), Nilai, Dibayar (tanggal + trx #), Berlaku s/d (+ "… hari lagi"), Aksi.
- Baris dengan sisa ≤ 30 hari berlatar **merah** (di data uji hari ini kemungkinan tidak ada —
  semua hak baru berumur ~6 bulan; tulis "tidak ada datanya" bila begitu).
- Di atas daftar: **"N hak berlaku · total nilai Rp …"** — cocokkan dengan jumlah manual.
- Tautan **"Tampilkan juga yang hangus"** ↔ **"Sembunyikan yang hangus"** berganti.

**FO:**
- Menu **Hak Tindakan tidak ada** di sidebar.
- Ketik langsung `http://localhost:8001/web/kasir/hak-tindakan` → halaman **403**.

**Ekspor Finance (hari 2, sesudah U80 & U81):**
- Superadmin/Owner → **Raw Data Export** → Weekly Pack → ↓ Download .zip → buka `refunds_raw`.
- Dua refund U80 dan U81 ada, **kolom `id_kunjungan_tindakan` terisi** (nomor tindakan yang sama
  dengan `#…` di layar). Refund jenis lain (obat, void) kolom itu kosong — wajar.

---

## 3. Sesudah selesai

1. Di WSL:
   ```bash
   python3 -m scripts.jejak_uji_ui
   ```
   Harus **0 [GAGAL]**. Bagian yang relevan: §3 Refund baru (U80/U81, termasuk "hari lampau
   disetujui orang lain"), §4 Sesi kasir, §5 Omzet (semua pembaca sepakat — refund tidak mengubah
   omzet hari bayar).
2. Dua pemeriksa tahap 4 (hanya membaca DB):
   ```bash
   python3 -m scripts.cek_tindakan_lunas_batal
   ```
   ```bash
   python3 -m scripts.cek_status_kunjungan
   ```
   Keduanya harus 0 temuan / 0 selisih.
3. Isi kolom **Hasil** U77–U83 di `UJI_UI_AUDIT_2026-10-05.md` (✅/❌ + catatan singkat).
4. Kalau ada ❌: catat **nomor transaksi, nomor tindakan (`#…`), dan pesan persis di layar** —
   itu cukup untuk melacaknya tanpa menebak.

## 4. Yang sengaja tidak diuji di layar (sudah ditutup test otomatis)

- Hak yang **hangus** (> 6 bulan) tidak bisa dipakai / direfund.
- Dua permintaan bersamaan atas hak yang sama.
- Sesi series yang tidak berstatus terjadwal saat disimpan → ditolak (409).

Sumber: `tests/integration/test_bayar_dulu_tahap4.py` (75 test), rancangan
`RENCANA_BAYAR_DULU_TAHAP4.md`, keputusan yang saya ambil sendiri di `HANDOFF_2026-10-28.md` §5
(mohon dikoreksi bila keliru — salah satunya: refund juga berlaku untuk **sesi 1 paket** yang sudah
jadi hak, selama belum ada sesi lain terpakai).
