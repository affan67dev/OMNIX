"""
OMNIX - Private Social Network Backend
Production-ready FastAPI application with Supabase integration.
"""

from fastapi import FastAPI, HTTPException, Depends, Request, Header
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, field_validator
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

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def backend_request_guard(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    except HTTPException:
        raise
    except Exception as error:
        add_admin_log("ERROR", f"Unhandled exception {request_id}: {error}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": "Internal server error", "request_id": request_id},
        )
    response.headers["X-Request-Id"] = request_id
    return response


@app.exception_handler(HTTPException)
async def app_http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "detail": exc.detail,
            "request_id": getattr(request.state, "request_id", None),
        },
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:80",
        "http://localhost",
        os.getenv("FRONTEND_URL", "")
    ],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Mount static files
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Supabase Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

FLAG_KEYWORDS = {
    "spam", "scam", "phishing", "fraud", "hate", "violence", "abuse", "harassment",
    "explicit", "sexual", "self-harm", "weapon", "bomb", "terror"
}
ACTION_KEYWORDS = {
    "spam", "scam", "abuse", "harass", "impersonation", "fraud"
}


def get_supabase_headers(use_service_key: bool = False) -> dict:
    """Return headers for Supabase API calls."""
    key = SUPABASE_SERVICE_KEY if use_service_key else SUPABASE_ANON_KEY
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


async def supabase_auth_request(endpoint: str, payload: dict, method: str = "POST") -> dict:
    """Make authenticated request to Supabase Auth API."""
    if not SUPABASE_URL:
        raise HTTPException(status_code=500, detail="Supabase configuration missing")

    url = f"{SUPABASE_URL}/auth/v1/{endpoint}"
    headers = get_supabase_headers()

    async with httpx.AsyncClient(timeout=30.0) as client:
        if method == "POST":
            response = await client.post(url, json=payload, headers=headers)
        else:
            response = await client.get(url, headers=headers)

        if response.status_code >= 400:
            try:
                error_data = response.json()
                detail = error_data.get("msg") or error_data.get("error_description") or error_data.get("message") or "Authentication failed"
            except Exception:
                detail = response.text or "Authentication failed"
            raise HTTPException(status_code=response.status_code, detail=detail)

        return response.json()


async def supabase_db_request(method: str, table: str, payload: dict = None, query: str = "") -> dict:
    """Make request to Supabase Database REST API."""
    if not SUPABASE_URL:
        raise HTTPException(status_code=500, detail="Supabase configuration missing")

    url = f"{SUPABASE_URL}/rest/v1/{table}{query}"
    headers = get_supabase_headers()
    headers["Prefer"] = "return=representation"

    async with httpx.AsyncClient(timeout=30.0) as client:
        if method == "POST":
            response = await client.post(url, json=payload, headers=headers)
        elif method == "GET":
            response = await client.get(url, headers=headers)
        elif method == "PATCH":
            response = await client.patch(url, json=payload, headers=headers)
        elif method == "DELETE":
            response = await client.delete(url, headers=headers)
        else:
            raise ValueError(f"Unsupported method: {method}")

        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)

        return response.json()


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO timestamp and return a timezone-aware datetime."""
    if not value:
        return None

    try:
        normalized = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def auto_flag_content(content: str, action: Optional[str] = None) -> dict:
    """Evaluate text and user action to decide whether content should be flagged."""
    normalized_text = (content or "").lower()
    normalized_action = (action or "").lower()
    reasons = []

    matched_keywords = [keyword for keyword in FLAG_KEYWORDS if keyword in normalized_text]
    if matched_keywords:
        reasons.append("keyword")

    action_matches = [keyword for keyword in ACTION_KEYWORDS if keyword in normalized_action]
    if action_matches:
        reasons.append("action")

    flagged = bool(reasons)
    if flagged and ("spam" in matched_keywords or "spam" in action_matches or "scam" in matched_keywords or "scam" in action_matches):
        severity = "high"
    elif flagged:
        severity = "medium"
    else:
        severity = "none"

    return {
        "flagged": flagged,
        "reasons": reasons,
        "severity": severity,
    }


def rank_posts_for_feed(posts: list[dict]) -> list[dict]:
    """Rank posts by engagement and recency while filtering out likely flagged content."""
    ranked = []
    now = datetime.now(timezone.utc)

    for post in posts or []:
        if not isinstance(post, dict):
            continue

        moderation = auto_flag_content(post.get("content") or "", post.get("action") or "")
        if moderation["flagged"]:
            continue

        likes = int(post.get("likes") or 0)
        comments = int(post.get("comments") or 0)
        shares = int(post.get("shares") or 0)
        created_at = _parse_datetime(post.get("created_at"))

        if created_at is None:
            age_hours = 72
        else:
            age_hours = max(0.0, (now - created_at).total_seconds() / 3600)

        recency_boost = max(0.0, (48 - age_hours) / 48) * 5
        score = likes * 2 + comments * 4 + shares * 6 + recency_boost
        ranked.append({"post": post, "score": score})

    ranked.sort(key=lambda item: (-item["score"], item["post"].get("created_at") or ""))
    return [item["post"] for item in ranked]


def verify_admin_request(authorization: Optional[str], role: Optional[str] = None, x_role: Optional[str] = None) -> bool:
    """Validate that an admin-only request is coming from an authorized role."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    normalized_role = (role or x_role or "").lower()
    if normalized_role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")

    return True


def trigger_signup_notification_webhook(payload: dict) -> dict:
    """Prepare a lightweight webhook payload for phone notification dispatch."""
    username = (payload or {}).get("username") or "unknown"
    email = (payload or {}).get("email") or ""
    return {
        "status": "queued",
        "channel": "phone",
        "recipient": email or f"{username}@register",
        "message": f"Welcome {username}! Your OMNIX account is ready.",
        "metadata": {
            "source": "signup-webhook",
            "payload": json.dumps(payload, sort_keys=True),
        },
    }


# Request Models with Validation
class LoginRequest(BaseModel):
    identity: str
    password: str


class SignupRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""
    mobile: Optional[str] = ""
    display_nickname: Optional[str] = ""
    phone_country_code: Optional[str] = "+1"
    phone_number: Optional[str] = ""
    otp_challenge_id: Optional[str] = ""
    legal_accepted: Optional[bool] = False

    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        if len(v) < 3:
            raise ValueError('Username must be at least 3 characters')
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('Username can only contain letters, numbers, and underscores')
        return v.lower()

    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError('Password must be at least 6 characters')
        return v


class ForgotPasswordRequest(BaseModel):
    mode: str = "email"
    email: Optional[EmailStr] = None
    country_code: Optional[str] = "+1"
    phone_number: Optional[str] = None


class OtpSendRequest(BaseModel):
    country_code: str = "+1"
    phone_number: str


class OtpVerifyRequest(BaseModel):
    challenge_id: str
    otp_code: str


class AvailabilityRequest(BaseModel):
    email: EmailStr
    username: str


class PostRequest(BaseModel):
    content: str
    image_url: Optional[str] = None
    visibility: Optional[str] = 'public'
    location: Optional[str] = 'Secure feed'
    tags: Optional[List[str]] = []


class PostInteractionRequest(BaseModel):
    interaction_type: str
    metadata: Optional[Dict[str, Any]] = None


class PostCommentRequest(BaseModel):
    comment: str


class StoryCreateRequest(BaseModel):
    media_name: str
    media_type: str = 'image'
    caption: Optional[str] = ''
    mentions: Optional[List[str]] = []
    location_name: Optional[str] = ''
    music_track: Optional[str] = ''
    overlay_text: Optional[str] = ''
    overlay_emoji: Optional[str] = ''
    overlay_x: Optional[float] = 0.5
    overlay_y: Optional[float] = 0.5
    overlay_scale: Optional[float] = 1.0


class SendMessageRequest(BaseModel):
    text: Optional[str] = None
    sender_id: Optional[str] = 'me'
    sender_name: Optional[str] = 'You'
    encrypted_payload: Optional[str] = None
    encryption_nonce: Optional[str] = None
    sender_ephemeral_public_key: Optional[str] = None
    recipient_key_id: Optional[str] = None
    encryption_algorithm: Optional[str] = None


class PrivacyUpdateRequest(BaseModel):
    is_private: bool
    is_blocked_from_search: Optional[bool] = None


class BlockUserRequest(BaseModel):
    reason: Optional[str] = None


class MuteUserRequest(BaseModel):
    mute_type: str
    duration: str


class ReportUserRequest(BaseModel):
    reason: str
    description: str = ""


class ChatSettingsUpdateRequest(BaseModel):
    custom_wallpaper: Optional[str] = None
    custom_nickname: Optional[str] = None
    is_muted: Optional[bool] = None
    mute_duration: Optional[str] = None
    notification_sound_enabled: Optional[bool] = None
    vibration_enabled: Optional[bool] = None


class ChatConversationStore:
    def __init__(self) -> None:
        self.listeners: Dict[str, List[asyncio.Queue]] = {}


chat_store = ChatConversationStore()


in_memory_posts: List[dict] = [
    {
        'id': 'seed-post-1',
        'content': 'Building the cleanest ecosystem network live.',
        'image_url': None,
        'visibility': 'public',
        'location': 'Secure Server Grid',
        'tags': ['#Ecosystem', '#BITE', '#Privacy'],
        'mentions': ['@shadow_dev'],
        'likes': 1424,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'user_id': 'local-user',
        'approved': True,
    },
    {
        'id': 'seed-post-2',
        'content': 'Self-healing recommendation pipeline integrated successfully.',
        'image_url': None,
        'visibility': 'followers',
        'location': 'Distributed Node 4',
        'tags': ['#Algorithm', '#AI', '#NextGen'],
        'mentions': ['@Aadil_724'],
        'likes': 890,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'user_id': 'user-ari',
        'approved': False,
    },
    {
        'id': 'seed-post-3',
        'content': 'Notification relay tuning finished ahead of schedule.',
        'image_url': None,
        'visibility': 'public',
        'location': 'Bridge Segment',
        'tags': ['#Notifications', '#Realtime'],
        'mentions': ['@nova_ai'],
        'likes': 642,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'user_id': 'user-nova',
        'approved': True,
    },
]

in_memory_stories: List[dict] = [
    {
        'id': 'story-1',
        'user_id': 'local-user',
        'username': 'operator_bite',
        'media_name': 'secure-grid-launch.jpg',
        'media_type': 'image',
        'caption': 'Night release is stable. Monitoring all nodes.',
        'mentions': ['@shadow_dev'],
        'location_name': 'Secure Server Grid',
        'music_track': 'Neon Circuit - Pulse Driver',
        'overlay_text': 'Launch Window',
        'overlay_emoji': '🚀',
        'overlay_x': 0.55,
        'overlay_y': 0.42,
        'overlay_scale': 1.0,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'expires_at': (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        'viewers': [],
    }
]

post_interaction_events: List[dict] = []

admin_logs_state: List[dict] = [
    {'id': 1, 'level': 'INFO', 'message': 'Secure feed sync completed', 'time': '2m ago'},
    {'id': 2, 'level': 'WARN', 'message': 'Private visibility filter toggled', 'time': '9m ago'},
    {'id': 3, 'level': 'INFO', 'message': 'Chat stream connected to shadow-node', 'time': '14m ago'},
]

otp_challenges: Dict[str, Dict[str, Any]] = {}
auth_identity_registry: Dict[str, Any] = {
    "phones": {},
    "emails": set(),
    "usernames": set(),
}


def add_admin_log(level: str, message: str) -> None:
    entry = {
        'id': int(datetime.now(timezone.utc).timestamp() * 1000),
        'level': level,
        'message': message,
        'time': 'just now',
    }
    admin_logs_state.insert(0, entry)
    admin_logs_state[:] = admin_logs_state[:8]


def prune_expired_stories() -> None:
    now = datetime.now(timezone.utc)
    active_items: List[dict] = []
    for story in in_memory_stories:
        try:
            expires_at = datetime.fromisoformat(story.get('expires_at', ''))
        except Exception:
            expires_at = now
        if expires_at > now:
            active_items.append(story)
    in_memory_stories[:] = active_items


def normalize_phone(country_code: str, phone_number: str) -> str:
    cc = re.sub(r"[^\d+]", "", (country_code or "").strip())
    digits = re.sub(r"\D", "", (phone_number or "").strip())
    if not digits or len(digits) < 8:
        raise HTTPException(status_code=400, detail="Enter a valid phone number")
    if not cc.startswith("+"):
        cc = f"+{re.sub(r'\D', '', cc)}"
    return f"{cc}{digits}"


def normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def refresh_identity_registry() -> None:
    auth_identity_registry["usernames"] = {normalize_username(user.get("username", "")) for user in social_graph.users.values() if user.get("username")}


def is_username_conflict_error(detail: str) -> bool:
    normalized_detail = (detail or "").lower()
    return (
        "username already taken" in normalized_detail
        or "username is already taken" in normalized_detail
        or "profiles_username_canonical_unique_idx" in normalized_detail
        or "duplicate key value violates unique constraint" in normalized_detail and "username" in normalized_detail
    )


async def find_existing_username_profile(username: str) -> Optional[Dict[str, Any]]:
    normalized_username = normalize_username(username)
    if not normalized_username:
        return None

    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for field_name in ("username_canonical", "username"):
                response = await client.get(
                    f"{SUPABASE_URL}/rest/v1/profiles",
                    headers=get_supabase_headers(use_service_key=True),
                    params={
                        "select": "id,user_id,username",
                        field_name: f"eq.{normalized_username}",
                        "limit": "1",
                    },
                )
                if response.status_code == 200:
                    rows = response.json()
                    if rows:
                        return rows[0]
                if response.status_code not in (200, 400, 404):
                    raise HTTPException(status_code=502, detail="Unable to validate username")
    for user in social_graph.users.values():
        if normalize_username(user.get("username", "")) == normalized_username:
            return user
    return None


async def find_existing_phone_profile(phone: str) -> Optional[Dict[str, Any]]:
    normalized_phone = normalize_phone("+", phone)
    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/profiles",
                headers=get_supabase_headers(use_service_key=True),
                params={"select": "id,user_id,username,mobile", "mobile": f"eq.{normalized_phone}", "limit": "1"},
            )
            if response.status_code == 200:
                rows = response.json()
                if rows:
                    return rows[0]
    for user in social_graph.users.values():
        if normalize_phone("+", str(user.get("mobile", ""))) == normalized_phone:
            return user
    return None


async def find_existing_email_profile(email: str) -> Optional[Dict[str, Any]]:
    normalized_email = (email or "").strip().lower()
    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/profiles",
                headers=get_supabase_headers(use_service_key=True),
                params={"select": "id,user_id,username,email", "email": f"eq.{normalized_email}", "limit": "1"},
            )
            if response.status_code == 200:
                rows = response.json()
                if rows:
                    return rows[0]
    return None


async def send_signup_otp(phone: str, challenge_id: str, otp_code: str) -> dict:
    """Send an OTP through the configured provider or expose a development-only local value."""
    webhook = os.getenv("SMS_WEBHOOK_URL", "")
    if webhook:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook, json={"to": phone, "otp": otp_code, "challenge_id": challenge_id})
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail="OTP delivery failed")
        return {"status": "sent"}
    if os.getenv("ENVIRONMENT", "production").lower() != "production":
        return {"status": "development", "otp": otp_code}
    raise HTTPException(status_code=503, detail="SMS delivery is not configured")


async def send_phone_otp(country_code: str, phone_number: str, purpose: str = "signup") -> dict:
    """Create and persist an OTP challenge with a provider-independent delivery hook."""
    phone = normalize_phone(country_code, phone_number)
    if purpose == "signup" and await find_existing_phone_profile(phone):
        raise HTTPException(status_code=409, detail="Phone number is already registered")
    challenge_id = str(uuid.uuid4())
    otp = f"{secrets.randbelow(1000000):06d}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    otp_challenges[challenge_id] = {"phone": phone, "otp": otp, "expires_at": expires_at, "attempts": 0, "purpose": purpose}
    delivery = await send_signup_otp(phone, challenge_id, otp)
    return {"success": True, "challenge_id": challenge_id, "expires_in": 300, "delivery": delivery}


async def verify_phone_otp(challenge_id: str, otp_code: str) -> dict:
    challenge = otp_challenges.get(challenge_id)
    if not challenge:
        raise HTTPException(status_code=404, detail="OTP challenge not found")
    if challenge["expires_at"] <= datetime.now(timezone.utc):
        otp_challenges.pop(challenge_id, None)
        raise HTTPException(status_code=400, detail="OTP expired")
    if challenge["attempts"] >= 5:
        raise HTTPException(status_code=429, detail="Too many OTP attempts")
    challenge["attempts"] += 1
    if not secrets.compare_digest(challenge["otp"], str(otp_code)):
        raise HTTPException(status_code=400, detail="Invalid OTP")
    otp_challenges.pop(challenge_id, None)
    return {"success": True, "phone": challenge["phone"], "purpose": challenge["purpose"]}


async def create_profile_after_otp(phone: str, username: str, email: Optional[str] = None) -> dict:
    normalized_username = normalize_username(username)
    if not re.match(r"^[a-z0-9_]{3,30}$", normalized_username):
        raise HTTPException(status_code=422, detail="Invalid username")
    existing_username = await find_existing_username_profile(normalized_username)
    if existing_username:
        raise HTTPException(status_code=409, detail="Username is already taken")
    existing_phone = await find_existing_phone_profile(phone)
    if existing_phone:
        return existing_phone

    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{SUPABASE_URL}/auth/v1/admin/users",
                headers=get_supabase_headers(use_service_key=True),
                json={"phone": phone, "phone_confirm": True, "user_metadata": {"username": normalized_username, "mobile": phone}},
            )
            if response.status_code >= 400:
                raise HTTPException(status_code=502, detail="Unable to create authentication user")
            auth_user = response.json()
            user_id = auth_user["id"]
            response = await client.post(
                f"{SUPABASE_URL}/rest/v1/profiles",
                headers={**get_supabase_headers(use_service_key=True), "Prefer": "return=representation"},
                json={"user_id": user_id, "username": normalized_username, "mobile": phone, "email": email},
            )
            if response.status_code >= 400:
                raise HTTPException(status_code=502, detail="Unable to create profile")
            rows = response.json()
            return rows[0] if rows else {"user_id": user_id, "username": normalized_username, "mobile": phone}

    user_id = f"local-{uuid.uuid4().hex}"
    user = {"id": user_id, "user_id": user_id, "username": normalized_username, "mobile": phone, "email": email}
    social_graph.users[user_id] = user
    return user


async def issue_session(user: dict, request: Request) -> dict:
    from backend.core.security import create_access_token
    token, jti, expires_at = create_access_token(str(user["user_id"] if user.get("user_id") else user["id"]), user.get("mobile", ""), user["username"])
    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
        from backend.services.supabase_db import insert_one
        await insert_one("auth_sessions", {"user_id": user["user_id"], "token_jti": jti, "expires_at": expires_at.isoformat(), "ip_address": request.client.host if request.client else None, "user_agent": request.headers.get("user-agent")})
    return {"access_token": token, "token_type": "bearer", "expires_at": expires_at.isoformat(), "user": {"id": user.get("user_id") or user.get("id"), "username": user["username"], "phone": user.get("mobile", "")}}


# Legacy route support is intentionally retained below for existing frontend compatibility.

@app.get("/")
async def root():
    return {"name": "OMNIX", "status": "online"}
