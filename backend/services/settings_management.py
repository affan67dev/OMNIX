from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from uuid import uuid4

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


class SettingsError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class SettingsManagementService:
    """Persistent settings service with no process-level user state."""

    PAUSE_DURATIONS = {"15m": timedelta(minutes=15), "1h": timedelta(hours=1), "2h": timedelta(hours=2), "4h": timedelta(hours=4), "8h": timedelta(hours=8)}
    TAG_POLICIES = {"everyone", "people_you_follow", "no_one"}
    SENSITIVE_CONTENT_LEVELS = {"standard", "less", "more"}
    TWO_FA_METHODS = {"sms", "totp"}

    DEFAULTS = {
        "account": {"account_status": "active", "is_deactivated": False, "deactivated_at": None, "deletion_requested_at": None, "deletion_scheduled_for": None, "can_restore_until": None},
        "security": {"two_factor_enabled": False, "two_factor_method": None, "login_alerts_enabled": True, "unrecognized_device_alerts": True, "password_changed_at": None},
        "content_preferences": {"sensitive_content_control": "standard", "hide_like_view_counts": False, "mention_policy": "people_you_follow", "tag_policy": "people_you_follow"},
        "story_settings": {"auto_save_to_archive": True, "save_to_phone_gallery": False},
        "storage_settings": {"cache_size_mb": 0, "cellular_data_saver": True, "photo_auto_download": "wifi_only", "video_auto_download": "wifi_only"},
        "notification_settings": {"pause_all_until": None, "push_likes": True, "push_comments": True, "push_new_followers": True, "push_direct_messages": True, "push_calls": True, "push_app_updates": True},
    }

    def _ensure_user(self, user_id: str) -> str:
        row = select_one_sync("profiles", filters={"user_id": user_id}, columns="user_id,username,full_name,bio,mobile,is_private,is_blocked_from_search,created_at,updated_at")
        if not row:
            raise SettingsError(404, "Settings account not found")
        return str(row["user_id"])

    def _settings_row(self, user_id: str) -> Dict[str, Any]:
        self._ensure_user(user_id)
        row = select_one_sync("user_settings", filters={"user_id": user_id}, columns="user_id,account,security,content_preferences,story_settings,storage_settings,notification_settings,updated_at")
        if row:
            return row
        return upsert_one_sync("user_settings", {"user_id": user_id, **self.DEFAULTS, "updated_at": iso_now()}, "user_id")

    def _category(self, user_id: str, category: str) -> Dict[str, Any]:
        row = self._settings_row(user_id)
        return {**self.DEFAULTS[category], **(row.get(category) or {})}

    def _save_category(self, user_id: str, category: str, values: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_user(user_id)
        return upsert_one_sync("user_settings", {"user_id": user_id, category: values, "updated_at": iso_now()}, "user_id")

    def get_overview(self, user_id: str) -> Dict[str, Any]:
        row = self._settings_row(user_id)
        profile = select_one_sync("profiles", filters={"user_id": user_id}, columns="user_id,username,full_name,bio,mobile,is_private,is_blocked_from_search,created_at,updated_at,followers_count,following_count,posts_count,omni_score") or {}
        subscription = select_one_sync("subscriptions", filters={"user_id": user_id}, columns="status,is_premium,expiry_at,renews_at") or {"status": "free", "is_premium": False, "expiry_at": None, "renews_at": None}
        account = {**self.DEFAULTS["account"], **(row.get("account") or {})}
        account.update({"user_id": user_id, "username": profile.get("username"), "email": None, "phone_number": profile.get("mobile"), "current_username": profile.get("username"), "account_created_date": profile.get("created_at"), "is_premium": bool(subscription.get("is_premium")), "subscription_expiry_date": subscription.get("expiry_at"), "subscription_status": subscription.get("status", "free")})
        sessions = self.list_sessions(user_id)
        return {"account": account, "security": self._category(user_id, "security"), "content_preferences": self._category(user_id, "content_preferences"), "story_settings": self._category(user_id, "story_settings"), "storage_settings": self._category(user_id, "storage_settings"), "notification_settings": self._category(user_id, "notification_settings"), "sessions": sessions, "archives": self.get_archives(user_id), "blocked_accounts": self.list_blocked_accounts(user_id), "muted_accounts": self.list_muted_accounts(user_id), "latest_export": next(iter(select_many_sync("data_export_requests", filters={"user_id": user_id}, columns="id,status,scope,download_path,expires_at,created_at,completed_at")), None), "premium": {"is_premium": bool(subscription.get("is_premium")), "subscription_expiry_date": subscription.get("expiry_at"), "subscription_status": subscription.get("status", "free")}}

    def update_personal_information(self, user_id: str, phone_number: str, email: str, gender: str, date_of_birth: str) -> Dict[str, Any]:
        self._ensure_user(user_id)
        # Sensitive account metadata is kept in the user-owned settings row; auth email changes remain an Auth concern.
        account = self._category(user_id, "account")
        account.update({"phone_number": phone_number.strip(), "email": email.strip().lower(), "gender": gender.strip().lower(), "date_of_birth": date_of_birth})
        row = self._save_category(user_id, "account", account)
        return {**account, "user_id": user_id}

    def request_data_export(self, user_id: str, include_messages: bool, include_posts: bool, include_profile: bool) -> Dict[str, Any]:
        self._ensure_user(user_id)
        expires = utc_now() + timedelta(days=7)
        row = insert_one_sync("data_export_requests", {"user_id": user_id, "status": "ready", "scope": {"include_messages": include_messages, "include_posts": include_posts, "include_profile": include_profile}, "download_path": None, "expires_at": expires.isoformat(), "completed_at": iso_now()})
        row["download_url"] = f"/api/settings/exports/{row['id']}/download"
        return row

    def build_export_payload(self, user_id: str, export_id: str) -> Dict[str, Any]:
        self._ensure_user(user_id)
        request = select_one_sync("data_export_requests", filters={"id": export_id, "user_id": user_id}, columns="id,status,scope,expires_at")
        if not request:
            raise SettingsError(404, "Export request not found")
        if request.get("status") != "ready":
            raise SettingsError(409, "Export is not ready")
        if request.get("expires_at") and datetime.fromisoformat(str(request["expires_at"]).replace("Z", "+00:00")) <= utc_now():
            raise SettingsError(410, "Export expired")
        scope = request.get("scope") or {}
        payload: Dict[str, Any] = {"generated_at": iso_now(), "scope": scope}
        if scope.get("include_profile", True): payload["profile"] = select_one_sync("profiles", filters={"user_id": user_id}, columns="*")
        if scope.get("include_posts", True): payload["posts"] = select_many_sync("posts", filters={"user_id": user_id}, columns="*")
        if scope.get("include_messages", True):
            memberships = select_many_sync("conversation_members", filters={"user_id": user_id}, columns="conversation_id,cleared_at")
            payload["messages"] = []
            for membership in memberships:
                payload["messages"].extend(select_many_sync("messages", filters={"conversation_id": membership["conversation_id"]}, columns="id,conversation_id,sender_id,text_content,encrypted_payload,encryption_nonce,is_zero_knowledge,delivery_state,created_at"))
        payload["archives"] = self.get_archives(user_id)
        return payload

    def deactivate_account(self, user_id: str, reason: str) -> Dict[str, Any]:
        self._ensure_user(user_id)
        account = self._category(user_id, "account")
        account.update({"is_deactivated": True, "deactivated_at": iso_now(), "account_status": "deactivated"})
        self._save_category(user_id, "account", account)
        self.logout_all_other_sessions(user_id, keep_current_session=False)
        return {"account": {**account, "user_id": user_id}, "message": f"Account deactivated: {reason.strip() or 'user_request'}"}

    def schedule_account_deletion(self, user_id: str, reason: str) -> Dict[str, Any]:
        self._ensure_user(user_id)
        now = utc_now(); scheduled = (now + timedelta(days=30)).isoformat()
        account = self._category(user_id, "account")
        account.update({"deletion_requested_at": now.isoformat(), "deletion_scheduled_for": scheduled, "can_restore_until": scheduled, "account_status": "pending_deletion"})
        self._save_category(user_id, "account", account); self.logout_all_other_sessions(user_id, keep_current_session=False)
        return {**account, "user_id": user_id}

    def restore_account(self, user_id: str) -> Dict[str, Any]:
        self._ensure_user(user_id); account = self._category(user_id, "account")
        until = account.get("can_restore_until")
        if not until: raise SettingsError(409, "Account is not pending deletion")
        if datetime.fromisoformat(str(until).replace("Z", "+00:00")) < utc_now(): raise SettingsError(410, "Restoration window expired")
        account.update({"is_deactivated": False, "deactivated_at": None, "deletion_requested_at": None, "deletion_scheduled_for": None, "can_restore_until": None, "account_status": "active"})
        self._save_category(user_id, "account", account); return {**account, "user_id": user_id}

    def change_password(self, user_id: str, current_password: str, new_password: str) -> Dict[str, Any]:
        self._ensure_user(user_id)
        if len(current_password.strip()) < 6 or len(new_password.strip()) < 8: raise SettingsError(400, "Password policy not met")
        security = self._category(user_id, "security"); security["password_changed_at"] = iso_now(); self._save_category(user_id, "security", security); return security

    def request_password_reset(self, user_id: str, channel: str, destination: str) -> Dict[str, Any]:
        self._ensure_user(user_id)
        if channel not in {"email", "sms"}: raise SettingsError(400, "Unsupported reset channel")
        challenge_id = str(uuid4()); otp = f"{secrets.randbelow(1_000_000):06d}"; expires = utc_now() + timedelta(minutes=10)
        pepper = os.getenv("OTP_PEPPER", "settings-reset-pepper")
        otp_hash = hashlib.sha256(f"{pepper}:{challenge_id}:{otp}".encode()).hexdigest()
        insert_one_sync("settings_password_resets", {"id": challenge_id, "user_id": user_id, "channel": channel, "destination": destination, "otp_hash": otp_hash, "expires_at": expires.isoformat()})
        result = {"challenge_id": challenge_id, "channel": channel, "destination_hint": destination[-4:].rjust(len(destination), "*") if destination else "", "expires_at": expires.isoformat()}
        if os.getenv("ENVIRONMENT", "production").lower() != "production": result["development_otp"] = otp
        return result

    def verify_password_reset(self, challenge_id: str, otp_code: str, new_password: str) -> Dict[str, Any]:
        challenge = select_one_sync("settings_password_resets", filters={"id": challenge_id}, columns="id,user_id,otp_hash,expires_at,verified_at,attempts")
        if not challenge: raise SettingsError(404, "Reset challenge not found")
        if challenge.get("verified_at"): raise SettingsError(400, "Reset challenge already used")
        if datetime.fromisoformat(str(challenge["expires_at"]).replace("Z", "+00:00")) <= utc_now(): raise SettingsError(410, "OTP expired")
        pepper = os.getenv("OTP_PEPPER", "settings-reset-pepper")
        expected = hashlib.sha256(f"{pepper}:{challenge_id}:{otp_code.strip()}".encode()).hexdigest()
        if not secrets.compare_digest(expected, str(challenge["otp_hash"])):
            attempts = int(challenge.get("attempts") or 0) + 1; update_one_sync("settings_password_resets", filters={"id": challenge_id}, payload={"attempts": attempts}); raise SettingsError(400, "Invalid OTP code")
        if len(new_password.strip()) < 8: raise SettingsError(400, "Password policy not met")
        update_one_sync("settings_password_resets", filters={"id": challenge_id}, payload={"verified_at": iso_now()})
        security = self._category(str(challenge["user_id"]), "security"); security["password_changed_at"] = iso_now(); self._save_category(str(challenge["user_id"]), "security", security)
        return {"success": True, "user_id": challenge["user_id"]}

    def setup_2fa(self, user_id: str, method: str) -> Dict[str, Any]:
        self._ensure_user(user_id)
        if method not in self.TWO_FA_METHODS: raise SettingsError(400, "Unsupported 2FA method")
        setup_id = str(uuid4()); verification_code = f"{secrets.randbelow(1_000_000):06d}"; pepper = os.getenv("OTP_PEPPER", "settings-2fa-pepper")
        verification_hash = hashlib.sha256(f"{pepper}:{setup_id}:{verification_code}".encode()).hexdigest()
        insert_one_sync("settings_2fa_challenges", {"id": setup_id, "user_id": user_id, "method": method, "verification_hash": verification_hash})
        result = {"setup_id": setup_id, "method": method, "qr_code_url": None, "phone_number": None}
        if method == "totp": result["qr_code_url"] = f"otpauth://totp/OMNIX:{user_id}?secret=SETUP_REQUIRED"
        if method == "sms": result["phone_number"] = self._category(user_id, "account").get("phone_number")
        if os.getenv("ENVIRONMENT", "production").lower() != "production": result["development_code"] = verification_code
        return result

    def verify_2fa_setup(self, user_id: str, setup_id: str, code: str) -> Dict[str, Any]:
        challenge = select_one_sync("settings_2fa_challenges", filters={"id": setup_id, "user_id": user_id}, columns="id,user_id,method,verification_hash,verified_at,expires_at")
        if not challenge: raise SettingsError(404, "2FA setup not found")
        pepper = os.getenv("OTP_PEPPER", "settings-2fa-pepper"); expected = hashlib.sha256(f"{pepper}:{setup_id}:{code.strip()}".encode()).hexdigest()
        if not secrets.compare_digest(expected, str(challenge["verification_hash"])): raise SettingsError(400, "Invalid verification code")
        update_one_sync("settings_2fa_challenges", filters={"id": setup_id}, payload={"verified_at": iso_now()})
        security = self._category(user_id, "security"); security.update({"two_factor_enabled": True, "two_factor_method": challenge["method"]}); self._save_category(user_id, "security", security); return security

    def disable_2fa(self, user_id: str) -> Dict[str, Any]:
        security = self._category(user_id, "security"); security.update({"two_factor_enabled": False, "two_factor_method": None}); self._save_category(user_id, "security", security); delete_many_sync("settings_2fa_challenges", filters={"user_id": user_id}); return security

    def list_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        self._ensure_user(user_id)
        return select_many_sync("auth_sessions", filters={"user_id": user_id}, columns="id,user_id,created_at,expires_at,revoked_at,ip_address,user_agent")

    def logout_session(self, user_id: str, session_id: str) -> None:
        self._ensure_user(user_id)
        row = select_one_sync("auth_sessions", filters={"id": session_id, "user_id": user_id}, columns="id")
        if not row: raise SettingsError(404, "Session not found")
        update_one_sync("auth_sessions", filters={"id": session_id, "user_id": user_id}, payload={"revoked_at": iso_now()})

    def logout_all_other_sessions(self, user_id: str, keep_current_session: bool = True) -> Dict[str, Any]:
        self._ensure_user(user_id); sessions = self.list_sessions(user_id); revoked = 0
        for session in sessions:
            if keep_current_session and session["id"] == sessions[0]["id"]: continue
            if not session.get("revoked_at"):
                update_one_sync("auth_sessions", filters={"id": session["id"], "user_id": user_id}, payload={"revoked_at": iso_now()}); revoked += 1
        return {"revoked_sessions": revoked}

    def update_alert_preferences(self, user_id: str, login_alerts_enabled: bool, unrecognized_device_alerts: bool) -> Dict[str, Any]:
        security = self._category(user_id, "security"); security.update({"login_alerts_enabled": login_alerts_enabled, "unrecognized_device_alerts": unrecognized_device_alerts}); self._save_category(user_id, "security", security); return security

    def list_blocked_accounts(self, user_id: str) -> List[Dict[str, Any]]:
        rows = select_many_sync("blocks", filters={"blocker_id": user_id}, columns="blocked_id,created_at")
        result = []
        for row in rows:
            try: profile = select_one_sync("profiles", filters={"user_id": row["blocked_id"]}, columns="user_id,username,full_name")
            except Exception: profile = None
            if profile: result.append({"user_id": profile["user_id"], "username": profile.get("username"), "display_name": profile.get("full_name") or profile.get("username"), "blocked_at": row.get("created_at")})
        return result

    def list_muted_accounts(self, user_id: str) -> Dict[str, List[Dict[str, Any]]]:
        rows = select_many_sync("mutes", filters={"muter_id": user_id}, columns="muted_id,created_at")
        grouped = {"posts": [], "stories": [], "chats": []}
        for row in rows:
            profile = select_one_sync("profiles", filters={"user_id": row["muted_id"]}, columns="user_id,username,full_name")
            if profile: grouped["chats"].append({"user_id": profile["user_id"], "username": profile.get("username"), "display_name": profile.get("full_name") or profile.get("username"), "mute_type": "user", "expires_at": None})
        return grouped

    def update_content_preferences(self, user_id: str, sensitive_content_control: str, hide_like_view_counts: bool, mention_policy: str, tag_policy: str) -> Dict[str, Any]:
        if sensitive_content_control not in self.SENSITIVE_CONTENT_LEVELS or mention_policy not in self.TAG_POLICIES or tag_policy not in self.TAG_POLICIES: raise SettingsError(400, "Unsupported content preference")
        settings = self._category(user_id, "content_preferences"); settings.update({"sensitive_content_control": sensitive_content_control, "hide_like_view_counts": hide_like_view_counts, "mention_policy": mention_policy, "tag_policy": tag_policy}); self._save_category(user_id, "content_preferences", settings); return settings

    def get_archives(self, user_id: str) -> Dict[str, List[Dict[str, Any]]]:
        rows = select_many_sync("archived_content", filters={"user_id": user_id}, columns="id,content_type,title,payload,archived_at")
        return {"posts": [r for r in rows if r.get("content_type") == "post"], "stories": [r for r in rows if r.get("content_type") == "story"]}

    def update_story_settings(self, user_id: str, auto_save_to_archive: bool, save_to_phone_gallery: bool) -> Dict[str, Any]:
        settings = self._category(user_id, "story_settings"); settings.update({"auto_save_to_archive": auto_save_to_archive, "save_to_phone_gallery": save_to_phone_gallery}); self._save_category(user_id, "story_settings", settings); return settings

    def clear_cache(self, user_id: str) -> Dict[str, Any]:
        settings = self._category(user_id, "storage_settings"); cleared = int(settings.get("cache_size_mb") or 0); settings["cache_size_mb"] = 0; self._save_category(user_id, "storage_settings", settings); return {"cleared_mb": cleared, "cache_size_mb": 0}

    def update_storage_settings(self, user_id: str, cellular_data_saver: bool, photo_auto_download: str, video_auto_download: str) -> Dict[str, Any]:
        if photo_auto_download not in {"wifi_only", "mobile_data"} or video_auto_download not in {"wifi_only", "mobile_data"}: raise SettingsError(400, "Unsupported auto-download setting")
        settings = self._category(user_id, "storage_settings"); settings.update({"cellular_data_saver": cellular_data_saver, "photo_auto_download": photo_auto_download, "video_auto_download": video_auto_download}); self._save_category(user_id, "storage_settings", settings); return settings

    def update_notification_preferences(self, user_id: str, push_likes: bool, push_comments: bool, push_new_followers: bool, push_direct_messages: bool, push_calls: bool, push_app_updates: bool) -> Dict[str, Any]:
        settings = self._category(user_id, "notification_settings"); settings.update({"push_likes": push_likes, "push_comments": push_comments, "push_new_followers": push_new_followers, "push_direct_messages": push_direct_messages, "push_calls": push_calls, "push_app_updates": push_app_updates}); self._save_category(user_id, "notification_settings", settings); return settings

    def pause_notifications(self, user_id: str, duration: str) -> Dict[str, Any]:
        if duration not in self.PAUSE_DURATIONS: raise SettingsError(400, "Unsupported notification pause duration")
        settings = self._category(user_id, "notification_settings"); settings["pause_all_until"] = (utc_now() + self.PAUSE_DURATIONS[duration]).isoformat(); self._save_category(user_id, "notification_settings", settings); return settings


settings_management = SettingsManagementService()
