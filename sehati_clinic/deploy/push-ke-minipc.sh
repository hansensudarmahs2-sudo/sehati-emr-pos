#!/usr/bin/env bash
# Kirim kode dev -> mini PC klinik. Dijalankan DARI DESKTOP (WSL), bukan di mini PC.
#
#   ./deploy/push-ke-minipc.sh          # dry-run (default, aman)
#   ./deploy/push-ke-minipc.sh --jalan  # benar-benar mengirim
#
# KENAPA SKRIP, BUKAN PERINTAH YANG DIKETIK ULANG
# ------------------------------------------------
# Daftar --exclude yang diketik ulang setiap deploy selalu bocor. Terbukti
# 2026-09-30: .pytest_cache/, .ruff_cache/, logs/pip_audit/ dan outputs/ nyaris
# terkirim ke mesin klinik hanya karena tidak ada di perintah yang diketik.
# Daftarnya sekarang hidup di satu tempat dan ikut ter-review saat berubah.
#
# --checksum WAJIB. Tanpa itu rsync membandingkan mtime, dan sesudah riwayat git
# pernah ditulis ulang (purge PHI 2026-09-27) SELURUH pohon terlihat "berubah" —
# dry-run jadi tak bisa dipakai menilai apa pun.
set -euo pipefail

TUJUAN="joderma-jemur@joderma-jemur:/srv/sehati/"
ASAL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/"

# Yang TIDAK boleh ikut ke mesin klinik, beserta alasannya:
KECUALI=(
  ".env"              # rahasia; mini PC punya .env sendiri yang BEDA
  "*.sql"             # dump bisa memuat PHI
  "backups/"          # backup mini PC ada di sana, jangan ditimpa dari dev
  ".venv/"            # virtualenv desktop, arsitektur/paths beda
  "__pycache__/"
  "*.pyc"
  "exports/"          # hasil export bisa memuat data pasien
  "outputs/"          # sama
  "uji_ui_log/"       # laporan jejak uji UI (scripts/jejak_uji_ui.py) — isi DB DEV,
                      # memuat nama staf/pasien uji. Diabaikan git, tapi rsync tidak
                      # membaca .gitignore: nyaris terkirim 2026-10-05.
  "static/uploads/"   # unggahan (logo klinik) milik MINI PC. Dengan --delete, logo
                      # yang diganti staf di sana akan ditimpa/dihapus versi desktop.
  "logs/"             # log dev tidak berarti di sana & bisa memuat jejak
  ".pytest_cache/"    # cache alat, sampah di produksi
  ".ruff_cache/"
  ".mypy_cache/"
  "node_modules/"
  "compose.laptop.yml"  # override Docker khusus laptop. Compose tidak memuatnya
                        # otomatis, jadi kehadirannya di mini PC tidak berbahaya —
                        # tapi berkas dev tidak punya urusan di mesin klinik.
)

ARGS=(-av --checksum --delete)
for k in "${KECUALI[@]}"; do ARGS+=(--exclude "$k"); done

if [[ "${1:-}" == "--jalan" ]]; then
  echo "[push] MENGIRIM SUNGGUHAN -> $TUJUAN"
else
  ARGS+=(-n)
  echo "[push] DRY-RUN (tambahkan --jalan untuk benar-benar mengirim)"
fi

echo "[push] asal  : $ASAL"
echo "[push] tujuan: $TUJUAN"
echo
rsync "${ARGS[@]}" "$ASAL" "$TUJUAN"
echo
if [[ "${1:-}" == "--jalan" ]]; then
  echo "[push] SELESAI. Langkah berikutnya DI MINI PC:"
  echo "       cd /srv/sehati && docker compose up -d --build"
  echo "       (entrypoint menjalankan 'alembic upgrade head' otomatis)"
else
  echo "[push] Periksa daftar di atas. Baris bertanda 'deleting' = berkas akan"
  echo "       HILANG di mini PC — pastikan itu memang yang diinginkan."
fi
