# Glossary — Istilah Klinik & Teknis

> Single source untuk semua istilah project ini.

---

## Istilah Klinik

### Domain Umum
| Istilah | Definisi |
|---------|----------|
| **EMR / eMR** | Electronic Medical Record. Sistem catatan medis digital pasien. |
| **POS** | Point of Sale. Sistem kasir untuk transaksi jual-beli. |
| **SOAP** | Subjective (anamnesa), Objective (pemeriksaan fisik), Assessment (diagnosa), Plan (rencana). Format standar catatan dokter per kunjungan. |
| **Anamnesa** | Wawancara dokter ke pasien untuk gathering riwayat keluhan & medis. |
| **Pemeriksaan Fisik** | Observasi fisik dokter (inspeksi, palpasi, dll). |
| **Diagnosa** | Kesimpulan kondisi medis pasien dari anamnesa + pemeriksaan. |
| **Antropometri** | Pengukuran fisik tubuh — tinggi, berat, lingkar, skinfold. |
| **Skinfold** | Tebal lipatan kulit (mm). Diukur di 3-7 titik untuk hitung body fat. |
| **BMI** | Body Mass Index = berat(kg) / tinggi(m)². Klasifikasi obesitas. |
| **Body Fat %** | Persentase lemak dari total berat badan. Estimasi via Pollock formula. |
| **Pollock 3-site** | Formula Jackson-Pollock untuk estimate body fat dari 3 skinfold + umur + jenis kelamin. |
| **Lean Mass %** | Persentase massa non-lemak (otot, tulang, organ). 100% − Body Fat %. |
| **Lingkar Perut** | Waist circumference (cm). Indikator risiko metabolic syndrome. |

### Role di Klinik
| Role | Tugas |
|------|-------|
| **FO (Front Office)** | Petugas pendaftaran. Flow manager pasien (registrasi, pembatalan, verifikasi member). |
| **Dokter** | Konsultasi, SOAP, plan treatment, otorisasi tindakan tertentu (PIN). |
| **Perawat** | Eksekusi treatment di ruang tindakan, antropometri, start/end treatment. |
| **Apoteker** | Serah obat, write-off stok rusak, suggested order, repacking bahan→produk. |
| **Kasir** | Hitung tagihan, terima pembayaran (split payment), void item dengan otorisasi. |
| **Admin** | CRUD master data, lihat laporan. |
| **Owner** | Akses semua + dashboard, approve aksi sensitif. |
| **Superadmin** | Setara Owner secara akses, plus manajemen user lainnya. |

### Treatment & Produk
| Istilah | Definisi |
|---------|----------|
| **Treatment** | Tindakan medis/estetik yang dilakukan di klinik (facial, laser, IPL, dll). |
| **Series Treatment** | Rangkaian treatment yang direncanakan dokter untuk beberapa pertemuan ke depan. |
| **Single Treatment** | Treatment yang dilakukan dalam 1 kunjungan saja. |
| **IPL** | Intense Pulsed Light. Treatment cahaya untuk pigmentasi/hair removal. |
| **Laser Pico** | Laser pico-second untuk pigmentasi & rejuvenation. |
| **Facial** | Perawatan wajah comprehensive (cleansing, extraction, mask, dll). |
| **Botox / Filler** | Injection treatment — butuh dokter, butuh_otorisasi=1. |
| **Up-Selling** | Perawat/dokter tawarkan treatment/produk tambahan saat pasien sudah on treatment. |
| **Butuh Otorisasi** | Treatment yang `butuh_otorisasi=1` di master_treatment — perawat tidak bisa langsung add ke keranjang, harus PIN dokter. |
| **Resep** | Daftar produk yang dokter resepkan untuk pasien (dijual lewat apotek). |
| **Iterasi Resep** | Resep yang boleh ditebus berulang sebanyak N kali (e.g., krim malam 3× tebus). |
| **Repacking** | Apoteker memecah bahan klinik (e.g., serum 1L) jadi produk jual (e.g., 33 botol 30ml). |
| **BHP** | Bahan Habis Pakai (kapas, alkohol, masker, dll). Konsumsi saat treatment. |

### Inventory
| Istilah | Definisi |
|---------|----------|
| **Stok Gudang Utama** | Stok bahan di gudang/storage utama klinik. |
| **Stok Kabin** | Stok bahan di ruang treatment (kabin). Diisi dari gudang utama. |
| **Rasio Konversi** | Konversi satuan terkecil ke satuan pembelian (e.g., 1 box = 100 pcs, rasio = 100). |
| **AMC** | Average Monthly Consumption. Rata-rata pemakaian per bulan, dasar suggested order. |
| **Fast Moving** | Item dengan AMC > 50/bulan. Buffer order = 2 bulan. |
| **Slow Moving** | Item dengan AMC ≤ 50/bulan. Buffer order = 1 bulan. |
| **Write-Off** | Pengurangan stok karena rusak/expired (bukan karena jual/dipakai). |
| **Stock Opname** | Pengecekan fisik stok aktual, lalu adjust di sistem (PENYESUAIAN). |
| **Stok Minus** | Kondisi stok < 0 di sistem (karena human error atau race condition). Dibolehkan tapi flagged. |

### Membership
| Istilah | Definisi |
|---------|----------|
| **Tier** | Level membership (REGULAR/VIP/VVIP saat ini; Basic/Gold/Platinum di Phase 2). |
| **Kuota Bulanan** | Benefit treatment yang reset tiap bulan (e.g., 1× facial/bulan). Hangus kalau tidak dipakai. |
| **Kuota Total Paket** | Benefit treatment yang berlaku selama masa membership total (e.g., 2× IPL/12 bulan). Bisa dipakai kapan saja. |
| **Eligible Member Discount** | Flag di `master_produk` untuk produk yang dapat diskon untuk member (3% untuk VIP). |
| **Diskon Treatment** | % off untuk semua treatment (10% VIP, 20% VVIP). |
| **Free Konsultasi** | Member dapat konsultasi dokter gratis (tidak masuk tagihan). |

### Status Antrian
| Status | Arti |
|--------|------|
| **ANTRI_KONSULTASI** | Menunggu dipanggil dokter. |
| **KONSULTASI** | Sedang dengan dokter. |
| **ANTRI_TREATMENT** | Menunggu perawat di ruang tindakan. |
| **ON_TREATMENT** | Sedang treatment (1+ tindakan PROSES). |
| **ANTRI_BAYAR** | Selesai treatment, menunggu kasir. |
| **ANTRI_OBAT** | Selesai bayar, menunggu apoteker serah obat. |
| **COMPLETED** | Selesai semua, pasien pulang. |
| **BATAL** | Dibatalkan FO (alasan apa pun). |

---

## Istilah Teknis

### Stack
| Istilah | Definisi |
|---------|----------|
| **FastAPI** | Python web framework untuk REST API. Type-safe, auto Swagger UI. |
| **SQLAlchemy** | Python ORM (Object-Relational Mapping). Map Python class ke DB table. |
| **Alembic** | Database migration tool untuk SQLAlchemy. Track schema changes. |
| **Pydantic** | Library untuk data validation via type hints. Dipakai FastAPI. |
| **PyMySQL** | Pure Python driver MySQL. Tidak perlu compile native code. |
| **JWT (JSON Web Token)** | Format token untuk authentication. Signed payload yang bisa di-verify. |
| **bcrypt** | Password hashing algorithm. Slow on purpose (resist brute force). |
| **uv** | Modern Python package manager (10× faster pip). |
| **pytest** | Python testing framework. |
| **HTMX** | JS library untuk interaktivitas web tanpa nulis JS (klik → AJAX request → swap HTML). |
| **Jinja2** | Python template engine untuk generate HTML server-side. |
| **Tailwind CSS** | Utility-first CSS framework. |

### Arsitektur
| Istilah | Definisi |
|---------|----------|
| **Layered Architecture** | Pola arsitektur dengan layer terpisah (presentation, API, service, repository, model). |
| **Repository Pattern** | Pattern untuk encapsulate query DB. Service akses DB lewat repository. |
| **Service Layer** | Tempat business logic. Orchestrate repositories. |
| **Dependency Injection** | FastAPI inject dependency (db session, current user) ke endpoint function via `Depends()`. |
| **Unit of Work** | 1 request = 1 session = 1 transaction. |
| **ORM** | Object-Relational Mapping. SQLAlchemy adalah ORM. |
| **DTO** | Data Transfer Object. Pydantic schemas berperan sebagai DTO. |
| **Schema** | Struktur data untuk request/response validation. Bukan DB schema. |
| **Migration** | Script untuk update DB schema antar versi. |
| **Baseline** | Migration "kosong" yang stamp DB existing sebagai starting point Alembic. |

### Auth & Security
| Istilah | Definisi |
|---------|----------|
| **RBAC** | Role-Based Access Control. User dapat akses berdasarkan role. |
| **Bearer Token** | Format Authorization header: `Authorization: Bearer <token>`. |
| **OAuth2PasswordBearer** | FastAPI scheme untuk auth username+password→JWT. |
| **CORS** | Cross-Origin Resource Sharing. Setting untuk allow browser fetch dari domain lain. |
| **CSRF** | Cross-Site Request Forgery. Attack vector di form web — perlu protection. |
| **bcrypt rounds** | Cost factor bcrypt. Default 12 = 2^12 iterations. |
| **Salt** | Random data ditambah ke password sebelum hash. Bcrypt auto-include salt. |
| **Token expiry / TTL** | Time-to-live token. Setelah expired tidak valid. 6 jam di project ini. |
| **Audit Log** | Catatan semua aksi sensitif (siapa, kapan, apa, before/after). |

### Database
| Istilah | Definisi |
|---------|----------|
| **PK (Primary Key)** | Kolom unique identifier per row. Biasanya auto-increment integer. |
| **FK (Foreign Key)** | Kolom yang referensi PK di tabel lain. Enforce referential integrity. |
| **Index** | Struktur data untuk speed up query. Trade-off: write lebih lambat. |
| **ENUM** | Tipe data dengan nilai terbatas (e.g., 'L', 'P' untuk jenis kelamin). |
| **DECIMAL(12,2)** | Tipe uang/numeric dengan presisi tinggi. 12 digit total, 2 di belakang desimal. |
| **AUTO_INCREMENT** | Counter otomatis untuk PK. |
| **NULL vs NOT NULL** | NULL = boleh kosong. NOT NULL = wajib isi. |
| **CASCADE DELETE** | Saat parent dihapus, child otomatis dihapus juga (jarang dipakai di EMR). |
| **Soft Delete** | Tandai row sebagai "deleted" (is_active=0) tapi tidak hapus fisik. |
| **Hard Delete** | DELETE FROM — hapus fisik row. |
| **FOR UPDATE** | SQL lock untuk prevent concurrent modification. |
| **Transaction** | Group of SQL operations yang either all-commit atau all-rollback. |
| **Idempotent** | Operasi yang aman dipanggil berkali-kali (hasil sama). |

### Testing
| Istilah | Definisi |
|---------|----------|
| **Unit Test** | Test 1 function/class secara isolasi. No DB, no network. |
| **Integration Test** | Test multiple components together. Pakai DB real atau test DB. |
| **Smoke Test** | Test paling dasar — apakah aplikasi bisa start sama sekali. |
| **Fixture** | Setup/teardown reusable untuk test (e.g., test client, test DB). |
| **Marker** | Label di test (e.g., `@pytest.mark.integration`) untuk filter saat run. |
| **Mock** | Fake object untuk replace dependency saat test. |

---

## Singkatan / Acronym Kuis Cepat

| Singkatan | Arti |
|-----------|------|
| API | Application Programming Interface |
| BMI | Body Mass Index |
| BHP | Bahan Habis Pakai |
| CRUD | Create, Read, Update, Delete |
| CORS | Cross-Origin Resource Sharing |
| CSRF | Cross-Site Request Forgery |
| DB | Database |
| DDL | Data Definition Language (CREATE, ALTER, DROP) |
| DML | Data Manipulation Language (INSERT, UPDATE, DELETE) |
| EMR / eMR | Electronic Medical Record |
| ENUM | Enumeration |
| FK | Foreign Key |
| FO | Front Office |
| GUI | Graphical User Interface |
| HTTP | Hypertext Transfer Protocol |
| HTTPS | HTTP Secure |
| IPL | Intense Pulsed Light |
| JSON | JavaScript Object Notation |
| JWT | JSON Web Token |
| MVP | Minimum Viable Product |
| ORM | Object-Relational Mapping |
| OS | Operating System |
| PDP | Perlindungan Data Pribadi (UU Indonesia setara GDPR) |
| PK | Primary Key |
| POS | Point of Sale |
| RBAC | Role-Based Access Control |
| REST | Representational State Transfer |
| RM | Rekam Medis (Medical Record number) |
| SOAP | Subjective Objective Assessment Plan |
| SQL | Structured Query Language |
| SSL/TLS | Secure Sockets Layer / Transport Layer Security |
| SSH | Secure Shell |
| TTL | Time-To-Live |
| URL | Uniform Resource Locator |
| UX | User Experience |
| VPS | Virtual Private Server |
| WSL | Windows Subsystem for Linux |
