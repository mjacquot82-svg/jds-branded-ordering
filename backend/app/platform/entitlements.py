from __future__ import annotations

import os
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.platform.models import BillingPlan, OrganizationSubscription

ENABLED_STATES = frozenset({"trialing", "active", "grace"})


def entitlement_features(session: Session, organization_id: UUID) -> tuple[str, str | None, dict]:
    if os.getenv("JDS_BILLING_ENFORCEMENT_ENABLED", "").strip().lower() not in {"1", "true", "yes"}:
        return "unconfigured", None, {"designStudio": True, "notifications": True, "loyalty": True}
    configured = session.scalar(select(func.count()).select_from(BillingPlan).where(BillingPlan.is_active.is_(True))) or 0
    if configured == 0:
        # Explicit pre-billing mode preserves the proven tenant while packaging is configured.
        return "unconfigured", None, {"designStudio": True, "notifications": True, "loyalty": True}
    row = session.execute(select(OrganizationSubscription, BillingPlan).join(BillingPlan, BillingPlan.key == OrganizationSubscription.plan_key).where(OrganizationSubscription.organization_id == organization_id, BillingPlan.is_active.is_(True))).first()
    if row is None:
        return "none", None, {}
    subscription, plan = row
    return subscription.state, plan.key, dict(plan.entitlements) if subscription.state in ENABLED_STATES else {}


def enforce_entitlement(session: Session, organization_id: UUID, feature: str) -> None:
    state, _, features = entitlement_features(session, organization_id)
    if features.get(feature) is not True:
        raise HTTPException(403, detail={"code":"entitlement_required","message":"This feature is not available for the organization subscription.","feature":feature,"subscriptionState":state})
