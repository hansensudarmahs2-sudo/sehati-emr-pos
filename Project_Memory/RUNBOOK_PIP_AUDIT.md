# Runbook — Scan Dependensi (pip-audit, ASVS V14.5.2)

**Tujuan:** deteksi kerentanan yang diketahui (CVE/advisory) pada paket Python Sehati, berkala.
**Sifat:** operasional; dijalankan di WSL/server, bukan di CI cloud (belum ada).

## Jalankan manual
```bash
cd /mnt/e/Claude/Projects/sehati-emr-pos/sehati_clinic
source .venv/bin/activate
bash scripts/security_pip_audit.sh
```
- Menampilkan tabel temuan + menyimpan `logs/pip_audit/pip_audit_<stamp>.json`.
- Exit code ≠ 0 = ada kerentanan (berguna untuk penjadwalan/alert).

## Membaca hasil
- **Tidak ada temuan** → aman untuk snapshot ini.
- **Ada temuan** → kolom paket + versi + ID advisory + versi perbaikan. Tindak lanjut:
  1. `pip install -U <paket>` ke versi aman, jalankan `pytest` (regresi).
  2. Kalau upgrade memutus kompatibilitas → catat sebagai risiko + jadwalkan.
  3. Commit perubahan `requirements` bila ada.

## Penjadwalan MINGGUAN

Skrip kini **auto-detect `.venv`** (tak perlu `activate`), menulis `logs/pip_audit/latest.json`,
menyisakan 12 JSON terakhir (retensi), dan **exit 2 bila ADA temuan** (0 = aman, 1 = error) +
menaruh marker `logs/pip_audit/VULN_FOUND`.

### Produksi (Ubuntu) — systemd timer [DIREKOMENDASIKAN]
File siap-pakai: `sehati_clinic/deployment/sehati-pipaudit.service` + `.timer` (jadwal: Senin 03:00, `Persistent=true`).
```bash
sudo cp deployment/sehati-pipaudit.service deployment/sehati-pipaudit.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sehati-pipaudit.timer
systemctl list-timers 'sehati-pipaudit*'     # cek jadwal berikutnya
sudo systemctl start sehati-pipaudit.service # jalankan sekali sekarang (uji)
systemctl status sehati-pipaudit.service     # hasil run terakhir (exit 2 = ada temuan)
journalctl -u sehati-pipaudit.service        # log detail
```
Monitoring cepat: cek keberadaan file `logs/pip_audit/VULN_FOUND` (ada = perlu tindak lanjut).
> Catatan: unit memakai `User=sehati`, `WorkingDirectory=/opt/sehati_clinic` — samakan dengan sehati-clinic.service.
> Karena exit 2 saat ada temuan, `systemctl status` akan menampilkan `failed` — itu SENGAJA (sinyal alert).

### Alternatif cron
`0 3 * * 1  cd /opt/sehati_clinic && bash scripts/security_pip_audit.sh >> logs/pip_audit/cron.log 2>&1`

### Dev Windows (Task Scheduler)
Program `wsl.exe`, Arguments:
`-d Ubuntu bash -lc "cd /mnt/e/Claude/Projects/sehati-emr-pos/sehati_clinic && bash scripts/security_pip_audit.sh"`
(tak perlu `source activate` lagi — skrip pakai `.venv` otomatis).

## Catatan
- Butuh koneksi internet (ambil database advisory).
- Bukan pengganti update rutin; hanya alat deteksi.
- Bila kelak ada CI, pindahkan langkah ini ke pipeline (gagalkan build saat `--strict`).
