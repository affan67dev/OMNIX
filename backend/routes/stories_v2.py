from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.services.supabase_db import insert_one, select_many, select_one, update_one
from backend.services.supabase_storage import upload_bytes

router = APIRouter(prefix="/api/stories", tags=["Stories"])
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


class StoryCreateRequest(BaseModel):
    media_name: str = Field(min_length=1, max_length=500)
    media_type: str = Field(default="image", pattern="^(image|video)$")
    caption: str = Field(default="", max_length=2200)
    mentions: list[str] = Field(default_factory=list, max_length=20)
    location_name: str = Field(default="", max_length=200)
    music_track: str = Field(default="", max_length=200)
    overlay_text: str = Field(default="", max_length=500)
    overlay_emoji: str = Field(default="", max_length=32)
    overlay_x: float = Field(default=0.5, ge=0, le=1)
    overlay_y: float = Field(default=0.5, ge=0, le=1)
    overlay_scale: float = Field(default=1.0, ge=0.5, le=2)


async def _signed_url(path: str, expires_in: int = 3600) -> str:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=503, detail="Supabase Storage is not configured")
    if not path.startswith("stories/"):
        raise HTTPException(status_code=400, detail="Invalid story media path")
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{SUPABASE_URL}/storage/v1/object/sign/stories/{path[len('stories/'):]}",
            headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json"},
            json={"expiresIn": expires_in},
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Unable to create media URL")
    data = response.json()
    signed = data.get("signedURL") or data.get("signedUrl")
    if not signed:
        raise HTTPException(status_code=502, detail="Invalid Storage response")
    return f"{SUPABASE_URL}/storage/v1{signed}" if signed.startswith("/") else signed


async def _decorate(stories: list[dict]) -> list[dict]:
    result = []
    for story in stories:
        row = dict(story)
        profile = await select_one("profiles", filters={"user_id": story["user_id"]}, columns="username")
        row["username"] = (profile or {}).get("username") or "user"
        row["media_url"] = await _signed_url(story["media_name"])
        result.append(row)
    return result


async def _can_view_story(viewer_id: str, story: dict) -> bool:
    """Enforce story visibility explicitly because service-role reads bypass RLS."""
    owner_id = str(story.get("user_id") or "")
    viewer_id = str(viewer_id or "")
    if not owner_id or not viewer_id:
        return False
    if owner_id == viewer_id:
        return True

    owner = await select_one("profiles", filters={"user_id": owner_id}, columns="user_id,is_private")
    if not owner:
        return False

    blocked = await select_one("blocks", filters={"blocker_id": viewer_id, "blocked_id": owner_id}, columns="blocker_id")
    if blocked:
        return False
    blocked_reverse = await select_one("blocks", filters={"blocker_id": owner_id, "blocked_id": viewer_id}, columns="blocker_id")
    if blocked_reverse:
        return False

    if not bool(owner.get("is_private")):
        return True

    follow = await select_one(
        "follows",
        filters={"follower_id": viewer_id, "following_id": owner_id, "status": "accepted"},
        columns="follower_id",
    )
    return follow is not None


@router.post("/upload")
async def upload_story_media(file: UploadFile = File(...), x_user_id: Optional[str] = Header(default=None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    content_type = file.content_type or ""
    if not (content_type.startswith("image/") or content_type.startswith("video/")):
        raise HTTPException(status_code=415, detail="Only image and video media are supported")
    data = await file.read()
    try:
        uploaded = await upload_bytes("stories", str(x_user_id), file.filename or "upload", content_type, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Media storage unavailable") from exc
    return {"success": True, **uploaded, "media_type": "video" if content_type.startswith("video/") else "image"}


@router.post("")
async def create_story(payload: StoryCreateRequest, x_user_id: Optional[str] = Header(default=None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not payload.media_name.startswith(f"stories/{x_user_id}/"):
        raise HTTPException(status_code=400, detail="Story media must be uploaded by the authenticated user")
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=24)
    row = await insert_one(
        "stories",
        {
            "user_id": str(x_user_id),
            "media_name": payload.media_name,
            "media_type": payload.media_type,
            "caption": payload.caption,
            "mentions": payload.mentions,
            "location_name": payload.location_name,
            "music_track": payload.music_track,
            "overlay_text": payload.overlay_text,
            "overlay_emoji": payload.overlay_emoji,
            "overlay_x": payload.overlay_x,
            "overlay_y": payload.overlay_y,
            "overlay_scale": payload.overlay_scale,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        },
    )
    return {"success": True, "story": row}


@router.get("/feed")
async def story_feed(x_user_id: Optional[str] = Header(default=None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=503, detail="Supabase is not configured")
    now = datetime.now(timezone.utc).isoformat()
    params = {"select": "id,user_id,media_name,media_type,caption,mentions,location_name,music_track,overlay_text,overlay_emoji,overlay_x,overlay_y,overlay_scale,created_at,expires_at", "expires_at": f"gt.{now}", "deleted_at": "is.null", "order": "created_at.desc", "limit": "100"}
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(f"{SUPABASE_URL}/rest/v1/stories", headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"}, params=params)
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Unable to load stories")
    stories = [story for story in response.json() if await _can_view_story(str(x_user_id), story)]
    return {"success": True, "stories": await _decorate(stories)}


@router.post("/{story_id}/view")
async def view_story(story_id: str, x_user_id: Optional[str] = Header(default=None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    story = await select_one("stories", filters={"id": story_id}, columns="id,user_id,expires_at,deleted_at")
    if not story or story.get("deleted_at"):
        raise HTTPException(status_code=404, detail="Story not found")
    expires_at = datetime.fromisoformat(str(story["expires_at"]).replace("Z", "+00:00"))
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Story expired")
    if not await _can_view_story(str(x_user_id), story):
        raise HTTPException(status_code=403, detail="Story unavailable")
    try:
        await insert_one("story_views", {"story_id": story_id, "user_id": str(x_user_id)})
    except Exception as exc:
        if "duplicate key" not in str(exc).lower() and "unique" not in str(exc).lower():
            raise HTTPException(status_code=503, detail="Unable to record story view") from exc
    return {"success": True}


@router.get("/{story_id}")
async def get_story(story_id: str, x_user_id: Optional[str] = Header(default=None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    story = await select_one("stories", filters={"id": story_id}, columns="id,user_id,media_name,media_type,caption,mentions,location_name,music_track,overlay_text,overlay_emoji,overlay_x,overlay_y,overlay_scale,created_at,expires_at,deleted_at")
    if not story or story.get("deleted_at"):
        raise HTTPException(status_code=404, detail="Story not found")
    if datetime.fromisoformat(str(story["expires_at"]).replace("Z", "+00:00")) <= datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Story expired")
    if not await _can_view_story(str(x_user_id), story):
        raise HTTPException(status_code=403, detail="Story unavailable")
    return {"success": True, "story": (await _decorate([story]))[0]}
