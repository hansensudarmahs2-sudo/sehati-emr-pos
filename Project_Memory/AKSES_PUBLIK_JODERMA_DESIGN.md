# Akses Publik Sehati eMR-POS via joderma.id — Design & Runbook

**Dibuat:** 2026-09-17 · **Sifat:** rencana arsitektur + runbook (belum dieksekusi).
**Tujuan:** akses EMR dari luar klinik lewat URL cantik (mis. `emr.joderma.id`) **tanpa**
mengetik alamat Tailscale `.ts.net`, dan **tanpa** klien perlu memasang Tailscale.

## Keputusan (dr. Hansen, 2026-09-17)
- **Model akses:** Privat + URL cantik — URL publik boleh, tapi hanya perangkat/staf
  berwenang yang boleh sampai ke halaman login (lapisan auth di depan app).
- **Domain:** `joderma.id` = domain internet resmi, DNS dikelola sendiri.
- **Arah terpilih:** **Cloudflare Tunnel + Cloudflare Access**, pakai **subdomain**
  (`emr.joderma.id`) — BUKAN subpath (`joderma.id/core-apps`).

## Kenapa subdomain, bukan subpath
Subpath (`/core-apps`) menuntut penyetelan ulang `root_path` FastAPI, path cookie, dan path
aset statis; lebih buruk lagi Sehati & Photodex akan berbagi domain → **cookie bisa bentrok**.
Subdomain per-app (`emr.joderma.id`, `photodex.joderma.id`) bersih & terisolasi.
Kesan "satu pintu" bisa dibuat via landing statis `apps.joderma.id` berisi tombol ke tiap app.

## Kenapa Cloudflare Tunnel + Access (vs alternatif)
| Opsi | URL cantik | Klien tanpa Tailscale | Privat (PHI) | Buka port router | Rawat infra |
|------|:---:|:---:|:---:|:---:|:---:|
| **Cloudflare Tunnel + Access** ✅ | ✅ | ✅ | ✅ (Access login) | ❌ tidak perlu | rendah |
| Split-DNS di atas Tailscale | ✅ | ❌ (butuh Tailscale) | ✅ (tailnet) | ❌ | rendah |
| VPS reverse-proxy + WireGuard | ✅ | ✅ | ✅ | ❌ | sedang (ada VPS) |
| Port-forward + nginx + Certbot | ✅ | ✅ | ⚠️ ekspos IP asli + permukaan penuh | ✅ perlu | sedang |
| Tailscale Funnel | ⚠️ nama `.ts.net` | ✅ | ⚠️ publik | ❌ | rendah |

Tunnel+Access menang: nama cantik, klien cukup browser+login, tetap privat, tanpa buka port,
IP klinik tersembunyi, TLS gratis otomatis.

## Prinsip yang dijaga
- **Aditif & reversibel.** `cloudflared` = service/container sendiri. Stack & nginx **Photodex
  tidak disentuh**. Jalur Tailscale lama tetap ada sebagai fallback.
- **PHI:** Access = lapisan auth DI DEPAN halaman login Sehati. "URL publik" ≠ "app terbuka".
- **LAN tetap jalan:** `joderma.id` internal (nginx Photodex di LAN) tak terganggu; subdomain
  publik baru terpisah dari resolusi LAN.

## Prasyarat
1. Domain `joderma.id` dipindah ke **Cloudflare DNS** (ganti nameserver di registrar).
   Record LAN internal tetap dikelola DNS lokal klinik — tidak bentrok.
2. Akun Cloudflare + Zero Trust (Access) aktif (tier gratis cukup untuk tim kecil).
3. Akses shell ke mini PC `joderma-jemur`.

## Runbook eksekusi (di server, oleh dr. Hansen/teknisi)
1. **DNS:** pindahkan `joderma.id` ke Cloudflare (nameserver). Verifikasi zona aktif.
2. **Install cloudflared** di mini PC (paket resmi Cloudflare untuk Ubuntu).
3. **Buat tunnel:** `cloudflared tunnel login` → `cloudflared tunnel create sehati`
   → route DNS: `cloudflared tunnel route dns sehati emr.joderma.id`.
4. **Config ingress** (`~/.cloudflared/config.yml`):
   `emr.joderma.id` → `http://127.0.0.1:8001` (service catch-all `http_status:404`).
   Jalankan sebagai service: `cloudflared service install` (auto-start).
5. **Cloudflare Access** (Zero Trust → Access → Applications):
   - Tambah aplikasi self-hosted `emr.joderma.id`.
   - Identity provider: One-time PIN (email) ATAU Google — lihat "Keputusan terbuka".
   - Policy: Allow — hanya daftar email staf berwenang.
   - Session duration wajar (mis. 24 jam) sejalan dgn idle-timeout app (60 mnt).
6. **Sisi Sehati:** pastikan `COOKIE_SECURE=true` (sudah). Bila ada validasi Host/allowed-host
   atau TRUSTED_PROXIES, tambahkan `emr.joderma.id` / rentang Cloudflare bila perlu.
   (App tetap bind 127.0.0.1:8001; cloudflared yang meneruskan.)
7. **CSP/HSTS (item S1 backlog):** setelah HTTPS stabil, aktifkan HSTS + CSP — sekalian.
8. **Smoke test:** dari HP di jaringan seluler (WiFi klinik OFF, Tailscale OFF) → buka
   `emr.joderma.id` → prompt Access → login → halaman login Sehati → login → dashboard.
9. **Fallback:** jalur Tailscale `:8443` lama tetap dibiarkan hidup sampai jalur baru terbukti.

## Keputusan terbuka (sebelum eksekusi)
- **Nama subdomain:** `emr.` / `core.` / `apps.` (default usulan: `emr.joderma.id`).
- **Identity provider Access:** email OTP (paling simpel, tanpa akun Google) vs Google
  (lebih mulus kalau staf sudah pakai akun Google klinik).
- **Photodex ikut?** dipindah ke pola tunnel yang sama (`photodex.joderma.id`) atau tetap
  Tailscale/LAN. (Rekomendasi: kerjakan Sehati dulu, Photodex menyusul bila lancar.)
- **Landing `apps.joderma.id`?** halaman statis berisi tombol ke tiap app (opsional, kosmetik).

## Catatan keamanan
- Access hanya melindungi hostname yang didaftarkan — pastikan **tidak ada** hostname tunnel
  lain yang bocor tanpa policy.
- Simpan kredensial tunnel (`~/.cloudflared/*.json`) seperti secret — jangan commit/sync.
- Tunnel = jalur keluar dari mini PC; tidak membuka port masuk, tapi tetap catat di inventori
  aset & backup config.
- Ini tidak menggantikan hardening app (rate-limit, CSRF, bcrypt, boot-guard) — melengkapinya.

## Status
RENCANA. Eksekusi menunggu keputusan terbuka di atas + jadwal (idealnya saat klinik tutup).
Referensi: DEPLOY_MINIPC_SEHATI_DESIGN.md, ARSITEKTUR_EKOSISTEM_DEPLOYMENT.md,
BACKLOG_TERKUBUR_2026-09.md (S1 CSP/HSTS).

---

## Update 2026-09-17 — Status DNS Cloudflare terkonfirmasi
Screenshot dashboard Cloudflare `joderma.id`:
- Zona **aktif di Cloudflare** (3/200 record). → **Prasyarat #1 (DNS di Cloudflare) SELESAI.**
- Record eksisting (biarkan, jangan disentuh):
  - `joderma.id` A → 216.198.79.1 (DNS only) — tak relevan ke EMR.
  - `photodex.joderma.id` A → 192.168.1.10 (DNS only, reserved/private IP) — jalur LAN Photodex.
    Catatan: membocorkan IP internal ke publik (harmless, IP privat tak terjangkau luar); rapikan opsional.
  - `poeguizu…` CNAME → gv-…dv.googlehosted.com — verifikasi domain Google.
- Rekomendasi Cloudflare (www record; MX+SPF/DKIM/DMARC) = **tidak wajib** untuk akses EMR.
  MX/SPF dst hanya bila mau email `@joderma.id`. Bukan blocker.

**Implikasi runbook:**
- Langkah 1 (pindah DNS) sudah beres → mulai dari Langkah 2 (install cloudflared).
- Langkah 3: `cloudflared tunnel route dns sehati emr.joderma.id` akan **membuat CNAME emr
  Proxied (oranye) otomatis** — JANGAN buat record emr manual, dan pastikan hasilnya Proxied
  (bukan "DNS only"), syarat agar Access + tunnel jalan.
- Saat Photodex menyusul ke akses luar: tambah hostname tunnel terpisah (mis. `app.joderma.id`
  atau `px.joderma.id`) — jangan pakai ulang record LAN `photodex.joderma.id` yang DNS-only.

---

## Keputusan final (2026-09-17) + runbook copy-paste
- **Hostname:** `emr.joderma.id`
- **Access login:** One-time PIN (Email OTP)
- **cloudflared:** dipasang di HOST mini PC (bukan di compose Sehati/Photodex) → aditif.
- Sehati tetap bind `127.0.0.1:8001`; cloudflared di host bisa menjangkaunya.

### Langkah di mini PC (Ubuntu)
```bash
# 1. Install cloudflared (repo resmi Cloudflare)
sudo mkdir -p /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update && sudo apt-get install -y cloudflared

# 2. Login (buka browser, pilih zona joderma.id)
cloudflared tunnel login

# 3. Buat tunnel + catat UUID + path credentials (~/.cloudflared/<UUID>.json)
cloudflared tunnel create sehati

# 4. Route DNS → otomatis bikin CNAME emr (Proxied/oranye)
cloudflared tunnel route dns sehati emr.joderma.id
```

### Config ~/.cloudflared/config.yml  (ganti <UUID> & <user>)
```yaml
tunnel: <UUID>
credentials-file: /home/<user>/.cloudflared/<UUID>.json
ingress:
  - hostname: emr.joderma.id
    service: http://127.0.0.1:8001
  - service: http_status:404
```

### Jalankan + pasang service
```bash
cloudflared tunnel run sehati          # uji foreground dulu (Ctrl-C bila OK)
sudo cloudflared service install        # pakai config.yml di atas
sudo systemctl enable --now cloudflared
systemctl status cloudflared
```

### Cloudflare Zero Trust → Access (di dashboard)
1. Zero Trust → Access → Applications → Add application → Self-hosted.
2. Application domain: `emr` . `joderma.id`. Session: 24h.
3. Policy: Action=Allow, Include → **Emails** → daftar email staf berwenang.
4. Login methods: pastikan **One-time PIN** aktif (Settings → Authentication).

### Sisi Sehati (cek, kemungkinan sudah oke)
- `COOKIE_SECURE=true` (sudah). `TRUSTED_PROXIES` sudah memuat `127.0.0.1` → app melihat
  cloudflared sebagai proxy tepercaya, XFF client IP benar. Tak perlu ubah kecuali ada
  allowed-host ketat → tambah `emr.joderma.id`.

### Smoke test
- HP di data seluler (WiFi klinik OFF, Tailscale OFF) → `https://emr.joderma.id`
  → prompt Access (email → PIN) → halaman login Sehati → login → dashboard.
- Jalur Tailscale `:8443` DIBIARKAN hidup sebagai fallback sampai jalur baru terbukti.

---

## STATUS: LIVE (2026-09-17)
Terpasang & terverifikasi dari rumah (via SSH Tailscale ke mini PC):
- **Tunnel** `sehati` → `emr.joderma.id` → `http://127.0.0.1:8001`. Precheck sehat (QUIC, 4 koneksi).
- **cloudflared service**: `/etc/systemd/system/cloudflared.service`, `active (running)` + **enabled**
  (auto-start saat reboot). Config: `/etc/cloudflared/config.yml`. Creds: `~/.cloudflared/<UUID>.json`.
- **Cloudflare account (dashboard):** `hansensudarma.hs2@gmail.com` (login via Google). Team: `rough-frog-30ff`.
- **Access (Zero Trust Free)**: aplikasi self-hosted `emr.joderma.id`, policy `Staf` Allow →
  **Include: Emails** = email pemilik saja (email lain ditolak — terverifikasi). Login method: One-time PIN.
  Session 24 jam. Just-in-time OFF.
- **Verifikasi:** email tak terdaftar (sehatisoftwaredevelopment@) → ditolak di gerbang = allowlist bekerja.
- **Fallback tetap hidup:** LAN (di klinik) + Tailscale `:8443`. Access hanya di jalur `emr.joderma.id`.

### Catatan operasional / sisa
- **Tambah email staf** ke policy `Staf` (Include→Emails) saat perlu akses remote; atau nanti pakai
  "Emails ending in @joderma.id" bila email domain klinik diaktifkan (Cloudflare Email Routing).
- **Secret:** `~/.cloudflared/*.json` = kredensial tunnel — jangan commit/sync.
- **Pelajaran UI:** halaman "Sign in to Cloudflare" (Google/Apple/GitHub + password) = login AKUN
  dashboard, BEDA dari gerbang Access app (nama tim + email → kirim PIN). Jangan tertukar.
- **Lanjutan (backlog S1):** kini HTTPS stabil → CSP/HSTS layak diaktifkan.
- Free plan: no SLA (praktik andal); 50 user; log 24 jam. Cukup untuk sekarang.
