import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import httpx
import jwt
from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, EmailStr

from backend.auth_utils import require_admin_user

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_TTL_MINUTES = int(os.getenv("JWT_TTL_MINUTES", "60"))
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    username: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user_id: str, email: str, username: str) -> str:
    if not JWT_SECRET:
        raise RuntimeError("JWT_SECRET must be configured")

    payload = {
        "sub": str(user_id),
        "email": email,
        "username": username,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=JWT_TTL_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_local_connection() -> sqlite3.Connection:
    conn = sqlite3.connect("database/users.db")
    conn.row_factory = sqlite3.Row
    return conn


def ensure_local_user_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


async def fetch_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{SUPABASE_URL}/rest/v1/users?email=eq.{email}&select=id,email,username,password_hash",
                    headers={
                        "apikey": SUPABASE_SERVICE_ROLE_KEY,
                        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                        "Content-Type": "application/json",
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    if data:
                        return data[0]
        except Exception:
            pass

    conn = get_local_connection()
    try:
        ensure_local_user_table(conn)
        row = conn.execute(
            "SELECT id, email, username, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "email": row["email"],
            "username": row["username"],
            "password_hash": row["password_hash"],
        }
    finally:
        conn.close()


async def create_user_record(user_data: Dict[str, Any]) -> Dict[str, Any]:
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{SUPABASE_URL}/rest/v1/users",
                    json=[user_data],
                    headers={
                        "apikey": SUPABASE_SERVICE_ROLE_KEY,
                        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                        "Content-Type": "application/json",
                        "Prefer": "return=representation",
                    },
                )
                if response.status_code in {200, 201, 204}:
                    try:
                        payload = response.json()
                        if isinstance(payload, list) and payload:
                            return payload[0]
                        return payload
                    except ValueError:
                        return user_data
        except Exception:
            pass

    conn = get_local_connection()
    try:
        ensure_local_user_table(conn)
        cursor = conn.execute(
            "INSERT INTO users (email, username, password_hash) VALUES (?, ?, ?)",
            (user_data["email"], user_data["username"], user_data["password_hash"]),
        )
        conn.commit()
        user_data["id"] = cursor.lastrowid
        return user_data
    finally:
        conn.close()


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(user: UserRegister):
    if not user.email or not user.password or not user.username:
        raise HTTPException(status_code=400, detail="Invalid data")

    email = str(user.email)
    username = user.username.lower().strip()
    existing_user = await fetch_user_by_email(email)
    if existing_user:
        raise HTTPException(status_code=409, detail="User already exists")

    created_user = await create_user_record(
        {
            "email": email,
            "username": username,
            "password_hash": hash_password(user.password),
        }
    )

    token = create_access_token(
        str(created_user.get("id", "local")),
        email,
        username,
    )

    return {
        "status": "success",
        "message": f"User {username} registered successfully",
        "token": token,
        "user": {
            "id": created_user.get("id", "local"),
            "email": email,
            "username": username,
        },
    }


@router.post("/login")
async def login_user(user: UserLogin):
    email = str(user.email)
    existing_user = await fetch_user_by_email(email)
    if not existing_user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(user.password, existing_user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(
        str(existing_user.get("id", "local")),
        email,
        existing_user.get("username", email.split("@", 1)[0]),
    )

    return {
        "status": "success",
        "token": token,
        "user": {
            "id": existing_user.get("id", "local"),
            "email": email,
            "username": existing_user.get("username", email.split("@", 1)[0]),
        },
    }


@router.get("/metrics-stream")
async def get_app_live_metrics(authorization: str | None = Header(default=None)):
    await require_admin_user(authorization)
    return {
        "active_users": 142,
        "api_calls_count": 5230,
        "database_status": "connected_supabase"
    }
