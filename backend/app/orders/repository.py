from datetime import datetime

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import Session, joinedload, selectinload

from app.catalog.models import (
    ModifierGroup,
    Product,
    ProductModifierGroup,
)
from app.orders.constants import FulfillmentStatus, OrderStatus
from app.orders.models import Order, OrderItem


class OrderRepository:
    """Catalog reads and pending-order aggregate persistence."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_idempotency_key(self, idempotency_key: str) -> Order | None:
        return self._session.scalar(
            select(Order)
            .options(
                selectinload(Order.items).selectinload(OrderItem.modifiers),
            )
            .where(Order.idempotency_key == idempotency_key)
        )

    def get_product_for_order(self, product_id: int) -> Product | None:
        return self._session.scalar(
            select(Product)
            .options(
                joinedload(Product.category),
                selectinload(Product.variants),
                selectinload(
                    Product.modifier_group_assignments
                )
                .joinedload(ProductModifierGroup.modifier_group)
                .selectinload(ModifierGroup.options),
            )
            .where(Product.id == product_id)
        )

    def add(self, order: Order) -> None:
        self._session.add(order)

    @staticmethod
    def _complete_order_query():
        return select(Order).options(
            selectinload(Order.items).selectinload(OrderItem.modifiers)
        )

    def active_orders(self, *, unpaid_cutoff: datetime) -> list[Order]:
        return list(
            self._session.scalars(
                self._complete_order_query()
                .where(
                    Order.fulfillment_status.notin_(
                        (FulfillmentStatus.COMPLETED, FulfillmentStatus.CANCELLED)
                    ),
                    or_(
                        Order.status == OrderStatus.PAID,
                        Order.created_at >= unpaid_cutoff,
                    ),
                )
                .order_by(Order.requested_pickup_at, Order.created_at, Order.id)
            ).all()
        )

    def history(self, *, limit: int = 100) -> list[Order]:
        return list(
            self._session.scalars(
                self._complete_order_query()
                .where(
                    Order.fulfillment_status.in_(
                        (FulfillmentStatus.COMPLETED, FulfillmentStatus.CANCELLED)
                    )
                )
                .order_by(
                    func.coalesce(
                        Order.completed_at,
                        Order.cancelled_at,
                        Order.fulfillment_updated_at,
                        Order.updated_at,
                    ).desc(),
                    Order.id.desc(),
                )
                .limit(limit)
            ).all()
        )

    def get_complete(self, order_id: int) -> Order | None:
        return self._session.scalar(
            self._complete_order_query().where(Order.id == order_id)
        )

    def transition(
        self,
        *,
        order_id: int,
        expected_version: int,
        current_status: FulfillmentStatus,
        target_status: FulfillmentStatus,
        now: datetime,
    ) -> bool:
        timestamp_column = {
            FulfillmentStatus.PREPARING: Order.preparing_at,
            FulfillmentStatus.READY: Order.ready_at,
            FulfillmentStatus.COMPLETED: Order.completed_at,
            FulfillmentStatus.CANCELLED: Order.cancelled_at,
        }.get(target_status)
        timestamp_values = (
            {Order.completed_at.key: None}
            if target_status == FulfillmentStatus.NEW
            else {timestamp_column.key: now}
        )
        result = self._session.execute(
            update(Order)
            .where(
                Order.id == order_id,
                Order.version == expected_version,
                Order.status == OrderStatus.PAID,
                Order.fulfillment_status == current_status,
            )
            .values(
                fulfillment_status=target_status,
                fulfillment_updated_at=now,
                version=Order.version + 1,
                updated_at=now,
                **timestamp_values,
            )
        )
        return result.rowcount == 1

    def dashboard_counts(self, *, day_start: datetime, day_end: datetime) -> dict:
        row = self._session.execute(
            select(
                func.count().filter(
                    Order.status == OrderStatus.PAID,
                    Order.fulfillment_status.notin_(
                        (FulfillmentStatus.COMPLETED, FulfillmentStatus.CANCELLED)
                    ),
                ),
                func.count().filter(
                    Order.status == OrderStatus.PAYMENT_PENDING,
                    Order.fulfillment_status.notin_(
                        (FulfillmentStatus.COMPLETED, FulfillmentStatus.CANCELLED)
                    ),
                ),
                func.count().filter(
                    Order.status == OrderStatus.PAID,
                    Order.requested_pickup_at >= day_start,
                    Order.requested_pickup_at < day_end,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                (
                                    (Order.status == OrderStatus.PAID)
                                    & (Order.requested_pickup_at >= day_start)
                                    & (Order.requested_pickup_at < day_end)
                                ),
                                Order.total_cents,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.count(func.distinct(Order.currency)).filter(
                    Order.status == OrderStatus.PAID,
                    Order.requested_pickup_at >= day_start,
                    Order.requested_pickup_at < day_end,
                ),
                func.min(Order.currency).filter(
                    Order.status == OrderStatus.PAID,
                    Order.requested_pickup_at >= day_start,
                    Order.requested_pickup_at < day_end,
                ),
            )
        ).one()
        return {
            "active_paid": row[0],
            "waiting_for_payment": row[1],
            "today_paid_count": row[2],
            "today_paid_revenue_cents": row[3] if row[4] <= 1 else None,
            "currency": row[5] if row[4] == 1 else None,
        }
