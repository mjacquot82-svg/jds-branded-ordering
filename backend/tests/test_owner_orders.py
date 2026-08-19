from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.api.v1.owner_auth import csrf_principal, current_principal
from app.jds_auth.models import Organization
from app.jds_auth.service import AuthPrincipal
from app.main import create_app
from app.orders.constants import FulfillmentStatus, OrderStatus
from app.orders.fulfillment import FulfillmentError, FulfillmentErrorCode, OwnerOrderService
from app.orders.models import Order, OrderItem
from tests.test_migrations import make_alembic_config
from tests.test_order_service import local_datetime, seed_order_dependencies


def principal(
    *permissions: str,
    organization_id: UUID | None = None,
) -> AuthPrincipal:
    return AuthPrincipal(
        user_id=uuid4(), membership_id=uuid4(), organization_id=organization_id or uuid4(),
        application_id=uuid4(), session_id=uuid4(), email="owner@example.com",
        display_name="Jessie", role="owner", permissions=frozenset(permissions),
        assurance_level="aal1",
    )


def add_order(
    session: Session,
    *,
    key: str,
    payment: OrderStatus = OrderStatus.PAID,
    fulfillment: FulfillmentStatus = FulfillmentStatus.NEW,
    pickup: datetime | None = None,
) -> Order:
    now = datetime.now(timezone.utc)
    order = Order(
        idempotency_key=key,
        request_fingerprint=(key[0] * 64),
        public_access_token=f"token-{key}",
        status=payment,
        fulfillment_status=fulfillment,
        guest_name="Jessie Guest",
        guest_email="guest@example.com",
        guest_phone="+15195550100",
        requested_pickup_at=pickup or now + timedelta(minutes=20),
        business_timezone="America/Toronto",
        currency="CAD",
        subtotal_cents=1000,
        tax_cents=130,
        tax_name="HST",
        tax_rate_millionths=1_300_000,
        total_cents=1130,
        version=1,
        expires_at=now + timedelta(hours=1),
        created_at=now,
        updated_at=now,
        items=[OrderItem(
            product_slug="latte", product_name="Latte", base_unit_price_cents=1000,
            unit_price_cents=1000, quantity=1, line_subtotal_cents=1000, sort_order=0,
        )],
    )
    session.add(order)
    session.flush()
    return order


@pytest.fixture
def owner_orders_api(postgresql_url: str) -> Iterator[tuple[TestClient, Engine]]:
    command.upgrade(make_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    with engine.begin() as connection:
        connection.execute(text(
            "TRUNCATE order_item_modifiers, order_items, orders, "
            "product_availability_overrides, product_availability, "
            "business_closures, business_hours, business_settings, "
            "product_modifier_groups, modifier_options, product_variants, "
            "products, modifier_groups, categories RESTART IDENTITY CASCADE"
        ))
    with Session(engine) as session:
        seed_order_dependencies(session)
        organization_id = session.scalar(
            select(Organization.id).where(Organization.slug == "the-guest-house")
        )
        assert organization_id is not None
    app = create_app(postgresql_url)
    owner = principal(
        "orders.read", "orders.fulfill", organization_id=organization_id
    )
    app.dependency_overrides[current_principal] = lambda: owner
    app.dependency_overrides[csrf_principal] = lambda: owner
    with TestClient(app) as client:
        yield client, engine
    engine.dispose()


@pytest.mark.postgresql
def test_owner_active_queue_is_pickup_ordered_and_returns_complete_snapshots(owner_orders_api) -> None:
    client, engine = owner_orders_api
    with Session(engine) as session:
        later = add_order(session, key="later", pickup=local_datetime(12, 0))
        earlier = add_order(session, key="earlier", pickup=local_datetime(11, 0))
        session.commit()
        earlier_id, later_id = earlier.id, later.id

    response = client.get("/api/v1/owner/orders/active")

    assert response.status_code == 200
    assert [value["id"] for value in response.json()] == [earlier_id, later_id]
    assert response.json()[0]["items"][0]["product_name"] == "Latte"
    assert response.json()[0]["customer_email"] == "guest@example.com"


@pytest.mark.postgresql
def test_owner_order_permissions_are_enforced(owner_orders_api) -> None:
    client, _ = owner_orders_api
    app = client.app
    denied = principal()
    app.dependency_overrides[current_principal] = lambda: denied
    app.dependency_overrides[csrf_principal] = lambda: denied

    assert client.get("/api/v1/owner/orders/active").status_code == 403
    assert client.patch("/api/v1/owner/orders/1/fulfillment", json={"status": "completed", "expected_version": 1}).status_code == 403


@pytest.mark.postgresql
def test_paid_order_moves_directly_to_completed_and_history(owner_orders_api) -> None:
    client, engine = owner_orders_api
    with Session(engine) as session:
        order = add_order(session, key="workflow")
        session.commit()
        order_id = order.id

    response = client.patch(
        f"/api/v1/owner/orders/{order_id}/fulfillment",
        json={"status": "completed", "expected_version": 1},
    )
    assert response.status_code == 200
    assert response.json()["fulfillment_status"] == "completed"
    assert response.json()["version"] == 2
    assert response.json()["payment_status"] == "paid"
    assert response.json()["fulfillment_timestamps"]["completed_at"] is not None

    repeated = client.patch(
        f"/api/v1/owner/orders/{order_id}/fulfillment",
        json={"status": "completed", "expected_version": 1},
    )
    assert repeated.status_code == 200
    assert repeated.json()["version"] == 2
    assert repeated.json()["fulfillment_timestamps"]["completed_at"] == (
        response.json()["fulfillment_timestamps"]["completed_at"]
    )

    assert client.get("/api/v1/owner/orders/active").json() == []
    assert client.get("/api/v1/owner/orders/history").json()[0]["id"] == order_id


@pytest.mark.postgresql
def test_completed_paid_order_can_return_to_active_safely(owner_orders_api) -> None:
    client, engine = owner_orders_api
    with Session(engine) as session:
        order = add_order(session, key="return-active", fulfillment=FulfillmentStatus.COMPLETED)
        order.completed_at = datetime.now(timezone.utc)
        order.version = 4
        session.commit()
        order_id = order.id

    response = client.patch(
        f"/api/v1/owner/orders/{order_id}/fulfillment",
        json={"status": "new", "expected_version": 4},
    )
    assert response.status_code == 200
    assert response.json()["fulfillment_status"] == "new"
    assert response.json()["payment_status"] == "paid"
    assert response.json()["version"] == 5
    assert response.json()["fulfillment_timestamps"]["completed_at"] is None

    repeated = client.patch(
        f"/api/v1/owner/orders/{order_id}/fulfillment",
        json={"status": "new", "expected_version": 4},
    )
    assert repeated.status_code == 200
    assert repeated.json()["version"] == 5
    assert [value["id"] for value in client.get("/api/v1/owner/orders/active").json()] == [order_id]
    assert all(value["id"] != order_id for value in client.get("/api/v1/owner/orders/history").json())


@pytest.mark.postgresql
@pytest.mark.parametrize("payment", [OrderStatus.PENDING, OrderStatus.PAYMENT_PENDING, OrderStatus.PAYMENT_FAILED])
def test_unpaid_orders_cannot_be_completed(owner_orders_api, payment) -> None:
    client, engine = owner_orders_api
    with Session(engine) as session:
        order = add_order(session, key=f"unpaid-{payment.value}", payment=payment)
        session.commit()
        order_id = order.id

    response = client.patch(
        f"/api/v1/owner/orders/{order_id}/fulfillment",
        json={"status": "completed", "expected_version": 1},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "payment_required"


@pytest.mark.postgresql
def test_invalid_terminal_and_stale_transitions_are_rejected(owner_orders_api) -> None:
    client, engine = owner_orders_api
    with Session(engine) as session:
        completed = add_order(session, key="completed", fulfillment=FulfillmentStatus.COMPLETED)
        preparing = add_order(session, key="stale", fulfillment=FulfillmentStatus.PREPARING)
        preparing.version = 2
        session.commit()
        completed_id, preparing_id = completed.id, preparing.id

    invalid = client.patch(f"/api/v1/owner/orders/{completed_id}/fulfillment", json={"status": "cancelled", "expected_version": 1})
    stale = client.patch(f"/api/v1/owner/orders/{preparing_id}/fulfillment", json={"status": "completed", "expected_version": 1})
    assert invalid.status_code == 409
    assert invalid.json()["detail"]["code"] == "invalid_fulfillment_transition"
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_order"


@pytest.mark.postgresql
@pytest.mark.parametrize("legacy_status", [FulfillmentStatus.PREPARING, FulfillmentStatus.READY])
def test_legacy_active_states_can_be_completed(owner_orders_api, legacy_status) -> None:
    client, engine = owner_orders_api
    with Session(engine) as session:
        order = add_order(session, key=f"legacy-{legacy_status.value}", fulfillment=legacy_status)
        session.commit()
        order_id = order.id

    response = client.patch(
        f"/api/v1/owner/orders/{order_id}/fulfillment",
        json={"status": "completed", "expected_version": 1},
    )
    assert response.status_code == 200
    assert response.json()["fulfillment_status"] == "completed"
    assert response.json()["payment_status"] == "paid"


@pytest.mark.postgresql
def test_cancellation_is_terminal_and_timestamped(owner_orders_api) -> None:
    client, engine = owner_orders_api
    with Session(engine) as session:
        order = add_order(session, key="cancel")
        session.commit()
        order_id = order.id

    cancelled = client.patch(f"/api/v1/owner/orders/{order_id}/fulfillment", json={"status": "cancelled", "expected_version": 1})
    assert cancelled.status_code == 200
    assert cancelled.json()["fulfillment_timestamps"]["cancelled_at"] is not None
    reopened = client.patch(f"/api/v1/owner/orders/{order_id}/fulfillment", json={"status": "completed", "expected_version": 2})
    assert reopened.status_code == 409
    return_to_active = client.patch(f"/api/v1/owner/orders/{order_id}/fulfillment", json={"status": "new", "expected_version": 2})
    assert return_to_active.status_code == 409


@pytest.mark.postgresql
def test_dashboard_uses_paid_orders_only(owner_orders_api) -> None:
    client, engine = owner_orders_api
    with Session(engine) as session:
        add_order(session, key="paid-new")
        add_order(session, key="paid-ready", fulfillment=FulfillmentStatus.READY)
        add_order(session, key="waiting", payment=OrderStatus.PAYMENT_PENDING)
        add_order(session, key="failed", payment=OrderStatus.PAYMENT_FAILED)
        session.commit()

    summary = client.get("/api/v1/owner/orders/summary")
    assert summary.status_code == 200
    assert summary.json()["active_paid"] == 2
    assert summary.json()["waiting_for_payment"] == 1
    assert summary.json()["today_paid_count"] == 2
    assert summary.json()["today_paid_revenue_cents"] == 2260
    assert summary.json()["currency"] == "CAD"
