# Design Doc — Master Klinik (Registry Identitas)

**Tanggal:** 2026-07-03
**Status:** DRAFT desain — belum ada kode. Untuk review dr. Hansen.
**Pemicu:** (1) No. RM perlu beda per klinik; (2) identitas PO bisa beda dari profil klinik tunggal;
(3) field SIA/SIPA/apoteker (perbaikan PO §B) belum punya rumah. Sejalan dgn arah "1 server → banyak klinik".

---

## 1. Keputusan yang sudah diambil (dr. Hansen, 2026-07-03)

- **Pasien = KOLAM BERSAMA** antar klinik (BUKAN dipartisi). → TIDAK ada multi-tenant isolation
  penuh. Prefix RM hanya "tag cabang" tempat pasien pertama didaftarkan.
- **Registry identitas DULU** — `master_klinik` sebagai daftar entitas klinik. Isolasi query
  per-klinik (id_klinik di semua tabel + scoping + RBAC) DITUNDA (tak dibutuhkan selama kolam bersama).

**Implikasi:** ini pekerjaan **RINGAN–MENENGAH**, bukan rearsitektur. Tidak menyentuh RBAC atau
scoping query. Yang berubah: sumber identitas dokumen (singleton → pilih klinik) + prefix RM per klinik.

---

## 2. Kondisi sekarang (hasil baca kode)

- `master_klinik_config` = **SINGLETON** (`id_config`, 1 baris). Kolom: nama_klinik, no_telepon,
  no_whatsapp, email, website, logo_path, mini_logo_path, footer_text, default_paper_nota/soap,
  ttd_dokter_text, (+ alamat_baris1..3 dipakai template). **Belum ada** no_sia / no_sipa / nama_apoteker.
- **No. RM** = `rm_clinic_prefix` (env, default "A") + `YYMMDD-NNN` → `A-260703-001`
  (`pasien_repo.generate_next_no_rm`, DEC-071a). Satu prefix global untuk semua.
- **0 kolom tenant** di pasien/transaksi/kunjungan/stok → sistem single-tenant murni hari ini.
- Identitas klinik dibaca di banyak titik: `print_service` (nota/PO/SOAP), `pemesanan_service`,
  `auth.py` + `_shared.py` (shell topbar/branding), `kasir*`, `settings.py`.

---

## 3. Desain `master_klinik`

Promosikan singleton → tabel multi-baris. **Migrasi: baris singleton sekarang jadi klinik #1 (default).**

**Tabel `master_klinik`:**

| kolom | tipe | catatan |
|---|---|---|
| id_klinik | PK int | |
| kode_klinik | str(10) unik | mis. "ACN", "CAB2" |
| nama_klinik | str(100) | |
| rm_prefix | str(5) | prefix No. RM klinik ini (gantikan env global) |
| alamat_baris1..3 | str | |
| no_telepon, no_whatsapp, email, website | str | |
| no_sia | str | Surat Izin Apotek (untuk PO) — BARU |
| no_sipa | str | Surat Izin Praktik Apoteker — BARU |
| nama_apoteker | str | penanggung jawab PO — BARU |
| logo_path, mini_logo_path | str | |
| footer_text, ttd_dokter_text | str | |
| default_paper_nota, default_paper_soap | str | |
| is_active | bool | |
| is_default | bool | tepat 1 klinik default (fallback identitas) |
| created_at, updated_at, id_staf_last_edit | | |

**"Provenance ringan" (nullable, TANPA scoping akses):** untuk dokumen yang butuh tahu "klinik mana",
tambah kolom `id_klinik` **nullable** di titik dokumen — BUKAN untuk membatasi akses, hanya jejak:
- `pasien.id_klinik_pendaftaran` — klinik tempat pasien pertama daftar → sumber prefix RM.
- `transaksi.id_klinik` — klinik tempat transaksi/nota dibuat.
- `pemesanan.id_klinik` — klinik penerbit PO (default = default clinic; bisa dipilih saat buat PO).

Semua default ke klinik default bila NULL → aman untuk data lama & 1-klinik.

---

## 4. Keputusan kunci & yang masih TERBUKA (perlu dr. Hansen di review)

1. **Nasib `master_klinik_config`:** rekomendasi = **rename/migrate jadi `master_klinik`** (baris lama
   jadi default), bukan bikin tabel paralel. Config service singleton → CRUD multi-baris.
   → OPEN: setuju promote, atau simpan config lama sbg "default global" + master_klinik terpisah?
2. **RM prefix source:** pindah dari env `rm_clinic_prefix` → `master_klinik.rm_prefix` klinik pendaftaran.
   → OPEN: kalau 1 klinik saja sekarang, cukup default; env dipertahankan sbg fallback saat id_klinik NULL?
3. **Klinik "aktif" per aksi:** karena 1 klinik fisik sekarang → semua default ke klinik default.
   PO: dropdown pilih klinik penerbit (default = default). Nota/RM: ikut provenance/default.
   → OPEN: apakah nota perlu bisa pilih klinik manual, atau selalu ikut klinik default/login?
4. **Staf ke klinik:** dalam mode kolam bersama, staf TIDAK perlu di-assign ke klinik (semua akses semua).
   → OPEN: perlu tag "home clinic" staf untuk default PO/nota? (opsional, kenyamanan).

---

## 5. Ripple (yang harus disentuh)

- **Model + migrasi**: master_klinik (dari config) + 3 kolom nullable id_klinik (pasien/transaksi/pemesanan).
- **klinik_config_service** → jadi master_klinik service (CRUD, set default, validasi 1 default).
- **pasien_repo.generate_next_no_rm** → prefix dari master_klinik (fallback env).
- **print_service** (nota/PO/SOAP) → ambil identitas dari klinik terkait dokumen (bukan singleton).
- **Halaman Profil Klinik (settings.py)** → jadi list + form multi-klinik (set default).
- **Form PO** → dropdown klinik penerbit; template PO isi SIA/SIPA/apoteker (tuntaskan PO §B sekaligus).
- **Shell topbar/branding** (auth.py, _shared.py) → tampilkan klinik default (atau klinik login nanti).

---

## 6. Fase implementasi (usulan, tiap fase bisa dites)

- **MK-L1** Model `master_klinik` + migrasi (promote config → baris default + kolom SIA/SIPA/apoteker/rm_prefix).
- **MK-L2** Service + halaman CRUD klinik (list, tambah, edit, set default; validasi 1 default).
- **MK-L3** RM prefix per klinik (pasien.id_klinik_pendaftaran + generate_next_no_rm) + test.
- **MK-L4** Identitas dokumen: transaksi.id_klinik + pemesanan.id_klinik; print_service pakai klinik dokumen.
- **MK-L5** Form PO pilih klinik + isi SIA/SIPA/apoteker di cetak (menutup PO §B sebagian).
- **MK-L6** Test + housekeeping (DEC + roadmap + update handoff).

Catatan: MK-L5 menyatukan sebagian backlog NOTA_PO_FAKTUR §B (SIA/SIPA/apoteker) — efisien digabung.

---

## 7. Blind spots / risiko

- **Retrofit id_klinik ke `pasien`** (tabel besar) — walau nullable & ringan, lakukan lebih awal
  (sebelum data membengkak) sesuai peringatan audit ASVS. Backfill = klinik default.
- **Godaan scope-creep ke multi-tenant penuh.** Tahan. Selama pasien kolam bersama, JANGAN tambah
  scoping query/RBAC per-klinik — itu proyek lain (dan sudah diputuskan ditunda).
- **"1 default" invariant** harus dijaga di service (set default klinik lain → unset yang lama, transaksional).
- **Konsistensi B-013**: model/migrasi/service ditulis via bash + verify (file identitas ada di banyak titik).
- **Bukan pengganti keamanan.** Kolam bersama = semua staf tetap bisa lihat semua pasien; kalau nanti
  privasi antar-cabang jadi isu, itu memicu keputusan multi-tenant (Scope B) — di luar dokumen ini.

---

## 8. REVISI setelah review dr. Hansen (2026-07-03)

**Framing final:** 1 PERUSAHAAN, banyak cabang klinik; pasien bebas pilih cabang → kolam bersama (pasti).
`id_klinik` = **jejak/klasifikasi untuk MEMPERJELAS audit trail** ("terjadi di cabang mana"), BUKAN
pembatas akses. Bukan multi-tenant beda-perusahaan. Tak ada scoping/RBAC per-klinik.

**Keputusan TERKUNCI:**
1. `master_klinik_config` → **PROMOTE** jadi `master_klinik` (baris lama = klinik default). [confirmed]
2. RM prefix → `master_klinik.rm_prefix`. **No. RM lama DIABAIKAN** (tak di-backfill); prefix per-klinik
   **berlaku untuk pendaftaran pasien BARU saja**. [confirmed]
3. **Klinik aktif per aksi = klinik default** (untuk sekarang). [confirmed arah]
5. **SIPA/apoteker = tabel anak `klinik_apoteker`** (nama + no_sipa + aktif/masa_berlaku), BUKAN field
   tunggal — karena bisa >1 apoteker & ada masa transisi perpanjangan SIPA. **PO: dropdown apoteker
   aktif; nama apoteker mengikuti SIPA yang dipilih.** `no_sia` tetap 1 per klinik. [confirmed]

**Resolusi "klinik aktif" (runtime) — poin 3/4, arah tapi belum dikunci:**
- Karena kolam bersama → **WAJIB 1 DB pusat otoritatif.** Ini mengunci: **JANGAN pakai replica/client-server
  per cabang** (sinkronisasi kolam bersama = konflik data berat; proyek terpisah, dihindari).
- Rekomendasi: **1 DB pusat + tiap cabang = titik akses.** "Server tahu dia klinik mana" = **identitas
  per-deployment**, dua bentuk (pilih saat deployment, TIDAK memblokir model data):
  - (a) **Instance per cabang**: app tiap cabang punya env `KODE_KLINIK=A/B` (menunjuk DB pusat).
  - (b) **Satu instance, dibedakan host/IP**: peta alamat masuk → klinik (Klinik C = IP ketiga).
- Konsekuensi: keluar LAN terisolasi → **TLS WAJIB** (sinkron dgn audit ASVS V9).
- **Poin 4 (home-clinic per staf) kemungkinan TIDAK PERLU** — identitas situs/terminal mengalahkan
  identitas staf; staf rotasi tak perlu ingat apa-apa. Dikonfirmasi saat deployment shape dipilih.
- **Tidak memblokir MK-L1..L3**: bangun dulu dgn resolver sementara = "klinik default"; pasang resolver
  env/host saat deployment.

**Dampak ke fase:** MK-L1 tambah tabel anak `klinik_apoteker` + `no_sia` di master_klinik.
MK-L5 (PO) pakai dropdown apoteker aktif. Sisanya tetap.

---

## 9. DISKUSI ARSITEKTUR MULTI-CABANG (dr. Hansen, 2026-07-04)

**Visi dr. Hansen:** 1 PC server melayani beberapa cabang · 1 kolam pasien (shared, nama cabang beda) ·
cabang dibedakan **IP address** · **prefix RM mengikuti cabang otomatis**. Ini = **opsi (b)** §8.

**Kelayakan IP-based (opsi b): VIABLE, dengan syarat.**
- Petakan **SUBNET → klinik** (mis. cabang A = 192.168.10.0/24, B = 192.168.20.0/24), BUKAN IP individual
  (rawan berubah DHCP). Tabel pemetaan subnet→id_klinik + fallback klinik default.
- Server baca IP klien dari request. **Awas NAT/proxy**: kalau ada reverse proxy, `request.client.host` =
  IP proxy → harus baca `X-Forwarded-For` (dan hanya percaya dari proxy tepercaya). Di LAN langsung tanpa proxy: aman.
- Resolusi PER-REQUEST → staf rotasi non-isu (identitas situs mengalahkan identitas staf).
- **Prefix RM ikut cabang:** saat pendaftaran, server tentukan cabang dari IP → pakai rm_prefix cabang itu.
  RM = tag cabang PENDAFTARAN (tetap walau pasien nanti ke cabang lain — konsisten kolam bersama).

**Fork penentu = LOKASI cabang:**
- **Co-located** (satu gedung/LAN, "cabang" = lantai/counter/ruang): 1 PC pusat + IP/subnet mapping = IDEAL,
  sederhana, robust. Opsi (b) sangat cocok.
- **Remote** (kota/gedung berbeda): 1 PC pusat melayani cabang remote via internet/VPN → **TLS WAJIB** +
  latensi + **single point of failure** (server/internet pusat mati → cabang remote lumpuh total).

**Tentang "server-client per cabang (replica, tetap 1 entitas)":**
- Ini menyelesaikan availability/latensi cabang remote, TAPI meng-introduce **sinkronisasi kolam pasien
  bersama = konflik data berat** (2 cabang daftar pasien sama / edit bentrok). Untuk SHARED POOL, replikasi
  adalah alat yang salah — proyek besar tersendiri. **Dihindari** kecuali offline-resilience benar-benar wajib.

**Rekomendasi:** **1 DB pusat + IP/subnet→klinik mapping (opsi b)**, hindari replica.
- Co-located → langsung ideal.
- Remote → tetap central-server + koneksi bagus + TLS (terima single-point-of-failure), JANGAN replikasi
  kecuali tak ada pilihan.
- Model data TIDAK berubah oleh pilihan ini (resolver klinik-aktif = potongan kecil). Bisa ditambah nanti
  (tabel `klinik_ip_mapping` + middleware set klinik-aktif dari IP) saat rename master_klinik multi-baris
  dieksekusi (cabang ke-2). Sampai itu: resolver = klinik default.

**PERLU dr. Hansen:** cabang ke depan CO-LOCATED (satu LAN) atau REMOTE (lokasi berbeda)? Menentukan
apakah opsi (b) IP-mapping cukup, atau perlu pertimbangan availability/replikasi.
