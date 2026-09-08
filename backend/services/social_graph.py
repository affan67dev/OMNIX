from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def resolve_expiry(duration: str) -> Optional[str]:
    presets = {
        "8_hours": timedelta(hours=8),
        "1_week": timedelta(weeks=1),
        "always": None,
    }
    if duration not in presets:
        raise ValueError("Unsupported duration")
    delta = presets[duration]
    if delta is None:
        return None
    return (utc_now() + delta).isoformat()


class SocialGraphError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class SocialGraphService:
    REPORT_REASONS = {"spam", "harassment", "inappropriate_content", "fraud"}
    MUTE_TYPES = {"user", "posts", "stories"}

    def __init__(self) -> None:
        self.users: Dict[str, Dict[str, Any]] = {
            "local-user": {
                "id": "local-user",
                "username": "operator_bite",
                "display_name": "Operator Bite",
                "bio": "System operator, moderation runner, and secure-network builder.",
                "avatar_color": "#38bdf8",
                "is_private": False,
                "is_blocked_from_search": False,
                "followers_count": 0,
                "following_count": 0,
                "posts_count": 3,
                "followers_visible": True,
                "following_visible": True,
                "posts": [
                    {"id": "post-local-1", "caption": "Control-room deployment shipped.", "visibility": "public"},
                    {"id": "post-local-2", "caption": "Latency held under target during stream tests.", "visibility": "followers"},
                ],
                "stories": ["Ops recap", "Release window"],
            },
            "user-nova": {
                "id": "user-nova",
                "username": "nova_ai",
                "display_name": "Nova",
                "bio": "Realtime comms specialist.",
                "avatar_color": "#f97316",
                "is_private": False,
                "is_blocked_from_search": False,
                "followers_count": 0,
                "following_count": 0,
                "posts_count": 4,
                "followers_visible": True,
                "following_visible": True,
                "posts": [
                    {"id": "post-nova-1", "caption": "Signal path green across all clusters.", "visibility": "public"},
                ],
                "stories": ["On-call", "Launch prep"],
            },
            "user-ari": {
                "id": "user-ari",
                "username": "ari_core",
                "display_name": "Ari",
                "bio": "Core infra and incident response.",
                "avatar_color": "#22c55e",
                "is_private": True,
                "is_blocked_from_search": False,
                "followers_count": 0,
                "following_count": 0,
                "posts_count": 2,
                "followers_visible": False,
                "following_visible": False,
                "posts": [
                    {"id": "post-ari-1", "caption": "Private deployment retrospective.", "visibility": "followers"},
                ],
                "stories": ["Private status update"],
            },
            "user-shadow": {
                "id": "user-shadow",
                "username": "shadow_dev",
                "display_name": "Shadow Dev",
                "bio": "Handles tooling, automation, and dark-launch tests.",
                "avatar_color": "#a855f7",
                "is_private": True,
                "is_blocked_from_search": False,
                "followers_count": 0,
                "following_count": 0,
                "posts_count": 5,
                "followers_visible": False,
                "following_visible": False,
                "posts": [
                    {"id": "post-shadow-1", "caption": "Staged release notes ready.", "visibility": "followers"},
                ],
                "stories": ["Security check", "Dark launch"],
            },
        }

        self.follow_relationships: Set[Tuple[str, str]] = {
            ("local-user", "user-nova"),
            ("user-nova", "local-user"),
        }
        self.follow_requests: Dict[str, Dict[str, Any]] = {
            "req-shadow-local": {
                "id": "req-shadow-local",
                "requester_id": "user-shadow",
                "target_id": "local-user",
                "status": "pending",
                "created_at": iso_now(),
                "responded_at": None,
            }
        }
        self.blocked_users: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.muted_users: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        self.reports: Dict[str, Dict[str, Any]] = {}
        self.chat_settings: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.conversations: Dict[str, Dict[str, Any]] = {
            "shadow-node": {
                "id": "shadow-node",
                "default_title": "Shadow Node",
                "participant_user_ids": ["local-user", "user-shadow"],
                "messages": [
                    {
                        "id": 1,
                        "conversation_id": "shadow-node",
                        "sender_id": "user-shadow",
                        "sender_name": "Shadow Dev",
                        "text": "The secure channel is live. Send a message and it will sync through the API.",
                        "created_at": iso_now(),
                    }
                ],
                "shared_media": [
                    {"id": "media-shadow-1", "type": "photo", "url": "/static/shared/shadow-grid.jpg", "label": "Grid snapshot"},
                    {"id": "media-shadow-2", "type": "doc", "url": "/static/shared/release-notes.pdf", "label": "Release notes"},
                ],
                "cleared_at_by_user": {},
            },
            "omni-core": {
                "id": "omni-core",
                "default_title": "Omni Core",
                "participant_user_ids": ["local-user", "user-ari"],
                "messages": [
                    {
                        "id": 1,
                        "conversation_id": "omni-core",
                        "sender_id": "user-ari",
                        "sender_name": "Ari",
                        "text": "Channel synced. Deployment status is green.",
                        "created_at": iso_now(),
                    }
                ],
                "shared_media": [
                    {"id": "media-ari-1", "type": "video", "url": "/static/shared/core-brief.mp4", "label": "Core brief"},
                ],
                "cleared_at_by_user": {},
            },
            "nova-link": {
                "id": "nova-link",
                "default_title": "Nova Link",
                "participant_user_ids": ["local-user", "user-nova"],
                "messages": [
                    {
                        "id": 1,
                        "conversation_id": "nova-link",
                        "sender_id": "user-nova",
                        "sender_name": "Nova",
                        "text": "Live stream and notification bridge are healthy.",
                        "created_at": iso_now(),
                    }
                ],
                "shared_media": [
                    {"id": "media-nova-1", "type": "photo", "url": "/static/shared/bridge.png", "label": "Bridge diagram"},
                ],
                "cleared_at_by_user": {},
            },
        }
        self.message_counters: Dict[str, int] = {
            conversation_id: len(conversation["messages"])
            for conversation_id, conversation in self.conversations.items()
        }
        self._refresh_follow_counts()

    def _refresh_follow_counts(self) -> None:
        for user in self.users.values():
            user["followers_count"] = 0
            user["following_count"] = 0
        for follower_id, following_id in self.follow_relationships:
            if follower_id in self.users:
                self.users[follower_id]["following_count"] += 1
            if following_id in self.users:
                self.users[following_id]["followers_count"] += 1

    def _get_user(self, user_id: str) -> Dict[str, Any]:
        user = self.users.get(user_id)
        if user is None:
            raise SocialGraphError(404, "User not found")
        return user

    def ensure_user(self, user_id: str, username: str, display_name: str) -> Dict[str, Any]:
        existing = self.users.get(user_id)
        if existing is not None:
            existing["username"] = username or existing.get("username") or user_id
            existing["display_name"] = display_name or existing.get("display_name") or username or user_id
            return deepcopy(existing)

        profile = {
            "id": user_id,
            "username": username or f"user_{user_id[:8]}",
            "display_name": display_name or username or "OMNIX User",
            "bio": "",
            "avatar_color": "#38bdf8",
            "is_private": False,
            "is_blocked_from_search": False,
            "followers_count": 0,
            "following_count": 0,
            "posts_count": 0,
            "followers_visible": True,
            "following_visible": True,
            "posts": [],
            "stories": [],
        }
        self.users[user_id] = profile
        self._refresh_follow_counts()
        return deepcopy(profile)

    def _get_conversation(self, conversation_id: str) -> Dict[str, Any]:
        conversation = self.conversations.get(conversation_id)
        if conversation is None:
            raise SocialGraphError(404, "Conversation not found")
        return conversation

    def is_blocked(self, left_user_id: str, right_user_id: str) -> bool:
        return (left_user_id, right_user_id) in self.blocked_users or (right_user_id, left_user_id) in self.blocked_users

    def _assert_contact_available(self, current_user_id: str, target_user_id: str) -> None:
        if current_user_id == target_user_id:
            return
        self._get_user(current_user_id)
        self._get_user(target_user_id)
        if self.is_blocked(current_user_id, target_user_id):
            raise SocialGraphError(403, "User Unavailable")

    def _is_following(self, follower_id: str, following_id: str) -> bool:
        return (follower_id, following_id) in self.follow_relationships

    def _relationship_state(self, current_user_id: str, target_user_id: str) -> Dict[str, Any]:
        blocked_by_current_user = (current_user_id, target_user_id) in self.blocked_users
        blocked_by_target_user = (target_user_id, current_user_id) in self.blocked_users
        outgoing_request = next(
            (
                request
                for request in self.follow_requests.values()
                if request["requester_id"] == current_user_id and request["target_id"] == target_user_id and request["status"] == "pending"
            ),
            None,
        )
        incoming_request = next(
            (
                request
                for request in self.follow_requests.values()
                if request["requester_id"] == target_user_id and request["target_id"] == current_user_id and request["status"] == "pending"
            ),
            None,
        )

        return {
            "is_self": current_user_id == target_user_id,
            "is_blocked": blocked_by_current_user or blocked_by_target_user,
            "blocked_by_current_user": blocked_by_current_user,
            "blocked_by_target_user": blocked_by_target_user,
            "is_following": self._is_following(current_user_id, target_user_id),
            "is_followed_by": self._is_following(target_user_id, current_user_id),
            "outgoing_follow_request": deepcopy(outgoing_request),
            "incoming_follow_request": deepcopy(incoming_request),
            "mutes": {
                mute_type: deepcopy(self.muted_users.get((current_user_id, target_user_id, mute_type)))
                for mute_type in self.MUTE_TYPES
            },
        }

    def _profile_access(self, current_user_id: str, target_user_id: str) -> Dict[str, bool]:
        target_user = self._get_user(target_user_id)
        relationship = self._relationship_state(current_user_id, target_user_id)
        can_view_private = relationship["is_self"] or relationship["is_following"]
        is_private = bool(target_user["is_private"])
        return {
            "can_view_full_profile": not is_private or can_view_private,
            "can_view_followers": (not is_private or can_view_private) and bool(target_user["followers_visible"]),
            "can_view_following": (not is_private or can_view_private) and bool(target_user["following_visible"]),
            "can_view_posts": not is_private or can_view_private,
            "can_view_stories": not is_private or can_view_private,
        }

    def get_me_overview(self, current_user_id: str) -> Dict[str, Any]:
        current_user = deepcopy(self._get_user(current_user_id))
        pending_incoming = [
            deepcopy(request)
            for request in self.follow_requests.values()
            if request["target_id"] == current_user_id and request["status"] == "pending"
        ]
        pending_outgoing = [
            deepcopy(request)
            for request in self.follow_requests.values()
            if request["requester_id"] == current_user_id and request["status"] == "pending"
        ]
        discover = []
        for user_id, user in self.users.items():
            if user_id == current_user_id or self.is_blocked(current_user_id, user_id):
                continue
            discover.append(
                {
                    **deepcopy(user),
                    "relationship": self._relationship_state(current_user_id, user_id),
                }
            )
        return {
            "me": current_user,
            "pending_incoming": pending_incoming,
            "pending_outgoing": pending_outgoing,
            "discover": discover,
            "followers": self.get_followers(current_user_id, current_user_id),
            "following": self.get_following(current_user_id, current_user_id),
        }

    def search_users(self, current_user_id: str, query: str) -> List[Dict[str, Any]]:
        normalized = query.strip().lower()
        results: List[Dict[str, Any]] = []
        for user_id, user in self.users.items():
            if self.is_blocked(current_user_id, user_id):
                continue
            if user["is_blocked_from_search"] and user_id != current_user_id:
                continue
            haystack = f"{user['username']} {user['display_name']} {user['bio']}".lower()
            if normalized and normalized not in haystack:
                continue
            results.append(
                {
                    "id": user["id"],
                    "username": user["username"],
                    "display_name": user["display_name"],
                    "avatar_color": user["avatar_color"],
                    "is_private": user["is_private"],
                    "relationship": self._relationship_state(current_user_id, user_id),
                }
            )
        return results

    def get_profile(self, current_user_id: str, target_user_id: str) -> Dict[str, Any]:
        self._assert_contact_available(current_user_id, target_user_id)
        target = deepcopy(self._get_user(target_user_id))
        access = self._profile_access(current_user_id, target_user_id)
        profile = {
            **target,
            "relationship": self._relationship_state(current_user_id, target_user_id),
            "access": access,
        }
        if not access["can_view_posts"]:
            profile["posts"] = []
        if not access["can_view_stories"]:
            profile["stories"] = []
        return profile

    def get_followers(self, current_user_id: str, target_user_id: str) -> List[Dict[str, Any]]:
        self._assert_contact_available(current_user_id, target_user_id)
        if not self._profile_access(current_user_id, target_user_id)["can_view_followers"]:
            raise SocialGraphError(403, "Followers list is private")
        follower_ids = [follower_id for follower_id, following_id in self.follow_relationships if following_id == target_user_id]
        return [deepcopy(self.users[follower_id]) for follower_id in follower_ids]

    def get_following(self, current_user_id: str, target_user_id: str) -> List[Dict[str, Any]]:
        self._assert_contact_available(current_user_id, target_user_id)
        if not self._profile_access(current_user_id, target_user_id)["can_view_following"]:
            raise SocialGraphError(403, "Following list is private")
        following_ids = [following_id for follower_id, following_id in self.follow_relationships if follower_id == target_user_id]
        return [deepcopy(self.users[following_id]) for following_id in following_ids]

    def get_posts(self, current_user_id: str, target_user_id: str) -> List[Dict[str, Any]]:
        self._assert_contact_available(current_user_id, target_user_id)
        access = self._profile_access(current_user_id, target_user_id)
        if not access["can_view_posts"]:
            raise SocialGraphError(403, "Posts are private")
        return deepcopy(self._get_user(target_user_id)["posts"])

    def create_follow(self, current_user_id: str, target_user_id: str) -> Dict[str, Any]:
        if current_user_id == target_user_id:
            raise SocialGraphError(400, "You cannot follow yourself")
        self._assert_contact_available(current_user_id, target_user_id)
        if self._is_following(current_user_id, target_user_id):
            return {
                "status": "following",
                "relationship": self._relationship_state(current_user_id, target_user_id),
                "target": deepcopy(self._get_user(target_user_id)),
            }

        pending = next(
            (
                request
                for request in self.follow_requests.values()
                if request["requester_id"] == current_user_id and request["target_id"] == target_user_id and request["status"] == "pending"
            ),
            None,
        )
        if pending:
            return {
                "status": "pending",
                "request": deepcopy(pending),
                "relationship": self._relationship_state(current_user_id, target_user_id),
                "target": deepcopy(self._get_user(target_user_id)),
            }

        target = self._get_user(target_user_id)
        if target["is_private"]:
            request_id = f"follow-{uuid4().hex}"
            request = {
                "id": request_id,
                "requester_id": current_user_id,
                "target_id": target_user_id,
                "status": "pending",
                "created_at": iso_now(),
                "responded_at": None,
            }
            self.follow_requests[request_id] = request
            return {
                "status": "pending",
                "request": deepcopy(request),
                "relationship": self._relationship_state(current_user_id, target_user_id),
                "target": deepcopy(target),
            }

        self.follow_relationships.add((current_user_id, target_user_id))
        self._refresh_follow_counts()
        return {
            "status": "following",
            "relationship": self._relationship_state(current_user_id, target_user_id),
            "target": deepcopy(self._get_user(target_user_id)),
        }

    def unfollow(self, current_user_id: str, target_user_id: str) -> Dict[str, Any]:
        self._assert_contact_available(current_user_id, target_user_id)
        self.follow_relationships.discard((current_user_id, target_user_id))
        self._refresh_follow_counts()
        return {
            "status": "not_following",
            "relationship": self._relationship_state(current_user_id, target_user_id),
            "target": deepcopy(self._get_user(target_user_id)),
        }

    def cancel_follow_request(self, current_user_id: str, request_id: str) -> Dict[str, Any]:
        request = self.follow_requests.get(request_id)
        if request is None:
            raise SocialGraphError(404, "Follow request not found")
        if request["requester_id"] != current_user_id:
            raise SocialGraphError(403, "You can only cancel your own request")
        request["status"] = "cancelled"
        request["responded_at"] = iso_now()
        return deepcopy(request)

    def respond_to_follow_request(self, current_user_id: str, request_id: str, action: str) -> Dict[str, Any]:
        request = self.follow_requests.get(request_id)
        if request is None:
            raise SocialGraphError(404, "Follow request not found")
        if request["target_id"] != current_user_id:
            raise SocialGraphError(403, "Only the target user can respond")
        if request["status"] != "pending":
            raise SocialGraphError(409, "Follow request already resolved")

        if action == "accept":
            request["status"] = "accepted"
            self.follow_relationships.add((request["requester_id"], request["target_id"]))
            self._refresh_follow_counts()
        elif action == "reject":
            request["status"] = "rejected"
        else:
            raise SocialGraphError(400, "Unsupported follow request action")
        request["responded_at"] = iso_now()
        return deepcopy(request)

    def update_privacy(self, current_user_id: str, is_private: bool, is_blocked_from_search: Optional[bool] = None) -> Dict[str, Any]:
        user = self._get_user(current_user_id)
        user["is_private"] = is_private
        if is_blocked_from_search is not None:
            user["is_blocked_from_search"] = is_blocked_from_search
        return deepcopy(user)

    def block_user(self, current_user_id: str, target_user_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        if current_user_id == target_user_id:
            raise SocialGraphError(400, "You cannot block yourself")
        self._get_user(current_user_id)
        self._get_user(target_user_id)
        self.blocked_users[(current_user_id, target_user_id)] = {
            "blocker_id": current_user_id,
            "blocked_id": target_user_id,
            "reason": reason,
            "created_at": iso_now(),
        }
        self.follow_relationships.discard((current_user_id, target_user_id))
        self.follow_relationships.discard((target_user_id, current_user_id))
        for request in self.follow_requests.values():
            if {request["requester_id"], request["target_id"]} == {current_user_id, target_user_id} and request["status"] == "pending":
                request["status"] = "cancelled"
                request["responded_at"] = iso_now()
        self._refresh_follow_counts()
        return deepcopy(self.blocked_users[(current_user_id, target_user_id)])

    def unblock_user(self, current_user_id: str, target_user_id: str) -> None:
        self.blocked_users.pop((current_user_id, target_user_id), None)

    def mute_user(self, current_user_id: str, target_user_id: str, mute_type: str, duration: str) -> Dict[str, Any]:
        if mute_type not in self.MUTE_TYPES:
            raise SocialGraphError(400, "Unsupported mute type")
        self._assert_contact_available(current_user_id, target_user_id)
        mute = {
            "muter_id": current_user_id,
            "muted_id": target_user_id,
            "mute_type": mute_type,
            "expires_at": resolve_expiry(duration),
            "duration": duration,
            "created_at": iso_now(),
        }
        self.muted_users[(current_user_id, target_user_id, mute_type)] = mute
        return deepcopy(mute)

    def unmute_user(self, current_user_id: str, target_user_id: str, mute_type: str) -> None:
        self.muted_users.pop((current_user_id, target_user_id, mute_type), None)

    def report_user(self, current_user_id: str, target_user_id: str, reason: str, description: str) -> Dict[str, Any]:
        normalized_reason = reason.strip().lower()
        if normalized_reason not in self.REPORT_REASONS:
            raise SocialGraphError(400, "Unsupported report reason")
        if current_user_id == target_user_id:
            raise SocialGraphError(400, "You cannot report yourself")
        self._get_user(current_user_id)
        self._get_user(target_user_id)
        report_id = f"report-{uuid4().hex}"
        report = {
            "id": report_id,
            "reporter_id": current_user_id,
            "reported_id": target_user_id,
            "reason": normalized_reason,
            "description": description.strip(),
            "status": "pending_review",
            "created_at": iso_now(),
        }
        self.reports[report_id] = report
        return deepcopy(report)

    def _get_partner_id(self, current_user_id: str, conversation_id: str) -> str:
        conversation = self._get_conversation(conversation_id)
        participants = conversation["participant_user_ids"]
        if current_user_id not in participants:
            raise SocialGraphError(403, "Conversation not available for the current user")
        partner_id = next((participant for participant in participants if participant != current_user_id), current_user_id)
        return partner_id

    def _get_chat_settings(self, current_user_id: str, conversation_id: str) -> Dict[str, Any]:
        settings = self.chat_settings.setdefault(
            (current_user_id, conversation_id),
            {
                "user_id": current_user_id,
                "chat_id": conversation_id,
                "custom_wallpaper": None,
                "custom_nickname": "",
                "is_muted": False,
                "mute_until": None,
                "notification_sound_enabled": True,
                "vibration_enabled": True,
                "updated_at": iso_now(),
            },
        )
        return settings

    def _visible_messages(self, current_user_id: str, conversation_id: str) -> List[Dict[str, Any]]:
        conversation = self._get_conversation(conversation_id)
        partner_id = self._get_partner_id(current_user_id, conversation_id)
        self._assert_contact_available(current_user_id, partner_id)
        cleared_at = conversation["cleared_at_by_user"].get(current_user_id)
        messages = conversation["messages"]
        if not cleared_at:
            return deepcopy(messages)
        cleared_time = datetime.fromisoformat(cleared_at)
        visible = [
            message
            for message in messages
            if datetime.fromisoformat(message["created_at"]) > cleared_time
        ]
        return deepcopy(visible)

    def list_conversations(self, current_user_id: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for conversation in self.conversations.values():
            if current_user_id not in conversation["participant_user_ids"]:
                continue
            partner_id = self._get_partner_id(current_user_id, conversation["id"])
            partner = deepcopy(self._get_user(partner_id))
            settings = deepcopy(self._get_chat_settings(current_user_id, conversation["id"]))
            unavailable = self.is_blocked(current_user_id, partner_id)
            title = settings["custom_nickname"].strip() or partner["display_name"] or conversation["default_title"]
            messages = [] if unavailable else self._visible_messages(current_user_id, conversation["id"])
            items.append(
                {
                    "id": conversation["id"],
                    "title": title,
                    "participants": [self.users[user_id]["display_name"] for user_id in conversation["participant_user_ids"]],
                    "partner_user_id": partner_id,
                    "partner": partner,
                    "messages": messages,
                    "is_unavailable": unavailable,
                    "chat_settings": settings,
                }
            )
        return items

    def get_conversation_messages(self, current_user_id: str, conversation_id: str) -> List[Dict[str, Any]]:
        return self._visible_messages(current_user_id, conversation_id)

    def send_message(
        self,
        current_user_id: str,
        conversation_id: str,
        sender_name: str,
        text: Optional[str],
        encrypted_payload: Optional[str] = None,
        encryption_nonce: Optional[str] = None,
        sender_ephemeral_public_key: Optional[str] = None,
        recipient_key_id: Optional[str] = None,
        encryption_algorithm: Optional[str] = None,
    ) -> Dict[str, Any]:
        conversation = self._get_conversation(conversation_id)
        partner_id = self._get_partner_id(current_user_id, conversation_id)
        self._assert_contact_available(current_user_id, partner_id)
        self.message_counters[conversation_id] = self.message_counters.get(conversation_id, 0) + 1
        zero_knowledge_payload = encrypted_payload is not None and encryption_nonce is not None
        message = {
            "id": self.message_counters[conversation_id],
            "conversation_id": conversation_id,
            "sender_id": current_user_id,
            "sender_name": sender_name,
            "text": (text or "").strip() if not zero_knowledge_payload else "",
            "created_at": iso_now(),
            "encrypted_payload": encrypted_payload,
            "encryption_nonce": encryption_nonce,
            "sender_ephemeral_public_key": sender_ephemeral_public_key,
            "recipient_key_id": recipient_key_id,
            "encryption_algorithm": encryption_algorithm,
            "is_zero_knowledge": zero_knowledge_payload,
            "delivery_state": "sent",
        }
        conversation["messages"].append(message)
        return deepcopy(message)

    def append_bot_reply(self, conversation_id: str, sender_id: str, sender_name: str, text: str) -> Dict[str, Any]:
        conversation = self._get_conversation(conversation_id)
        self.message_counters[conversation_id] = self.message_counters.get(conversation_id, 0) + 1
        reply = {
            "id": self.message_counters[conversation_id],
            "conversation_id": conversation_id,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "text": text,
            "created_at": iso_now(),
        }
        conversation["messages"].append(reply)
        return deepcopy(reply)

    def get_chat_details(self, current_user_id: str, conversation_id: str) -> Dict[str, Any]:
        conversation = self._get_conversation(conversation_id)
        partner_id = self._get_partner_id(current_user_id, conversation_id)
        partner = self.get_profile(current_user_id, partner_id)
        settings = deepcopy(self._get_chat_settings(current_user_id, conversation_id))
        return {
            "conversation_id": conversation_id,
            "profile": partner,
            "shared_media": deepcopy(conversation["shared_media"]),
            "settings": settings,
            "relationship": self._relationship_state(current_user_id, partner_id),
        }

    def update_chat_settings(
        self,
        current_user_id: str,
        conversation_id: str,
        custom_wallpaper: Optional[str],
        custom_nickname: Optional[str],
        is_muted: Optional[bool],
        mute_duration: Optional[str],
        notification_sound_enabled: Optional[bool],
        vibration_enabled: Optional[bool],
    ) -> Dict[str, Any]:
        partner_id = self._get_partner_id(current_user_id, conversation_id)
        self._assert_contact_available(current_user_id, partner_id)
        settings = self._get_chat_settings(current_user_id, conversation_id)
        if custom_wallpaper is not None:
            settings["custom_wallpaper"] = custom_wallpaper or None
        if custom_nickname is not None:
            settings["custom_nickname"] = custom_nickname.strip()
        if is_muted is not None:
            settings["is_muted"] = is_muted
            settings["mute_until"] = resolve_expiry(mute_duration or "always") if is_muted else None
        if notification_sound_enabled is not None:
            settings["notification_sound_enabled"] = notification_sound_enabled
        if vibration_enabled is not None:
            settings["vibration_enabled"] = vibration_enabled
        settings["updated_at"] = iso_now()
        return deepcopy(settings)

    def reset_wallpaper(self, current_user_id: str, conversation_id: str) -> Dict[str, Any]:
        settings = self._get_chat_settings(current_user_id, conversation_id)
        settings["custom_wallpaper"] = None
        settings["updated_at"] = iso_now()
        return deepcopy(settings)

    def clear_chat_history(self, current_user_id: str, conversation_id: str) -> Dict[str, Any]:
        conversation = self._get_conversation(conversation_id)
        self._get_partner_id(current_user_id, conversation_id)
        conversation["cleared_at_by_user"][current_user_id] = iso_now()
        return {"conversation_id": conversation_id, "cleared_at": conversation["cleared_at_by_user"][current_user_id]}

    def search_chat(self, current_user_id: str, conversation_id: str, query: str) -> List[Dict[str, Any]]:
        normalized = query.strip().lower()
        if not normalized:
            return []
        return [
            message
            for message in self._visible_messages(current_user_id, conversation_id)
            if normalized in message["text"].lower()
        ]

    def export_chat(self, current_user_id: str, conversation_id: str) -> Dict[str, Any]:
        messages = self._visible_messages(current_user_id, conversation_id)
        transcript = "\n".join(
            f"[{message['created_at']}] {message['sender_name']}: {message['text']}"
            for message in messages
        )
        return {
            "conversation_id": conversation_id,
            "filename": f"{conversation_id}-export.txt",
            "content": transcript,
        }


social_graph = SocialGraphService()