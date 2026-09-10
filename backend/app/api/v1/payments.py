"""Generic payment API — selects tenant provider and delegates to the port."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.api.v1.catalog import ladels_compatibility_tenant
from app.api.v1.customer_auth import current_ordering_customer
from app.api.v1.owner_auth import require_read_permission
from app.api.v1.tenant_context import authenticated_owner_tenant
from app.db.session import get_db_session
from app.jds_auth.service import AuthPrincipal
from app.orders.models import Order, OrderItem
from app.payments.errors import (
    PaymentCheckoutError,
    PaymentPortError,
    ProviderNotConfiguredError,
    ProviderNotConnectedError,
    UnsupportedProviderError,
)
from app.payments.service import (
    connection_status_for_org,
    create_checkout_for_order,
    get_payment_settings,
)
from app.tenancy.context import TenantContext

router = APIRouter(prefix="/payments", tags=["payments"])
logger = logging.getLogger(__name__)


def reject_staging_payments(request: Request) -> None:
    if (
        getattr(request.app.state, "staging_review_enabled", False)
        and getattr(request.app.state, "payment_mode", "") == "fixture-disabled"
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "staging_payments_disabled",
                "message": "STAGING — real payments are disabled.",
            },
        )


class PaymentConnectionResponse(BaseModel):
    connected: bool
    provider: str
    display_hint: str
    environment: str | None = None
    health: str = "disconnected"
    payment_connected: bool = False


class CheckoutResponse(BaseModel):
    provider: str
    checkout_url: str
    checkout_session_id: str
    expires_at: datetime | None = None


def _http_for_payment_error(error: PaymentPortError) -> HTTPException:
    code = getattr(error, "code", "payment_error")
    if isinstance(error, (ProviderNotConfiguredError, UnsupportedProviderError)):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif isinstance(error, ProviderNotConnectedError):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif isinstance(error, PaymentCheckoutError) and code in {
        "order_already_paid",
    }:
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(error, PaymentCheckoutError) and code == "order_expired":
        status_code = status.HTTP_410_GONE
    else:
        status_code = status.HTTP_502_BAD_GATEWAY
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": str(error)},
    )


@router.get("/connection", response_model=PaymentConnectionResponse)
def payment_connection(
    session: Session = Depends(get_db_session),
    _: object = Depends(require_read_permission("integrations.manage")),
    tenant: TenantContext = Depends(authenticated_owner_tenant),
) -> PaymentConnectionResponse:
    status_obj = connection_status_for_org(session, tenant.organization_id)
    settings = get_payment_settings(session, tenant.organization_id)
    return PaymentConnectionResponse(
        connected=status_obj.connected,
        provider=status_obj.provider or (settings.provider_key if settings else ""),
        display_hint=status_obj.display_hint,
        environment=status_obj.environment,
        health=status_obj.health,
        payment_connected=status_obj.connected,
    )


@router.post(
    "/orders/{public_token}/checkout",
    response_model=CheckoutResponse,
    dependencies=[Depends(reject_staging_payments)],
)
def create_order_checkout(
    public_token: str,
    response: Response,
    customer: AuthPrincipal = Depends(current_ordering_customer),
    session: Session = Depends(get_db_session),
    tenant: TenantContext = Depends(ladels_compatibility_tenant),
) -> CheckoutResponse:
    """Provider-neutral checkout. Cart/storefront should call this, not /clover."""
    response.headers["Cache-Control"] = "no-store"
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

    try:
        checkout = create_checkout_for_order(session, order)
        session.commit()
    except PaymentPortError as error:
        session.rollback()
        logger.warning(
            "generic checkout rejected org=%s order=%s code=%s",
            tenant.organization_id,
            getattr(order, "id", None),
            getattr(error, "code", "payment_error"),
        )
        raise _http_for_payment_error(error) from error
    except SQLAlchemyError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "checkout_persistence_failed",
                "message": "Your order was saved, but payment is temporarily unavailable.",
            },
        ) from error

    if not checkout.redirect_url or not checkout.provider_ref:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "checkout_invalid_response",
                "message": "Payment provider returned an invalid checkout session.",
            },
        )
    return CheckoutResponse(
        provider=checkout.provider,
        checkout_url=checkout.redirect_url,
        checkout_session_id=checkout.provider_ref,
        expires_at=checkout.expires_at,
    )
