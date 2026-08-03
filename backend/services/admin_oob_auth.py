from __future__ import annotations

import asyncio
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class AdminAuthChallenge:
    challenge_id: str
    tablet_android_id: str
    wifi_ssid: str
    gateway_ip: str
    requested_at: str
    expires_at: str
    status: str = "pending"
    decision: Optional[str] = None
    decision_note: Optional[str] = None
    phone_nonce: Optional[str] = None
    approved_token: Optional[str] = None
    approved_at: Optional[str] = None
    events: List[Dict[str, Any]] = field(default_factory=list)


class AdminOobAuthService:
    def __init__(self) -> None:
        self._challenges: Dict[str, AdminAuthChallenge] = {}
        self._listeners: Dict[str, List[asyncio.Queue]] = {}

    def _allowed_tablet_ids(self) -> set[str]:
        raw = os.getenv("ADMIN_ALLOWED_TABLET_ANDROID_IDS", "")
        return {item.strip() for item in raw.split(",") if item.strip()}

    def _allowed_ssids(self) -> set[str]:
        raw = os.getenv("ADMIN_ALLOWED_HOTSPOT_SSIDS", "")
        return {item.strip() for item in raw.split(",") if item.strip()}

    def _allowed_gateways(self) -> set[str]:
        raw = os.getenv("ADMIN_ALLOWED_GATEWAY_IPS", "")
        return {item.strip() for item in raw.split(",") if item.strip()}

    def validate_tablet_environment(self, tablet_android_id: str, wifi_ssid: str, gateway_ip: str) -> None:
        allowed_ids = self._allowed_tablet_ids()
        allowed_ssids = self._allowed_ssids()
        allowed_gateways = self._allowed_gateways()

        if allowed_ids and tablet_android_id not in allowed_ids:
            raise ValueError("Tablet is not registered")

        if allowed_ssids and wifi_ssid not in allowed_ssids:
            raise ValueError("Hotspot SSID is not allowed")

        if allowed_gateways and gateway_ip not in allowed_gateways:
            raise ValueError("Gateway IP is not allowed")

    def create_challenge(self, tablet_android_id: str, wifi_ssid: str, gateway_ip: str) -> AdminAuthChallenge:
        now = utc_now()
        challenge = AdminAuthChallenge(
            challenge_id=f"admin-auth-{uuid4().hex}",
            tablet_android_id=tablet_android_id,
            wifi_ssid=wifi_ssid,
            gateway_ip=gateway_ip,
            requested_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=5)).isoformat(),
        )
        challenge.events.append({"type": "challenge_created", "ts": challenge.requested_at})
        self._challenges[challenge.challenge_id] = challenge
        return challenge

    def get_challenge(self, challenge_id: str) -> Optional[AdminAuthChallenge]:
        challenge = self._challenges.get(challenge_id)
        if challenge is None:
            return None

        if self.is_expired(challenge) and challenge.status == "pending":
            challenge.status = "expired"
            challenge.events.append({"type": "expired", "ts": utc_now().isoformat()})

        return challenge

    def is_expired(self, challenge: AdminAuthChallenge) -> bool:
        expiry = datetime.fromisoformat(challenge.expires_at)
        return utc_now() >= expiry

    async def push_event(self, challenge_id: str, event: Dict[str, Any]) -> None:
        listeners = self._listeners.get(challenge_id, [])
        for queue in listeners:
            await queue.put(event)

    async def register_listener(self, challenge_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._listeners.setdefault(challenge_id, []).append(queue)
        return queue

    def unregister_listener(self, challenge_id: str, queue: asyncio.Queue) -> None:
        listeners = self._listeners.get(challenge_id, [])
        if queue in listeners:
            listeners.remove(queue)
        if not listeners and challenge_id in self._listeners:
            self._listeners.pop(challenge_id, None)

    async def phone_decision(self, challenge_id: str, decision: str, decision_note: Optional[str] = None) -> AdminAuthChallenge:
        challenge = self.get_challenge(challenge_id)
        if challenge is None:
            raise KeyError("Challenge not found")

        if challenge.status != "pending":
            raise ValueError("Challenge is no longer pending")

        normalized = decision.lower().strip()
        if normalized not in {"yes", "no"}:
            raise ValueError("Decision must be yes or no")

        challenge.decision = normalized
        challenge.decision_note = decision_note
        challenge.events.append({"type": "phone_decision", "value": normalized, "ts": utc_now().isoformat()})

        if normalized == "no":
            challenge.status = "denied"
            await self.push_event(challenge_id, {"type": "authorization_denied", "message": "Authorization denied from phone."})
            return challenge

        challenge.phone_nonce = secrets.token_urlsafe(32)
        await self.push_event(challenge_id, {"type": "phone_confirmed", "message": "Phone confirmation received. Awaiting biometric scan."})
        return challenge

    async def approve_with_biometric(self, challenge_id: str, nonce: str, approver_id: str) -> AdminAuthChallenge:
        challenge = self.get_challenge(challenge_id)
        if challenge is None:
            raise KeyError("Challenge not found")

        if challenge.status != "pending":
            raise ValueError("Challenge is no longer pending")

        if challenge.decision != "yes":
            raise ValueError("Phone decision is missing")

        if not challenge.phone_nonce or nonce != challenge.phone_nonce:
            raise ValueError("Invalid nonce")

        challenge.status = "approved"
        challenge.approved_token = secrets.token_urlsafe(48)
        challenge.approved_at = utc_now().isoformat()
        challenge.events.append(
            {
                "type": "biometric_approved",
                "approver_id": approver_id,
                "approved_at": challenge.approved_at,
            }
        )
        await self.push_event(
            challenge_id,
            {
                "type": "authorized",
                "message": "Authorized! Opening Admin Dashboard...",
            },
        )
        return challenge


admin_oob_auth_service = AdminOobAuthService()
