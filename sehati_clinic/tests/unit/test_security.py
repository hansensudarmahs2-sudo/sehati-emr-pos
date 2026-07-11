"""
Unit tests untuk app.core.security.

Pure function tests — no DB, no FastAPI. Cepat & deterministic.
"""

from datetime import timedelta

import pytest
from jose import JWTError

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    """bcrypt hash + verify."""

    def test_hash_password_returns_bcrypt_format(self):
        """Hash harus dalam format bcrypt ($2b$...)"""
        hashed = hash_password("MyPassword123")
        assert hashed.startswith("$2b$")
        assert len(hashed) == 60  # bcrypt hash selalu 60 char

    def test_verify_correct_password(self):
        """Password yang benar harus return True."""
        plaintext = "MyPassword123"
        hashed = hash_password(plaintext)
        assert verify_password(plaintext, hashed) is True

    def test_verify_wrong_password(self):
        """Password yang salah harus return False."""
        hashed = hash_password("MyPassword123")
        assert verify_password("WrongPassword", hashed) is False

    def test_verify_empty_password(self):
        """Empty password tidak boleh dianggap valid."""
        hashed = hash_password("MyPassword123")
        assert verify_password("", hashed) is False

    def test_verify_with_empty_hash(self):
        """Empty hash tidak boleh crash, harus return False."""
        assert verify_password("anything", "") is False

    def test_hash_long_password_truncated_to_72_bytes(self):
        """Password > 72 byte harus di-truncate, bukan crash."""
        long_pw = "a" * 100  # 100 byte > 72
        hashed = hash_password(long_pw)
        assert hashed.startswith("$2b$")
        # Verify: input sama (yang akan di-truncate ke 72) harus pass
        assert verify_password(long_pw, hashed) is True

    def test_hash_two_identical_passwords_different_hash(self):
        """Salt random — dua hash dari password sama harus beda."""
        pw = "SamePassword"
        h1 = hash_password(pw)
        h2 = hash_password(pw)
        assert h1 != h2
        # Tapi keduanya valid untuk verify password yang sama
        assert verify_password(pw, h1) is True
        assert verify_password(pw, h2) is True


class TestJWT:
    """JWT encode/decode."""

    def test_create_and_decode_token(self):
        """Token yang baru di-create harus bisa di-decode kembali."""
        payload = {"sub": "1", "role": "Dokter", "username": "dokter_andi"}
        token = create_access_token(payload)
        decoded = decode_access_token(token)
        assert decoded["sub"] == "1"
        assert decoded["role"] == "Dokter"
        assert decoded["username"] == "dokter_andi"
        assert "exp" in decoded
        assert "iat" in decoded

    def test_token_has_default_expiry(self):
        """Token tanpa expires_delta pakai default dari settings."""
        from app.config import settings

        token = create_access_token({"sub": "1"})
        decoded = decode_access_token(token)

        # exp - iat = jwt_access_token_expire_hours
        expected_seconds = settings.jwt_access_token_expire_hours * 3600
        actual_seconds = decoded["exp"] - decoded["iat"]
        assert abs(actual_seconds - expected_seconds) <= 1  # toleransi 1 detik

    def test_token_with_custom_expiry(self):
        """Pass expires_delta override default."""
        token = create_access_token({"sub": "1"}, expires_delta=timedelta(minutes=5))
        decoded = decode_access_token(token)
        actual_seconds = decoded["exp"] - decoded["iat"]
        assert abs(actual_seconds - 300) <= 1

    def test_decode_invalid_token_raises(self):
        """Token rusak harus raise JWTError."""
        with pytest.raises(JWTError):
            decode_access_token("not.a.valid.jwt.token")

    def test_decode_expired_token_raises(self):
        """Token expired harus raise JWTError."""
        token = create_access_token({"sub": "1"}, expires_delta=timedelta(seconds=-1))
        with pytest.raises(JWTError):
            decode_access_token(token)
