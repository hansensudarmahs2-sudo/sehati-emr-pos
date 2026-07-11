"""
Security utilities — password hashing (bcrypt) & JWT.

Bcrypt limit 72 byte di-handle otomatis (auto-truncate) supaya konsisten
dengan tools/migrate_passwords.py yang sebelumnya dipakai.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
from jose import JWTError, jwt

from app.config import settings


# ----- Bcrypt limits -----
BCRYPT_MAX_BYTES = 72


# ----- Password hashing -----
def hash_password(plaintext: str) -> str:
    """
    Hash password dengan bcrypt.

    Auto-truncate ke 72 byte (bcrypt hard limit) supaya tidak crash
    pada password panjang.
    """
    pw_bytes = (plaintext or "").encode("utf-8")[:BCRYPT_MAX_BYTES]
    hashed = bcrypt.hashpw(pw_bytes, bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(plaintext: str, hashed: str) -> bool:
    """
    Verifikasi plaintext password vs bcrypt hash.

    Auto-truncate input ke 72 byte supaya konsisten dengan hash_password().
    """
    if not plaintext or not hashed:
        return False
    try:
        pw_bytes = plaintext.encode("utf-8")[:BCRYPT_MAX_BYTES]
        return bcrypt.checkpw(pw_bytes, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ----- JWT -----
def create_access_token(
    payload: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Generate JWT access token.

    Default expiry: sesuai settings (6 jam, match logika anchor shift dokter).
    """
    to_encode = payload.copy()

    if expires_delta is None:
        expires_delta = timedelta(hours=settings.jwt_access_token_expire_hours)

    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})

    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode JWT access token. Raise JWTError kalau invalid/expired.

    Caller harus catch JWTError untuk handle "session expired".
    """
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )


__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_access_token",
    "JWTError",
]
