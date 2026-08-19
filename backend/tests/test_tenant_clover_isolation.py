import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.clover import _active_credential, connection_status, get_settings
from app.clover.config import CloverSettings
from app.clover.models import CloverInstallation, CloverPaymentEvent
from app.clover.security import TokenCipher
from app.jds_auth.models import Organization
from app.orders.models import Order
from app.tenancy.context import TenantContext, TenantResolutionSource
from app.tenancy.resolver import LADELS_ORGANIZATION_ID
from tests.test_orders_api import order_payload, orders_api  # noqa: F401
from tests.test_jds_auth import auth_client, auth_engine, auth_settings, fake_provider  # noqa: F401
from tests.test_tenant_auth_isolation import _add_membership, _login


def _settings(*, merchant_id: str = "merchant-a") -> CloverSettings:
    return CloverSettings(
        app_id="shared-platform-app",
        app_secret="platform-secret",
        token_encryption_key=Fernet.generate_key().decode(),
        state_secret="s" * 48,
        webhook_secret="w" * 48,
        public_app_url="https://api.example.test",
        frontend_url="https://shop.example.test",
        merchant_id=merchant_id,
        environment="sandbox",
        ecommerce_private_token="legacy-private-token",
    )


def _tenant(organization_id, slug: str) -> TenantContext:
    return TenantContext(
        organization_id=organization_id,
        organization_slug=slug,
        source=TenantResolutionSource.AUTHENTICATED_MEMBERSHIP,
    )


def _signature(settings: CloverSettings, payload: bytes) -> str:
    timestamp = int(time.time())
    digest = hmac.new(
        settings.webhook_secret.encode(),
        str(timestamp).encode() + b"." + payload,
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_oauth_state_for_a_cannot_install_or_overwrite_b(
    auth_client, auth_engine, monkeypatch,
) -> None:
    for name, value in {
        "CLOVER_APP_ID": "shared-platform-app",
        "CLOVER_APP_SECRET": "platform-secret",
        "CLOVER_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "CLOVER_STATE_SECRET": "s" * 48,
        "CLOVER_WEBHOOK_SECRET": "w" * 48,
        "PUBLIC_APP_URL": "https://api.example.test",
        "FRONTEND_URL": "https://shop.example.test",
    }.items():
        monkeypatch.setenv(name, value)
    login = await _login(auth_client)
    started = await auth_client.get("/api/v1/clover/oauth/start")
    assert started.status_code == 302
    state = parse_qs(urlparse(started.headers["location"]).query)["state"][0]
    membership_b, _ = _add_membership(
        auth_engine, user_email="owner@example.com", slug=f"oauth-b-{uuid4()}"
    )
    selected = await auth_client.post(
        f"/api/v1/owner/auth/organizations/{membership_b}/select",
        headers={"Origin": "http://test", "X-CSRF-Token": login["csrf_token"]},
    )
    assert selected.status_code == 200
    cookies = "; ".join(f"{key}={value}" for key, value in auth_client.cookies.items())
    callback = await auth_client.get(
        "/api/v1/clover/oauth/callback",
        params={"code": "unused-code", "state": state, "merchant_id": "merchant-a"},
        headers={"Cookie": cookies + f"; guesthouse_clover_oauth_state={state}"},
    )
    assert callback.status_code == 403
    with Session(auth_engine) as session:
        assert session.scalar(select(CloverInstallation)) is None


@pytest.mark.postgresql
def test_checkout_and_webhook_resolve_through_exact_tenant_installation(
    orders_api, monkeypatch,
) -> None:
    client, engine, ids = orders_api
    settings = _settings()
    client.app.dependency_overrides[get_settings] = lambda: settings
    created = client.post("/api/v1/orders", json=order_payload(ids)).json()
    with Session(engine) as session, session.begin():
        order = session.scalar(
            select(Order).where(Order.public_access_token == created["public_token"])
        )
        order.expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    monkeypatch.setattr(
        "app.clover.client.CloverClient.create_checkout",
        lambda *_args, **_kwargs: {
            "href": "https://checkout.example.test/a",
            "checkoutSessionId": "deliberately-colliding-session",
            "expirationTime": int((time.time() + 900) * 1000),
        },
    )
    assert client.post(
        f"/api/v1/clover/orders/{created['public_token']}/checkout"
    ).status_code == 200

    with Session(engine) as session, session.begin():
        tenant_b = Organization(slug=f"clover-b-{uuid4()}", name="Clover B")
        session.add(tenant_b)
        session.flush()
        session.add(
            CloverInstallation(
                organization_id=tenant_b.id,
                merchant_id="merchant-b",
                environment="sandbox",
                app_id=settings.app_id,
                access_token_encrypted="b-access",
                refresh_token_encrypted="b-refresh",
                access_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                connection_state="connected",
            )
        )

    wrong = json.dumps(
        {
            "type": "PAYMENT",
            "status": "APPROVED",
            "merchantId": "merchant-b",
            "data": "deliberately-colliding-session",
        },
        separators=(",", ":"),
    ).encode()
    assert client.post(
        "/api/v1/clover/webhooks/hosted-checkout",
        content=wrong,
        headers={"Clover-Signature": _signature(settings, wrong)},
    ).status_code == 204
    assert client.get(
        f"/api/v1/orders/{created['public_token']}"
    ).json()["status"] == "payment_pending"

    unknown = wrong.replace(b"merchant-b", b"unknown-merchant")
    assert client.post(
        "/api/v1/clover/webhooks/hosted-checkout",
        content=unknown,
        headers={"Clover-Signature": _signature(settings, unknown)},
    ).status_code == 204
    assert client.get(
        f"/api/v1/orders/{created['public_token']}"
    ).json()["status"] == "payment_pending"


@pytest.mark.postgresql
def test_installation_order_and_payment_event_constraints_fail_closed(
    orders_api,
) -> None:
    client, engine, ids = orders_api
    settings = _settings()
    client.app.dependency_overrides[get_settings] = lambda: settings
    created = client.post("/api/v1/orders", json=order_payload(ids)).json()
    with Session(engine) as session, session.begin():
        tenant_b = Organization(
            slug=f"clover-constraint-b-{uuid4()}", name="Clover Constraint B"
        )
        session.add(tenant_b)
        session.flush()
        installation_a = CloverInstallation(
            organization_id=LADELS_ORGANIZATION_ID,
            merchant_id="merchant-a",
            environment="sandbox",
            app_id=settings.app_id,
            access_token_encrypted="a-access",
            refresh_token_encrypted="a-refresh",
            access_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            connection_state="connected",
        )
        installation_b = CloverInstallation(
            organization_id=tenant_b.id,
            merchant_id="merchant-b",
            environment="sandbox",
            app_id=settings.app_id,
            access_token_encrypted="b-access",
            refresh_token_encrypted="b-refresh",
            access_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            connection_state="connected",
        )
        session.add_all([installation_a, installation_b])
        session.flush()
        session.add_all([
            CloverPaymentEvent(
                organization_id=LADELS_ORGANIZATION_ID,
                installation_id=installation_a.id,
                environment="sandbox", merchant_id="merchant-a",
                payment_id="colliding-payment", checkout_session_id="same-session",
                source="test", outcome="received",
            ),
            CloverPaymentEvent(
                organization_id=tenant_b.id,
                installation_id=installation_b.id,
                environment="sandbox", merchant_id="merchant-b",
                payment_id="colliding-payment", checkout_session_id="same-session",
                source="test", outcome="received",
            ),
        ])

    with Session(engine) as session:
        order = session.scalar(
            select(Order).where(Order.public_access_token == created["public_token"])
        )
        installation_b = session.scalar(
            select(CloverInstallation).where(CloverInstallation.merchant_id == "merchant-b")
        )
        order.clover_installation_id = installation_b.id
        order.clover_environment = "sandbox"
        order.clover_merchant_id = "merchant-b"
        order.clover_checkout_session_id = "cross-tenant"
        order.clover_checkout_url = "https://checkout.example.test/cross"
        order.clover_checkout_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        with pytest.raises(IntegrityError):
            session.commit()

    with Session(engine) as session:
        installation_a = session.scalar(
            select(CloverInstallation).where(CloverInstallation.merchant_id == "merchant-a")
        )
        session.add(
            CloverPaymentEvent(
                organization_id=LADELS_ORGANIZATION_ID,
                installation_id=installation_a.id,
                environment="sandbox", merchant_id="merchant-a",
                payment_id="colliding-payment", checkout_session_id="other-session",
                source="test", outcome="received",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.postgresql
def test_credentials_and_connection_diagnostics_are_tenant_isolated(
    orders_api,
) -> None:
    _, engine, _ = orders_api
    key = Fernet.generate_key().decode()
    settings = _settings()
    settings = CloverSettings(**{**settings.__dict__, "token_encryption_key": key, "ecommerce_private_token": None})
    cipher = TokenCipher(key)
    with Session(engine) as session, session.begin():
        tenant_b = Organization(
            slug=f"clover-diagnostics-b-{uuid4()}", name="Clover Diagnostics B"
        )
        session.add(tenant_b)
        session.flush()
        tenant_b_id = tenant_b.id
        session.add_all([
            CloverInstallation(
                organization_id=LADELS_ORGANIZATION_ID, merchant_id="merchant-a",
                environment="sandbox", app_id=settings.app_id,
                access_token_encrypted=cipher.encrypt("token-a"),
                refresh_token_encrypted=cipher.encrypt("refresh-a"),
                access_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                connection_state="connected",
            ),
            CloverInstallation(
                organization_id=tenant_b.id, merchant_id="merchant-b",
                environment="sandbox", app_id=settings.app_id,
                access_token_encrypted=cipher.encrypt("token-b"),
                refresh_token_encrypted=cipher.encrypt("refresh-b"),
                access_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                connection_state="connected",
            ),
        ])
    with Session(engine) as session:
        installation_a, token_a = _active_credential(
            session, settings, organization_id=LADELS_ORGANIZATION_ID
        )
        installation_b, token_b = _active_credential(
            session, settings, organization_id=tenant_b_id
        )
        assert (installation_a.merchant_id, token_a) == ("merchant-a", "token-a")
        assert (installation_b.merchant_id, token_b) == ("merchant-b", "token-b")
        diagnostic_a = connection_status(
            session, settings, object(), _tenant(LADELS_ORGANIZATION_ID, "the-guest-house")
        )
        diagnostic_b = connection_status(
            session, settings, object(), _tenant(tenant_b_id, "clover-diagnostics-b")
        )
        assert diagnostic_a.merchant_id != diagnostic_b.merchant_id
