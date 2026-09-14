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
replace_once(main, "from backend.routes.auth_v2 import router as auth_v2_router\n", "from backend.routes.auth_v2 import router as auth_v2_router\nfrom backend.routes.stories_v2 import router as stories_v2_router\n", "main.py auth imports")
replace_once(main, "app.include_router(auth_v2_router)\n", "app.include_router(auth_v2_router)\napp.include_router(stories_v2_router)\n", "main.py router registration")

old_guard = '''async def _validate_supabase_access_token(token: str) -> str:\n    if not SUPABASE_URL or not SUPABASE_ANON_KEY:\n'''
new_guard = '''async def _validate_supabase_access_token(token: str) -> str:\n    # The phone-auth flow returns an application JWT backed by auth_sessions.\n    # Validate that revocable session first; otherwise fall back to a Supabase Auth JWT.\n    from backend.core.security import decode_access_token\n    if os.getenv("JWT_SECRET", ""):\n        try:\n            payload = decode_access_token(token)\n            session = await supabase_db_request("GET", "auth_sessions", query=f"?select=user_id,expires_at,revoked_at&token_jti=eq.{payload['jti']}&limit=1")\n            row = session[0] if session else None\n            if not row or row.get("revoked_at") or str(row.get("user_id")) != str(payload.get("sub")):\n                raise HTTPException(status_code=401, detail="Invalid or revoked session")\n            expiry = _parse_datetime(row.get("expires_at"))\n            if expiry and expiry <= datetime.now(timezone.utc):\n                raise HTTPException(status_code=401, detail="Session expired")\n            return str(payload["sub"])\n        except HTTPException:\n            raise\n        except Exception:\n            pass\n\n    if not SUPABASE_URL or not SUPABASE_ANON_KEY:\n'''
main_text = main.read_text(encoding="utf-8")
if "decode_access_token(token)" not in main_text:
    if old_guard not in main_text:
        raise SystemExit("beta hardening v7: auth guard is neither legacy nor already patched")
    main_text = main_text.replace(old_guard, new_guard, 1)
    main.write_text(main_text, encoding="utf-8")

text = main.read_text(encoding="utf-8")
text = text.replace('max_body = 1 * 1024 * 1024 if "application/json" in content_type else 2 * 1024 * 1024', 'max_body = 1 * 1024 * 1024 if "application/json" in content_type else 25 * 1024 * 1024', 1)
main.write_text(text, encoding="utf-8")

env_example = ROOT / ".env.example"
env = env_example.read_text(encoding="utf-8")
env = env.replace("SUPABASE_URL=https://YOUR_PROJECT.supabase.co", "SUPABASE_URL=https://wvekrddnalmgfnvhycwl.supabase.co")
env_example.write_text(env, encoding="utf-8")

social_api = ROOT / "src/utils/socialApi.ts"
replace_once(social_api, "export { API_BASE };", '''export async function apiUpload<T>(path: string, file: File): Promise<T> {\n  const url = new URL(`${API_BASE}${path}`);\n  const form = new FormData();\n  form.append('file', file);\n  const headers = new Headers();\n  try {\n    const accessToken = window.localStorage.getItem('access_token');\n    if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);\n  } catch (error) {\n    console.error('Unable to read access token', error);\n  }\n  const response = await fetch(url.toString(), { method: 'POST', headers, body: form });\n  const payload = await response.json().catch(() => null);\n  if (!response.ok) {\n    const detail = payload && typeof payload === 'object' && 'detail' in payload ? String(payload.detail) : `Upload failed with status ${response.status}`;\n    throw new Error(detail);\n  }\n  return payload as T;\n}\n\nexport { API_BASE };''', "socialApi.ts uploader")

stories = ROOT / "src/components/ui/Stories.tsx"
replace_once(stories, "import { apiJson } from '../../utils/socialApi';", "import { apiJson, apiUpload } from '../../utils/socialApi';", "Stories import")
replace_once(stories, "  const [selectedMediaName, setSelectedMediaName] = useState('');", "  const [selectedMediaName, setSelectedMediaName] = useState('');\n  const [selectedMediaFile, setSelectedMediaFile] = useState<File | null>(null);", "Stories media state")
replace_once(stories, "    setSelectedMediaName(file.name);", "    setSelectedMediaName(file.name);\n    setSelectedMediaFile(file);", "Stories file selection")
old_publish = '''    try {\n      await apiJson('/api/stories', {\n        method: 'POST',\n        body: JSON.stringify({\n          media_name: selectedMediaName,'''
new_publish = '''    try {\n      if (!selectedMediaFile) throw new Error('Selected media is no longer available. Please choose it again.');\n      const upload = await apiUpload<{ success: boolean; path: string; media_type: 'image' | 'video' }>('/api/stories/upload', selectedMediaFile);\n      await apiJson('/api/stories', {\n        method: 'POST',\n        body: JSON.stringify({\n          media_name: upload.path,\n          media_type: upload.media_type,'''
replace_once(stories, old_publish, new_publish, "Stories publish upload")
replace_once(stories, "      setSelectedMediaName('');", "      setSelectedMediaName('');\n      setSelectedMediaFile(null);", "Stories publish reset")
print("beta hardening v7 completed")
