from __future__ import annotations

import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

# Legacy compatibility module. The production application uses Supabase-backed
# auth routes. This module intentionally refuses to operate in production so
# an in-memory auth implementation cannot be deployed accidentally.
_otp_store: Dict[str, Dict[str, Any]] = {}
_users: Dict[str, Dict[str, Any]] = {}

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
JWT_SECRET = os.getenv("OMNIX_JWT_SECRET", "")
JWT_ALGORITHM = os.getenv("OMNIX_JWT_ALGORITHM", "HS256")
OTP_EXPIRY_SECONDS = int(os.getenv("OMNIX_OTP_EXPIRY_SECONDS", "300"))
JWT_EXPIRY_DAYS = int(os.getenv("OMNIX_JWT_EXPIRY_DAYS", "30"))

if ENVIRONMENT in {"production", "prod"} and not JWT_SECRET:
    raise RuntimeError("OMNIX_JWT_SECRET is required if the legacy auth module is enabled")

router = APIRouter()


class SendOTPRequest(BaseModel):
    phone: str


class VerifyOTPRequest(BaseModel):
    phone: str
    otp: str


def _now_epoch() -> int:
    return int(time.time())


def _generate_otp() -> str:
    return f"{secrets.randbelow(1000000):06d}"


def _create_jwt_for_user(user_id: str, phone: str) -> str:
    if not JWT_SECRET:
        raise RuntimeError("OMNIX_JWT_SECRET is required")
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=JWT_EXPIRY_DAYS)
    payload = {
        "sub": user_id,
        "phone": phone,
        "exp": int(expires.timestamp()),
        "iat": int(now.timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


@router.post("/send", status_code=200)
async def send_otp(req: SendOTPRequest):
    if ENVIRONMENT in {"production", "prod"}:
        raise HTTPException(status_code=503, detail="Legacy in-memory OTP authentication is disabled in production")

    phone = req.phone.strip()
    if not phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="phone is required")
    otp = _generate_otp()
    expires_at = _now_epoch() + OTP_EXPIRY_SECONDS
    _otp_store[phone] = {"otp": otp, "expires_at": expires_at}
    # Never log the OTP. Local development can inspect the test store directly.
    return {"status": "ok", "sent": True, "expires_in": OTP_EXPIRY_SECONDS}


@router.post("/verify", status_code=200)
async def verify_otp(req: VerifyOTPRequest):
    phone = req.phone.strip()
    otp = req.otp.strip()
    if not phone or not otp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="phone and otp required")
    entry = _otp_store.get(phone)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no otp pending for this phone")
    if _now_epoch() > int(entry["expires_at"]):
        _otp_store.pop(phone, None)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="otp expired")
    if not secrets.compare_digest(str(entry["otp"]), otp):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid otp")
    user = _users.get(phone)
    if user is None:
        user_id = f"user-{secrets.token_hex(6)}"
        user = {"id": user_id, "phone": phone, "created_at": datetime.now(timezone.utc).isoformat()}
        _users[phone] = user
    _otp_store.pop(phone, None)
    token = _create_jwt_for_user(user["id"], phone)
    return {"token": token, "user": user}
