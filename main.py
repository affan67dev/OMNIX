"""
OMNIX - Private Social Network Backend
Production-ready FastAPI application with Supabase integration.
"""

from fastapi import FastAPI, HTTPException, Depends, Request, Header
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field, field_validator
import asyncio
import json
import os
import httpx
import uuid
import secrets
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from typing import Optional, Dict, List, Any
import re
from datetime import datetime, timezone, timedelta
from backend.services.social_graph import SocialGraphError, social_graph
from backend.routes.settings_management import router as settings_management_router
from backend.routes.billing import router as billing_router
from backend.routes.push_notifications import router as push_notifications_router
from backend.services.push_notifications import PushNotificationError, push_notification_service
from backend.routes.zero_knowledge import router as zero_knowledge_router
from backend.routes.admin_oob_auth import router as admin_oob_auth_router
from backend.routes.auth_v2 import router as auth_v2_router
from backend.routes.stories_v2 import router as stories_v2_router
from backend.routes.reels_v2 import router as reels_v2_router
from backend.core.security import hash_otp, verify_otp_hash

app = FastAPI(
    title="OMNIX",
    description="Private Social Network API",
    version="1.0.0",
    docs_url="/docs" if os.getenv("ENABLE_DOCS", "false").lower() == "true" else None,
    redoc_url=None
)

app.include_router(settings_management_router)
app.include_router(billing_router)
app.include_router(push_notifications_router)
app.include_router(zero_knowledge_router)
app.include_router(admin_oob_auth_router)
app.include_router(auth_v2_router)
app.include_router(stories_v2_router)
app.include_router(reels_v2_router)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[os.getenv("GLOBAL_RATE_LIMIT", "120/minute")],
    storage_uri=os.getenv("RATE_LIMIT_STORAGE_URI", "memory://"),
    headers_enabled=True,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def backend_request_guard(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            body_size = int(content_length)
        except ValueError:
            body_size = 0
        content_type = request.headers.get("content-type", "").lower()
        max_body = 1 * 1024 * 1024 if "application/json" in content_type else 25 * 1024 * 1024
        if body_size > max_body:
            return JSONResponse(status_code=413, content={"success": False, "detail": "Request payload is too large", "request_id": request_id})
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    except HTTPException:
        raise
    except Exception as error:
        add_admin_log("ERROR", f"Unhandled exception {request_id}: {error}")
        return JSONResponse(status_code=500, content={"success": False, "detail": "Internal server error", "request_id": request_id})
    response.headers["X-Request-Id"] = request_id
    return response

PUBLIC_API_PATHS = {
    "/api/auth/login", "/api/auth/signup", "/api/auth/otp/send", "/api/auth/otp/verify",
    "/api/auth/availability", "/api/auth/forgot-password", "/api/auth/refresh", "/api/auth/google", "/api/health",
}

async def _validate_supabase_access_token(token: str) -> str:
    from backend.core.security import decode_access_token
    if os.getenv("JWT_SECRET", ""):
        try:
            payload = decode_access_token(token)
            session = await supabase_db_request("GET", "auth_sessions", query=f"?select=user_id,expires_at,revoked_at&token_jti=eq.{payload['jti']}&limit=1")
            row = session[0] if session else None
            if not row or row.get("revoked_at") or str(row.get("user_id")) != str(payload.get("sub")):
                raise HTTPException(status_code=401, detail="Invalid or revoked session")
            expiry = _parse_datetime(row.get("expires_at"))
            if expiry and expiry <= datetime.now(timezone.utc):
                raise HTTPException(status_code=401, detail="Session expired")
            return str(payload["sub"])
        except HTTPException:
            raise
        except Exception:
            pass
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(status_code=503, detail="Authentication service is not configured")
    if not token or len(token) > 8192:
        raise HTTPException(status_code=401, detail="Invalid access token")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{SUPABASE_URL}/auth/v1/user", headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"})
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Authentication service unavailable") from exc
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")
    try:
        user = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid authentication response") from exc
    user_id = user.get("id") if isinstance(user, dict) else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid access token")
    return str(user_id)

@app.middleware("http")
async def authenticated_api_guard(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or not path.startswith("/api/"):
        return await call_next(request)
    if path in PUBLIC_API_PATHS or path.startswith("/api/admin-auth/"):
        return await call_next(request)
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        return JSONResponse(status_code=401, content={"success": False, "detail": "Authentication required", "request_id": getattr(request.state, "request_id", None)})
    token = authorization.split(" ", 1)[1].strip()
    try:
        user_id = await _validate_supabase_access_token(token)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"success": False, "detail": exc.detail, "request_id": getattr(request.state, "request_id", None)})
    request.scope["headers"] = [(key, value) for key, value in request.scope.get("headers", []) if key.lower() != b"x-user-id"] + [(b"x-user-id", user_id.encode("utf-8"))]
    return await call_next(request)

@app.exception_handler(RequestValidationError)
async def app_validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"success": False, "detail": "Invalid request payload", "request_id": getattr(request.state, "request_id", None)})

@app.exception_handler(HTTPException)
async def app_http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"success": False, "detail": exc.detail, "request_id": getattr(request.state, "request_id", None)})


def _cors_origins() -> list[str]:
    configured = os.getenv("CORS_ORIGINS", "")
    candidates = [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]
    frontend = os.getenv("FRONTEND_URL", "").strip().rstrip("/")
    if frontend:
        candidates.append(frontend)
    if not candidates and os.getenv("ENVIRONMENT", "production").lower() != "production":
        candidates.extend(["http://localhost:5173", "http://localhost:3000", "http://localhost:80", "http://localhost"])
    return list(dict.fromkeys(candidates))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-Id", "X-Admin-Key"],
    allow_credentials=True,
)

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

FLAG_KEYWORDS = {"spam", "scam", "phishing", "fraud", "hate", "violence", "abuse", "harassment", "explicit", "sexual", "self-harm", "weapon", "bomb", "terror"}
ACTION_KEYWORDS = {"spam", "scam", "abuse", "harass", "impersonation", "fraud"}

def get_supabase_headers(use_service_key: bool = False) -> dict:
    key = SUPABASE_SERVICE_KEY if use_service_key else SUPABASE_ANON_KEY
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}

async def supabase_auth_request(endpoint: str, payload: dict, method: str = "POST") -> dict:
    if not SUPABASE_URL: raise HTTPException(status_code=500, detail="Supabase configuration missing")
    url = f"{SUPABASE_URL}/auth/v1/{endpoint}"
    headers = get_supabase_headers()
    async with httpx.AsyncClient(timeout=30.0) as client:
        if method == "POST": response = await client.post(url, json=payload, headers=headers)
        else: response = await client.get(url, headers=headers)
    if response.status_code >= 400:
        try:
            error_data = response.json()
            detail = error_data.get("msg") or error_data.get("error_description") or error_data.get("message") or "Authentication failed"
        except Exception:
            detail = "Authentication failed"
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()

async def supabase_auth_user_request(access_token: str) -> dict:
    if not SUPABASE_URL or not SUPABASE_ANON_KEY: raise HTTPException(status_code=503, detail="Supabase configuration missing")
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{SUPABASE_URL}/auth/v1/user", headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {access_token}"})
    if response.status_code >= 400: raise HTTPException(status_code=401, detail="Invalid or expired access token")
    try: return response.json()
    except ValueError as exc: raise HTTPException(status_code=502, detail="Invalid authentication response") from exc
