from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ensure_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"Required anchor missing in {path}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_all(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        return
    path.write_text(text.replace(old, new), encoding="utf-8")


def harden_main() -> None:
    main = ROOT / "main.py"

    ensure_once(
        main,
        "from backend.routes.auth_v2 import router as auth_v2_router\n",
        "from backend.routes.auth_v2 import router as auth_v2_router\nfrom backend.core.security import hash_otp, verify_otp_hash\n",
    )

    if "async def authenticated_api_guard(" not in main.read_text(encoding="utf-8"):
        guard = '''PUBLIC_API_PATHS = {\n    "/api/auth/login",\n    "/api/auth/signup",\n    "/api/auth/otp/send",\n    "/api/auth/otp/verify",\n    "/api/auth/availability",\n    "/api/auth/forgot-password",\n    "/api/auth/refresh",\n    "/api/auth/google",\n    "/api/health",\n}\n\n\nasync def _validate_supabase_access_token(token: str) -> str:\n    if not SUPABASE_URL or not SUPABASE_ANON_KEY:\n        raise HTTPException(status_code=503, detail="Authentication service is not configured")\n    if not token or len(token) > 8192:\n        raise HTTPException(status_code=401, detail="Invalid access token")\n    try:\n        async with httpx.AsyncClient(timeout=10.0) as client:\n            response = await client.get(\n                f"{SUPABASE_URL}/auth/v1/user",\n                headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"},\n            )\n    except httpx.HTTPError as exc:\n        raise HTTPException(status_code=503, detail="Authentication service unavailable") from exc\n    if response.status_code != 200:\n        raise HTTPException(status_code=401, detail="Invalid or expired access token")\n    try:\n        user = response.json()\n    except ValueError as exc:\n        raise HTTPException(status_code=401, detail="Invalid authentication response") from exc\n    user_id = user.get("id") if isinstance(user, dict) else None\n    if not user_id:\n        raise HTTPException(status_code=401, detail="Invalid access token")\n    return str(user_id)\n\n\n@app.middleware("http")\nasync def authenticated_api_guard(request: Request, call_next):\n    path = request.url.path\n    if request.method == "OPTIONS" or not path.startswith("/api/"):\n        return await call_next(request)\n    if path in PUBLIC_API_PATHS or path.startswith("/api/admin-auth/"):\n        return await call_next(request)\n\n    authorization = request.headers.get("authorization", "")\n    if not authorization.lower().startswith("bearer "):\n        return JSONResponse(status_code=401, content={"success": False, "detail": "Authentication required", "request_id": getattr(request.state, "request_id", None)})\n    token = authorization.split(" ", 1)[1].strip()\n    try:\n        user_id = await _validate_supabase_access_token(token)\n    except HTTPException as exc:\n        return JSONResponse(status_code=exc.status_code, content={"success": False, "detail": exc.detail, "request_id": getattr(request.state, "request_id", None)})\n\n    # Legacy handlers consume x-user-id; overwrite it from the server-validated token.\n    request.scope["headers"] = [(key, value) for key, value in request.scope.get("headers", []) if key.lower() != b"x-user-id"] + [(b"x-user-id", user_id.encode("utf-8"))]\n    return await call_next(request)\n\n\n'''
        ensure_once(main, '@app.exception_handler(RequestValidationError)\n', guard + '@app.exception_handler(RequestValidationError)\n')

    ensure_once(
        main,
        '''    data = {\n        "content": req.content,\n        "image_url": req.image_url,\n        "visibility": req.visibility,\n        "location": req.location,\n        "tags": req.tags or [],\n    }\n    result = await supabase_db_request("POST", "posts", data)\n''',
        '''    current_user_id = resolve_current_user_id(x_user_id)\n    data = {\n        "content": req.content.strip(),\n        "image_url": req.image_url,\n        "visibility": req.visibility,\n        "location": req.location,\n        "tags": req.tags or [],\n        "user_id": current_user_id,\n    }\n    result = await supabase_db_request("POST", "posts", data)\n''',
    )

    ensure_once(
        main,
        '''@app.delete("/api/posts/{post_id}")\nasync def delete_post(post_id: str):\n    """Delete a post."""\n    query = f"?id=eq.{post_id}"\n    await supabase_db_request("DELETE", "posts", query=query)\n    return {"success": True, "message": "Post deleted"}\n''',
        '''@app.delete("/api/posts/{post_id}")\nasync def delete_post(post_id: str, x_user_id: Optional[str] = Header(default=None)):\n    """Delete only a post owned by the authenticated user."""\n    current_user_id = resolve_current_user_id(x_user_id)\n    if not re.fullmatch(r"[0-9a-fA-F-]{36}", post_id or ""):\n        raise HTTPException(status_code=400, detail="Invalid post id")\n    query = f"?id=eq.{post_id}&user_id=eq.{current_user_id}"\n    result = await supabase_db_request("DELETE", "posts", query=query)\n    if not result:\n        raise HTTPException(status_code=404, detail="Post not found")\n    return {"success": True, "message": "Post deleted"}\n''',
    )

    ensure_once(
        main,
        '''class PostRequest(BaseModel):\n    content: str\n    image_url: Optional[str] = None\n    visibility: Optional[str] = 'public'\n    location: Optional[str] = 'Secure feed'\n    tags: Optional[List[str]] = []\n''',
        '''class PostRequest(BaseModel):\n    content: str = Field(min_length=1, max_length=5000)\n    image_url: Optional[str] = Field(default=None, max_length=2048)\n    visibility: str = Field(default='public', pattern='^(public|followers|private)$')\n    location: str = Field(default='Secure feed', max_length=200)\n    tags: List[str] = Field(default_factory=list, max_length=20)\n\n    @field_validator("content")\n    @classmethod\n    def normalize_content(cls, value: str) -> str:\n        value = value.strip()\n        if not value:\n            raise ValueError("Content cannot be empty")\n        return value\n''',
    )

    # Replace both legacy OTP storage sites; never retain plaintext OTPs.
    replace_all(main, '"otp_code": otp_code,\n        "verified": False,', '"otp_hash": hash_otp(challenge_id, otp_code),\n        "verified": False,\n        "attempts": 0,\n        "max_attempts": 5,')
    replace_all(
        main,
        '''    if not re.match(r"^\\d{6}$", req.otp_code or ""):\n        raise HTTPException(status_code=400, detail="Enter a valid 6-digit OTP")\n\n    if challenge["otp_code"] != req.otp_code:\n        raise HTTPException(status_code=400, detail="Incorrect OTP code")\n\n    challenge["verified"] = True\n''',
        '''    if not re.match(r"^\\d{6}$", req.otp_code or ""):\n        raise HTTPException(status_code=400, detail="Enter a valid 6-digit OTP")\n    if int(challenge.get("attempts", 0)) >= int(challenge.get("max_attempts", 5)):\n        raise HTTPException(status_code=429, detail="Too many OTP attempts")\n    if not verify_otp_hash(req.challenge_id, req.otp_code, challenge.get("otp_hash", "")):\n        challenge["attempts"] = int(challenge.get("attempts", 0)) + 1\n        raise HTTPException(status_code=400, detail="Incorrect OTP code")\n\n    challenge["verified"] = True\n''',
    )
    replace_all(
        main,
        'if os.getenv("EXPOSE_DEV_OTP", "true").lower() == "true":',
        'if os.getenv("EXPOSE_DEV_OTP", "false").lower() == "true" and os.getenv("ENVIRONMENT", "production").lower() != "production":',
    )

    ensure_once(
        main,
        '''    token = authorization.split(" ")[1]\n\n    user_info = await supabase_auth_request("user", {}, method="GET")\n''',
        '''    token = authorization.split(" ", 1)[1].strip()\n    user_id = await _validate_supabase_access_token(token)\n    user_info = await supabase_auth_user_request(token)\n    user_info.setdefault("id", user_id)\n''',
    )

    ensure_once(
        main,
        '''async def supabase_db_request(method: str, table: str, payload: dict = None, query: str = "") -> dict:\n''',
        '''async def supabase_auth_user_request(access_token: str) -> dict:\n    if not SUPABASE_URL or not SUPABASE_ANON_KEY:\n        raise HTTPException(status_code=503, detail="Supabase configuration missing")\n    async with httpx.AsyncClient(timeout=10.0) as client:\n        response = await client.get(\n            f"{SUPABASE_URL}/auth/v1/user",\n            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {access_token}"},\n        )\n    if response.status_code >= 400:\n        raise HTTPException(status_code=401, detail="Invalid or expired access token")\n    try:\n        return response.json()\n    except ValueError as exc:\n        raise HTTPException(status_code=502, detail="Invalid authentication response") from exc\n\n\nasync def supabase_db_request(method: str, table: str, payload: dict = None, query: str = "") -> dict:\n''',
    )

    ensure_once(
        main,
        '''@app.post("/api/auth/logout")\nasync def api_logout(authorization: Optional[str] = None):\n    """Logout user and invalidate session."""\n    if authorization and authorization.startswith("Bearer "):\n        token = authorization.split(" ")[1]\n        await supabase_auth_request("logout", {}, method="POST")\n\n    return {"success": True, "message": "Logged out successfully"}\n''',
        '''@app.post("/api/auth/logout")\nasync def api_logout(request: Request):\n    """Logout the authenticated Supabase session."""\n    authorization = request.headers.get("authorization", "")\n    if not authorization.lower().startswith("bearer "):\n        raise HTTPException(status_code=401, detail="Authentication required")\n    token = authorization.split(" ", 1)[1].strip()\n    await _validate_supabase_access_token(token)\n    try:\n        async with httpx.AsyncClient(timeout=10.0) as client:\n            response = await client.post(\n                f"{SUPABASE_URL}/auth/v1/logout",\n                headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"},\n            )\n        if response.status_code >= 400:\n            raise HTTPException(status_code=502, detail="Logout failed")\n    except httpx.HTTPError as exc:\n        raise HTTPException(status_code=503, detail="Authentication service unavailable") from exc\n    return {"success": True, "message": "Logged out successfully"}\n''',
    )


if __name__ == "__main__":
    harden_main()
    print("beta hardening v2 completed")
