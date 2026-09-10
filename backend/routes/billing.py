from __future__ import annotations

import hmac
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from backend.core.security import CurrentUser
from backend.services.billing import BillingError, billing_service

router = APIRouter(prefix="/api/v1/billing", tags=["Billing"])
INTERNAL_SERVICE_KEY = os.getenv("INTERNAL_SERVICE_KEY", "")


def require_internal_key(value: Optional[str]) -> None:
    if not INTERNAL_SERVICE_KEY or not value or not hmac.compare_digest(value, INTERNAL_SERVICE_KEY):
        raise HTTPException(status_code=401, detail="Internal authorization required")


def raise_billing_error(error: BillingError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.detail)


class VerifyPurchaseRequest(BaseModel):
    product_id: str
    purchase_token: str
    package_name: Optional[str] = None
    order_id: Optional[str] = None


class RealtimeNotificationRequest(BaseModel):
    notification: Dict[str, Any]


@router.get("/subscription")
async def get_subscription_summary(current_user: CurrentUser):
    return {"success": True, "subscription": await billing_service.get_subscription_summary(str(current_user["sub"]))}


@router.post("/verify-purchase")
async def verify_purchase(req: VerifyPurchaseRequest, current_user: CurrentUser):
    try:
        subscription = await billing_service.verify_purchase(
            user_id=str(current_user["sub"]), product_id=req.product_id,
            purchase_token=req.purchase_token, package_name=req.package_name, order_id=req.order_id,
        )
    except BillingError as error:
        raise_billing_error(error)
    return {"success": True, "subscription": subscription}


@router.post("/google-play/notifications")
async def handle_google_play_notification(req: RealtimeNotificationRequest,
                                           x_internal_service_key: Optional[str] = Header(default=None)):
    require_internal_key(x_internal_service_key)
    try:
        result = await billing_service.handle_google_notification(req.notification)
    except BillingError as error:
        raise_billing_error(error)
    return {"success": True, **result}


@router.post("/reconcile-subscriptions")
async def reconcile_subscriptions(current_user: CurrentUser,
                                  x_internal_service_key: Optional[str] = Header(default=None)):
    # Reconciliation is intentionally restricted to trusted server jobs. A user token alone is not enough.
    require_internal_key(x_internal_service_key)
    result = await billing_service.reconcile_all()
    return {"success": True, **result}
