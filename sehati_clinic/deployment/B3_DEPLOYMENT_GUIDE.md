# B3 — Deployment Guide (Server Lokal Klinik)

**Versi:** REFRESH 2026-07-04. Skenario **1 klinik, server Ubuntu native (mini-PC khusus), LAN, HTTP,
tanpa akses remote**. TLS/remote/multi-cabang/eMR-POS mini = fase lanjutan (lihat §Arah Masa Depan).
**Audiens:** dr. Hansen (non-programmer) — langkah demi langkah.
**Prinsip:** sesederhana mungkin, aplikasi mandiri dari internet, auto-pulih saat reboot.

> File config siap-pakai ada di folder ini: `sehati-clinic.service`, `nginx_sehati.conf`, `.env.prod.example`.
> Head migrasi terkini = **20260703_2400** (`alembic upgrade head` harus sampai sini).

---

## Arsitektur Target
```
[PC/Android klinik]  --WiFi/LAN-->  [Router/AP]  --LAN-->  [SERVER Ubuntu]
   browser (HTTP)                                            ├─ uvicorn (FastAPI) :8000  (systemd)
                                                             ├─ nginx :80               (reverse proxy)
                                                             └─ MySQL :3306
```
- Server IP statis (mis. `192.168.1.10`). Staf akses `http://192.168.1.10`.
- Tidak ada koneksi internet→server. Internet di sisi client tidak wajib untuk operasi inti.

---

## B3.1 — Self-host Aset Frontend  ✅ SUDAH SELESAI (DEC-073)
Tailwind/HTMX/Tom Select sudah lokal (`static/vendor/` + `static/css/app.css`, `build_tailwind.sh`).
**Aksi saat deploy:** cukup VERIFIKASI — putus internet, buka app → harus normal (bagian checklist).

## B3.2 — File `.env` Produksi
Salin `deployment/.env.prod.example` → `/opt/sehati_clinic/.env`, isi nilai asli.
- **`APP_DEBUG=false` WAJIB** — boot-guard MENOLAK start bila `true` di production (DEC-093).
- **`JWT_SECRET_KEY`** WAJIB acak ≥32 char — boot-guard tolak default/pendek (A6).
  `python3 -c "import secrets; print(secrets.token_urlsafe(64))"`
- **`COOKIE_SECURE=false`** benar untuk HTTP LAN (kalau true di HTTP → login gagal). HTTPS nanti → true.

## B3.3 — uvicorn jadi Service systemd  🔴 WAJIB
Pakai `deployment/sehati-clinic.service`:
```bash
sudo cp deployment/sehati-clinic.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sehati-clinic
sudo systemctl status sehati-clinic
```
Auto-nyala saat boot + auto-restart saat crash (dengan batas restart-loop).

## B3.4 — nginx Reverse Proxy  (disarankan)
Pakai `deployment/nginx_sehati.conf` (staf cukup ketik `http://IP` tanpa `:8000`; statis cepat).
```bash
sudo cp deployment/nginx_sehati.conf /etc/nginx/sites-available/sehati
sudo ln -s /etc/nginx/sites-available/sehati /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```
> `X-Forwarded-For` di conf itu PENTING: rate-limit login per-IP + (kelak) resolusi klinik-per-IP multi-cabang.

## B3.5 — IP Statis Server + Cara Akses
- Reservasi DHCP di router (MAC server → selalu `192.168.1.10`) — paling mudah. Atau set statis di OS.
- Staf: browser → `http://192.168.1.10`. Android: harus WiFi klinik (bukan data seluler).
- (Opsional) nama mudah via DNS router: `http://erm.klinik`.

## B3.6 — MySQL Produksi + Least-Privilege
Tuning (`/etc/mysql/mysql.conf.d/mysqld.cnf`):
```ini
[mysqld]
wait_timeout = 600            # >280s, cegah "Lost connection" (DEC-036/B-002)
max_connections = 100
innodb_buffer_pool_size = 512M   # sesuaikan RAM
```
```bash
sudo systemctl enable --now mysql
```
**Least-privilege (V1.2):** user app `klinik_prod` cukup `SELECT,INSERT,UPDATE,DELETE` di `db_sehati`
(bukan ALL PRIVILEGES). Migrasi/DDL pakai user admin terpisah saat upgrade.
**(Opsional, V7.3.1 audit immutable):** cabut `UPDATE,DELETE` `klinik_prod` di tabel `audit_log`.

## B3.7 — Backup Otomatis + Offsite  🔴 WAJIB
- `backups/backup.sh` (mysqldump + uploads + source) — jadwalkan harian:
```bash
sudo crontab -e
0 23 * * * /opt/sehati_clinic/backups/backup.sh
```
- **Offsite:** rutin copy backup ke drive eksternal/NAS/flashdisk. 1 server = 1 titik gagal.
- **Tes restore** ≥1× di DB staging (`backups/restore.sh`). Lihat `backups/README.md`.

## B3.8 — Upgrade & Rollback
**Upgrade:** stop service → backup DB → deploy kode baru → `alembic upgrade head` (ke 20260703_2400+) →
start → cek status. **Rollback:** stop → restore DB backup → kembalikan kode versi lama (git tag) → start.

## B3.9 — SETUP DATA AWAL (sebelum operasional)  🆕
Setelah app jalan + `alembic upgrade head`, login Owner lalu isi via UI:
1. **Profil Klinik** (Settings): nama, alamat, No. **SIA**, logo/mini-logo, footer nota, default paper,
   **rm_prefix**, **Lead Time + Cadangan** (stok minimal dinamis).
2. **Apoteker + SIPA** (Profil Klinik) — WAJIB minimal 1 (dipakai PO & Retur).
3. **Master**: Distributor, **Lokasi Pengiriman**, Produk/Treatment/Bahan, Membership.
4. **Staf & role** (Owner/FO/Dokter/Perawat/Kasir/Apoteker/Purchasing) + password/PIN produksi.
5. **Reset data test / clean slate** bila DB masih berisi data uji.

## B3.10 — Checklist Pra-Launch + Smoke Test Final
- [ ] Reboot server → app auto-nyala (tes cabut-colok listrik).
- [ ] Semua role login OK.
- [ ] Alur klinis penuh: daftar → SOAP → tindakan → **bayar → cetak nota** (A5 & thermal di printer asli).
- [ ] **Audit akses-baca**: buka rekam medis → muncul di Reports → Audit Log (filter tabel=pasien).
- [ ] **Pengadaan**: buat PO (termin/apoteker/SIA) → approve → cetak PO → **Terima Barang** (parsial +
      total ditagih/diskon terbalik) → **cetak Faktur (Finance & Inventory)** → lot & stok update.
- [ ] **Retur**: buat → approve (lot terpotong) → input Nota (tukar→lot / refund) → cetak.
- [ ] **Opname per-batch** RETAIL: hitung 1 batch → approve → stok/lot konsisten.
- [ ] **Stok minimal dinamis**: alert dashboard + Suggested Order pakai ambang efektif.
- [ ] **Komisi**: bayar tindakan → komisi tercatat; laporan komisi tampil.
- [ ] **Tutup Kasir** + Rekap Harian jalan.
- [ ] App tampil normal saat **internet DIPUTUS** (verifikasi B3.1).
- [ ] Backup harian jalan + file muncul; **tes restore** berhasil.
- [ ] IP statis terkonfirmasi; semua workstation bisa akses.

---

## Postur Keamanan (kondisi go-live LAN)
**Sudah aman:** SQLi (parameterized), XSS (Jinja autoescape), CSRF (middleware), rate-limit login,
bcrypt-12, role dari DB tiap request, boot-guard (JWT + APP_DEBUG), security headers dasar
(nosniff/X-Frame-Options/Referrer-Policy, pure-ASGI — B-031), **audit akses-baca** (DEC-096).
**Ditunda sampai TLS/remote/cloud** (aman selama LAN terisolasi): TLS (V9), CSP/HSTS, enkripsi at-rest,
2FA, idle-timeout, password ≥12. Lihat `AUDIT_ASVS_SEHATI_2026-07-03.md` + `_CATATAN_TINDAK_LANJUT`.

## Arah Masa Depan (JANGAN diaktifkan di go-live LAN ini)
- **Remote / multi-cabang**: 1 DB pusat + resolusi klinik via IP/subnet (opsi b) → **TLS WAJIB**.
  Lihat `MASTER_KLINIK_MODULE_DESIGN §9`.
- **eMR-POS mini (contingency cabang) + re-sync**: lihat `EMRPOS_MINI_CONTINGENCY_DESIGN.md` (belum dibangun).
- **Stok RETAIL per-cabang + lot per-cabang**: prasyarat multi-cabang (belum; 1 klinik tak perlu).

## Estimasi Effort & Pembagian
~6-9 jam. Inti wajib: B3.3 (systemd), B3.7 (backup), B3.9 (setup data).
- **Sudah disiapkan (file/kode):** B3.1 (self-host, DEC-073), config `.service`/`nginx.conf`/`.env.prod.example`, guide ini.
- **Di server klinik (Bapak/teknisi):** install service, IP statis, tuning+grant MySQL, cron backup, setup data, smoke test fisik.

---

## Lampiran A — WSL2 & Teaser Pre-Live Test

### A1. Desktop Windows+WSL sekarang → server TEASER (uji coba, bukan produksi)
1. **Jalankan app** di WSL (Ubuntu):
   ```bash
   cd ~/sehati_clinic && source .venv/bin/activate
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
   Untuk teaser, pakai `.env` dgn `APP_ENV=development` (hindari boot-guard produksi) atau `.env` staging lengkap.
2. **Cari IP:** WSL → `ip addr show eth0 | grep 'inet '` (mis. `172.x.x.x`). LAN Windows → `ipconfig` (mis. `192.168.1.50`).
3. **PowerShell Windows (Run as Administrator)** — teruskan port host→WSL + buka firewall:
   ```powershell
   netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=8000 connectaddress=<IP-WSL> connectport=8000
   netsh advfirewall firewall add rule name="Sehati8000" dir=in action=allow protocol=TCP localport=8000
   ```
4. **Device lain** di WiFi klinik → buka `http://<IP-LAN-Windows>:8000`.
5. **(Windows 11) alternatif tanpa portproxy:** file `C:\Users\<user>\.wslconfig`:
   ```ini
   [wsl2]
   networkingMode=mirrored
   ```
   `wsl --shutdown` → WSL berbagi IP host; device LAN langsung `http://<IP-Windows>:8000`.
> Catatan: IP WSL bisa berubah tiap restart WSL → ulangi step 3, atau pakai mirrored mode. TEASER only.

### A2. Kalau KELAK produksi pakai WSL2 (bukan Ubuntu native)
- **Aktifkan systemd:** `/etc/wsl.conf` →
  ```ini
  [boot]
  systemd=true
  ```
  lalu `wsl --shutdown` (dari Windows). Setelah itu `sehati-clinic.service` jalan normal.
- **Auto-start saat Windows boot:** buat Task Scheduler Windows (trigger: At log on / At startup) yang menjalankan
  `wsl -d Ubuntu -u root systemctl start sehati-clinic` (atau cukup `wsl` agar distro + systemd nyala).
- **Reachability LAN:** sama seperti A1 (portproxy/firewall atau mirrored networking).
- File `sehati-clinic.service` / `nginx_sehati.conf` / `.env` **TIDAK berubah** — hanya cara "membungkus" boot & jaringan yang beda.
> Native Ubuntu tetap lebih sederhana & andal untuk produksi. WSL2 oke untuk teaser / sementara.

---

## Lampiran B — Teaser REMOTE (PC rumah → diakses dari klinik, di luar LAN)

**Konteks:** server = desktop rumah (WSL), klien = klinik (jaringan berbeda / internet). Prinsip: JANGAN
port-forward router yang membuka EMR ke internet publik. Pakai tunnel/overlay + enkripsi. **DATA TEST SAJA.**

### Opsi 1 — Tailscale (REKOMENDASI: privat, terenkripsi, tanpa expose publik)
1. **PC rumah:** install Tailscale (Windows host atau di dalam WSL), login → dapat IP tailnet `100.x.x.x`.
   - Jalankan app: `uvicorn app.main:app --host 0.0.0.0 --port 8000` (WSL).
   - Kalau Tailscale di Windows host: teruskan ke WSL dgn `netsh portproxy` (Lampiran A step 3).
     Kalau Tailscale di dalam WSL: langsung.
2. **Device klinik:** install Tailscale, login akun SAMA → join tailnet.
3. Klinik buka `http://100.x.x.x:8000` (IP tailnet PC rumah). Trafik sudah terenkripsi WireGuard →
   `COOKIE_SECURE=false` OK, tak perlu sertifikat.
4. (Opsional TLS in-tunnel) `tailscale serve` bisa beri HTTPS `*.ts.net`.
> Keunggulan: EMR TIDAK terlihat dari internet publik — hanya device di tailnet-mu. Paling aman utk teaser.

### Opsi 2 — Cloudflare Tunnel (URL HTTPS publik + WAJIB gerbang login)
1. **WSL:** install `cloudflared`. Cepat (URL sementara): `cloudflared tunnel --url http://localhost:8000`
   → dapat `https://<random>.trycloudflare.com`. (Named tunnel + domain sendiri utk yang menetap.)
2. **WAJIB pasang Cloudflare Access** (email/OTP gate) di depan hostname → cegah publik sembarangan buka EMR.
3. Klinik buka URL HTTPS di browser (tanpa instal apa pun). Set `COOKIE_SECURE=true` (akses via HTTPS).
> Lebih praktis (tanpa instal di sisi klien), tapi publik → keamanan bergantung pada Access gate. Wajib.

### Caveat (kedua opsi)
- **Data TEST only** untuk teaser; jangan pasien asli.
- PC rumah harus **nyala + WSL jalan + internet hidup**; mati → klinik tak bisa akses.
- Ini **teaser**, bukan produksi. Produksi tetap sesuai badan panduan (server klinik LAN), dan bila kelak
  remote sungguhan → arsitektur `MASTER_KLINIK §9` (1 DB pusat + TLS + resolusi klinik) & contingency
  `EMRPOS_MINI_CONTINGENCY_DESIGN.md`.

### B.1 — Skrip auto-refresh portproxy (Tailscale sudah di Windows host)
File: `deployment/refresh-sehati-teaser.ps1`. Karena Tailscale jalan di **Windows host** dan app di **WSL**,
portproxy `100.122.33.115:8000 → <IP-WSL>:8000` harus disegarkan tiap WSL restart (IP WSL berubah).
Skrip ini otomatis: ambil IP WSL terkini → perbarui portproxy → pastikan aturan firewall. Jalankan sebagai
Administrator tiap menyalakan teaser. Edit `$TailscaleIP` bila IP tailnet desktop berubah (`tailscale ip -4`).
**Device klien (HP/laptop) WAJIB pasang Tailscale + login akun sama** untuk menjangkau `100.x.x.x`.
