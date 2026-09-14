from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.services.supabase_db import supabase_db_request
from backend.services.supabase_storage import upload_bytes

router = APIRouter(prefix="/api/reels", tags=["Reels"])


class ReelCreateRequest(BaseModel):
    media_path: str = Field(min_length=1, max_length=500)
    caption: str = Field(default="", max_length=2200)


async def _require_user(request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return str(user_id)


def _signed_url(path: str) -> str:
    base = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base or not key:
        raise HTTPException(status_code=503, detail="Supabase media service is not configured")
    # Signed URLs are generated server-side; the service-role key never reaches clients.
    import httpx
    try:
        response = httpx.post(
            f"{base}/storage/v1/object/sign/reels/{path}",
            headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"expiresIn": 3600},
            timeout=20,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Media signing service unavailable") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Unable to sign reel media")
    signed = response.json().get("signedURL")
    if not signed:
        raise HTTPException(status_code=502, detail="Invalid media signing response")
    return f"{base}/storage/v1{signed}" if signed.startswith("/") else signed


@router.post("/upload")
async def upload_reel(request, file: UploadFile = File(...)):
    user_id = await _require_user(request)
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
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"success": True, "path": result["path"], "media_type": "video"}


@router.post("")
async def create_reel(request, payload: ReelCreateRequest):
    user_id = await _require_user(request)
    expected = f"reels/{user_id}/"
    if not payload.media_path.startswith(expected):
        raise HTTPException(status_code=403, detail="Reel media ownership validation failed")
    row = {
        "user_id": user_id,
        "video_url": payload.media_path,
        "caption": payload.caption,
        "duration": None,
        "view_count": 0,
    }
    try:
        created = await supabase_db_request("POST", "/rest/v1/reels", json=row, headers={"Prefer": "return=representation"})
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to persist reel") from exc
    return {"success": True, "reel": created[0] if isinstance(created, list) and created else created}


@router.get("")
async def list_reels(request, limit: int = 20, offset: int = 0):
    await _require_user(request)
    limit = max(1, min(limit, 50))
    offset = max(0, offset)
    try:
        rows = await supabase_db_request(
            "GET",
            f"/rest/v1/reels?select=id,user_id,video_url,caption,duration,view_count,created_at&order=created_at.desc&limit={limit}&offset={offset}",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to load reels") from exc
    for row in rows or []:
        row["media_url"] = _signed_url(row["video_url"])
    return {"success": True, "reels": rows or [], "limit": limit, "offset": offset}


@router.post("/{reel_id}/view")
async def view_reel(request, reel_id: str):
    await _require_user(request)
    # View counts are persisted atomically by the database function when available.
    try:
        await supabase_db_request("POST", "/rest/v1/rpc/increment_reel_view", json={"target_reel_id": reel_id})
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to record reel view") from exc
    return {"success": True}
