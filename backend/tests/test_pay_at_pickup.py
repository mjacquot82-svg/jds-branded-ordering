"""Pay at pickup + new-order alert email (trial readiness)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.communications import order_alerts
from app.jds_auth.models import JdsUser
from app.orders.constants import FulfillmentStatus, OrderStatus
from app.orders.models import Order
from app.payments.models import OrganizationOrderSettings, PayAtPickupBlock
from app.platform.models import OperationalAuditEvent
from app.tenancy.resolver import LADELS_ORGANIZATION_ID
from tests.test_orders_api import order_payload, orders_api  # noqa: F401
from tests.test_owner_orders import add_order, owner_orders_api  # noqa: F401
from app.api.v1.customer_auth import current_ordering_customer


def _customer_id(client):
    return client.app.dependency_overrides[current_ordering_customer]().user_id


def _settings(engine, *, enabled=True, min_completed=0, max_total=2500, alert="shop@example.test"):
    with Session(engine) as session, session.begin():
        session.execute(delete(PayAtPickupBlock))
        row = session.get(OrganizationOrderSettings, LADELS_ORGANIZATION_ID)
        if row is None:
            row = OrganizationOrderSettings(organization_id=LADELS_ORGANIZATION_ID)
            session.add(row)
        row.pay_at_pickup_enabled = enabled
        row.pay_at_pickup_min_completed_orders = min_completed
        row.pay_at_pickup_max_total_cents = max_total
        row.new_order_alert_email = alert


def _verify(engine, user_id, verified=True):
    with Session(engine) as session, session.begin():
        session.get(JdsUser, user_id).email_verified_at = datetime.now(timezone.utc) if verified else None


def _fresh_order(client, engine, ids, key="pap-order-request-1"):
    created = client.post("/api/v1/orders", json=order_payload(ids, idempotency_key=key))
    assert created.status_code == 201, created.text
    body = created.json()
    with Session(engine) as session, session.begin():
        order = session.scalar(select(Order).where(Order.public_access_token == body["public_token"]))
        order.expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
        order.requested_pickup_at = datetime.now(timezone.utc) + timedelta(minutes=20)
    return body


@pytest.fixture
def sent(monkeypatch):
    messages = []
    monkeypatch.setattr(order_alerts, "email_sender", messages.append)
    return messages


@pytest.mark.postgresql
def test_pay_at_pickup_off_by_default(orders_api, sent) -> None:
    client, engine, ids = orders_api
    with Session(engine) as session, session.begin():
        session.execute(delete(OrganizationOrderSettings))
    body = _fresh_order(client, engine, ids)
    eligibility = client.get("/api/v1/payments/pay-at-pickup/eligibility").json()
    assert eligibility["available"] is False and eligibility["reason"] == "not_offered"
    assert eligibility["max_total_cents"] == 2500 and eligibility["min_completed_orders"] == 1
    response = client.post(f"/api/v1/payments/orders/{body['public_token']}/pay-at-pickup")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "not_offered"
    assert sent == []


@pytest.mark.postgresql
def test_pay_at_pickup_protections(orders_api, sent) -> None:
    client, engine, ids = orders_api
    user_id = _customer_id(client)
    _settings(engine, min_completed=0)
    _verify(engine, user_id, verified=False)
    assert client.get("/api/v1/payments/pay-at-pickup/eligibility").json()["reason"] == "email_not_verified"
    _verify(engine, user_id)
    _settings(engine, min_completed=1)
    assert client.get("/api/v1/payments/pay-at-pickup/eligibility").json()["reason"] == "not_enough_completed_orders"
    _settings(engine, min_completed=0, max_total=100)
    body = _fresh_order(client, engine, ids)
    response = client.post(f"/api/v1/payments/orders/{body['public_token']}/pay-at-pickup")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "order_total_too_high"
    assert client.get("/api/v1/payments/pay-at-pickup/eligibility?total_cents=50").json()["available"] is True


@pytest.mark.postgresql
def test_pay_at_pickup_accept_never_looks_electronically_paid_and_alerts(orders_api, sent) -> None:
    client, engine, ids = orders_api
    user_id = _customer_id(client)
    _verify(engine, user_id)
    _settings(engine, min_completed=0, max_total=100000)
    body = _fresh_order(client, engine, ids)
    response = client.post(f"/api/v1/payments/orders/{body['public_token']}/pay-at-pickup")
    assert response.status_code == 200, response.text
    assert response.json()["payment_status"] == "manual_unpaid"
    again = client.post(f"/api/v1/payments/orders/{body['public_token']}/pay-at-pickup")
    assert again.status_code == 200
    with Session(engine) as session:
        order = session.scalar(select(Order).where(Order.public_access_token == body["public_token"]))
        assert order.status == OrderStatus.PAYMENT_PENDING
        assert order.payment_status == "manual_unpaid"
        assert order.payment_provider is None and order.payment_provider_txn_id is None
        assert order.expires_at > order.requested_pickup_at
    assert len(sent) == 1  # idempotent retry does not resend
    assert sent[0].to == "shop@example.test"
    assert "PAY AT PICKUP" in sent[0].text and "pay at pickup" in sent[0].subject


@pytest.mark.postgresql
def test_alert_failure_never_breaks_the_order(orders_api, monkeypatch) -> None:
    client, engine, ids = orders_api
    _verify(engine, _customer_id(client))
    _settings(engine, min_completed=0, max_total=100000)

    def boom(_message):
        raise RuntimeError("provider down")

    monkeypatch.setattr(order_alerts, "email_sender", boom)
    body = _fresh_order(client, engine, ids)
    response = client.post(f"/api/v1/payments/orders/{body['public_token']}/pay-at-pickup")
    assert response.status_code == 200


def test_alert_skips_when_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("JDS_ORDER_ALERT_RESEND_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        order_alerts._resend_sender(order_alerts.AlertEmail(to="a@b.c", subject="s", text="t"))


@pytest.mark.postgresql
def test_staff_mark_paid_and_no_show(owner_orders_api) -> None:
    client, engine = owner_orders_api
    owner_id = client.app.dependency_overrides[
        __import__("app.api.v1.owner_auth", fromlist=["csrf_principal"]).csrf_principal
    ]().user_id
    customer_id = uuid4()
    with Session(engine) as session, session.begin():
        session.execute(delete(PayAtPickupBlock))
        session.add_all([
            JdsUser(id=owner_id, primary_email=f"owner-{owner_id}@example.test", display_name="Owner", status="active"),
            JdsUser(id=customer_id, primary_email=f"c-{customer_id}@example.test", display_name="C", status="active",
                    email_verified_at=datetime.now(timezone.utc)),
        ])
        session.flush()
        ids = []
        for key in ("pap-paid-0001", "pap-noshow-001"):
            order = add_order(session, key=key, payment=OrderStatus.PAYMENT_PENDING)
            order.payment_status = "manual_unpaid"
            order.payment_provider_metadata = {"method": "pay_at_pickup"}
            order.customer_user_id = customer_id
            ids.append(order.id)
        online = add_order(session, key="online-paid-1")
        online_id = online.id

    active = {o["id"]: o for o in client.get("/api/v1/owner/orders/active").json()}
    assert active[ids[0]]["payment_method"] == "pay_at_pickup"
    assert active[ids[0]]["pay_at_pickup_unpaid"] is True
    assert active[online_id]["payment_method"] == "online"

    # cannot complete before collecting payment
    blocked = client.patch(f"/api/v1/owner/orders/{ids[0]}/fulfillment", json={"status": "completed", "expected_version": 1})
    assert blocked.status_code == 409
    stale = client.post(f"/api/v1/owner/orders/{ids[0]}/mark-paid", json={"expected_version": 9})
    assert stale.status_code == 409
    paid = client.post(f"/api/v1/owner/orders/{ids[0]}/mark-paid", json={"expected_version": 1})
    assert paid.status_code == 200, paid.text
    assert paid.json()["payment_status"] == "paid" and paid.json()["pay_at_pickup_unpaid"] is False
    done = client.patch(f"/api/v1/owner/orders/{ids[0]}/fulfillment", json={"status": "completed", "expected_version": 2})
    assert done.status_code == 200
    assert client.post(f"/api/v1/owner/orders/{online_id}/no-show", json={"expected_version": 1}).status_code == 409

    no_show = client.post(f"/api/v1/owner/orders/{ids[1]}/no-show", json={"expected_version": 1})
    assert no_show.status_code == 200, no_show.text
    assert no_show.json()["fulfillment_status"] == "cancelled"
    with Session(engine) as session:
        paid_order = session.get(Order, ids[0])
        assert paid_order.payment_provider is None and paid_order.payment_provider_txn_id is None
        assert session.scalar(select(PayAtPickupBlock).where(PayAtPickupBlock.customer_user_id == customer_id)) is not None
        actions = set(session.scalars(select(OperationalAuditEvent.action).where(
            OperationalAuditEvent.target_id.in_([str(i) for i in ids]))))
        assert {"order.pay_at_pickup.collected", "order.pay_at_pickup.no_show"} <= actions
        from app.payments.pay_at_pickup import check_eligibility
        session.merge(OrganizationOrderSettings(organization_id=LADELS_ORGANIZATION_ID, pay_at_pickup_enabled=True,
                                                pay_at_pickup_min_completed_orders=0, pay_at_pickup_max_total_cents=2500))
        session.flush()
        assert check_eligibility(session, LADELS_ORGANIZATION_ID, customer_id, total_cents=100).reason == "blocked_after_no_show"
        session.rollback()


@pytest.mark.postgresql
def test_owner_order_settings_round_trip(owner_orders_api) -> None:
    from app.api.v1.owner_auth import csrf_principal, current_principal
    client, engine = owner_orders_api
    base = client.app.dependency_overrides[csrf_principal]()
    from dataclasses import replace
    manager = replace(base, permissions=frozenset({"orders.read", "availability.manage"}))
    client.app.dependency_overrides[csrf_principal] = lambda: manager
    client.app.dependency_overrides[current_principal] = lambda: manager
    with Session(engine) as session, session.begin():
        session.execute(delete(OrganizationOrderSettings))
    assert client.get("/api/v1/owner/order-settings").json() == {
        "pay_at_pickup_enabled": False, "pay_at_pickup_min_completed_orders": 1,
        "pay_at_pickup_max_total_cents": 2500, "new_order_alert_email": None,
    }
    bad = client.put("/api/v1/owner/order-settings", json={"pay_at_pickup_enabled": True, "new_order_alert_email": "nope"})
    assert bad.status_code == 422
    saved = client.put("/api/v1/owner/order-settings", json={
        "pay_at_pickup_enabled": True, "pay_at_pickup_min_completed_orders": 2,
        "pay_at_pickup_max_total_cents": 3000, "new_order_alert_email": "orders@shop.test",
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()["pay_at_pickup_min_completed_orders"] == 2
    with Session(engine) as session, session.begin():
        session.execute(delete(OrganizationOrderSettings))


@pytest.mark.postgresql
def test_pay_at_pickup_satisfies_payment_readiness_without_clover(orders_api, monkeypatch) -> None:
    from app.platform.readiness import clover_available, evaluate_storefront_readiness

    _client, engine, _ids = orders_api
    for name in ("CLOVER_APP_ID", "CLOVER_APP_SECRET"):
        monkeypatch.delenv(name, raising=False)
    assert clover_available() is False
    _settings(engine, enabled=False)
    with Session(engine) as session:
        before = evaluate_storefront_readiness(session, LADELS_ORGANIZATION_ID).checks["payment_connected"]
    _settings(engine, enabled=True)
    with Session(engine) as session:
        assert evaluate_storefront_readiness(session, LADELS_ORGANIZATION_ID).checks["payment_connected"] is True
    with Session(engine) as session, session.begin():
        session.execute(delete(OrganizationOrderSettings))
    assert before in (True, False)
