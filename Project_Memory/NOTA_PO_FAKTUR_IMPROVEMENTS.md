# BACKLOG — Perbaikan Nota, PO, & Faktur (dr. Hansen, 2026-07-02)

Status: CATATAN + diskusi. Belum dikerjakan. Diangkat sebelum P-L8.

---

## A. Format NOTA (cetak pembayaran) — ✅ SELESAI (DEC-090, 2026-07-02)
> Butir 1-9 semua terpasang di nota_a5 (lengkap + blok ttd) & nota_thermal (tanpa blok ttd).
> Bonus: header A5 3-zona (logo kiri · nama+judul tengah · alamat kanan), pin @page A5, auto-fit JS.
1. Nama pasien + **(tanggal lahir)** dalam kurung.
2. Nomor RM.
3. Jenis kelamin.
4. **Tenaga medis** yang menangani (dokter/perawat).
5. Tanggal transaksi **+ jam**.
6. Kasir.
7. Isi nota (item).
8. Jenis pembayaran.
9. **Blok bawah**: kotak catatan + ttd pasien + ttd kasir/tenaga medis.
   Distribusi lebar: **catatan 2/5 · ttd pasien 1/10 · ttd tenaga medis 1/10** (sisanya spasi).

Catatan implementasi: sebagian data sudah ada (pasien, kasir, waktu_bayar). "Tenaga medis yang menangani"
= dokter kunjungan (id_staf_dokter_assigned / SOAP). Perlu ditambah ke context nota.

---

## B. Format PO (cetak) — perlu dilengkapi
1. Nomor PO ✅ (sudah).
2. **Termin** = jatuh tempo bayar setelah barang diterima, satuan **hari** (mis. 30 hari). Kolom baru di PO.
3. Tanggal PO ✅.
4. Dibuat oleh ✅.
5. **Validitas PO** = masa berlaku PO. Default **tanpa batas**. Kolom baru (opsional, nullable).
6. **Nomor SIA** (Surat Izin Apotek — izin apotek/klinik). Perlu tempat penyimpanan → lihat §D.
7. **Nomor SIPA** (Surat Izin Praktik Apoteker). Per-apoteker → lihat §D.
8. **Nama apoteker** (penanggung jawab PO).
9. **Dikirim ke** (ship-to). Sekarang 1 klinik; ke depan 2+ klinik → lihat §E.

---

## C. Faktur / Penerimaan — CELAH BESAR (perlu diskusi)
### C1. Status PO / siklus + faktur per-pengiriman
- Butuh status jelas: **berjalan / selesai / rilis** (+ yang sudah ada ORDERED/PARTIAL/RECEIVED).
- **Pengiriman parsial:** dari 12 item dipesan, hanya 3 datang → faktur untuk **3 item itu saja** dengan
  nomor faktur sendiri. Artinya **1 faktur = 1 pengiriman (per receive event)**, bukan digabung se-PO.
- Sekarang: faktur/cetak masih menggabung SEMUA receive se-PO. Perlu jadi per-delivery.

### C2. PPN & Diskon di halaman faktur + ALGORITMA DISKON TERBALIK
Sekarang faktur belum ada PPN & diskon. Masalah nyata: **diskon sering tidak diberitahu ke penerima**,
jadi asisten apoteker harus **mengira-ngira** diskon & harga asli per item.

**Usulan algoritma (hilangkan tebak-tebakan):**
Diketahui:
- `X` = harga seharusnya (subtotal pra-pajak = Σ harga order item, dari PO/master).
- `t` = PPN% (mis. 11%).
- `Y` = total yang benar-benar ditagih distributor (di faktur).
- `Z` = jumlah item.
- Asumsi: **diskon seragam** (persen sama untuk tiap item), diterapkan **sebelum PPN**.

Maka:
```
Y = X · (1 − d) · (1 + t)
→ d = 1 − Y / ( X · (1 + t) )          (persen diskon)
→ harga_terima_item = harga_order_item · (1 − d)
```
Contoh: X = 1.000.000, t = 11% → tanpa diskon = 1.110.000. Ditagih Y = 888.000
→ d = 1 − 888.000/1.110.000 = 20%. Per item (mis. 3×333.333) → terima 266.667/item.

Jadi asisten cukup input **Y (total ditagih)** + PPN% (X & Z sudah dari PO) → sistem hitung diskon% & harga
per item OTOMATIS. **Nol tebak-tebakan.**

Contoh 2-item (dr. Hansen): A=750.000, B=250.000 → X=1.000.000; PPN 11%; ditagih Y=888.000.
→ d = 1 − 888.000/1.110.000 = **20%** → A=600.000, B=200.000. Cek (600.000+200.000)×1,11 = 888.000 ✓.
UX: asisten ketik **satu angka (total ditagih)** → harga terima tiap item terisi otomatis + diskon% tampil.
Dua-arah: kalau diskon diberitahu (mis. 20%), ketik 20% → sistem hitung Y.
DIKONFIRMASI dr. Hansen: **diskon seragam per item, sebelum PPN**. (Diskon beda-per-item = kasus jarang, di luar cakupan.)

**PRIORITAS (dr. Hansen 2026-07-02):** kerjakan P-L8 (laporan inventory) dulu → lalu **format nota** →
lalu rombak faktur (PPN/diskon) + PO (termin/SIA/SIPA/dll) belakangan (karena besar).

---

## D. Master Surat Izin (SIA/SIPA) — usulan
- **SIA** (izin apotek) melekat ke **klinik** → simpan di Profil Klinik (kolom `nomor_sia`).
- **SIPA** + **nama apoteker** melekat ke **staf apoteker** → simpan di master_staf (kolom `nomor_sipa`),
  nama = nama_staf. PO cetak menarik dari apoteker penanggung jawab.
- Alternatif: tabel `master_surat_izin` tersendiri (kalau izin bisa banyak/berganti). ➡️ Diskusi.

---

## E. Multi-klinik (ship-to) — usulan
- Sekarang 1 klinik → "dikirim ke" = Profil Klinik.
- Ke depan 2+ klinik → butuh **master klinik/cabang** + PO/faktur pilih tujuan kirim.
- Rancang field "dikirim ke" agar klinik-aware sejak sekarang (default klinik tunggal), migrasi ringan nanti.

---

## Ringkas keputusan yang perlu dr. Hansen jawab
1. Diskon: **sebelum PPN** & **seragam per item** — benar? Ada skenario diskon flat rupiah?
2. Faktur **per-pengiriman** (1 faktur = 1 receive event) — setuju?
3. SIA di Profil Klinik + SIPA di master_staf apoteker — atau tabel master_surat_izin tersendiri?
4. Multi-klinik: rancang field ship-to sekarang (default 1 klinik) — oke?
5. Prioritas: nota dulu, atau faktur (PPN/diskon) dulu?

---

## E. KEKURANGAN PO (temuan dr. Hansen 2026-07-03, setelah PO-B)

1. **Total saat input PO** — form PO belum tampilkan total berjalan saat mengetik item. (JS running-total.)
2. **SIA di PO** — sudah ditambah di CETAK PO (po_a5 header, PO-B). Perlu dr. Hansen isi No. SIA di Profil
   Klinik + test cetak. (Kalau maksudnya SIA perlu di tempat lain juga, konfirmasi.)
3. **Alamat penerima (ship-to) bisa ≠ klinik ini** — perlu DROPDOWN alamat/klinik tujuan kirim. Butuh
   "database klinik/lokasi". → dua opsi: (a) tabel ringan `lokasi_pengiriman` (daftar alamat kirim saja),
   atau (b) MAJUKAN rename master_klinik multi-baris (yg tadinya ditunda). Perlu keputusan.
4. **Autofill dari PO sebelumnya** — saat buat PO, item yang sama bisa auto-isi (harga/qty terakhir) dari PO
   lampau. (Butuh lookup histori item per produk.)

## F. Alur PO→cetak (konfirmasi dr. Hansen)
1. PO dibuat → approve → cetak PO (kirim / dokumentasi).
2. Bila distributor WAJIB order via aplikasi mereka → dokumentasi PO = hasil cetak aplikasi distributor
   (cetak PO kita jadi opsional). → sistem tak memaksa cetak PO.
