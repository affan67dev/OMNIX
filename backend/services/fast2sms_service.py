from __future__ import annotations

import os
import re
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class Fast2SMSResult:
    success: bool
    request_id: str | None = None
    error_code: str | None = None


def normalize_indian_mobile(phone_e164: str) -> str:
    value = str(phone_e164 or "").strip()
    digits = re.sub(r"\D", "", value)
    if value.startswith("+91"):
        digits = digits[2:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if not re.fullmatch(r"[6-9]\d{9}", digits):
        raise ValueError("Invalid Indian mobile number")
    return digits


async def send_otp(phone_e164: str, otp: str, *, challenge_id: str) -> Fast2SMSResult:
    api_key = os.getenv("FAST2SMS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Fast2SMS is not configured")

    mobile = normalize_indian_mobile(phone_e164)
    if not re.fullmatch(r"\d{6,10}", otp):
        raise ValueError("Invalid OTP format")

    base_url = os.getenv("FAST2SMS_BASE_URL", "https://www.fast2sms.com/dev").rstrip("/")
    otp_id = os.getenv("FAST2SMS_OTP_ID", "").strip()
    if not otp_id:
        raise RuntimeError("Fast2SMS OTP template is not configured")

    expiry = int(os.getenv("FAST2SMS_OTP_EXPIRY_MINUTES", os.getenv("OTP_TTL_MINUTES", "5")))
    payload = {
        "mobile": mobile,
        "otp_id": otp_id,
        "otp_expiry": max(1, min(expiry, 10080)),
        "otp_length": len(otp),
        "otp": otp,
        "udf1": challenge_id,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{base_url}/otp/send",
                headers={"Authorization": api_key, "Content-Type": "application/json"},
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise RuntimeError("Fast2SMS request timed out") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError("Fast2SMS request failed") from exc

    if response.status_code in (401, 403):
        raise RuntimeError("Fast2SMS authentication failed")
    if response.status_code >= 400:
        # Provider response bodies are deliberately not propagated to clients because
        # they may contain operational details. Keep only a safe internal error code.
        raise RuntimeError(f"Fast2SMS provider rejected request ({response.status_code})")

    try:
        body = response.json()
    except ValueError:
        body = {}

    if isinstance(body, dict) and body.get("return") is False:
        message = str(body.get("message") or body.get("msg") or "provider_rejected").lower()
        raise RuntimeError(f"Fast2SMS provider rejected request: {message[:80]}")

    request_id = None
    if isinstance(body, dict):
        request_id = body.get("request_id") or body.get("requestId")
    return Fast2SMSResult(success=True, request_id=str(request_id) if request_id else None)
