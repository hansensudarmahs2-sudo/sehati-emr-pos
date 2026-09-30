#!/usr/bin/env bash
# Gerbang PHI — tolak berkas berisi data pasien / rahasia yang TERLACAK git.
#
# LATAR: 2026-09-29 ditemukan 778 baris kunjungan (nama pasien, no. RM, keluhan) dan
# ~2.050 baris komisi (nama pasien + poliklinik "Kulit & Kelamin") sudah ter-commit dan
# ter-push ke GitHub sejak commit pertama.
#
# Gerbang lama (D4) memakai pola: \.env$ | backup.*\.(sql|zip) | /backups/ | medis
# KETIGA berkas di atas LOLOS dari pola itu — `12_medical_soap_raw.csv` memakai kata
# "medical", bukan "medis". Gerbang yang tidak pernah gagal saat diuji pada kebocoran
# nyata hanya memberi rasa aman palsu. Karena itu pemeriksa ini bekerja dua lapis:
#
#   Lapis 1 — NAMA berkas mencurigakan (murah, menangkap pola yang sudah dikenal)
#   Lapis 2 — ISI berkas memuat kolom identitas pasien (menangkap yang namanya polos)
#
# Lapis 2 yang penting: berkas bernama `laporan_q3.csv` pun ketahuan kalau isinya
# berkolom nama_pasien/no_rm.
#
# Pakai:  bash scripts/cek_phi_tracked.sh
# Pasang sebagai hook:  ln -sf ../../scripts/cek_phi_tracked.sh .git/hooks/pre-commit
#
# Keluar 0 = bersih, 1 = ada temuan.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1

TEMUAN=0

lapor() {
    printf '  ✗ %-58s %s\n' "$1" "$2"
    TEMUAN=$((TEMUAN + 1))
}

echo "=== Lapis 1: nama berkas mencurigakan ==="
# Termasuk 'medical' DAN 'medis'; exports/; historical_excel; dump; kunci.
# Dua kelompok, karena bahayanya berbeda jenis.
#
# ⚠ `(^|/)` di depan backups?/exports?: versi lama menulis `/backups?/` saja,
#   sehingga folder `exports/` di AKAR repo LOLOS — hanya yang bersarang seperti
#   `sehati_clinic/exports/` yang tertangkap. Ditemukan lewat uji negatif
#   2026-09-30, bukan lewat kejadian nyata.
# KERAS — berbahaya apa pun ekstensinya. TIDAK ADA pengecualian: kunci, dump,
# arsip, folder ekspor. Berkas seperti ini tidak pernah punya alasan sah berada
# di dalam repo.
POLA_NAMA_KERAS='(^|/)\.env$|(^|/)\.env\.|backup.*\.(sql|zip|gz)|(^|/)backups?/|(^|/)exports?/|historical_excel/.*\.(xlsx|xls|csv)|\.pem$|\.key$|id_rsa|\.age$'

# TOPIK — kata yang menandakan berkas DATA, tapi wajar muncul di nama berkas
# KODE dan DOKUMEN. `cek_clinical_pack.py` dan migrasi `..._pasien_pseudonim.py`
# memblokir commit mereka sendiri 2026-09-30 justru karena ini.
POLA_NAMA_TOPIK='medis|medical|soap_raw|visits_raw|patient|pasien_raw|clinical_pack|clinical_.*\.(csv|json)|pseudonim|pseudonym|.*_map\.(csv|json|sql)|pid_map'

# Templat SENGAJA dilacak — `.env.example` dkk berisi nama variabel, bukan nilainya.
# Gerbang yang berteriak untuk hal wajar akan diabaikan orang, dan gerbang yang
# diabaikan sama saja dengan tidak ada.
POLA_KECUALI='\.(example|sample|template|dist)$|\.example\.|README|\.md$'

# Berkas SUMBER: dikecualikan dari POLA_NAMA_TOPIK saja, TIDAK dari POLA_NAMA_KERAS.
# `.sql` SENGAJA TIDAK ada di sini — dump SQL justru berkas yang paling mungkin
# memuat baris pasien sungguhan.
POLA_SUMBER='\.(md|py|sh|html|j2|css|js)$'

# ⚠ CELAH YANG DITERIMA SADAR: berkas .md/.py/.sh dkk tidak diperiksa lapis 1
# untuk kata TOPIK, dan lapis 2 memang hanya memindai csv/tsv/json/xml. Jadi data
# pasien yang DITEMPEL ke dalam dokumen atau kode TIDAK akan tertangkap. Jangan
# pernah menempel isi tabel pasien ke dokumen atau ke skrip — tulis strukturnya,
# bukan barisnya.
KERAS=$(git ls-files | grep -iE "$POLA_NAMA_KERAS" | grep -ivE "$POLA_KECUALI" || true)
TOPIK=$(git ls-files | grep -iE "$POLA_NAMA_TOPIK" | grep -ivE "$POLA_KECUALI" \
        | grep -ivE "$POLA_SUMBER" || true)
HASIL1=$(printf '%s\n%s\n' "$KERAS" "$TOPIK" | grep -v '^$' || true)
if [ -n "$HASIL1" ]; then
    while IFS= read -r f; do lapor "$f" "nama mencurigakan"; done <<< "$HASIL1"
else
    echo "  ✓ nihil"
fi

echo
echo "=== Lapis 2: isi berkas teks memuat kolom identitas pasien ==="
# Hanya berkas teks tabular/terstruktur, dan hanya HEADER-nya yang dibaca — jangan
# sampai pemeriksa ini sendiri menumpahkan isi PHI ke layar atau ke log CI.
POLA_ISI='nama_pasien|no_rm|nomor_rm|nik_pasien|nomor_ktp|keluhan_utama|anamnesa|diagnosa|pseudonim|pid_map'
ADA2=0
while IFS= read -r f; do
    [ -f "$f" ] || continue
    # Lewati berkas yang memang MENDEFINISIKAN kolom itu (kode, migrasi, model, desain).
    case "$f" in
        *.py|*.sql|*.md|*.html|*.j2|*.txt) continue ;;
    esac
    if head -c 4096 "$f" 2>/dev/null | grep -qiE "$POLA_ISI"; then
        lapor "$f" "header memuat kolom identitas pasien"
        ADA2=1
    fi
done < <(git ls-files -- '*.csv' '*.tsv' '*.json' '*.xml')
[ "$ADA2" -eq 0 ] && echo "  ✓ nihil"

echo
echo "=== Lapis 3: berkas Excel terlacak (isinya tidak bisa dibaca grep) ==="
HASIL3=$(git ls-files -- '*.xlsx' '*.xls' || true)
if [ -n "$HASIL3" ]; then
    echo "  ⚠ periksa MANUAL — grep tidak bisa melihat isi berkas biner:"
    while IFS= read -r f; do echo "      $f"; done <<< "$HASIL3"
    echo "      (daftar produk/tindakan wajar; rincian komisi & data pasien TIDAK)"
else
    echo "  ✓ tidak ada berkas Excel terlacak"
fi

echo
if [ "$TEMUAN" -gt 0 ]; then
    cat <<'PESAN'
GAGAL — ada berkas berisi data pasien/rahasia yang dilacak git.

Cara menanganinya (berkas TETAP ada di disk):
  git rm -r --cached <path>
  echo "<path>" >> .gitignore
  git commit -m "berhenti melacak berkas berisi data pasien"

Kalau berkas itu SUDAH pernah ter-push, menghapusnya hari ini TIDAK cukup — ia masih
bisa diambil dari commit lama. Riwayatnya perlu ditulis ulang; prosedurnya ada di
Project_Memory (housekeeping 2026-09-29), termasuk jebakan filter-repo yang membuang
commit .gitignore-nya.
PESAN
    exit 1
fi
echo "BERSIH — tidak ada berkas PHI yang dilacak git."
exit 0
