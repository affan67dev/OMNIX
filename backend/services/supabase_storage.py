from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

BUCKETS = {
    "stories": {"prefix": "stories", "max_bytes": 25 * 1024 * 1024},
    "posts": {"prefix": "posts", "max_bytes": 25 * 1024 * 1024},
    "reels": {"prefix": "reels", "max_bytes": 100 * 1024 * 1024},
}


def _headers() -> dict[str, str]:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/octet-stream",
    }


def _validate_upload(bucket: str, filename: str, content_type: str, data: bytes) -> None:
    config = BUCKETS.get(bucket)
    if not config:
        raise ValueError("Unsupported storage bucket")
    if not filename or Path(filename).name != filename:
        raise ValueError("Invalid filename")
    if len(data) > config["max_bytes"]:
        raise ValueError("Media file is too large")
    if bucket in {"stories", "posts"} and not content_type.startswith("image/") and not content_type.startswith("video/"):
        raise ValueError("Only image and video media are supported")
    if bucket == "reels" and not content_type.startswith("video/"):
        raise ValueError("Reels require video media")


async def upload_bytes(bucket: str, owner_id: str, filename: str, content_type: str, data: bytes) -> dict[str, str]:
    _validate_upload(bucket, filename, content_type, data)
    safe_name = Path(filename).name
    object_path = f"{BUCKETS[bucket]['prefix']}/{owner_id}/{uuid4().hex}-{safe_name}"
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{object_path}"
    headers = _headers()
    headers["Content-Type"] = content_type or "application/octet-stream"
    headers["x-upsert"] = "false"
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, headers=headers, content=data)
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase Storage upload failed: {response.text}")
    return {
        "bucket": bucket,
        "path": object_path,
        "public_url": f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{object_path}",
    }
