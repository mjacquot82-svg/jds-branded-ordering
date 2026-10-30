"""Square routes: owner OAuth connect, connection status, verified webhooks, status check."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.catalog import ladels_compatibility_tenant
from app.api.v1.customer_auth import optional_ordering_customer
from app.api.v1.owner_auth import require_read_permission
from app.api.v1.tenant_context import authenticated_owner_tenant
from app.clover.security import (
    InvalidOAuthState,
    create_oauth_state,
    oauth_nonce_hash,
    verify_oauth_state,
)
from app.communications.customer_receipts import send_customer_receipt_safely
from app.communications.order_alerts import send_new_order_alert_safely
from app.db.session import get_db_session
from app.jds_auth.service import AuthPrincipal
from app.orders.constants import OrderStatus
from app.orders.models import Order
from app.orders.repository import order_owner_clause
from app.payments.models import PaymentEvent
from app.payments.service import ensure_provider_selected
from app.platform.commercial import enforce_live_commerce
from app.square.client import SquareApiError, SquareClient
from app.square.config import SquareConfigurationError, SquareSettings
from app.square.models import SquareInstallation, SquareOAuthState
from app.square.security import InvalidSquareSignature, SquareTokenCipher, verify_square_signature
from app.square.service import (
    PROVIDER_KEY,
    SquareNotConnected,
    apply_verified_payment,
    pick_location,
    reconcile_from_square_order,
)
from app.tenancy.context import TenantContext

logger = logging.getLogger(__name__)

OAUTH_STATE_COOKIE = "jds_square_oauth_state"
MAX_WEBHOOK_BODY_BYTES = 64 * 1024


def reject_staging_square(request: Request) -> None:
    if (
        getattr(request.app.state, "staging_review_enabled", False)
        and getattr(request.app.state, "payment_mode", "") == "fixture-disabled"
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "staging_payments_disabled",
                    "message": "STAGING — real payments and Square connections are disabled."},
        )


router = APIRouter(prefix="/square", tags=["square"], dependencies=[Depends(reject_staging_square)])


def get_square_settings() -> SquareSettings:
    settings = SquareSettings.from_env()
    try:
        settings.validate()
    except SquareConfigurationError as error:
        logger.warning("Square route used but Square is not configured: %s", error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "square_not_configured", "message": "Square payments are not set up yet."},
        ) from error
    return settings


def get_square_client(settings: SquareSettings = Depends(get_square_settings)) -> SquareClient:
    return SquareClient(settings)


def _no_store(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _admin_redirect(settings: SquareSettings, result: str) -> RedirectResponse:
    response = RedirectResponse(
        f"{settings.frontend_url.rstrip('/')}/admin?{urlencode({'square': result})}",
        status_code=status.HTTP_302_FOUND,
    )
    response.delete_cookie(OAUTH_STATE_COOKIE)
    return _no_store(response)


@router.get("/oauth/start")
def square_oauth_start(
    session: Session = Depends(get_db_session),
    settings: SquareSettings = Depends(get_square_settings),
    client: SquareClient = Depends(get_square_client),
    principal: AuthPrincipal = Depends(require_read_permission("integrations.manage")),
    tenant: TenantContext = Depends(authenticated_owner_tenant),
) -> RedirectResponse:
    enforce_live_commerce(session, tenant.organization_id, action="square_oauth")
    state = create_oauth_state(
        settings.state_secret, organization_id=str(tenant.organization_id),
        membership_id=str(principal.membership_id), environment=settings.environment,
        app_id=settings.application_id,
    )
    claims = verify_oauth_state(state, settings.state_secret)
    session.add(SquareOAuthState(
        nonce_hash=oauth_nonce_hash(claims["nonce"]),
        organization_id=tenant.organization_id, membership_id=principal.membership_id,
        environment=settings.environment, application_id=settings.application_id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    ))
    session.commit()
    response = RedirectResponse(client.authorization_url(state), status_code=status.HTTP_302_FOUND)
    response.set_cookie(OAUTH_STATE_COOKIE, state, httponly=True, max_age=600, samesite="lax", secure=True)
    return _no_store(response)


@router.get("/oauth/callback")
def square_oauth_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
    settings: SquareSettings = Depends(get_square_settings),
    client: SquareClient = Depends(get_square_client),
) -> RedirectResponse:
    """Public browser redirect from Square.

    A redirect cannot carry the owner's bearer token, so the request is
    authenticated by the HMAC-signed ``state`` (shop + owner membership +
    issue time + nonce) plus a single-use, unexpired nonce row stored when the
    owner started the connection. Every outcome redirects to the owner dashboard.
    """
    if error:
        # Owner pressed "Deny" on Square, or Square refused. Nothing is stored.
        return _admin_redirect(settings, "cancelled")
    cookie_state = request.cookies.get(OAUTH_STATE_COOKIE)
    if not code or not state or (cookie_state is not None and cookie_state != state):
        return _admin_redirect(settings, "error")
    try:
        claims = verify_oauth_state(state, settings.state_secret)
        organization_id = UUID(str(claims.get("organization_id")))
        membership_id = UUID(str(claims.get("membership_id")))
    except (InvalidOAuthState, ValueError, TypeError):
        logger.warning("Square OAuth callback rejected: invalid state")
        return _admin_redirect(settings, "error")
    if claims.get("environment") != settings.environment or claims.get("app_id") != settings.application_id:
        logger.warning("Square OAuth callback rejected: environment/app mismatch")
        return _admin_redirect(settings, "error")
    try:
        oauth_state = session.scalar(
            select(SquareOAuthState).where(
                SquareOAuthState.nonce_hash == oauth_nonce_hash(claims["nonce"]),
                SquareOAuthState.organization_id == organization_id,
                SquareOAuthState.membership_id == membership_id,
                SquareOAuthState.consumed_at.is_(None),
                SquareOAuthState.expires_at > datetime.now(timezone.utc),
            ).with_for_update()
        )
        if oauth_state is None:
            raise InvalidOAuthState("Square sign-in link was already used or expired.")
        oauth_state.consumed_at = datetime.now(timezone.utc)
        session.commit()

        pair = client.exchange_code(code)
        claimed = session.scalar(select(SquareInstallation).where(
            SquareInstallation.environment == settings.environment,
            SquareInstallation.merchant_id == pair.merchant_id,
        ))
        if claimed is not None and claimed.organization_id != organization_id:
            raise ValueError("Square seller is already connected to another business.")
        location = pick_location(client.list_locations(pair.access_token))
        cipher = SquareTokenCipher(settings.token_encryption_key)
        installation = session.scalar(select(SquareInstallation).where(
            SquareInstallation.organization_id == organization_id,
            SquareInstallation.environment == settings.environment,
        ).with_for_update())
        if installation is None:
            installation = SquareInstallation(
                id=uuid4(), organization_id=organization_id, environment=settings.environment,
                merchant_id=pair.merchant_id, application_id=settings.application_id,
                access_token_encrypted="", refresh_token_encrypted="",
                access_token_expires_at=pair.expires_at,
            )
            session.add(installation)
        installation.merchant_id = pair.merchant_id
        installation.application_id = settings.application_id
        installation.access_token_encrypted = cipher.encrypt(pair.access_token)
        installation.refresh_token_encrypted = cipher.encrypt(pair.refresh_token)
        installation.access_token_expires_at = pair.expires_at
        installation.location_id = str(location["id"]) if location else None
        installation.currency = str(location.get("currency") or "") or None if location else None
        installation.connection_state = "connected"
        installation.reconnect_reason = None if location else "no_active_location"
        ensure_provider_selected(session, organization_id, PROVIDER_KEY)
        session.commit()
    except (SquareApiError, InvalidOAuthState, SQLAlchemyError, ValueError) as exc:
        session.rollback()
        logger.warning("Square OAuth failed org=%s reason=%s", organization_id,
                       getattr(exc, "code", type(exc).__name__))
        return _admin_redirect(settings, "error")
    return _admin_redirect(settings, "connected" if location else "no_location")


class SquareConnectionResponse(BaseModel):
    configured: bool
    connected: bool
    environment: str | None = None
    health: str
    merchant_id_hint: str | None = None
    location_id: str | None = None


@router.get("/connection", response_model=SquareConnectionResponse)
def square_connection(
    response: Response,
    session: Session = Depends(get_db_session),
    _: object = Depends(require_read_permission("integrations.manage")),
    tenant: TenantContext = Depends(authenticated_owner_tenant),
) -> SquareConnectionResponse:
    from app.payments.adapters.square_adapter import SquarePaymentProvider

    _no_store(response)
    status_ = SquarePaymentProvider().connection_status(session, tenant.organization_id)
    installation = None
    if status_.environment:
        installation = session.scalar(select(SquareInstallation).where(
            SquareInstallation.organization_id == tenant.organization_id,
            SquareInstallation.environment == status_.environment,
        ))
    hint = None
    if installation is not None and installation.merchant_id:
        hint = f"…{installation.merchant_id[-4:]}"
    return SquareConnectionResponse(
        configured=bool(status_.details.get("platform_configured")),
        connected=status_.connected, environment=status_.environment, health=status_.health,
        merchant_id_hint=hint, location_id=installation.location_id if installation else None,
    )


def _record_event(session: Session, **values) -> PaymentEvent | None:
    """Insert once per Square event_id; returns None for a duplicate delivery."""
    event = PaymentEvent(provider_key=PROVIDER_KEY, **values)
    try:
        with session.begin_nested():
            session.add(event)
            session.flush()
    except IntegrityError:
        return None
    return event


@router.post("/webhooks")
async def square_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
    settings: SquareSettings = Depends(get_square_settings),
    client: SquareClient = Depends(get_square_client),
) -> Response:
    raw = await request.body()
    if len(raw) > MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(status_code=413, detail={"code": "square_webhook_too_large"})
    try:
        verify_square_signature(
            raw, request.headers.get("x-square-hmacsha256-signature"),
            settings.webhook_url, settings.webhook_signature_key,
        )
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
    except InvalidSquareSignature as exc:
        logger.warning("Square webhook rejected: bad signature")
        raise HTTPException(status_code=401, detail={"code": "square_webhook_signature_invalid"}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "square_webhook_invalid"}) from exc

    event_type = str(payload.get("type") or "")
    event_id = str(payload.get("event_id") or "")
    payment = ((payload.get("data") or {}).get("object") or {}).get("payment") or {}
    payment_id = payment.get("id")
    square_order_id = payment.get("order_id")
    if not event_type.startswith("payment.") or not event_id or not payment_id or not square_order_id:
        return Response(status_code=200)  # acknowledged, nothing to do

    installation = session.scalar(select(SquareInstallation).where(
        SquareInstallation.environment == settings.environment,
        SquareInstallation.merchant_id == str(payload.get("merchant_id") or ""),
    ))
    if installation is None:
        logger.info("Square webhook for unknown seller ignored")
        return Response(status_code=200)
    order = session.scalar(select(Order).where(
        Order.organization_id == installation.organization_id,
        Order.payment_provider == PROVIDER_KEY,
        Order.payment_checkout_ref == str(square_order_id),
    ).with_for_update())

    event = _record_event(
        session, organization_id=installation.organization_id, provider_event_id=event_id[:200],
        event_type=event_type[:80], checkout_ref=str(square_order_id)[:200],
        provider_payment_ref=str(payment_id)[:200], order_id=order.id if order else None,
        outcome="received", payload_sha256=hashlib.sha256(raw).hexdigest(),
        metadata_json={"reported_status": str(payment.get("status") or "")[:30]},
    )
    if event is None:
        session.commit()
        return Response(status_code=200)
    if order is None:
        event.outcome = "order_not_found"
        session.commit()
        return Response(status_code=200)

    previous_status = order.status
    try:
        newly_paid, outcome = apply_verified_payment(
            session, settings, installation, order, str(payment_id), client=client
        )
    except (SquareApiError, SquareNotConnected) as exc:
        if isinstance(exc, SquareNotConnected):
            session.commit()  # keep the reconnect_required flag; event row too
        else:
            session.rollback()
        logger.error("Square webhook verification failed code=%s order=%s",
                     getattr(exc, "code", "not_connected"), order.id)
        # Non-2xx makes Square retry later; the event row was rolled back too.
        raise HTTPException(status_code=503, detail={"code": "square_verification_unavailable"}) from exc
    event.outcome = outcome
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(status_code=503, detail={"code": "webhook_persistence_failed"}) from exc
    if newly_paid and previous_status != OrderStatus.PAID:
        send_new_order_alert_safely(session, order)
        send_customer_receipt_safely(session, order)
    return Response(status_code=200)


class SquarePaymentStatusResponse(BaseModel):
    order_status: str
    payment_status: str | None
    paid: bool


@router.post("/orders/{public_token}/refresh", response_model=SquarePaymentStatusResponse)
def square_refresh_payment_status(
    public_token: str,
    response: Response,
    customer: AuthPrincipal | None = Depends(optional_ordering_customer),
    session: Session = Depends(get_db_session),
    settings: SquareSettings = Depends(get_square_settings),
    client: SquareClient = Depends(get_square_client),
    tenant: TenantContext = Depends(ladels_compatibility_tenant),
) -> SquarePaymentStatusResponse:
    """Confirmation page fallback if the webhook is slow: ask Square directly."""
    _no_store(response)
    order = session.scalar(select(Order).where(
        Order.public_access_token == public_token,
        order_owner_clause(customer.user_id if customer else None),
        Order.organization_id == tenant.organization_id,
    ).with_for_update())
    if order is None:
        raise HTTPException(status_code=404, detail={"code": "order_not_found"})
    previous_status = order.status
    newly_paid = False
    try:
        newly_paid, _ = reconcile_from_square_order(session, settings, order, client=client)
        session.commit()
    except (SquareApiError, SquareNotConnected) as exc:
        if isinstance(exc, SquareNotConnected):
            session.commit()  # keep the reconnect_required flag
        else:
            session.rollback()
        raise HTTPException(status_code=503, detail={"code": "square_status_unavailable"}) from exc
    if newly_paid and previous_status != OrderStatus.PAID:
        send_new_order_alert_safely(session, order)
        send_customer_receipt_safely(session, order)
    return SquarePaymentStatusResponse(
        order_status=str(getattr(order.status, "value", order.status)),
        payment_status=order.payment_status, paid=order.status == OrderStatus.PAID,
    )
