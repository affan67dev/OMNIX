from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"beta hardening v7: expected anchor missing in {label}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


main = ROOT / "main.py"
replace_once(
    main,
    "from backend.routes.auth_v2 import router as auth_v2_router\n",
    "from backend.routes.auth_v2 import router as auth_v2_router\nfrom backend.routes.stories_v2 import router as stories_v2_router\n",
    "main.py auth imports",
)
replace_once(
    main,
    "app.include_router(auth_v2_router)\n",
    "app.include_router(auth_v2_router)\napp.include_router(stories_v2_router)\n",
    "main.py router registration",
)

# The application-issued JWT is stored in auth_sessions and is the token returned by /api/v2/auth/phone/verify.
# The request guard must accept that token instead of incorrectly requiring a Supabase Auth JWT.
old_guard = '''async def _validate_supabase_access_token(token: str) -> str:\n    if not SUPABASE_URL or not SUPABASE_ANON_KEY:\n'''
new_guard = '''async def _validate_supabase_access_token(token: str) -> str:\n    # Accept the application's own revocable JWT first. It is checked against the\n    # persistent auth_sessions row by get_current_user and never exposed as a secret.\n    from backend.core.security import decode_access_token\n    if os.getenv("JWT_SECRET", ""):\n        try:\n            payload = decode_access_token(token)\n            session = await supabase_db_request("GET", "auth_sessions", query=f"?select=user_id,expires_at,revoked_at&token_jti=eq.{payload['jti']}&limit=1")\n            row = session[0] if session else None\n            if not row or row.get("revoked_at") or str(row.get("user_id")) != str(payload.get("sub")):\n                raise HTTPException(status_code=401, detail="Invalid or revoked session")\n            expiry = _parse_datetime(row.get("expires_at"))\n            if expiry and expiry <= datetime.now(timezone.utc):\n                raise HTTPException(status_code=401, detail="Session expired")\n            return str(payload["sub"])\n        except HTTPException:\n            raise\n        except Exception:\n            pass\n\n    if not SUPABASE_URL or not SUPABASE_ANON_KEY:\n'''
if old_guard in main.read_text(encoding="utf-8"):
    main.write_text(main.read_text(encoding="utf-8").replace(old_guard, new_guard, 1), encoding="utf-8")

# Keep media requests possible while still enforcing a bounded API payload.
text = main.read_text(encoding="utf-8")
old_limit = 'max_body = 1 * 1024 * 1024 if "application/json" in content_type else 2 * 1024 * 1024'
new_limit = 'max_body = 1 * 1024 * 1024 if "application/json" in content_type else 25 * 1024 * 1024'
if old_limit in text:
    text = text.replace(old_limit, new_limit, 1)
main.write_text(text, encoding="utf-8")

# Make the checked-in example point at the requested project without including any secret key.
env_example = ROOT / ".env.example"
env = env_example.read_text(encoding="utf-8")
env = env.replace("SUPABASE_URL=https://YOUR_PROJECT.supabase.co", "SUPABASE_URL=https://wvekrddnalmgfnvhycwl.supabase.co")
env_example.write_text(env, encoding="utf-8")

print("beta hardening v7 completed")
