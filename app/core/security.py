"""Password hashing and JWT token helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import Settings
from app.core.errors import authentication_error

MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""

    password_bytes = password.encode("utf-8")
    if len(password_bytes) > MAX_PASSWORD_BYTES:
        raise ValueError("Password must not exceed 72 bytes")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password without leaking bcrypt errors."""

    try:
        password_bytes = password.encode("utf-8")
        if len(password_bytes) > MAX_PASSWORD_BYTES:
            return False
        return bcrypt.checkpw(password_bytes, password_hash.encode("utf-8"))
    except (TypeError, ValueError):
        return False


def create_access_token(user_id: int, settings: Settings) -> tuple[str, int]:
    """Create a signed access token and return it with its lifetime in seconds."""

    now = datetime.now(UTC)
    expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    expires_at = now + expires_delta
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": expires_at,
        "iss": settings.jwt_issuer,
        "type": "access",
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_value,
        algorithm=settings.jwt_algorithm,
    )
    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str, settings: Settings) -> int:
    """Validate a token and return its user ID."""

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret_value,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "exp", "iat", "iss"]},
        )
        if payload.get("type") != "access":
            raise authentication_error("Invalid access token")
        return int(payload["sub"])
    except (jwt.InvalidTokenError, TypeError, ValueError) as exc:
        raise authentication_error("Invalid or expired access token") from exc
