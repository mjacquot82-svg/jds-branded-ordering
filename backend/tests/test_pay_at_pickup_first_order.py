"""Pay at pickup works on a customer's first order, guests included (beta finding t42u)."""

from __future__ import annotations

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.v1.customer_auth import optional_ordering_customer
from app.orders.models import Order
from app.payments.pay_at_pickup import DEFAULT_MIN_COMPLETED_ORDERS, check_eligibility
from app.tenancy.resolver import LADELS_ORGANIZATION_ID
from tests.test_orders_api import order_payload, orders_api  # noqa: F401
from tests.test_pay_at_pickup import _customer_id, _fresh_order, _settings, _verify, sent  # noqa: F401


def test_default_needs_no_completed_orders() -> None:
    assert DEFAULT_MIN_COMPLETED_ORDERS == 0


@pytest.fixture(autouse=True)
def _restore_pay_at_pickup_off(request):
    engine = request.getfixturevalue("orders_api")[1] if "orders_api" in request.fixturenames or "as_guest" in request.fixturenames else None
    yield
    if engine is not None:
        _settings(engine, enabled=False)


@pytest.fixture
def as_guest(orders_api):  # noqa: F811
    client, engine, ids = orders_api
    previous = client.app.dependency_overrides[optional_ordering_customer]
    client.app.dependency_overrides[optional_ordering_customer] = lambda: None
    yield client, engine, ids
    client.app.dependency_overrides[optional_ordering_customer] = previous


@pytest.mark.postgresql
def test_guest_first_order_pay_at_pickup_succeeds(as_guest, sent) -> None:  # noqa: F811
    client, engine, ids = as_guest
    _settings(engine, min_completed=0, max_total=100000)
    eligibility = client.get("/api/v1/payments/pay-at-pickup/eligibility?total_cents=500").json()
    assert eligibility["available"] is True and eligibility["completed_orders"] == 0
    body = _fresh_order(client, engine, ids, key="pap-guest-first-0001")
    response = client.post(f"/api/v1/payments/orders/{body['public_token']}/pay-at-pickup")
    assert response.status_code == 200, response.text
    assert response.json()["payment_status"] == "manual_unpaid"
    with Session(engine) as session:
        order = session.scalar(select(Order).where(Order.public_access_token == body["public_token"]))
        assert order.customer_user_id is None and order.payment_provider is None


@pytest.mark.postgresql
def test_signed_in_first_order_pay_at_pickup_succeeds(orders_api, sent) -> None:  # noqa: F811
    client, engine, ids = orders_api
    _verify(engine, _customer_id(client))
    _settings(engine, min_completed=DEFAULT_MIN_COMPLETED_ORDERS, max_total=100000)
    assert client.get("/api/v1/payments/pay-at-pickup/eligibility").json()["available"] is True
    body = _fresh_order(client, engine, ids, key="pap-signed-first-001")
    response = client.post(f"/api/v1/payments/orders/{body['public_token']}/pay-at-pickup")
    assert response.status_code == 200, response.text


@pytest.mark.postgresql
def test_guest_over_max_total_rejected(as_guest, sent) -> None:  # noqa: F811
    client, engine, ids = as_guest
    _settings(engine, min_completed=0, max_total=100)
    body = _fresh_order(client, engine, ids, key="pap-guest-overmax-01")
    response = client.post(f"/api/v1/payments/orders/{body['public_token']}/pay-at-pickup")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "order_total_too_high"


@pytest.mark.postgresql
def test_signed_in_over_max_total_rejected(orders_api, sent) -> None:  # noqa: F811
    client, engine, ids = orders_api
    _verify(engine, _customer_id(client))
    _settings(engine, min_completed=0, max_total=100)
    body = _fresh_order(client, engine, ids, key="pap-signed-overmax-1")
    response = client.post(f"/api/v1/payments/orders/{body['public_token']}/pay-at-pickup")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "order_total_too_high"


@pytest.mark.postgresql
def test_owner_can_tighten_guests_out(as_guest, sent) -> None:  # noqa: F811
    client, engine, ids = as_guest
    _settings(engine, min_completed=1, max_total=100000)
    assert client.get("/api/v1/payments/pay-at-pickup/eligibility").json()["reason"] == "sign_in_required"
    body = _fresh_order(client, engine, ids, key="pap-guest-tight-0001")
    response = client.post(f"/api/v1/payments/orders/{body['public_token']}/pay-at-pickup")
    assert response.status_code == 403 and response.json()["detail"]["code"] == "sign_in_required"


@pytest.mark.postgresql
def test_guest_no_show_blocks_same_contact(as_guest, sent) -> None:  # noqa: F811
    client, engine, ids = as_guest
    _settings(engine, min_completed=0, max_total=100000)
    body = _fresh_order(client, engine, ids, key="pap-guest-noshow-001")
    with Session(engine) as session, session.begin():
        session.execute(update(Order).where(Order.public_access_token == body["public_token"]).values(
            payment_status="cancelled", payment_provider_metadata={"method": "pay_at_pickup", "no_show": True}))
    with Session(engine) as session:
        result = check_eligibility(session, LADELS_ORGANIZATION_ID, None, total_cents=100,
                                   guest_name="Jessie Guest", guest_email="JESSIE@example.com", guest_phone=None)
        assert result.reason == "blocked_after_no_show"
        missing = check_eligibility(session, LADELS_ORGANIZATION_ID, None, total_cents=100,
                                    guest_name="", guest_email="new@example.com", guest_phone=None)
        assert missing.reason == "guest_contact_required"
        fresh = check_eligibility(session, LADELS_ORGANIZATION_ID, None, total_cents=100,
                                  guest_name="Sam", guest_email=None, guest_phone="+15550000000")
        assert fresh.available is True
