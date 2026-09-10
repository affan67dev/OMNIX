from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one match in {path}: {count}")
    path.write_text(text.replace(old, new), encoding="utf-8")


# FastAPI hardening: global SlowAPI default, bounded request metadata, and safe validation errors.
main = ROOT / "main.py"
replace_once(
    main,
    "from fastapi import FastAPI, HTTPException, Depends, Request, Header\n",
    "from fastapi import FastAPI, HTTPException, Depends, Request, Header\nfrom fastapi.exceptions import RequestValidationError\n",
)
replace_once(
    main,
    "limiter = Limiter(key_func=get_remote_address)\napp.state.limiter = limiter\n",
    '''limiter = Limiter(\n    key_func=get_remote_address,\n    default_limits=[os.getenv("GLOBAL_RATE_LIMIT", "120/minute")],\n    storage_uri=os.getenv("RATE_LIMIT_STORAGE_URI", "memory://"),\n    headers_enabled=True,\n)\napp.state.limiter = limiter\n''',
)
replace_once(
    main,
    '''@app.middleware("http")\nasync def backend_request_guard(request: Request, call_next):\n    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))\n''',
    '''@app.middleware("http")\nasync def backend_request_guard(request: Request, call_next):\n    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))\n    # Reject oversized API bodies before application/DB work. Direct-to-Storage media\n    # uploads should not traverse this API; JSON APIs are deliberately small.\n    content_length = request.headers.get("content-length")\n    if content_length:\n        try:\n            body_size = int(content_length)\n        except ValueError:\n            body_size = 0\n        content_type = request.headers.get("content-type", "").lower()\n        max_body = 1 * 1024 * 1024 if "application/json" in content_type else 2 * 1024 * 1024\n        if body_size > max_body:\n            return JSONResponse(\n                status_code=413,\n                content={"success": False, "detail": "Request payload is too large", "request_id": request_id},\n            )\n''',
)
replace_once(
    main,
    '''@app.exception_handler(HTTPException)\nasync def app_http_exception_handler(request: Request, exc: HTTPException):\n''',
    '''@app.exception_handler(RequestValidationError)\nasync def app_validation_exception_handler(request: Request, exc: RequestValidationError):\n    return JSONResponse(\n        status_code=422,\n        content={\n            "success": False,\n            "detail": "Invalid request payload",\n            "request_id": getattr(request.state, "request_id", None),\n        },\n    )\n\n\n@app.exception_handler(HTTPException)\nasync def app_http_exception_handler(request: Request, exc: HTTPException):\n''',
)

# Client feed: small pages instead of a 20-row initial dump, plus opportunistic media caching.
feed = ROOT / "src/components/ui/HomeFeed.tsx"
replace_once(
    feed,
    "import { apiJson } from '../../utils/socialApi';\n",
    "import { apiJson } from '../../utils/socialApi';\nimport { prefetchMedia } from '../../utils/mediaCache';\n",
)
replace_once(
    feed,
    "  const [statusMessage, setStatusMessage] = useState('');\n",
    "  const [statusMessage, setStatusMessage] = useState('');\n  const [feedOffset, setFeedOffset] = useState(0);\n  const [loadingMore, setLoadingMore] = useState(false);\n",
)
replace_once(
    feed,
    "query: { limit: 20 },",
    "query: { limit: 5, offset: 0 },",
)
replace_once(
    feed,
    "          setPosts(mappedPosts);\n\n          for (const item of mappedPosts) {",
    """          setPosts(mappedPosts);\n          setFeedOffset(mappedPosts.length);\n          void prefetchMedia(mappedPosts.slice(0, 3).map((item) => item.image_url ?? '').filter(Boolean));\n\n          for (const item of mappedPosts) {""",
)
insert_before = "  const toggledPosts = useMemo(() => {\n"
load_more = '''  const loadMore = async () => {\n    if (loadingMore) return;\n    setLoadingMore(true);\n    try {\n      const data = await apiJson<{ success: boolean; posts: Record<string, unknown>[] }>('/api/posts/feed', {\n        query: { limit: 5, offset: feedOffset },\n      });\n      if (!data?.success) return;\n      const next = (data.posts ?? []).map((post: Record<string, unknown>) => ({\n        id: typeof post.id === 'string' ? post.id : `post-${String(post.content ?? Date.now())}`,\n        author: post.user_id ? `user_${String(post.user_id).slice(0, 6)}` : 'omni_user',\n        likes: typeof post.likes === 'number' ? post.likes : 0,\n        caption: typeof post.content === 'string' ? post.content : 'Shared from the private network',\n        tags: Array.isArray(post.tags) ? post.tags.filter((tag): tag is string => typeof tag === 'string') : [],\n        mentions: Array.isArray(post.mentions) ? post.mentions.filter((mention): mention is string => typeof mention === 'string') : [],\n        location: typeof post.location === 'string' ? post.location : 'Secure feed',\n        visibility: typeof post.visibility === 'string' ? post.visibility : 'public',\n        created_at: typeof post.created_at === 'string' ? post.created_at : undefined,\n        image_url: typeof post.image_url === 'string' ? post.image_url : null,\n        comments_count: typeof post.comments_count === 'number' ? post.comments_count : 0,\n        shares_count: typeof post.shares_count === 'number' ? post.shares_count : 0,\n        impression_count: typeof post.impression_count === 'number' ? post.impression_count : 0,\n      }));\n      setPosts((current) => [...current, ...next.filter((item) => !current.some((existing) => existing.id === item.id))]);\n      setFeedOffset((current) => current + next.length);\n      void prefetchMedia(next.slice(0, 3).map((item) => item.image_url ?? '').filter(Boolean));\n    } finally {\n      setLoadingMore(false);\n    }\n  };\n\n'''
replace_once(feed, insert_before, load_more + insert_before)
# Add a bounded pagination control near the end of the rendered feed.
replace_once(
    feed,
    "      )}\n    </div>\n  );\n}",
    """      )}\n      {!loading && toggledPosts.length >= 5 ? (\n        <button type=\"button\" onClick={() => void loadMore()} disabled={loadingMore} style={{ margin: '4px 14px 18px', width: 'calc(100% - 28px)', padding: '10px', borderRadius: '999px', border: '1px solid #334155', background: '#0f172a', color: '#f8fafc', cursor: loadingMore ? 'wait' : 'pointer' }}>\n          {loadingMore ? 'Loading…' : 'Load 5 more'}\n        </button>\n      ) : null}\n    </div>\n  );\n}""",
)

print("production hardening migration completed")
