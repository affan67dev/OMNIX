from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_TTL_MINUTES = int(os.getenv("JWT_TTL_MINUTES", "60"))
OTP_PEPPER = os.getenv("OTP_PEPPER", "")

bearer = HTTPBearer(auto_error=False)


def _require_secret(value: str, name: str) -> str:
    if not value or len(value) < 32:
        raise RuntimeError(f"{name} must be configured with at least 32 characters")
    return value


def create_access_token(user_id: str, phone: str, username: str) -> str:
    secret = _require_secret(JWT_SECRET, "JWT_SECRET")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "phone": phone,
        "username": username,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=JWT_TTL_MINUTES)).timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    secret = _require_secret(JWT_SECRET, "JWT_SECRET")
    try:
        payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM], options={"require": ["sub", "iat", "exp", "type"]})
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired access token") from exc
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token")
    return payload


async def get_current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return decode_access_token(credentials.credentials)


CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(challenge_id: str, otp: str) -> str:
    pepper = _require_secret(OTP_PEPPER, "OTP_PEPPER")
    return hmac.new(pepper.encode(), f"{challenge_id}:{otp}".encode(), hashlib.sha256).hexdigest()


def verify_otp_hash(challenge_id: str, otp: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(challenge_id, otp), expected_hash)
