from __future__ import annotations

import json
import os
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

try:
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2 import service_account
except Exception:  # pragma: no cover - optional in local development
    GoogleAuthRequest = None
    service_account = None


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PushNotificationError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class PushNotificationService:
    def __init__(self) -> None:
        self.project_id = os.getenv("FIREBASE_PROJECT_ID", "omnix-bytechat")
        self.service_account_file = os.getenv("FIREBASE_SERVICE_ACCOUNT_FILE", "")
        self.service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
        self.device_tokens: Dict[str, List[Dict[str, Any]]] = {}
        self.events: List[Dict[str, Any]] = []

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
        await asyncio.to_thread(credentials.refresh, GoogleAuthRequest())
        return credentials.token

    def register_device(
        self,
        user_id: str,
        fcm_token: str,
        platform: str,
        device_id: str,
        app_version: Optional[str],
    ) -> Dict[str, Any]:
        registrations = self.device_tokens.setdefault(user_id, [])
        existing = next((item for item in registrations if item["fcm_token"] == fcm_token or item["device_id"] == device_id), None)
        payload = {
            "id": existing["id"] if existing else f"device-{uuid4().hex}",
            "user_id": user_id,
            "fcm_token": fcm_token,
            "platform": platform,
            "device_id": device_id,
            "app_version": app_version,
            "registered_at": iso_now(),
            "last_seen_at": iso_now(),
        }
        if existing:
            existing.update(payload)
        else:
            registrations.append(payload)
        return deepcopy(payload)

    def _user_tokens(self, user_id: str) -> List[Dict[str, Any]]:
        return [deepcopy(item) for item in self.device_tokens.get(user_id, [])]

    async def _send_message(self, user_id: str, message: Dict[str, Any], event_type: str) -> Dict[str, Any]:
        tokens = self._user_tokens(user_id)
        if not tokens:
            event = {
                "id": f"push-{uuid4().hex}",
                "user_id": user_id,
                "event_type": event_type,
                "status": "skipped",
                "reason": "no_registered_devices",
                "created_at": iso_now(),
                "message": deepcopy(message),
            }
            self.events.append(event)
            return event

        access_token = await self._access_token()
        delivered_to = []
        for token in tokens:
            if access_token is None:
                delivered_to.append({"device_id": token["device_id"], "status": "queued_local"})
                continue
            url = f"https://fcm.googleapis.com/v1/projects/{self.project_id}/messages:send"
            body = {"message": {**message, "token": token["fcm_token"]}}
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                if response.status_code >= 400:
                    raise PushNotificationError(response.status_code, response.text or "Failed to send push notification")
                delivered_to.append({"device_id": token["device_id"], "status": "sent", "response": response.json()})

        event = {
            "id": f"push-{uuid4().hex}",
            "user_id": user_id,
            "event_type": event_type,
            "status": "sent" if delivered_to else "skipped",
            "created_at": iso_now(),
            "message": deepcopy(message),
            "deliveries": delivered_to,
        }
        self.events.append(event)
        return event

    async def send_direct_message(self, recipient_user_id: str, conversation_id: str, sender_name: str, preview_text: str) -> Dict[str, Any]:
        message = {
            "android": {
                "priority": "high",
                "notification": {
                    "channel_id": "messages",
                    "click_action": "OPEN_CHAT",
                },
            },
            "notification": {
                "title": sender_name,
                "body": preview_text[:120],
            },
            "data": {
                "notificationType": "direct_message",
                "targetScreen": "chat",
                "conversationId": conversation_id,
                "senderName": sender_name,
            },
        }
        return await self._send_message(recipient_user_id, message, "direct_message")

    async def send_incoming_call(self, recipient_user_id: str, caller_name: str, call_type: str, conversation_id: str) -> Dict[str, Any]:
        message = {
            "android": {
                "priority": "high",
                "notification": {
                    "channel_id": "calls",
                    "click_action": "OPEN_CALL",
                },
            },
            "notification": {
                "title": f"Incoming {call_type} call",
                "body": f"{caller_name} is calling you",
            },
            "data": {
                "notificationType": "incoming_call",
                "targetScreen": "chat",
                "conversationId": conversation_id,
                "callerName": caller_name,
                "callType": call_type,
            },
        }
        return await self._send_message(recipient_user_id, message, "incoming_call")

    async def send_social_event(self, recipient_user_id: str, actor_name: str, event_name: str, profile_id: str) -> Dict[str, Any]:
        body_map = {
            "follow_request": f"{actor_name} sent you a follow request",
            "like": f"{actor_name} liked your post",
            "mention": f"{actor_name} mentioned you",
        }
        message = {
            "android": {
                "priority": "normal",
                "notification": {
                    "channel_id": "social",
                    "click_action": "OPEN_PROFILE",
                },
            },
            "notification": {
                "title": "ByteChat activity",
                "body": body_map.get(event_name, f"{actor_name} interacted with you"),
            },
            "data": {
                "notificationType": event_name,
                "targetScreen": "profile",
                "profileId": profile_id,
                "actorName": actor_name,
            },
        }
        return await self._send_message(recipient_user_id, message, event_name)

    async def send_admin_authorization_prompt(
        self,
        recipient_user_id: str,
        challenge_id: str,
        tablet_android_id: str,
        hotspot_ssid: str,
        gateway_ip: str,
    ) -> Dict[str, Any]:
        message = {
            "android": {
                "priority": "high",
                "notification": {
                    "channel_id": "security",
                    "click_action": "OPEN_ADMIN_AUTH",
                },
            },
            "notification": {
                "title": "Hey Affan!",
                "body": "Are you trying to open Admin Dashboard?",
            },
            "data": {
                "notificationType": "admin_auth_prompt",
                "challengeId": challenge_id,
                "tabletAndroidId": tablet_android_id,
                "hotspotSsid": hotspot_ssid,
                "gatewayIp": gateway_ip,
                "yesAction": "YES",
                "noAction": "NO",
            },
        }
        return await self._send_message(recipient_user_id, message, "admin_auth_prompt")


push_notification_service = PushNotificationService()
