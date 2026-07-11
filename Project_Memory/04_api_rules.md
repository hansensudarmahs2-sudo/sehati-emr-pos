# API Rules — REST Convention

> Standar untuk semua REST API endpoint di project ini.

---

## URL Structure

```
/api/v1/<domain>/<action_or_id>
```

**Versioning:** `v1` di prefix. Saat ada breaking change di masa depan, bikin `v2` paralel.

### Examples (existing & planned)

| Method | URL | Domain | Description |
|--------|-----|--------|-------------|
| POST | `/api/v1/auth/login` | auth | Login |
| POST | `/api/v1/auth/logout` | auth | Logout |
| GET | `/api/v1/auth/me` | auth | Current user info |
| POST | `/api/v1/auth/change-password` | auth | Change own password |
| GET | `/api/v1/staf` | staf | List all staf |
| GET | `/api/v1/staf/{id}` | staf | Detail staf |
| POST | `/api/v1/staf` | staf | Create staf baru |
| PUT | `/api/v1/staf/{id}` | staf | Update profile |
| PATCH | `/api/v1/staf/{id}/reset-password` | staf | Reset password user lain |
| PATCH | `/api/v1/staf/{id}/reset-pin` | staf | Reset PIN |
| PATCH | `/api/v1/staf/{id}/set-active` | staf | Enable/disable |
| POST | `/api/v1/pasien/baru` | pasien | (planned) Register baru |
| GET | `/api/v1/pasien/cari?q=...` | pasien | (planned) Search |
| GET | `/api/v1/pasien/{id}` | pasien | (planned) Detail |

---

## HTTP Method Convention

| Method | Use Case | Idempotent? |
|--------|----------|-------------|
| `GET` | Read data | ✓ |
| `POST` | Create new entity / non-CRUD action (login, logout) | ✗ |
| `PUT` | Replace entire entity (full update) | ✓ |
| `PATCH` | Partial update / state change (reset-password, set-active) | ✓ |
| `DELETE` | Hard delete (jarang dipakai — prefer soft delete via PATCH) | ✓ |

---

## Response Format

### Sukses (standard)

**Untuk single resource:**
```json
{
  "id_pasien": 123,
  "no_rm": "260520-001",
  "nama": "...",
  ...
}
```

**Untuk list:**
```json
{
  "status": "success",
  "total": 8,
  "data": [
    { ... },
    { ... }
  ]
}
```

**Untuk action (login, register baru):**
```json
{
  "status": "success",
  "message": "Data pasien baru berhasil disimpan.",
  "data": {
    "no_rm": "260520-001",
    "id_pasien": 123,
    ...
  }
}
```

### Error

**HTTP 4xx/5xx** dengan FastAPI default format:
```json
{
  "detail": "Pesan error dalam bahasa Indonesia."
}
```

**Validation error (Pydantic — 422):**
```json
{
  "detail": [
    {
      "loc": ["body", "nama"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## HTTP Status Codes

| Code | Use Case |
|------|----------|
| `200 OK` | Success (GET, PUT, PATCH, POST untuk action) |
| `201 Created` | Resource baru dibuat (POST /staf, POST /pasien/baru) |
| `204 No Content` | Success tanpa body (jarang dipakai) |
| `400 Bad Request` | Business logic error (misal: "Password baru harus berbeda") |
| `401 Unauthorized` | Token invalid/expired/no token |
| `403 Forbidden` | Role tidak punya akses (RBAC fail) |
| `404 Not Found` | Resource tidak ada |
| `409 Conflict` | Duplikasi (misal: username sudah ada) |
| `422 Unprocessable Entity` | Pydantic validation fail |
| `500 Internal Server Error` | Unhandled exception |

---

## Authentication

Semua endpoint kecuali yang public **wajib** include header:
```
Authorization: Bearer <jwt_access_token>
```

**Public endpoints (no auth):**
- `POST /api/v1/auth/login`
- `GET /` (landing)
- `GET /health`
- `GET /health/db`
- `GET /docs`, `/redoc`, `/openapi.json`

**JWT Payload:**
```json
{
  "sub": "<id_staf_string>",
  "role": "Dokter",
  "username": "dokter_andi",
  "iat": 1234567890,
  "exp": 1234567890
}
```

**Token expiry:** 6 jam (sesuai logika anchor shift).

---

## RBAC (Role-Based Access Control)

Pakai dependency `role_required(*roles)`. Contoh:

```python
@router.post(
    "/api/v1/pasien/baru",
    dependencies=[Depends(role_required(StafRoleEnum.FO, StafRoleEnum.ADMIN, ...))],
)
def register_pasien(...): ...
```

### Role Matrix (Default Mapping)

| Endpoint Group | Allowed Roles |
|----------------|---------------|
| Auth (login/logout/me/change-pwd) | Public (login) / Any authenticated (rest) |
| SDM Management — list/detail | Owner, Superadmin, Admin |
| SDM Management — create/reset/active | Owner, Superadmin |
| Pasien — register baru | FO, Admin, Superadmin, Owner |
| Pasien — search & view | FO, Dokter, Perawat, Apoteker, Kasir, Admin, Superadmin, Owner |
| Pasien — alergi add | FO, Perawat, Dokter, Admin, Owner |
| Pasien — alergi delete | Dokter, Admin, Superadmin, Owner (Hanya Dokter & up — filosofi EMR) |
| Kunjungan — ubah status (batal) | FO, Owner, Superadmin |
| Dokter SOAP | Dokter, Owner |
| Treatment start/end | Perawat, Dokter, Owner |
| Treatment upsell (butuh_otorisasi=1) | Perawat dengan PIN dokter OR Dokter langsung |
| Kasir — bayar, void | Kasir, Admin, Owner |
| Apotek | Apoteker, Admin, Owner |
| Inventory write-off | Apoteker, Owner |
| Reports | Owner, Admin, Superadmin |
| Master CRUD | Owner, Superadmin |

---

## Pagination Convention

Untuk endpoint list:
```
GET /api/v1/staf?page=1&limit=20
```

Default: `page=1, limit=50`. Max limit: 100.

Response:
```json
{
  "status": "success",
  "total": 234,
  "page": 1,
  "limit": 20,
  "total_pages": 12,
  "data": [...]
}
```

**Untuk Phase 1:** belum implement pagination — pakai `limit` simple di repository. Akan di-implement saat data >100 row.

---

## Search Convention

```
GET /api/v1/pasien/cari?q=Budi&limit=10
```

Search field implicit dari domain:
- Pasien: nama, no_rm, nomor_telepon (ILIKE %q%)
- Staf: username, nama_staf

Case-insensitive (ILIKE).

---

## Idempotency

Endpoint `POST` yang non-action (misal: register pasien) **tidak idempotent** — call 2× akan create 2 row.

Solusi anti-double-submit di frontend nanti:
- Disable submit button setelah klik
- Show loading state
- Server tidak punya idempotency key (untuk MVP). Bisa di-add di Phase 2 kalau perlu.

---

## API Versioning Strategy

- Current: `v1`
- Breaking change → bikin `v2` paralel, deprecate `v1` setelah 6 bulan
- Non-breaking change (add endpoint, add optional field): tetap di `v1`

---

## Swagger UI

Otomatis di-generate FastAPI di `/docs`. Tagging endpoint pakai kategori bahasa Indonesia/English mixed:
- `Auth`
- `SDM Management`
- `Pasien` (planned)
- `Kunjungan` (planned)
- `Kasir` (planned)
- `Apotek` (planned)
- `Dokter` (planned)
- `Treatment` (planned)
- `Inventory` (planned)
- `Membership` (planned)
- `Reports` (planned)
- `Master` (planned — Phase 1 minggu 6)
- `Meta` (health, root)
