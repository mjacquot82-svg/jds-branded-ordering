"""Read-only per-shop usage + revenue feed for JDS Owner Cockpit, and an optional payment hook.

Feed:  GET /api/v1/platform/cockpit/feed?period=YYYY-MM   (Authorization: Bearer $JDS_COCKPIT_FEED_TOKEN)
Hook:  if JDS_COCKPIT_WEBHOOK_URL is set, each paid/failed platform charge is POSTed there as JSON,
       signed with header X-JDS-Signature = hex HMAC-SHA256(JDS_COCKPIT_FEED_TOKEN, raw body).
No customer names, emails, phones or card data ever leave through either path.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import Session

from app.billing.config import PACKAGE_PRICES_CENTS, billing_enabled, monthly_amount_cents
from app.billing.models import BillingPayment, ShopBillingAccount, ShopUsageCounter
from app.catalog.models import Product
from app.jds_auth.models import Membership, Organization, Role
from app.orders.models import Order
from app.platform.models import CustomerRelationship, MediaAsset

logger = logging.getLogger(__name__)

PAID_ORDER_STATUSES = ("paid", "manual_unpaid")


def feed_token() -> str:
    return os.getenv("JDS_COCKPIT_FEED_TOKEN", "").strip()


def token_ok(header: str | None) -> bool:
    token = feed_token()
    if not token or not header or not header.startswith("Bearer "):
        return False
    return hmac.compare_digest(header[7:].strip().encode(), token.encode())


def _period_bounds(period: str) -> tuple[datetime, datetime]:
    start = datetime.strptime(period, "%Y-%m").replace(tzinfo=timezone.utc)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start, end


def shop_feed(session: Session, period: str) -> dict:
    start, end = _period_bounds(period)
    enabled = billing_enabled()
    shops = []
    for org in session.scalars(select(Organization).order_by(Organization.name)).all():
        account = session.get(ShopBillingAccount, org.id)
        package = (account.package_key if account and account.package_key else None) or org.selected_package
        extra = account.extra_locations if account else 0
        list_price = monthly_amount_cents(package, extra) if package in PACKAGE_PRICES_CENTS else 0
        charging = enabled and not org.billing_exempt
        payments = session.execute(select(BillingPayment.outcome, func.coalesce(func.sum(BillingPayment.amount_cents), 0))
                                   .where(BillingPayment.organization_id == org.id, BillingPayment.period == period)
                                   .group_by(BillingPayment.outcome)).all()
        sums = {outcome: int(total) for outcome, total in payments}
        orders = session.execute(select(func.count(), func.coalesce(func.sum(Order.total_cents), 0))
                                 .where(Order.organization_id == org.id, Order.created_at >= start, Order.created_at < end,
                                        Order.payment_status.in_(PAID_ORDER_STATUSES))).one()
        all_orders = session.scalar(select(func.count()).select_from(Order)
                                    .where(Order.organization_id == org.id, Order.created_at >= start, Order.created_at < end)) or 0
        counters = dict(session.execute(select(ShopUsageCounter.metric, ShopUsageCounter.count)
                                        .where(ShopUsageCounter.organization_id == org.id, ShopUsageCounter.period == period)).all())
        media = session.execute(select(func.count(), func.coalesce(func.sum(cast(MediaAsset.byte_size, Integer)), 0))
                                .where(MediaAsset.organization_id == org.id, MediaAsset.status == "active")).one()
        staff = session.scalar(select(func.count()).select_from(Membership).join(Role, Role.id == Membership.role_id)
                               .where(Membership.organization_id == org.id, Membership.status == "active", Role.key == "staff")) or 0
        shops.append({
            "organizationId": str(org.id), "slug": org.slug, "name": org.name,
            "lifecycleStatus": getattr(org, "lifecycle_status", None),
            "package": package, "extraLocations": extra, "billingExempt": bool(org.billing_exempt),
            "billingStatus": account.status if account else "none",
            "listPriceCents": list_price,
            "expectedRevenueCents": list_price if charging else 0,
            "billedCents": sums.get("paid", 0) + sums.get("failed", 0),
            "paidCents": sums.get("paid", 0), "failedCents": sums.get("failed", 0),
            "ordersPlaced": int(all_orders), "ordersPaid": int(orders[0]), "orderSalesCents": int(orders[1]),
            "emailsSent": int(counters.get("emails_sent", 0)), "textsSent": int(counters.get("texts_sent", 0)),
            "mediaFiles": int(media[0]), "storageBytes": int(media[1]),
            "activeStaff": int(staff),
            "products": int(session.scalar(select(func.count()).select_from(Product).where(Product.organization_id == org.id)) or 0),
            "customers": int(session.scalar(select(func.count()).select_from(CustomerRelationship).where(CustomerRelationship.organization_id == org.id)) or 0),
        })
    return {"period": period, "currency": "CAD", "billingEnabled": enabled,
            "generatedAt": datetime.now(timezone.utc).isoformat(), "shops": shops,
            "totals": {key: sum(shop[key] for shop in shops) for key in (
                "expectedRevenueCents", "paidCents", "failedCents", "ordersPlaced", "orderSalesCents",
                "emailsSent", "textsSent", "storageBytes", "activeStaff")}}


def payment_event_payload(payment: BillingPayment) -> dict:
    return {"type": f"jds.billing.payment_{payment.outcome}", "id": str(payment.id),
            "organizationId": str(payment.organization_id), "amountCents": payment.amount_cents,
            "currency": payment.currency, "package": payment.package_key, "period": payment.period,
            "occurredAt": payment.occurred_at.isoformat() if payment.occurred_at else None}


def emit_payment_event(payment: BillingPayment) -> bool:
    url = os.getenv("JDS_COCKPIT_WEBHOOK_URL", "").strip()
    token = feed_token()
    if not url or not token:
        return False
    try:
        import httpx

        body = json.dumps(payment_event_payload(payment), separators=(",", ":")).encode()
        signature = hmac.new(token.encode(), body, hashlib.sha256).hexdigest()
        httpx.post(url, content=body, timeout=5.0,
                   headers={"Content-Type": "application/json", "X-JDS-Signature": signature}).raise_for_status()
        return True
    except Exception as error:  # noqa: BLE001 - Cockpit being down must never affect billing
        logger.warning("cockpit hook failed error=%s", type(error).__name__)
        return False
