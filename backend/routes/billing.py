from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from backend.services.billing import BillingError, billing_service
from backend.services.social_graph import social_graph


router = APIRouter(prefix="/api/v1/billing", tags=["Billing"])


def resolve_current_user_id(x_user_id: Optional[str]) -> str:
    candidate = (x_user_id or "").strip()
    if not candidate:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if candidate not in social_graph.users:
        raise HTTPException(status_code=403, detail="User context is invalid")
    return candidate


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
async def get_subscription_summary(x_user_id: Optional[str] = Header(default=None)):
    user_id = resolve_current_user_id(x_user_id)
    return {"success": True, "subscription": billing_service.get_subscription_summary(user_id)}


@router.post("/verify-purchase")
async def verify_purchase(req: VerifyPurchaseRequest, x_user_id: Optional[str] = Header(default=None)):
    user_id = resolve_current_user_id(x_user_id)
    try:
        subscription = await billing_service.verify_purchase(
            user_id=user_id,
            product_id=req.product_id,
            purchase_token=req.purchase_token,
            package_name=req.package_name,
            order_id=req.order_id,
        )
    except BillingError as error:
        raise_billing_error(error)
    return {"success": True, "subscription": subscription}


@router.post("/google-play/notifications")
async def handle_google_play_notification(req: RealtimeNotificationRequest):
    try:
        result = await billing_service.handle_google_notification(req.notification)
    except BillingError as error:
        raise_billing_error(error)
    return {"success": True, **result}


@router.post("/reconcile-subscriptions")
async def reconcile_subscriptions():
    result = billing_service.reconcile_all()
    return {"success": True, **result}