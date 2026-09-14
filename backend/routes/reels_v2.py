from __future__ import annotations

import os
from typing import Optional

import httpx
from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.services.supabase_db import insert_one, select_many
from backend.services.supabase_storage import upload_bytes

router = APIRouter(prefix="/api/reels", tags=["Reels"])


class ReelCreateRequest(BaseModel):
    media_path: str = Field(min_length=1, max_length=500)
    caption: str = Field(default="", max_length=2200)


def _require_user(x_user_id: Optional[str]) -> str:
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return str(x_user_id)


async def _signed_url(path: str) -> str:
    base = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base or not key or not path.startswith("reels/"):
        raise HTTPException(status_code=503, detail="Supabase media service is not configured")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{base}/storage/v1/object/sign/reels/{path[len('reels/'):]}",
                headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"expiresIn": 3600},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Media signing service unavailable") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Unable to sign reel media")
    signed = response.json().get("signedURL") or response.json().get("signedUrl")
    if not signed:
        raise HTTPException(status_code=502, detail="Invalid media signing response")
    return f"{base}/storage/v1{signed}" if signed.startswith("/") else signed


@router.post("/upload")
async def upload_reel(file: UploadFile = File(...), x_user_id: Optional[str] = Header(default=None)):
    user_id = _require_user(x_user_id)
    content_type = (file.content_type or "").lower()
    if not content_type.startswith("video/"):
        raise HTTPException(status_code=415, detail="Reels require a video file")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty media file")
    try:
        result = await upload_bytes("reels", user_id, file.filename or "reel.mp4", content_type, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Media storage unavailable") from exc
    return {"success": True, "path": result["path"], "media_type": "video"}


@router.post("")
async def create_reel(payload: ReelCreateRequest, x_user_id: Optional[str] = Header(default=None)):
    user_id = _require_user(x_user_id)
    expected = f"reels/{user_id}/"
    if not payload.media_path.startswith(expected):
        raise HTTPException(status_code=403, detail="Reel media ownership validation failed")
    try:
        row = await insert_one("reels", {"user_id": user_id, "video_url": payload.media_path, "caption": payload.caption, "view_count": 0})
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to persist reel") from exc
    return {"success": True, "reel": row}


@router.get("")
async def list_reels(limit: int = 20, offset: int = 0, x_user_id: Optional[str] = Header(default=None)):
    _require_user(x_user_id)
    limit = max(1, min(limit, 50))
    offset = max(0, offset)
    try:
        rows = await select_many("reels", columns="id,user_id,video_url,caption,duration,view_count,created_at")
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to load reels") from exc
    rows = rows[offset:offset + limit]
    for row in rows:
        row["media_url"] = await _signed_url(row["video_url"])
    return {"success": True, "reels": rows, "limit": limit, "offset": offset}


@router.post("/{reel_id}/view")
async def view_reel(reel_id: str, x_user_id: Optional[str] = Header(default=None)):
    _require_user(x_user_id)
    base = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base or not key:
        raise HTTPException(status_code=503, detail="Supabase is not configured")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{base}/rest/v1/rpc/increment_reel_view",
                headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"target_reel_id": reel_id},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Unable to record reel view") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Unable to record reel view")
    return {"success": True}
