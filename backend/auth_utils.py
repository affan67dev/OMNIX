from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException

from backend.services.billing import billing_service
from backend.services.settings_management import settings_management
from backend.services.social_graph import social_graph


def extract_bearer_token(authorization: Optional[str], access_token: Optional[str] = None) -> str:
    if access_token:
        return access_token.strip()

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return token


async def fetch_authenticated_user(authorization: Optional[str], access_token: Optional[str] = None) -> Dict[str, Any]:
    token = extract_bearer_token(authorization, access_token)
    supabase_url = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL", "")
    supabase_anon_key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY", "")
    if not supabase_url or not supabase_anon_key:
        raise HTTPException(status_code=503, detail="Authentication is not configured")

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{supabase_url}/auth/v1/user",
            headers={
                "apikey": supabase_anon_key,
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )

    if response.status_code >= 400:
        try:
            payload = response.json()
        except Exception:
            payload = {}
        detail = payload.get("msg") or payload.get("error_description") or payload.get("message") or "Authentication failed"
        raise HTTPException(status_code=401, detail=detail)

    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("id"):
        raise HTTPException(status_code=401, detail="Invalid authenticated user payload")
    return payload


def ensure_application_user(auth_user: Dict[str, Any]) -> str:
    user_id = str(auth_user.get("id") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid authenticated user payload")

    metadata = auth_user.get("user_metadata") or {}
    email = str(auth_user.get("email") or "").strip().lower()
    username = (
        str(metadata.get("username") or "").strip()
        or (email.split("@", 1)[0] if email else "")
        or f"user-{user_id[:8]}"
    )
    display_name = (
        str(metadata.get("full_name") or "").strip()
        or str(metadata.get("display_name") or "").strip()
        or username
    )
    phone = str(metadata.get("mobile") or metadata.get("phone") or auth_user.get("phone") or "").strip()

    social_graph.ensure_user(user_id, username=username, display_name=display_name)
    settings_management.ensure_user(user_id, email=email, phone_number=phone, username=username)
    billing_service.ensure_user(user_id)
    return user_id


async def require_authenticated_user_id(authorization: Optional[str], access_token: Optional[str] = None) -> str:
    return ensure_application_user(await fetch_authenticated_user(authorization, access_token))


async def require_admin_user(authorization: Optional[str], access_token: Optional[str] = None) -> Dict[str, Any]:
    auth_user = await fetch_authenticated_user(authorization, access_token)
    ensure_application_user(auth_user)

    app_metadata = auth_user.get("app_metadata") or {}
    user_metadata = auth_user.get("user_metadata") or {}
    roles = {
        str(app_metadata.get("role") or "").strip().lower(),
        str(user_metadata.get("role") or "").strip().lower(),
    }

    configured_ids = {item.strip() for item in os.getenv("ADMIN_USER_IDS", "").split(",") if item.strip()}
    configured_emails = {item.strip().lower() for item in os.getenv("ADMIN_USER_EMAILS", "").split(",") if item.strip()}

    if (
        "admin" in roles
        or str(auth_user.get("id") or "") in configured_ids
        or str(auth_user.get("email") or "").strip().lower() in configured_emails
    ):
        return auth_user

    raise HTTPException(status_code=403, detail="Admin role required")
