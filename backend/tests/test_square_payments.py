"""Square provider (PR 1): config, OAuth connect, checkout, verified webhooks, refresh."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.v1.owner_auth import current_principal
from app.api.v1.tenant_context import authenticated_owner_tenant
from app.jds_auth.service import AuthPrincipal
from app.orders.constants import OrderStatus
from app.orders.models import Order
from app.payments.adapters.square_adapter import SquarePaymentProvider
from app.payments.models import OrganizationPaymentSettings, PaymentEvent
from app.payments.service import ensure_provider_selected, is_payment_connected
from app.square.client import SquareApiError, SquareClient, SquareTokenPair
from app.square.config import SquareSettings
from app.square.models import SquareInstallation
from app.square.security import (
    InvalidSquareSignature,
    SquareTokenCipher,
    square_signature,
    verify_square_signature,
)
from app.square.service import active_access_token
from app.tenancy.resolver import LADELS_ORGANIZATION_ID
from tests.test_order_service import LADELS_TENANT
from tests.test_orders_api import order_payload, orders_api  # noqa: F401

WEBHOOK_KEY = "square-webhook-signature-key-test"


def _square_env(monkeypatch) -> str:
    key = Fernet.generate_key().decode()
    for name, value in {
        "JDS_SQUARE_APPLICATION_ID": "sandbox-sq0idb-test",
        "JDS_SQUARE_APPLICATION_SECRET": "sandbox-sq0csb-test-secret",
        "JDS_SQUARE_WEBHOOK_SIGNATURE_KEY": WEBHOOK_KEY,
        "JDS_SQUARE_TOKEN_ENCRYPTION_KEY": key,
        "JDS_SQUARE_STATE_SECRET": "q" * 48,
        "JDS_SQUARE_ENVIRONMENT": "sandbox",
        "PUBLIC_APP_URL": "https://api.example.test",
        "FRONTEND_URL": "https://shop.example.test",
    }.items():
        monkeypatch.setenv(name, value)
    return key


def _clear_square_env(monkeypatch) -> None:
    for name in (
        "JDS_SQUARE_APPLICATION_ID", "JDS_SQUARE_APPLICATION_SECRET", "JDS_SQUARE_WEBHOOK_SIGNATURE_KEY",
        "JDS_SQUARE_TOKEN_ENCRYPTION_KEY", "JDS_SQUARE_STATE_SECRET", "JDS_SQUARE_ENVIRONMENT",
        "JDS_SQUARE_WEBHOOK_URL",
    ):
        monkeypatch.delenv(name, raising=False)


def _reset_square(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE square_oauth_states, square_installations, payment_events"))
        connection.execute(text("DELETE FROM organization_payment_settings"))


def _install(engine, key: str, *, expires_in: timedelta = timedelta(days=30), location: str | None = "LOC1"):
    cipher = SquareTokenCipher(key)
    with Session(engine) as session, session.begin():
        ensure_provider_selected(session, LADELS_ORGANIZATION_ID, "square")
        session.add(SquareInstallation(
            id=uuid4(), organization_id=LADELS_ORGANIZATION_ID, environment="sandbox",
            merchant_id="MERCHANT1", application_id="sandbox-sq0idb-test", location_id=location,
            currency="CAD", access_token_encrypted=cipher.encrypt("access-old"),
            refresh_token_encrypted=cipher.encrypt("refresh-1"),
            access_token_expires_at=datetime.now(timezone.utc) + expires_in,
        ))


def _new_order(client, engine, ids) -> Order:
    created = client.post("/api/v1/orders", json=order_payload(ids)).json()
    with Session(engine, expire_on_commit=False) as session, session.begin():
        order = session.scalar(select(Order).where(Order.public_access_token == created["public_token"]))
        order.expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    return order


def _signed_post(client, payload: dict, key: str = WEBHOOK_KEY):
    body = json.dumps(payload).encode()
    sig = square_signature(body, "https://api.example.test/api/v1/square/webhooks", key)
    return client.post(
        "/api/v1/square/webhooks", content=body,
        headers={"content-type": "application/json", "x-square-hmacsha256-signature": sig},
    )


def _payment_event(order_ref: str, *, event_id: str = "evt-1", status: str = "COMPLETED") -> dict:
    return {
        "merchant_id": "MERCHANT1", "type": "payment.updated", "event_id": event_id,
        "data": {"type": "payment", "id": "PAY1", "object": {"payment": {
            "id": "PAY1", "order_id": order_ref, "status": status,
        }}},
    }


# --- configuration / signature -------------------------------------------------

def test_square_is_inert_without_configuration(monkeypatch) -> None:
    _clear_square_env(monkeypatch)
    assert SquareSettings.from_env().is_configured is False


def test_sandbox_requires_sandbox_application_id(monkeypatch) -> None:
    _square_env(monkeypatch)
    monkeypatch.setenv("JDS_SQUARE_APPLICATION_ID", "sq0idp-production-id")
    assert SquareSettings.from_env().is_configured is False
    monkeypatch.setenv("JDS_SQUARE_ENVIRONMENT", "production")
    assert SquareSettings.from_env().is_configured is True
    assert SquareSettings.from_env().api_base_url == "https://connect.squareup.com"


def test_square_signature_verification() -> None:
    body = b'{"a":1}'
    url = "https://api.example.test/api/v1/square/webhooks"
    verify_square_signature(body, square_signature(body, url, "k"), url, "k")
    with pytest.raises(InvalidSquareSignature):
        verify_square_signature(body, square_signature(body, url, "other"), url, "k")
    with pytest.raises(InvalidSquareSignature):
        verify_square_signature(body + b" ", square_signature(body, url, "k"), url, "k")
    with pytest.raises(InvalidSquareSignature):
        verify_square_signature(body, None, url, "k")


def test_authorization_url_requests_payment_scopes(monkeypatch) -> None:
    _square_env(monkeypatch)
    url = SquareClient(SquareSettings.from_env()).authorization_url("STATE")
    parsed = urlparse(url)
    assert parsed.netloc == "connect.squareupsandbox.com"
    query = parse_qs(parsed.query)
    assert query["client_id"] == ["sandbox-sq0idb-test"]
    assert "PAYMENTS_WRITE" in query["scope"][0]
    assert query["redirect_uri"] == ["https://api.example.test/api/v1/square/oauth/callback"]


# --- DB-backed flows ---------------------------------------------------------

@pytest.mark.postgresql
def test_webhook_route_is_unavailable_when_unconfigured(orders_api, monkeypatch) -> None:
    _clear_square_env(monkeypatch)
    client, engine, _ = orders_api
    response = client.post("/api/v1/square/webhooks", content=b"{}")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "square_not_configured"


@pytest.mark.postgresql
def test_oauth_connect_stores_encrypted_tokens_and_selects_square(orders_api, monkeypatch) -> None:
    key = _square_env(monkeypatch)
    client, engine, _ = orders_api
    _reset_square(engine)
    owner = AuthPrincipal(
        user_id=uuid4(), membership_id=uuid4(), organization_id=LADELS_ORGANIZATION_ID,
        application_id=uuid4(), session_id=uuid4(), email="owner@example.com", display_name="Owner",
        role="owner", permissions=frozenset({"integrations.manage"}), assurance_level="aal1",
    )
    client.app.dependency_overrides[current_principal] = lambda: owner
    client.app.dependency_overrides[authenticated_owner_tenant] = lambda: LADELS_TENANT
    monkeypatch.setattr(SquareClient, "exchange_code", lambda self, code: SquareTokenPair(
        access_token="plain-access", refresh_token="plain-refresh",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30), merchant_id="MERCHANT1",
    ))
    monkeypatch.setattr(SquareClient, "list_locations", lambda self, token: [
        {"id": "CLOSED", "status": "INACTIVE"},
        {"id": "LOC1", "status": "ACTIVE", "currency": "CAD", "capabilities": ["CREDIT_CARD_PROCESSING"]},
    ])
    try:
        start = client.get("/api/v1/square/oauth/start", follow_redirects=False)
        assert start.status_code == 302
        state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        # Missing cookie → rejected.
        bad = client.get(f"/api/v1/square/oauth/callback?code=c&state={state}", follow_redirects=False)
        assert bad.status_code == 400
        cookie = {"cookie": f"jds_square_oauth_state={state}"}
        done = client.get(f"/api/v1/square/oauth/callback?code=c&state={state}", headers=cookie,
                          follow_redirects=False)
        assert done.status_code == 302
        assert done.headers["location"] == "https://shop.example.test/admin?square=connected"
        # State is single-use.
        replay = client.get(f"/api/v1/square/oauth/callback?code=c&state={state}", headers=cookie,
                            follow_redirects=False)
        assert replay.headers["location"].endswith("square=error")
        # Denied on Square → nothing stored, friendly redirect.
        denied = client.get("/api/v1/square/oauth/callback?error=access_denied", follow_redirects=False)
        assert denied.headers["location"].endswith("square=cancelled")
        status_body = client.get("/api/v1/square/connection").json()
        assert status_body["connected"] is True
        assert status_body["merchant_id_hint"] == "…ANT1"
    finally:
        client.app.dependency_overrides.pop(current_principal, None)
        client.app.dependency_overrides.pop(authenticated_owner_tenant, None)
    with Session(engine) as session:
        installation = session.scalar(select(SquareInstallation))
        assert installation.location_id == "LOC1"
        assert "plain-access" not in installation.access_token_encrypted
        assert SquareTokenCipher(key).decrypt(installation.access_token_encrypted) == "plain-access"
        assert session.get(OrganizationPaymentSettings, LADELS_ORGANIZATION_ID).provider_key == "square"
        assert is_payment_connected(session, LADELS_ORGANIZATION_ID) is True


@pytest.mark.postgresql
def test_checkout_creates_one_payment_link_for_exact_total(orders_api, monkeypatch) -> None:
    key = _square_env(monkeypatch)
    client, engine, ids = orders_api
    _reset_square(engine)
    _install(engine, key)
    order = _new_order(client, engine, ids)
    calls: list[dict] = []

    def fake_link(self, token, payload):
        assert token == "access-old"
        calls.append(payload)
        return {"id": "LINK1", "url": "https://square.link/u/abc", "order_id": "SQORDER1"}

    monkeypatch.setattr(SquareClient, "create_payment_link", fake_link)
    first = client.post(f"/api/v1/payments/orders/{order.public_access_token}/checkout")
    assert first.status_code == 200, first.text
    assert first.json() == {
        "provider": "square", "checkout_url": "https://square.link/u/abc",
        "checkout_session_id": "SQORDER1", "expires_at": first.json()["expires_at"],
    }
    second = client.post(f"/api/v1/payments/orders/{order.public_access_token}/checkout")
    assert second.status_code == 200
    assert len(calls) == 1  # reused, never a second Square order
    quick = calls[0]["quick_pay"]
    assert quick["price_money"] == {"amount": order.total_cents, "currency": order.currency}
    assert quick["location_id"] == "LOC1"
    assert "payment=success" in calls[0]["checkout_options"]["redirect_url"]
    with Session(engine) as session:
        saved = session.get(Order, order.id)
        assert saved.status == OrderStatus.PAYMENT_PENDING
        assert saved.payment_provider == "square"
        assert saved.clover_checkout_session_id is None


@pytest.mark.postgresql
def test_checkout_rejected_when_square_not_connected(orders_api, monkeypatch) -> None:
    _square_env(monkeypatch)
    client, engine, ids = orders_api
    _reset_square(engine)
    with Session(engine) as session, session.begin():
        ensure_provider_selected(session, LADELS_ORGANIZATION_ID, "square")
    order = _new_order(client, engine, ids)
    response = client.post(f"/api/v1/payments/orders/{order.public_access_token}/checkout")
    assert response.status_code == 503


def _pending_square_order(client, engine, ids, key, monkeypatch) -> Order:
    _install(engine, key)
    order = _new_order(client, engine, ids)
    monkeypatch.setattr(SquareClient, "create_payment_link", lambda self, t, p: {
        "id": "LINK1", "url": "https://square.link/u/abc", "order_id": "SQORDER1"})
    assert client.post(f"/api/v1/payments/orders/{order.public_access_token}/checkout").status_code == 200
    return order


@pytest.mark.postgresql
def test_verified_webhook_marks_paid_once(orders_api, monkeypatch) -> None:
    key = _square_env(monkeypatch)
    client, engine, ids = orders_api
    _reset_square(engine)
    order = _pending_square_order(client, engine, ids, key, monkeypatch)
    fetched: list[str] = []

    def fake_payment(self, token, payment_id):
        fetched.append(payment_id)
        return {"id": payment_id, "order_id": "SQORDER1", "status": "COMPLETED", "location_id": "LOC1",
                "amount_money": {"amount": order.total_cents, "currency": order.currency}}

    monkeypatch.setattr(SquareClient, "get_payment", fake_payment)
    assert _signed_post(client, _payment_event("SQORDER1")).status_code == 200
    assert _signed_post(client, _payment_event("SQORDER1")).status_code == 200  # duplicate delivery
    assert fetched == ["PAY1"]
    with Session(engine) as session:
        saved = session.get(Order, order.id)
        assert saved.status == OrderStatus.PAID
        assert saved.payment_status == "paid"
        assert saved.payment_provider_txn_id == "PAY1"
        events = session.scalars(select(PaymentEvent)).all()
        assert [e.outcome for e in events] == ["paid_transition_applied"]


@pytest.mark.postgresql
def test_webhook_never_trusts_body_amount_or_bad_signature(orders_api, monkeypatch) -> None:
    key = _square_env(monkeypatch)
    client, engine, ids = orders_api
    _reset_square(engine)
    order = _pending_square_order(client, engine, ids, key, monkeypatch)
    monkeypatch.setattr(SquareClient, "get_payment", lambda self, t, pid: {
        "id": pid, "order_id": "SQORDER1", "status": "COMPLETED", "location_id": "LOC1",
        "amount_money": {"amount": 1, "currency": order.currency}})
    assert _signed_post(client, _payment_event("SQORDER1"), key="wrong-key").status_code == 401
    assert _signed_post(client, _payment_event("SQORDER1")).status_code == 200
    with Session(engine) as session:
        assert session.get(Order, order.id).status == OrderStatus.PAYMENT_PENDING
        assert session.scalar(select(PaymentEvent.outcome)) == "amount_mismatch"


@pytest.mark.postgresql
def test_status_check_endpoint_marks_paid_from_square_order(orders_api, monkeypatch) -> None:
    key = _square_env(monkeypatch)
    client, engine, ids = orders_api
    _reset_square(engine)
    order = _pending_square_order(client, engine, ids, key, monkeypatch)
    monkeypatch.setattr(SquareClient, "get_order", lambda self, t, oid: {
        "id": oid, "tenders": [{"id": "T1", "payment_id": "PAY9"}]})
    monkeypatch.setattr(SquareClient, "get_payment", lambda self, t, pid: {
        "id": pid, "order_id": "SQORDER1", "status": "COMPLETED", "location_id": "LOC1",
        "amount_money": {"amount": order.total_cents, "currency": order.currency}})
    response = client.post(f"/api/v1/square/orders/{order.public_access_token}/refresh")
    assert response.status_code == 200, response.text
    assert response.json()["paid"] is True


@pytest.mark.postgresql
def test_token_refresh_and_reconnect_required(orders_api, monkeypatch) -> None:
    key = _square_env(monkeypatch)
    _, engine, _ = orders_api
    _reset_square(engine)
    _install(engine, key, expires_in=timedelta(days=2))
    settings = SquareSettings.from_env()
    monkeypatch.setattr(SquareClient, "refresh_access_token", lambda self, rt: SquareTokenPair(
        access_token="access-new", refresh_token=rt,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30), merchant_id="MERCHANT1"))
    with Session(engine) as session, session.begin():
        installation = session.scalar(select(SquareInstallation))
        assert active_access_token(session, settings, installation) == "access-new"
        assert SquareTokenCipher(key).decrypt(installation.access_token_encrypted) == "access-new"
        installation.access_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    def rejected(self, rt):
        raise SquareApiError("no", code="square_unauthorized", status_code=401)

    monkeypatch.setattr(SquareClient, "refresh_access_token", rejected)
    from app.square.service import SquareNotConnected
    with Session(engine) as session:
        installation = session.scalar(select(SquareInstallation))
        with pytest.raises(SquareNotConnected):
            active_access_token(session, settings, installation)
        session.commit()
    with Session(engine) as session:
        assert session.scalar(select(SquareInstallation.connection_state)) == "reconnect_required"
        status_ = SquarePaymentProvider().connection_status(session, LADELS_ORGANIZATION_ID)
        assert status_.connected is False and status_.health == "reconnect_required"


@pytest.mark.postgresql
def test_launch_readiness_and_owner_summary_accept_square(orders_api, monkeypatch) -> None:
    from app.platform.readiness import evaluate_storefront_readiness, payment_provider_summary, square_available

    key = _square_env(monkeypatch)
    _, engine, _ = orders_api
    _reset_square(engine)
    with Session(engine) as session:
        assert payment_provider_summary(session, LADELS_ORGANIZATION_ID) == {
            "selectedProvider": None, "squareHealth": "disconnected"}
    _install(engine, key)
    with Session(engine) as session:
        assert square_available() is True
        assert evaluate_storefront_readiness(session, LADELS_ORGANIZATION_ID).checks["payment_connected"] is True
        assert payment_provider_summary(session, LADELS_ORGANIZATION_ID) == {
            "selectedProvider": "square", "squareHealth": "healthy"}
    _clear_square_env(monkeypatch)
    with Session(engine) as session:
        assert square_available() is False
        assert payment_provider_summary(session, LADELS_ORGANIZATION_ID)["squareHealth"] is None
        # Square chosen but platform not set up → not ready (fails closed).
        assert evaluate_storefront_readiness(session, LADELS_ORGANIZATION_ID).checks["payment_connected"] is False
