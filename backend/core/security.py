from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Annotated
from uuid import uuid4

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.services.supabase_db import select_one

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_TTL_MINUTES = int(os.getenv("JWT_TTL_MINUTES", "60"))
OTP_PEPPER = os.getenv("OTP_PEPPER", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "") or os.getenv("VITE_SUPABASE_ANON_KEY", "")

bearer = HTTPBearer(auto_error=False)


def _require_secret(value: str, name: str) -> str:
    if not value or len(value) < 32:
        raise RuntimeError(f"{name} must be configured with at least 32 characters")
    return value


def create_access_token(user_id: str, phone: str, username: str) -> tuple[str, str, datetime]:
    secret = _require_secret(JWT_SECRET, "JWT_SECRET")
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=JWT_TTL_MINUTES)
    jti = uuid4().hex
    payload = {
        "sub": str(user_id),
        "phone": phone,
        "username": username,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM), jti, expires_at


def decode_access_token(token: str) -> dict[str, Any]:
    secret = _require_secret(JWT_SECRET, "JWT_SECRET")
    try:
        payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM], options={"require": ["sub", "jti", "iat", "exp", "type"]})
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired access token") from exc
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token")
    return payload


async def _validate_supabase_token(token: str) -> dict[str, Any]:
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(status_code=503, detail="Authentication service is not configured")
    if not token or len(token) > 8192:
        raise HTTPException(status_code=401, detail="Invalid access token")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{SUPABASE_URL}/auth/v1/user",
                headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Authentication service unavailable") from exc
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")
    try:
        user = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid authentication response") from exc
    if not isinstance(user, dict) or not user.get("id"):
        raise HTTPException(status_code=401, detail="Invalid access token")
    return {
        "sub": str(user["id"]),
        "email": user.get("email", ""),
        "username": (user.get("user_metadata") or {}).get("username", ""),
        "phone": user.get("phone", ""),
        "type": "supabase",
    }


async def get_current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    token = credentials.credentials

    # Prefer the application's own revocable session tokens when they are supplied.
    if JWT_SECRET:
        try:
            payload = decode_access_token(token)
            try:
                session = await select_one("auth_sessions", filters={"token_jti": payload["jti"]}, columns="user_id,expires_at,revoked_at")
            except Exception as exc:
                raise HTTPException(status_code=503, detail="Authentication store unavailable") from exc
            if not session or session.get("revoked_at"):
                raise HTTPException(status_code=401, detail="Session revoked")
            expires_at = session.get("expires_at")
            if expires_at and datetime.fromisoformat(str(expires_at).replace("Z", "+00:00")) <= datetime.now(timezone.utc):
                raise HTTPException(status_code=401, detail="Session expired")
            if str(session.get("user_id")) != str(payload.get("sub")):
                raise HTTPException(status_code=401, detail="Invalid session")
            return payload
        except HTTPException as exc:
            # A token that successfully decoded but failed a revocation/session check must
            # not be silently upgraded to a different authentication mechanism.
            if exc.detail in {"Session revoked", "Session expired", "Invalid session"}:
                raise

    # Legacy frontend authentication uses Supabase access tokens. Validate them against
    # Supabase instead of accepting a client-supplied user id header.
    return await _validate_supabase_token(token)


CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(challenge_id: str, otp: str) -> str:
    pepper = _require_secret(OTP_PEPPER, "OTP_PEPPER")
    return hmac.new(pepper.encode(), f"{challenge_id}:{otp}".encode(), hashlib.sha256).hexdigest()


def verify_otp_hash(challenge_id: str, otp: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(challenge_id, otp), expected_hash)
