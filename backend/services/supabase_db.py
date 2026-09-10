from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def _headers() -> dict[str, str]:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _filter(field: str, value: Any) -> str:
    return f"{quote(field, safe='')}=eq.{quote(str(value), safe='')}"


async def select_one(table: str, *, filters: dict[str, Any], columns: str = "*") -> dict[str, Any] | None:
    params = {"select": columns, "limit": "1"}
    params.update({k: f"eq.{v}" for k, v in filters.items()})
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=_headers(), params=params)
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase select failed: {response.text}")
    rows = response.json()
    return rows[0] if rows else None


async def select_many(table: str, *, filters: dict[str, Any] | None = None, columns: str = "*") -> list[dict[str, Any]]:
    params = {"select": columns}
    for key, value in (filters or {}).items():
        params[key] = f"eq.{value}"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=_headers(), params=params)
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase select failed: {response.text}")
    return response.json()


async def insert_one(table: str, payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=_headers(), json=payload)
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase insert failed: {response.text}")
    rows = response.json()
    return rows[0] if rows else payload


async def upsert_one(table: str, payload: dict[str, Any], on_conflict: str) -> dict[str, Any]:
    headers = _headers()
    headers["Prefer"] = f"resolution=merge-duplicates,return=representation"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=headers,
            params={"on_conflict": on_conflict},
            json=payload,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase upsert failed: {response.text}")
    rows = response.json()
    return rows[0] if rows else payload


async def update_one(table: str, *, filters: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    params = {k: f"eq.{v}" for k, v in filters.items()}
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.patch(f"{SUPABASE_URL}/rest/v1/{table}", headers=_headers(), params=params, json=payload)
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase update failed: {response.text}")
    rows = response.json()
    return rows[0] if rows else None
