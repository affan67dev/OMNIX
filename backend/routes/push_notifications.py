from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from backend.core.security import CurrentUser
from backend.services.push_notifications import PushNotificationError, push_notification_service

router = APIRouter(prefix="/api/v1/push", tags=["Push Notifications"])


def require_internal_service_key(value: Optional[str]) -> None:
    expected = os.getenv("INTERNAL_SERVICE_KEY", "")
    if not expected or value != expected:
        raise HTTPException(status_code=403, detail="Internal service authorization required")


def raise_push_error(error: PushNotificationError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.detail)


class RegisterDeviceRequest(BaseModel):
    fcm_token: str
    platform: str = "android"
    device_id: str
    app_version: Optional[str] = None


class DirectMessagePushRequest(BaseModel):
    recipient_user_id: str
    conversation_id: str
    sender_name: str
    preview_text: str


class IncomingCallPushRequest(BaseModel):
    recipient_user_id: str
    caller_name: str
    call_type: str
    conversation_id: str


class SocialEventPushRequest(BaseModel):
    recipient_user_id: str
    actor_name: str
    event_name: str
    profile_id: str


@router.post("/register-device")
async def register_device(req: RegisterDeviceRequest, current_user: CurrentUser):
    try:
        device = await push_notification_service.register_device(
            str(current_user["sub"]), req.fcm_token, req.platform, req.device_id, req.app_version
        )
    except PushNotificationError as error:
        raise_push_error(error)
    return {"success": True, "device": device}


@router.post("/send/direct-message")
async def send_direct_message_push(req: DirectMessagePushRequest, x_internal_service_key: Optional[str] = Header(default=None)):
    require_internal_service_key(x_internal_service_key)
    try:
        result = await push_notification_service.send_direct_message(req.recipient_user_id, req.conversation_id, req.sender_name, req.preview_text)
    except PushNotificationError as error:
        raise_push_error(error)
    return {"success": True, "result": result}


@router.post("/send/incoming-call")
async def send_incoming_call_push(req: IncomingCallPushRequest, x_internal_service_key: Optional[str] = Header(default=None)):
    require_internal_service_key(x_internal_service_key)
    try:
        result = await push_notification_service.send_incoming_call(req.recipient_user_id, req.caller_name, req.call_type, req.conversation_id)
    except PushNotificationError as error:
        raise_push_error(error)
    return {"success": True, "result": result}


@router.post("/send/social-event")
async def send_social_event_push(req: SocialEventPushRequest, x_internal_service_key: Optional[str] = Header(default=None)):
    require_internal_service_key(x_internal_service_key)
    try:
        result = await push_notification_service.send_social_event(req.recipient_user_id, req.actor_name, req.event_name, req.profile_id)
    except PushNotificationError as error:
        raise_push_error(error)
    return {"success": True, "result": result}
