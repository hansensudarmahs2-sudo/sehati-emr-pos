# Rencana Fitur Sehat-i — Hasil Diskusi (07 Juli 2026)

> **Catatan penting:** Ini kumpulan ide kasar hasil brainstorming, **belum final**. Setiap poin di bawah perlu dibahas ulang (feasibility, skema data, prioritas, edge case) sebelum masuk ke tahap implementasi apa pun.

---

## Konteks masalah

Titik konflik operasional paling sering terjadi di **antrian**, khususnya:
1. Pasien booking (sudah bayar di muka) masuk mendahului walk-in yang sudah lama menunggu → walk-in merasa diserobot.
2. Kombinasi terburuk: walk-in sudah lama menunggu + pasien booking masuk duluan → komplain berat.
3. Konsultasi dokter lebih lama dari perkiraan → pasien bertanya tanpa tahu alasannya.

Prinsip desain yang disepakati: **warna/UI hanya untuk membawa informasi fungsional, bukan dekorasi.** Setiap fitur baru dicek dulu apakah menambah beban riil ke sistem operasional (query, refresh rate, jumlah client) sebelum dianggap layak.

---

## 1. Perubahan warna kartu antrian berdasarkan waktu tunggu terlama

- Warna kartu tahap (Antri Konsul, Antri Treatment, dst) ditentukan oleh **pasien dengan waktu tunggu TERLAMA** di tahap itu (MAX, bukan rata-rata).
- Threshold awal: `< 10 menit` hijau, `11–20 menit` kuning, `> 20 menit` merah. (Threshold bisa beda per tahap — perlu dikalibrasi dari data riil, bukan asumsi.)
- Tampilkan juga angka menit eksplisit di kartu (bukan cuma warna) — penting untuk aksesibilitas dan presisi.
- Tahap "Sedang Tindakan" dikecualikan dari logika waktu tunggu (statusnya "in progress", bukan "menunggu").

**Auto-refresh — sudah disepakati:**
- **FO (Front Office):** auto-refresh tiap 30 detik, **hanya 1 station/client**.
- **Dokter/Perawat:** manual refresh saja (bukan continuous polling).
- Perlu dipastikan: endpoint query untuk fitur ini **terisolasi** dari endpoint dashboard besar (omzet/laporan), supaya benar-benar ringan.

**Kesimpulan diskusi:** dampak ke beban sistem praktis nol dengan skema di atas, asal query terpisah dan prioritas terisolasi (dikonfirmasi bisa dijamin dari sisi arsitektur).

---

## 2. Nomor antrian gabungan (booking + walk-in) + QR tracking per kunjungan

**Belum di-build — status saat ini baru status antrian di DB, belum ada nomor urut eksplisit.**

- Sehati generate nomor antrian otomatis, menggabungkan slot booking dan walk-in sesuai urutan waktu yang seharusnya (booking diselipkan sesuai jam janji, bukan FIFO murni).
- Nomor antrian dicetak via **thermal printer**, dengan QR code untuk tracking kunjungan hari itu.
- QR mengarah ke landing page publik yang menampilkan status antrian pasien secara real-time.

**Keputusan desain terkait:**
- **Tidak pakai member login** — pakai token acak per-kunjungan (bukan nomor antrian itu sendiri, supaya tidak predictable/bisa diintip orang lain).
- Landing page hanya menampilkan data minimal: nomor antrian + estimasi waktu panggil. Tidak ada nama lengkap, keluhan, atau data PHI lain.
- Token expire otomatis setelah kunjungan selesai/hari berakhir.
- Auto-refresh di landing page: 30–60 detik, berhenti polling kalau tab tidak aktif atau status sudah "dipanggil/selesai".

**Detail cetak thermal untuk diperhatikan saat implementasi:**
- Ukuran QR minimal ±2.5–3 cm persegi (resolusi thermal umumnya 180–203 dpi).
- Sisakan quiet zone yang cukup di sekeliling QR.
- Cetak juga kode token dalam bentuk teks pendek di bawah QR sebagai fallback manual kalau QR gagal di-scan.
- Pertimbangkan self-check berkala kualitas cetak (thermal head bisa aus/pudar seiring waktu).

**Manfaat langsung:** begitu nomor antrian ada, pasien walk-in yang melihat pasien booking dipanggil duluan bisa langsung paham alasannya lewat label "Booking 19:45" — mengurangi rasa diserobot tanpa mengubah aturan dasar bahwa booking tetap harus dihormati.

---

## 3. Fitur "Skip / Lewati sementara" — bergantung pada fitur #2

- Kalau pasien dipanggil tapi belum ada di ruang tunggu, FO bisa skip sementara; pasien otomatis diselipkan lagi setelah beberapa nomor berikutnya.
- **Baru bisa dibangun setelah nomor antrian (#2) ada**, karena "skip beberapa nomor" butuh urutan eksplisit — status DB saja tidak cukup untuk merepresentasikan posisi ini secara bermakna.

**Urutan build yang disepakati:** Nomor antrian + QR → fitur turunan seperti skip menyusul setelahnya.

---

## 4. History SOAP di panel kanan bawah (saat dokter mengisi SOAP)

- Menampilkan riwayat kunjungan pasien sebelumnya tanpa dokter perlu bolak-balik cari data.
- Format per kunjungan: **2 baris** — resume di baris atas, treatment + produk yang dipakai di baris bawah (tanpa ringkasan tambahan).
- Bisa di-scroll untuk lihat kunjungan lebih lama (lazy-load/pagination, jangan tarik seluruh riwayat sekaligus terutama untuk pasien lama).
- Data di-fetch sekali saat halaman SOAP dibuka — tidak perlu polling, karena riwayat tidak berubah selama sesi konsultasi berjalan.

**Manfaat:** berpotensi mempercepat durasi konsultasi (salah satu sumber utama antrian menumpuk), karena dokter tidak perlu mencari-cari histori secara manual.

---

## 5. Badge notifikasi per role

Badge kecil di sidebar/menu, **event-specific per role** (bukan notifikasi generik):

| Role | Lokasi badge | Event yang di-trigger |
|---|---|---|
| Dokter/Perawat | Menu "Antrian Saya" | Pasien baru masuk antrian klinis |
| Kasir | Menu "Kasir/POS" | Transaksi baru masuk antri bayar |
| Apotek | Menu "Apotek" | Resep baru masuk antri obat |

- Pertimbangkan menggabungkan semua badge ini ke **satu endpoint "notifikasi ringkas per role"** dipanggil saat sidebar di-load/manual refresh, bukan 4 query terpisah berjalan sendiri-sendiri.

---

## 6. Antri bayar — tidak perlu fitur baru, pendekatan scale-up berbasis data

- Keputusan: **tidak** membuat jalur prioritas (fast lane vs full purchase) karena berpotensi menimbulkan konflik baru.
- Solusi yang dipilih: pakai **audit log waktu bayar yang sudah ada** untuk pantau insiden antri bayar > X menit dengan frekuensi tertentu dalam periode waktu → jadi dasar keputusan tambah kasir (scale-up SDM, bukan fitur teknis).
- Ini bisa masuk sebagai laporan periodik sederhana (mingguan/bulanan), konsisten dengan sistem reporting owner yang sudah ada — tidak perlu fitur real-time tambahan.

---

## 7. Reminder follow-up treatment/konsultasi untuk kontrol (belum ada — untuk ditambahkan)

**Konteks:** hasil riset singkat terhadap software EMR-POS aesthetic clinic lain (AestheticsPro, Aesthetic Record, Pabau, Moxie) — beberapa fitur yang mereka tonjolkan ternyata sudah tercover di Sehati:
- Sisa kuota membership (free treatment / series treatment, member & non-member) — **sudah ada**, termasuk logic pemotongan kuota yang sudah ditest. Konfirmasi ulang
- Validasi konflik jadwal ruang/alat — **tidak relevan sebagai masalah**, karena booking Sehati sudah dibuat per-slot tetap (per jam untuk tindakan, per 30 menit untuk konsultasi), tidak ada stacking di jam yang sama.
- Before/after photo documentation & tagging — **sudah tercover** lewat modul derma-ai yang sudah ada.

Yang teridentifikasi sebagai celah nyata: **reminder follow-up treatment/konsultasi untuk kontrol**.

**Ide kasar:**
- List "Due for follow-up" di dashboard staff (bukan notifikasi ke pasien).
- Trigger berdasarkan jenis treatment yang punya jadwal follow-up standar (misal treatment tertentu perlu kontrol 2 minggu kemudian) — kemungkinan besar bisa dipetakan dari Master Treatment yang sudah ada, tinggal tambah field "interval follow-up (hari)" per jenis treatment.
- Query batch harian (dihitung sekali semalam atau saat dashboard staff dibuka), bukan real-time — karena sifatnya tidak urgent per detik seperti antrian.
- Bisa mulai dari internal-only dulu (staff yang lihat dan follow up manual ke pasien), otomasisasi ke pasien dipending dan belum masuk ke rencana hanya catatan saja.
- Status apakah sudah difolow up atau belum oleh FO masih perlu dibahas dalam perancangan halaman follow up (penting untuk audit trail log)

---

## Urutan prioritas kasar (untuk didiskusikan ulang, bukan keputusan final)

1. Nomor antrian gabungan (booking + walk-in) + QR tracking
2. History SOAP panel kanan bawah
3. Badge notifikasi per role
4. Fitur skip (setelah nomor antrian solid)
5. Monitoring antri bayar via audit log (laporan periodik, bukan fitur real-time)
6. Reminder follow-up treatment (list internal untuk staff dulu)

---

*Dokumen ini adalah hasil diskusi eksploratif dan belum melalui proses desain teknis formal (skema database, kontrak API, estimasi effort). Mohon dibahas bersama sebelum dieksekusi ke tahap coding.*