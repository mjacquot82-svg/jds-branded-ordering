from collections.abc import Iterator
import hashlib
import hmac
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from threading import Barrier, Lock
from uuid import uuid4

import pytest
from alembic import command
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from fastapi.responses import Response
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.availability.models import ProductAvailabilityOverride
from app.api.v1.clover import _active_credential, create_hosted_checkout, get_settings
from app.api.v1.customer_auth import current_ordering_customer
from app.api.v1.orders import get_current_time
from app.clover.client import CloverApiError, CloverClient, CloverTokenPair
from app.clover.config import CloverSettings
from app.clover.models import CloverPaymentEvent
from app.clover.models import CloverInstallation
from app.clover.security import TokenCipher
from app.main import create_app
from app.jds_auth.service import AuthPrincipal
from app.jds_auth.models import JdsUser
from app.orders.models import Order
from app.tenancy.resolver import LADELS_ORGANIZATION_ID
from tests.test_migrations import make_alembic_config
from tests.test_order_service import local_datetime, seed_order_dependencies


@pytest.fixture
def orders_api(
    postgresql_url: str,
) -> Iterator[tuple[TestClient, Engine, dict[str, int]]]:
    command.upgrade(make_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE clover_payment_events, clover_installations, "
                "order_item_modifiers, order_items, orders, "
                "product_availability_overrides, product_availability, "
                "business_closures, business_hours, business_settings, "
                "product_modifier_groups, modifier_options, "
                "product_variants, products, modifier_groups, categories "
                "RESTART IDENTITY CASCADE"
            )
        )
    customer = AuthPrincipal(
        user_id=uuid4(), membership_id=uuid4(), organization_id=uuid4(),
        application_id=uuid4(), session_id=uuid4(), email=f"ordering-{uuid4()}@example.com",
        display_name="Ordering Customer", role="customer", permissions=frozenset(),
        assurance_level="aal1",
    )
    with Session(engine, expire_on_commit=False) as session:
        ids = seed_order_dependencies(session)
        session.add(JdsUser(
            id=customer.user_id, primary_email=customer.email,
            display_name=customer.display_name, status="active",
        ))
        session.commit()

    application = create_app(postgresql_url)
    application.dependency_overrides[get_current_time] = lambda: local_datetime(8)
    application.dependency_overrides[current_ordering_customer] = lambda: customer
    with TestClient(application) as client:
        yield client, engine, ids

    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE order_item_modifiers, order_items, orders, "
                "product_availability_overrides, product_availability, "
                "business_closures, business_hours, business_settings, "
                "product_modifier_groups, modifier_options, "
                "product_variants, products, modifier_groups, categories "
                "RESTART IDENTITY CASCADE"
            )
        )
    engine.dispose()


def order_payload(ids: dict[str, int], **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "idempotency_key": "api-order-request-123",
        "customer": {
            "name": "Jessie Guest",
            "email": "jessie@example.com",
            "phone": "+15551234567",
        },
        "requested_pickup_at": local_datetime(8, 30).isoformat(),
        "notes": "Extra hot",
        "lines": [
            {
                "product_id": ids["product"],
                "variant_id": ids["large"],
                "modifier_option_ids": [ids["oat"], ids["vanilla"]],
                "quantity": 2,
            }
        ],
    }
    payload.update(overrides)
    return payload


@pytest.mark.postgresql
def test_create_order_returns_public_pending_snapshot(
    orders_api: tuple[TestClient, Engine, dict[str, int]],
) -> None:
    client, engine, ids = orders_api

    response = client.post("/api/v1/orders", json=order_payload(ids))

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {
        "public_token",
        "status",
        "customer",
        "notes",
        "requested_pickup_at",
        "business_timezone",
        "currency",
        "subtotal_cents",
        "tax_cents",
        "total_cents",
        "expires_at",
        "created_at",
        "updated_at",
        "items",
    }
    assert body["status"] == "pending"
    assert body["currency"] == "CAD"
    assert body["customer"] == {
        "name": "Jessie Guest",
        "email": "jessie@example.com",
        "phone": "+15551234567",
    }
    assert body["subtotal_cents"] == 1620
    assert body["tax_cents"] == 211
    assert body["total_cents"] == 1831
    assert body["items"][0]["variant_key"] == "large"
    assert [modifier["option_key"] for modifier in body["items"][0]["modifiers"]] == [
        "oat",
        "vanilla",
    ]
    assert "id" not in body
    assert "source_product_id" not in body["items"][0]
    assert "idempotency_key" not in body

    with Session(engine) as session:
        assert session.scalar(select(text("count(*)")).select_from(Order)) == 1


@pytest.mark.postgresql
def test_authenticated_order_uses_authoritative_checkout_contact(
    orders_api: tuple[TestClient, Engine, dict[str, int]],
) -> None:
    client, engine, ids = orders_api
    customer_email = f"marc-{uuid4()}@example.com"
    customer = AuthPrincipal(
        user_id=uuid4(), membership_id=uuid4(), organization_id=uuid4(),
        application_id=uuid4(), session_id=uuid4(), email=customer_email,
        display_name="Marc Jacquot", role="customer", permissions=frozenset(),
        assurance_level="aal1",
    )
    with Session(engine) as session:
        session.add(JdsUser(
            id=customer.user_id,
            primary_email=customer.email,
            display_name=customer.display_name,
            status="active",
        ))
        session.commit()
    client.app.dependency_overrides[current_ordering_customer] = lambda: customer
    payload = order_payload(ids, customer={
        "name": "Checkout Customer",
        "email": "checkout@example.com",
        "phone": "+15551234567",
    })

    response = client.post("/api/v1/orders", json=payload)

    assert response.status_code == 201
    assert response.json()["customer"]["name"] == "Checkout Customer"
    assert response.json()["customer"]["email"] == "checkout@example.com"
    with Session(engine) as session:
        order = session.scalar(select(Order))
        assert order is not None
        assert order.guest_name == "Checkout Customer"
        assert order.guest_email == "checkout@example.com"
        assert order.customer_user_id == customer.user_id


@pytest.mark.postgresql
def test_customer_cannot_read_or_checkout_another_customers_order(
    orders_api: tuple[TestClient, Engine, dict[str, int]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, engine, ids = orders_api
    created = client.post("/api/v1/orders", json=order_payload(ids)).json()
    other = AuthPrincipal(
        user_id=uuid4(), membership_id=uuid4(), organization_id=uuid4(),
        application_id=uuid4(), session_id=uuid4(), email="other@example.com",
        display_name="Other Customer", role="customer", permissions=frozenset(),
        assurance_level="aal1",
    )
    with Session(engine) as session:
        session.add(JdsUser(
            id=other.user_id, primary_email=other.email,
            display_name=other.display_name, status="active",
        ))
        session.commit()
    client.app.dependency_overrides[current_ordering_customer] = lambda: other
    settings = CloverSettings(
        app_id="app-id", app_secret="app-secret",
        token_encryption_key=Fernet.generate_key().decode(),
        state_secret="s" * 48, webhook_secret="w" * 48,
        public_app_url="https://api.example.test",
        frontend_url="https://shop.example.test", merchant_id="merchant-id",
        ecommerce_private_token="private-token",
    )
    client.app.dependency_overrides[get_settings] = lambda: settings
    calls = 0

    def external_checkout(*_: object, **__: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {}

    monkeypatch.setattr(CloverClient, "create_checkout", external_checkout)
    assert client.get(f"/api/v1/orders/{created['public_token']}").status_code == 404
    assert client.post(
        f"/api/v1/clover/orders/{created['public_token']}/checkout"
    ).status_code == 404
    assert calls == 0
    client.app.dependency_overrides.pop(get_settings, None)


@pytest.mark.postgresql
def test_scheduling_options_accept_cart_identifiers_and_return_exact_timestamps(
    orders_api: tuple[TestClient, Engine, dict[str, int]],
) -> None:
    client, _, ids = orders_api

    response = client.post(
        "/api/v1/scheduling/options",
        json={
            "lines": [{
                "product_id": ids["product"],
                "variant_id": ids["large"],
                "quantity": 2,
            }],
            "custom_pickup_time": "08:30",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ordering_available"] is True
    assert body["minimum_lead_time_minutes"] == 15
    assert body["pickup_interval_minutes"] == 5
    assert body["maximum_advance_days"] == 14
    assert body["earliest_pickup_at"] == local_datetime(8, 15).isoformat()
    assert body["quick_pickup_options"][0] == {
        "key": "asap",
        "label": "ASAP",
        "requested_pickup_at": local_datetime(8, 15).isoformat(),
        "preference_minutes": None,
    }
    assert body["custom_pickup_at"] == local_datetime(8, 30).isoformat()


@pytest.mark.postgresql
def test_order_creation_rejects_pickup_that_became_stale_after_scheduling(
    orders_api: tuple[TestClient, Engine, dict[str, int]],
) -> None:
    client, engine, ids = orders_api
    schedule = client.post(
        "/api/v1/scheduling/options",
        json={"lines": [{"product_id": ids["product"], "variant_id": ids["large"], "quantity": 1}]},
    ).json()

    with engine.begin() as connection:
        connection.execute(text("UPDATE business_settings SET minimum_lead_time_minutes = 30 WHERE id = 1"))

    response = client.post(
        "/api/v1/orders",
        json=order_payload(
            ids,
            idempotency_key="stale-scheduled-pickup",
            requested_pickup_at=schedule["earliest_pickup_at"],
        ),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "pickup_invalid"


@pytest.mark.postgresql
def test_create_order_replays_idempotently_and_rejects_conflict(
    orders_api: tuple[TestClient, Engine, dict[str, int]],
) -> None:
    client, engine, ids = orders_api
    payload = order_payload(ids)

    first = client.post("/api/v1/orders", json=payload)
    replay = client.post("/api/v1/orders", json=payload)
    conflicting_payload = order_payload(ids)
    conflicting_payload["notes"] = "Different notes"
    conflict = client.post("/api/v1/orders", json=conflicting_payload)

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json() == first.json()
    assert conflict.status_code == 409
    assert conflict.json() == {
        "detail": {
            "code": "idempotency_conflict",
            "message": "Idempotency key was already used for a different order.",
        }
    }
    with Session(engine) as session:
        assert session.scalar(select(text("count(*)")).select_from(Order)) == 1


@pytest.mark.postgresql
def test_create_order_rejects_invalid_customer_and_pickup(
    orders_api: tuple[TestClient, Engine, dict[str, int]],
) -> None:
    client, _, ids = orders_api
    invalid_customer = order_payload(ids)
    invalid_customer["customer"] = {
        "name": "Guest",
        "email": "invalid",
        "phone": "123",
    }

    customer_response = client.post("/api/v1/orders", json=invalid_customer)
    pickup_response = client.post(
        "/api/v1/orders",
        json=order_payload(
            ids,
            idempotency_key="invalid-pickup-request",
            requested_pickup_at=local_datetime(6, 30).isoformat(),
        ),
    )

    assert customer_response.status_code == 422
    assert customer_response.json() == {
        "detail": {
            "code": "request_validation_error",
            "message": "Order request validation failed.",
        }
    }
    assert pickup_response.status_code == 422
    assert pickup_response.json()["detail"]["code"] == "pickup_invalid"


@pytest.mark.postgresql
@pytest.mark.parametrize(
    ("line", "expected_code"),
    [
        (
            {
                "product_id": 999999,
                "variant_id": None,
                "modifier_option_ids": [],
                "quantity": 1,
            },
            "product_not_sellable",
        ),
        (
            {
                "product_id": "product",
                "variant_id": "small",
                "modifier_option_ids": [999999],
                "quantity": 1,
            },
            "modifier_option_invalid",
        ),
    ],
)
def test_create_order_rejects_invalid_products_and_modifiers(
    orders_api: tuple[TestClient, Engine, dict[str, int]],
    line: dict[str, object],
    expected_code: str,
) -> None:
    client, _, ids = orders_api
    resolved_line = {
        key: ids[value] if isinstance(value, str) else value
        for key, value in line.items()
    }

    response = client.post(
        "/api/v1/orders",
        json=order_payload(
            ids,
            idempotency_key=f"invalid-{expected_code}",
            lines=[resolved_line],
        ),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == expected_code


@pytest.mark.postgresql
def test_get_order_by_public_token_and_return_not_found(
    orders_api: tuple[TestClient, Engine, dict[str, int]],
) -> None:
    client, _, ids = orders_api
    created = client.post("/api/v1/orders", json=order_payload(ids))
    token = created.json()["public_token"]

    found = client.get(f"/api/v1/orders/{token}")
    missing = client.get("/api/v1/orders/not-a-real-order-token")

    assert found.status_code == 200
    assert found.json() == created.json()
    assert missing.status_code == 404
    assert missing.json() == {
        "detail": {
            "code": "order_not_found",
            "message": "Pending order was not found.",
        }
    }


@pytest.mark.postgresql
def test_clover_checkout_is_idempotent_and_webhook_state_is_monotonic(
    orders_api: tuple[TestClient, Engine, dict[str, int]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, engine, ids = orders_api
    settings = CloverSettings(
        app_id="app-id",
        app_secret="app-secret",
        token_encryption_key=Fernet.generate_key().decode(),
        state_secret="s" * 48,
        webhook_secret="w" * 48,
        public_app_url="https://api.example.test",
        frontend_url="https://shop.example.test",
        merchant_id="merchant-id",
        ecommerce_private_token="private-token",
    )
    client.app.dependency_overrides[get_settings] = lambda: settings

    created = client.post("/api/v1/orders", json=order_payload(ids)).json()
    with Session(engine) as session:
        order = session.scalar(
            select(Order).where(
                Order.public_access_token == created["public_token"]
            )
        )
        order.expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
        session.commit()

    calls = 0

    def create_checkout(*_: object, **__: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {
            "href": "https://checkout.example.test/session",
            "checkoutSessionId": "checkout-session",
            "expirationTime": int(
                (datetime.now(timezone.utc) + timedelta(minutes=15)).timestamp()
                * 1000
            ),
        }

    monkeypatch.setattr(CloverClient, "create_checkout", create_checkout)
    path = f"/api/v1/clover/orders/{created['public_token']}/checkout"
    first = client.post(path)
    replay = client.post(path)

    assert first.status_code == 200
    assert replay.json() == first.json()
    assert calls == 1
    assert client.get(
        f"/api/v1/orders/{created['public_token']}"
    ).json()["status"] == "payment_pending"

    approved_payload = json.dumps(
        {
            "type": "PAYMENT",
            "status": "APPROVED",
            "merchantId": "merchant-id",
            "data": "checkout-session",
        },
        separators=(",", ":"),
    ).encode()
    timestamp = int(time.time())
    signature = hmac.new(
        settings.webhook_secret.encode(),
        str(timestamp).encode() + b"." + approved_payload,
        hashlib.sha256,
    ).hexdigest()
    approved = client.post(
        "/api/v1/clover/webhooks/hosted-checkout",
        content=approved_payload,
        headers={"Clover-Signature": f"t={timestamp},v1={signature}"},
    )
    assert approved.status_code == 204
    assert client.get(
        f"/api/v1/orders/{created['public_token']}"
    ).json()["status"] == "paid"
    with Session(engine) as session:
        paid_version = session.scalar(select(Order.version).where(
            Order.public_access_token == created["public_token"]
        ))
    duplicate = client.post(
        "/api/v1/clover/webhooks/hosted-checkout",
        content=approved_payload,
        headers={"Clover-Signature": f"t={timestamp},v1={signature}"},
    )
    assert duplicate.status_code == 204
    with Session(engine) as session:
        assert session.scalar(select(Order.version).where(
            Order.public_access_token == created["public_token"]
        )) == paid_version

    declined_payload = approved_payload.replace(b"APPROVED", b"DECLINED")
    declined_signature = hmac.new(
        settings.webhook_secret.encode(),
        str(timestamp).encode() + b"." + declined_payload,
        hashlib.sha256,
    ).hexdigest()
    declined = client.post(
        "/api/v1/clover/webhooks/hosted-checkout",
        content=declined_payload,
        headers={"Clover-Signature": f"t={timestamp},v1={declined_signature}"},
    )
    assert declined.status_code == 204
    assert client.get(
        f"/api/v1/orders/{created['public_token']}"
    ).json()["status"] == "paid"
    assert client.post(path).status_code == 409
    with Session(engine) as session:
        events = list(session.scalars(select(CloverPaymentEvent)).all())
        assert len(events) == 2
        assert events[0].outcome == "paid_transition_applied"
        assert events[0].environment == "sandbox"
    client.app.dependency_overrides.pop(get_settings, None)


@pytest.mark.postgresql
def test_production_webhook_requires_verified_cad_payment_evidence(
    orders_api: tuple[TestClient, Engine, dict[str, int]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, engine, ids = orders_api
    key = Fernet.generate_key().decode()
    sandbox_settings = CloverSettings(
        app_id="sandbox-app", app_secret="sandbox-secret",
        token_encryption_key=key, state_secret="s" * 48,
        webhook_secret="w" * 48, public_app_url="https://api.example.test",
        frontend_url="https://shop.example.test", merchant_id="merchant-id",
        environment="sandbox", ecommerce_private_token="sandbox-private-token",
    )
    client.app.dependency_overrides[get_settings] = lambda: sandbox_settings
    created = client.post("/api/v1/orders", json=order_payload(ids)).json()
    with Session(engine) as session:
        order = session.scalar(select(Order).where(Order.public_access_token == created["public_token"]))
        order.expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
        session.commit()

    monkeypatch.setattr(
        CloverClient,
        "create_checkout",
        lambda *_args, **_kwargs: {
            "href": "https://checkout.example.test/production-evidence",
            "checkoutSessionId": "production-checkout-session",
            "expirationTime": int((time.time() + 900) * 1000),
        },
    )
    assert client.post(
        f"/api/v1/clover/orders/{created['public_token']}/checkout"
    ).status_code == 200

    production_settings = CloverSettings(
        app_id="production-app", app_secret="production-secret",
        token_encryption_key=key, state_secret="p" * 48,
        webhook_secret="q" * 48, public_app_url="https://api.example.test",
        frontend_url="https://shop.example.test", merchant_id="merchant-id",
        environment="production",
    )
    cipher = TokenCipher(key)
    with Session(engine) as session:
        session.add(CloverInstallation(
            merchant_id="merchant-id", environment="production",
            app_id="production-app",
            access_token_encrypted=cipher.encrypt("production-access"),
            refresh_token_encrypted=cipher.encrypt("production-refresh"),
            access_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
            refresh_token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            connection_state="connected",
        ))
        session.commit()
    client.app.dependency_overrides[get_settings] = lambda: production_settings

    payment = {
        "id": "production-payment-id",
        "result": "SUCCESS",
        "amount": created["total_cents"],
        "currency": "CAD",
    }
    monkeypatch.setattr(CloverClient, "get_payment", lambda *_args, **_kwargs: payment)
    payload = json.dumps({
        "type": "PAYMENT", "status": "APPROVED", "merchantId": "merchant-id",
        "data": "production-checkout-session", "id": "production-payment-id",
    }, separators=(",", ":")).encode()
    timestamp = int(time.time())
    signature = hmac.new(
        production_settings.webhook_secret.encode(),
        str(timestamp).encode() + b"." + payload,
        hashlib.sha256,
    ).hexdigest()
    assert client.post(
        "/api/v1/clover/webhooks/hosted-checkout", content=payload,
        headers={"Clover-Signature": f"t={timestamp},v1={signature}"},
    ).status_code == 204
    assert client.get(f"/api/v1/orders/{created['public_token']}").json()["status"] == "paid"

    with Session(engine) as session:
        event = session.scalar(select(CloverPaymentEvent).where(
            CloverPaymentEvent.payment_id == "production-payment-id"
        ))
        assert event is not None
        assert event.verified_amount_cents == created["total_cents"]
        assert event.verified_currency == "CAD"
        assert event.outcome == "paid_transition_applied"
    client.app.dependency_overrides.pop(get_settings, None)


@pytest.mark.postgresql
def test_oauth_refresh_rotation_is_serialized_and_environment_scoped(
    orders_api: tuple[TestClient, Engine, dict[str, int]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, engine, _ = orders_api
    key = Fernet.generate_key().decode()
    config = CloverSettings(
        app_id="sandbox-oauth-app", app_secret="sandbox-secret",
        token_encryption_key=key, state_secret="s" * 48,
        webhook_secret="w" * 48, public_app_url="https://api.example.test",
        frontend_url="https://shop.example.test", merchant_id="merchant-id",
        environment="sandbox",
    )
    cipher = TokenCipher(key)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        session.add_all([
            CloverInstallation(
                merchant_id="merchant-id", environment="sandbox",
                app_id="sandbox-oauth-app",
                access_token_encrypted=cipher.encrypt("expired-access"),
                refresh_token_encrypted=cipher.encrypt("sandbox-refresh"),
                access_token_expires_at=now - timedelta(minutes=1),
                refresh_token_expires_at=now + timedelta(days=30),
                connection_state="connected",
            ),
            CloverInstallation(
                merchant_id="merchant-id", environment="production",
                app_id="production-app",
                access_token_encrypted=cipher.encrypt("production-access"),
                refresh_token_encrypted=cipher.encrypt("production-refresh"),
                access_token_expires_at=now + timedelta(hours=2),
                refresh_token_expires_at=now + timedelta(days=30),
                connection_state="connected",
            ),
        ])
        session.commit()

    calls = 0
    calls_lock = Lock()

    def refresh(*_: object, **__: object) -> CloverTokenPair:
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.1)
        return CloverTokenPair(
            access_token="rotated-access",
            refresh_token="rotated-refresh",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            refresh_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )

    monkeypatch.setattr(CloverClient, "refresh_access_token", refresh)

    def active() -> tuple[str, str]:
        with Session(engine) as session:
            return _active_credential(session, config)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: active(), range(2)))

    assert results == [
        ("merchant-id", "rotated-access"),
        ("merchant-id", "rotated-access"),
    ]
    assert calls == 1
    with Session(engine) as session:
        sandbox = session.scalar(select(CloverInstallation).where(
            CloverInstallation.environment == "sandbox"
        ))
        production = session.scalar(select(CloverInstallation).where(
            CloverInstallation.environment == "production"
        ))
        assert cipher.decrypt(sandbox.refresh_token_encrypted) == "rotated-refresh"
        assert cipher.decrypt(production.access_token_encrypted) == "production-access"


@pytest.mark.postgresql
def test_clover_checkout_failure_preserves_order_and_returns_honest_message(
    orders_api: tuple[TestClient, Engine, dict[str, int]],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, engine, ids = orders_api
    settings = CloverSettings(
        app_id="app-id",
        app_secret="app-secret",
        token_encryption_key=Fernet.generate_key().decode(),
        state_secret="s" * 48,
        webhook_secret="w" * 48,
        public_app_url="https://api.example.test",
        frontend_url="https://shop.example.test",
        merchant_id="merchant-id",
        ecommerce_private_token="private-token",
    )
    client.app.dependency_overrides[get_settings] = lambda: settings
    created = client.post("/api/v1/orders", json=order_payload(ids)).json()
    with Session(engine) as session:
        order = session.scalar(
            select(Order).where(
                Order.public_access_token == created["public_token"]
            )
        )
        assert order is not None
        order.expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
        session.commit()

    def rejected_checkout(*_: object, **__: object) -> dict:
        raise CloverApiError(
            "Clover checkout request failed (401).",
            code="clover_rejected_request",
            upstream_status=401,
            upstream_error_code="AUTH-401",
            upstream_error_message="Hosted Checkout is not authorized.",
            upstream_response_body={
                "code": "AUTH-401",
                "message": "Hosted Checkout is not authorized.",
                "token": "[REDACTED]",
            },
            upstream_response_headers={"x-request-id": "clover-request-123"},
        )

    monkeypatch.setattr(CloverClient, "create_checkout", rejected_checkout)
    response = client.post(
        f"/api/v1/clover/orders/{created['public_token']}/checkout"
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": {
            "code": "clover_rejected_request",
            "message": "Your order was saved, but secure payment could not "
            "be started. Please try payment again.",
        }
    }
    log_message = caplog.messages[-1]
    assert "Clover checkout creation failed" in log_message
    assert '"upstream_http_status": 401' in log_message
    assert '"upstream_error_code": "AUTH-401"' in log_message
    assert '"x-request-id": "clover-request-123"' in log_message
    assert "[REDACTED]" in log_message
    assert "private-token" not in log_message
    with Session(engine) as session:
        order = session.scalar(
            select(Order).where(Order.public_access_token == created["public_token"])
        )
        assert order is not None
        assert order.status == "pending"
        assert order.clover_checkout_session_id is None

    client.app.dependency_overrides.pop(get_settings, None)


@pytest.mark.postgresql
def test_concurrent_clover_checkout_requests_create_one_external_session(
    orders_api: tuple[TestClient, Engine, dict[str, int]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, engine, ids = orders_api
    settings = CloverSettings(
        app_id="app-id",
        app_secret="app-secret",
        token_encryption_key=Fernet.generate_key().decode(),
        state_secret="s" * 48,
        webhook_secret="w" * 48,
        public_app_url="https://api.example.test",
        frontend_url="https://shop.example.test",
        merchant_id="merchant-id",
        ecommerce_private_token="private-token",
    )
    created = client.post("/api/v1/orders", json=order_payload(ids)).json()
    with Session(engine) as session:
        order = session.scalar(
            select(Order).where(
                Order.public_access_token == created["public_token"]
            )
        )
        order.expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
        session.commit()

    barrier = Barrier(2)
    calls = 0
    calls_lock = Lock()

    def external_checkout(*_: object, **__: object) -> dict[str, object]:
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.2)
        return {
            "href": "https://checkout.example.test/session",
            "checkoutSessionId": "concurrent-session",
            "expirationTime": int(
                (datetime.now(timezone.utc) + timedelta(minutes=15)).timestamp()
                * 1000
            ),
        }

    monkeypatch.setattr(CloverClient, "create_checkout", external_checkout)

    def checkout() -> str:
        barrier.wait(timeout=5)
        with Session(engine, expire_on_commit=False) as session:
            result = create_hosted_checkout(
                created["public_token"],
                Response(),
                client.app.dependency_overrides[current_ordering_customer](),
                session,
                settings,
            )
            return result.checkout_session_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: checkout(), range(2)))

    assert results == ["concurrent-session", "concurrent-session"]
    assert calls == 1


@pytest.mark.postgresql
def test_create_order_rejects_unavailable_product(
    orders_api: tuple[TestClient, Engine, dict[str, int]],
) -> None:
    client, engine, ids = orders_api
    with Session(engine) as session:
        session.add(
            ProductAvailabilityOverride(
                organization_id=LADELS_ORGANIZATION_ID,
                product_id=ids["product"],
                business_date=date(2026, 7, 28),
                is_available=False,
                reason="Sold out today",
            )
        )
        session.commit()

    response = client.post(
        "/api/v1/orders",
        json=order_payload(ids),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "product_not_sellable",
        "message": "Sold out today",
    }


def test_order_openapi_documents_contract_and_errors() -> None:
    with TestClient(create_app()) as client:
        schema = client.get("/openapi.json").json()

    post_operation = schema["paths"]["/api/v1/orders"]["post"]
    get_operation = schema["paths"]["/api/v1/orders/{public_token}"]["get"]
    assert post_operation["tags"] == ["orders"]
    assert post_operation["responses"]["201"]
    assert post_operation["responses"]["409"]
    assert post_operation["responses"]["422"]
    assert get_operation["responses"]["200"]
    assert get_operation["responses"]["404"]
