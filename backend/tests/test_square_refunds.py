"""Owner-initiated full refunds for paid Square orders."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.communications import order_alerts
from app.jds_auth.models import JdsUser
from app.orders.constants import OrderStatus
from app.orders.models import Order
from app.platform.models import OperationalAuditEvent
from app.square.client import SquareApiError, SquareClient
from tests.test_owner_orders import add_order, owner_orders_api  # noqa: F401
from tests.test_square_payments import _install, _reset_square, _square_env


def _owner_user(client, engine) -> None:
    from app.api.v1.owner_auth import csrf_principal

    owner_id = client.app.dependency_overrides[csrf_principal]().user_id
    with Session(engine) as session, session.begin():
        if session.get(JdsUser, owner_id) is None:
            session.add(JdsUser(id=owner_id, primary_email=f"owner-{owner_id}@example.test",
                                display_name="Owner", status="active"))


def _paid_square_order(engine, key: str, *, provider: str = "square") -> int:
    with Session(engine) as session, session.begin():
        order = add_order(session, key=key)
        order.payment_provider = provider
        order.payment_status = "paid"
        order.payment_checkout_ref = "SQORDER1"
        order.payment_provider_txn_id = "PAY1"
        order.payment_provider_metadata = {"environment": "sandbox", "merchant_id": "MERCHANT1"}
        session.flush()
        return order.id


@pytest.fixture
def refund_api(owner_orders_api, monkeypatch):
    client, engine = owner_orders_api
    key = _square_env(monkeypatch)
    _reset_square(engine)
    _install(engine, key)
    _owner_user(client, engine)
    sent: list = []
    monkeypatch.setenv("JDS_ORDER_ALERT_RESEND_API_KEY", "re_test")
    monkeypatch.setenv("JDS_ORDER_ALERT_FROM_EMAIL", "orders@example.test")
    monkeypatch.setattr(order_alerts, "email_sender", sent.append)
    return client, engine, sent


@pytest.mark.postgresql
def test_full_refund_is_idempotent_and_recorded(refund_api, monkeypatch) -> None:
    client, engine, sent = refund_api
    order_id = _paid_square_order(engine, "sq-refund-0001")
    calls: list[dict] = []

    def fake_refund(self, token, payload):
        assert token == "access-old"  # the shop's own decrypted token
        calls.append(payload)
        return {"id": "REFUND1", "status": "PENDING"}

    monkeypatch.setattr(SquareClient, "refund_payment", fake_refund)
    active = {o["id"]: o for o in client.get("/api/v1/owner/orders/active").json()}
    assert active[order_id]["refundable"] is True and active[order_id]["refunded"] is False

    assert client.post(f"/api/v1/owner/orders/{order_id}/refund", json={"expected_version": 9}).status_code == 409
    first = client.post(f"/api/v1/owner/orders/{order_id}/refund", json={"expected_version": 1})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["refunded"] is True and body["refundable"] is False and body["refund_status"] == "pending"
    again = client.post(f"/api/v1/owner/orders/{order_id}/refund", json={"expected_version": 1})
    assert again.status_code == 200 and again.json()["refunded"] is True
    assert len(calls) == 1
    assert calls[0]["payment_id"] == "PAY1"
    assert calls[0]["amount_money"] == {"amount": 1130, "currency": "CAD"}
    assert len(calls[0]["idempotency_key"]) <= 45
    assert len(sent) == 1 and "refunded" in sent[0].subject
    with Session(engine) as session:
        saved = session.get(Order, order_id)
        assert saved.payment_status == "refunded" and saved.status == OrderStatus.PAID
        assert saved.payment_provider_metadata["refund"]["id"] == "REFUND1"
        assert session.scalar(select(OperationalAuditEvent).where(
            OperationalAuditEvent.action == "order.refunded",
            OperationalAuditEvent.target_id == str(order_id))) is not None


@pytest.mark.postgresql
def test_refund_rejections(refund_api, monkeypatch) -> None:
    client, engine, sent = refund_api
    order_id = _paid_square_order(engine, "sq-refund-0002")
    monkeypatch.setattr(SquareClient, "refund_payment",
                        lambda self, t, p: {"id": "R2", "status": "REJECTED"})
    rejected = client.post(f"/api/v1/owner/orders/{order_id}/refund", json={"expected_version": 1})
    assert rejected.status_code == 409 and rejected.json()["detail"]["code"] == "payment_refund_refund_rejected"

    def boom(self, t, p):
        raise SquareApiError("x", code="square_unauthorized", status_code=401)

    monkeypatch.setattr(SquareClient, "refund_payment", boom)
    failed = client.post(f"/api/v1/owner/orders/{order_id}/refund", json={"expected_version": 1})
    assert failed.status_code == 409 and failed.json()["detail"]["code"] == "payment_refund_failed"
    partial = client.post(f"/api/v1/owner/orders/{order_id}/refund", json={"expected_version": 1, "amount_cents": 100})
    assert partial.json()["detail"]["code"] == "payment_partial_refund_unsupported"

    clover_id = _paid_square_order(engine, "clover-refund-1", provider="clover")
    clover = client.post(f"/api/v1/owner/orders/{clover_id}/refund", json={"expected_version": 1})
    assert clover.status_code == 409 and clover.json()["detail"]["code"] == "payment_refund_not_implemented"

    with Session(engine) as session, session.begin():
        unpaid = add_order(session, key="sq-unpaid-0003", payment=OrderStatus.PAYMENT_PENDING)
        unpaid.payment_provider = "square"
        session.flush()
        unpaid_id = unpaid.id
    assert client.post(f"/api/v1/owner/orders/{unpaid_id}/refund", json={"expected_version": 1}).status_code == 409
    assert client.post("/api/v1/owner/orders/999999/refund", json={"expected_version": 1}).status_code == 404
    with Session(engine) as session:
        assert session.get(Order, order_id).payment_status == "paid"
    assert sent == []


def test_refund_requires_fulfill_permission(owner_orders_api) -> None:
    from app.api.v1.owner_auth import csrf_principal, current_principal
    from tests.test_owner_orders import principal

    client, _ = owner_orders_api
    reader = principal("orders.read")
    client.app.dependency_overrides[current_principal] = lambda: reader
    client.app.dependency_overrides[csrf_principal] = lambda: reader
    assert client.post("/api/v1/owner/orders/1/refund", json={"expected_version": 1}).status_code == 403
