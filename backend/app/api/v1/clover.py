import hashlib
import json
import logging
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.clover.client import CloverApiError, CloverClient, CloverTokenPair
from app.clover.config import CloverConfigurationError, CloverSettings
from app.clover.models import CloverInstallation, CloverOAuthState, CloverPaymentEvent
from app.clover.security import (
    InvalidOAuthState,
    InvalidWebhookSignature,
    TokenCipher,
    create_oauth_state,
    oauth_nonce_hash,
    verify_oauth_state,
    verify_webhook_signature,
)
from app.api.v1.owner_auth import require_permission, require_read_permission
from app.api.v1.customer_auth import current_ordering_customer
from app.api.v1.catalog import ladels_compatibility_tenant
from app.api.v1.tenant_context import authenticated_owner_tenant
from app.db.session import get_db_session
from app.orders.constants import OrderStatus
from app.orders.models import Order, OrderItem
from app.jds_auth.models import Organization
from app.jds_auth.service import AuthPrincipal
from app.orders.pricing import calculate_tax_cents
from app.tenancy.context import TenantContext

router = APIRouter(prefix="/clover", tags=["clover"])
logger = logging.getLogger(__name__)
OAUTH_STATE_COOKIE = "guesthouse_clover_oauth_state"
MAX_WEBHOOK_BODY_BYTES = 64 * 1024


def _masked_identifier(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _parse_clover_checkout_expiration(value: object) -> datetime:
    if isinstance(value, bool):
        raise ValueError("Clover returned an invalid checkout expiration.")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            raise ValueError("Clover returned an invalid checkout expiration.")
        try:
            return datetime.fromtimestamp(int(normalized) / 1000, tz=timezone.utc)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
            except ValueError as error:
                raise ValueError(
                    "Clover returned an invalid checkout expiration."
                ) from error
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError("Clover returned an invalid checkout expiration.")
            return parsed.astimezone(timezone.utc)
    raise ValueError("Clover returned an invalid checkout expiration.")


def _hosted_checkout_session_id(payload: dict) -> object:
    return (
        payload.get("checkoutSessionId")
        or payload.get("checkout_session_id")
        or payload.get("data")
        or payload.get("Data")
    )


class CloverConnectionResponse(BaseModel):
    configured: bool
    connected: bool
    environment: str | None = None
    merchant_id: str | None = None
    health: str = "disconnected"
    credential_source: str | None = None
    access_token_expires_at: datetime | None = None
    refresh_token_expires_at: datetime | None = None
    configuration: dict[str, object] | None = None


class CloverCheckoutResponse(BaseModel):
    checkout_url: str
    checkout_session_id: str
    expires_at: datetime | None = None


class CloverReconciliationRequest(BaseModel):
    payment_id: str


def _payment_id(payload: dict) -> str | None:
    value = payload.get("id") or payload.get("Id") or payload.get("paymentId")
    return value if isinstance(value, str) and value.strip() else None


def _payment_facts(payment: dict) -> tuple[str | None, int | None, str | None, str | None]:
    status_value = payment.get("result") or payment.get("status")
    amount_value = payment.get("amount")
    currency_value = payment.get("currency") or payment.get("currencyCode")
    transaction_info = payment.get("transactionInfo")
    if currency_value is None and isinstance(transaction_info, dict):
        currency_value = transaction_info.get("currency")
    session_value = (
        payment.get("checkoutSessionId")
        or payment.get("checkout_session_id")
        or payment.get("externalReferenceId")
    )
    return (
        str(status_value).upper() if status_value is not None else None,
        amount_value if isinstance(amount_value, int) and not isinstance(amount_value, bool) else None,
        str(currency_value).upper() if currency_value is not None else None,
        session_value if isinstance(session_value, str) else None,
    )


def _verify_payment_evidence(
    payment: dict,
    *,
    payment_id: str,
    order: Order,
    require_session_identity: bool,
) -> tuple[str, int, str | None]:
    returned_id = payment.get("id")
    payment_status, amount_cents, currency, session_id = _payment_facts(payment)
    if returned_id != payment_id:
        raise ValueError("Clover payment identity does not match.")
    if payment_status not in {"APPROVED", "SUCCESS"}:
        raise ValueError("Clover payment is not approved.")
    if amount_cents != order.total_cents:
        raise ValueError("Clover payment amount does not match the order.")
    if currency is not None and currency != order.currency:
        raise ValueError("Clover payment currency does not match the order.")
    if order.currency != "CAD":
        raise ValueError("Clover production reconciliation requires CAD.")
    if require_session_identity and session_id != order.clover_checkout_session_id:
        raise ValueError("Clover payment does not prove the checkout session identity.")
    return payment_status, amount_cents, currency


def _record_payment_event(
    session: Session,
    *,
    installation: CloverInstallation,
    payment_id: str,
    checkout_session_id: str,
    order: Order | None,
    source: str,
    payload_hash: str | None,
    reported_status: str | None,
    verified_status: str | None,
    verified_amount_cents: int | None,
    verified_currency: str | None,
    outcome: str,
    detail: str | None = None,
) -> CloverPaymentEvent:
    existing = session.scalar(
        select(CloverPaymentEvent).where(
            CloverPaymentEvent.installation_id == installation.id,
            CloverPaymentEvent.payment_id == payment_id,
        )
    )
    if existing is not None:
        return existing
    event = CloverPaymentEvent(
        organization_id=installation.organization_id,
        installation_id=installation.id,
        environment=installation.environment,
        merchant_id=installation.merchant_id,
        payment_id=payment_id,
        checkout_session_id=checkout_session_id,
        order_id=order.id if order is not None else None,
        source=source,
        webhook_payload_sha256=payload_hash,
        reported_status=reported_status,
        verified_status=verified_status,
        verified_amount_cents=verified_amount_cents,
        verified_currency=verified_currency,
        outcome=outcome,
        detail=detail,
    )
    session.add(event)
    return event


def get_settings() -> CloverSettings:
    settings = CloverSettings.from_env()
    try:
        settings.validate()
    except CloverConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "clover_not_configured", "message": str(error)},
        ) from error
    return settings


def _configuration_diagnostic(
    settings: CloverSettings,
    installation: CloverInstallation | None,
) -> dict[str, object]:
    return {
        "environment": settings.environment,
        "app_id_masked": _masked_identifier(settings.app_id),
        "merchant_id_masked": _masked_identifier(
            installation.merchant_id if installation is not None else None
        ),
        "credential_source": settings.credential_source,
        "oauth_configured": bool(settings.app_id and settings.app_secret),
        "webhook_configured": bool(settings.webhook_secret),
        "page_configuration": (
            "configured"
            if installation is not None and installation.page_config_uuid
            else "default"
        ),
        "page_config_uuid_masked": _masked_identifier(
            installation.page_config_uuid if installation is not None else None
        ),
        "platform_api_host": settings.platform_api_base_url,
        "hosted_checkout_host": settings.hosted_checkout_base_url,
        "ecommerce_service_host": settings.ecommerce_service_base_url,
        "tokenization_host": settings.tokenization_base_url,
    }


def _installation_health(
    installation: CloverInstallation | None,
    *,
    now: datetime | None = None,
) -> str:
    if installation is None:
        return "disconnected"
    current_time = now or datetime.now(timezone.utc)
    if installation.connection_state == "reconnect_required":
        return "reconnect_required"
    if (
        installation.refresh_token_expires_at is not None
        and installation.refresh_token_expires_at <= current_time
    ):
        return "reconnect_required"
    if installation.access_token_expires_at <= current_time + timedelta(minutes=2):
        return "refresh_required"
    if installation.access_token_expires_at <= current_time + timedelta(hours=24):
        return "expiring"
    return "healthy"


@router.get("", include_in_schema=False)
def clover_launch() -> RedirectResponse:
    return RedirectResponse(url="/api/v1/clover/oauth/start", status_code=302)


@router.get("/oauth/start")
def oauth_start(
    session: Session = Depends(get_db_session),
    settings: CloverSettings = Depends(get_settings),
    principal: AuthPrincipal = Depends(require_read_permission("integrations.manage")),
    tenant: TenantContext = Depends(authenticated_owner_tenant),
) -> RedirectResponse:
    state = create_oauth_state(
        settings.state_secret, organization_id=str(tenant.organization_id),
        membership_id=str(principal.membership_id), environment=settings.environment,
        app_id=settings.app_id,
    )
    claims = verify_oauth_state(state, settings.state_secret)
    session.add(CloverOAuthState(
        nonce_hash=oauth_nonce_hash(claims["nonce"]),
        organization_id=tenant.organization_id, membership_id=principal.membership_id,
        environment=settings.environment, app_id=settings.app_id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    ))
    session.commit()
    response = RedirectResponse(
        CloverClient(settings).authorization_url(state),
        status_code=status.HTTP_302_FOUND,
    )
    response.set_cookie(
        OAUTH_STATE_COOKIE,
        state,
        httponly=True,
        max_age=600,
        samesite="lax",
        secure=True,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get("/oauth/callback")
def oauth_callback(
    request: Request,
    code: str = Query(min_length=1),
    state: str = Query(min_length=1),
    merchant_id: str | None = Query(default=None),
    merchantId: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
    settings: CloverSettings = Depends(get_settings),
    principal: AuthPrincipal = Depends(require_read_permission("integrations.manage")),
    tenant: TenantContext = Depends(authenticated_owner_tenant),
) -> RedirectResponse:
    resolved_merchant_id = merchant_id or merchantId
    returned_cookie = request.cookies.get(OAUTH_STATE_COOKIE)
    if not resolved_merchant_id or not returned_cookie:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_oauth_callback", "message": "OAuth callback is incomplete."},
        )
    try:
        claims = verify_oauth_state(state, settings.state_secret)
    except InvalidOAuthState as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_oauth_state", "message": str(error)},
        ) from error
    if returned_cookie != state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_oauth_state", "message": "OAuth state does not match."},
        )
    if (
        claims.get("organization_id") != str(tenant.organization_id)
        or claims.get("membership_id") != str(principal.membership_id)
        or claims.get("environment") != settings.environment
        or claims.get("app_id") != settings.app_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "clover_tenant_mismatch",
                "message": "Clover authorization does not match this organization.",
            },
        )

    try:
        oauth_state = session.scalar(
            select(CloverOAuthState).where(
                CloverOAuthState.nonce_hash == oauth_nonce_hash(claims["nonce"]),
                CloverOAuthState.organization_id == tenant.organization_id,
                CloverOAuthState.membership_id == principal.membership_id,
                CloverOAuthState.consumed_at.is_(None),
                CloverOAuthState.expires_at > datetime.now(timezone.utc),
            ).with_for_update()
        )
        if oauth_state is None:
            raise InvalidOAuthState("OAuth state has already been used or expired.")
        oauth_state.consumed_at = datetime.now(timezone.utc)
        session.commit()
        pair = CloverClient(settings).exchange_code(code)
        cipher = TokenCipher(settings.token_encryption_key)
        claimed = session.scalar(select(CloverInstallation).where(CloverInstallation.environment == settings.environment, CloverInstallation.merchant_id == resolved_merchant_id))
        if claimed is not None and claimed.organization_id != tenant.organization_id:
            raise ValueError("Clover merchant is already connected to another organization.")
        installation = session.scalar(select(CloverInstallation).where(CloverInstallation.organization_id == tenant.organization_id, CloverInstallation.environment == settings.environment).with_for_update())
        if installation is None:
            installation = CloverInstallation(id=uuid4(), organization_id=tenant.organization_id, merchant_id=resolved_merchant_id, environment=settings.environment, app_id=settings.app_id, access_token_encrypted="", refresh_token_encrypted="", access_token_expires_at=pair.expires_at)
            session.add(installation)
        installation.merchant_id = resolved_merchant_id
        installation.app_id = settings.app_id
        installation.access_token_encrypted = cipher.encrypt(pair.access_token)
        installation.refresh_token_encrypted = cipher.encrypt(pair.refresh_token)
        installation.access_token_expires_at = pair.expires_at
        installation.refresh_token_expires_at = pair.refresh_expires_at
        installation.connection_state = "connected"
        installation.reconnect_reason = None
        installation.page_config_uuid = settings.page_config_uuid
        session.commit()
    except (CloverApiError, InvalidOAuthState, SQLAlchemyError, ValueError) as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "clover_oauth_failed", "message": "Clover authorization failed."},
        ) from error

    query = urlencode({"clover": "connected"})
    response = RedirectResponse(
        f"{settings.frontend_url.rstrip('/')}/admin?{query}",
        status_code=status.HTTP_302_FOUND,
    )
    response.delete_cookie(OAUTH_STATE_COOKIE)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get("/connection", response_model=CloverConnectionResponse)
def connection_status(
    session: Session = Depends(get_db_session),
    settings: CloverSettings = Depends(get_settings),
    _: object = Depends(require_read_permission("integrations.manage")),
    tenant: TenantContext = Depends(authenticated_owner_tenant),
) -> CloverConnectionResponse:
    if settings.ecommerce_private_token:
        installation, _ = _active_credential(
            session, settings, organization_id=tenant.organization_id
        )
        session.commit()
    else:
        installation = None
    try:
        if installation is None:
            installation = session.scalar(
                select(CloverInstallation).where(
                    CloverInstallation.organization_id == tenant.organization_id,
                    CloverInstallation.environment == settings.environment,
                )
            )
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "clover_connection_unavailable"},
        ) from error
    return CloverConnectionResponse(
        configured=True,
        connected=(
            installation is not None
            and bool(settings.ecommerce_private_token or installation.access_token_encrypted)
        ),
        environment=settings.environment,
        merchant_id=_masked_identifier(
            installation.merchant_id if installation is not None else None
        ),
        health=(
            _installation_health(installation)
            if installation is not None
            and bool(settings.ecommerce_private_token or installation.access_token_encrypted)
            else "disconnected"
        ),
        credential_source=settings.credential_source,
        access_token_expires_at=(
            installation.access_token_expires_at
            if installation and installation.access_token_encrypted
            else None
        ),
        refresh_token_expires_at=(
            installation.refresh_token_expires_at
            if installation and installation.access_token_encrypted
            else None
        ),
        configuration=_configuration_diagnostic(settings, installation),
    )


def _active_credential(
    session: Session,
    settings: CloverSettings,
    *,
    organization_id: UUID,
    installation_id: UUID | None = None,
) -> tuple[CloverInstallation, str]:

    installation_query = select(CloverInstallation).where(
        CloverInstallation.organization_id == organization_id,
        CloverInstallation.environment == settings.environment,
    )
    if installation_id is not None:
        installation_query = installation_query.where(
            CloverInstallation.id == installation_id
        )
    try:
        installation = session.scalar(installation_query)
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "clover_connection_unavailable"},
        ) from error
    if installation is None:
        legacy_organization = session.scalar(
            select(Organization).where(
                Organization.id == organization_id,
                Organization.slug == "the-guest-house",
            )
        )
        if settings.ecommerce_private_token and legacy_organization is not None:
            installation = CloverInstallation(
                id=uuid4(),
                organization_id=organization_id,
                merchant_id=settings.merchant_id,
                environment=settings.environment,
                app_id=settings.app_id,
                access_token_encrypted="",
                refresh_token_encrypted="",
                access_token_expires_at=datetime.max.replace(tzinfo=timezone.utc),
                connection_state="connected",
                page_config_uuid=settings.page_config_uuid,
            )
            session.add(installation)
            try:
                session.flush()
            except SQLAlchemyError as error:
                session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={"code": "clover_connection_unavailable"},
                ) from error
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "clover_not_connected", "message": "Connect Clover before checkout."},
            )

    if settings.ecommerce_private_token:
        if installation.merchant_id != settings.merchant_id:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "clover_legacy_credential_mismatch"},
            )
        return installation, settings.ecommerce_private_token

    health = _installation_health(installation)
    if health == "reconnect_required":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "clover_reconnect_required", "message": "Reconnect Clover."},
        )

    cipher = TokenCipher(settings.token_encryption_key)
    refresh_cutoff = datetime.now(timezone.utc) + timedelta(minutes=2)
    if installation.access_token_expires_at > refresh_cutoff:
        try:
            return installation, cipher.decrypt(
                installation.access_token_encrypted
            )
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": "clover_token_invalid", "message": "Reconnect Clover."},
            ) from error

    try:
        installation = session.scalar(
            installation_query.with_for_update().execution_options(
                populate_existing=True
            )
        )
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "clover_connection_unavailable"},
        ) from error
    if installation is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "clover_not_connected", "message": "Connect Clover before checkout."},
        )
    if installation.access_token_expires_at <= refresh_cutoff:
        try:
            current_refresh_token = cipher.decrypt(
                installation.refresh_token_encrypted
            )
            pair: CloverTokenPair = CloverClient(settings).refresh_access_token(
                current_refresh_token
            )
        except (CloverApiError, ValueError) as error:
            session.rollback()
            if isinstance(error, ValueError) or (
                isinstance(error, CloverApiError)
                and error.upstream_status in {400, 401, 403}
            ):
                installation = session.scalar(installation_query.with_for_update())
                if installation is not None:
                    installation.connection_state = "reconnect_required"
                    installation.reconnect_reason = "refresh_rejected"
                    session.commit()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": "clover_refresh_failed", "message": "Reconnect Clover."},
            ) from error
        try:
            installation.access_token_encrypted = cipher.encrypt(pair.access_token)
            installation.refresh_token_encrypted = cipher.encrypt(pair.refresh_token)
            installation.access_token_expires_at = pair.expires_at
            installation.refresh_token_expires_at = pair.refresh_expires_at
            installation.connection_state = "connected"
            installation.reconnect_reason = None
            session.commit()
        except (SQLAlchemyError, ValueError) as error:
            session.rollback()
            # Clover refresh tokens are single-use. If persistence fails after
            # Clover issued a new pair, the stored token may no longer be usable.
            # Do not guess at recovery-token semantics: require authorization again.
            try:
                installation = session.scalar(installation_query.with_for_update())
                if installation is not None:
                    installation.connection_state = "reconnect_required"
                    installation.reconnect_reason = "refresh_rotation_not_persisted"
                    session.commit()
            except SQLAlchemyError:
                session.rollback()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": "clover_refresh_failed", "message": "Reconnect Clover."},
            ) from error

    try:
        return installation, cipher.decrypt(
            installation.access_token_encrypted
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "clover_token_invalid", "message": "Reconnect Clover."},
        ) from error


def _checkout_payload(
    order: Order,
    settings: CloverSettings,
    *,
    page_config_uuid: str | None = None,
) -> dict:
    if settings.environment == "production" and order.currency != "CAD":
        raise ValueError("Production Clover checkout requires a CAD order.")
    name_parts = order.guest_name.split(maxsplit=1)
    customer = {
        "firstName": name_parts[0],
        "email": order.guest_email,
        "phoneNumber": order.guest_phone,
    }
    if len(name_parts) > 1:
        customer["lastName"] = name_parts[1]
    base_return_url = (
        f"{settings.frontend_url.rstrip('/')}/confirmation"
        f"?order={order.public_access_token}"
    )
    line_items = []
    for item in order.items:
        base_name = (
            f"{item.variant_name} {item.product_name}"
            if item.variant_name
            else item.product_name
        )
        grouped_modifiers: OrderedDict[str, list[str]] = OrderedDict()
        for modifier in item.modifiers:
            option = modifier.modifier_option_name
            if modifier.quantity > 1:
                option = f"{option} x{modifier.quantity}"
            grouped_modifiers.setdefault(
                modifier.modifier_group_name, []
            ).append(option)
        configuration = " · ".join(
            f"{group_name}: {', '.join(options)}"
            for group_name, options in grouped_modifiers.items()
        )
        # `note` is Clover's documented line-item description field, but its
        # Hosted Checkout theme does not always render notes. Keep the concise
        # configuration in the supported name as well so it remains visible.
        line_item = {
            "name": (
                f"{base_name} — {configuration}" if configuration else base_name
            ),
            "note": configuration,
            "price": item.unit_price_cents,
            "unitQty": item.quantity,
            "taxRates": [
                {"name": order.tax_name, "rate": order.tax_rate_millionths}
            ] if order.tax_rate_millionths else [],
        }
        line_items.append(line_item)
    subtotal_cents = sum(
        item.unit_price_cents * item.quantity for item in order.items
    )
    calculated_tax_cents = calculate_tax_cents(
        subtotal_cents, order.tax_rate_millionths
    )
    if calculated_tax_cents != order.tax_cents:
        raise ValueError("Clover checkout tax does not match the order tax.")
    charged_cents = subtotal_cents + calculated_tax_cents
    if charged_cents != order.total_cents:
        raise ValueError("Clover checkout total does not match the order total.")

    payload = {
        "customer": customer,
        "redirectUrls": {
            "success": f"{base_return_url}&payment=success&session_id={{CHECKOUT_SESSION_ID}}",
            "failure": f"{base_return_url}&payment=failure&session_id={{CHECKOUT_SESSION_ID}}",
            "cancel": f"{base_return_url}&payment=cancelled&session_id={{CHECKOUT_SESSION_ID}}",
        },
        "shoppingCart": {"lineItems": line_items},
    }
    if page_config_uuid:
        payload["pageConfigUuid"] = page_config_uuid
    return payload


@router.get("/debug/tax-rates")
def debug_clover_tax_rates(
    response: Response,
    session: Session = Depends(get_db_session),
    settings: CloverSettings = Depends(get_settings),
    _: object = Depends(require_read_permission("integrations.manage")),
    tenant: TenantContext = Depends(authenticated_owner_tenant),
) -> dict:
    """Temporary authenticated diagnostic for Clover merchant tax rates."""
    if settings.environment != "sandbox":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "diagnostic_not_available"},
        )
    response.headers["Cache-Control"] = "no-store"
    current_time = datetime.now(timezone.utc)
    credential_source = (
        "CLOVER_ECOMMERCE_PRIVATE_TOKEN"
        if settings.ecommerce_private_token
        else "OAuth installation"
    )
    stored_expiration_before = None
    installation = session.scalar(
        select(CloverInstallation).where(
            CloverInstallation.organization_id == tenant.organization_id,
            CloverInstallation.environment == settings.environment,
        )
    )
    persisted_installation_app_id = (
        installation.app_id if installation is not None else None
    )
    if credential_source == "OAuth installation" and installation is not None:
        stored_expiration_before = installation.access_token_expires_at

    installation, access_token = _active_credential(
        session, settings, organization_id=tenant.organization_id
    )
    merchant_id = installation.merchant_id
    stored_expiration = stored_expiration_before
    token_refreshed = False
    if credential_source == "OAuth installation":
        installation = session.scalar(
            select(CloverInstallation)
            .where(
                CloverInstallation.organization_id == tenant.organization_id,
                CloverInstallation.environment == settings.environment,
            )
            .execution_options(populate_existing=True)
        )
        if installation is not None:
            stored_expiration = installation.access_token_expires_at
            persisted_installation_app_id = installation.app_id
            token_refreshed = stored_expiration != stored_expiration_before

    credential_diagnostic = {
        "credential_source": credential_source,
        "configured_app_id_masked": _masked_identifier(settings.app_id),
        "persisted_installation_app_id_masked": _masked_identifier(
            persisted_installation_app_id
        ),
        "merchant_id_masked": _masked_identifier(merchant_id),
        "token_refreshed": token_refreshed,
        "stored_expiration": (
            stored_expiration.isoformat() if stored_expiration is not None else None
        ),
        "current_utc_time": current_time.isoformat(),
    }
    logger.info(
        "Clover tax rates credential diagnostic: %s",
        json.dumps(credential_diagnostic, sort_keys=True),
    )
    try:
        data, upstream_status, upstream_headers = (
            CloverClient(settings).get_merchant_tax_rates(
                access_token=access_token,
                merchant_id=merchant_id,
            )
        )
    except CloverApiError as error:
        request_id = next(
            (
                error.upstream_response_headers.get(name)
                for name in (
                    "x-request-id",
                    "x-correlation-id",
                    "trace-id",
                    "x-trace-id",
                    "cf-ray",
                )
                if error.upstream_response_headers.get(name)
            ),
            None,
        )
        logger.error(
            "Clover tax rates diagnostic failed: %s",
            json.dumps(
                {
                    "merchant_id_masked": _masked_identifier(merchant_id),
                    "upstream_status": error.upstream_status,
                    "response_body": error.upstream_response_body,
                    "request_id": request_id,
                },
                default=str,
                sort_keys=True,
            ),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": error.code,
                "credential_diagnostic": credential_diagnostic,
                "upstream_status": error.upstream_status,
                "response_body": error.upstream_response_body,
                "request_id": request_id,
            },
        ) from error

    logger.info(
        "Clover tax rates diagnostic: %s",
        json.dumps(
            {
                "merchant_id_masked": _masked_identifier(merchant_id),
                "upstream_status": upstream_status,
                "response_body": data,
                "upstream_headers": upstream_headers,
            },
            default=str,
            sort_keys=True,
        ),
    )
    return {
        "credential_diagnostic": credential_diagnostic,
        "clover_response": data,
    }


@router.post(
    "/orders/{public_token}/checkout",
    response_model=CloverCheckoutResponse,
)
def create_hosted_checkout(
    public_token: str,
    response: Response,
    customer: AuthPrincipal = Depends(current_ordering_customer),
    session: Session = Depends(get_db_session),
    settings: CloverSettings = Depends(get_settings),
    tenant: TenantContext = Depends(ladels_compatibility_tenant),
) -> CloverCheckoutResponse:
    response.headers["Cache-Control"] = "no-store"
    now = datetime.now(timezone.utc)
    try:
        order = session.scalar(
            select(Order)
            .options(selectinload(Order.items).selectinload(OrderItem.modifiers))
            .where(
                Order.public_access_token == public_token,
                Order.customer_user_id == customer.user_id,
                Order.organization_id == tenant.organization_id,
            )
            .with_for_update()
        )
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "checkout_service_unavailable"},
        ) from error
    if order is None:
        raise HTTPException(status_code=404, detail={"code": "order_not_found"})
    installation, access_token = _active_credential(
        session,
        settings,
        organization_id=order.organization_id,
        installation_id=order.clover_installation_id,
    )
    merchant_id = installation.merchant_id
    if order.status == OrderStatus.PAID:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "order_already_paid", "message": "Order is already paid."},
        )
    if order.expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"code": "order_expired", "message": "Order has expired."},
        )
    if (
        order.clover_checkout_url
        and order.clover_checkout_session_id
        and order.clover_checkout_expires_at
    ):
        if order.clover_checkout_expires_at > now:
            return CloverCheckoutResponse(
                checkout_url=order.clover_checkout_url,
                checkout_session_id=order.clover_checkout_session_id,
                expires_at=order.clover_checkout_expires_at,
            )

    try:
        result = CloverClient(settings).create_checkout(
            access_token=access_token,
            merchant_id=merchant_id,
            payload=_checkout_payload(
                order,
                settings,
                page_config_uuid=installation.page_config_uuid,
            ),
        )
        order.clover_installation_id = installation.id
        order.clover_environment = installation.environment
        order.clover_merchant_id = merchant_id
        order.clover_checkout_session_id = result["checkoutSessionId"]
        order.clover_checkout_url = result["href"]
        expiration = result.get("expirationTime")
        order.clover_checkout_expires_at = (
            _parse_clover_checkout_expiration(expiration)
            if expiration
            else now + timedelta(minutes=15)
        )
        if order.clover_checkout_expires_at <= now:
            raise ValueError("Clover returned an expired checkout session.")
        order.status = OrderStatus.PAYMENT_PENDING
        order.version += 1
        session.commit()
    except CloverApiError as error:
        session.rollback()
        logger.error(
            "Clover checkout creation failed: %s",
            json.dumps(
                {
                    "clover_error_code": error.code,
                    "upstream_http_status": error.upstream_status,
                    "upstream_error_code": error.upstream_error_code,
                    "upstream_error_message": error.upstream_error_message,
                    "upstream_response_body": error.upstream_response_body,
                    "upstream_response_headers": error.upstream_response_headers,
                    "timeout_information": error.timeout_information,
                    "order_id": order.id,
                },
                default=str,
                sort_keys=True,
            ),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": error.code,
                "message": (
                    "Your order was saved, but we couldn’t reach our payment "
                    "provider. Please try payment again."
                    if error.code in {"clover_timeout", "clover_unreachable"}
                    else "Your order was saved, but secure payment could not "
                    "be started. Please try payment again."
                ),
            },
        ) from error
    except SQLAlchemyError as error:
        session.rollback()
        logger.exception(
            "Checkout persistence failed after Clover response",
            extra={"order_id": order.id},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "checkout_persistence_failed",
                "message": "Your order was saved, but payment is temporarily "
                "unavailable. Please try payment again.",
            },
        ) from error
    except (TypeError, ValueError) as error:
        session.rollback()
        logger.exception(
            "Checkout response or order totals were invalid",
            extra={"order_id": order.id},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "checkout_configuration_error",
                "message": "Your order was saved, but payment is temporarily "
                "unavailable. Please try payment again.",
            },
        ) from error

    return CloverCheckoutResponse(
        checkout_url=order.clover_checkout_url,
        checkout_session_id=order.clover_checkout_session_id,
        expires_at=order.clover_checkout_expires_at,
    )


@router.post("/webhooks/hosted-checkout", status_code=status.HTTP_204_NO_CONTENT)
async def hosted_checkout_webhook(
    request: Request,
    clover_signature: str = Header(alias="Clover-Signature"),
    content_length: int | None = Header(default=None, alias="Content-Length"),
    session: Session = Depends(get_db_session),
    settings: CloverSettings = Depends(get_settings),
) -> Response:
    if content_length is not None and content_length > MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": "clover_webhook_too_large"},
        )
    raw_body = await request.body()
    if len(raw_body) > MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": "clover_webhook_too_large"},
        )
    try:
        verify_webhook_signature(
            raw_body,
            clover_signature,
            settings.webhook_secret,
        )
        payload = json.loads(raw_body)
        if not isinstance(payload, dict):
            raise ValueError("Clover webhook payload must be an object.")
    except (InvalidWebhookSignature, json.JSONDecodeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_clover_webhook", "message": str(error)},
        ) from error

    checkout_session_id = _hosted_checkout_session_id(payload)
    payload_hash = hashlib.sha256(raw_body).hexdigest()
    payment_id = _payment_id(payload)
    event_type = str(payload.get("type") or payload.get("Type") or "").upper()
    payment_status = str(
        payload.get("status") or payload.get("Status") or ""
    ).upper()
    merchant_id = (
        payload.get("merchantId")
        or payload.get("merchant_id")
        or payload.get("MerchantId")
    )
    webhook_diagnostic = {
        "webhook_type": event_type,
        "webhook_status": payment_status,
        "merchant_id_masked": _masked_identifier(
            merchant_id if isinstance(merchant_id, str) else None
        ),
        "checkout_session_id_masked": _masked_identifier(
            checkout_session_id if isinstance(checkout_session_id, str) else None
        ),
        "payment_id_masked": _masked_identifier(payment_id),
    }
    logger.warning(
        "Clover Hosted Checkout webhook received: %s",
        json.dumps(webhook_diagnostic, default=str, sort_keys=True),
    )
    if (
        event_type != "PAYMENT"
        or not isinstance(checkout_session_id, str)
        or not isinstance(merchant_id, str)
    ):
        if event_type != "PAYMENT":
            reason = "unsupported_webhook_type"
        elif not isinstance(checkout_session_id, str):
            reason = "checkout_session_id_is_missing_or_invalid"
        else:
            reason = "merchant_id_is_missing_or_invalid"
        logger.warning(
            "Clover Hosted Checkout webhook ignored: %s",
            json.dumps(
                {
                    **webhook_diagnostic,
                    "matching_order_found": False,
                    "order_status_changed": False,
                    "reason": reason,
                },
                default=str,
                sort_keys=True,
            ),
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    try:
        installation = session.scalar(
            select(CloverInstallation).where(
                CloverInstallation.environment == settings.environment,
                CloverInstallation.merchant_id == merchant_id,
                CloverInstallation.connection_state != "disconnected",
            )
        )
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "webhook_persistence_failed"},
        ) from error
    if installation is None:
        logger.warning(
            "Clover Hosted Checkout webhook ignored: %s",
            json.dumps(
                {
                    **webhook_diagnostic,
                    "matching_order_found": False,
                    "order_status_changed": False,
                    "reason": "unknown_clover_installation",
                },
                default=str,
                sort_keys=True,
            ),
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    verified_payment: dict | None = None
    if (
        settings.environment == "production"
        and payment_status == "APPROVED"
    ):
        if payment_id is None:
            logger.error(
                "Production Clover webhook omitted payment identity: %s",
                json.dumps(webhook_diagnostic, sort_keys=True),
            )
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        try:
            credential_installation, access_token = _active_credential(
                session,
                settings,
                organization_id=installation.organization_id,
                installation_id=installation.id,
            )
            verified_payment = CloverClient(settings).get_payment(
                access_token=access_token,
                merchant_id=credential_installation.merchant_id,
                payment_id=payment_id,
            )
        except (CloverApiError, HTTPException) as error:
            session.rollback()
            logger.error(
                "Production Clover payment evidence lookup failed: %s",
                json.dumps(webhook_diagnostic, sort_keys=True),
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "clover_payment_verification_unavailable"},
            ) from error

    try:
        order = session.scalar(
            select(Order)
            .where(
                Order.clover_checkout_session_id == checkout_session_id,
                Order.clover_merchant_id == merchant_id,
                Order.clover_installation_id == installation.id,
                Order.clover_environment == installation.environment,
                Order.organization_id == installation.organization_id,
            )
            .with_for_update()
        )
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "webhook_persistence_failed"},
        ) from error
    if order is None:
        logger.warning(
            "Clover Hosted Checkout webhook did not match an order: %s",
            json.dumps(
                {
                    **webhook_diagnostic,
                    "matching_order_found": False,
                    "order_status_changed": False,
                    "reason": (
                        "no_order_matches_both_checkout_session_id_and_merchant_id"
                    ),
                },
                default=str,
                sort_keys=True,
            ),
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    verified_status = None
    verified_amount_cents = None
    verified_currency = None
    if verified_payment is not None and payment_id is not None:
        try:
            (
                verified_status,
                verified_amount_cents,
                verified_currency,
            ) = _verify_payment_evidence(
                verified_payment,
                payment_id=payment_id,
                order=order,
                require_session_identity=False,
            )
        except ValueError as error:
            _record_payment_event(
                session,
                installation=installation,
                payment_id=payment_id,
                checkout_session_id=checkout_session_id,
                order=order,
                source="hosted_checkout_webhook",
                payload_hash=payload_hash,
                reported_status=payment_status,
                verified_status=None,
                verified_amount_cents=None,
                verified_currency=None,
                outcome="rejected",
                detail=str(error),
            )
            session.commit()
            logger.error(
                "Production Clover payment evidence rejected: %s",
                json.dumps(webhook_diagnostic, sort_keys=True),
            )
            return Response(status_code=status.HTTP_204_NO_CONTENT)

    event_payment_id = payment_id or f"webhook:{payload_hash}"
    event = _record_payment_event(
        session,
        installation=installation,
        payment_id=event_payment_id,
        checkout_session_id=checkout_session_id,
        order=order,
        source="hosted_checkout_webhook",
        payload_hash=payload_hash,
        reported_status=payment_status,
        verified_status=verified_status,
        verified_amount_cents=verified_amount_cents,
        verified_currency=verified_currency,
        outcome="received",
    )
    if (
        event.order_id != order.id
        or event.checkout_session_id != checkout_session_id
    ):
        logger.error(
            "Clover payment identity was already bound to another checkout: %s",
            json.dumps(webhook_diagnostic, sort_keys=True),
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    previous_status = order.status
    if payment_status == "APPROVED" and order.status != OrderStatus.PAID:
        order.status = OrderStatus.PAID
        event.outcome = "paid_transition_applied"
    elif (
        payment_status in {"DECLINED", "FAILED"}
        and order.status != OrderStatus.PAID
    ):
        order.status = OrderStatus.PAYMENT_FAILED
        event.outcome = "failed_transition_applied"
    else:
        if order.status == OrderStatus.PAID:
            reason = "paid_order_transition_is_monotonic"
        elif payment_status not in {"APPROVED", "DECLINED", "FAILED"}:
            reason = "unsupported_payment_status"
        else:
            reason = "order_already_has_target_status"
        logger.warning(
            "Clover Hosted Checkout webhook transition skipped: %s",
            json.dumps(
                {
                    **webhook_diagnostic,
                    "matching_order_found": True,
                    "order_status_changed": False,
                    "order_status": str(order.status),
                    "reason": reason,
                },
                default=str,
                sort_keys=True,
            ),
        )
        if event.outcome == "received":
            event.outcome = "duplicate_or_ignored"
            event.detail = reason
        session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    order.version += 1
    try:
        session.commit()
    except SQLAlchemyError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "webhook_persistence_failed"},
        ) from error
    logger.warning(
        "Clover Hosted Checkout webhook transition applied: %s",
        json.dumps(
            {
                **webhook_diagnostic,
                "matching_order_found": True,
                "order_status_changed": True,
                "previous_order_status": str(previous_status),
                "order_status": str(order.status),
            },
            default=str,
            sort_keys=True,
        ),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/orders/{public_token}/reconcile", status_code=status.HTTP_204_NO_CONTENT)
def reconcile_hosted_checkout_payment(
    public_token: str,
    request_body: CloverReconciliationRequest,
    session: Session = Depends(get_db_session),
    settings: CloverSettings = Depends(get_settings),
    _: object = Depends(require_permission("integrations.manage")),
    tenant: TenantContext = Depends(authenticated_owner_tenant),
) -> Response:
    """Recover a missed webhook only when Clover proves every required identity."""
    if settings.environment != "production":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "reconciliation_production_only"},
        )
    order = session.scalar(select(Order).where(Order.public_access_token == public_token, Order.organization_id == tenant.organization_id))
    if order is None:
        raise HTTPException(status_code=404, detail={"code": "order_not_found"})
    checkout_session_id = order.clover_checkout_session_id
    if not checkout_session_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "clover_checkout_identity_missing"},
        )
    if order.status == OrderStatus.PAID:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if (
        not order.clover_checkout_session_id
        or order.clover_installation_id is None
        or order.clover_environment != settings.environment
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "clover_checkout_identity_missing"},
        )
    installation, access_token = _active_credential(
        session,
        settings,
        organization_id=tenant.organization_id,
        installation_id=order.clover_installation_id,
    )
    merchant_id = installation.merchant_id
    if order.clover_merchant_id != merchant_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "clover_checkout_identity_missing"},
        )
    order = session.scalar(
        select(Order).where(Order.public_access_token == public_token, Order.organization_id == tenant.organization_id).with_for_update()
    )
    if order is None:
        raise HTTPException(status_code=404, detail={"code": "order_not_found"})
    try:
        payment = CloverClient(settings).get_payment(
            access_token=access_token,
            merchant_id=merchant_id,
            payment_id=request_body.payment_id,
        )
        verified_status, verified_amount, verified_currency = _verify_payment_evidence(
            payment,
            payment_id=request_body.payment_id,
            order=order,
            require_session_identity=True,
        )
    except CloverApiError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "clover_payment_verification_unavailable"},
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "clover_payment_evidence_insufficient", "message": str(error)},
        ) from error

    event = _record_payment_event(
        session,
        installation=installation,
        payment_id=request_body.payment_id,
        checkout_session_id=checkout_session_id,
        order=order,
        source="owner_reconciliation",
        payload_hash=None,
        reported_status=None,
        verified_status=verified_status,
        verified_amount_cents=verified_amount,
        verified_currency=verified_currency,
        outcome="paid_transition_applied",
    )
    if (
        event.order_id != order.id
        or event.checkout_session_id != checkout_session_id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "clover_payment_already_reconciled"},
        )
    if order.status != OrderStatus.PAID:
        order.status = OrderStatus.PAID
        order.version += 1
    else:
        event.outcome = "duplicate_or_ignored"
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
