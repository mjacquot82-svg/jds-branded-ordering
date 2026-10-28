"""M1 payment provider abstraction — required scenarios."""

from __future__ import annotations

from types import SimpleNamespace

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.clover.config import CloverSettings
from app.clover.models import CloverInstallation
from app.clover.security import InvalidWebhookSignature
from app.jds_auth.models import Organization
from app.orders.constants import OrderStatus
from app.orders.models import Order
from app.payments.errors import ProviderNotConfiguredError, UnsupportedProviderError
from app.payments.models import OrganizationPaymentSettings
from app.payments.order_payment import (
    PAYMENT_STATUS_MANUAL,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_UNPAID,
    assert_not_false_paid,
    mark_electronically_paid,
)
from app.payments.port import CheckoutSession, ConnectionStatus, PaymentProvider
from app.payments.registry import SUPPORTED_PROVIDERS, get_provider, resolve_provider_key
from app.payments.service import (
    ensure_provider_selected,
    is_payment_connected,
    resolve_tenant_provider_key,
)
from app.platform.readiness import evaluate_storefront_readiness
from tests.test_orders_api import order_payload, orders_api  # noqa: F401
from tests.test_jds_auth import auth_client, auth_engine, auth_settings, fake_provider  # noqa: F401


def _clover_env(monkeypatch, **extra: str) -> str:
    key = Fernet.generate_key().decode()
    for name, value in {
        "CLOVER_APP_ID": "shared-platform-app",
        "CLOVER_APP_SECRET": "platform-secret",
        "CLOVER_TOKEN_ENCRYPTION_KEY": key,
        "CLOVER_STATE_SECRET": "s" * 48,
        "CLOVER_WEBHOOK_SECRET": "w" * 48,
        "PUBLIC_APP_URL": "https://api.example.test",
        "FRONTEND_URL": "https://shop.example.test",
        "CLOVER_ENVIRONMENT": "sandbox",
        **extra,
    }.items():
        monkeypatch.setenv(name, value)
    return key


def test_only_clover_is_enabled_provider() -> None:
    assert SUPPORTED_PROVIDERS == frozenset({"clover"})
    assert get_provider("clover").key == "clover"


def test_unsupported_provider_fails_closed_no_clover_fallback() -> None:
    with pytest.raises(UnsupportedProviderError) as caught:
        get_provider("stripe")
    assert caught.value.code == "payment_provider_unsupported"
    with pytest.raises(UnsupportedProviderError):
        resolve_provider_key("square")
    with pytest.raises(UnsupportedProviderError):
        resolve_provider_key("moneris")
    with pytest.raises(UnsupportedProviderError):
        resolve_provider_key("")


def test_second_provider_registration_path_is_port_only() -> None:
    class FakeSquare:
        key = "square"

        def connection_status(self, session, organization_id):
            return ConnectionStatus(connected=True, provider="square", display_hint="Square connected", health="healthy")

        def create_checkout(self, session, order, *, return_urls=None):
            return CheckoutSession(provider="square", provider_ref="sq_chk_1", redirect_url="https://square.example/checkout")

        def reconcile(self, session, order):
            raise NotImplementedError

        def handle_webhook(self, session, *, headers, body):
            return []

        def refund(self, session, order, amount_cents=None):
            raise NotImplementedError

    provider: PaymentProvider = FakeSquare()
    assert provider.key == "square"
    session = provider.create_checkout(None, None)  # type: ignore[arg-type]
    assert session.redirect_url.startswith("https://square.example/")


def test_manual_unpaid_must_never_look_electronically_paid() -> None:
    order = SimpleNamespace(
        status=OrderStatus.PAID,
        payment_status=PAYMENT_STATUS_MANUAL,
        payment_provider_txn_id=None,
    )
    with pytest.raises(ValueError, match="electronically paid"):
        assert_not_false_paid(order)
    order.payment_status = PAYMENT_STATUS_UNPAID
    with pytest.raises(ValueError, match="electronically paid"):
        assert_not_false_paid(order)
    order.payment_status = PAYMENT_STATUS_PAID
    order.payment_provider_txn_id = "pay_abc"
    assert_not_false_paid(order)


def test_mark_electronically_paid_sets_generic_fields() -> None:
    order = SimpleNamespace(
        status=OrderStatus.PAYMENT_PENDING,
        payment_status="pending",
        payment_provider_txn_id=None,
        payment_paid_at=None,
        payment_failure_code="prior",
    )
    mark_electronically_paid(order, provider_txn_ref="pay_123")
    assert order.status == OrderStatus.PAID
    assert order.payment_status == PAYMENT_STATUS_PAID
    assert order.payment_provider_txn_id == "pay_123"
    assert order.payment_paid_at is not None
    assert order.payment_failure_code is None


@pytest.mark.postgresql
def test_missing_provider_settings_fails_closed(orders_api, monkeypatch) -> None:
    """Checkout must not silently use Clover when provider settings are missing."""
    _clover_env(monkeypatch)
    client, engine, ids = orders_api
    with Session(engine) as session, session.begin():
        org_id = session.scalar(select(Organization.id).limit(1))
        session.execute(
            text("DELETE FROM organization_payment_settings WHERE organization_id = CAST(:id AS uuid)"),
            {"id": str(org_id)},
        )
        if session.scalar(select(CloverInstallation).where(CloverInstallation.organization_id == org_id)) is None:
            session.add(
                CloverInstallation(
                    id=uuid4(),
                    organization_id=org_id,
                    merchant_id=f"merchant-{uuid4().hex[:8]}",
                    environment="sandbox",
                    app_id="shared-platform-app",
                    access_token_encrypted="x",
                    refresh_token_encrypted="y",
                    access_token_expires_at=datetime.now(timezone.utc) + timedelta(days=1),
                    connection_state="connected",
                )
            )
        # resolve/checkout fail closed even if a Clover installation exists
        with pytest.raises(ProviderNotConfiguredError):
            resolve_tenant_provider_key(session, org_id)
    created = client.post("/api/v1/orders", json=order_payload(ids)).json()
    response = client.post(f"/api/v1/payments/orders/{created['public_token']}/checkout")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "payment_provider_not_configured"


@pytest.mark.postgresql
def test_unsupported_provider_key_in_settings_fails_closed(orders_api, monkeypatch) -> None:
    _clover_env(monkeypatch)
    _, engine, _ = orders_api
    with Session(engine) as session:
        org_id = session.scalar(select(Organization.id).limit(1))
        ensure_provider_selected(session, org_id, 'clover')
        session.commit()
        session.execute(
            text(
                "UPDATE organization_payment_settings SET provider_key = 'stripe' "
                'WHERE organization_id = CAST(:id AS uuid)'
            ),
            {'id': str(org_id)},
        )
        session.commit()
        row = session.get(OrganizationPaymentSettings, org_id)
        assert row is not None
        assert row.provider_key == 'stripe'
        assert is_payment_connected(session, org_id) is False
        with pytest.raises(UnsupportedProviderError):
            resolve_tenant_provider_key(session, org_id)


@pytest.mark.postgresql
def test_clover_tenant_checkout_via_generic_payments_api(orders_api, monkeypatch) -> None:
    import time
    from app.api.v1.clover import get_settings

    key = _clover_env(
        monkeypatch,
        CLOVER_ECOMMERCE_PRIVATE_TOKEN="legacy-private-token",
        CLOVER_MERCHANT_ID="merchant-payments-m1",
    )
    client, engine, ids = orders_api
    settings = CloverSettings(
        app_id="shared-platform-app",
        app_secret="platform-secret",
        token_encryption_key=key,
        state_secret="s" * 48,
        webhook_secret="w" * 48,
        public_app_url="https://api.example.test",
        frontend_url="https://shop.example.test",
        merchant_id="merchant-payments-m1",
        environment="sandbox",
        ecommerce_private_token="legacy-private-token",
    )
    client.app.dependency_overrides[get_settings] = lambda: settings
    with Session(engine) as session, session.begin():
        org_id = session.scalar(select(Organization.id).limit(1))
        ensure_provider_selected(session, org_id, "clover")
        installation = session.scalar(
            select(CloverInstallation).where(
                CloverInstallation.organization_id == org_id,
                CloverInstallation.environment == "sandbox",
            )
        )
        if installation is None:
            session.add(
                CloverInstallation(
                    id=uuid4(),
                    organization_id=org_id,
                    merchant_id="merchant-payments-m1",
                    environment="sandbox",
                    app_id="shared-platform-app",
                    access_token_encrypted="",
                    refresh_token_encrypted="",
                    access_token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                    connection_state="connected",
                )
            )
        else:
            installation.merchant_id = "merchant-payments-m1"
            installation.connection_state = "connected"
    created = client.post("/api/v1/orders", json=order_payload(ids)).json()
    with Session(engine) as session, session.begin():
        order = session.scalar(select(Order).where(Order.public_access_token == created["public_token"]))
        order.expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    monkeypatch.setattr(
        "app.clover.client.CloverClient.create_checkout",
        lambda *_args, **_kwargs: {
            "href": "https://checkout.example.test/m1",
            "checkoutSessionId": "m1-session",
            "expirationTime": int((time.time() + 900) * 1000),
        },
    )
    response = client.post(f"/api/v1/payments/orders/{created['public_token']}/checkout")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "clover"
    assert body["checkout_session_id"] == "m1-session"
    assert body["checkout_url"] == "https://checkout.example.test/m1"
    with Session(engine) as session:
        order = session.scalar(select(Order).where(Order.public_access_token == created["public_token"]))
        assert order.payment_provider == "clover"
        assert order.payment_checkout_ref == "m1-session"
        assert order.payment_status == "pending"
        assert order.clover_checkout_session_id == "m1-session"
        assert order.status == OrderStatus.PAYMENT_PENDING.value


@pytest.mark.postgresql
def test_generic_checkout_rejects_when_provider_missing(orders_api, monkeypatch) -> None:
    _clover_env(monkeypatch)
    client, engine, ids = orders_api
    with Session(engine) as session, session.begin():
        org_id = session.scalar(select(Organization.id).limit(1))
        session.execute(
            text("DELETE FROM organization_payment_settings WHERE organization_id = CAST(:id AS uuid)"),
            {"id": str(org_id)},
        )
    created = client.post("/api/v1/orders", json=order_payload(ids)).json()
    response = client.post(f"/api/v1/payments/orders/{created['public_token']}/checkout")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "payment_provider_not_configured"


@pytest.mark.postgresql
def test_readiness_exposes_payment_connected_with_clover_alias(orders_api, monkeypatch) -> None:
    _clover_env(monkeypatch)
    _, engine, _ = orders_api
    with Session(engine) as session, session.begin():
        org_id = session.scalar(select(Organization.id).limit(1))
        session.execute(
            text("DELETE FROM organization_payment_settings WHERE organization_id = CAST(:id AS uuid)"),
            {"id": str(org_id)},
        )
        result = evaluate_storefront_readiness(session, org_id)
        assert "payment_connected" in result.checks
        assert "clover" in result.checks
        assert result.checks["payment_connected"] is False
        assert result.checks["clover"] is False


@pytest.mark.postgresql
def test_tenant_payment_settings_are_org_scoped(orders_api, monkeypatch) -> None:
    _clover_env(monkeypatch)
    _, engine, _ = orders_api
    with Session(engine) as session, session.begin():
        a = Organization(id=uuid4(), slug=f"pay-a-{uuid4().hex[:8]}", name="Pay A", is_active=True)
        b = Organization(id=uuid4(), slug=f"pay-b-{uuid4().hex[:8]}", name="Pay B", is_active=True)
        session.add_all([a, b])
        session.flush()
        ensure_provider_selected(session, a.id, "clover")
        assert session.get(OrganizationPaymentSettings, b.id) is None
        with pytest.raises(ProviderNotConfiguredError):
            resolve_tenant_provider_key(session, b.id)
        assert resolve_tenant_provider_key(session, a.id) == "clover"


def test_clover_adapter_webhook_signature_validation(monkeypatch) -> None:
    import hashlib
    import hmac
    import json
    import time
    from app.payments.adapters.clover_adapter import CloverPaymentProvider

    secret = "w" * 48
    _clover_env(monkeypatch, CLOVER_WEBHOOK_SECRET=secret)
    body = json.dumps({"type": "PAYMENT", "status": "APPROVED", "id": "pay1"}).encode()
    provider = CloverPaymentProvider()
    with pytest.raises(InvalidWebhookSignature):
        provider.handle_webhook(None, headers={"Clover-Signature": "t=1,v1=bad"}, body=body)
    timestamp = int(time.time())
    digest = hmac.new(secret.encode(), str(timestamp).encode() + b"." + body, hashlib.sha256).hexdigest()
    events = provider.handle_webhook(None, headers={"Clover-Signature": f"t={timestamp},v1={digest}"}, body=body)
    assert len(events) == 1
    assert events[0].provider == "clover"
    assert events[0].type == "payment.succeeded"
