from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
main = ROOT / "main.py"
text = main.read_text(encoding="utf-8")
old = '''    except HTTPException:\n        query = f"?select=id,user_id,content,image_url,visibility,location,tags,created_at,deleted_at&deleted_at=is.null&order=created_at.desc,id.desc&limit={requested_limit}&offset={requested_offset}"\n        result = await supabase_db_request("GET", "posts", query=query)\n\n    return {"success": True, "posts": result or []}\n'''
new = '''    except HTTPException:\n        # Safe compatibility path for deployments where the feed RPC migration is not applied yet.\n        fetch_limit = min(requested_offset + requested_limit * 4, 200)\n        query = f"?select=id,user_id,content,image_url,visibility,location,tags,created_at,deleted_at&deleted_at=is.null&order=created_at.desc,id.desc&limit={fetch_limit}&offset=0"\n        candidates = await supabase_db_request("GET", "posts", query=query)\n        visible = []\n        for post in candidates or []:\n            owner_id = str(post.get("user_id") or "")\n            visibility = post.get("visibility") or "public"\n            if owner_id == str(current_user_id):\n                visible.append(post)\n            elif visibility == "public" and not social_graph.is_blocked(str(current_user_id), owner_id):\n                visible.append(post)\n            elif visibility == "followers" and not social_graph.is_blocked(str(current_user_id), owner_id) and social_graph._is_following(str(current_user_id), owner_id):\n                visible.append(post)\n            if len(visible) >= requested_offset + requested_limit:\n                break\n        result = visible[requested_offset:requested_offset + requested_limit]\n\n    return {"success": True, "posts": result or []}\n'''
if old in text:
    text = text.replace(old, new, 1)
main.write_text(text, encoding="utf-8")
print("beta hardening v6 completed")
