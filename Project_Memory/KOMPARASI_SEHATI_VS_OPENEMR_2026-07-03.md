# Komparasi Keamanan & Wiring: Sehati vs OpenEMR

**Tanggal:** 3 Juli 2026
**Fokus:** Keamanan, RBAC, dan *wiring* (bagaimana kontrol ditegakkan di seluruh aplikasi) — BUKAN fungsi/fitur (keduanya beda domain: OpenEMR umum, Sehati klinik estetik).
**Sumber:** Pembacaan kode langsung `openemr-master` (3.781 file PHP) vs `sehati_clinic` (FastAPI). OpenEMR versi master per Juli 2026.
**Sifat:** Analisis arsitektural. Tujuan: belajar dari EMR matang/tersertifikasi, bukan meniru bulat-bulat.

---

## 1. Ringkasan

OpenEMR adalah EMR open-source paling matang di dunia, sudah dipakai luas dan mengejar sertifikasi *Meaningful Use* (MU) / standar audit kesehatan AS. Wajar jika keamanannya lebih kaya. Yang menarik: **untuk kontrol-kontrol fundamental, Sehati sudah setara** (parameterized SQL, CSRF penuh, hashing kuat, RBAC server-side). Perbedaannya bukan "aman vs tidak aman", melainkan **kedalaman & cakupan** — OpenEMR menutup lapisan akuntabilitas medis (audit-baca, tamper-evidence, disclosure accounting, break-glass) dan enkripsi yang Sehati belum punya.

Yang juga penting: **Sehati lebih modern & lebih rapi wiring-nya.** OpenEMR membayar kematangannya dengan kompleksitas besar (state global, campuran kode legacy `.inc.php` + modern `src/`, dan **304 titik pengecekan ACL manual** yang rawan "lupa satu"). Sehati menegakkan kontrol secara **terpusat & otomatis** (CSRF via middleware, RBAC via dependency) — permukaan bug "lupa cek" jauh lebih kecil.

**Kesimpulan singkat:** Sehati sudah di kelas "aman" untuk skalanya. OpenEMR berguna sebagai **peta jalan akuntabilitas medis** — tunjukkan persis seperti apa audit-baca, tamper-evidence, dan MFA yang matang, yang kebetulan persis gap ASVS Sehati (V7.2.1, V7.3.1, V2.7).

---

## 2. Perbandingan Per-Axis

| Axis | OpenEMR | Sehati | Penilaian |
|------|---------|--------|-----------|
| **Model RBAC** | GACL — *data-driven*: section+ACO (mis. `patients\|med`, `encounters\|notes_a`) disimpan di DB, per-user **dan** per-group, allow/deny dengan **deny-precedence**, superuser bypass. Granular: `view/write/addonly/wsome` + **"my vs any"**. | *Code-defined*: `role_required(*roles)` enum, dicek di dependency FastAPI. Coarse-grained (per-role, bukan per-objek). | OE jauh lebih granular & fleksibel, tapi kompleks (butuh UI admin ACL, tabel `gacl_*`). Sehati coarser tapi **mudah dinalar & di-audit**. Untuk klinik kecil, pilihan Sehati defensibel. |
| **Penegakan RBAC** | Manual: `AclMain::aclCheckCore(...)` dipanggil **~304 tempat**. | Terpusat: dependency `role_required` + cek cookie. | **Keunggulan Sehati.** 304 titik manual = risiko "lupa cek di 1 endpoint". Pendekatan terpusat Sehati lebih tahan-bug. |
| **Hashing password** | Configurable Argon2id/Argon2i/bcrypt/SHA512, cost tunable via admin, `password_needs_rehash` auto-upgrade. | bcrypt cost 12 (fixed). | OE lebih fleksibel + jalur upgrade. bcrypt-12 Sehati kuat & cukup. Selisih kecil. |
| **Brute-force** | Counter ganda: **per-IP DAN per-username** + lockout, di-audit. | Per-IP cascade cooldown (sengaja BUKAN per-akun, hindari lockout DoS staf). | Filosofi beda. OE lebih ketat; Sehati sengaja pilih ketersediaan operasional. Keduanya valid. |
| **MFA** | Native **TOTP + U2F**. | Belum ada. | **Keunggulan OE.** Sesuai rekomendasi Sehati V2.7 (owner/superadmin). |
| **CSRF** | HMAC synchronizer (secret di session → token per-subject via `hash_hmac`, `hash_equals`), ~441 titik. | Double-submit cookie via **middleware** (`hash`/`compare_digest`), otomatis semua `/web`. | Kedua pola kuat. **Wiring Sehati lebih aman**: middleware otomatis vs 441 pemanggilan manual. |
| **SQL / injection** | adodb `?` binding (parameterized). | SQLAlchemy `select()` + bound `text()`. | Setara aman. Keduanya lulus. |
| **Output escaping (XSS)** | Manual: helper `xlt()/text()/attr()` di tiap output. | **Jinja2 autoescape otomatis.** | **Wiring Sehati lebih aman** (default aman vs harus ingat escape tiap kali). |
| **Audit — mutasi** | Ada (`EventAuditLogger`). | Ada (`AuditService`: CREATE/UPDATE/DELETE/LOGIN/VOID). | Setara. |
| **Audit — BACA rekam medis** | **Ya** — `auditSQLEvent` mencatat query termasuk **SELECT** pada tabel patient-record (+`pid`), dengan gate konfigurasi. | **Tidak.** Hanya mutasi. | **Gap Sehati (V7.2.1).** OE = model referensi. |
| **Audit — tamper-evidence** | **Checksum + tabel `log_comment_encrypt`** (MU2), opsi **ATNA** (kirim audit ke server audit standar). | Append-only **by convention** (app tak pernah delete/update). | **Gap Sehati (V7.3.1).** OE punya integritas kriptografis. |
| **Disclosure accounting** | Ada (`recordDisclosure` — kewajiban HIPAA: catat kapan PHI dibagikan ke pihak ke-3). | Tidak ada. | Spesifik regulasi AS. Belum relevan untuk Sehati (kecuali ekspansi regulasi). |
| **Break-glass** | Ada (akses darurat dgn audit berat). | Tidak ada. | Konsep berguna diketahui; belum wajib. |
| **Enkripsi at-rest** | App-level: dua key set (drive+DB), enkripsi kolom, key ber-versi. | Belum (rencana BitLocker disk-level pasca-deploy). | OE lebih granular (kolom). Disk-level Sehati lebih sederhana; layer beda. |
| **Kematangan vs kompleksitas** | Sangat matang, tersertifikasi; TAPI berat: state global (`OEGlobalsBag`), campur legacy `.inc.php` + `src/`. | Modern, layered (repo→service→API), Pydantic, ketat & ringkas. | Trade-off klasik: fitur/sertifikasi vs kebersihan & kecepatan iterasi. |

---

## 3. Analisa

**Di fundamental, Sehati sejajar — dan kadang wiring-nya lebih bersih.** Tiga hal yang sering jadi bug di EMR (SQLi, XSS, CSRF) justru ditegakkan Sehati secara *otomatis by default*: SQLAlchemy mencegah injeksi, Jinja2 autoescape mencegah XSS tanpa perlu diingat, dan CSRF middleware melindungi seluruh `/web` tanpa pemanggilan per-endpoint. OpenEMR mengandalkan disiplin developer memanggil `xlt()`, `aclCheckCore()`, dan `CsrfUtils::` di ratusan tempat — powerful tapi satu kelupaan = satu lubang. Ini sisi di mana **arsitektur muda Sehati justru unggul**: permukaan "human error" lebih kecil.

**Perbedaan sesungguhnya ada di lapisan akuntabilitas medis — dan itu bukan kebetulan.** OpenEMR dibangun mengejar sertifikasi kesehatan AS, sehingga ia punya persis hal-hal yang jadi *gap* ASVS Sehati:

- **Audit-baca (V7.2.1).** `auditSQLEvent` OpenEMR mencatat bahkan `SELECT` pada tabel rekam medis, lengkap dengan `pid` pasien yang sedang dibuka. Inilah jawaban "siapa membuka rekam medis siapa" yang belum bisa dijawab Sehati. Menariknya, OE melakukannya di **lapisan SQL** (menangkap semua akses, tapi kasar & berisik); Sehati bisa melakukannya lebih bersih di **lapisan service** (log eksplisit di endpoint detail/riwayat pasien & SOAP).
- **Tamper-evidence (V7.3.1).** OE tidak sekadar "append-only by convention" — ia menyimpan checksum tiap entri di tabel terpisah dan mendukung pengiriman ke server audit ATNA. Jadi perubahan log **terdeteksi**, bukan sekadar "tidak dilakukan aplikasi". Untuk Sehati saat ini (app tak pernah delete log) konvensi cukup; untuk multi-klinik nanti, rantai-checksum layak dipertimbangkan.
- **MFA (V2.7).** OE mendukung TOTP+U2F native — persis rekomendasi 2FA untuk owner/superadmin.

**"My vs any" memvalidasi desain SOAP-mu.** OpenEMR membedakan `notes` (encounter milik sendiri) vs `notes_a` (encounter siapa pun) di dalam **model izin**-nya. Itu persis konsep owner-check SOAP Sehati ("hanya dokter pemeriksa asli yang boleh edit") — bedanya Sehati meng-hardcode-nya di satu service, OE menggeneralkannya jadi permission. Artinya: instingmu benar dan sejalan dengan EMR matang. Kalau nanti banyak jenis sumber daya butuh aturan "milik-sendiri vs siapa-pun", pola OE menunjukkan cara menggeneralkannya.

**Yang TIDAK perlu ditiru.** Jangan tertarik meniru granularitas GACL 304-titik atau state global OpenEMR. Itu utang kompleksitas yang lahir dari 20 tahun legacy + tuntutan sertifikasi. Untuk klinik estetik kecil-menengah, itu justru menambah permukaan bug tanpa manfaat sepadan. Pertahankan penegakan terpusat Sehati.

**Catatan multi-klinik.** Perlu diketahui: **OpenEMR pun bukan multi-tenant** dalam arti satu instans melayani banyak entitas terpisah — modelnya satu-install-per-praktik (fitur "sites" terbatas). Jadi untuk rencana Sehati "1 server → banyak klinik", **tidak ada contoh siap-pakai di OpenEMR**; scoping `klinik_id` per-query tetap harus kamu desain sendiri. OE tetap berguna sebagai referensi audit & MFA, bukan tenancy.

---

## 4. Yang Bisa Diadopsi Sehati (konkret, berurut nilai)

1. **Audit-baca rekam medis (dari `auditSQLEvent`).** Adopsi *konsep*-nya, bukan implementasi SQL-layer-nya. Tambah `AuditService.log_view(id_pasien, ...)` dan panggil di endpoint detail/riwayat pasien + SOAP. Lebih bersih dari cara OE karena eksplisit di service. → Tutup **V7.2.1**.
2. **MFA TOTP untuk owner/superadmin.** OE membuktikan TOTP praktis di EMR on-prem. Terapkan hanya untuk role berhak-tinggi (sesuai keputusan sebelumnya — dokter tidak diwajibkan). → Tutup **V2.7**.
3. **Tamper-evidence audit (opsional, untuk multi-klinik).** Kalau menuju multi-klinik/cloud, tiru ide checksum-chain OE untuk `audit_log` (hash tiap baris memuat hash baris sebelumnya). → Perkuat **V7.3.1**.
4. **Generalisasi "my vs any"** kalau kebutuhan bertambah — pola OE `notes` vs `notes_a` sebagai referensi memindah owner-check dari kode ke model izin.
5. **Break-glass (jauh ke depan).** Kalau ada skenario akses darurat (dokter jaga butuh rekam pasien bukan pasiennya saat emergency), pola OE: izinkan tapi audit berat + notifikasi.

**Jangan adopsi:** GACL data-driven penuh, ACL manual per-titik, state global, disclosure accounting (spesifik HIPAA/AS) — kecuali regulasi Indonesia menuntutnya.

---

## 5. Penilaian Akhir

Dibanding OpenEMR, Sehati **bukan versi "kurang aman"** — ia versi **lebih kecil, lebih modern, dengan wiring lebih bersih**, yang secara sengaja belum memasang lapisan akuntabilitas medis kelas-sertifikasi. Untuk klinik tunggal di LAN, itu keputusan yang wajar. Tiga hal yang membuat OpenEMR "healthcare-grade" — audit-baca, tamper-evidence, MFA — kebetulan adalah tepat gap yang sudah teridentifikasi di audit ASVS Sehati. Jadi OpenEMR mengonfirmasi peta jalan yang sama, dari sudut EMR yang sudah menempuhnya: **fundamental sudah beres; naik kelas = akuntabilitas akses + faktor kedua.**

---

*Analisis arsitektural read-only. Tidak ada kode yang diubah. OpenEMR = GNU GPL 3; hanya dipelajari polanya, tidak menyalin kode.*
