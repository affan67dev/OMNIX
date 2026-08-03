from __future__ import annotations

import secrets
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from backend.services.billing import billing_service
from backend.services.social_graph import social_graph


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


class SettingsError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class SettingsManagementService:
    PAUSE_DURATIONS = {
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "2h": timedelta(hours=2),
        "4h": timedelta(hours=4),
        "8h": timedelta(hours=8),
    }
    TAG_POLICIES = {"everyone", "people_you_follow", "no_one"}
    SENSITIVE_CONTENT_LEVELS = {"standard", "less", "more"}
    TWO_FA_METHODS = {"sms", "totp"}

    def __init__(self) -> None:
        self.accounts: Dict[str, Dict[str, Any]] = {
            "local-user": {
                "user_id": "local-user",
                "email": "operator@omnix.app",
                "phone_number": "+1-202-555-0112",
                "gender": "non_binary",
                "date_of_birth": "1997-09-14",
                "account_created_date": "2024-02-19T12:00:00+00:00",
                "first_username": "operator_zero",
                "current_username": "operator_bite",
                "account_status": "active",
                "is_premium": False,
                "subscription_expiry_date": None,
                "subscription_status": "free",
                "is_deactivated": False,
                "deactivated_at": None,
                "deletion_requested_at": None,
                "deletion_scheduled_for": None,
                "can_restore_until": None,
            }
        }

        self.security: Dict[str, Dict[str, Any]] = {
            "local-user": {
                "two_factor_enabled": True,
                "two_factor_method": "totp",
                "totp_secret_masked": "JBSW-Y3DP-XXXX",
                "sms_2fa_phone": "+1-202-555-0112",
                "login_alerts_enabled": True,
                "unrecognized_device_alerts": True,
                "password_changed_at": "2026-07-05T18:42:00+00:00",
                "backup_codes_remaining": 6,
            }
        }

        self.content_preferences: Dict[str, Dict[str, Any]] = {
            "local-user": {
                "sensitive_content_control": "standard",
                "hide_like_view_counts": False,
                "mention_policy": "people_you_follow",
                "tag_policy": "people_you_follow",
            }
        }

        self.story_settings: Dict[str, Dict[str, Any]] = {
            "local-user": {
                "auto_save_to_archive": True,
                "save_to_phone_gallery": False,
            }
        }

        self.storage_settings: Dict[str, Dict[str, Any]] = {
            "local-user": {
                "cache_size_mb": 286,
                "cellular_data_saver": True,
                "photo_auto_download": "wifi_only",
                "video_auto_download": "wifi_only",
            }
        }

        self.notification_settings: Dict[str, Dict[str, Any]] = {
            "local-user": {
                "pause_all_until": None,
                "push_likes": True,
                "push_comments": True,
                "push_new_followers": True,
                "push_direct_messages": True,
                "push_calls": True,
                "push_app_updates": True,
            }
        }

        self.sessions: Dict[str, List[Dict[str, Any]]] = {
            "local-user": [
                {
                    "id": "session-current",
                    "device_name": "Pixel 9 Pro",
                    "os": "Android 16",
                    "location": "New York, US",
                    "ip_address": "203.0.113.10",
                    "last_active_at": "2026-07-21T09:12:00+00:00",
                    "current": True,
                    "recognized": True,
                    "is_active": True,
                },
                {
                    "id": "session-laptop",
                    "device_name": "ThinkPad X1",
                    "os": "Ubuntu 24.04",
                    "location": "New York, US",
                    "ip_address": "198.51.100.44",
                    "last_active_at": "2026-07-20T22:41:00+00:00",
                    "current": False,
                    "recognized": True,
                    "is_active": True,
                },
                {
                    "id": "session-tablet",
                    "device_name": "iPad Air",
                    "os": "iPadOS 19",
                    "location": "Unknown",
                    "ip_address": "192.0.2.87",
                    "last_active_at": "2026-07-19T17:03:00+00:00",
                    "current": False,
                    "recognized": False,
                    "is_active": True,
                },
            ]
        }

        self.password_reset_challenges: Dict[str, Dict[str, Any]] = {}
        self.data_export_requests: Dict[str, List[Dict[str, Any]]] = {
            "local-user": []
        }
        self.archives: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
            "local-user": {
                "posts": [
                    {"id": "arch-post-1", "caption": "Launch retrospective archived.", "archived_at": "2026-06-11T11:21:00+00:00"},
                    {"id": "arch-post-2", "caption": "Retention experiment snapshot.", "archived_at": "2026-07-03T07:50:00+00:00"},
                ],
                "stories": [
                    {"id": "arch-story-1", "title": "Incident wrap-up", "archived_at": "2026-07-17T05:00:00+00:00"},
                    {"id": "arch-story-2", "title": "Nightly build status", "archived_at": "2026-07-20T05:00:00+00:00"},
                ],
            }
        }

    def ensure_user(self, user_id: str, email: str = "", phone_number: str = "", username: str = "") -> None:
        self.accounts.setdefault(
            user_id,
            {
                "user_id": user_id,
                "email": email,
                "phone_number": phone_number,
                "gender": "unspecified",
                "date_of_birth": "",
                "account_created_date": iso_now(),
                "first_username": username or user_id,
                "current_username": username or user_id,
                "account_status": "active",
                "is_premium": False,
                "subscription_expiry_date": None,
                "subscription_status": "free",
                "is_deactivated": False,
                "deactivated_at": None,
                "deletion_requested_at": None,
                "deletion_scheduled_for": None,
                "can_restore_until": None,
            },
        )
        self.security.setdefault(
            user_id,
            {
                "two_factor_enabled": False,
                "two_factor_method": None,
                "totp_secret_masked": None,
                "sms_2fa_phone": phone_number,
                "login_alerts_enabled": True,
                "unrecognized_device_alerts": True,
                "password_changed_at": iso_now(),
                "backup_codes_remaining": 0,
            },
        )
        self.content_preferences.setdefault(
            user_id,
            {
                "sensitive_content_control": "standard",
                "hide_like_view_counts": False,
                "mention_policy": "people_you_follow",
                "tag_policy": "people_you_follow",
            },
        )
        self.story_settings.setdefault(user_id, {"auto_save_to_archive": True, "save_to_phone_gallery": False})
        self.storage_settings.setdefault(
            user_id,
            {
                "cache_size_mb": 0,
                "cellular_data_saver": True,
                "photo_auto_download": "wifi_only",
                "video_auto_download": "wifi_only",
            },
        )
        self.notification_settings.setdefault(
            user_id,
            {
                "pause_all_until": None,
                "push_likes": True,
                "push_comments": True,
                "push_new_followers": True,
                "push_direct_messages": True,
                "push_calls": True,
                "push_app_updates": True,
            },
        )
        self.sessions.setdefault(user_id, [])
        self.data_export_requests.setdefault(user_id, [])
        self.archives.setdefault(user_id, {"posts": [], "stories": []})

    def _ensure_user(self, user_id: str) -> None:
        if user_id not in self.accounts:
            raise SettingsError(404, "Settings account not found")

    def _active_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        self._ensure_user(user_id)
        return [session for session in self.sessions.get(user_id, []) if session["is_active"]]

    def get_overview(self, user_id: str) -> Dict[str, Any]:
        self._ensure_user(user_id)
        premium = billing_service.get_subscription_summary(user_id)
        account = deepcopy(self.accounts[user_id])
        account["is_premium"] = premium["is_premium"]
        account["subscription_expiry_date"] = premium["subscription_expiry_date"]
        account["subscription_status"] = premium["subscription_status"]
        return {
            "account": account,
            "security": deepcopy(self.security[user_id]),
            "content_preferences": deepcopy(self.content_preferences[user_id]),
            "story_settings": deepcopy(self.story_settings[user_id]),
            "storage_settings": deepcopy(self.storage_settings[user_id]),
            "notification_settings": deepcopy(self.notification_settings[user_id]),
            "sessions": deepcopy(self._active_sessions(user_id)),
            "archives": deepcopy(self.archives[user_id]),
            "blocked_accounts": self.list_blocked_accounts(user_id),
            "muted_accounts": self.list_muted_accounts(user_id),
            "latest_export": deepcopy(self.data_export_requests[user_id][-1]) if self.data_export_requests[user_id] else None,
            "premium": premium,
        }

    def update_personal_information(
        self,
        user_id: str,
        phone_number: str,
        email: str,
        gender: str,
        date_of_birth: str,
    ) -> Dict[str, Any]:
        self._ensure_user(user_id)
        account = self.accounts[user_id]
        account.update(
            {
                "phone_number": phone_number.strip(),
                "email": email.strip().lower(),
                "gender": gender.strip().lower(),
                "date_of_birth": date_of_birth,
            }
        )
        return deepcopy(account)

    def request_data_export(self, user_id: str, include_messages: bool, include_posts: bool, include_profile: bool) -> Dict[str, Any]:
        self._ensure_user(user_id)
        export_request = {
            "id": f"export-{uuid4().hex}",
            "status": "queued",
            "requested_at": iso_now(),
            "download_url": None,
            "expires_at": None,
            "format": "zip",
            "scope": {
                "include_messages": include_messages,
                "include_posts": include_posts,
                "include_profile": include_profile,
            },
        }
        # Local/dev fallback: immediately mark as ready.
        export_request["status"] = "ready"
        export_request["download_url"] = f"/api/settings/exports/{export_request['id']}/download"
        export_request["expires_at"] = (utc_now() + timedelta(days=7)).isoformat()
        self.data_export_requests[user_id].append(export_request)
        return deepcopy(export_request)

    def build_export_payload(self, user_id: str, export_id: str) -> Dict[str, Any]:
        self._ensure_user(user_id)
        export_request = next((item for item in self.data_export_requests[user_id] if item["id"] == export_id), None)
        if export_request is None:
            raise SettingsError(404, "Export request not found")
        if export_request["status"] != "ready":
            raise SettingsError(409, "Export is not ready")
        user_messages = []
        for conversation in social_graph.list_conversations(user_id):
            for message in conversation["messages"]:
                user_messages.append(message)
        payload = {
            "account": deepcopy(self.accounts[user_id]),
            "profile": deepcopy(social_graph.users.get(user_id, {})),
            "posts": deepcopy(social_graph.users.get(user_id, {}).get("posts", [])),
            "messages": user_messages,
            "archives": deepcopy(self.archives[user_id]),
            "generated_at": iso_now(),
        }
        return payload

    def deactivate_account(self, user_id: str, reason: str) -> Dict[str, Any]:
        self._ensure_user(user_id)
        account = self.accounts[user_id]
        account["is_deactivated"] = True
        account["deactivated_at"] = iso_now()
        account["account_status"] = "deactivated"
        self.logout_all_other_sessions(user_id, keep_current_session=False)
        return {
            "account": deepcopy(account),
            "message": f"Account deactivated: {reason.strip() or 'user_request'}",
        }

    def schedule_account_deletion(self, user_id: str, reason: str) -> Dict[str, Any]:
        self._ensure_user(user_id)
        now = utc_now()
        account = self.accounts[user_id]
        account["deletion_requested_at"] = now.isoformat()
        account["deletion_scheduled_for"] = (now + timedelta(days=30)).isoformat()
        account["can_restore_until"] = account["deletion_scheduled_for"]
        account["account_status"] = "pending_deletion"
        self.logout_all_other_sessions(user_id, keep_current_session=False)
        return deepcopy(account)

    def restore_account(self, user_id: str) -> Dict[str, Any]:
        self._ensure_user(user_id)
        account = self.accounts[user_id]
        if not account["can_restore_until"]:
            raise SettingsError(409, "Account is not pending deletion")
        restore_until = datetime.fromisoformat(account["can_restore_until"])
        if restore_until < utc_now():
            raise SettingsError(410, "Restoration window expired")
        account["is_deactivated"] = False
        account["deactivated_at"] = None
        account["deletion_requested_at"] = None
        account["deletion_scheduled_for"] = None
        account["can_restore_until"] = None
        account["account_status"] = "active"
        return deepcopy(account)

    def change_password(self, user_id: str, current_password: str, new_password: str) -> Dict[str, Any]:
        self._ensure_user(user_id)
        if len(current_password.strip()) < 6 or len(new_password.strip()) < 8:
            raise SettingsError(400, "Password policy not met")
        security = self.security[user_id]
        security["password_changed_at"] = iso_now()
        return deepcopy(security)

    def request_password_reset(self, user_id: str, channel: str, destination: str) -> Dict[str, Any]:
        self._ensure_user(user_id)
        if channel not in {"email", "sms"}:
            raise SettingsError(400, "Unsupported reset channel")
        challenge_id = f"otp-{uuid4().hex}"
        challenge = {
            "id": challenge_id,
            "user_id": user_id,
            "channel": channel,
            "destination": destination,
            "otp_code": f"{secrets.randbelow(10**6):06d}",
            "expires_at": (utc_now() + timedelta(minutes=10)).isoformat(),
            "verified": False,
        }
        self.password_reset_challenges[challenge_id] = challenge
        return {
            "challenge_id": challenge_id,
            "channel": channel,
            "destination_hint": destination[-4:].rjust(len(destination), "*") if destination else "",
            "expires_at": challenge["expires_at"],
        }

    def verify_password_reset(self, challenge_id: str, otp_code: str, new_password: str) -> Dict[str, Any]:
        challenge = self.password_reset_challenges.get(challenge_id)
        if challenge is None:
            raise SettingsError(404, "Reset challenge not found")
        if datetime.fromisoformat(challenge["expires_at"]) < utc_now():
            raise SettingsError(410, "OTP expired")
        if otp_code.strip() != challenge["otp_code"]:
            raise SettingsError(400, "Invalid OTP code")
        user_id = challenge["user_id"]
        self.change_password(user_id, "temporary-reset", new_password)
        challenge["verified"] = True
        return {"success": True, "user_id": user_id}

    def setup_2fa(self, user_id: str, method: str) -> Dict[str, Any]:
        self._ensure_user(user_id)
        if method not in self.TWO_FA_METHODS:
            raise SettingsError(400, "Unsupported 2FA method")
        setup_id = f"2fa-{uuid4().hex}"
        security = self.security[user_id]
        security["pending_2fa_setup"] = {
            "setup_id": setup_id,
            "method": method,
            "verification_code": f"{secrets.randbelow(10**6):06d}",
            "created_at": iso_now(),
        }
        return {
            "setup_id": setup_id,
            "method": method,
            "qr_code_url": f"otpauth://totp/OMNIX:{user_id}?secret=JBSWY3DPEHPK3PXP" if method == "totp" else None,
            "phone_number": security.get("sms_2fa_phone") if method == "sms" else None,
        }

    def verify_2fa_setup(self, user_id: str, setup_id: str, code: str) -> Dict[str, Any]:
        self._ensure_user(user_id)
        security = self.security[user_id]
        pending = security.get("pending_2fa_setup")
        if not pending or pending.get("setup_id") != setup_id:
            raise SettingsError(404, "2FA setup not found")
        if pending["verification_code"] != code.strip():
            raise SettingsError(400, "Invalid verification code")
        security["two_factor_enabled"] = True
        security["two_factor_method"] = pending["method"]
        security.pop("pending_2fa_setup", None)
        return deepcopy(security)

    def disable_2fa(self, user_id: str) -> Dict[str, Any]:
        self._ensure_user(user_id)
        security = self.security[user_id]
        security["two_factor_enabled"] = False
        security["two_factor_method"] = None
        security.pop("pending_2fa_setup", None)
        return deepcopy(security)

    def list_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        return deepcopy(self._active_sessions(user_id))

    def logout_session(self, user_id: str, session_id: str) -> None:
        sessions = self._active_sessions(user_id)
        match = next((session for session in sessions if session["id"] == session_id), None)
        if match is None:
            raise SettingsError(404, "Session not found")
        match["is_active"] = False
        match["revoked_at"] = iso_now()

    def logout_all_other_sessions(self, user_id: str, keep_current_session: bool = True) -> Dict[str, Any]:
        revoked = 0
        for session in self.sessions.get(user_id, []):
            if not session["is_active"]:
                continue
            if keep_current_session and session.get("current"):
                continue
            session["is_active"] = False
            session["revoked_at"] = iso_now()
            revoked += 1
        return {"revoked_sessions": revoked}

    def update_alert_preferences(self, user_id: str, login_alerts_enabled: bool, unrecognized_device_alerts: bool) -> Dict[str, Any]:
        self._ensure_user(user_id)
        security = self.security[user_id]
        security["login_alerts_enabled"] = login_alerts_enabled
        security["unrecognized_device_alerts"] = unrecognized_device_alerts
        return deepcopy(security)

    def list_blocked_accounts(self, user_id: str) -> List[Dict[str, Any]]:
        blocked = []
        for (blocker_id, blocked_id), record in social_graph.blocked_users.items():
            if blocker_id != user_id:
                continue
            target = social_graph.users.get(blocked_id)
            if target is None:
                continue
            blocked.append({
                "user_id": blocked_id,
                "username": target["username"],
                "display_name": target["display_name"],
                "blocked_at": record["created_at"],
            })
        return blocked

    def list_muted_accounts(self, user_id: str) -> Dict[str, List[Dict[str, Any]]]:
        grouped = {"posts": [], "stories": [], "chats": []}
        for (muter_id, muted_id, mute_type), record in social_graph.muted_users.items():
            if muter_id != user_id:
                continue
            target = social_graph.users.get(muted_id)
            if target is None:
                continue
            payload = {
                "user_id": muted_id,
                "username": target["username"],
                "display_name": target["display_name"],
                "mute_type": mute_type,
                "expires_at": record["expires_at"],
            }
            if mute_type == "posts":
                grouped["posts"].append(payload)
            elif mute_type == "stories":
                grouped["stories"].append(payload)
            else:
                grouped["chats"].append(payload)
        return grouped

    def update_content_preferences(
        self,
        user_id: str,
        sensitive_content_control: str,
        hide_like_view_counts: bool,
        mention_policy: str,
        tag_policy: str,
    ) -> Dict[str, Any]:
        self._ensure_user(user_id)
        if sensitive_content_control not in self.SENSITIVE_CONTENT_LEVELS:
            raise SettingsError(400, "Unsupported sensitive content level")
        if mention_policy not in self.TAG_POLICIES or tag_policy not in self.TAG_POLICIES:
            raise SettingsError(400, "Unsupported mention or tag policy")
        settings = self.content_preferences[user_id]
        settings.update(
            {
                "sensitive_content_control": sensitive_content_control,
                "hide_like_view_counts": hide_like_view_counts,
                "mention_policy": mention_policy,
                "tag_policy": tag_policy,
            }
        )
        return deepcopy(settings)

    def get_archives(self, user_id: str) -> Dict[str, List[Dict[str, Any]]]:
        self._ensure_user(user_id)
        return deepcopy(self.archives[user_id])

    def update_story_settings(self, user_id: str, auto_save_to_archive: bool, save_to_phone_gallery: bool) -> Dict[str, Any]:
        self._ensure_user(user_id)
        settings = self.story_settings[user_id]
        settings.update(
            {
                "auto_save_to_archive": auto_save_to_archive,
                "save_to_phone_gallery": save_to_phone_gallery,
            }
        )
        return deepcopy(settings)

    def clear_cache(self, user_id: str) -> Dict[str, Any]:
        self._ensure_user(user_id)
        storage = self.storage_settings[user_id]
        cleared = storage["cache_size_mb"]
        storage["cache_size_mb"] = 0
        return {"cleared_mb": cleared, "cache_size_mb": 0}

    def update_storage_settings(
        self,
        user_id: str,
        cellular_data_saver: bool,
        photo_auto_download: str,
        video_auto_download: str,
    ) -> Dict[str, Any]:
        self._ensure_user(user_id)
        if photo_auto_download not in {"wifi_only", "mobile_data"}:
            raise SettingsError(400, "Unsupported photo auto-download setting")
        if video_auto_download not in {"wifi_only", "mobile_data"}:
            raise SettingsError(400, "Unsupported video auto-download setting")
        settings = self.storage_settings[user_id]
        settings.update(
            {
                "cellular_data_saver": cellular_data_saver,
                "photo_auto_download": photo_auto_download,
                "video_auto_download": video_auto_download,
            }
        )
        return deepcopy(settings)

    def update_notification_preferences(
        self,
        user_id: str,
        push_likes: bool,
        push_comments: bool,
        push_new_followers: bool,
        push_direct_messages: bool,
        push_calls: bool,
        push_app_updates: bool,
    ) -> Dict[str, Any]:
        self._ensure_user(user_id)
        settings = self.notification_settings[user_id]
        settings.update(
            {
                "push_likes": push_likes,
                "push_comments": push_comments,
                "push_new_followers": push_new_followers,
                "push_direct_messages": push_direct_messages,
                "push_calls": push_calls,
                "push_app_updates": push_app_updates,
            }
        )
        return deepcopy(settings)

    def pause_notifications(self, user_id: str, duration: str) -> Dict[str, Any]:
        self._ensure_user(user_id)
        if duration not in self.PAUSE_DURATIONS:
            raise SettingsError(400, "Unsupported notification pause duration")
        settings = self.notification_settings[user_id]
        settings["pause_all_until"] = (utc_now() + self.PAUSE_DURATIONS[duration]).isoformat()
        return deepcopy(settings)


settings_management = SettingsManagementService()