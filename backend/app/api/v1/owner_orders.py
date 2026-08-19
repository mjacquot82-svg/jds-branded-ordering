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
            reference=f"GH-{order.id:06d}",
            version=order.version,
            payment_status=order.status,
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
