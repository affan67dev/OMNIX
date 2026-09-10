from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.core.security import create_access_token, generate_otp, hash_otp, verify_otp_hash
from backend.services.supabase_db import insert_one, select_one, update_one, upsert_one

router = APIRouter(prefix="/api/v2/auth", tags=["Authentication v2"])
limiter = Limiter(key_func=get_remote_address)
OTP_TTL_MINUTES = int(os.getenv("OTP_TTL_MINUTES", "5"))
ENVIRONMENT = os.getenv("ENVIRONMENT", "production").lower()
SMS_WEBHOOK_URL = os.getenv("SMS_WEBHOOK_URL", "")


class PhoneRequest(BaseModel):
    country_code: str = Field(default="+91", min_length=2, max_length=6)
    phone_number: str = Field(min_length=6, max_length=15)
    purpose: str = Field(default="signup", pattern="^(signup|login|password_reset)$")

    @field_validator("phone_number")
    @classmethod
    def digits_only(cls, value: str) -> str:
        digits = re.sub(r"\D", "", value)
        if not 8 <= len(digits) <= 15:
            raise ValueError("Invalid phone number")
        return digits

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str) -> str:
        value = "+" + re.sub(r"\D", "", value)
        if not 1 <= len(value) <= 5:
            raise ValueError("Invalid country code")
        return value


class OTPVerifyRequest(BaseModel):
    challenge_id: str = Field(min_length=10, max_length=100)
    otp_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    username: Optional[str] = Field(default=None, min_length=3, max_length=30)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9_]{3,30}", value):
            raise ValueError("Username must contain only letters, numbers and underscores")
        return value


async def _send_otp(phone: str, otp: str, challenge_id: str) -> str:
    if not SMS_WEBHOOK_URL:
        if ENVIRONMENT != "production":
            return "development"
        raise HTTPException(status_code=503, detail="SMS delivery is not configured")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(SMS_WEBHOOK_URL, json={"to": phone, "otp": otp, "challenge_id": challenge_id})
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail="OTP delivery failed")
        return "sent"
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="OTP delivery failed") from exc


async def _find_profile_by_phone(phone: str) -> dict | None:
    return await select_one("profiles", filters={"mobile": phone}, columns="id,user_id,username,mobile")


async def _find_profile_by_username(username: str) -> dict | None:
    normalized = username.strip().lower()
    return await select_one("profiles", filters={"username": normalized}, columns="id,user_id,username,mobile")


async def _ensure_supabase_user(phone: str, username: str) -> dict:
    username = username.strip().lower()
    existing_phone = await _find_profile_by_phone(phone)
    if existing_phone:
        return existing_phone

    existing_username = await _find_profile_by_username(username)
    if existing_username:
        raise HTTPException(status_code=409, detail="Username is already taken")

    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    if not service_key or not supabase_url:
        raise HTTPException(status_code=503, detail="Supabase authentication is not configured")

    password = uuid4().hex + uuid4().hex
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{supabase_url}/auth/v1/admin/users",
            headers={"apikey": service_key, "Authorization": f"Bearer {service_key}", "Content-Type": "application/json"},
            json={"phone": phone, "phone_confirm": True, "password": password, "user_metadata": {"username": username, "mobile": phone}},
        )
    if response.status_code >= 400:
        detail = response.text
        if "already registered" in detail.lower() or "already exists" in detail.lower():
            existing = await _find_profile_by_phone(phone)
            if existing:
                return existing
        raise HTTPException(status_code=502, detail="Unable to create account")

    auth_user = response.json()
    user_id = auth_user["id"]
    try:
        return await upsert_one(
            "profiles",
            {"user_id": user_id, "username": username, "mobile": phone},
            "user_id",
        )
    except RuntimeError as exc:
        # PostgreSQL remains the final race-safe uniqueness authority.
        if "profiles_username_ci_unique" in str(exc) or "duplicate key" in str(exc).lower():
            raise HTTPException(status_code=409, detail="Username is already taken") from exc
        raise


@router.post("/phone/request", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("3/minute")
async def request_phone_otp(request: Request, payload: PhoneRequest):
    phone = f"{payload.country_code}{payload.phone_number}"
    existing = await _find_profile_by_phone(phone)
    if payload.purpose == "signup" and existing:
        raise HTTPException(status_code=409, detail="Phone number is already registered")
    if payload.purpose == "login" and not existing:
        raise HTTPException(status_code=404, detail="Account not found")

    challenge_id = str(uuid4())
    otp = generate_otp()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES)
    await insert_one(
        "phone_otp_challenges",
        {
            "id": challenge_id,
            "phone_e164": phone,
            "otp_hash": hash_otp(challenge_id, otp),
            "purpose": payload.purpose,
            "expires_at": expires_at.isoformat(),
            "requested_ip": request.client.host if request.client else None,
            "user_id": existing.get("user_id") if existing else None,
        },
    )
    delivery = await _send_otp(phone, otp, challenge_id)
    response = {"success": True, "challenge_id": challenge_id, "expires_in": OTP_TTL_MINUTES * 60, "delivery": delivery}
    if ENVIRONMENT != "production":
        response["development_otp"] = otp
    return response


@router.post("/phone/verify")
@limiter.limit("10/minute")
async def verify_phone_otp(request: Request, payload: OTPVerifyRequest):
    challenge = await select_one(
        "phone_otp_challenges",
        filters={"id": payload.challenge_id},
        columns="id,phone_e164,otp_hash,purpose,attempts,max_attempts,expires_at,consumed_at,user_id",
    )
    if not challenge:
        raise HTTPException(status_code=404, detail="OTP challenge not found")
    if challenge.get("consumed_at"):
        raise HTTPException(status_code=400, detail="OTP already used")
    expires_at = datetime.fromisoformat(str(challenge["expires_at"]).replace("Z", "+00:00"))
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="OTP expired")
    attempts = int(challenge.get("attempts") or 0)
    if attempts >= int(challenge.get("max_attempts") or 5):
        raise HTTPException(status_code=429, detail="Too many OTP attempts")
    if not verify_otp_hash(payload.challenge_id, payload.otp_code, challenge["otp_hash"]):
        await update_one("phone_otp_challenges", filters={"id": payload.challenge_id}, payload={"attempts": attempts + 1})
        raise HTTPException(status_code=400, detail="Invalid OTP")

    phone = challenge["phone_e164"]
    profile = await _find_profile_by_phone(phone)
    if profile is None:
        if not payload.username:
            raise HTTPException(status_code=409, detail="Username is required for a new account")
        profile = await _ensure_supabase_user(phone, payload.username)
    elif payload.username and payload.username != profile.get("username"):
        raise HTTPException(status_code=409, detail="Account already exists; username cannot be changed during login")

    await update_one("phone_otp_challenges", filters={"id": payload.challenge_id}, payload={"consumed_at": datetime.now(timezone.utc).isoformat(), "user_id": profile["user_id"]})

    token, jti, expires_at = create_access_token(str(profile["user_id"]), phone, profile["username"])
    await insert_one(
        "auth_sessions",
        {"user_id": profile["user_id"], "token_jti": jti, "expires_at": expires_at.isoformat(), "ip_address": request.client.host if request.client else None, "user_agent": request.headers.get("user-agent")},
    )
    return {"success": True, "access_token": token, "token_type": "bearer", "expires_at": expires_at.isoformat(), "user": {"id": profile["user_id"], "username": profile["username"], "phone": phone}}


@router.post("/logout")
async def logout(request: Request):
    from backend.core.security import decode_access_token

    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = decode_access_token(authorization.split(" ", 1)[1])
    await update_one("auth_sessions", filters={"token_jti": payload["jti"]}, payload={"revoked_at": datetime.now(timezone.utc).isoformat()})
    return {"success": True}
