# Backup & Restore Sehati (Docker) — mini PC

Tiga skrip di `deploy/`, dijalankan dari `/srv/sehati`:

| Skrip | Fungsi | Sifat |
|---|---|---|
| `backup.sh` | Dump MySQL (via container) + arsip uploads → `backups/`. Enkripsi age opsional. Retensi N terbaru. | Aman, kapan saja |
| `restore-verify.sh` | Uji backup terbaru: restore ke DB scratch `db_sehati_verify`, bandingkan jumlah tabel & baris dgn live, lalu hapus scratch. | **NON-destruktif** (live aman) |
| `restore.sh` | Pemulihan bencana: timpa DB live dari sebuah backup (buat safety-backup + konfirmasi 'RESTORE' dulu). | **DESTRUKTIF** — hanya saat perlu |

## Uji rutin (disarankan malam saat klinik tutup)
```bash
cd /srv/sehati
bash deploy/backup.sh            # buat backup
bash deploy/restore-verify.sh    # uji backup terbaru bisa di-restore (tanpa sentuh live)
```
Lulus = "✅ LULUS — angka cocok".

## Enkripsi (WAJIB sebelum ada data pasien nyata)
Backup berisi hash password staf & (nanti) data pasien → enkripsi dengan `age`.
Kunci dibuat di mesin LAIN (mis. desktop), **kunci privat JANGAN di mini PC**:
```bash
# [desktop]  buat pasangan kunci, simpan file ini aman + salinan offline
age-keygen -o ~/sehati-backup.key
grep 'public key' ~/sehati-backup.key      # age1.... -> salin
```
Lalu di mini PC, isi `.env`:
```
BACKUP_RECIPIENT=age1....     # kunci PUBLIK
```
Setelah itu `backup.sh` otomatis menghasilkan `*.sql.gz.age` (terenkripsi).
Restore dari `.age` perlu kunci privat (dekripsi di mesin tepercaya):
```
age -d -i ~/sehati-backup.key -o out.sql.gz backups/sehati_db_XXXX.sql.gz.age
```

## Jadwal harian (cron)
```bash
crontab -e
# backup tiap hari 22:30
30 22 * * *  cd /srv/sehati && bash deploy/backup.sh >> backups/backup_cron.log 2>&1
```

## Catatan
- Backup DB pakai user root container (via $MYSQL_ROOT_PASSWORD) — dump lengkap.
- Off-site (salin arsip ke luar gedung) = celah yang masih terbuka, susulkan.
