from app.orders.reference import order_reference
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.orders import get_order_session
from app.api.v1.owner_auth import require_permission, require_read_permission
from app.api.v1.tenant_context import authenticated_owner_tenant
from app.api.v1.order_schemas import OrderItemSnapshot
from app.jds_auth.service import AuthPrincipal
from app.orders.constants import FulfillmentStatus, OrderStatus
from app.orders.fulfillment import (
    FulfillmentError,
    FulfillmentErrorCode,
    OwnerOrderService,
)
from app.orders.models import Order
from app.tenancy.context import TenantContext
from app.payments.pay_at_pickup import (
    PayAtPickupError,
    is_pay_at_pickup,
    mark_collected_at_counter,
    mark_no_show,
)

router = APIRouter(prefix="/owner/orders", tags=["owner-orders"])


class OwnerOrderSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FulfillmentTimestamps(OwnerOrderSchema):
    preparing_at: datetime | None
    ready_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None


class OwnerOrderResponse(OwnerOrderSchema):
    id: int
    reference: str
    version: int
    payment_status: OrderStatus
    payment_method: str
    pay_at_pickup_unpaid: bool
    payment_provider: str | None = None
    refunded: bool = False
    refund_status: str | None = None
    refundable: bool = False
    fulfillment_status: FulfillmentStatus
    customer_name: str
    customer_email: str
    customer_phone: str
    notes: str | None
    requested_pickup_at: datetime
    business_timezone: str
    currency: str
    subtotal_cents: int
    tax_cents: int
    tax_name: str
    total_cents: int
    item_count: int
    created_at: datetime
    updated_at: datetime
    fulfillment_timestamps: FulfillmentTimestamps
    items: list[OrderItemSnapshot]

    @classmethod
    def from_model(cls, order: Order) -> "OwnerOrderResponse":
        return cls(
            id=order.id,
            reference=order_reference(order),
            version=order.version,
            payment_status=order.status,
            payment_method="pay_at_pickup" if is_pay_at_pickup(order) else "online",
            pay_at_pickup_unpaid=is_pay_at_pickup(order) and order.status != OrderStatus.PAID
            and order.fulfillment_status != FulfillmentStatus.CANCELLED,
            payment_provider=order.payment_provider,
            refunded=order.payment_status == "refunded",
            refund_status=((order.payment_provider_metadata or {}).get("refund") or {}).get("status"),
            refundable=order.payment_provider == "square" and order.status == OrderStatus.PAID
            and order.payment_status == "paid" and bool(order.payment_provider_txn_id),
            fulfillment_status=order.fulfillment_status,
            customer_name=order.guest_name,
            customer_email=order.guest_email,
            customer_phone=order.guest_phone,
            notes=order.notes,
            requested_pickup_at=order.requested_pickup_at,
            business_timezone=order.business_timezone,
            currency=order.currency,
            subtotal_cents=order.subtotal_cents,
            tax_cents=order.tax_cents,
            tax_name=order.tax_name,
            total_cents=order.total_cents,
            item_count=sum(item.quantity for item in order.items),
            created_at=order.created_at,
            updated_at=order.updated_at,
            fulfillment_timestamps=FulfillmentTimestamps(
                preparing_at=order.preparing_at,
                ready_at=order.ready_at,
                completed_at=order.completed_at,
                cancelled_at=order.cancelled_at,
            ),
            items=[OrderItemSnapshot.from_model(item) for item in order.items],
        )


class FulfillmentUpdate(OwnerOrderSchema):
    status: FulfillmentStatus
    expected_version: int = Field(ge=1)


class DashboardSummary(OwnerOrderSchema):
    active_paid: int
    waiting_for_payment: int
    today_paid_count: int
    today_paid_revenue_cents: int | None
    currency: str | None


def get_service(
    session: Session = Depends(get_order_session),
    tenant: TenantContext = Depends(authenticated_owner_tenant),
) -> OwnerOrderService:
    return OwnerOrderService(session, tenant)


def _handle_error(error: Exception) -> None:
    if isinstance(error, FulfillmentError):
        status_code = {
            FulfillmentErrorCode.NOT_FOUND: status.HTTP_404_NOT_FOUND,
            FulfillmentErrorCode.PAYMENT_REQUIRED: status.HTTP_409_CONFLICT,
            FulfillmentErrorCode.INVALID_TRANSITION: status.HTTP_409_CONFLICT,
            FulfillmentErrorCode.STALE: status.HTTP_409_CONFLICT,
        }[error.code]
        raise HTTPException(
            status_code=status_code,
            detail={"code": error.code.value, "message": str(error)},
        ) from error
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "owner_orders_unavailable",
            "message": "Orders are temporarily unavailable.",
        },
    ) from error


@router.get("/active", response_model=list[OwnerOrderResponse])
def active_orders(
    _: AuthPrincipal = Depends(require_read_permission("orders.read")),
    service: OwnerOrderService = Depends(get_service),
) -> list[OwnerOrderResponse]:
    try:
        return [
            OwnerOrderResponse.from_model(order)
            for order in service.active_orders(now=datetime.now(timezone.utc))
        ]
    except SQLAlchemyError as error:
        _handle_error(error)


@router.get("/history", response_model=list[OwnerOrderResponse])
def order_history(
    _: AuthPrincipal = Depends(require_read_permission("orders.read")),
    service: OwnerOrderService = Depends(get_service),
) -> list[OwnerOrderResponse]:
    try:
        return [OwnerOrderResponse.from_model(order) for order in service.history()]
    except SQLAlchemyError as error:
        _handle_error(error)


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(
    _: AuthPrincipal = Depends(require_read_permission("orders.read")),
    service: OwnerOrderService = Depends(get_service),
) -> DashboardSummary:
    try:
        return DashboardSummary(**service.dashboard(now=datetime.now(timezone.utc)))
    except (SQLAlchemyError, RuntimeError, ValueError) as error:
        _handle_error(error)


@router.get("/{order_id}", response_model=OwnerOrderResponse)
def order_detail(
    order_id: int = Path(ge=1),
    _: AuthPrincipal = Depends(require_read_permission("orders.read")),
    service: OwnerOrderService = Depends(get_service),
) -> OwnerOrderResponse:
    try:
        return OwnerOrderResponse.from_model(service.order(order_id))
    except (SQLAlchemyError, FulfillmentError) as error:
        _handle_error(error)


@router.patch("/{order_id}/fulfillment", response_model=OwnerOrderResponse)
def update_fulfillment(
    payload: FulfillmentUpdate,
    order_id: int = Path(ge=1),
    _: AuthPrincipal = Depends(require_permission("orders.fulfill")),
    service: OwnerOrderService = Depends(get_service),
) -> OwnerOrderResponse:
    try:
        order = service.transition(
            order_id,
            target=payload.status,
            expected_version=payload.expected_version,
            now=datetime.now(timezone.utc),
        )
        return OwnerOrderResponse.from_model(order)
    except (SQLAlchemyError, FulfillmentError) as error:
        _handle_error(error)


class PayAtPickupAction(OwnerOrderSchema):
    expected_version: int = Field(ge=1)


def _pay_at_pickup_action(service: OwnerOrderService, order_id: int, principal: AuthPrincipal, payload: PayAtPickupAction, action) -> OwnerOrderResponse:
    try:
        order = service.order(order_id)
        action(service._session, order, actor_user_id=principal.user_id, expected_version=payload.expected_version)
        service._session.commit()
        return OwnerOrderResponse.from_model(service.order(order_id))
    except PayAtPickupError as error:
        service._session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": error.code, "message": str(error)}) from error
    except (SQLAlchemyError, FulfillmentError) as error:
        service._session.rollback()
        _handle_error(error)


@router.post("/{order_id}/mark-paid", response_model=OwnerOrderResponse)
def mark_pay_at_pickup_paid(
    payload: PayAtPickupAction,
    order_id: int = Path(ge=1),
    principal: AuthPrincipal = Depends(require_permission("orders.fulfill")),
    service: OwnerOrderService = Depends(get_service),
) -> OwnerOrderResponse:
    """Staff took cash/card at the counter for a pay-at-pickup order."""
    return _pay_at_pickup_action(service, order_id, principal, payload, mark_collected_at_counter)


@router.post("/{order_id}/no-show", response_model=OwnerOrderResponse)
def mark_pay_at_pickup_no_show(
    payload: PayAtPickupAction,
    order_id: int = Path(ge=1),
    principal: AuthPrincipal = Depends(require_permission("orders.fulfill")),
    service: OwnerOrderService = Depends(get_service),
) -> OwnerOrderResponse:
    """Customer never came: cancel the order and turn off pay at pickup for them."""
    return _pay_at_pickup_action(service, order_id, principal, payload, mark_no_show)


class RefundRequest(OwnerOrderSchema):
    expected_version: int = Field(ge=1)
    # Only full refunds for now; if sent, must equal the order total.
    amount_cents: int | None = Field(default=None, ge=1)


@router.post("/{order_id}/refund", response_model=OwnerOrderResponse)
def refund_order(
    payload: RefundRequest,
    order_id: int = Path(ge=1),
    principal: AuthPrincipal = Depends(require_permission("orders.fulfill")),
    service: OwnerOrderService = Depends(get_service),
) -> OwnerOrderResponse:
    """Fully refund a paid online order through the shop's own payment provider."""
    from app.communications.customer_receipts import send_refund_email_safely
    from app.payments.errors import PaymentPortError
    from app.payments.registry import get_provider
    from app.platform.models import OperationalAuditEvent

    session = service._session
    try:
        order = service.order(order_id)  # tenant-scoped: 404 for other shops' orders
        if order.payment_status == "refunded":
            return OwnerOrderResponse.from_model(order)  # idempotent repeat
        if payload.expected_version != order.version:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={
                "code": "stale_order", "message": "This order changed on another device. Refresh and try again."})
        if not order.payment_provider or order.status != OrderStatus.PAID:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={
                "code": "not_refundable", "message": "Only orders paid online can be refunded."})
        result = get_provider(order.payment_provider).refund(session, order, payload.amount_cents)
        session.add(OperationalAuditEvent(
            organization_id=order.organization_id, scope="tenant", actor_user_id=principal.user_id,
            action="order.refunded", target_type="order", target_id=str(order.id), outcome="success",
            metadata_json={"provider": result.provider, "amount_cents": result.amount_cents,
                           "refund_status": result.status},
        ))
        session.commit()
        refreshed = service.order(order_id)
        send_refund_email_safely(session, refreshed)
        return OwnerOrderResponse.from_model(refreshed)
    except HTTPException:
        session.rollback()
        raise
    except PaymentPortError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail={"code": error.code, "message": str(error)}) from error
    except (SQLAlchemyError, FulfillmentError) as error:
        session.rollback()
        _handle_error(error)
