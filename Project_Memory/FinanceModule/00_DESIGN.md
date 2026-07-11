# Finance Module — Architecture Design

**Status**: 🟡 DESIGN PHASE — No implementation yet  
**Decision Date**: 11 Juni 2026  
**Source Discussion**: DEC-064 (lihat 11_decisions_log.md)  
**Implementation Trigger**: Setelah Bapak consult finance consultant + decide go/no-go

---

## 🎯 Konteks & Motivasi

### Mengapa Pisahkan Finance Module dari Sehati eRM-POS?

| Reason | Detail |
|--------|--------|
| **Domain Separation** | eRM-POS fokus: pasien, kunjungan, treatment, kasir. Finance Module fokus: akuntansi, payroll, tax. Beda domain expertise, beda audience user, beda compliance requirement. |
| **Codebase Maintainability** | Sehati codebase sudah 25K+ lines. Tambah full akuntansi (jurnal, COA, neraca, payroll, tax) akan double size. Pisah = both modules stay manageable. |
| **Independent Evolution** | Finance regulation (tax, PSAK) update tanpa kompromi operasional klinik. eRM-POS update (new feature klinik) tanpa break finance reporting. |
| **Different Audience** | Klinik staff (dokter/perawat/kasir) tidak butuh akses Finance. Owner + akuntan butuh Finance terpisah dengan UI khusus. |
| **Sensitive Data Isolation** | Finance data (gaji, komisi, profit margin, tax) lebih sensitif. Separate process = better access control. |

### Scope Finance Module (per keputusan Bapak)

Finance Module akan mencakup **4 area** sekaligus:

1. **Akuntansi Standar** — Jurnal entry, Buku Besar, Neraca, Laba Rugi (PSAK compliant)
2. **Cash Flow + Analytics** — Uang masuk/keluar, omzet vs cost, margin per kategori
3. **Komisi & Payroll** — Hitung komisi dokter/perawat per periode + slip gaji + PPh 21
4. **Tax & Compliance** — PPN (kalau klinik PKP), e-Faktur, SPT bulanan/tahunan

---

## 🏗️ Architecture Decision

### Connection: **REST API (Pull-based, with Future Webhook)**

**Decision Rationale**:
- Loose coupling (schema independence)
- Multi-client future-ready (BI tool, mobile, tax integration)
- Reuse existing `/api/v1/*` pattern di Sehati
- Authentication + audit infrastructure ready

**Why NOT Shared DB**:
- Tight schema coupling
- Migration jadi koordinasi 2 module (risk break)
- Finance jadi terikat sama ORM models Sehati

**Why NOT File Export**:
- Tidak cocok untuk near-real-time (1 menit polling)
- Data gap antara batch
- Format brittle

**Why NOT Event Stream (Kafka/RabbitMQ)**:
- Overkill untuk 1-menit polling
- Butuh infra tambahan (message broker)
- Complexity tidak sebanding dengan benefit

### Hosting: **LAN Deployment (Different Server, Same Network)**

**Decision Rationale**:
- Sehati di server kasir, Finance di PC Owner
- Akses via LAN (mis. `http://192.168.1.10:8000/api/v1/finance/*`)
- Data sensitif tetap di klinik
- Internet failure tidak ganggu Finance operation
- Backup keduanya independen

**Future Evolution**:
- Klinik scale ke multi-branch → migrate ke cloud SaaS
- Hybrid: Finance cloud + eRM-POS lokal dengan VPN/tunneling

### Sync Frequency: **Near-Real-Time (1 menit polling)**

- Finance pull data tiap 1-5 menit
- Cukup untuk most use case (dashboard finance, laporan harian, payroll bulanan)
- Tidak butuh sub-second freshness
- Webhook bisa di-add Phase 2 untuk event penting (void besar, PO closed)

---

## 📐 API Specification — `/api/v1/finance/*`

Reserved namespace. Endpoint placeholder untuk diisi saat Finance Module mulai dibangun.

### 1. Transaksi Penjualan (Source of Truth Omzet)

```
GET /api/v1/finance/transaksi
  Query params:
    - since: ISO8601 timestamp (last sync cursor)
    - until: ISO8601 timestamp (default: now)
    - include_void: bool (default: true) — kalau true, void juga di-pull
    - page, page_size
  
  Response:
    {
      "items": [
        {
          "id_transaksi": int,
          "id_kunjungan": int,
          "waktu_bayar": datetime,
          "status_transaksi": "BAYAR" | "VOID",
          "void_at": datetime | null,
          "void_reason_code": str | null,
          "void_reason_note": str | null,
          "late_void": bool,
          "no_rm": str,
          "nama_pasien": str,
          "tipe_membership": str | null,
          "id_staf_kasir": int,
          "nama_kasir": str,
          
          "subtotal": float,
          "nominal_diskon": float,
          "total_tagihan": float,
          "keterangan_promo": str,
          
          "items": [
            {
              "tipe": "TND" | "OBT",
              "id_treatment": int | null,
              "id_produk": int | null,
              "nama": str,
              "qty": float,
              "harga_satuan": float,
              "subtotal": float,
              "hpp_at_sale": float | null,   ← snapshot HPP saat transaksi
              "id_kuota_member": int | null,  ← kalau pakai kuota benefit
              "id_rencana": int | null       ← kalau bagian series
            }
          ],
          
          "pembayaran": [
            { "metode_bayar": str, "nominal": float }
          ]
        }
      ],
      "total_count": int,
      "page": int,
      "total_pages": int,
      "cursor_next": datetime
    }

  Use Case: Finance pull transaksi baru/updated since last sync → record jurnal entry
            (Sales Revenue, Cost of Goods Sold, Cash/Bank, Discount Expense)
```

### 2. Detail Transaksi Tunggal

```
GET /api/v1/finance/transaksi/{id_transaksi}
  Response: Same as item structure above (untuk debug/reconciliation manual)
```

### 3. Pengadaan (Cost Side)

```
GET /api/v1/finance/pengadaan
  Query params:
    - since, until: timestamp
    - status: "RECEIVED" | "PARTIAL_RECEIVED" | "ORDERED" | "CANCELLED" | "all"
    - page, page_size
  
  Response:
    {
      "items": [
        {
          "id_pemesanan": int,
          "tanggal_po": datetime,
          "supplier_nama": str,
          "status": str,
          "subtotal": float,
          "total_diskon": float,
          "total": float,
          "items_received": [
            {
              "id_pemesanan_item": int,
              "tipe_item": "PRODUK" | "BAHAN",
              "id_produk": int | null,
              "id_bahan": int | null,
              "nama_item": str,
              "qty_pesan": float,
              "qty_terima": float,
              "harga_satuan": float,
              "subtotal": float
            }
          ]
        }
      ]
    }
  
  Use Case: Finance record Purchases (Cost of Goods Purchased), Accounts Payable,
            Inventory increase. Plus 3-way match validation (PO vs Receive vs Invoice supplier).
```

### 4. Komisi & Payroll

```
GET /api/v1/finance/komisi/staf
  Query params:
    - periode_dari, periode_sampai: date range
    - id_staf: int | null (filter staf tertentu)
  
  Response:
    {
      "summary": [
        {
          "id_staf": int,
          "nama_staf": str,
          "role": str,
          "komisi_treatment": float,    ← sum komisi_dokter/perawat × tindakan SELESAI
          "komisi_produk": float,        ← sum komisi_dokter × resep DIBAYAR (jangan VOID)
          "total_komisi": float
        }
      ],
      "detail": [
        {
          "id_staf": int,
          "tanggal": date,
          "source_type": "TINDAKAN" | "PRODUK",
          "id_source": int,   ← id_kunjungan_tindakan or id_resep
          "nama_item": str,
          "base_value": float, ← harga atau nominal
          "komisi_persen": float | null,
          "komisi_nominal": float
        }
      ]
    }
  
  Use Case: Finance hitung slip gaji bulanan + PPh 21. Validation: tidak hitung komisi
            dari transaksi VOID atau resep BATAL.
```

### 5. Inventory Snapshot (Untuk Neraca)

```
GET /api/v1/finance/inventory/stok-value
  Query params:
    - at_timestamp: ISO8601 datetime (default: now)
  
  Response:
    {
      "timestamp": datetime,
      "total_stok_value": float,   ← sum (stok_terkini × hpp_per_unit) semua produk + bahan
      "breakdown": {
        "produk_retail": float,
        "produk_cabin": float,
        "produk_alat": float,
        "bahan_habis_pakai": float
      },
      "items_sample": [   ← top 20 items by value untuk verification
        { "tipe": "PRODUK", "nama": str, "stok": float, "hpp_per_unit": float, "value": float }
      ]
    }
  
  Use Case: Finance record Inventory Asset di Neraca per akhir periode.
```

### 6. Cash Flow per Metode Bayar

```
GET /api/v1/finance/cashflow/per-metode
  Query params:
    - periode_dari, periode_sampai: date range
    - per: "harian" | "mingguan" | "bulanan"
  
  Response:
    {
      "periode": [
        {
          "tanggal": date,
          "TUNAI": float,
          "QRIS": float,
          "DEBIT": float,
          "KREDIT": float,
          "TRANSFER": float,
          "total": float,
          "void_amount": float   ← total void di tanggal tsb (untuk reconciliation)
        }
      ]
    }
  
  Use Case: Finance reconciliation kas vs setoran bank, validasi mesin EDC,
            cashflow report.
```

### 7. Series Prepaid Liability (Customer Deposit)

```
GET /api/v1/finance/series-deposit
  Query params:
    - active_only: bool (default: true) — filter status PENDING + SCHEDULED
  
  Response:
    {
      "total_outstanding_value": float,   ← total uang yang sudah dibayar tapi belum digunakan
      "by_pasien": [
        {
          "id_pasien": int,
          "no_rm": str,
          "nama_pasien": str,
          "rencana": [
            {
              "id_rencana": int,
              "id_treatment": int,
              "nama_treatment": str,
              "urutan_sesi": int,
              "total_sesi": int,
              "harga_paket": float,
              "status": str,
              "tgl_kunjungan_pembuat": date  ← kapan series dibeli
            }
          ]
        }
      ]
    }
  
  Use Case: Finance record sebagai Customer Deposit Liability di Neraca.
            Saat pasien pakai sesi → revenue recognition + liability decrement.
```

### 8. Membership Commitment

```
GET /api/v1/finance/membership-commitment
  Response:
    {
      "by_pasien": [
        {
          "id_pasien": int,
          "tipe_membership": str,
          "kuota_outstanding": [
            {
              "id_treatment": int,
              "nama_treatment": str,
              "kuota_periode": str,
              "sisa_kuota": int,
              "value_per_treatment": float,
              "outstanding_value": float
            }
          ]
        }
      ],
      "total_outstanding_value": float
    }
  
  Use Case: Finance treat sebagai Contingent Liability atau Deferred Revenue
            tergantung accounting policy.
```

### 9. Sync Cursor (For Idempotency)

```
POST /api/v1/finance/sync-cursor
  Body:
    {
      "module": "journal_entry" | "payroll" | "inventory_valuation",
      "last_synced_at": ISO8601 datetime,
      "last_processed_id": int | null,   ← optional, untuk gap detection
      "notes": str | null
    }
  
  Response: { "status": "recorded", "cursor_id": int }
  
  Use Case: Finance lapor balik ke Sehati "saya sudah sync sampai timestamp X".
            Sehati record untuk audit + future query optimization (incremental pull).
```

### 10. Health Check & Metadata

```
GET /api/v1/finance/health
  Response: { "status": "ok", "server_time": datetime, "version": "1.0.0" }

GET /api/v1/finance/metadata
  Response:
    {
      "klinik_id": str,
      "klinik_nama": str,
      "version_schema": str,
      "supported_endpoints": list[str],
      "rate_limit_per_minute": int
    }
```

---

## 🗄️ Database Schema — Penyambung di Sehati Side

### Tabel Baru

#### 1. `finance_sync_cursor` — Track Last Sync Per Module

```sql
CREATE TABLE finance_sync_cursor (
    id_cursor       INT PRIMARY KEY AUTO_INCREMENT,
    module          VARCHAR(50) NOT NULL,       -- 'journal_entry', 'payroll', 'inventory_valuation', etc.
    last_synced_at  DATETIME NOT NULL,
    last_processed_id INT NULL,
    notes           TEXT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_module (module)
);
```

**Purpose**: Idempotency + audit untuk Finance Module integration. Finance bisa query "sejak kapan saya sync terakhir" tanpa duplicate processing.

#### 2. `external_api_keys` — Authentication Untuk External Module

```sql
CREATE TABLE external_api_keys (
    id_key          INT PRIMARY KEY AUTO_INCREMENT,
    name            VARCHAR(100) NOT NULL,      -- 'finance_module', 'bi_dashboard', etc.
    key_hash        VARCHAR(255) NOT NULL,      -- bcrypt hash of API key
    scopes          TEXT NOT NULL,              -- comma-separated: 'finance:read,finance:write'
    is_active       BOOLEAN DEFAULT TRUE,
    last_used_at    DATETIME NULL,
    expires_at      DATETIME NULL,              -- optional expiry
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by      INT NULL,
    INDEX idx_active (is_active),
    UNIQUE KEY uk_name (name)
);
```

**Purpose**: API key validation untuk request dari Finance Module. Phase 1 cukup 1 key. Phase 2 multi-client.

#### 3. `external_webhook_configs` — Future Phase 2 Push Events

```sql
CREATE TABLE external_webhook_configs (
    id_webhook      INT PRIMARY KEY AUTO_INCREMENT,
    name            VARCHAR(100) NOT NULL,
    url             VARCHAR(500) NOT NULL,
    event_types     TEXT NOT NULL,              -- comma: 'transaksi.voided,po.received'
    secret          VARCHAR(255) NOT NULL,      -- HMAC secret untuk verify
    is_active       BOOLEAN DEFAULT TRUE,
    last_triggered_at DATETIME NULL,
    last_success_at DATETIME NULL,
    failure_count   INT DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Purpose**: Future Phase 2 — Sehati push event ke Finance saat transaksi besar void / PO closed / etc.

#### 4. `external_request_log` — Audit Untuk External API Calls

```sql
CREATE TABLE external_request_log (
    id_log          BIGINT PRIMARY KEY AUTO_INCREMENT,
    id_key          INT NULL,                   -- FK ke external_api_keys
    endpoint        VARCHAR(255) NOT NULL,
    http_method     VARCHAR(10) NOT NULL,
    ip_address      VARCHAR(45) NULL,
    status_code     INT NOT NULL,
    response_time_ms INT NULL,
    error_message   TEXT NULL,
    request_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_request_at (request_at),
    INDEX idx_key_at (id_key, request_at)
);
```

**Purpose**: Audit trail siapa pull data kapan, untuk monitoring + debug.

### Alter Existing Table

#### `transaksi_detail_produk.hpp_at_sale` — HPP Snapshot

```sql
ALTER TABLE transaksi_detail_produk
    ADD COLUMN hpp_at_sale DECIMAL(12, 2) NULL AFTER subtotal;
```

**Purpose**: Saat transaksi bayar, snapshot `master_produk.hpp_per_unit` ke `transaksi_detail_produk.hpp_at_sale`. Crucial untuk Cost of Goods Sold (COGS) di Finance — kalau HPP master_produk berubah ke depan, historical COGS tetap akurat.

**Note**: Migration untuk add column. Service `proses_bayar()` perlu di-update untuk populate field ini.

---

## 🔐 Security Model

### Authentication Flow

```
1. Finance Module dibuat dengan API key (catat di external_api_keys, bcrypt hashed)
2. Setiap request, Finance kirim header: Authorization: Bearer {api_key_plain}
3. Sehati middleware:
   a. Extract key
   b. Hash with bcrypt
   c. Match against external_api_keys.key_hash WHERE is_active=TRUE
   d. Update last_used_at
   e. Check scope vs endpoint required permission
   f. Log to external_request_log
4. Return data atau 401/403
```

### Rate Limiting

- Per API key: max 60 requests/minute (default, configurable)
- Reject 429 Too Many Requests kalau exceed
- Future: implement sliding window di middleware

### Data Privacy

- Endpoint return minimal field needed untuk finance (no foto pasien, no medical detail)
- Pasien info: hanya `no_rm`, `nama_pasien`, `tipe_membership` (no alergi, no penyakit kronis)
- Audit log di Sehati log siapa pull what data kapan

---

## 🔄 Sequence Diagram

```
Finance Module (LAN PC Owner)        Sehati eRM-POS (Server Kasir)
─────────────────────────────────────────────────────────────────────
1. Last sync cursor (cron 1 menit)
   ├── GET sync cursor from local
   │   "last_synced_at": "2026-06-11 10:00:00"
   │
2. Pull new transaksi
   ├── GET /api/v1/finance/transaksi
   │   ?since=2026-06-11T10:00:00&page=1&page_size=500
   │   Authorization: Bearer abc123...
   │
   │                              ─→ Middleware validate API key
   │                                  Log to external_request_log
   │                              ─→ Query transaksi_kasir WHERE
   │                                  (waktu_bayar > since OR void_at > since)
   │                                  ORDER BY id ASC
   │                              ─→ Build response with items + pembayaran
   │                              ←─ JSON response 200
   │
3. Process transaksi
   ├── For each transaksi:
   │     ├── Create Jurnal Entry:
   │     │     Dr Cash/Bank    XX
   │     │     Dr COGS         XX
   │     │       Cr Sales      XX
   │     │       Cr Inventory  XX
   │     ├── If void: Reverse Jurnal Entry
   │     └── Update local sync cursor
   │
4. Lapor balik ke Sehati
   ├── POST /api/v1/finance/sync-cursor
   │   { "module": "journal_entry", "last_synced_at": "2026-06-11 10:01:30" }
   │                              ─→ Update finance_sync_cursor
   │                              ←─ 200 OK
   │
5. Sleep 1 menit → ulangi
```

---

## 🎯 Implementation Roadmap

### Phase 0 (NOW): Skeleton + Documentation
- [x] Design doc (this file)
- [ ] Skeleton API route `/api/v1/finance/*` — return 501 Not Implemented
- [ ] Migration SQL skeleton untuk 4 table + hpp_at_sale (tidak applied, save di migrations_sql/)
- [ ] DEC-064 di decisions log

### Phase 1 (Future): Core Sehati Side Integration
- [ ] Apply migration 017
- [ ] Implement API key authentication middleware
- [ ] Implement endpoint #1 (transaksi) + #2 (single transaksi) + #3 (pengadaan)
- [ ] Populate `hpp_at_sale` di `proses_bayar()` service
- [ ] Audit log integration
- [ ] Rate limiting middleware

### Phase 2 (Future): Extended Endpoints + Webhook
- [ ] Implement endpoint #4 komisi, #5 inventory, #6 cashflow, #7 series, #8 membership
- [ ] Webhook config table + push event mechanism
- [ ] Multi-client support (BI dashboard, mobile)

### Phase 3 (External): Finance Module Build
- [ ] Bapak build Finance Module di PC Owner (different codebase)
- [ ] Setup polling job 1 menit
- [ ] Build UI: Jurnal, Buku Besar, Neraca, L/R, Slip Gaji, SPT
- [ ] Integration dengan Accurate/Jurnal/Zahir (kalau perlu)

---

## ❓ Open Questions untuk Diskusi Berikutnya

| Question | Why It Matters |
|----------|----------------|
| Finance Module akan custom-build atau pakai existing tool (Accurate, Jurnal, Zahir, dll)? | Affect API design — kalau custom, fleksibel. Kalau pakai existing, perlu adapter layer. |
| Klinik PKP atau bukan? | Affect PPN calculation + faktur format |
| Periode tutup buku per bulan, kuartal, atau tahun? | Affect data immutability rule (closed period tidak boleh ubah) |
| Multi-tenant ready? (beberapa klinik share Finance Module) | Affect schema (perlu klinik_id di setiap row?) |
| Currency? Rupiah only atau multi? | Affect schema decimal precision |
| Existing chart of accounts (COA) atau buat baru? | Affect mapping dari transaksi → jurnal |

---

## 📚 References

- DEC-046: Owner Raw Data Export Pack (existing CSV export pattern — bisa jadi backup channel)
- DEC-060: Hybrid Komisi (komisi calculation logic, untuk endpoint #4)
- DEC-063: Void Pembayaran (status_transaksi=VOID handling)
- DEC-038: Pengadaan/PO module (untuk endpoint #3)
- DEC-049: Series Treatment pricing (untuk endpoint #7)

---

## 🔁 Maintenance Plan

- Update doc ini setiap kali ada decision baru terkait Finance Module
- Tambah section "Implementation Notes" saat Phase 1 mulai
- Version API: `/api/v1/finance/*` → `/api/v2/finance/*` kalau breaking change
- Deprecation policy: 6 bulan notice sebelum remove endpoint v1

---

## 🔄 REVISION 1 — External Review Refinements (11 Juni 2026, post-midnight)

Bapak telaah design doc dengan OpenAI dan dapat 12 usulan. Setelah diskusi, 6 refinement WAJIB diadopsi + 1 di-defer. Plus polling default berubah jadi 15 menit (dari 1 menit). Plus hybrid polling + manual export strategy.

### ✅ Adopted Refinements

#### R1 — Hybrid Polling + Manual Export Strategy

| Channel | Default | Purpose |
|---------|---------|---------|
| **Channel 1: Polling Automatic** | 15 menit (configurable per module) | Dashboard finance, live monitoring, incremental sync |
| **Channel 2: Manual Export Trigger** | On-demand via Owner button | End-of-day/end-of-month closing, batch reconciliation, audit-able file |

**Manual Export Reuse**: Existing `Reports Export Pack` (DEC-046) → tambah preset filter "Finance Pull All" yang generate ZIP berisi semua data finance-relevant dengan dictionary.

**Rationale**: 
- Akuntansi tidak butuh sub-menit freshness
- 15 menit cukup untuk most live dashboard need
- Manual export = safety net kalau polling fail + audit-able file untuk consultant review
- Cost ringan: polling 96x/day @ 15min vs 1440x/day @ 1min

#### R2 — Transaction Document Number (Stable Reference)

**Problem**: Saat ini cuma `id_transaksi` (auto-increment internal). Akuntansi butuh "nomor dokumen formal" yang:
- Immutable (tidak berubah)
- Reset per periode (optional)
- Format manusiawi (mudah dibaca)
- Tidak coupling dengan internal DB primary key

**Proposed Format**: `TRX-YYYY-MM-NNNNNN`
- Contoh: `TRX-2026-06-000001`
- Sequence reset per bulan (atau tahun, configurable)
- Generated saat transaksi pertama kali commit BAYAR (immutable)
- Disimpan di `transaksi_kasir.doc_number` (new field)

**Migration**: Add `doc_number VARCHAR(50) UNIQUE` ke `transaksi_kasir`.

**API Response Update**: Endpoint `/transaksi` include `doc_number` field.

#### R3 — `updated_at` Cursor untuk Reliable Incremental Sync

**Problem**: Saat ini cursor pakai `waktu_bayar` atau `void_at` di query. Tidak cukup robust kalau ada update lain (mis. status change, koreksi).

**Solution**: Add `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` ke `transaksi_kasir`. Cursor pull pakai `WHERE updated_at > since`.

**Benefit**: Any change to transaksi → updated_at auto-bump → Finance pull next cycle. No data loss.

**Migration**: 
```sql
ALTER TABLE transaksi_kasir 
    ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP 
        ON UPDATE CURRENT_TIMESTAMP 
        AFTER waktu_bayar;
```

#### R4 — Item-Level Discount Allocation

**Problem**: Diskon saat ini di header `transaksi_kasir.nominal_diskon` (single number). Untuk akuntansi akurat:
- COGS per item perlu margin akurat
- Tax reporting per kategori produk
- Profitability per treatment/produk

**Solution**: Allocate diskon ke per item secara proporsional (default) atau eksplisit (kalau ada promo per-item).

**Schema Update**:
- `transaksi_detail_produk.diskon_allocated DECIMAL(12, 2) NULL`
- `kunjungan_tindakan.diskon_allocated DECIMAL(12, 2) NULL` (alternatif join saat report)

**Algorithm** (saat `proses_bayar`):
```python
def allocate_discount(items, total_discount):
    """Proporsional ke harga × qty per item."""
    total_value = sum(it.harga * it.qty for it in items)
    if total_value == 0:
        return [0] * len(items)
    return [
        round(it.harga * it.qty / total_value * total_discount, 2)
        for it in items
    ]
```

**API Response**: Per item include `diskon_allocated` field.

#### R5 — API Key Model: Prefix + HMAC-SHA256 (Bukan Bcrypt-Only)

**Problem**: Bcrypt slow on purpose (untuk password). API key validation per request → CPU-heavy kalau bcrypt.

**Proposed Format**: `fin_pk_xxxxx.yyyyyy` 
- `fin_pk_` = prefix tetap (untuk identify "finance public key")
- `xxxxx` = 8-char random ID (indexed di DB untuk fast lookup)
- `yyyyyy` = HMAC-SHA256 signature

**Verification**:
1. Parse: extract prefix + ID + signature
2. Look up DB by ID (indexed)
3. Compute HMAC dengan secret stored
4. Compare HMAC (constant-time compare)
5. Faster than bcrypt 10-100x

**Migration Update**: `external_api_keys` revised:
```sql
ALTER TABLE external_api_keys
    ADD COLUMN key_prefix VARCHAR(20) NOT NULL,  -- 'fin_pk_xxxxx'
    ADD COLUMN key_secret VARCHAR(255) NOT NULL, -- HMAC secret (bukan hash of plain key)
    DROP COLUMN key_hash;  -- replaced
ALTER TABLE external_api_keys ADD UNIQUE KEY uk_prefix (key_prefix);
```

**Storage**: Plain key = `fin_pk_abc12345.signature_xxx`. DB store: prefix `fin_pk_abc12345` + secret. When validating: HMAC the request → compare.

#### R6 — Raw Payload Storage + Idempotency (Finance Side)

**Pattern**: Finance Module wajib implement (dokumentasi sebagai design note, bukan code di Sehati):

```
Finance Module flow:
1. Pull data dari Sehati API
2. SAVE raw JSON payload + compute content_hash (SHA256)
3. Check idempotency table: hash sudah pernah diproses?
   - Yes → skip
   - No → mark pending → next step
4. Process: convert ke journal entries
5. Mark idempotency record = processed
6. Update sync cursor di Sehati
```

**Benefit**: 
- Replay capability (debug accounting issue)
- Audit-able (raw data preserved)
- Idempotent (no duplicate journal entries)
- Gap detection (cursor + content hash)

**Sehati side**: Tidak perlu store payload (Finance yang handle). Hanya provide stable, deterministic response.

#### R7 — Feature Flag Safety untuk API Routes

**Problem**: Saat ini `app/api/v1/finance.py` registered, all return 501. Risk: kalau ada bug yang convert 501 → 200 dengan empty body, atau security middleware belum jalan → data leak.

**Solution**: Feature flag di `app/core/config.py`:
```python
FINANCE_API_ENABLED: bool = False  # Default OFF until Phase 1 ready
```

Plus middleware check di `app/api/v1/finance.py`:
```python
from app.core.config import settings

@router.get("/...")
def list_transaksi_for_finance(...):
    if not settings.FINANCE_API_ENABLED:
        raise HTTPException(404, "Endpoint not enabled")
    raise _not_yet_implemented(...)
```

**Behavior**: 
- `FINANCE_API_ENABLED=False` → semua endpoint return 404 Not Found (Sehati tidak expose existence)
- `FINANCE_API_ENABLED=True` → endpoint visible di Swagger, return 501 atau real data
- Phase 1: set True kalau API key auth + rate limiting sudah implemented

### 🟡 Deferred (Re-visit Saat Finance Consultant Available)

#### D1 — Stable Finance Category Mapping (Original Suggestion #6)

**Why Defer**: Butuh consultant define COA structure dulu. Mapping `treatment → COA account` dan `produk → COA account` adalah keputusan accounting policy.

**Placeholder**: Add field `finance_category VARCHAR(50) NULL` ke `master_treatment` dan `master_produk` (di future migration), populated empty for now. Consultant fill saat Phase 1 implementation.

### 📊 Updated Summary Table

| Aspect | Original Decision | After Revision 1 |
|--------|-------------------|------------------|
| Connection | REST API | REST API + manual export fallback |
| Polling | 1 menit | **15 menit configurable** |
| Doc Number | Internal `id_transaksi` only | **+ `doc_number` formal (TRX-YYYY-MM-NNNNNN)** |
| Sync Cursor | `waktu_bayar` / `void_at` | **`updated_at` (auto-bump on any change)** |
| Discount Tracking | Header-level only | **+ Item-level allocation (proporsional default)** |
| API Auth | Bcrypt hash | **Prefix + HMAC-SHA256** |
| Idempotency | Not specified | **Required at Finance side (raw payload + content hash)** |
| Safety | Always registered | **Feature flag `FINANCE_API_ENABLED`** |
| Stable Category | In design | **Deferred until consultant** |

### 🗄️ Updated Migration Skeleton (017 — TIDAK dijalankan dulu)

Tambahan ke `migrations_sql/017_finance_module_skeleton.sql`:
- `transaksi_kasir.doc_number VARCHAR(50) UNIQUE NOT NULL` (untuk transaksi baru)
- `transaksi_kasir.updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP`
- `transaksi_detail_produk.diskon_allocated DECIMAL(12,2) NULL`
- `kunjungan_tindakan.diskon_allocated DECIMAL(12,2) NULL`
- `external_api_keys` revised: `key_prefix` + `key_secret` (drop `key_hash`)
- (Optional) `master_treatment.finance_category VARCHAR(50) NULL` (kalau Bapak mau prep field)
- (Optional) `master_produk.finance_category VARCHAR(50) NULL`

### 🎯 Implementation Order Update (Phase 1)

1. **Feature flag config** + middleware (Safety first)
2. **Migration 017 v2** apply (schema lengkap dengan revisi)
3. **`doc_number` generator** saat `proses_bayar()` (immutable from creation)
4. **`updated_at` auto-bump** via SQLAlchemy ORM event listener
5. **Discount allocation** logic di `proses_bayar()` + populate fields
6. **HPP snapshot** di `proses_bayar()` (sudah di original design)
7. **API key Prefix+HMAC** auth middleware
8. **Implement core endpoints**: transaksi, transaksi/{id}, pengadaan, sync-cursor
9. **Rate limiting** middleware
10. **Audit log** integration
11. **Test end-to-end** dengan mock Finance client

### 📌 Open Questions (Untuk Konsultan Finance Nanti)

Plus yang sudah ada di section sebelumnya:
- Doc number format: per bulan vs per tahun reset? Sequence padding (6 atau 8 digit)?
- Discount allocation: proporsional saja, atau perlu support explicit per-item?
- `finance_category` enum atau free-text? Hierarchical (parent.child)?
- Idempotency window: berapa lama Finance simpan raw payload? Compliance requirement?

---

## 📝 Notes for Implementation Planning

Bapak setuju adopt 6 refinement di atas + hybrid polling/manual + defer #6. Sehari ini (11 Juni 2026 dini hari) **tidak ada implementasi code**. Semua perubahan tercatat di design doc + decisions log. Implementasi sebenarnya menunggu:
1. Konsultasi finance consultant (untuk decide COA + accounting policy)
2. Go/no-go decision Bapak
3. Phase 1 timeline yang jelas

Estimated effort Phase 1 (saat trigger): **3-5 sesi** untuk skeleton → working API dengan core endpoints + auth + audit.

---

## 🔄 REVISION 2 — PIVOT TO PURE VIEWER MODE (11 Juni 2026, post-midnight)

⚠️ **IMPORTANT**: Banyak section di doc ini superseded. Lihat **`01_VIEWER_BRIEF.md`** untuk approach final + **DEC-065** di decisions log.

### TL;DR Pivot

Setelah Bapak diskusi kedua dengan Claude → adopt approach yang jauh lebih ramping:

| Aspect | Old (DEC-064 ambition) | New (DEC-065 reality) |
|--------|------------------------|------------------------|
| **Role** | Full finance system paralel | Pure Viewer (read-only, derived-only) |
| **Source of Truth** | Finance Module sendiri | **Accurate Online** (akuntan klinik sudah pakai) |
| **Output** | Jurnal, Buku Besar, Neraca, L/R, Slip Gaji, SPT, e-Faktur | **3 view simple**: Jurnal Sederhana, Cashflow, Komisi |
| **Laba Bersih** | Show full P&L | **Tidak ditampilkan** (biaya operasional di Accurate) |
| **Tax/PSAK Compliance** | Custom build | **Tidak dibangun** (domain Accurate) |
| **Effort Phase 1** | 3-5 sesi | 1-2 sesi (setelah prasyarat siap) |
| **Maintenance** | High (compliance abadi) | Low (cuma derive logic) |

### Sections SUPERSEDED

Yang sebelumnya di doc ini, sekarang DROPPED dari scope:

- ❌ API endpoint #4 `/inventory/stok-value` (Neraca lengkap dropped)
- ❌ API endpoint #7 `/series-deposit` (PSAK liability recognition dropped)
- ❌ API endpoint #8 `/membership-commitment` (Contingent liability dropped)
- ❌ External webhook configs (push events) — Phase 2 reserved
- ❌ Raw payload + idempotency Finance side — tidak diperlukan tanpa journal posting

### Sections STAYS (Masih Relevan)

- ✅ Architecture: REST API + LAN deployment (infrastructure)
- ✅ API endpoint #1 `/transaksi` (untuk Jurnal Sederhana Harian)
- ✅ API endpoint #3 `/pengadaan` (untuk Cost side reference)
- ✅ API endpoint #4 `/komisi/staf` (untuk Ringkasan Komisi)
- ✅ API endpoint #6 `/cashflow/per-metode` (untuk Cashflow view)
- ✅ Sync cursor + auth + audit infrastructure
- ✅ Refinements R2-R4 (doc_number, updated_at, item-level discount, hpp_at_sale)
- ✅ Feature flag `FINANCE_API_ENABLED`

### Polling Reconsideration

Bapak's idea bisa jadi 1 jam karena viewer mode lebih toleran. Atau bahkan: **manual trigger only** (no polling) saat awal — kalau viewer cuma dibuka sesekali oleh Bapak.

### Manual Export = Now Critical

Reuse Reports Export Pack (DEC-046) sebagai PRIMARY interface awal:
- Bapak klik tombol "Generate Finance Snapshot" di Reports menu
- Sehati build CSV/ZIP berisi 3 view data
- Bapak buka file di Excel atau viewer tool
- **Tidak perlu Finance Module separate dulu** (mungkin)

### 3 View Specification (Refer to `01_VIEWER_BRIEF.md`)

1. **Jurnal Sederhana Harian** — Dr/Cr layout, akun selaras COA Accurate (config)
2. **Cashflow per Metode Bayar** — Daily/monthly breakdown + void
3. **Ringkasan Komisi** — DEC-060 hybrid logic, per staf, per periode

Detail UI mockup + algoritma per view → akan didokumen saat Phase 1 trigger.

### Constitution (Non-Negotiable Rules) — From Brief

1. Accurate = single source of truth. Kalau angka beda, Accurate yang benar.
2. Read-only, derived-only. NO input/jurnal manual di modul.
3. Indikatif. Footer wajib: *"Angka indikatif dari data operasional Sehati. Sumber resmi & pajak: Accurate."*
4. JANGAN bangun (domain Accurate): e-Faktur, SPT, PPh 21, tutup buku, neraca lengkap, depresiasi, payroll tax, import/feeder ke Accurate.

### Scope Guard — Yang Sehati TIDAK Tahu

Sehati hanya tahu **pendapatan + HPP/persediaan + komisi**. Biaya operasional (sewa, gaji, listrik, marketing) ada di Accurate, TIDAK di Sehati.

**Konsekuensi**: modul TIDAK menampilkan laba bersih. Hanya **pendapatan + gross margin**. Paksa modul jadi P&L lengkap = butuh input biaya manual = duplikasi Accurate = langgar prinsip derive-only.

### Upgrade Path: Pure Viewer → Feeder (Future)

Saat akuntan/Accurate minta data spesifik untuk import:
1. Cek format import Accurate Online (template Excel / API)
2. Bikin exporter map dari view ke template
3. Karena COA mapping sudah aligned, **incremental addition** bukan rewrite

### Implementation Order (Revised untuk Pure Viewer Mode)

**Phase 1** (saat trigger):
1. **Prasyarat Sehati side** (R2-R4):
   - HPP snapshot di proses_bayar
   - doc_number generator
   - updated_at auto-bump
   - Item-level discount allocation
2. **Reports Export Pack preset**: "Finance Snapshot" yang berisi 3 view data
3. **(Optional)** 3 view halaman di Sehati `/web/reports/finance-viewer/*` dengan footer indikatif

**Phase 2** (saat akuntan minta export ke Accurate):
- Build exporter ke template Accurate Online

### Implementation Order DROPPED

Yang di section sebelumnya "Phase 1 (Future)" + "Phase 2 (Future)" — semua yang related ke full akuntansi (Inventory snapshot, Series Deposit, Membership Commitment, Webhook, Multi-tenant) → DEFERRED INDEFINITELY atau DROPPED.

### Open Questions REVISED

Tinggal yang relevan untuk Pure Viewer:
- Cash basis atau accrual? (default cash sampai dikonfirmasi)
- Pengakuan pendapatan series & membership? (default saat bayar penuh sesi 1)
- PKP atau non-PKP? (default non-PKP gross)
- COA mapping Accurate (export dari akuntan)
- Periode tutup buku? (untuk indikatif rekonsiliasi)

Yang DROPPED (tidak relevan untuk Viewer):
- ❌ Multi-tenant
- ❌ Multi-currency
- ❌ Custom build vs existing tool — sudah jawab: Accurate Online
- ❌ Tax brackets
- ❌ Payroll calculation logic

---

## 📌 Final Status (Revision 2)

**Sebelumnya**: Design phase untuk full Finance Module dengan banyak compliance liability  
**Sekarang**: Pure Viewer mode — 3 simple view, derived dari Sehati, Accurate tetap source of truth  

**Effort drop**: ~70% lebih ringan dari original ambition.  
**Risk drop**: ~90% lebih ringan (no compliance maintenance abadi).  
**Value preserved**: Bapak tetap dapat alat baca pribadi untuk understanding klinik finansial.

**Source untuk reference**: 
- `01_VIEWER_BRIEF.md` — final architecture brief
- `DEC-065` di `11_decisions_log.md` — decision rationale
- This file (DESIGN 00) — historical context + infrastructure decisions yang masih relevan
