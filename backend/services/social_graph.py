from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from backend.services.supabase_db import delete_many_sync, insert_one_sync, select_many_sync, select_one_sync, update_one_sync, upsert_one_sync


def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def iso_now() -> str:
    return utc_now().isoformat()

def resolve_expiry(duration: str) -> Optional[str]:
    presets = {"8_hours": timedelta(hours=8), "1_week": timedelta(weeks=1), "always": None}
    if duration not in presets: raise ValueError("Unsupported duration")
    delta = presets[duration]
    return None if delta is None else (utc_now() + delta).isoformat()

class SocialGraphError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail); self.status_code = status_code; self.detail = detail

class _DatabaseUsersView:
    """Read-only compatibility view for legacy callers; it stores nothing locally."""
    def values(self):
        try: return [SocialGraphService._normalize_profile(row) for row in select_many_sync("profiles", columns="user_id,username,full_name,bio,profile_pic_url,cover_pic_url,is_private,is_blocked_from_search,omni_score,followers_count,following_count,posts_count,streak,created_at,updated_at")]
        except Exception: return []
    def get(self, user_id: str, default=None):
        if user_id == "local-user": return default
        try: return SocialGraphService._normalize_profile(select_one_sync("profiles", filters={"user_id": user_id}, columns="user_id,username,full_name,bio,profile_pic_url,cover_pic_url,is_private,is_blocked_from_search,omni_score,followers_count,following_count,posts_count,streak,created_at,updated_at") or {}) if select_one_sync("profiles", filters={"user_id": user_id}, columns="user_id") else default
        except Exception: return default
    def __contains__(self, user_id: object) -> bool:
        if not isinstance(user_id, str): return False
        try: return select_one_sync("profiles", filters={"user_id": user_id}, columns="user_id") is not None
        except Exception: return False

class _DatabaseConversationsView:
    def get(self, conversation_id: str, default=None):
        try: return select_one_sync("conversations", filters={"id": conversation_id}, columns="id,is_group,name,created_by,created_at,updated_at") or default
        except Exception: return default

class SocialGraphService:
    """Database-backed social/chat service with no persistent process-level user state."""
    REPORT_REASONS = {"spam", "harassment", "inappropriate_content", "fraud"}
    MUTE_TYPES = {"user", "posts", "stories"}

    # Compatibility adapters are query-backed, not dictionaries containing user data.
    @property
    def users(self): return _DatabaseUsersView()
    @property
    def conversations(self): return _DatabaseConversationsView()

    @staticmethod
    def _validate_uuid(value: str, label: str = "user id") -> str:
        try: return str(UUID(str(value)))
        except (TypeError, ValueError): raise SocialGraphError(400, f"Invalid {label}")

    def _profile(self, user_id: str) -> Dict[str, Any]:
        user_id = self._validate_uuid(user_id)
        row = select_one_sync("profiles", filters={"user_id": user_id}, columns="id,user_id,username,full_name,bio,profile_pic_url,cover_pic_url,is_private,is_blocked_from_search,omni_score,followers_count,following_count,posts_count,streak,created_at,updated_at")
        if not row: raise SocialGraphError(404, "User not found")
        return self._normalize_profile(row)

    @staticmethod
    def _normalize_profile(row: Dict[str, Any]) -> Dict[str, Any]:
        return {"id": row.get("user_id") or row.get("id"), "user_id": row.get("user_id") or row.get("id"), "username": row.get("username") or "", "display_name": row.get("full_name") or row.get("username") or "", "bio": row.get("bio") or "", "avatar_color": None, "profile_pic_url": row.get("profile_pic_url"), "cover_pic_url": row.get("cover_pic_url"), "is_private": bool(row.get("is_private")), "is_blocked_from_search": bool(row.get("is_blocked_from_search")), "omni_score": row.get("omni_score", 0), "followers_count": int(row.get("followers_count") or 0), "following_count": int(row.get("following_count") or 0), "posts_count": int(row.get("posts_count") or 0), "streak": int(row.get("streak") or 0), "created_at": row.get("created_at"), "updated_at": row.get("updated_at")}

    def _assert_user(self, user_id: str) -> str: return self._profile(user_id)["user_id"]
    def _assert_contact_available(self, current_user_id: str, target_user_id: str) -> None:
        current_user_id = self._assert_user(current_user_id); target_user_id = self._assert_user(target_user_id)
        if current_user_id != target_user_id and self.is_blocked(current_user_id, target_user_id): raise SocialGraphError(403, "User Unavailable")

    def is_blocked(self, left_user_id: str, right_user_id: str) -> bool:
        left_user_id = self._validate_uuid(left_user_id); right_user_id = self._validate_uuid(right_user_id)
        return bool(select_one_sync("blocks", filters={"blocker_id": left_user_id, "blocked_id": right_user_id}, columns="blocker_id") or select_one_sync("blocks", filters={"blocker_id": right_user_id, "blocked_id": left_user_id}, columns="blocker_id"))
    def _is_following(self, follower_id: str, following_id: str) -> bool:
        row = select_one_sync("follows", filters={"follower_id": follower_id, "following_id": following_id}, columns="status"); return bool(row and row.get("status") == "accepted")
    def _follow_request(self, requester_id: str, target_id: str, status: str = "pending") -> Optional[Dict[str, Any]]:
        row = select_one_sync("follows", filters={"follower_id": requester_id, "following_id": target_id, "status": status}, columns="follower_id,following_id,status,created_at")
        if row: row["id"] = f"{row['follower_id']}:{row['following_id']}"
        return row
    def _relationship_state(self, current_user_id: str, target_user_id: str) -> Dict[str, Any]:
        current_user_id = self._validate_uuid(current_user_id); target_user_id = self._validate_uuid(target_user_id)
        b1 = bool(select_one_sync("blocks", filters={"blocker_id": current_user_id, "blocked_id": target_user_id}, columns="blocker_id")); b2 = bool(select_one_sync("blocks", filters={"blocker_id": target_user_id, "blocked_id": current_user_id}, columns="blocker_id"))
        outgoing = self._follow_request(current_user_id, target_user_id); incoming = self._follow_request(target_user_id, current_user_id)
        return {"is_self": current_user_id == target_user_id, "is_blocked": b1 or b2, "blocked_by_current_user": b1, "blocked_by_target_user": b2, "is_following": self._is_following(current_user_id, target_user_id), "is_followed_by": self._is_following(target_user_id, current_user_id), "outgoing_follow_request": outgoing, "incoming_follow_request": incoming}
    def _profile_access(self, current_user_id: str, target_user_id: str) -> Dict[str, bool]:
        target = self._profile(target_user_id); rel = self._relationship_state(current_user_id, target_user_id); allowed = not target["is_private"] or rel["is_self"] or rel["is_following"]
        return {"can_view_full_profile": allowed, "can_view_followers": allowed, "can_view_following": allowed, "can_view_posts": allowed, "can_view_stories": allowed}

    def get_me_overview(self, current_user_id: str) -> Dict[str, Any]:
        current_user_id = self._assert_user(current_user_id)
        incoming = select_many_sync("follows", filters={"following_id": current_user_id, "status": "pending"}, columns="follower_id,following_id,status,created_at"); outgoing = select_many_sync("follows", filters={"follower_id": current_user_id, "status": "pending"}, columns="follower_id,following_id,status,created_at")
        for row in incoming + outgoing: row["id"] = f"{row['follower_id']}:{row['following_id']}"
        return {"me": self._profile(current_user_id), "pending_incoming": incoming, "pending_outgoing": outgoing, "discover": self.search_users(current_user_id, ""), "followers": self.get_followers(current_user_id, current_user_id), "following": self.get_following(current_user_id, current_user_id)}
    def search_users(self, current_user_id: str, query: str) -> List[Dict[str, Any]]:
        current_user_id = self._assert_user(current_user_id); q = (query or "").strip().lower(); results=[]
        rows = select_many_sync("profiles", columns="user_id,username,full_name,bio,profile_pic_url,is_private,is_blocked_from_search,followers_count,following_count,posts_count")
        for row in rows:
            uid = row.get("user_id")
            if not uid or self.is_blocked(current_user_id, uid) or (row.get("is_blocked_from_search") and uid != current_user_id): continue
            if q and q not in f"{row.get('username') or ''} {row.get('full_name') or ''} {row.get('bio') or ''}".lower(): continue
            p=self._normalize_profile(row); p["relationship"]=self._relationship_state(current_user_id, uid); results.append({k:p[k] for k in ("id","username","display_name","avatar_color","is_private","relationship")})
        return results
    def get_profile(self, current_user_id: str, target_user_id: str) -> Dict[str, Any]:
        self._assert_contact_available(current_user_id,target_user_id); p=self._profile(target_user_id); p["relationship"]=self._relationship_state(current_user_id,target_user_id); p["access"]=self._profile_access(current_user_id,target_user_id); p["posts"]=self.get_posts(current_user_id,target_user_id) if p["access"]["can_view_posts"] else []; return p
    def get_followers(self,current_user_id:str,target_user_id:str)->List[Dict[str,Any]]:
        self._assert_contact_available(current_user_id,target_user_id)
        if not self._profile_access(current_user_id,target_user_id)["can_view_followers"]: raise SocialGraphError(403,"Followers list is private")
        return [self._profile(r["follower_id"]) for r in select_many_sync("follows",filters={"following_id":target_user_id,"status":"accepted"},columns="follower_id")]
    def get_following(self,current_user_id:str,target_user_id:str)->List[Dict[str,Any]]:
        self._assert_contact_available(current_user_id,target_user_id)
        if not self._profile_access(current_user_id,target_user_id)["can_view_following"]: raise SocialGraphError(403,"Following list is private")
        return [self._profile(r["following_id"]) for r in select_many_sync("follows",filters={"follower_id":target_user_id,"status":"accepted"},columns="following_id")]
    def get_posts(self,current_user_id:str,target_user_id:str)->List[Dict[str,Any]]:
        self._assert_contact_available(current_user_id,target_user_id)
        if not self._profile_access(current_user_id,target_user_id)["can_view_posts"]: raise SocialGraphError(403,"Posts are private")
        return select_many_sync("posts",filters={"user_id":target_user_id},columns="*")
    def create_follow(self,current_user_id:str,target_user_id:str)->Dict[str,Any]:
        current_user_id=self._assert_user(current_user_id); target_user_id=self._assert_user(target_user_id)
        if current_user_id==target_user_id: raise SocialGraphError(400,"You cannot follow yourself")
        self._assert_contact_available(current_user_id,target_user_id); existing=self._follow_request(current_user_id,target_user_id)
        if self._is_following(current_user_id,target_user_id): return {"status":"following","relationship":self._relationship_state(current_user_id,target_user_id),"target":self._profile(target_user_id)}
        if existing: return {"status":"pending","request":existing,"relationship":self._relationship_state(current_user_id,target_user_id),"target":self._profile(target_user_id)}
        status="pending" if self._profile(target_user_id)["is_private"] else "accepted"; row=upsert_one_sync("follows",{"follower_id":current_user_id,"following_id":target_user_id,"status":status},"follower_id,following_id"); row["id"]=f"{current_user_id}:{target_user_id}"; return {"status":"pending" if status=="pending" else "following","request":row if status=="pending" else None,"relationship":self._relationship_state(current_user_id,target_user_id),"target":self._profile(target_user_id)}
    def unfollow(self,current_user_id:str,target_user_id:str)->Dict[str,Any]:
        self._assert_contact_available(current_user_id,target_user_id); delete_many_sync("follows",filters={"follower_id":current_user_id,"following_id":target_user_id}); return {"status":"not_following","relationship":self._relationship_state(current_user_id,target_user_id),"target":self._profile(target_user_id)}
    def cancel_follow_request(self,current_user_id:str,request_id:str)->Dict[str,Any]:
        parts=str(request_id).split(":",1)
        if len(parts)!=2: raise SocialGraphError(404,"Follow request not found")
        requester,target=parts; row=select_one_sync("follows",filters={"follower_id":requester,"following_id":target,"status":"pending"},columns="follower_id,following_id,status,created_at")
        if not row: raise SocialGraphError(404,"Follow request not found")
        if requester!=current_user_id: raise SocialGraphError(403,"You can only cancel your own request")
        delete_many_sync("follows",filters={"follower_id":requester,"following_id":target}); row.update({"id":str(request_id),"status":"cancelled","responded_at":iso_now()}); return row
    def respond_to_follow_request(self,current_user_id:str,request_id:str,action:str)->Dict[str,Any]:
        parts=str(request_id).split(":",1)
        if len(parts)!=2: raise SocialGraphError(404,"Follow request not found")
        requester,target=parts; row=select_one_sync("follows",filters={"follower_id":requester,"following_id":target,"status":"pending"},columns="follower_id,following_id,status,created_at")
        if not row: raise SocialGraphError(404,"Follow request not found")
        if target!=current_user_id: raise SocialGraphError(403,"Only the target user can respond")
        if action=="accept": row=update_one_sync("follows",filters={"follower_id":requester,"following_id":target},payload={"status":"accepted"}) or row
        elif action=="reject": delete_many_sync("follows",filters={"follower_id":requester,"following_id":target}); row["status"]="rejected"
        else: raise SocialGraphError(400,"Unsupported follow request action")
        row["id"]=str(request_id); row["responded_at"]=iso_now(); return row
    def update_privacy(self,current_user_id:str,is_private:bool,is_blocked_from_search:Optional[bool]=None)->Dict[str,Any]:
        self._assert_user(current_user_id); payload={"is_private":bool(is_private)}
        if is_blocked_from_search is not None: payload["is_blocked_from_search"]=bool(is_blocked_from_search)
        row=update_one_sync("profiles",filters={"user_id":current_user_id},payload=payload)
        if not row: raise SocialGraphError(404,"User not found")
        return self._normalize_profile(row)
    def block_user(self,current_user_id:str,target_user_id:str,reason:Optional[str]=None)->Dict[str,Any]:
        current_user_id=self._assert_user(current_user_id); target_user_id=self._assert_user(target_user_id)
        if current_user_id==target_user_id: raise SocialGraphError(400,"You cannot block yourself")
        row=upsert_one_sync("blocks",{"blocker_id":current_user_id,"blocked_id":target_user_id},"blocker_id,blocked_id"); delete_many_sync("follows",filters={"follower_id":current_user_id,"following_id":target_user_id}); delete_many_sync("follows",filters={"follower_id":target_user_id,"following_id":current_user_id}); row["reason"]=reason; return row
    def unblock_user(self,current_user_id:str,target_user_id:str)->None:
        self._assert_user(current_user_id); delete_many_sync("blocks",filters={"blocker_id":current_user_id,"blocked_id":target_user_id})
    def mute_user(self,current_user_id:str,target_user_id:str,mute_type:str,duration:str)->Dict[str,Any]:
        if mute_type not in self.MUTE_TYPES: raise SocialGraphError(400,"Unsupported mute type")
        self._assert_contact_available(current_user_id,target_user_id); row=upsert_one_sync("mutes",{"muter_id":current_user_id,"muted_id":target_user_id},"muter_id,muted_id"); row.update({"mute_type":mute_type,"expires_at":resolve_expiry(duration),"duration":duration}); return row
    def unmute_user(self,current_user_id:str,target_user_id:str,mute_type:str)->None:
        if mute_type not in self.MUTE_TYPES: raise SocialGraphError(400,"Unsupported mute type")
        self._assert_user(current_user_id); delete_many_sync("mutes",filters={"muter_id":current_user_id,"muted_id":target_user_id})
    def report_user(self,current_user_id:str,target_user_id:str,reason:str,description:str)->Dict[str,Any]:
        current_user_id=self._assert_user(current_user_id); target_user_id=self._assert_user(target_user_id); reason=(reason or "").strip().lower()
        if reason not in self.REPORT_REASONS: raise SocialGraphError(400,"Unsupported report reason")
        if current_user_id==target_user_id: raise SocialGraphError(400,"You cannot report yourself")
        return insert_one_sync("content_reports",{"reporter_id":current_user_id,"reported_user_id":target_user_id,"reason":reason,"details":(description or "").strip(),"status":"open"})
    def _conversation(self,current_user_id:str,conversation_id:str)->Dict[str,Any]:
        self._assert_user(current_user_id); self._validate_uuid(conversation_id,"conversation id"); member=select_one_sync("conversation_members",filters={"conversation_id":conversation_id,"user_id":current_user_id},columns="conversation_id,user_id,joined_at,cleared_at")
        if not member: raise SocialGraphError(403,"Conversation not available for the current user")
        conversation=select_one_sync("conversations",filters={"id":conversation_id},columns="id,is_group,name,created_by,created_at,updated_at")
        if not conversation: raise SocialGraphError(404,"Conversation not found")
        return {"conversation":conversation,"membership":member}
    def _partner(self,current_user_id:str,conversation_id:str)->Optional[str]:
        self._conversation(current_user_id,conversation_id); return next((r["user_id"] for r in select_many_sync("conversation_members",filters={"conversation_id":conversation_id},columns="user_id") if r.get("user_id")!=current_user_id),None)
    def _settings(self,current_user_id:str,conversation_id:str)->Dict[str,Any]:
        row=select_one_sync("chat_settings",filters={"conversation_id":conversation_id,"user_id":current_user_id},columns="conversation_id,user_id,custom_wallpaper,custom_nickname,is_muted,mute_until,notification_sound_enabled,vibration_enabled,updated_at")
        return row or {"conversation_id":conversation_id,"user_id":current_user_id,"custom_wallpaper":None,"custom_nickname":"","is_muted":False,"mute_until":None,"notification_sound_enabled":True,"vibration_enabled":True,"updated_at":iso_now()}
    def _messages(self,current_user_id:str,conversation_id:str)->List[Dict[str,Any]]:
        membership=self._conversation(current_user_id,conversation_id)["membership"]; partner=self._partner(current_user_id,conversation_id)
        if partner and self.is_blocked(current_user_id,partner): return []
        rows=select_many_sync("messages",filters={"conversation_id":conversation_id},columns="id,conversation_id,sender_id,text_content,encrypted_payload,encryption_nonce,sender_ephemeral_public_key,recipient_key_id,encryption_algorithm,is_zero_knowledge,delivery_state,created_at,deleted_at")
        cutoff=membership.get("cleared_at")
        if cutoff:
            dt=datetime.fromisoformat(str(cutoff).replace("Z","+00:00")); rows=[r for r in rows if datetime.fromisoformat(str(r.get("created_at")).replace("Z","+00:00"))>dt]
        for row in rows:
            sender=self._profile(row["sender_id"]); row["sender_name"]=sender["display_name"]; row["text"]="" if row.get("is_zero_knowledge") else (row.get("text_content") or "")
        return rows
    def list_conversations(self,current_user_id:str)->List[Dict[str,Any]]:
        current_user_id=self._assert_user(current_user_id); items=[]
        for m in select_many_sync("conversation_members",filters={"user_id":current_user_id},columns="conversation_id,user_id,joined_at,cleared_at"):
            cid=m["conversation_id"]; c=select_one_sync("conversations",filters={"id":cid},columns="id,is_group,name,created_by,created_at,updated_at")
            if not c: continue
            partner_id=self._partner(current_user_id,cid); partner=self._profile(partner_id) if partner_id else None; settings=self._settings(current_user_id,cid); title=(settings.get("custom_nickname") or "").strip() or (partner or {}).get("display_name") or c.get("name") or "Conversation"
            items.append({"id":cid,"title":title,"participants":[self._profile(r["user_id"])["display_name"] for r in select_many_sync("conversation_members",filters={"conversation_id":cid},columns="user_id")],"partner_user_id":partner_id,"partner":partner,"messages":self._messages(current_user_id,cid),"is_unavailable":bool(partner_id and self.is_blocked(current_user_id,partner_id)),"chat_settings":settings})
        return items
    def get_conversation_messages(self,current_user_id:str,conversation_id:str)->List[Dict[str,Any]]: return self._messages(current_user_id,conversation_id)
    def send_message(self,current_user_id:str,conversation_id:str,sender_name:str,text:Optional[str],encrypted_payload:Optional[str]=None,encryption_nonce:Optional[str]=None,sender_ephemeral_public_key:Optional[str]=None,recipient_key_id:Optional[str]=None,encryption_algorithm:Optional[str]=None)->Dict[str,Any]:
        current_user_id=self._assert_user(current_user_id); partner=self._partner(current_user_id,conversation_id)
        if not partner: raise SocialGraphError(403,"Conversation recipient not found")
        self._assert_contact_available(current_user_id,partner); zero=bool(encrypted_payload and encryption_nonce)
        if not zero and not (text or "").strip(): raise SocialGraphError(400,"Message text is required")
        profile=self._profile(current_user_id); row=insert_one_sync("messages",{"conversation_id":conversation_id,"sender_id":current_user_id,"text_content":"" if zero else (text or "").strip(),"encrypted_payload":encrypted_payload,"encryption_nonce":encryption_nonce,"sender_ephemeral_public_key":sender_ephemeral_public_key,"recipient_key_id":recipient_key_id,"encryption_algorithm":encryption_algorithm,"is_zero_knowledge":zero,"delivery_state":"sent"}); row["sender_name"]=profile["display_name"]; row["text"]="" if zero else row.get("text_content") or ""; return row
    def append_bot_reply(self,conversation_id:str,sender_id:str,sender_name:str,text:str)->Dict[str,Any]:
        self._validate_uuid(conversation_id,"conversation id"); self._validate_uuid(sender_id,"sender id"); row=insert_one_sync("messages",{"conversation_id":conversation_id,"sender_id":sender_id,"text_content":(text or "").strip(),"is_zero_knowledge":False,"delivery_state":"sent"}); row["sender_name"]=sender_name; row["text"]=row.get("text_content") or ""; return row
    def get_chat_details(self,current_user_id:str,conversation_id:str)->Dict[str,Any]:
        partner=self._partner(current_user_id,conversation_id)
        if not partner: raise SocialGraphError(404,"Conversation partner not found")
        return {"conversation_id":conversation_id,"profile":self.get_profile(current_user_id,partner),"shared_media":select_many_sync("chat_media",filters={"conversation_id":conversation_id},columns="id,conversation_id,uploaded_by,storage_path,media_type,label,created_at"),"settings":self._settings(current_user_id,conversation_id),"relationship":self._relationship_state(current_user_id,partner)}
    def update_chat_settings(self,current_user_id:str,conversation_id:str,custom_wallpaper:Optional[str],custom_nickname:Optional[str],is_muted:Optional[bool],mute_duration:Optional[str],notification_sound_enabled:Optional[bool],vibration_enabled:Optional[bool])->Dict[str,Any]:
        self._conversation(current_user_id,conversation_id); cur=self._settings(current_user_id,conversation_id); payload={"conversation_id":conversation_id,"user_id":current_user_id,"custom_wallpaper":custom_wallpaper if custom_wallpaper is not None else cur["custom_wallpaper"],"custom_nickname":custom_nickname.strip() if custom_nickname is not None else cur["custom_nickname"],"is_muted":is_muted if is_muted is not None else cur["is_muted"],"mute_until":resolve_expiry(mute_duration or "always") if is_muted else cur["mute_until"],"notification_sound_enabled":notification_sound_enabled if notification_sound_enabled is not None else cur["notification_sound_enabled"],"vibration_enabled":vibration_enabled if vibration_enabled is not None else cur["vibration_enabled"]}; return upsert_one_sync("chat_settings",payload,"conversation_id,user_id")
    def reset_wallpaper(self,current_user_id:str,conversation_id:str)->Dict[str,Any]: self._conversation(current_user_id,conversation_id); return upsert_one_sync("chat_settings",{**self._settings(current_user_id,conversation_id),"custom_wallpaper":None,"updated_at":iso_now()},"conversation_id,user_id")
    def clear_chat_history(self,current_user_id:str,conversation_id:str)->Dict[str,Any]: self._conversation(current_user_id,conversation_id); now=iso_now(); update_one_sync("conversation_members",filters={"conversation_id":conversation_id,"user_id":current_user_id},payload={"cleared_at":now}); return {"conversation_id":conversation_id,"cleared_at":now}
    def search_chat(self,current_user_id:str,conversation_id:str,q:str)->List[Dict[str,Any]]:
        q=(q or "").strip().lower(); return [] if not q else [m for m in self._messages(current_user_id,conversation_id) if q in (m.get("text") or "").lower()]
    def export_chat(self,current_user_id:str,conversation_id:str)->Dict[str,Any]:
        messages=self._messages(current_user_id,conversation_id); return {"conversation_id":conversation_id,"filename":f"{conversation_id}-export.txt","content":"\n".join(f"[{m['created_at']}] {m['sender_name']}: {m.get('text') or ''}" for m in messages)}
    def _active_stories(self,current_user_id:str,target_user_id:str)->List[Dict[str,Any]]:
        self._assert_contact_available(current_user_id,target_user_id); now=iso_now(); return [r for r in select_many_sync("stories",filters={"user_id":target_user_id},columns="*") if not r.get("deleted_at") and str(r.get("expires_at",""))>now]

social_graph=SocialGraphService()
