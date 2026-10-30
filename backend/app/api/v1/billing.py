"""Owner billing, platform-admin billing overview, Square billing webhook, Cockpit feed."""

from __future__ import annotations

import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.catalog import get_catalog_session
from app.api.v1.owner_auth import csrf_principal, current_principal
from app.api.v1.tenant_context import authenticated_owner_tenant
from app.billing import cockpit
from app.billing.config import BillingSquareSettings, billing_enabled, monthly_amount_cents
from app.billing.models import BillingPayment, ShopBillingAccount
from app.billing.service import billing_view, change_package, handle_square_event, ordering_paused, run_billing_sweep, save_card_and_subscribe
from app.billing.usage import period_of
from app.jds_auth.models import Organization
from app.jds_auth.service import AuthPrincipal
from app.platform.models import OperationalAuditEvent, PlatformGrant
from app.square.security import InvalidSquareSignature, verify_square_signature
from app.tenancy.context import TenantContext

router = APIRouter(tags=["billing"])


def _require_owner(principal: AuthPrincipal) -> None:
    if principal.role not in {"owner", "manager"}:
        raise HTTPException(403, detail={"code": "owner_required", "message": "Only the shop owner can manage billing."})


def _require_grant(session: Session, principal: AuthPrincipal, capability: str) -> None:
    grant = session.scalar(select(PlatformGrant.id).where(PlatformGrant.user_id == principal.user_id, PlatformGrant.capability == capability,
                                                          PlatformGrant.is_active.is_(True)))
    if grant is None:
        raise HTTPException(403, detail={"code": "platform_access_required", "message": "Platform access is not authorized."})


class CardInput(BaseModel):
    sourceId: str = Field(min_length=1, max_length=500)
    package: Literal["starter", "plus", "pro"] | None = None


class PackageChangeInput(BaseModel):
    package: Literal["starter", "plus", "pro"]
    extraLocations: int | None = Field(default=None, ge=0, le=50)


@router.get("/owner/billing")
def owner_billing(response: Response, tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    response.headers["Cache-Control"] = "private, no-store"
    return billing_view(session, tenant.organization_id)


@router.post("/owner/billing/card")
def owner_billing_card(payload: CardInput, principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    _require_owner(principal)
    save_card_and_subscribe(session, tenant.organization_id, source_id=payload.sourceId, package_key=payload.package, actor=principal.user_id)
    return billing_view(session, tenant.organization_id)


@router.put("/owner/billing/package")
def owner_billing_package(payload: PackageChangeInput, principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    _require_owner(principal)
    if not billing_enabled():
        raise HTTPException(409, detail={"code": "billing_off", "message": "Billing is not switched on. Your shop is free during the beta."})
    change_package(session, tenant.organization_id, package_key=payload.package, extra_locations=payload.extraLocations, actor=principal.user_id)
    return billing_view(session, tenant.organization_id)


@router.post("/billing/square/webhook")
async def billing_square_webhook(request: Request, session: Session = Depends(get_catalog_session),
                                 signature: str | None = Header(default=None, alias="x-square-hmacsha256-signature")) -> dict:
    settings = BillingSquareSettings.from_env()
    raw = await request.body()
    if not settings.webhook_signature_key or not settings.webhook_url:
        raise HTTPException(503, detail="Billing webhook is not configured.")
    try:
        verify_square_signature(raw, signature, settings.webhook_url, settings.webhook_signature_key)
    except InvalidSquareSignature as error:
        raise HTTPException(401, detail="Invalid signature.") from error
    try:
        event = json.loads(raw)
    except ValueError as error:
        raise HTTPException(400, detail="Invalid JSON.") from error
    return {"result": handle_square_event(session, event)}


@router.get("/platform/admin/billing")
def platform_billing(principal: AuthPrincipal = Depends(current_principal), session: Session = Depends(get_catalog_session)) -> dict:
    _require_grant(session, principal, "platform.organizations.read")
    enabled = billing_enabled()
    period = period_of()
    shops = []
    for org in session.scalars(select(Organization).order_by(Organization.name)).all():
        account = session.get(ShopBillingAccount, org.id)
        package = (account.package_key if account and account.package_key else None) or org.selected_package
        amount = (account.monthly_amount_cents if account and account.monthly_amount_cents else
                  (monthly_amount_cents(package) if package else 0))
        status = "exempt" if org.billing_exempt else (account.status if account else "none")
        last_paid = session.scalar(select(BillingPayment.occurred_at).where(BillingPayment.organization_id == org.id, BillingPayment.outcome == "paid")
                                   .order_by(BillingPayment.occurred_at.desc()).limit(1))
        shops.append({"id": str(org.id), "name": org.name, "package": package, "pendingPackage": account.pending_package_key if account else None,
                      "extraLocations": account.extra_locations if account else 0, "monthlyAmountCents": amount,
                      "status": status, "exempt": bool(org.billing_exempt), "hasCard": bool(account and account.card_last4),
                      "nextBillOn": account.next_bill_on.isoformat() if account and account.next_bill_on else None,
                      "graceEndsAt": account.grace_ends_at.isoformat() if account and account.grace_ends_at else None,
                      "orderingPaused": ordering_paused(session, org.id),
                      "lastPaidAt": last_paid.isoformat() if last_paid else None})
    paying = [s for s in shops if s["status"] in {"active", "past_due", "paused"}]
    return {"enabled": enabled, "period": period, "currency": "CAD", "shops": shops,
            "monthlyRecurringCents": sum(s["monthlyAmountCents"] for s in shops if s["status"] == "active"),
            "atRiskCents": sum(s["monthlyAmountCents"] for s in shops if s["status"] in {"past_due", "paused"}),
            "counts": {"paid": sum(1 for s in paying if s["status"] == "active"),
                       "behind": sum(1 for s in paying if s["status"] != "active"),
                       "exempt": sum(1 for s in shops if s["exempt"]),
                       "noSubscription": sum(1 for s in shops if s["status"] in {"none", "cancelled"})}}


class ExemptInput(BaseModel):
    exempt: bool


@router.put("/platform/admin/organizations/{organization_id}/billing-exempt")
def platform_billing_exempt(organization_id: UUID, payload: ExemptInput, principal: AuthPrincipal = Depends(csrf_principal), session: Session = Depends(get_catalog_session)) -> dict:
    _require_grant(session, principal, "platform.organizations.write")
    org = session.get(Organization, organization_id)
    if org is None:
        raise HTTPException(404, detail="Organization not found.")
    org.billing_exempt = payload.exempt
    session.add(OperationalAuditEvent(organization_id=org.id, scope="platform", actor_user_id=principal.user_id, action="billing.exempt_changed",
                                      target_type="organization", target_id=str(org.id), outcome="success", metadata_json={"exempt": payload.exempt}))
    session.commit()
    return {"id": str(org.id), "exempt": org.billing_exempt}


@router.post("/platform/admin/billing/sweep")
def platform_billing_sweep(principal: AuthPrincipal = Depends(csrf_principal), session: Session = Depends(get_catalog_session)) -> dict:
    _require_grant(session, principal, "platform.organizations.write")
    return run_billing_sweep(session)


@router.get("/platform/cockpit/feed")
def cockpit_feed(response: Response, period: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
                 authorization: str | None = Header(default=None), session: Session = Depends(get_catalog_session)) -> dict:
    """Read-only, token-protected per-shop usage + revenue for JDS Owner Cockpit. No personal data."""
    if not cockpit.feed_token():
        raise HTTPException(404, detail="Not found.")
    if not cockpit.token_ok(authorization):
        raise HTTPException(401, detail="Unauthorized.")
    response.headers["Cache-Control"] = "private, no-store"
    return cockpit.shop_feed(session, period or period_of())
