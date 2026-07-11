# Coding Style — Python

> Style guide untuk semua kode Python di project ini.

---

## General Principles

1. **Pemula-friendly** — kode harus bisa dibaca oleh dr. Hansen (yang tidak punya background coding) dengan bantuan comments.
2. **Type hints everywhere** — semua function signature pakai type hint.
3. **Komentar Indonesia untuk domain, English untuk teknis.**
4. **PEP 8** dengan modifikasi: line length 100 (bukan 79).
5. **Ruff** sebagai linter + formatter wajib pass sebelum commit.

---

## Naming

| What | Style | Examples |
|------|-------|----------|
| Module (file) | `snake_case.py` | `pasien_service.py`, `staf_repo.py` |
| Class | `PascalCase` | `PasienService`, `MasterStaf` |
| Function | `snake_case` | `register_pasien_baru`, `get_by_id` |
| Variable | `snake_case` | `id_pasien`, `no_rm_baru` |
| Constant | `UPPER_SNAKE_CASE` | `BCRYPT_MAX_BYTES`, `DEFAULT_LIMIT` |
| Private | `_leading_underscore` | `_enums`, `_helper_func` |
| Pydantic schema | `PascalCase` dengan suffix | `PasienBaruRequest`, `PasienResponse` |
| Enum class | `PascalCase` dengan suffix `Enum` | `StafRoleEnum`, `StatusAntrianEnum` |
| Enum value (Python) | match DB ENUM persis | `OWNER = "Owner"`, `BERAT = "Berat"` |

---

## Type Hints

### Wajib

```python
def get_by_id(self, id_staf: int) -> Optional[MasterStaf]:
    return self.db.get(MasterStaf, id_staf)

def list_staf(self, only_active: bool = False) -> list[MasterStaf]:
    ...
```

### Modern Style (Python 3.10+)

Pakai built-in generic:
- `list[X]` bukan `List[X]`
- `dict[K, V]` bukan `Dict[K, V]`
- `X | None` atau `Optional[X]` (saya prefer `Optional[X]` untuk readability pemula)

### SQLAlchemy 2.x

```python
class MasterStaf(Base):
    __tablename__ = "master_staf"

    id_staf: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    pin: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
```

**Mapped[X]** = non-nullable. **Mapped[Optional[X]]** = nullable.

---

## Docstrings

### Module docstring (wajib)

```python
"""
PasienService — business logic untuk pasien (register, search, detail, alergi).

Pertahankan logika dokter dari kode `main_api.py`:
- register_pasien_baru: 1 transaksi atomik
- generate no_rm dengan format YYMMDD-NNN
"""
```

### Class docstring (wajib untuk public class)

```python
class PasienService:
    """Service untuk semua operasi pasien."""
```

### Function docstring (wajib untuk public method)

```python
def register_pasien_baru(self, payload: PasienBaruRequest, id_staf_fo: int) -> dict:
    """
    Register pasien baru + buat kunjungan pertama, semua dalam 1 transaksi.

    Pertahankan urutan dari kode dokter line 192-269.

    Args:
        payload: data pasien lengkap (incl. alergi & penyakit).
        id_staf_fo: ID FO yang mendaftarkan.

    Returns:
        dict dengan keys: status, message, data (no_rm, id_pasien, ...).

    Raises:
        HTTPException 500 kalau transaksi gagal di tengah jalan.
    """
```

### Private function (boleh skip docstring kalau jelas)

```python
def _hash_value(plaintext: str) -> tuple[str, bool]:
    # bcrypt, auto-truncate 72 bytes
    ...
```

---

## Imports

### Urutan (PEP 8)

```python
# 1. Standard library
from datetime import datetime
from typing import Optional

# 2. Third-party
import bcrypt
from fastapi import HTTPException
from sqlalchemy.orm import Session

# 3. Local (project)
from app.config import settings
from app.db.models import MasterStaf
```

### Style

- Pakai `from ... import` untuk class/function specific.
- Hindari `from x import *` kecuali di `__init__.py` yang sengaja re-export.
- Group dengan blank line antar 3 kelompok.

---

## Function Design

### Single Responsibility

Function harus do **one thing**. Kalau perlu split:

```python
# ❌ Bad
def register_and_login(payload):
    # 50 baris untuk register
    # 20 baris untuk login
    ...

# ✓ Good
def register(payload): ...
def login(username, password): ...
```

### Max ~50 baris

Kalau function > 50 baris, pertimbangkan refactor jadi sub-functions.

### Early Return

```python
# ✓ Preferred — early return
def get_user(id):
    user = db.get(User, id)
    if user is None:
        raise NotFound(...)
    if not user.is_active:
        raise Forbidden(...)
    return user

# ❌ Avoid — deep nesting
def get_user(id):
    user = db.get(User, id)
    if user:
        if user.is_active:
            return user
        else:
            raise Forbidden(...)
    else:
        raise NotFound(...)
```

---

## Error Handling

### Pakai HTTPException untuk error API

```python
from fastapi import HTTPException, status

if not staf:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Staf dengan ID {id_staf} tidak ditemukan.",
    )
```

### Pesan error WAJIB bahasa Indonesia

User-facing message harus jelas dan dalam bahasa Indonesia (klinik pakai bahasa Indonesia).

```python
detail="Username atau password salah."  # ✓
detail="Authentication failed"          # ❌ — bahasa Inggris
```

### Transaction Rollback

```python
try:
    # ... DB operations
    self.db.commit()
    return result
except HTTPException:
    raise  # re-raise HTTPException tanpa rollback override
except Exception as e:
    self.db.rollback()
    raise HTTPException(
        status_code=500,
        detail=f"Gagal {operation}: {str(e)}",
    )
```

---

## Comments

### Domain Knowledge → Indonesia

```python
# Anchor shift logic — preserve kalau masih hari yang sama
# (dipertahankan dari kode dokter, untuk rekap shift kasir)
today = shift_anchor.date()
if not staf.waktu_mulai_shift or staf.waktu_mulai_shift.date() != today:
    staf.waktu_mulai_shift = shift_anchor
```

### Technical Note → English OK

```python
# FastAPI auto-inject via Depends(get_db)
db: DbSession,
```

### TODO/FIXME

```python
# TODO: implement pagination saat data > 100 row
# FIXME: race condition possible di counter no_rm
```

---

## SQLAlchemy Conventions

### Repository Pattern

```python
class PasienRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, id_pasien: int) -> Optional[Pasien]:
        return self.db.get(Pasien, id_pasien)

    def create(self, pasien: Pasien) -> Pasien:
        self.db.add(pasien)
        self.db.flush()  # assign PK tapi belum commit
        return pasien
```

**Aturan:**
- Repository **JANGAN call `commit()`** — itu tanggung jawab Service.
- Pakai `flush()` untuk dapat PK setelah `add()` tanpa commit.
- Repository **JANGAN ada business logic** — cuma CRUD + query.

### Query Style

```python
# ✓ Preferred — SQLAlchemy 2.x style
stmt = select(MasterStaf).where(MasterStaf.username == username)
return self.db.execute(stmt).scalar_one_or_none()

# ❌ Avoid — legacy 1.x style
return self.db.query(MasterStaf).filter_by(username=username).first()
```

---

## Pydantic Conventions

### Schema Naming

```python
class PasienBaruRequest(BaseModel):    # Request input
    ...

class PasienResponse(BaseModel):       # Response output
    model_config = ConfigDict(from_attributes=True)  # for ORM → Pydantic
    ...

class PasienListResponse(BaseModel):   # List wrapper
    status: str = "success"
    total: int
    data: list[PasienResponse]
```

### Validation

```python
from pydantic import Field

class StafCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=6, max_length=100)
    role: StafRoleEnum  # ← validate ke enum, error otomatis kalau salah value
```

---

## Testing Conventions

### File Structure

```
tests/
├── conftest.py             # shared fixtures
├── unit/                   # no DB, pure function
│   └── test_security.py
└── integration/            # pakai DB real + TestClient
    └── test_auth_endpoints.py
```

### Naming

```python
class TestPasswordHashing:
    def test_verify_correct_password(self):
        ...
    def test_verify_wrong_password(self):
        ...
```

Format: `def test_<behavior_or_scenario>()`.

### Markers

```python
import pytest

pytestmark = pytest.mark.integration  # mark seluruh file

@pytest.mark.slow
def test_long_running(): ...
```

Markers di `pyproject.toml` di `[tool.pytest.ini_options]`.

---

## Git Commit Convention

Pakai Conventional Commits:

```
feat: tambah endpoint /pasien/cari
fix: harga produk 0 di transaksi_detail_produk
test: unit test untuk pasien_service
refactor: pindah no_rm generation ke repository
docs: update README dengan setup instructions
chore: bump SQLAlchemy ke 2.0.30
```

**Body opsional** untuk explanation panjang:

```
feat: SDM management module

- CRUD staf via endpoint /api/v1/staf
- Reset password & PIN oleh Owner/Superadmin
- Change own password (validasi password lama)
- RBAC ketat: hanya Owner/Superadmin yang bisa reset password user lain
```

---

## Don't Do This

❌ **Tidak ada `print()` di production code** — pakai `logger` dari `app.core.logging` (kalau sudah dibuat).

❌ **Tidak ada hardcoded secret** — semua di `.env`.

❌ **Tidak ada SQL string concatenation** — selalu pakai parameter binding.

❌ **Tidak ada `assert` di production** — pakai `if ... raise` instead.

❌ **Tidak ada mutable default argument:**
```python
# ❌ Bad
def foo(items: list = []): ...

# ✓ Good
def foo(items: Optional[list] = None):
    if items is None:
        items = []
```

❌ **Tidak ada cross-layer access** — Router jangan akses Repository/Model langsung.
