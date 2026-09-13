from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


def replace_block(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.DOTALL)
    if count == 0:
        if replacement in text:
            return text
        raise SystemExit(f"Required block not found: {label}")
    return updated


def main() -> None:
    text = MAIN.read_text(encoding="utf-8")

    helper = '''async def _get_authorized_post(post_id: str, viewer_id: str) -> dict:\n    if not re.fullmatch(r"[0-9a-fA-F-]{36}", post_id or ""):\n        raise HTTPException(status_code=400, detail="Invalid post id")\n    query = f"?select=id,user_id,visibility,deleted_at&id=eq.{post_id}&limit=1"\n    rows = await supabase_db_request("GET", "posts", query=query)\n    if not rows:\n        raise HTTPException(status_code=404, detail="Post not found")\n    post = rows[0]\n    if post.get("deleted_at"):\n        raise HTTPException(status_code=404, detail="Post not found")\n    owner_id = str(post.get("user_id") or "")\n    visibility = post.get("visibility") or "public"\n    if owner_id != str(viewer_id):\n        if visibility == "private":\n            raise HTTPException(status_code=403, detail="Post is private")\n        if visibility == "followers" and not social_graph._is_following(str(viewer_id), owner_id):\n            raise HTTPException(status_code=403, detail="Post is limited to followers")\n        if social_graph.is_blocked(str(viewer_id), owner_id):\n            raise HTTPException(status_code=403, detail="Post unavailable")\n    return post\n\n\n'''
    if "async def _get_authorized_post(" not in text:
        text = text.replace("# Posts API Routes\n", helper + "# Posts API Routes\n", 1)

    interaction = '''@app.post("/api/posts/{post_id}/interactions")\nasync def post_interaction(post_id: str, req: PostInteractionRequest, x_user_id: Optional[str] = Header(default=None)):\n    """Persist post engagement in Supabase instead of process memory."""\n    current_user_id = resolve_current_user_id(x_user_id)\n    post = await _get_authorized_post(post_id, current_user_id)\n    interaction_type = (req.interaction_type or "").strip().lower()\n    allowed = {"like", "dislike", "comment", "share", "impression", "hashtag_click", "watch_time"}\n    if interaction_type not in allowed:\n        raise HTTPException(status_code=400, detail="Unsupported interaction type")\n\n    if interaction_type == "like":\n        try:\n            await supabase_db_request("POST", "post_likes", {"post_id": post_id, "user_id": current_user_id})\n        except HTTPException as exc:\n            if exc.status_code != 409:\n                raise\n    elif interaction_type == "dislike":\n        await supabase_db_request("DELETE", "post_likes", query=f"?post_id=eq.{post_id}&user_id=eq.{current_user_id}")\n    elif interaction_type == "share":\n        try:\n            await supabase_db_request("POST", "post_shares", {"post_id": post_id, "user_id": current_user_id})\n        except HTTPException as exc:\n            if exc.status_code != 409:\n                raise\n    elif interaction_type in {"impression", "watch_time"}:\n        metadata = req.metadata or {}\n        watch_ms = int(metadata.get("watch_ms", 0) or 0) if interaction_type == "watch_time" else 0\n        await supabase_db_request("POST", "post_views", {"post_id": post_id, "user_id": current_user_id, "watch_ms": max(0, watch_ms)})\n\n    event_type = "watch" if interaction_type == "watch_time" else interaction_type\n    if event_type in {"impression", "click", "like", "comment", "share", "bookmark", "view", "watch"}:\n        await supabase_db_request("POST", "feed_events", {"user_id": current_user_id, "post_id": post_id, "event_type": event_type, "value": None, "session_id": (req.metadata or {}).get("session_id")})\n\n    return {"success": True, "event": {"post_id": post_id, "user_id": current_user_id, "interaction_type": interaction_type}, "post": post}\n\n\n'''
    text = replace_block(text, r'@app\.post\("/api/posts/\{post_id\}/interactions"\).*?(?=@app\.post\("/api/posts/\{post_id\}/comments")', interaction, "post interaction")

    comment = '''@app.post("/api/posts/{post_id}/comments")\nasync def add_post_comment(post_id: str, req: PostCommentRequest, x_user_id: Optional[str] = Header(default=None)):\n    current_user_id = resolve_current_user_id(x_user_id)\n    await _get_authorized_post(post_id, current_user_id)\n    content = (req.comment or "").strip()\n    if not content:\n        raise HTTPException(status_code=400, detail="Comment cannot be empty")\n    if len(content) > 2000:\n        raise HTTPException(status_code=422, detail="Comment is too long")\n    row = await supabase_db_request("POST", "post_comments", {"post_id": post_id, "user_id": current_user_id, "content": content})\n    comment = row[0] if isinstance(row, list) and row else row\n    return {"success": True, "comment": comment, "comments_count": len(await supabase_db_request("GET", "post_comments", query=f"?select=id&post_id=eq.{post_id}"))}\n\n\n@app.get("/api/posts/{post_id}/comments")\nasync def list_post_comments(post_id: str, x_user_id: Optional[str] = Header(default=None)):\n    current_user_id = resolve_current_user_id(x_user_id)\n    await _get_authorized_post(post_id, current_user_id)\n    comments = await supabase_db_request("GET", "post_comments", query=f"?select=id,post_id,user_id,content,created_at,updated_at&post_id=eq.{post_id}&order=created_at.asc&limit=100")\n    return {"success": True, "comments": comments}\n\n\n'''
    text = replace_block(text, r'@app\.post\("/api/posts/\{post_id\}/comments"\).*?(?=@app\.get\("/api/recommendation/events"\))', comment, "post comments")

    feed = '''@app.get("/api/posts/feed")\nasync def get_feed(limit: int = 20, offset: int = 0, x_user_id: Optional[str] = Header(default=None)):\n    """Return a bounded, database-filtered feed for the authenticated user."""\n    current_user_id = resolve_current_user_id(x_user_id)\n    requested_limit = max(1, min(int(limit), 50))\n    requested_offset = max(0, int(offset))\n\n    if not SUPABASE_URL:\n        visible_posts = [post for post in in_memory_posts if can_view_author_posts(current_user_id, post.get("user_id", ""))]\n        ranked = rank_posts_for_feed(visible_posts)\n        return {"success": True, "posts": ranked[requested_offset:requested_offset + requested_limit]}\n\n    try:\n        result = await supabase_db_request(\n            "POST",\n            "rpc/get_feed_posts",\n            {"viewer_id": current_user_id, "page_limit": requested_limit, "page_offset": requested_offset},\n        )\n    except HTTPException:\n        # Safe fallback for deployments where the feed RPC migration has not yet been applied.\n        query = f"?select=id,user_id,content,image_url,visibility,location,tags,created_at,deleted_at&deleted_at=is.null&order=created_at.desc,id.desc&limit={requested_limit}&offset={requested_offset}"\n        result = await supabase_db_request("GET", "posts", query=query)\n\n    return {"success": True, "posts": result or []}\n\n\n'''
    text = replace_block(text, r'@app\.get\("/api/posts/feed"\).*?(?=@app\.post\("/api/admin/moderation/flag"\))', feed, "feed")

    # Bound comment payloads at the model boundary too.
    text = text.replace("class PostCommentRequest(BaseModel):\n    comment: str", "class PostCommentRequest(BaseModel):\n    comment: str = Field(min_length=1, max_length=2000)", 1)
    MAIN.write_text(text, encoding="utf-8")
    print("beta hardening v4 completed")


if __name__ == "__main__":
    main()
