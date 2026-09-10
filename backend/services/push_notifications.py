from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any, Dict, List, Optional

import httpx

try:
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2 import service_account
except Exception:  # pragma: no cover
    GoogleAuthRequest = None
    service_account = None

from backend.services.supabase_db import insert_one, select_many, upsert_one


class PushNotificationError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class PushNotificationService:
    def __init__(self) -> None:
        self.project_id = os.getenv("FIREBASE_PROJECT_ID", "")
        self.service_account_file = os.getenv("FIREBASE_SERVICE_ACCOUNT_FILE", "")
        self.service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")

    def _load_google_credentials(self):
        if service_account is None or GoogleAuthRequest is None:
            return None
        if self.service_account_file and os.path.exists(self.service_account_file):
            return service_account.Credentials.from_service_account_file(
                self.service_account_file,
                scopes=["https://www.googleapis.com/auth/firebase.messaging"],
            )
        if self.service_account_json:
            return service_account.Credentials.from_service_account_info(
                json.loads(self.service_account_json),
                scopes=["https://www.googleapis.com/auth/firebase.messaging"],
            )
        return None

    async def _access_token(self) -> Optional[str]:
        credentials = self._load_google_credentials()
        if credentials is None:
            return None
        credentials.refresh(GoogleAuthRequest())
        return credentials.token

    async def register_device(
        self,
        user_id: str,
        fcm_token: str,
        platform: str,
        device_id: str,
        app_version: Optional[str],
    ) -> Dict[str, Any]:
        if platform not in {"android", "ios", "web"}:
            raise PushNotificationError(400, "Unsupported platform")
        if not fcm_token.strip() or not device_id.strip():
            raise PushNotificationError(400, "FCM token and device ID are required")
        payload = {
            "user_id": user_id,
            "fcm_token": fcm_token.strip(),
            "platform": platform,
            "device_id": device_id.strip(),
            "app_version": app_version,
        }
        return await upsert_one("push_devices", payload, "user_id,device_id")

    async def _user_tokens(self, user_id: str) -> List[Dict[str, Any]]:
        return await select_many(
            "push_devices",
            filters={"user_id": user_id},
            columns="id,user_id,fcm_token,platform,device_id,app_version,registered_at,last_seen_at",
        )

    async def _record_event(self, user_id: str, event_type: str, status: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await insert_one(
            "push_events",
            {"user_id": user_id, "event_type": event_type, "status": status, "payload": payload},
        )

    async def _send_message(self, user_id: str, message: Dict[str, Any], event_type: str) -> Dict[str, Any]:
        tokens = await self._user_tokens(user_id)
        if not tokens:
            return await self._record_event(user_id, event_type, "skipped", {"reason": "no_registered_devices", "message": message})

        access_token = await self._access_token()
        deliveries: List[Dict[str, Any]] = []
        if access_token is None:
            return await self._record_event(user_id, event_type, "failed", {"reason": "firebase_credentials_not_configured"})

        if not self.project_id:
            raise PushNotificationError(503, "FIREBASE_PROJECT_ID is not configured")

        url = f"https://fcm.googleapis.com/v1/projects/{self.project_id}/messages:send"
        async with httpx.AsyncClient(timeout=20.0) as client:
            for token in tokens:
                response = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    json={"message": {**message, "token": token["fcm_token"]}},
                )
                if response.status_code >= 400:
                    raise PushNotificationError(response.status_code, response.text or "Failed to send push notification")
                deliveries.append({"device_id": token["device_id"], "status": "sent", "response": response.json()})

        return await self._record_event(user_id, event_type, "sent", {"message": message, "deliveries": deliveries})

    async def send_direct_message(self, recipient_user_id: str, conversation_id: str, sender_name: str, preview_text: str) -> Dict[str, Any]:
        message = {
            "android": {"priority": "high", "notification": {"channel_id": "messages", "click_action": "OPEN_CHAT"}},
            "notification": {"title": sender_name, "body": preview_text[:120]},
            "data": {"notificationType": "direct_message", "targetScreen": "chat", "conversationId": conversation_id, "senderName": sender_name},
        }
        return await self._send_message(recipient_user_id, message, "direct_message")

    async def send_incoming_call(self, recipient_user_id: str, caller_name: str, call_type: str, conversation_id: str) -> Dict[str, Any]:
        message = {
            "android": {"priority": "high", "notification": {"channel_id": "calls", "click_action": "OPEN_CALL"}},
            "notification": {"title": f"Incoming {call_type} call", "body": f"{caller_name} is calling you"},
            "data": {"notificationType": "incoming_call", "targetScreen": "chat", "conversationId": conversation_id, "callerName": caller_name, "callType": call_type},
        }
        return await self._send_message(recipient_user_id, message, "incoming_call")

    async def send_social_event(self, recipient_user_id: str, actor_name: str, event_name: str, profile_id: str) -> Dict[str, Any]:
        body_map = {
            "follow_request": f"{actor_name} sent you a follow request",
            "like": f"{actor_name} liked your post",
            "mention": f"{actor_name} mentioned you",
        }
        message = {
            "android": {"priority": "normal", "notification": {"channel_id": "social", "click_action": "OPEN_PROFILE"}},
            "notification": {"title": "OMNIX activity", "body": body_map.get(event_name, f"{actor_name} interacted with you")},
            "data": {"notificationType": event_name, "targetScreen": "profile", "profileId": profile_id, "actorName": actor_name},
        }
        return await self._send_message(recipient_user_id, message, event_name)

    async def send_admin_authorization_prompt(self, recipient_user_id: str, challenge_id: str, tablet_android_id: str, hotspot_ssid: str, gateway_ip: str) -> Dict[str, Any]:
        message = {
            "android": {"priority": "high", "notification": {"channel_id": "security", "click_action": "OPEN_ADMIN_AUTH"}},
            "notification": {"title": "OMNIX security", "body": "Admin authorization requested"},
            "data": {"notificationType": "admin_auth_prompt", "challengeId": challenge_id, "tabletAndroidId": tablet_android_id, "hotspotSsid": hotspot_ssid, "gatewayIp": gateway_ip, "yesAction": "YES", "noAction": "NO"},
        }
        return await self._send_message(recipient_user_id, message, "admin_auth_prompt")


push_notification_service = PushNotificationService()
