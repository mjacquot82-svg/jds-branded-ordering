from datetime import datetime, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.availability.repository import AvailabilityRepository
from app.tenancy.context import TenantContext
from app.orders.constants import FulfillmentStatus, OrderStatus
from app.orders.models import Order
from app.orders.repository import OrderRepository
from app.loyalty.service import LoyaltyService


class FulfillmentErrorCode(str, Enum):
    NOT_FOUND = "order_not_found"
    PAYMENT_REQUIRED = "payment_required"
    INVALID_TRANSITION = "invalid_fulfillment_transition"
    STALE = "stale_order"


class FulfillmentError(ValueError):
    def __init__(self, code: FulfillmentErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


TRANSITIONS = {
    FulfillmentStatus.NEW: frozenset(
        {FulfillmentStatus.COMPLETED, FulfillmentStatus.CANCELLED}
    ),
    FulfillmentStatus.PREPARING: frozenset(
        {FulfillmentStatus.COMPLETED, FulfillmentStatus.CANCELLED}
    ),
    FulfillmentStatus.READY: frozenset(
        {FulfillmentStatus.COMPLETED, FulfillmentStatus.CANCELLED}
    ),
    FulfillmentStatus.COMPLETED: frozenset({FulfillmentStatus.NEW}),
    FulfillmentStatus.CANCELLED: frozenset(),
}


class OwnerOrderService:
    def __init__(self, session: Session, tenant: TenantContext) -> None:
        self._session = session
        self._tenant = tenant
        self._orders = OrderRepository(session, tenant)

    def active_orders(self, *, now: datetime) -> list[Order]:
        return self._orders.active_orders(unpaid_cutoff=now - timedelta(days=1))

    def history(self) -> list[Order]:
        return self._orders.history()

    def order(self, order_id: int) -> Order:
        order = self._orders.get_complete(order_id)
        if order is None:
            raise FulfillmentError(
                FulfillmentErrorCode.NOT_FOUND, "Order was not found."
            )
        return order

    def transition(
        self,
        order_id: int,
        *,
        target: FulfillmentStatus,
        expected_version: int,
        now: datetime,
    ) -> Order:
        order = self.order(order_id)
        if order.fulfillment_status == target:
            return order
        if order.status != OrderStatus.PAID:
            raise FulfillmentError(
                FulfillmentErrorCode.PAYMENT_REQUIRED,
                "Only paid orders can be updated.",
            )
        if target not in TRANSITIONS[order.fulfillment_status]:
            raise FulfillmentError(
                FulfillmentErrorCode.INVALID_TRANSITION,
                "That order can no longer be moved to the requested stage.",
            )
        if expected_version != order.version:
            raise FulfillmentError(
                FulfillmentErrorCode.STALE,
                "This order changed on another device. Refresh and try again.",
            )
        if not self._orders.transition(
            order_id=order_id,
            expected_version=expected_version,
            current_status=order.fulfillment_status,
            target_status=target,
            now=now,
        ):
            self._session.rollback()
            raise FulfillmentError(
                FulfillmentErrorCode.STALE,
                "This order changed on another device. Refresh and try again.",
            )
        if target == FulfillmentStatus.COMPLETED:
            LoyaltyService(self._session).award_completed_order(
                order_id,
                organization_id=self._tenant.organization_id,
            )
        self._session.commit()
        return self.order(order_id)

    def dashboard(self, *, now: datetime) -> dict:
        settings = AvailabilityRepository(
            self._session,
            self._tenant,
        ).get_business_settings()
        if settings is None:
            raise RuntimeError("Business settings are unavailable.")
        local_now = now.astimezone(ZoneInfo(settings.timezone))
        local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        return self._orders.dashboard_counts(
            day_start=local_start,
            day_end=local_start + timedelta(days=1),
        )
