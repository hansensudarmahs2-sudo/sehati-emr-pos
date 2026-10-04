# Paket Klinis Tahap B — tindakan, resep, racikan, followup

**Dibangun 2026-10-04 di laptop.** Melengkapi Tahap A (profil, kunjungan, SOAP,
diagnosa, peta gabung). Tidak ada migrasi — semua data sudah ada di tabel yang ada.

---

## 1. Kenapa Tahap B ada

Tahap A mengirim **narasi dan kode diagnosa**, tapi berhenti di situ. Modul analisis
(Oracle / Council AI) melihat pasien datang, didiagnosa, lalu… tidak ada apa-apa. Ia
tidak bisa menjawab dua pertanyaan yang justru paling ingin dijawab klinik:

1. **Apa yang sebenarnya diberikan** ke pasien — tindakan apa, obat apa, racikan apa.
2. **Apakah pasien kembali** — atau hilang tanpa kontrol.

`followup` yang menjawab nomor 2, dan itu alasan utama Tahap B dikerjakan.

---

## 2. Lima berkas (empat konsep)

Racikan butuh dua berkas: induk dan bahan. Jadi "4 berkas" di CLAUDE.md §8 menjadi 5.

| Berkas | Sumber | Kunci |
|---|---|---|
| `06_clinical_tindakan.csv` | `kunjungan_tindakan` + `master_treatment` + `master_staf` | `tid`, `kid`, `pid` |
| `07_clinical_resep.csv` | `kunjungan_resep` + `master_produk` | `rid`, `kid`, `pid` |
| `08_clinical_racikan.csv` | `kunjungan_racikan` | `racid`, `kid`, `pid` |
| `09_clinical_racikan_bahan.csv` | `kunjungan_racikan_bahan` | `bid`, `racid`, `kid`, `pid` |
| `10_clinical_followup.csv` | `followup` + `master_treatment` | `fid`, `kid`, `pid` |

Ditambahkan di **akhir** `REGISTRY` dengan sengaja: nomor urut berkas berasal dari
urutan di sana. Menyisipkan di tengah akan menomori ulang berkas Tahap A, dan penerima
yang sudah menyimpan riwayat akan melihat berkas "baru" yang sebenarnya sama.

---

## 3. Keputusan dr. Hansen — kolom uang TIDAK ikut

Tabel racikan menyimpan `harga_satuan`, `subtotal`, `biaya_racik`, `total`. **Tidak
satu pun dikirim.**

Alasannya: paket klinis baru saja dipisahkan dari `finance_pack` justru karena hak
akses dan jalur keluarnya berbeda. Kalau harga ikut di sini, pemisahan itu batal —
paket klinis jadi punya nilai komersial, dan alasan untuk membatasinya jadi kabur.
Yang dikirim adalah **apa yang diberikan** ke pasien: bahan, dosis, satuan, aturan
pakai. Bukan berapa harganya.

### Ditulis sebagai PAGAR, bukan komentar

Komentar tidak menahan siapa pun. Kolom harga di `kunjungan_racikan_bahan` duduk tepat
di sebelah kolom dosis — menambahkannya ke `SELECT` hanya butuh satu kata, dan tidak
akan terlihat salah saat ditulis.

Karena itu `pagar_kolom()` sekarang menolak **dua** kelas kolom:

```python
KOLOM_TERLARANG  →  KolomTerlarangError   (identitas pasien, sudah ada)
KOLOM_UANG       →  KolomUangError        (angka uang, BARU)
```

Berjalan pada setiap baris setiap berkas, Tahap A maupun B. Diuji dua arah: 10 dataset
nyata lolos, dan 5 nama kolom uang yang disisipkan ditolak semua.

---

## 4. Yang ikut, dan kenapa

**`clinical_tindakan`** — nama tindakan, status, pelaksana (dokter & perawat sebagai
**nama**, bukan id, mengikuti `visits` yang sudah mengirim `nama_dokter` atas permintaan
dr. Hansen), waktu mulai/selesai. `dari_kuota_member` dan `dari_rencana` dikirim sebagai
**bendera 1/0**, bukan id — cukup untuk membedakan tindakan yang ditebus dari kuota
membership atau rencana terapi, tanpa membocorkan kunci internal.

**`clinical_resep`** — `kandungan` dan `golongan` ikut. Untuk pertanyaan klinis yang
berarti adalah zat aktif dan kelas obatnya, bukan merek dagang; tanpa itu analis harus
memetakan 154 nama dagang sendiri. `is_iterasi` menandai tebus ulang — penanda
kelangsungan terapi.

**`clinical_racikan` + `_bahan`** — `nama_snapshot` sudah tersimpan di tabel, jadi
racikan tidak punya masalah rename (lihat §5). Bahan membawa `dosis_per_unit`,
`satuan_dosis`, `kekuatan_snapshot`, `mode_hitung`, `dipakai`. `pid` dan `kid` ikut di
berkas bahan walau bisa dijangkau lewat `racid`, supaya berkas itu bisa dianalisa
sendiri — pola yang sama dipakai berkas Tahap A.

**`clinical_followup`** — `status` membedakan:

| status | artinya |
|---|---|
| `PENDING` / `CONFIRMED` / `RESCHEDULED` | masih dalam alur |
| **`NO_ANSWER`** | dihubungi, tidak menjawab |
| **`CANCELLED`** | membatalkan |

Dua yang terakhir adalah sinyal drop case yang dicari. Tanpa berkas ini, analis melihat
pasien berhenti datang dan tidak bisa membedakan "sembuh lalu tidak perlu kembali" dari
"hilang tanpa kontrol".

⚠ **Followup disaring per `due_date`, bukan per tanggal kunjungan.** Followup hidup
SESUDAH kunjungannya; memakai `tgl_kunjungan` membuat followup yang jatuh tempo di luar
rentang ikut hilang — dan drop case paling telat justru yang paling penting terlihat.

---

## 5. Keterbatasan yang diketahui — dicatat, bukan ditemukan sebagai kejutan

**`kunjungan_tindakan` tidak punya snapshot nama.** Tidak seperti `kunjungan_diagnosa`
yang menyimpan `nama_snapshot`, nama tindakan di-JOIN dari `master_treatment`
**sekarang**. Kalau sebuah tindakan di-rename, SELURUH riwayatnya ikut berubah nama di
ekspor berikutnya — analis akan melihat satu tindakan lenyap dan tindakan lain muncul
dengan riwayat panjang, tanpa penjelasan. Ini pola yang sama dengan yang ditutup
`clinical_pid_gabung` untuk pasien.

Menambalnya butuh kolom snapshot = **migrasi**, dan Tahap B sengaja tanpa migrasi.
**Perlu keputusan dr. Hansen** apakah itu dikerjakan di tahap berikutnya.

**`catatan` di followup adalah teks bebas.** Petugas menuliskan hasil menelepon di sana,
jadi ia bisa memuat nama dan nomor orang. Dikirim apa adanya sesuai keputusan dr. Hansen
— dan itu bagian dari kenapa paket ini rahasia dan terenkripsi, bukan anonim.

**Belum ikut sama sekali:** alergi, penyakit kronis, antropometri. Dipisah ke tahap
berikutnya atas keputusan dr. Hansen (4 berkas dulu).

---

## 6. Bug yang ditemukan saat pengujian

`kekuatan_snapshot` adalah `decimal(10,3)` di DB, bukan teks. Versi pertama kode
menuliskannya sebagai `r[7] or ""` — yang akan mengubah nilai 0 jadi string kosong dan
mengirim objek `Decimal` untuk nilai lain. Ketahuan hanya karena ada data uji nyata;
dengan DB kosong, query-nya "berhasil" tanpa pernah membuktikan apa pun.

---

## 7. Temuan sampingan: pemeriksa urutan pid berteriak serigala

`cek_clinical_pack.py` menguji bahwa `pid` tidak mencerminkan urutan `id_pasien`.
Pengujiannya membandingkan dua urutan — tapi untuk **n** pasien, peluang permutasi acak
kebetulan sama dengan urutan id adalah **1/n!**. Jadi:

| n pasien | peluang gagal palsu |
|---|---|
| 1 | **100%** — selalu gagal |
| 2 | **50%** |
| 3 | 17% |
| 8 | 1/40.320 |

Di DB dev berisi 2 pasien uji, ia melaporkan kebocoran privasi yang tidak ada — pid-nya
memang dari `secrets`, hanya kebetulan terurut. Pemeriksa privasi yang sering salah
melatih orang mengabaikannya, persis yang tidak boleh terjadi di berkas ini. Sekarang
uji itu menyatakan **TIDAK DAPAT DIUJI** di bawah 8 pasien, alih-alih gagal.

---

## 8. Status pengujian

Diverifikasi di laptop dengan data uji buatan (2 pasien, 3 kunjungan, tindakan, 2 resep,
2 racikan, 1 bahan, 2 followup termasuk satu `NO_ANSWER`):

| | |
|---|---|
| 10 dataset dijalankan | semua menghasilkan baris, nol error |
| Pagar identitas (dua arah) | 5 kolom identitas disisipkan → ditolak semua |
| Pagar uang (dua arah) | 5 kolom uang disisipkan → ditolak semua; 10 dataset nyata lolos |
| `cek_clinical_pack` | **48 lulus, 1 gagal** |

Satu kegagalan itu `BACKUP_RECIPIENT` tidak ada di laptop — kunci backup memang hanya
di desktop (CLAUDE.md §6). **Konsekuensinya: ekspor paket klinis BELUM pernah dijalankan
ujung-ke-ujung dengan Tahap B** — ZIP + enkripsi age + `cek_paket_klinis_keluar` masih
harus dijalankan di desktop sebelum ini dianggap tuntas.

⚠ Data uji (`no_rm` A-T901/A-T902, nama berawalan "UJI … Tahap B") sengaja **ditinggal**
di DB laptop supaya Tahap B bisa diuji ulang. Jangan dipakai di mesin lain.
