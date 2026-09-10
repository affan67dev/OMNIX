from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

from backend.services.supabase_db import insert_one, select_many, select_one, upsert_one

try:
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2 import service_account
except Exception:  # pragma: no cover
    GoogleAuthRequest = None
    service_account = None


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

    def get_manage_subscription_url(self, product_id: str) -> str:
        return f"https://play.google.com/store/account/subscriptions?sku={product_id}&package={self.package_name}"

    async def get_subscription_summary(self, user_id: str) -> Dict[str, Any]:
        row = await select_one("subscriptions", filters={"user_id": user_id})
        if row is None:
            return {
                "user_id": user_id, "is_premium": False, "subscription_product_id": None,
                "subscription_purchase_token": None, "subscription_expiry_date": None,
                "subscription_status": "free", "renews_at": None, "cancel_at_period_end": False,
                "last_verified_at": None, "latest_order_id": None,
                "manage_subscription_url": self.get_manage_subscription_url(self.PRODUCT_ID),
                "product_id": self.PRODUCT_ID,
            }
        expiry = row.get("expiry_at")
        status = row.get("status", "free")
        is_premium = bool(row.get("is_premium")) and status in {"active", "cancelled"}
        if expiry:
            try:
                if datetime.fromisoformat(str(expiry).replace("Z", "+00:00")) <= datetime.now(timezone.utc):
                    status = "expired"
                    is_premium = False
            except ValueError:
                is_premium = False
        return {
            "user_id": user_id,
            "is_premium": is_premium,
            "subscription_product_id": row.get("product_id"),
            "subscription_purchase_token": row.get("purchase_token"),
            "subscription_expiry_date": expiry,
            "subscription_status": status,
            "renews_at": row.get("renews_at"),
            "cancel_at_period_end": bool(row.get("cancel_at_period_end")),
            "last_verified_at": row.get("last_verified_at"),
            "latest_order_id": row.get("order_id"),
            "manage_subscription_url": self.get_manage_subscription_url(row.get("product_id") or self.PRODUCT_ID),
            "product_id": self.PRODUCT_ID,
        }

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
        credentials.refresh(GoogleAuthRequest())
        return credentials.token

    async def _google_subscription_status(self, purchase_token: str) -> Dict[str, Any]:
        access_token = await self._google_access_token()
        if access_token is None:
            raise BillingError(503, "Google Play verification is not configured")
        url = f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{self.package_name}/purchases/subscriptionsv2/tokens/{purchase_token}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"})
        if response.status_code == 404:
            raise BillingError(404, "Purchase token not found in Google Play")
        if response.status_code >= 400:
            raise BillingError(response.status_code, response.text or "Google Play verification failed")
        return response.json()

    def _map_google_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        state = (payload.get("subscriptionState") or "").upper()
        line = (payload.get("lineItems") or [{}])[0]
        expiry = line.get("expiryTime")
        product_id = line.get("productId") or self.PRODUCT_ID
        auto_renew = bool((line.get("autoRenewingPlan") or {}).get("autoRenewEnabled"))
        status = {
            "SUBSCRIPTION_STATE_ACTIVE": "active", "SUBSCRIPTION_STATE_CANCELED": "cancelled",
            "SUBSCRIPTION_STATE_EXPIRED": "expired", "SUBSCRIPTION_STATE_IN_GRACE_PERIOD": "active",
            "SUBSCRIPTION_STATE_ON_HOLD": "payment_issue", "SUBSCRIPTION_STATE_PAUSED": "paused",
            "SUBSCRIPTION_STATE_PENDING": "pending",
        }.get(state, "failed")
        return {"product_id": product_id, "status": status, "expiry_at": expiry,
                "renews_at": expiry if auto_renew else None,
                "cancel_at_period_end": not auto_renew and status in {"active", "cancelled"},
                "payload": payload}

    async def verify_purchase(self, user_id: str, product_id: str, purchase_token: str,
                              package_name: Optional[str], order_id: Optional[str]) -> Dict[str, Any]:
        if product_id != self.PRODUCT_ID:
            raise BillingError(400, "Unsupported product id")
        if (package_name or self.package_name) != self.package_name:
            raise BillingError(400, "Package name mismatch")
        if not purchase_token.strip():
            raise BillingError(400, "Purchase token is required")
        verified = self._map_google_state(await self._google_subscription_status(purchase_token))
        now = datetime.now(timezone.utc).isoformat()
        await upsert_one("subscriptions", {
            "user_id": user_id, "product_id": verified["product_id"], "purchase_token": purchase_token,
            "order_id": order_id, "status": verified["status"],
            "is_premium": verified["status"] in {"active", "cancelled"},
            "expiry_at": verified["expiry_at"], "renews_at": verified["renews_at"],
            "cancel_at_period_end": verified["cancel_at_period_end"], "last_verified_at": now,
            "provider_payload": verified["payload"], "updated_at": now,
        }, "user_id")
        await insert_one("purchase_events", {
            "user_id": user_id, "product_id": verified["product_id"], "purchase_token": purchase_token,
            "order_id": order_id, "status": verified["status"], "verified_at": now,
            "payload": verified["payload"],
        })
        return await self.get_subscription_summary(user_id)

    async def reconcile_user(self, user_id: str) -> Dict[str, Any]:
        row = await select_one("subscriptions", filters={"user_id": user_id})
        if not row or not row.get("purchase_token"):
            return await self.get_subscription_summary(user_id)
        try:
            return await self.verify_purchase(user_id, row.get("product_id") or self.PRODUCT_ID,
                                              row["purchase_token"], self.package_name, row.get("order_id"))
        except BillingError:
            return await self.get_subscription_summary(user_id)

    async def handle_google_notification(self, notification_payload: Dict[str, Any]) -> Dict[str, Any]:
        notification = notification_payload.get("subscriptionNotification") or {}
        token = notification.get("purchaseToken")
        if not token:
            return {"processed": False, "reason": "missing purchase token"}
        row = await select_one("subscriptions", filters={"purchase_token": token})
        if not row:
            return {"processed": False, "reason": "purchase token not mapped"}
        await self.verify_purchase(str(row["user_id"]), row.get("product_id") or self.PRODUCT_ID,
                                   token, self.package_name, row.get("order_id"))
        return {"processed": True, "user_id": row["user_id"]}

    async def reconcile_all(self) -> Dict[str, Any]:
        rows = await select_many("subscriptions", columns="user_id")
        results = [await self.reconcile_user(str(row["user_id"])) for row in rows]
        return {"checked": len(results), "subscriptions": results}


billing_service = BillingService()
