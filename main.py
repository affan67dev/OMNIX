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
from backend.auth_utils import fetch_authenticated_user, require_admin_user, require_authenticated_user_id
from backend.services.social_graph import SocialGraphError, social_graph
from backend.routes.settings_management import router as settings_management_router
from backend.routes.billing import router as billing_router
from backend.routes.push_notifications import router as push_notifications_router
from backend.services.push_notifications import PushNotificationError, push_notification_service
from backend.routes.zero_knowledge import router as zero_knowledge_router
from backend.routes.admin_oob_auth import router as admin_oob_auth_router

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

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def backend_request_guard(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    request.state.request_id = request_id
    try:
        if requires_authenticated_user(request.url.path):
            access_token = request.query_params.get("access_token") if request.url.path.endswith("/stream") else None
            user_id = await require_authenticated_user_id(request.headers.get("authorization"), access_token=access_token)
            inject_header(request, "x-user-id", user_id)
            request.state.user_id = user_id
        response = await call_next(request)
    except HTTPException as error:
        return JSONResponse(
            status_code=error.status_code,
            content={"success": False, "detail": error.detail, "request_id": request_id},
        )
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
        origin
        for origin in [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://localhost:80",
            "http://localhost",
            os.getenv("FRONTEND_URL", "").strip(),
        ]
        if origin
    ],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
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


AUTHENTICATED_PATH_PREFIXES = (
    "/api/chat",
    "/api/settings",
    "/api/v1/billing",
    "/api/v1/push",
    "/api/v1/security",
    "/api/social",
    "/api/users",
    "/api/reports",
    "/api/stories",
    "/api/posts",
)
AUTHENTICATED_EXACT_PATHS = {
    "/api/chat/conversations",
    "/api/stories/feed",
}


def requires_authenticated_user(path: str) -> bool:
    return path in AUTHENTICATED_EXACT_PATHS or path.startswith(AUTHENTICATED_PATH_PREFIXES)


def inject_header(request: Request, header_name: str, header_value: str) -> None:
    normalized = header_name.lower().encode()
    request.scope["headers"] = [
        (key, value)
        for key, value in request.scope["headers"]
        if key != normalized
    ] + [(normalized, header_value.encode())]


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
    raise HTTPException(status_code=500, detail="Use async admin validation")


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
                if response.status_code >= 400:
                    continue
                rows = response.json()
                if isinstance(rows, list) and rows:
                    return rows[0]

    if normalized_username in auth_identity_registry["usernames"]:
        return {"username": normalized_username}

    return None


def prune_expired_otp_challenges() -> None:
    now = datetime.now(timezone.utc)
    expired_ids = [challenge_id for challenge_id, challenge in otp_challenges.items() if challenge["expires_at"] <= now]
    for challenge_id in expired_ids:
        otp_challenges.pop(challenge_id, None)


def is_phone_identity(identity: str) -> bool:
    cleaned = re.sub(r"[\s\-()]+", "", identity or "")
    return bool(re.match(r"^\+?\d{8,16}$", cleaned))


refresh_identity_registry()


def resolve_current_user_id(x_user_id: Optional[str]) -> str:
    candidate = (x_user_id or "").strip()
    if not candidate:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if candidate not in social_graph.users:
        raise HTTPException(status_code=403, detail="User context is invalid")
    return candidate


def raise_social_error(error: SocialGraphError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.detail)


def get_conversation_partner_id(current_user_id: str, conversation_id: str) -> Optional[str]:
    conversation = social_graph.conversations.get(conversation_id)
    if conversation is None:
        return None
    participants = conversation.get('participant_user_ids', [])
    return next((participant for participant in participants if participant != current_user_id), None)


def can_view_author_posts(current_user_id: str, author_id: str) -> bool:
    if author_id not in social_graph.users:
        return True
    if social_graph.is_blocked(current_user_id, author_id):
        return False
    return bool(social_graph._profile_access(current_user_id, author_id)["can_view_posts"])


async def broadcast_message(conversation_id: str, message: dict) -> None:
    queues = list(chat_store.listeners.get(conversation_id, []))
    for queue in queues:
        try:
            await queue.put(message)
        except Exception:
            continue


@app.get("/api/chat/conversations")
async def list_chat_conversations(x_user_id: Optional[str] = Header(default=None)):
    """Return all chat conversations with their recent message history."""
    current_user_id = resolve_current_user_id(x_user_id)
    conversations = social_graph.list_conversations(current_user_id)
    return {"success": True, "conversations": conversations}


@app.get("/api/chat/conversations/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: str, x_user_id: Optional[str] = Header(default=None)):
    """Return message history for a given conversation."""
    current_user_id = resolve_current_user_id(x_user_id)
    try:
        messages = social_graph.get_conversation_messages(current_user_id, conversation_id)
    except SocialGraphError as error:
        raise_social_error(error)
    return {"success": True, "conversation_id": conversation_id, "messages": messages}


@app.post("/api/chat/conversations/{conversation_id}/messages")
async def send_chat_message(conversation_id: str, req: SendMessageRequest, x_user_id: Optional[str] = Header(default=None)):
    """Persist and broadcast a message to the active conversation."""
    if not ((req.text and req.text.strip()) or (req.encrypted_payload and req.encryption_nonce)):
        raise HTTPException(status_code=400, detail="Message text or encrypted payload is required")

    current_user_id = resolve_current_user_id(x_user_id)
    sender_name = req.sender_name or social_graph.users[current_user_id]["display_name"]
    try:
        message = social_graph.send_message(
            current_user_id,
            conversation_id,
            sender_name,
            req.text,
            req.encrypted_payload,
            req.encryption_nonce,
            req.sender_ephemeral_public_key,
            req.recipient_key_id,
            req.encryption_algorithm,
        )
    except SocialGraphError as error:
        raise_social_error(error)

    await broadcast_message(conversation_id, message)

    partner_id = get_conversation_partner_id(current_user_id, conversation_id)
    if partner_id:
        try:
            preview_text = req.text.strip() if req.text and req.text.strip() else "New encrypted message"
            await push_notification_service.send_direct_message(partner_id, conversation_id, sender_name, preview_text)
        except PushNotificationError:
            pass

    if req.sender_id != 'bot' and not req.encrypted_payload:
        await asyncio.sleep(0.35)
        reply = social_graph.append_bot_reply(
            conversation_id,
            'system-bot',
            'Nova',
            'Received and synced. The backend just pushed the update to the live stream.',
        )
        await broadcast_message(conversation_id, reply)

    return {"success": True, "message": message}


@app.get("/api/chat/conversations/{conversation_id}/details")
async def get_chat_details(conversation_id: str, x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    try:
        details = social_graph.get_chat_details(current_user_id, conversation_id)
    except SocialGraphError as error:
        raise_social_error(error)
    return {"success": True, **details}


@app.patch("/api/chat/conversations/{conversation_id}/settings")
async def update_chat_settings(conversation_id: str, req: ChatSettingsUpdateRequest, x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    try:
        settings = social_graph.update_chat_settings(
            current_user_id,
            conversation_id,
            req.custom_wallpaper,
            req.custom_nickname,
            req.is_muted,
            req.mute_duration,
            req.notification_sound_enabled,
            req.vibration_enabled,
        )
    except (SocialGraphError, ValueError) as error:
        if isinstance(error, SocialGraphError):
            raise_social_error(error)
        raise HTTPException(status_code=400, detail=str(error))
    return {"success": True, "settings": settings}


@app.post("/api/chat/conversations/{conversation_id}/reset-wallpaper")
async def reset_chat_wallpaper(conversation_id: str, x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    try:
        settings = social_graph.reset_wallpaper(current_user_id, conversation_id)
    except SocialGraphError as error:
        raise_social_error(error)
    return {"success": True, "settings": settings}


@app.post("/api/chat/conversations/{conversation_id}/clear")
async def clear_chat_history(conversation_id: str, x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    try:
        result = social_graph.clear_chat_history(current_user_id, conversation_id)
    except SocialGraphError as error:
        raise_social_error(error)
    return {"success": True, **result}


@app.get("/api/chat/conversations/{conversation_id}/search")
async def search_in_chat(conversation_id: str, q: str = '', x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    try:
        results = social_graph.search_chat(current_user_id, conversation_id, q)
    except SocialGraphError as error:
        raise_social_error(error)
    return {"success": True, "matches": results}


@app.get("/api/chat/conversations/{conversation_id}/export")
async def export_chat(conversation_id: str, x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    try:
        exported = social_graph.export_chat(current_user_id, conversation_id)
    except SocialGraphError as error:
        raise_social_error(error)
    return {"success": True, **exported}


@app.get("/api/social/me/overview")
async def get_social_overview(x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    return {"success": True, **social_graph.get_me_overview(current_user_id)}


@app.get("/api/users/search")
async def search_users(q: str = '', x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    return {"success": True, "results": social_graph.search_users(current_user_id, q)}


@app.get("/api/users/{user_id}/profile")
async def get_user_profile(user_id: str, x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    try:
        profile = social_graph.get_profile(current_user_id, user_id)
    except SocialGraphError as error:
        raise_social_error(error)
    return {"success": True, "profile": profile}


@app.get("/api/users/{user_id}/followers")
async def get_user_followers(user_id: str, x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    try:
        followers = social_graph.get_followers(current_user_id, user_id)
    except SocialGraphError as error:
        raise_social_error(error)
    return {"success": True, "followers": followers}


@app.get("/api/users/{user_id}/following")
async def get_user_following(user_id: str, x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    try:
        following = social_graph.get_following(current_user_id, user_id)
    except SocialGraphError as error:
        raise_social_error(error)
    return {"success": True, "following": following}


@app.get("/api/users/{user_id}/posts")
async def get_user_posts(user_id: str, x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    try:
        posts = social_graph.get_posts(current_user_id, user_id)
    except SocialGraphError as error:
        raise_social_error(error)
    return {"success": True, "posts": posts}


@app.post("/api/users/{user_id}/follow")
async def follow_user(user_id: str, x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    try:
        result = social_graph.create_follow(current_user_id, user_id)
    except SocialGraphError as error:
        raise_social_error(error)
    if result.get("status") == "pending":
        actor_name = social_graph.users[current_user_id]["display_name"]
        try:
            await push_notification_service.send_social_event(user_id, actor_name, "follow_request", user_id)
        except PushNotificationError:
            pass
    return {"success": True, **result}


@app.delete("/api/users/{user_id}/follow")
async def unfollow_user(user_id: str, x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    try:
        result = social_graph.unfollow(current_user_id, user_id)
    except SocialGraphError as error:
        raise_social_error(error)
    return {"success": True, **result}


@app.delete("/api/follow-requests/{request_id}")
async def cancel_follow_request(request_id: str, x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    try:
        request = social_graph.cancel_follow_request(current_user_id, request_id)
    except SocialGraphError as error:
        raise_social_error(error)
    return {"success": True, "request": request}


@app.post("/api/follow-requests/{request_id}/accept")
async def accept_follow_request(request_id: str, x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    try:
        request = social_graph.respond_to_follow_request(current_user_id, request_id, 'accept')
    except SocialGraphError as error:
        raise_social_error(error)
    return {"success": True, "request": request}


@app.post("/api/follow-requests/{request_id}/reject")
async def reject_follow_request(request_id: str, x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    try:
        request = social_graph.respond_to_follow_request(current_user_id, request_id, 'reject')
    except SocialGraphError as error:
        raise_social_error(error)
    return {"success": True, "request": request}


@app.patch("/api/users/me/privacy")
async def update_my_privacy(req: PrivacyUpdateRequest, x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    user = social_graph.update_privacy(current_user_id, req.is_private, req.is_blocked_from_search)
    return {"success": True, "user": user}


@app.post("/api/users/{user_id}/block")
async def block_user(user_id: str, req: BlockUserRequest, x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    try:
        block = social_graph.block_user(current_user_id, user_id, req.reason)
    except SocialGraphError as error:
        raise_social_error(error)
    return {"success": True, "block": block}


@app.delete("/api/users/{user_id}/block")
async def unblock_user(user_id: str, x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    social_graph.unblock_user(current_user_id, user_id)
    return {"success": True, "message": "User unblocked"}


@app.post("/api/users/{user_id}/mute")
async def mute_user(user_id: str, req: MuteUserRequest, x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    try:
        mute = social_graph.mute_user(current_user_id, user_id, req.mute_type, req.duration)
    except (SocialGraphError, ValueError) as error:
        if isinstance(error, SocialGraphError):
            raise_social_error(error)
        raise HTTPException(status_code=400, detail=str(error))
    return {"success": True, "mute": mute}


@app.delete("/api/users/{user_id}/mute")
async def unmute_user(user_id: str, mute_type: str, x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    social_graph.unmute_user(current_user_id, user_id, mute_type)
    return {"success": True, "message": "User unmuted"}


@app.post("/api/reports/users/{user_id}")
async def report_user(user_id: str, req: ReportUserRequest, x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    try:
        report = social_graph.report_user(current_user_id, user_id, req.reason, req.description)
    except SocialGraphError as error:
        raise_social_error(error)
    return {"success": True, "report": report}


@app.get("/api/chat/conversations/{conversation_id}/stream")
async def stream_chat_messages(conversation_id: str, request: Request, x_user_id: Optional[str] = Header(default=None)):
    """Expose a simple SSE stream for real-time chat updates."""
    current_user_id = resolve_current_user_id(x_user_id)
    conversation = social_graph.conversations.get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if current_user_id not in conversation.get("participant_user_ids", []):
        raise HTTPException(status_code=403, detail="Conversation access denied")

    queue: asyncio.Queue = asyncio.Queue()
    chat_store.listeners.setdefault(conversation_id, []).append(queue)

    async def event_stream():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=30)
                except asyncio.TimeoutError:
                    continue
                yield f"event: message\ndata: {json.dumps(payload)}\n\n"
        finally:
            listeners = chat_store.listeners.get(conversation_id, [])
            chat_store.listeners[conversation_id] = [item for item in listeners if item is not queue]
            if not chat_store.listeners.get(conversation_id):
                chat_store.listeners.pop(conversation_id, None)

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


class ModerationRequest(BaseModel):
    content: str
    action: Optional[str] = None


# Page Routes
@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve login page or React app in production."""
    if os.path.exists("dist/index.html"):
        with open("dist/index.html", "r", encoding="utf-8") as f:
            return f.read()
    return FileResponse("templates/login.html")


@app.get("/home")
async def home():
    return FileResponse("templates/home.html")


@app.get("/search")
async def search():
    return FileResponse("templates/search.html")


@app.get("/create")
async def create():
    return FileResponse("templates/create.html")


@app.get("/chat")
async def chat():
    return FileResponse("templates/chat.html")


@app.get("/profile")
async def profile():
    return FileResponse("templates/profile.html")


@app.get("/signup")
async def signup():
    return FileResponse("templates/signup.html")


@app.get("/forgot-password")
async def forgot_password():
    return FileResponse("templates/forgot-password.html")


@app.get("/terms")
async def terms():
    return FileResponse("templates/terms.html")


@app.get("/privacy")
async def privacy():
    return FileResponse("templates/privacy.html")


# Authentication API Routes
@app.post("/api/auth/login")
@limiter.limit("5/minute")
async def api_login(request: Request, req: LoginRequest):
    """Authenticate user via Supabase Auth."""
    identity = (req.identity or "").strip()
    if not identity:
        raise HTTPException(status_code=400, detail="Identity is required")

    if "@" in identity:
        email = identity.lower()
    elif is_phone_identity(identity):
        normalized_phone = normalize_phone("+", identity)
        mapped_email = auth_identity_registry["phones"].get(normalized_phone)
        if not mapped_email:
            raise HTTPException(status_code=404, detail="Phone number is not registered")
        email = mapped_email
    else:
        email = f"{identity.lower()}@shadow.omnix"

    result = await supabase_auth_request("token", {
        "grant_type": "password",
        "email": email,
        "password": req.password,
    })

    return {
        "success": True,
        "access_token": result.get("access_token", ""),
        "refresh_token": result.get("refresh_token", ""),
        "expires_in": result.get("expires_in", 3600),
        "user": {
            "id": result.get("user", {}).get("id", ""),
            "email": result.get("user", {}).get("email", email),
            "username": req.identity,
        },
    }


@app.post("/api/auth/signup")
@limiter.limit("3/minute")
async def api_signup(request: Request, req: SignupRequest):
    """Register new user via Supabase Auth."""
    refresh_identity_registry()

    normalized_username = normalize_username(req.username)
    existing_username_profile = await find_existing_username_profile(normalized_username)
    if existing_username_profile:
        raise HTTPException(status_code=409, detail="Username already taken")

    normalized_email = req.email.strip().lower()
    if normalized_email in auth_identity_registry["emails"]:
        raise HTTPException(status_code=409, detail="Email is already registered")

    if not req.legal_accepted:
        raise HTTPException(status_code=400, detail="You must accept Terms and Privacy Policy")

    normalized_phone = ""
    if req.phone_number:
        normalized_phone = normalize_phone(req.phone_country_code or "+1", req.phone_number)
        existing_phone_email = auth_identity_registry["phones"].get(normalized_phone)
        if existing_phone_email:
            raise HTTPException(status_code=409, detail="Phone number already exists")
        prune_expired_otp_challenges()
        challenge = otp_challenges.get(req.otp_challenge_id or "")
        if not challenge or challenge["phone"] != normalized_phone or not challenge.get("verified"):
            raise HTTPException(status_code=400, detail="Phone verification is required before signup")
    try:
        result = await supabase_auth_request("signup", {
            "email": normalized_email,
            "password": req.password,
            "data": {
                "username": normalized_username,
                "full_name": f"{req.first_name} {req.last_name}".strip(),
                "display_nickname": (req.display_nickname or "").strip(),
                "mobile": normalized_phone or req.mobile or "",
                "phone_country_code": req.phone_country_code or "+1",
                "terms_accepted": bool(req.legal_accepted),
                "privacy_accepted": bool(req.legal_accepted),
            },
        })
    except HTTPException as error:
        if is_username_conflict_error(str(error.detail)):
            raise HTTPException(status_code=409, detail="Username already taken") from error
        raise

    auth_identity_registry["usernames"].add(normalized_username)
    auth_identity_registry["emails"].add(normalized_email)
    if normalized_phone:
        auth_identity_registry["phones"][normalized_phone] = normalized_email

    token_result: Dict[str, Any] = {}
    token_payload = {
        "grant_type": "password",
        "email": normalized_email,
        "password": req.password,
    }
    try:
        token_result = await supabase_auth_request("token", token_payload)
    except HTTPException:
        token_result = {}

    webhook_payload = trigger_signup_notification_webhook({
        "username": req.username,
        "email": req.email,
        "mobile": req.mobile or "",
    })

    return {
        "success": True,
        "user_id": result.get("id", ""),
        "message": "Account created successfully.",
        "access_token": token_result.get("access_token", ""),
        "refresh_token": token_result.get("refresh_token", ""),
        "expires_in": token_result.get("expires_in", 3600),
        "user": {
            "id": token_result.get("user", {}).get("id", result.get("id", "")),
            "email": normalized_email,
            "username": normalized_username,
            "phone": normalized_phone,
        },
        "notification_webhook": webhook_payload,
    }


@app.post("/api/auth/otp/send")
@limiter.limit("6/minute")
async def api_send_signup_otp(request: Request, req: OtpSendRequest):
    prune_expired_otp_challenges()
    phone = normalize_phone(req.country_code, req.phone_number)

    if phone in auth_identity_registry["phones"]:
        raise HTTPException(status_code=409, detail="Phone number already exists")

    otp_code = f"{secrets.randbelow(10**6):06d}"
    challenge_id = f"otp_{uuid.uuid4().hex}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    otp_challenges[challenge_id] = {
        "phone": phone,
        "otp_code": otp_code,
        "verified": False,
        "expires_at": expires_at,
    }

    payload = {
        "success": True,
        "challenge_id": challenge_id,
        "expires_at": expires_at.isoformat(),
        "message": "OTP sent successfully",
    }
    if os.getenv("EXPOSE_DEV_OTP", "false").lower() == "true":
        payload["otp_code"] = otp_code
    return payload


@app.post("/api/auth/otp/verify")
@limiter.limit("10/minute")
async def api_verify_signup_otp(request: Request, req: OtpVerifyRequest):
    prune_expired_otp_challenges()
    challenge = otp_challenges.get(req.challenge_id)
    if not challenge:
        raise HTTPException(status_code=404, detail="OTP challenge expired or not found")

    if not re.match(r"^\d{6}$", req.otp_code or ""):
        raise HTTPException(status_code=400, detail="Enter a valid 6-digit OTP")

    if challenge["otp_code"] != req.otp_code:
        raise HTTPException(status_code=400, detail="Incorrect OTP code")

    challenge["verified"] = True
    return {
        "success": True,
        "challenge_id": req.challenge_id,
        "phone": challenge["phone"],
        "message": "Phone verification successful",
    }


@app.post("/api/auth/availability")
@limiter.limit("10/minute")
async def api_check_auth_availability(request: Request, req: AvailabilityRequest):
    refresh_identity_registry()
    normalized_username = normalize_username(req.username)
    normalized_email = req.email.strip().lower()
    username_available = await find_existing_username_profile(normalized_username) is None
    email_available = normalized_email not in auth_identity_registry["emails"]
    return {
        "success": True,
        "username_available": username_available,
        "email_available": email_available,
    }


@app.post("/api/auth/forgot-password")
@limiter.limit("2/minute")
async def api_forgot_password(request: Request, req: ForgotPasswordRequest):
    """Send a password reset link (email) or reset OTP (phone)."""
    mode = (req.mode or "email").strip().lower()
    if mode not in {"email", "phone"}:
        raise HTTPException(status_code=400, detail="mode must be 'email' or 'phone'")

    if mode == "email":
        if not req.email:
            raise HTTPException(status_code=400, detail="Email is required for email reset")
        await supabase_auth_request("recover", {"email": str(req.email)})
        return {
            "success": True,
            "message": "Password reset link sent successfully.",
        }

    if not req.phone_number:
        raise HTTPException(status_code=400, detail="Phone number is required for phone reset")

    prune_expired_otp_challenges()
    phone = normalize_phone(req.country_code or "+1", req.phone_number)
    otp_code = f"{secrets.randbelow(10**6):06d}"
    challenge_id = f"otp_{uuid.uuid4().hex}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    otp_challenges[challenge_id] = {
        "phone": phone,
        "otp_code": otp_code,
        "verified": False,
        "expires_at": expires_at,
        "purpose": "password_reset",
    }

    payload: Dict[str, Any] = {
        "success": True,
        "challenge_id": challenge_id,
        "expires_at": expires_at.isoformat(),
        "message": "Password reset OTP sent successfully.",
    }
    if os.getenv("EXPOSE_DEV_OTP", "false").lower() == "true":
        payload["otp_code"] = otp_code
    return payload


@app.get("/api/auth/me")
async def api_me(authorization: Optional[str] = Header(default=None)):
    """Get current authenticated user info."""
    user_info = await fetch_authenticated_user(authorization)

    return {
        "success": True,
        "user": user_info
    }


@app.post("/api/auth/refresh")
async def api_refresh_token(refresh_token: str):
    """Refresh access token."""
    result = await supabase_auth_request("token", {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    })

    return {
        "success": True,
        "access_token": result.get("access_token", ""),
        "refresh_token": result.get("refresh_token", ""),
        "expires_in": result.get("expires_in", 3600),
    }


@app.post("/api/auth/logout")
async def api_logout(authorization: Optional[str] = Header(default=None)):
    """Logout user and invalidate session."""
    if authorization and authorization.startswith("Bearer "):
        headers = get_supabase_headers()
        headers["Authorization"] = authorization
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{SUPABASE_URL}/auth/v1/logout", headers=headers)
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text or "Logout failed")

    return {"success": True, "message": "Logged out successfully"}


# Google OAuth placeholder (ready for implementation)
@app.get("/api/auth/google")
async def google_oauth_redirect():
    """Initiate Google OAuth flow."""
    if not SUPABASE_URL:
        raise HTTPException(status_code=500, detail="OAuth not configured")

    redirect_url = f"{SUPABASE_URL}/auth/v1/authorize?provider=google&redirect_to={os.getenv('FRONTEND_URL', 'http://localhost')}/auth/callback"
    return {"redirect_url": redirect_url}


@app.get("/api/stories/feed")
async def get_story_feed(x_user_id: Optional[str] = Header(default=None)):
    """Return active stories visible to the current user."""
    current_user_id = resolve_current_user_id(x_user_id)
    prune_expired_stories()
    visible: List[dict] = []
    for story in in_memory_stories:
        if can_view_author_posts(current_user_id, story.get('user_id', '')):
            visible.append(story)
    return {"success": True, "stories": visible}


@app.get("/api/stories/music/search")
async def search_story_music(q: str = ''):
    query = (q or '').strip().lower()
    library = [
        'Neon Circuit - Pulse Driver',
        'Shadowline - Midnight Run',
        'Nova Sync - Skyline Bloom',
        'Byte Signal - Orbital Echo',
    ]
    tracks = [item for item in library if query in item.lower()] if query else library
    return {"success": True, "tracks": tracks[:10]}


@app.get("/api/stories/location/search")
async def search_story_location(q: str = ''):
    query = (q or '').strip().lower()
    locations = [
        'Secure Server Grid',
        'Distributed Node 4',
        'Bridge Segment',
        'Ops Control Bay',
        'Blue Harbor Downtown',
    ]
    results = [item for item in locations if query in item.lower()] if query else locations
    return {"success": True, "locations": results[:10]}


@app.get("/api/stories/mentions")
async def search_story_mentions(q: str = ''):
    query = normalize_username(q)
    users = [
        {'id': user_id, 'username': user.get('username', ''), 'display_name': user.get('display_name', '')}
        for user_id, user in social_graph.users.items()
    ]
    if query:
        users = [item for item in users if query in normalize_username(item.get('username', ''))]
    return {"success": True, "results": users[:12]}


@app.post("/api/stories")
async def create_story(req: StoryCreateRequest, x_user_id: Optional[str] = Header(default=None)):
    """Create a story that auto-expires in 24 hours."""
    current_user_id = resolve_current_user_id(x_user_id)
    owner = social_graph.users.get(current_user_id, {'username': 'local_user'})
    now = datetime.now(timezone.utc)
    story = {
        'id': f"story-{uuid.uuid4().hex[:10]}",
        'user_id': current_user_id,
        'username': owner.get('username', 'local_user'),
        'media_name': req.media_name,
        'media_type': req.media_type,
        'caption': req.caption or '',
        'mentions': req.mentions or [],
        'location_name': req.location_name or '',
        'music_track': req.music_track or '',
        'overlay_text': req.overlay_text or '',
        'overlay_emoji': req.overlay_emoji or '',
        'overlay_x': req.overlay_x if req.overlay_x is not None else 0.5,
        'overlay_y': req.overlay_y if req.overlay_y is not None else 0.5,
        'overlay_scale': req.overlay_scale if req.overlay_scale is not None else 1.0,
        'created_at': now.isoformat(),
        'expires_at': (now + timedelta(hours=24)).isoformat(),
        'viewers': [],
    }
    in_memory_stories.insert(0, story)
    add_admin_log("INFO", f"Story {story['id']} published by @{story['username']}")
    return {"success": True, "story": story}


@app.post("/api/stories/{story_id}/view")
async def add_story_viewer(story_id: str, x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    story = next((item for item in in_memory_stories if item.get('id') == story_id), None)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")

    if current_user_id not in story['viewers']:
        story['viewers'].append(current_user_id)
        add_admin_log("INFO", f"Story {story_id} viewed by {current_user_id}")
    return {"success": True, "viewers_count": len(story['viewers'])}


@app.get("/api/stories/{story_id}/viewers")
async def get_story_viewers(story_id: str):
    story = next((item for item in in_memory_stories if item.get('id') == story_id), None)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")
    return {"success": True, "viewers": story.get('viewers', [])}


@app.post("/api/posts/{post_id}/interactions")
async def post_interaction(post_id: str, req: PostInteractionRequest, x_user_id: Optional[str] = Header(default=None)):
    """Track post interaction events for recommendation pipelines."""
    current_user_id = resolve_current_user_id(x_user_id)
    post = next((item for item in in_memory_posts if item.get('id') == post_id), None)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    interaction_type = (req.interaction_type or '').strip().lower()
    if interaction_type not in {'like', 'dislike', 'comment', 'share', 'impression', 'hashtag_click', 'watch_time'}:
        raise HTTPException(status_code=400, detail="Unsupported interaction type")

    event = {
        'id': f"evt-{uuid.uuid4().hex[:10]}",
        'post_id': post_id,
        'user_id': current_user_id,
        'interaction_type': interaction_type,
        'metadata': req.metadata or {},
        'created_at': datetime.now(timezone.utc).isoformat(),
    }
    post_interaction_events.append(event)

    if interaction_type == 'like':
        post['likes'] = int(post.get('likes', 0)) + 1
    if interaction_type == 'dislike':
        post['likes'] = max(0, int(post.get('likes', 0)) - 1)
    if interaction_type == 'share':
        post['shares_count'] = int(post.get('shares_count', 0)) + 1
    if interaction_type == 'impression':
        post['impression_count'] = int(post.get('impression_count', 0)) + 1
    if interaction_type == 'comment':
        post['comments_count'] = int(post.get('comments_count', 0)) + 1

    add_admin_log("INFO", f"Post event {interaction_type} on {post_id}")
    return {"success": True, "event": event, "post": post}


@app.post("/api/posts/{post_id}/comments")
async def add_post_comment(post_id: str, req: PostCommentRequest, x_user_id: Optional[str] = Header(default=None)):
    current_user_id = resolve_current_user_id(x_user_id)
    post = next((item for item in in_memory_posts if item.get('id') == post_id), None)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    if not req.comment.strip():
        raise HTTPException(status_code=400, detail="Comment cannot be empty")

    comments = post.setdefault('comments', [])
    comment = {
        'id': f"cmt-{uuid.uuid4().hex[:10]}",
        'post_id': post_id,
        'user_id': current_user_id,
        'comment': req.comment.strip(),
        'created_at': datetime.now(timezone.utc).isoformat(),
    }
    comments.append(comment)
    post['comments_count'] = len(comments)
    add_admin_log("INFO", f"Comment added on {post_id}")
    return {"success": True, "comment": comment, "comments_count": len(comments)}


@app.get("/api/posts/{post_id}/comments")
async def list_post_comments(post_id: str):
    post = next((item for item in in_memory_posts if item.get('id') == post_id), None)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"success": True, "comments": post.get('comments', [])}


@app.get("/api/recommendation/events")
async def recommendation_events(limit: int = 80):
    return {"success": True, "events": post_interaction_events[-limit:]}


# Posts API Routes
@app.post("/api/posts")
async def create_post(req: PostRequest, authorization: Optional[str] = None, x_user_id: Optional[str] = Header(default=None)):
    """Create a new post."""
    moderation = auto_flag_content(req.content)
    if not SUPABASE_URL:
        current_user_id = resolve_current_user_id(x_user_id)
        created = {
            'id': f'local-post-{len(in_memory_posts) + 1}',
            'content': req.content,
            'image_url': req.image_url,
            'visibility': req.visibility,
            'location': req.location,
            'tags': req.tags or ['#OMNIX'],
            'mentions': [],
            'likes': 0,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'user_id': current_user_id,
        }
        created['approved'] = True
        in_memory_posts.insert(0, created)
        add_admin_log("INFO", f"Post {created['id']} created")
        return {"success": True, "message": "Post created successfully", "data": created, "moderation": moderation}

    data = {
        "content": req.content,
        "image_url": req.image_url,
        "visibility": req.visibility,
        "location": req.location,
        "tags": req.tags or [],
    }
    result = await supabase_db_request("POST", "posts", data)
    return {
        "success": True,
        "message": "Post created successfully",
        "data": result,
        "moderation": moderation,
    }


@app.get("/api/posts/feed")
async def get_feed(limit: int = 20, offset: int = 0, x_user_id: Optional[str] = Header(default=None)):
    """Get posts feed ranked by engagement and recency."""
    requested_limit = max(1, min(int(limit), 100))
    requested_offset = max(0, int(offset))
    current_user_id = resolve_current_user_id(x_user_id)

    if not SUPABASE_URL:
        visible_posts = [post for post in in_memory_posts if can_view_author_posts(current_user_id, post.get('user_id', ''))]
        ranked_posts = rank_posts_for_feed(visible_posts)
        paged_posts = ranked_posts[requested_offset:requested_offset + requested_limit]
        return {"success": True, "posts": paged_posts}

    fetch_limit = min(requested_offset + requested_limit * 4 + 20, 200)
    query = f"?select=*&order=created_at.desc&limit={fetch_limit}&offset=0"
    try:
        result = await supabase_db_request("GET", "posts", query=query)
    except HTTPException:
        visible_posts = [post for post in in_memory_posts if can_view_author_posts(current_user_id, post.get('user_id', ''))]
        result = visible_posts

    ranked_posts = rank_posts_for_feed(result)
    paged_posts = ranked_posts[requested_offset:requested_offset + requested_limit]

    return {"success": True, "posts": paged_posts}


@app.post("/api/admin/moderation/flag")
async def flag_content_for_review(request: Request, req: ModerationRequest):
    """Process reported text or actions for automatic moderation review."""
    await require_admin_user(request.headers.get("authorization"))
    moderation = auto_flag_content(req.content, action=req.action)
    return {
        "success": True,
        "flagged": moderation["flagged"],
        "severity": moderation["severity"],
        "reasons": moderation["reasons"],
    }


@app.get("/api/posts/{post_id}")
async def get_post(post_id: str, x_user_id: Optional[str] = Header(default=None)):
    """Get single post by ID."""
    current_user_id = resolve_current_user_id(x_user_id)
    if not SUPABASE_URL:
        post = next((item for item in in_memory_posts if item['id'] == post_id), None)
        if post is None:
            raise HTTPException(status_code=404, detail="Post not found")
        if not can_view_author_posts(current_user_id, post.get('user_id', '')):
            raise HTTPException(status_code=403, detail="Posts are private")
        return {"success": True, "post": post}

    query = f"?select=*&id=eq.{post_id}"
    result = await supabase_db_request("GET", "posts", query=query)
    if not result:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"success": True, "post": result[0]}


@app.delete("/api/posts/{post_id}")
async def delete_post(post_id: str, x_user_id: Optional[str] = Header(default=None)):
    """Delete a post."""
    current_user_id = resolve_current_user_id(x_user_id)
    if not SUPABASE_URL:
        post = next((item for item in in_memory_posts if item["id"] == post_id), None)
        if post is None:
            raise HTTPException(status_code=404, detail="Post not found")
        if post.get("user_id") != current_user_id:
            raise HTTPException(status_code=403, detail="You can only delete your own posts")
        in_memory_posts[:] = [item for item in in_memory_posts if item["id"] != post_id]
        return {"success": True, "message": "Post deleted"}

    result = await supabase_db_request("GET", "posts", query=f"?select=id,user_id&id=eq.{post_id}")
    if not result:
        raise HTTPException(status_code=404, detail="Post not found")
    if result[0].get("user_id") != current_user_id:
        raise HTTPException(status_code=403, detail="You can only delete your own posts")
    query = f"?id=eq.{post_id}"
    await supabase_db_request("DELETE", "posts", query=query)
    return {"success": True, "message": "Post deleted"}


# Health check endpoint
@app.get("/api/health")
async def health_check():
    """Health check for monitoring."""
    return {
        "status": "healthy",
        "service": "omnix-api",
        "version": "1.0.0"
    }


# Mount React production build
if os.path.exists("dist"):
    app.mount("/assets", StaticFiles(directory="dist/assets"), name="assets")

    @app.get("/{path:path}", response_class=HTMLResponse)
    async def serve_spa(path: str):
        """Serve React SPA for all unmatched routes."""
        # Skip API and static routes
        if path.startswith("api/") or path.startswith("static/") or path.endswith((".css", ".js", ".png", ".jpg", ".svg", ".ico")):
            raise HTTPException(status_code=404)

        # Serve index.html for SPA routing
        index_path = "dist/index.html"
        if os.path.exists(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                return f.read()
        raise HTTPException(status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
