from __future__ import annotations

import json
import os
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

try:
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2 import service_account
except Exception:  # pragma: no cover - optional in local dev
    GoogleAuthRequest = None
    service_account = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


class BillingError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class BillingService:
    PRODUCT_ID = "bytechat_monthly_40"
    GOOGLE_SCOPE = "https://www.googleapis.com/auth/androidpublisher"

    def __init__(self) -> None:
        self.package_name = os.getenv("GOOGLE_PLAY_PACKAGE_NAME", "com.omnix.app")
        self.service_account_file = os.getenv("GOOGLE_PLAY_SERVICE_ACCOUNT_FILE", "")
        self.service_account_json = os.getenv("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON", "")
        self.subscriptions: Dict[str, Dict[str, Any]] = {
            "local-user": {
                "user_id": "local-user",
                "is_premium": False,
                "subscription_product_id": None,
                "subscription_purchase_token": None,
                "subscription_expiry_date": None,
                "subscription_status": "free",
                "renews_at": None,
                "cancel_at_period_end": False,
                "last_verified_at": None,
                "latest_order_id": None,
            }
        }
        self.purchase_events: List[Dict[str, Any]] = []

    def _ensure_user(self, user_id: str) -> Dict[str, Any]:
        return self.subscriptions.setdefault(
            user_id,
            {
                "user_id": user_id,
                "is_premium": False,
                "subscription_product_id": None,
                "subscription_purchase_token": None,
                "subscription_expiry_date": None,
                "subscription_status": "free",
                "renews_at": None,
                "cancel_at_period_end": False,
                "last_verified_at": None,
                "latest_order_id": None,
            },
        )

    def ensure_user(self, user_id: str) -> Dict[str, Any]:
        return self._ensure_user(user_id)

    def get_subscription_summary(self, user_id: str) -> Dict[str, Any]:
        self.reconcile_user(user_id)
        summary = deepcopy(self._ensure_user(user_id))
        summary["manage_subscription_url"] = self.get_manage_subscription_url(summary.get("subscription_product_id") or self.PRODUCT_ID)
        summary["product_id"] = self.PRODUCT_ID
        return summary

    def get_manage_subscription_url(self, product_id: str) -> str:
        return f"https://play.google.com/store/account/subscriptions?sku={product_id}&package={self.package_name}"

    def _load_google_credentials(self):
        if service_account is None or GoogleAuthRequest is None:
            return None
        if self.service_account_file and os.path.exists(self.service_account_file):
            return service_account.Credentials.from_service_account_file(self.service_account_file, scopes=[self.GOOGLE_SCOPE])
        if self.service_account_json:
            return service_account.Credentials.from_service_account_info(json.loads(self.service_account_json), scopes=[self.GOOGLE_SCOPE])
        return None

    async def _google_access_token(self) -> Optional[str]:
        credentials = self._load_google_credentials()
        if credentials is None:
            return None
        await asyncio.to_thread(credentials.refresh, GoogleAuthRequest())
        return credentials.token

    async def _google_subscription_status(self, purchase_token: str) -> Optional[Dict[str, Any]]:
        access_token = await self._google_access_token()
        if access_token is None:
            return None

        url = (
            f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/"
            f"{self.package_name}/purchases/subscriptionsv2/tokens/{purchase_token}"
        )
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 404:
                raise BillingError(404, "Purchase token not found in Google Play")
            if response.status_code >= 400:
                raise BillingError(response.status_code, response.text or "Google Play verification failed")
            return response.json()

    def _map_google_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        subscription_state = (payload.get("subscriptionState") or "").upper()
        line_items = payload.get("lineItems") or []
        line_item = line_items[0] if line_items else {}
        expiry = line_item.get("expiryTime")
        product_id = line_item.get("productId") or self.PRODUCT_ID
        auto_renew_enabled = bool(line_item.get("autoRenewingPlan", {}).get("autoRenewEnabled", False))

        mapped_status = {
            "SUBSCRIPTION_STATE_ACTIVE": "active",
            "SUBSCRIPTION_STATE_CANCELED": "cancelled",
            "SUBSCRIPTION_STATE_EXPIRED": "expired",
            "SUBSCRIPTION_STATE_IN_GRACE_PERIOD": "active",
            "SUBSCRIPTION_STATE_ON_HOLD": "payment_issue",
            "SUBSCRIPTION_STATE_PAUSED": "paused",
            "SUBSCRIPTION_STATE_PENDING": "pending",
        }.get(subscription_state, "failed")

        return {
            "product_id": product_id,
            "subscription_status": mapped_status,
            "subscription_expiry_date": expiry,
            "renews_at": expiry if auto_renew_enabled else None,
            "cancel_at_period_end": not auto_renew_enabled and mapped_status in {"active", "cancelled"},
            "google_payload": payload,
        }

    def _dev_verification(self, purchase_token: str, product_id: str) -> Dict[str, Any]:
        if product_id != self.PRODUCT_ID:
            raise BillingError(400, "Unsupported product id")
        if purchase_token.startswith("pending_"):
            status = "pending"
            expiry = (utc_now() + timedelta(days=30)).isoformat()
        elif purchase_token.startswith("cancelled_"):
            status = "cancelled"
            expiry = (utc_now() + timedelta(days=5)).isoformat()
        elif purchase_token.startswith("failed_"):
            status = "failed"
            expiry = None
        else:
            status = "active"
            expiry = (utc_now() + timedelta(days=30)).isoformat()
        return {
            "product_id": product_id,
            "subscription_status": status,
            "subscription_expiry_date": expiry,
            "renews_at": expiry if status == "active" else None,
            "cancel_at_period_end": status == "cancelled",
            "google_payload": {"mode": "development_fallback", "purchaseToken": purchase_token},
        }

    async def verify_purchase(
        self,
        user_id: str,
        product_id: str,
        purchase_token: str,
        package_name: Optional[str],
        order_id: Optional[str],
    ) -> Dict[str, Any]:
        subscription = self._ensure_user(user_id)
        resolved_package_name = package_name or self.package_name
        if resolved_package_name != self.package_name:
            raise BillingError(400, "Package name mismatch")

        google_payload = await self._google_subscription_status(purchase_token)
        verified = self._map_google_state(google_payload) if google_payload else self._dev_verification(purchase_token, product_id)

        subscription.update(
            {
                "subscription_product_id": verified["product_id"],
                "subscription_purchase_token": purchase_token,
                "subscription_expiry_date": verified["subscription_expiry_date"],
                "subscription_status": verified["subscription_status"],
                "renews_at": verified["renews_at"],
                "cancel_at_period_end": verified["cancel_at_period_end"],
                "is_premium": verified["subscription_status"] in {"active", "cancelled"},
                "last_verified_at": iso_now(),
                "latest_order_id": order_id,
            }
        )

        self.purchase_events.append(
            {
                "id": f"purchase-{uuid4().hex}",
                "user_id": user_id,
                "product_id": verified["product_id"],
                "purchase_token": purchase_token,
                "order_id": order_id,
                "status": verified["subscription_status"],
                "verified_at": subscription["last_verified_at"],
                "payload": verified["google_payload"],
            }
        )
        return self.get_subscription_summary(user_id)

    def reconcile_user(self, user_id: str) -> Dict[str, Any]:
        subscription = self._ensure_user(user_id)
        expiry_value = subscription.get("subscription_expiry_date")
        if expiry_value:
            expiry_time = datetime.fromisoformat(expiry_value.replace("Z", "+00:00"))
            if expiry_time <= utc_now() and subscription.get("subscription_status") not in {"expired", "failed"}:
                subscription["subscription_status"] = "expired"
                subscription["is_premium"] = False
                subscription["renews_at"] = None
        if subscription.get("subscription_status") in {"failed", "expired", "free"}:
            subscription["is_premium"] = False
        return deepcopy(subscription)

    def reconcile_all(self) -> Dict[str, Any]:
        results = []
        for user_id in list(self.subscriptions.keys()):
            results.append(self.reconcile_user(user_id))
        return {"checked": len(results), "subscriptions": results}

    async def handle_google_notification(self, notification_payload: Dict[str, Any]) -> Dict[str, Any]:
        event = deepcopy(notification_payload)
        subscription_notification = event.get("subscriptionNotification") or {}
        purchase_token = subscription_notification.get("purchaseToken")
        if not purchase_token:
            return {"processed": False, "reason": "missing purchase token"}

        matched_user = next(
            (
                user_id
                for user_id, subscription in self.subscriptions.items()
                if subscription.get("subscription_purchase_token") == purchase_token
            ),
            None,
        )
        if matched_user is None:
            return {"processed": False, "reason": "purchase token not mapped locally"}

        await self.verify_purchase(
            matched_user,
            self.subscriptions[matched_user].get("subscription_product_id") or self.PRODUCT_ID,
            purchase_token,
            self.package_name,
            self.subscriptions[matched_user].get("latest_order_id"),
        )
        return {"processed": True, "user_id": matched_user}


billing_service = BillingService()