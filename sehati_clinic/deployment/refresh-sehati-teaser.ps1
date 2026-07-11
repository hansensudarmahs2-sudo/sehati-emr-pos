# ============================================================
#  refresh-sehati-teaser.ps1
#  Auto-refresh portproxy Tailscale -> WSL untuk teaser Sehati.
#  Jalankan sbg ADMINISTRATOR tiap kali menyalakan teaser
#  (IP WSL berubah tiap WSL di-restart).
#  Klik kanan > Run with PowerShell (as Admin), atau:
#     powershell -ExecutionPolicy Bypass -File .\refresh-sehati-teaser.ps1
# ============================================================

$TailscaleIP = "100.122.33.115"   # IP Tailscale desktop ini (cek: tailscale ip -4)
$Port        = 8000               # port uvicorn Sehati

# --- 0. Pastikan dijalankan sebagai Administrator ---
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()`
          ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "HARUS dijalankan sebagai Administrator (netsh & firewall butuh admin)." -ForegroundColor Red
    exit 1
}

# --- 1. Ambil IP WSL saat ini ---
$wslRaw = (wsl hostname -I).Trim()
$WslIP  = ($wslRaw -split '\s+')[0]
if ([string]::IsNullOrWhiteSpace($WslIP)) {
    Write-Host "GAGAL: WSL belum jalan / tak dapat IP. Nyalakan WSL dulu (buka Ubuntu)." -ForegroundColor Red
    exit 1
}
Write-Host "IP WSL       : $WslIP"
Write-Host "IP Tailscale : $TailscaleIP"

# --- 2. Perbarui portproxy (hapus lama -> tambah baru) ---
netsh interface portproxy delete v4tov4 listenaddress=$TailscaleIP listenport=$Port 2>$null | Out-Null
netsh interface portproxy add    v4tov4 listenaddress=$TailscaleIP listenport=$Port connectaddress=$WslIP connectport=$Port

# --- 3. Pastikan aturan firewall ada (buat sekali) ---
$ruleName = "Sehati-teaser-$Port"
if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow `
        -Protocol TCP -LocalPort $Port | Out-Null
    Write-Host "Aturan firewall '$ruleName' dibuat."
}

# --- 4. Ringkasan ---
Write-Host "`nPortproxy aktif:" -ForegroundColor Green
netsh interface portproxy show v4tov4
Write-Host "`nSiap. Dari device (Tailscale ON): " -NoNewline
Write-Host "http://$($TailscaleIP):$Port" -ForegroundColor Cyan
Write-Host "Pastikan uvicorn jalan di WSL: uvicorn app.main:app --host 0.0.0.0 --port $Port`n"
