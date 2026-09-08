from __future__ import annotations

import asyncio
import json
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.auth_utils import require_admin_user
from backend.services.admin_oob_auth import admin_oob_auth_service
from backend.services.push_notifications import PushNotificationError, push_notification_service


router = APIRouter(prefix="/api/admin-auth", tags=["admin-auth"])


class TabletBootstrapRequest(BaseModel):
    tablet_android_id: str = Field(min_length=8)
    wifi_ssid: str = Field(min_length=1)
    gateway_ip: str = Field(min_length=7)


class PhoneDecisionRequest(BaseModel):
    challenge_id: str
    decision: str
    decision_note: Optional[str] = None


class BiometricApprovalRequest(BaseModel):
    challenge_id: str
    phone_nonce: str
    approver_id: str = "affan-phone"


@router.post("/tablet/bootstrap")
async def admin_tablet_bootstrap(req: TabletBootstrapRequest):
    try:
        admin_oob_auth_service.validate_tablet_environment(
            req.tablet_android_id,
            req.wifi_ssid,
            req.gateway_ip,
        )
    except ValueError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error

    challenge = admin_oob_auth_service.create_challenge(
        tablet_android_id=req.tablet_android_id,
        wifi_ssid=req.wifi_ssid,
        gateway_ip=req.gateway_ip,
    )

    phone_user_id = os.getenv("ADMIN_AUTH_PHONE_USER_ID", "affan-phone")
    try:
        await push_notification_service.send_admin_authorization_prompt(
            recipient_user_id=phone_user_id,
            challenge_id=challenge.challenge_id,
            tablet_android_id=req.tablet_android_id,
            hotspot_ssid=req.wifi_ssid,
            gateway_ip=req.gateway_ip,
        )
    except PushNotificationError as error:
        raise HTTPException(status_code=502, detail=f"Unable to dispatch phone push: {error.detail}") from error

    return {
        "success": True,
        "challenge_id": challenge.challenge_id,
        "status": challenge.status,
        "requested_at": challenge.requested_at,
        "expires_at": challenge.expires_at,
        "message": "Please wait for authorizing on Affan's Phone...",
    }


@router.post("/phone/respond")
async def admin_phone_respond(req: PhoneDecisionRequest, authorization: Optional[str] = Header(default=None)):
    await require_admin_user(authorization)
    try:
        challenge = await admin_oob_auth_service.phone_decision(
            challenge_id=req.challenge_id,
            decision=req.decision,
            decision_note=req.decision_note,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    return {
        "success": True,
        "challenge_id": challenge.challenge_id,
        "status": challenge.status,
        "phone_nonce": challenge.phone_nonce,
    }


@router.post("/phone/biometric-approve")
async def admin_phone_biometric_approve(req: BiometricApprovalRequest, authorization: Optional[str] = Header(default=None)):
    await require_admin_user(authorization)
    try:
        challenge = await admin_oob_auth_service.approve_with_biometric(
            challenge_id=req.challenge_id,
            nonce=req.phone_nonce,
            approver_id=req.approver_id,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    return {
        "success": True,
        "challenge_id": challenge.challenge_id,
        "status": challenge.status,
        "approved_at": challenge.approved_at,
    }


@router.get("/tablet/status/{challenge_id}")
async def admin_tablet_status(challenge_id: str, authorization: Optional[str] = Header(default=None)):
    await require_admin_user(authorization)
    challenge = admin_oob_auth_service.get_challenge(challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found")

    return {
        "success": True,
        "challenge_id": challenge.challenge_id,
        "status": challenge.status,
        "message": "Authorized! Opening Admin Dashboard..." if challenge.status == "approved" else None,
        "expires_at": challenge.expires_at,
    }


@router.get("/tablet/stream/{challenge_id}")
async def admin_tablet_stream(challenge_id: str, authorization: Optional[str] = Header(default=None)):
    await require_admin_user(authorization)
    challenge = admin_oob_auth_service.get_challenge(challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found")

    async def event_generator():
        queue = await admin_oob_auth_service.register_listener(challenge_id)
        try:
            # Initial state frame so tablets have immediate context.
            yield f"data: {json.dumps({'type': 'state', 'status': challenge.status})}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") in {"authorized", "authorization_denied"}:
                        break
                except TimeoutError:
                    current = admin_oob_auth_service.get_challenge(challenge_id)
                    heartbeat = {"type": "heartbeat", "status": current.status if current else "missing"}
                    yield f"data: {json.dumps(heartbeat)}\n\n"
        finally:
            admin_oob_auth_service.unregister_listener(challenge_id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
