import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import HTTPException, status

from config.settings import settings


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
# bcrypt is used when available; a PBKDF2-HMAC-SHA256 fallback keeps the app
# functional on environments where the bcrypt wheel is unavailable.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - environment dependent
    import bcrypt

    _HAS_BCRYPT = True
except ImportError:  # pragma: no cover
    _HAS_BCRYPT = False

_PBKDF2_ITERATIONS = 390_000


def _pbkdf2_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), _PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def _pbkdf2_verify(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, expected = stored.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), int(iterations)
        )
        return secrets.compare_digest(digest.hex(), expected)
    except (ValueError, TypeError):
        return False


def hash_password(password: str) -> str:
    if _HAS_BCRYPT:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    return _pbkdf2_hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if hashed_password.startswith("pbkdf2_sha256$"):
        return _pbkdf2_verify(plain_password, hashed_password)
    if _HAS_BCRYPT:
        try:
            return bcrypt.checkpw(
                plain_password.encode(), hashed_password.encode()
            )
        except ValueError:
            return False
    return False


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------
def _create_token(
    subject: str | int, token_type: str, expires_delta: timedelta
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(subject: str | int) -> str:
    return _create_token(
        subject, "access", timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )


def create_refresh_token(subject: str | int) -> str:
    return _create_token(
        subject, "refresh", timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )


def decode_token(token: str, expected_type: str | None = None) -> dict:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if expected_type and payload.get("type") != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload
