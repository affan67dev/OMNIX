from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from backend.services.supabase_db import (
    delete_many_sync,
    insert_one_sync,
    select_many_sync,
    select_one_sync,
    update_one_sync,
    upsert_one_sync,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def resolve_expiry(duration: str) -> Optional[str]:
    presets = {"8_hours": timedelta(hours=8), "1_week": timedelta(weeks=1), "always": None}
    if duration not in presets:
        raise ValueError("Unsupported duration")
    delta = presets[duration]
    return None if delta is None else (utc_now() + delta).isoformat()


class SocialGraphError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class SocialGraphService:
    """Database-backed social/chat service.

    This class intentionally has no process-level user state. Every read/write goes to
    Supabase PostgreSQL. The application authenticates the caller with its verified JWT;
    database mutations additionally enforce ownership predicates before they are issued.
    Direct Supabase client access remains protected by the table RLS policies.
    """

    REPORT_REASONS = {"spam", "harassment", "inappropriate_content", "fraud"}
    MUTE_TYPES = {"user", "posts", "stories"}

    @staticmethod
    def _validate_uuid(value: str, label: str = "user id") -> str:
        try:
            return str(UUID(str(value)))
        except (TypeError, ValueError):
            raise SocialGraphError(400, f"Invalid {label}")

    def _profile(self, user_id: str) -> Dict[str, Any]:
        user_id = self._validate_uuid(user_id)
        row = select_one_sync(
            "profiles",
            filters={"user_id": user_id},
            columns="id,user_id,username,full_name,bio,profile_pic_url,cover_pic_url,is_private,is_blocked_from_search,omni_score,followers_count,following_count,posts_count,streak,created_at,updated_at",
        )
        if not row:
            raise SocialGraphError(404, "User not found")
        return self._normalize_profile(row)

    @staticmethod
    def _normalize_profile(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": row.get("user_id") or row.get("id"),
            "user_id": row.get("user_id") or row.get("id"),
            "username": row.get("username") or "",
            "display_name": row.get("full_name") or row.get("username") or "",
            "bio": row.get("bio") or "",
            "avatar_color": None,
            "profile_pic_url": row.get("profile_pic_url"),
            "cover_pic_url": row.get("cover_pic_url"),
            "is_private": bool(row.get("is_private")),
            "is_blocked_from_search": bool(row.get("is_blocked_from_search")),
            "omni_score": row.get("omni_score", 0),
            "followers_count": int(row.get("followers_count") or 0),
            "following_count": int(row.get("following_count") or 0),
            "posts_count": int(row.get("posts_count") or 0),
            "streak": int(row.get("streak") or 0),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    def _assert_user(self, user_id: str) -> str:
        return self._profile(user_id)["user_id"]

    def _assert_contact_available(self, current_user_id: str, target_user_id: str) -> None:
        current_user_id = self._assert_user(current_user_id)
        target_user_id = self._assert_user(target_user_id)
        if current_user_id != target_user_id and self.is_blocked(current_user_id, target_user_id):
            raise SocialGraphError(403, "User Unavailable")

    def is_blocked(self, left_user_id: str, right_user_id: str) -> bool:
        left_user_id = self._validate_uuid(left_user_id)
        right_user_id = self._validate_uuid(right_user_id)
        return bool(
            select_one_sync("blocks", filters={"blocker_id": left_user_id, "blocked_id": right_user_id}, columns="blocker_id")
            or select_one_sync("blocks", filters={"blocker_id": right_user_id, "blocked_id": left_user_id}, columns="blocker_id")
        )

    def _is_following(self, follower_id: str, following_id: str) -> bool:
        row = select_one_sync("follows", filters={"follower_id": follower_id, "following_id": following_id}, columns="status")
        return bool(row and row.get("status") == "accepted")

    def _follow_request(self, requester_id: str, target_id: str, status: str = "pending") -> Optional[Dict[str, Any]]:
        return select_one_sync(
            "follows",
            filters={"follower_id": requester_id, "following_id": target_id, "status": status},
            columns="follower_id,following_id,status,created_at",
        )

    def _relationship_state(self, current_user_id: str, target_user_id: str) -> Dict[str, Any]:
        current_user_id = self._validate_uuid(current_user_id)
        target_user_id = self._validate_uuid(target_user_id)
        blocked_by_current_user = bool(select_one_sync("blocks", filters={"blocker_id": current_user_id, "blocked_id": target_user_id}, columns="blocker_id"))
        blocked_by_target_user = bool(select_one_sync("blocks", filters={"blocker_id": target_user_id, "blocked_id": current_user_id}, columns="blocker_id"))
        outgoing = self._follow_request(current_user_id, target_user_id)
        incoming = self._follow_request(target_user_id, current_user_id)
        mutes = {}
        for mute_type in self.MUTE_TYPES:
            row = select_one_sync("mutes", filters={"muter_id": current_user_id, "muted_id": target_user_id}, columns="muter_id,muted_id,created_at")
            mutes[mute_type] = None
            if row:
                # The current schema has one row per pair, so a single active mute is represented here.
                mutes[mute_type] = {**row, "mute_type": mute_type}
        return {
            "is_self": current_user_id == target_user_id,
            "is_blocked": blocked_by_current_user or blocked_by_target_user,
            "blocked_by_current_user": blocked_by_current_user,
            "blocked_by_target_user": blocked_by_target_user,
            "is_following": self._is_following(current_user_id, target_user_id),
            "is_followed_by": self._is_following(target_user_id, current_user_id),
            "outgoing_follow_request": outgoing,
            "incoming_follow_request": incoming,
            "mutes": mutes,
        }

    def _profile_access(self, current_user_id: str, target_user_id: str) -> Dict[str, bool]:
        target = self._profile(target_user_id)
        relationship = self._relationship_state(current_user_id, target_user_id)
        can_view_private = relationship["is_self"] or relationship["is_following"]
        is_private = bool(target["is_private"])
        return {
            "can_view_full_profile": not is_private or can_view_private,
            "can_view_followers": (not is_private or can_view_private),
            "can_view_following": (not is_private or can_view_private),
            "can_view_posts": not is_private or can_view_private,
            "can_view_stories": not is_private or can_view_private,
        }

    def get_me_overview(self, current_user_id: str) -> Dict[str, Any]:
        current_user_id = self._assert_user(current_user_id)
        incoming = select_many_sync("follows", filters={"following_id": current_user_id, "status": "pending"}, columns="follower_id,following_id,status,created_at")
        outgoing = select_many_sync("follows", filters={"follower_id": current_user_id, "status": "pending"}, columns="follower_id,following_id,status,created_at")
        discover = []
        for row in select_many_sync("profiles", columns="user_id,username,full_name,bio,profile_pic_url,cover_pic_url,is_private,is_blocked_from_search,omni_score,followers_count,following_count,posts_count,streak,created_at,updated_at"):
            user_id = row.get("user_id")
            if not user_id or user_id == current_user_id or self.is_blocked(current_user_id, user_id):
                continue
            if row.get("is_blocked_from_search"):
                continue
            profile = self._normalize_profile(row)
            profile["relationship"] = self._relationship_state(current_user_id, user_id)
            discover.append(profile)
        return {
            "me": self._profile(current_user_id),
            "pending_incoming": incoming,
            "pending_outgoing": outgoing,
            "discover": discover,
            "followers": self.get_followers(current_user_id, current_user_id),
            "following": self.get_following(current_user_id, current_user_id),
        }

    def search_users(self, current_user_id: str, query: str) -> List[Dict[str, Any]]:
        current_user_id = self._assert_user(current_user_id)
        normalized = (query or "").strip().lower()
        results = []
        for row in select_many_sync("profiles", columns="user_id,username,full_name,bio,profile_pic_url,is_private,is_blocked_from_search,followers_count,following_count,posts_count"):
            user_id = row.get("user_id")
            if not user_id or self.is_blocked(current_user_id, user_id):
                continue
            if row.get("is_blocked_from_search") and user_id != current_user_id:
                continue
            haystack = f"{row.get('username') or ''} {row.get('full_name') or ''} {row.get('bio') or ''}".lower()
            if normalized and normalized not in haystack:
                continue
            profile = self._normalize_profile(row)
            profile["relationship"] = self._relationship_state(current_user_id, user_id)
            results.append({k: profile[k] for k in ("id", "username", "display_name", "avatar_color", "is_private", "relationship")})
        return results

    def get_profile(self, current_user_id: str, target_user_id: str) -> Dict[str, Any]:
        self._assert_contact_available(current_user_id, target_user_id)
        target = self._profile(target_user_id)
        access = self._profile_access(current_user_id, target_user_id)
        target["relationship"] = self._relationship_state(current_user_id, target_user_id)
        target["access"] = access
        target["posts"] = self.get_posts(current_user_id, target_user_id) if access["can_view_posts"] else []
        target["stories"] = self._active_stories(current_user_id, target_user_id) if access["can_view_stories"] else []
        return target

    def get_followers(self, current_user_id: str, target_user_id: str) -> List[Dict[str, Any]]:
        self._assert_contact_available(current_user_id, target_user_id)
        if not self._profile_access(current_user_id, target_user_id)["can_view_followers"]:
            raise SocialGraphError(403, "Followers list is private")
        rows = select_many_sync("follows", filters={"following_id": target_user_id, "status": "accepted"}, columns="follower_id,created_at")
        return [self._profile(row["follower_id"]) for row in rows if row.get("follower_id")]

    def get_following(self, current_user_id: str, target_user_id: str) -> List[Dict[str, Any]]:
        self._assert_contact_available(current_user_id, target_user_id)
        if not self._profile_access(current_user_id, target_user_id)["can_view_following"]:
            raise SocialGraphError(403, "Following list is private")
        rows = select_many_sync("follows", filters={"follower_id": target_user_id, "status": "accepted"}, columns="following_id,created_at")
        return [self._profile(row["following_id"]) for row in rows if row.get("following_id")]

    def get_posts(self, current_user_id: str, target_user_id: str) -> List[Dict[str, Any]]:
        self._assert_contact_available(current_user_id, target_user_id)
        access = self._profile_access(current_user_id, target_user_id)
        if not access["can_view_posts"]:
            raise SocialGraphError(403, "Posts are private")
        rows = select_many_sync("posts", filters={"user_id": target_user_id}, columns="*")
        return rows

    def create_follow(self, current_user_id: str, target_user_id: str) -> Dict[str, Any]:
        current_user_id = self._assert_user(current_user_id)
        target_user_id = self._assert_user(target_user_id)
        if current_user_id == target_user_id:
            raise SocialGraphError(400, "You cannot follow yourself")
        self._assert_contact_available(current_user_id, target_user_id)
        if self._is_following(current_user_id, target_user_id):
            return {"status": "following", "relationship": self._relationship_state(current_user_id, target_user_id), "target": self._profile(target_user_id)}
        pending = self._follow_request(current_user_id, target_user_id)
        if pending:
            return {"status": "pending", "request": pending, "relationship": self._relationship_state(current_user_id, target_user_id), "target": self._profile(target_user_id)}
        target = self._profile(target_user_id)
        status = "pending" if target["is_private"] else "accepted"
        row = upsert_one_sync("follows", {"follower_id": current_user_id, "following_id": target_user_id, "status": status}, "follower_id,following_id")
        return {"status": "pending" if status == "pending" else "following", "request": row if status == "pending" else None, "relationship": self._relationship_state(current_user_id, target_user_id), "target": self._profile(target_user_id)}

    def unfollow(self, current_user_id: str, target_user_id: str) -> Dict[str, Any]:
        self._assert_contact_available(current_user_id, target_user_id)
        delete_many_sync("follows", filters={"follower_id": current_user_id, "following_id": target_user_id})
        return {"status": "not_following", "relationship": self._relationship_state(current_user_id, target_user_id), "target": self._profile(target_user_id)}

    def cancel_follow_request(self, current_user_id: str, request_id: str) -> Dict[str, Any]:
        # Follow requests are rows in follows. UUID request ids are not separately generated.
        try:
            request_uuid = self._validate_uuid(request_id, "request id")
        except SocialGraphError:
            # Backward compatibility for old clients: allow a composite identifier only when it resolves uniquely.
            parts = str(request_id).split(":")
            if len(parts) != 2:
                raise SocialGraphError(404, "Follow request not found")
            requester_id, target_id = parts
        else:
            row = select_one_sync("follows", filters={"follower_id": current_user_id, "status": "pending"}, columns="follower_id,following_id,status,created_at")
            if not row or row.get("id") != request_uuid:
                raise SocialGraphError(404, "Follow request not found")
            requester_id, target_id = row["follower_id"], row["following_id"]
        row = select_one_sync("follows", filters={"follower_id": requester_id, "following_id": target_id, "status": "pending"}, columns="follower_id,following_id,status,created_at")
        if not row or row["follower_id"] != current_user_id:
            raise SocialGraphError(403, "You can only cancel your own request")
        delete_many_sync("follows", filters={"follower_id": requester_id, "following_id": target_id})
        return {**row, "status": "cancelled", "responded_at": iso_now()}

    def respond_to_follow_request(self, current_user_id: str, request_id: str, action: str) -> Dict[str, Any]:
        action = (action or "").lower()
        if action not in {"accept", "reject"}:
            raise SocialGraphError(400, "Unsupported follow request action")
        rows = select_many_sync("follows", filters={"following_id": current_user_id, "status": "pending"}, columns="follower_id,following_id,status,created_at")
        row = None
        for candidate in rows:
            if candidate.get("follower_id") == request_id or candidate.get("id") == request_id:
                row = candidate
                break
        if row is None and ":" in str(request_id):
            requester, target = str(request_id).split(":", 1)
            if target == current_user_id:
                row = select_one_sync("follows", filters={"follower_id": requester, "following_id": target, "status": "pending"}, columns="follower_id,following_id,status,created_at")
        if row is None:
            raise SocialGraphError(404, "Follow request not found")
        if row["following_id"] != current_user_id:
            raise SocialGraphError(403, "Only the target user can respond")
        if action == "accept":
            updated = update_one_sync("follows", filters={"follower_id": row["follower_id"], "following_id": current_user_id}, payload={"status": "accepted"}) or {**row, "status": "accepted"}
        else:
            delete_many_sync("follows", filters={"follower_id": row["follower_id"], "following_id": current_user_id})
            updated = {**row, "status": "rejected"}
        return {**updated, "responded_at": iso_now()}

    def update_privacy(self, current_user_id: str, is_private: bool, is_blocked_from_search: Optional[bool] = None) -> Dict[str, Any]:
        self._assert_user(current_user_id)
        payload = {"is_private": bool(is_private)}
        if is_blocked_from_search is not None:
            payload["is_blocked_from_search"] = bool(is_blocked_from_search)
        updated = update_one_sync("profiles", filters={"user_id": current_user_id}, payload=payload)
        if not updated:
            raise SocialGraphError(404, "User not found")
        return self._normalize_profile(updated)

    def block_user(self, current_user_id: str, target_user_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        current_user_id = self._assert_user(current_user_id)
        target_user_id = self._assert_user(target_user_id)
        if current_user_id == target_user_id:
            raise SocialGraphError(400, "You cannot block yourself")
        row = upsert_one_sync("blocks", {"blocker_id": current_user_id, "blocked_id": target_user_id}, "blocker_id,blocked_id")
        delete_many_sync("follows", filters={"follower_id": current_user_id, "following_id": target_user_id})
        delete_many_sync("follows", filters={"follower_id": target_user_id, "following_id": current_user_id})
        return {**row, "reason": reason}

    def unblock_user(self, current_user_id: str, target_user_id: str) -> None:
        self._assert_user(current_user_id)
        delete_many_sync("blocks", filters={"blocker_id": current_user_id, "blocked_id": target_user_id})

    def mute_user(self, current_user_id: str, target_user_id: str, mute_type: str, duration: str) -> Dict[str, Any]:
        if mute_type not in self.MUTE_TYPES:
            raise SocialGraphError(400, "Unsupported mute type")
        self._assert_contact_available(current_user_id, target_user_id)
        row = upsert_one_sync("mutes", {"muter_id": current_user_id, "muted_id": target_user_id}, "muter_id,muted_id")
        return {**row, "mute_type": mute_type, "expires_at": resolve_expiry(duration), "duration": duration}

    def unmute_user(self, current_user_id: str, target_user_id: str, mute_type: str) -> None:
        if mute_type not in self.MUTE_TYPES:
            raise SocialGraphError(400, "Unsupported mute type")
        self._assert_user(current_user_id)
        delete_many_sync("mutes", filters={"muter_id": current_user_id, "muted_id": target_user_id})

    def report_user(self, current_user_id: str, target_user_id: str, reason: str, description: str) -> Dict[str, Any]:
        current_user_id = self._assert_user(current_user_id)
        target_user_id = self._assert_user(target_user_id)
        normalized_reason = (reason or "").strip().lower()
        if normalized_reason not in self.REPORT_REASONS:
            raise SocialGraphError(400, "Unsupported report reason")
        if current_user_id == target_user_id:
            raise SocialGraphError(400, "You cannot report yourself")
        return insert_one_sync("content_reports", {"reporter_id": current_user_id, "reported_user_id": target_user_id, "reason": normalized_reason, "details": (description or "").strip(), "status": "open"})

    def _conversation(self, current_user_id: str, conversation_id: str) -> Dict[str, Any]:
        current_user_id = self._assert_user(current_user_id)
        self._validate_uuid(conversation_id, "conversation id")
        membership = select_one_sync("conversation_members", filters={"conversation_id": conversation_id, "user_id": current_user_id}, columns="conversation_id,user_id,joined_at,cleared_at")
        if not membership:
            raise SocialGraphError(403, "Conversation not available for the current user")
        conversation = select_one_sync("conversations", filters={"id": conversation_id}, columns="id,is_group,name,created_by,created_at,updated_at")
        if not conversation:
            raise SocialGraphError(404, "Conversation not found")
        return {"conversation": conversation, "membership": membership}

    def _partner(self, current_user_id: str, conversation_id: str) -> Optional[str]:
        self._conversation(current_user_id, conversation_id)
        members = select_many_sync("conversation_members", filters={"conversation_id": conversation_id}, columns="user_id")
        return next((row["user_id"] for row in members if row.get("user_id") != current_user_id), None)

    def _settings(self, current_user_id: str, conversation_id: str) -> Dict[str, Any]:
        row = select_one_sync("chat_settings", filters={"conversation_id": conversation_id, "user_id": current_user_id}, columns="conversation_id,user_id,custom_wallpaper,custom_nickname,is_muted,mute_until,notification_sound_enabled,vibration_enabled,updated_at")
        if row:
            return row
        return {
            "conversation_id": conversation_id, "user_id": current_user_id,
            "custom_wallpaper": None, "custom_nickname": "", "is_muted": False,
            "mute_until": None, "notification_sound_enabled": True,
            "vibration_enabled": True, "updated_at": iso_now(),
        }

    def _messages(self, current_user_id: str, conversation_id: str) -> List[Dict[str, Any]]:
        membership = self._conversation(current_user_id, conversation_id)["membership"]
        partner = self._partner(current_user_id, conversation_id)
        if partner and self.is_blocked(current_user_id, partner):
            return []
        rows = select_many_sync("messages", filters={"conversation_id": conversation_id}, columns="id,conversation_id,sender_id,text_content,encrypted_payload,encryption_nonce,sender_ephemeral_public_key,recipient_key_id,encryption_algorithm,is_zero_knowledge,delivery_state,created_at,deleted_at")
        cleared_at = membership.get("cleared_at")
        if cleared_at:
            cutoff = datetime.fromisoformat(str(cleared_at).replace("Z", "+00:00"))
            rows = [r for r in rows if datetime.fromisoformat(str(r.get("created_at")).replace("Z", "+00:00")) > cutoff]
        for row in rows:
            sender = self._profile(row["sender_id"])
            row["sender_name"] = sender["display_name"]
            row["text"] = "" if row.get("is_zero_knowledge") else (row.get("text_content") or "")
        return rows

    def list_conversations(self, current_user_id: str) -> List[Dict[str, Any]]:
        current_user_id = self._assert_user(current_user_id)
        memberships = select_many_sync("conversation_members", filters={"user_id": current_user_id}, columns="conversation_id,user_id,joined_at,cleared_at")
        items = []
        for membership in memberships:
            cid = membership["conversation_id"]
            conversation = select_one_sync("conversations", filters={"id": cid}, columns="id,is_group,name,created_by,created_at,updated_at")
            if not conversation:
                continue
            partner_id = self._partner(current_user_id, cid)
            partner = self._profile(partner_id) if partner_id else None
            settings = self._settings(current_user_id, cid)
            title = (settings.get("custom_nickname") or "").strip() or (partner or {}).get("display_name") or conversation.get("name") or "Conversation"
            items.append({"id": cid, "title": title, "participants": [self._profile(r["user_id"])["display_name"] for r in select_many_sync("conversation_members", filters={"conversation_id": cid}, columns="user_id")], "partner_user_id": partner_id, "partner": partner, "messages": self._messages(current_user_id, cid), "is_unavailable": bool(partner_id and self.is_blocked(current_user_id, partner_id)), "chat_settings": settings})
        return items

    def get_conversation_messages(self, current_user_id: str, conversation_id: str) -> List[Dict[str, Any]]:
        return self._messages(current_user_id, conversation_id)

    def send_message(self, current_user_id: str, conversation_id: str, sender_name: str, text: Optional[str], encrypted_payload: Optional[str] = None, encryption_nonce: Optional[str] = None, sender_ephemeral_public_key: Optional[str] = None, recipient_key_id: Optional[str] = None, encryption_algorithm: Optional[str] = None) -> Dict[str, Any]:
        current_user_id = self._assert_user(current_user_id)
        partner_id = self._partner(current_user_id, conversation_id)
        if not partner_id:
            raise SocialGraphError(403, "Conversation recipient not found")
        self._assert_contact_available(current_user_id, partner_id)
        zero_knowledge = bool(encrypted_payload and encryption_nonce)
        if not zero_knowledge and not (text or "").strip():
            raise SocialGraphError(400, "Message text is required")
        profile = self._profile(current_user_id)
        row = insert_one_sync("messages", {"conversation_id": conversation_id, "sender_id": current_user_id, "text_content": "" if zero_knowledge else (text or "").strip(), "encrypted_payload": encrypted_payload, "encryption_nonce": encryption_nonce, "sender_ephemeral_public_key": sender_ephemeral_public_key, "recipient_key_id": recipient_key_id, "encryption_algorithm": encryption_algorithm, "is_zero_knowledge": zero_knowledge, "delivery_state": "sent"})
        row["sender_name"] = profile["display_name"]
        row["text"] = "" if zero_knowledge else (row.get("text_content") or "")
        return row

    def append_bot_reply(self, conversation_id: str, sender_id: str, sender_name: str, text: str) -> Dict[str, Any]:
        self._validate_uuid(conversation_id, "conversation id")
        self._validate_uuid(sender_id, "sender id")
        row = insert_one_sync("messages", {"conversation_id": conversation_id, "sender_id": sender_id, "text_content": (text or "").strip(), "is_zero_knowledge": False, "delivery_state": "sent"})
        row["sender_name"] = sender_name
        row["text"] = row.get("text_content") or ""
        return row

    def get_chat_details(self, current_user_id: str, conversation_id: str) -> Dict[str, Any]:
        partner_id = self._partner(current_user_id, conversation_id)
        if not partner_id:
            raise SocialGraphError(404, "Conversation partner not found")
        partner = self.get_profile(current_user_id, partner_id)
        media = select_many_sync("chat_media", filters={"conversation_id": conversation_id}, columns="id,conversation_id,uploaded_by,storage_path,media_type,label,created_at")
        return {"conversation_id": conversation_id, "profile": partner, "shared_media": media, "settings": self._settings(current_user_id, conversation_id), "relationship": self._relationship_state(current_user_id, partner_id)}

    def update_chat_settings(self, current_user_id: str, conversation_id: str, custom_wallpaper: Optional[str], custom_nickname: Optional[str], is_muted: Optional[bool], mute_duration: Optional[str], notification_sound_enabled: Optional[bool], vibration_enabled: Optional[bool]) -> Dict[str, Any]:
        partner_id = self._partner(current_user_id, conversation_id)
        if not partner_id:
            raise SocialGraphError(404, "Conversation partner not found")
        self._assert_contact_available(current_user_id, partner_id)
        current = self._settings(current_user_id, conversation_id)
        payload = {"conversation_id": conversation_id, "user_id": current_user_id, **current}
        if custom_wallpaper is not None: payload["custom_wallpaper"] = custom_wallpaper or None
        if custom_nickname is not None: payload["custom_nickname"] = custom_nickname.strip()
        if is_muted is not None:
            payload["is_muted"] = is_muted
            payload["mute_until"] = resolve_expiry(mute_duration or "always") if is_muted else None
        if notification_sound_enabled is not None: payload["notification_sound_enabled"] = notification_sound_enabled
        if vibration_enabled is not None: payload["vibration_enabled"] = vibration_enabled
        payload["updated_at"] = iso_now()
        allowed = {k: payload[k] for k in ("conversation_id","user_id","custom_wallpaper","custom_nickname","is_muted","mute_until","notification_sound_enabled","vibration_enabled")}
        return upsert_one_sync("chat_settings", allowed, "conversation_id,user_id")

    def reset_wallpaper(self, current_user_id: str, conversation_id: str) -> Dict[str, Any]:
        self._conversation(current_user_id, conversation_id)
        return upsert_one_sync("chat_settings", {**self._settings(current_user_id, conversation_id), "custom_wallpaper": None, "updated_at": iso_now()}, "conversation_id,user_id")

    def clear_chat_history(self, current_user_id: str, conversation_id: str) -> Dict[str, Any]:
        membership = self._conversation(current_user_id, conversation_id)["membership"]
        now = iso_now()
        updated = update_one_sync("conversation_members", filters={"conversation_id": conversation_id, "user_id": current_user_id}, payload={"cleared_at": now})
        return {"conversation_id": conversation_id, "cleared_at": (updated or {"cleared_at": now})["cleared_at"]}

    def search_chat(self, current_user_id: str, conversation_id: str, query: str) -> List[Dict[str, Any]]:
        normalized = (query or "").strip().lower()
        if not normalized:
            return []
        return [m for m in self._messages(current_user_id, conversation_id) if normalized in (m.get("text") or "").lower()]

    def export_chat(self, current_user_id: str, conversation_id: str) -> Dict[str, Any]:
        messages = self._messages(current_user_id, conversation_id)
        transcript = "\n".join(f"[{m['created_at']}] {m['sender_name']}: {m.get('text') or ''}" for m in messages)
        return {"conversation_id": conversation_id, "filename": f"{conversation_id}-export.txt", "content": transcript}

    def _active_stories(self, current_user_id: str, target_user_id: str) -> List[Dict[str, Any]]:
        self._assert_contact_available(current_user_id, target_user_id)
        now = iso_now()
        rows = select_many_sync("stories", filters={"user_id": target_user_id}, columns="*")
        return [r for r in rows if not r.get("deleted_at") and str(r.get("expires_at", "")) > now]


social_graph = SocialGraphService()
