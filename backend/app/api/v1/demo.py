"""Public self-service demo funnel API (M2)."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.catalog import get_catalog_session
from app.api.v1.owner_auth import (
    client_identifier,
    csrf_principal,
    current_principal,
    get_auth_settings,
    require_trusted_origin,
    session_response,
)
from app.api.v1.tenant_context import authenticated_owner_tenant
from app.jds_auth.config import AuthSettings
from app.jds_auth.models import Organization
from app.jds_auth.schemas import SessionResponse
from app.jds_auth.service import AuthPrincipal, utc_now
from app.platform.commercial import COMMERCIAL_PROSPECT, is_prospect
from app.platform.demo_limits import limits_payload, pilot_config_payload
from app.platform.demo_service import (
    ALLOWED_FUNNEL_EVENTS,
    DemoFunnelService,
    DemoServiceError,
    public_pricing,
    record_funnel_event,
)
from app.platform.models import (
    DemoActivationRequest,
    DemoFunnelEvent,
    OperationalAuditEvent,
    PlatformGrant,
)
from app.platform.models import DesignWorkspace, MediaAsset, BusinessProfile
from app.tenancy.context import TenantContext

router = APIRouter(tags=["demo"])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DemoSignupInput(Strict):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=10, max_length=1024)
    business_name: str = Field(min_length=1, max_length=200)
    contact_name: str = Field(default="", max_length=200)
    desired_slug: str | None = Field(default=None, max_length=63, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    invite_code: str | None = Field(default=None, max_length=128)


class DemoEnterInput(Strict):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=1024)


class DemoResendVerificationInput(Strict):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class FunnelEventInput(Strict):
    event_name: str = Field(min_length=3, max_length=60)
    metadata: dict = Field(default_factory=dict)


class ActivationRequestInput(Strict):
    business_name: str = Field(min_length=1, max_length=200)
    contact_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str | None = Field(default=None, max_length=30)
    city: str = Field(default="", max_length=120)
    desired_domain: str | None = Field(default=None, max_length=253)
    processor_preference: str = Field(default="not_sure", pattern=r"^(clover|square|stripe|moneris|other|not_sure)$")


def get_demo_service(
    request: Request,
    session: Session = Depends(get_catalog_session),
    settings: AuthSettings = Depends(get_auth_settings),
) -> DemoFunnelService:
    provider = getattr(request.app.state, "auth_provider", None)
    if provider is None:
        raise HTTPException(503, detail={"code": "authentication_unavailable", "message": "Demo signup is unavailable."})
    return DemoFunnelService(session, settings, provider)


def _raise_demo(error: DemoServiceError, status: int = 400) -> None:
    raise HTTPException(status, detail={"code": error.code, "message": str(error)})


@router.get("/demo/pricing")
def demo_pricing(session: Session = Depends(get_catalog_session)) -> dict:
    pricing = public_pricing(session)
    return {
        "planKey": pricing.plan_key,
        "label": pricing.label,
        "currency": pricing.currency,
        "amountCents": pricing.amount_cents,
        "amountDisplay": f"{pricing.currency} ${pricing.amount_cents / 100:.2f}/{pricing.interval}",
        "interval": pricing.interval,
        "jdsSalesTakePercent": pricing.jds_sales_take_percent,
        "disclosure": pricing.disclosure,
        "limits": limits_payload(),
    }


@router.get("/demo/limits")
def demo_limits() -> dict:
    return limits_payload()


@router.get("/demo/pilot-config")
def demo_pilot_config() -> dict:
    """Public controlled-pilot knobs (invite gate / optional CAPTCHA site key)."""
    return pilot_config_payload()


@router.post("/demo/signup")
def demo_signup(
    payload: DemoSignupInput,
    response: Response,
    request: Request,
    _: None = Depends(require_trusted_origin),
    service: DemoFunnelService = Depends(get_demo_service),
    settings: AuthSettings = Depends(get_auth_settings),
    now: datetime = Depends(utc_now),
) -> dict:
    try:
        status, issued = service.signup(
            email=payload.email,
            password=payload.password,
            business_name=payload.business_name,
            contact_name=payload.contact_name,
            desired_slug=payload.desired_slug,
            now=now,
            user_agent=request.headers.get("user-agent"),
            client_id=client_identifier(request),
            invite_code=payload.invite_code,
        )
    except DemoServiceError as error:
        if error.code == "rate_limited":
            code_status = 429
        elif error.code == "account_exists":
            code_status = 409
        elif error.code == "invite_required":
            code_status = 403
        else:
            code_status = 400
        _raise_demo(error, code_status)
    if status == "verification_required":
        return {
            "status": "verification_required",
            "email": payload.email.strip().lower(),
            "message": (
                "We sent a verification link to your email. Open it, then return here and choose "
                "“I already started” with the same email and password to open your demo."
            ),
            "nextSteps": [
                "Check inbox and spam for the JDS verification email",
                "Open the link (it returns you to /build/verify)",
                "Use “I already started” with the same email and password",
            ],
        }
    assert issued is not None
    response.set_cookie(
        settings.session_cookie_name,
        issued.token,
        max_age=settings.session_absolute_hours * 3600,
        secure=settings.secure_cookies,
        httponly=True,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    body = session_response(issued.principal, issued.csrf_token, service.session)
    return {"status": "ready", "session": body.model_dump(), "commercialMode": COMMERCIAL_PROSPECT}


@router.post("/demo/enter")
def demo_enter(
    payload: DemoEnterInput,
    response: Response,
    request: Request,
    _: None = Depends(require_trusted_origin),
    service: DemoFunnelService = Depends(get_demo_service),
    settings: AuthSettings = Depends(get_auth_settings),
    now: datetime = Depends(utc_now),
) -> dict:
    try:
        status, issued = service.enter(
            email=payload.email,
            password=payload.password,
            now=now,
            user_agent=request.headers.get("user-agent"),
            client_id=client_identifier(request),
        )
    except DemoServiceError as error:
        code_status = 429 if error.code == "rate_limited" else 401 if error.code == "authentication_failed" else 400
        _raise_demo(error, code_status)
    if status == "verification_required":
        return {
            "status": "verification_required",
            "email": payload.email.strip().lower(),
            "message": (
                "Your email is not verified yet. Open the verification link we sent, "
                "or resend it below, then sign in again with the same password."
            ),
            "nextSteps": [
                "Open the verification link from your email",
                "Or resend verification from this page",
                "Then use “I already started” again",
            ],
        }
    assert issued is not None
    response.set_cookie(
        settings.session_cookie_name,
        issued.token,
        max_age=settings.session_absolute_hours * 3600,
        secure=settings.secure_cookies,
        httponly=True,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    org = service.session.get(Organization, issued.principal.organization_id)
    body = session_response(issued.principal, issued.csrf_token, service.session)
    return {
        "status": "ready",
        "session": body.model_dump(),
        "commercialMode": getattr(org, "commercial_mode", "live") if org else "live",
    }


@router.post("/demo/resend-verification")
def demo_resend_verification(
    payload: DemoResendVerificationInput,
    request: Request,
    _: None = Depends(require_trusted_origin),
    service: DemoFunnelService = Depends(get_demo_service),
    now: datetime = Depends(utc_now),
) -> dict:
    try:
        service.resend_verification(
            email=payload.email,
            now=now,
            client_id=client_identifier(request),
        )
    except DemoServiceError as error:
        # Always return a calm, non-enumerating message for the pilot UX.
        if error.code == "rate_limited":
            _raise_demo(error, 429)
        return {
            "status": "accepted",
            "message": (
                "If that email still needs verification, check your inbox and spam folder "
                "for the link. Then use “I already started”."
            ),
        }
    return {
        "status": "accepted",
        "message": (
            "If that email still needs verification, check your inbox and spam folder "
            "for the link. Then use “I already started”."
        ),
    }


@router.get("/owner/demo/status")
def owner_demo_status(
    response: Response,
    tenant: TenantContext = Depends(authenticated_owner_tenant),
    session: Session = Depends(get_catalog_session),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    organization = session.get(Organization, tenant.organization_id)
    mode = getattr(organization, "commercial_mode", "live") if organization else "live"
    activation = session.scalar(
        select(DemoActivationRequest)
        .where(DemoActivationRequest.organization_id == tenant.organization_id)
        .order_by(DemoActivationRequest.created_at.desc())
    )
    pricing = public_pricing(session)
    return {
        "commercialMode": mode,
        "isProspect": mode == COMMERCIAL_PROSPECT,
        "commerceEnabled": mode == "live",
        "checkoutEnabled": False if mode == COMMERCIAL_PROSPECT else None,
        "pricing": {
            "planKey": pricing.plan_key,
            "amountCents": pricing.amount_cents,
            "currency": pricing.currency,
            "amountDisplay": f"{pricing.currency} ${pricing.amount_cents / 100:.2f}/{pricing.interval}",
            "jdsSalesTakePercent": 0,
            "disclosure": pricing.disclosure,
        },
        "limits": limits_payload() if mode == COMMERCIAL_PROSPECT else None,
        "activationRequest": None
        if activation is None
        else {
            "id": str(activation.id),
            "status": activation.status,
            "processorPreference": activation.processor_preference,
            "createdAt": activation.created_at,
            "businessName": activation.business_name,
        },
    }


@router.post("/owner/demo/events", status_code=201)
def owner_demo_event(
    payload: FunnelEventInput,
    principal: AuthPrincipal = Depends(csrf_principal),
    tenant: TenantContext = Depends(authenticated_owner_tenant),
    session: Session = Depends(get_catalog_session),
) -> dict:
    if payload.event_name not in ALLOWED_FUNNEL_EVENTS:
        raise HTTPException(422, detail={"code": "invalid_event", "message": "Unsupported funnel event."})
    # Keep metadata small / non-PII heavy
    meta = {str(k)[:40]: str(v)[:120] for k, v in list((payload.metadata or {}).items())[:10]}
    event = record_funnel_event(
        session,
        event_name=payload.event_name,
        organization_id=tenant.organization_id,
        actor_user_id=principal.user_id,
        metadata=meta,
    )
    session.commit()
    return {"id": str(event.id), "eventName": event.event_name}


@router.post("/owner/demo/activation-request", status_code=201)
def owner_activation_request(
    payload: ActivationRequestInput,
    principal: AuthPrincipal = Depends(csrf_principal),
    tenant: TenantContext = Depends(authenticated_owner_tenant),
    service: DemoFunnelService = Depends(get_demo_service),
    now: datetime = Depends(utc_now),
) -> dict:
    try:
        item = service.request_activation(
            organization_id=tenant.organization_id,
            user_id=principal.user_id,
            business_name=payload.business_name,
            contact_name=payload.contact_name,
            email=payload.email,
            phone=payload.phone,
            city=payload.city,
            desired_domain=payload.desired_domain,
            processor_preference=payload.processor_preference,
            now=now,
        )
    except DemoServiceError as error:
        status = 429 if error.code == "rate_limited" else 409 if error.code in {"already_requested", "not_a_prospect"} else 400
        _raise_demo(error, status)
    return {
        "id": str(item.id),
        "status": item.status,
        "quotedAmountCents": item.quoted_amount_cents,
        "quotedCurrency": item.quoted_currency,
        "message": "Thanks — JDS will review your activation request and help you go live.",
    }


@router.get("/platform/admin/demo-prospects")
def platform_demo_prospects(
    principal: AuthPrincipal = Depends(current_principal),
    session: Session = Depends(get_catalog_session),
) -> list[dict]:
    grant = session.scalar(
        select(PlatformGrant.id).where(
            PlatformGrant.user_id == principal.user_id,
            PlatformGrant.capability == "platform.organizations.read",
            PlatformGrant.is_active.is_(True),
        )
    )
    if grant is None:
        raise HTTPException(403, detail={"code": "platform_access_required", "message": "Platform access is not authorized."})
    orgs = session.scalars(
        select(Organization).where(Organization.commercial_mode == COMMERCIAL_PROSPECT).order_by(Organization.created_at.desc())
    ).all()
    result = []
    for org in orgs:
        activation = session.scalar(
            select(DemoActivationRequest)
            .where(DemoActivationRequest.organization_id == org.id)
            .order_by(DemoActivationRequest.created_at.desc())
        )
        recent = session.scalars(
            select(DemoFunnelEvent)
            .where(DemoFunnelEvent.organization_id == org.id)
            .order_by(DemoFunnelEvent.occurred_at.desc())
            .limit(5)
        ).all()
        result.append(
            {
                "id": str(org.id),
                "name": org.name,
                "slug": org.slug,
                "commercialMode": org.commercial_mode,
                "lifecycleStatus": org.lifecycle_status,
                "createdAt": org.created_at,
                "activation": None
                if activation is None
                else {
                    "id": str(activation.id),
                    "status": activation.status,
                    "email": activation.email,
                    "contactName": activation.contact_name,
                    "businessName": activation.business_name,
                    "processorPreference": activation.processor_preference,
                    "city": activation.city,
                    "createdAt": activation.created_at,
                },
                "recentActivity": [
                    {"event": item.event_name, "occurredAt": item.occurred_at} for item in recent
                ],
            }
        )
    return result


@router.get("/platform/admin/activation-requests")
def platform_activation_requests(
    principal: AuthPrincipal = Depends(current_principal),
    session: Session = Depends(get_catalog_session),
) -> list[dict]:
    grant = session.scalar(
        select(PlatformGrant.id).where(
            PlatformGrant.user_id == principal.user_id,
            PlatformGrant.capability == "platform.organizations.read",
            PlatformGrant.is_active.is_(True),
        )
    )
    if grant is None:
        raise HTTPException(403, detail={"code": "platform_access_required", "message": "Platform access is not authorized."})
    rows = session.scalars(select(DemoActivationRequest).order_by(DemoActivationRequest.created_at.desc()).limit(100)).all()
    return [
        {
            "id": str(item.id),
            "organizationId": str(item.organization_id),
            "businessName": item.business_name,
            "contactName": item.contact_name,
            "email": item.email,
            "phone": item.phone,
            "city": item.city,
            "desiredDomain": item.desired_domain,
            "processorPreference": item.processor_preference,
            "status": item.status,
            "quotedAmountCents": item.quoted_amount_cents,
            "quotedCurrency": item.quoted_currency,
            "createdAt": item.created_at,
        }
        for item in rows
    ]


class PromoteInput(Strict):
    confirm: bool = True


@router.post("/platform/admin/organizations/{organization_id}/promote-to-live")
def platform_promote_to_live(
    organization_id: UUID,
    payload: PromoteInput,
    principal: AuthPrincipal = Depends(csrf_principal),
    session: Session = Depends(get_catalog_session),
    service: DemoFunnelService = Depends(get_demo_service),
    now: datetime = Depends(utc_now),
) -> dict:
    # Promotion changes commercial state, so it needs the platform *write* capability
    # (read-only platform viewers can see prospects but cannot promote them).
    grant = session.scalar(
        select(PlatformGrant.id).where(
            PlatformGrant.user_id == principal.user_id,
            PlatformGrant.capability == "platform.organizations.write",
            PlatformGrant.is_active.is_(True),
        )
    )
    if grant is None:
        raise HTTPException(403, detail={"code": "platform_access_required", "message": "Platform access is not authorized."})
    if not payload.confirm:
        raise HTTPException(422, detail="Confirmation required.")
    # Snapshot preservation evidence before promote
    workspace = session.get(DesignWorkspace, organization_id)
    media_count = session.scalar(
        select(MediaAsset.id).where(MediaAsset.organization_id == organization_id, MediaAsset.status == "active").limit(1)
    )
    profile = session.get(BusinessProfile, organization_id)
    try:
        organization = service.promote_to_live(
            organization_id=organization_id,
            actor_user_id=principal.user_id,
            now=now,
        )
    except DemoServiceError as error:
        _raise_demo(error, 404 if error.code == "not_found" else 400)
    return {
        "id": str(organization.id),
        "commercialMode": organization.commercial_mode,
        "preserved": {
            "designRevision": workspace.revision if workspace else None,
            "hasMedia": media_count is not None,
            "businessName": profile.display_name if profile else organization.name,
        },
    }
