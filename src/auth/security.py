# -*- coding: utf-8 -*-
"""
Core password hashing and JWT token helpers.

Prefers Argon2id when available and falls back to stdlib PBKDF2 so auth routes
remain operational even in slim runtime environments.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt

from src.observability import incr_metric, log_event

try:
    from argon2 import PasswordHasher  # type: ignore
    from argon2.exceptions import VerifyMismatchError  # type: ignore

    ARGON2_AVAILABLE = True
except Exception:
    ARGON2_AVAILABLE = False

    class VerifyMismatchError(Exception):
        """Compatibility fallback when argon2 is unavailable."""

    class PasswordHasher:  # type: ignore[override]
        def __init__(self, iterations: int = 390000):
            self.iterations = iterations

        @staticmethod
        def _b64encode(raw: bytes) -> str:
            return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

        @staticmethod
        def _b64decode(text: str) -> bytes:
            padding = "=" * (-len(text) % 4)
            return base64.urlsafe_b64decode(text + padding)

        def hash(self, password: str) -> str:
            salt = secrets.token_bytes(16)
            digest = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt,
                self.iterations,
            )
            return (
                f"pbkdf2_sha256${self.iterations}$"
                f"{self._b64encode(salt)}${self._b64encode(digest)}"
            )

        def verify(self, hashed_password: str, plain_password: str) -> bool:
            if not hashed_password.startswith("pbkdf2_sha256$"):
                raise VerifyMismatchError("unsupported hash format without argon2")
            _, iterations_text, salt_text, digest_text = hashed_password.split("$", 3)
            iterations = int(iterations_text)
            salt = self._b64decode(salt_text)
            expected = self._b64decode(digest_text)
            actual = hashlib.pbkdf2_hmac(
                "sha256",
                plain_password.encode("utf-8"),
                salt,
                iterations,
            )
            if not hmac.compare_digest(actual, expected):
                raise VerifyMismatchError("password mismatch")
            return True


ph = PasswordHasher(memory_cost=65536, time_cost=3, parallelism=4) if ARGON2_AVAILABLE else PasswordHasher()
FAKE_HASH = ph.hash("stabled_dummy_password_for_constant_time")

if not ARGON2_AVAILABLE:
    incr_metric("auth.hash_fallback_total", algorithm="pbkdf2_sha256")
    log_event(
        "auth.hash_fallback_enabled",
        level="warning",
        algorithm="pbkdf2_sha256",
    )


DEV_JWT_SECRET_KEY = "eduagent-explicit-development-only-jwt-secret"
_INSECURE_JWT_SECRETS = frozenset({
    "",
    DEV_JWT_SECRET_KEY,
    "prod_secret_sign_key_997126_edu_agent",
    "change-me-in-production",
    "changeme",
    "secret",
})
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "").strip() or DEV_JWT_SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7


class SecurityConfigurationError(RuntimeError):
    """Raised when production authentication would use unsafe configuration."""


def _is_production() -> bool:
    environment = (
        os.getenv("APP_ENV")
        or os.getenv("ENVIRONMENT")
        or os.getenv("NODE_ENV")
        or "development"
    )
    return str(environment).strip().lower() in {"prod", "production"}


def validate_security_configuration() -> None:
    """Fail closed when production JWT signing is missing or predictable."""
    configured = os.getenv("JWT_SECRET_KEY", "").strip()
    if not _is_production():
        return
    if configured in _INSECURE_JWT_SECRETS or len(configured) < 32:
        raise SecurityConfigurationError(
            "JWT_SECRET_KEY must be a non-default secret of at least 32 characters in production"
        )


def _jwt_secret() -> str:
    validate_security_configuration()
    return os.getenv("JWT_SECRET_KEY", "").strip() or DEV_JWT_SECRET_KEY


class SecurityManager:
    """Password hashing and JWT token management."""

    @staticmethod
    def hash_password(password: str) -> str:
        return ph.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        try:
            return ph.verify(hashed_password, plain_password)
        except VerifyMismatchError:
            return False

    @staticmethod
    def execute_constant_time_fallback() -> None:
        try:
            ph.verify(FAKE_HASH, "invalid_match_trigger")
        except VerifyMismatchError:
            pass

    @staticmethod
    def create_token_pair(
        user_id: str,
        role: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, str]:
        secret = _jwt_secret()
        if _is_production() and not session_id:
            raise SecurityConfigurationError("Production JWTs require a persistent session_id")
        now = datetime.now(timezone.utc)

        access_jti = str(uuid.uuid4())
        access_expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_payload = {
            "sub": user_id,
            "role": role,
            "exp": access_expire,
            "jti": access_jti,
            "type": "access",
        }
        if session_id:
            access_payload["sid"] = session_id

        refresh_jti = str(uuid.uuid4())
        refresh_expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        refresh_payload = {
            "sub": user_id,
            "exp": refresh_expire,
            "jti": refresh_jti,
            "type": "refresh",
        }
        if session_id:
            refresh_payload["sid"] = session_id

        return {
            "access_token": jwt.encode(access_payload, secret, algorithm=ALGORITHM),
            "refresh_token": jwt.encode(refresh_payload, secret, algorithm=ALGORITHM),
            "access_jti": access_jti,
            "refresh_jti": refresh_jti,
            "session_id": session_id or "",
        }

    @staticmethod
    def decode_token(token: str) -> Dict[str, Any]:
        secret = _jwt_secret()
        try:
            payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
            if (
                _is_production()
                and payload.get("type") in {"access", "refresh"}
                and not payload.get("sid")
            ):
                raise ValueError("SESSION_REQUIRED")
            return payload
        except jwt.ExpiredSignatureError:
            raise ValueError("TOKEN_EXPIRED")
        except jwt.InvalidTokenError:
            raise ValueError("TOKEN_INVALID")
