"""Tenant payment configuration + port orchestration for core readiness/checkout."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clover.models import CloverInstallation
from app.orders.models import Order
from app.payments.errors import (
    PaymentPortError,
    ProviderNotConfiguredError,
    ProviderNotConnectedError,
    UnsupportedProviderError,
)
from app.payments.models import OrganizationPaymentSettings
from app.payments.port import CheckoutSession, ConnectionStatus, PaymentStatusResult, ReturnUrls
from app.payments.registry import get_provider, resolve_provider_key

logger = logging.getLogger(__name__)


def get_payment_settings(
    session: Session, organization_id: UUID
) -> OrganizationPaymentSettings | None:
    return session.get(OrganizationPaymentSettings, organization_id)


def ensure_provider_selected(
    session: Session,
    organization_id: UUID,
    provider_key: str,
) -> OrganizationPaymentSettings:
    """Set or update the tenant's selected provider (no fake credentials)."""
    key = resolve_provider_key(provider_key)
    settings = get_payment_settings(session, organization_id)
    if settings is None:
        settings = OrganizationPaymentSettings(
            organization_id=organization_id,
            provider_key=key,
        )
        session.add(settings)
    else:
        settings.provider_key = key
    return settings


def ensure_clover_selected_when_connected(
    session: Session, organization_id: UUID
) -> OrganizationPaymentSettings | None:
    """When a Clover installation connects, select clover as the tenant provider."""
    installation = session.scalar(
        select(CloverInstallation.id).where(
            CloverInstallation.organization_id == organization_id,
            CloverInstallation.connection_state == "connected",
        ).limit(1)
    )
    if installation is None:
        return get_payment_settings(session, organization_id)
    return ensure_provider_selected(session, organization_id, "clover")


def resolve_tenant_provider_key(session: Session, organization_id: UUID) -> str:
    settings = get_payment_settings(session, organization_id)
    if settings is None or not settings.provider_key:
        # Fail closed: do NOT silently fall back to Clover even if an installation exists.
        raise ProviderNotConfiguredError(
            "No payment provider is configured for this business. "
            "Choose and connect a payment provider before checkout."
        )
    return resolve_provider_key(settings.provider_key)


def is_payment_connected(session: Session, organization_id: UUID) -> bool:
    """Readiness: can this tenant accept electronic payments via its selected provider?

    Dual-write repair: if settings are missing but a connected Clover installation
    already exists (pre-M1 / test fixtures), select clover. Checkout still fails
    closed when settings are absent — it does not call this repair path.

    For Clover, readiness matches pre-M1 semantics: a tenant-scoped connected
    installation is enough (platform CLOVER_* ops config is checked at checkout).
    """
    if get_payment_settings(session, organization_id) is None:
        ensure_clover_selected_when_connected(session, organization_id)
    try:
        key = resolve_tenant_provider_key(session, organization_id)
    except (ProviderNotConfiguredError, UnsupportedProviderError):
        return False
    if key == "clover":
        return bool(
            session.scalar(
                select(CloverInstallation.id).where(
                    CloverInstallation.organization_id == organization_id,
                    CloverInstallation.connection_state == "connected",
                ).limit(1)
            )
        )
    provider = get_provider(key)
    return bool(provider.connection_status(session, organization_id).connected)


def connection_status_for_org(
    session: Session, organization_id: UUID
) -> ConnectionStatus:
    try:
        key = resolve_tenant_provider_key(session, organization_id)
    except ProviderNotConfiguredError as error:
        return ConnectionStatus(
            connected=False,
            provider="",
            display_hint=str(error),
            health="not_configured",
        )
    except UnsupportedProviderError as error:
        return ConnectionStatus(
            connected=False,
            provider=(get_payment_settings(session, organization_id).provider_key
                      if get_payment_settings(session, organization_id) else ""),
            display_hint=str(error),
            health="unsupported",
        )
    return get_provider(key).connection_status(session, organization_id)


def create_checkout_for_order(
    session: Session,
    order: Order,
    *,
    return_urls: ReturnUrls | None = None,
) -> CheckoutSession:
    """Core → port → adapter. Fail closed for missing/unsupported provider."""
    try:
        key = resolve_tenant_provider_key(session, order.organization_id)
    except PaymentPortError:
        logger.warning(
            "checkout rejected: payment provider missing/unsupported org=%s order=%s",
            order.organization_id,
            order.id,
        )
        raise
    provider = get_provider(key)
    status = provider.connection_status(session, order.organization_id)
    if not status.connected:
        raise ProviderNotConnectedError(
            "Payment provider is not connected. Connect payments before checkout."
        )
    return provider.create_checkout(session, order, return_urls=return_urls)


def reconcile_order_payment(session: Session, order: Order) -> PaymentStatusResult:
    key = resolve_tenant_provider_key(session, order.organization_id)
    return get_provider(key).reconcile(session, order)
