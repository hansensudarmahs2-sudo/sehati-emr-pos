"""
FastAPI dependencies — reusable di semua router.

Akses:
    from app.core.deps import get_db, get_current_user, role_required
"""

from typing import Annotated, Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import JWTError, decode_access_token
from app.db.models import MasterStaf, StafRoleEnum
from app.db.session import SessionLocal


# ----- OAuth2 scheme -----
# tokenUrl harus match dengan endpoint login kita
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# ----- DB session dependency -----
def get_db():
    """Yield Session, otomatis close setelah request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Type alias untuk dipakai di router
DbSession = Annotated[Session, Depends(get_db)]


# ----- Current user dependency -----
def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: DbSession,
) -> MasterStaf:
    """
    Decode JWT, fetch user dari DB, validasi session.

    Raise 401 kalau:
    - Token invalid / expired
    - Staf tidak ditemukan
    - Staf is_active = False
    - Session tidak aktif (is_logged_in=0 atau token_expired_at lewat)
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sesi tidak valid atau habis. Silakan login kembali.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. Decode JWT
    try:
        payload = decode_access_token(token)
        id_staf: int | None = payload.get("sub")
        if id_staf is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # 2. Fetch staf dari DB
    staf = db.get(MasterStaf, int(id_staf))
    if staf is None:
        raise credentials_exception

    # 3. Validasi status aktif
    if not staf.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akun tidak aktif. Hubungi admin.",
        )

    # 4. Validasi session (logout terpusat — kalau is_logged_in=0, paksa logout)
    if not staf.is_logged_in:
        raise credentials_exception

    return staf


# Type alias
CurrentUser = Annotated[MasterStaf, Depends(get_current_user)]


# ----- Role-based access control -----
def role_required(*allowed_roles: StafRoleEnum) -> Callable:
    """
    Factory dependency untuk RBAC.

    Pakai:
        @router.post("/...", dependencies=[Depends(role_required(StafRoleEnum.FO, StafRoleEnum.ADMIN))])
        def my_endpoint(...): ...

    Atau:
        def my_endpoint(user: MasterStaf = Depends(role_required(StafRoleEnum.DOKTER))):
            # user.role guaranteed in allowed_roles
            ...
    """
    # Normalize ke set untuk lookup cepat
    allowed_set = {r.value if isinstance(r, StafRoleEnum) else r for r in allowed_roles}

    def dependency(user: CurrentUser) -> MasterStaf:
        user_role = user.role.value if isinstance(user.role, StafRoleEnum) else user.role
        if user_role not in allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Akses ditolak. Role Anda ({user_role}) tidak memiliki izin untuk endpoint ini.",
            )
        return user

    return dependency


__all__ = [
    "get_db",
    "DbSession",
    "get_current_user",
    "CurrentUser",
    "role_required",
    "oauth2_scheme",
]
