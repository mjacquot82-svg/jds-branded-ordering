from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException, Response

import app.api.v1.clover as clover_api
from app.api.v1.clover import (
    _checkout_payload,
    _hosted_checkout_session_id,
    _masked_identifier,
    _parse_clover_checkout_expiration,
    _installation_health,
    _verify_payment_evidence,
)
from app.clover.models import CloverInstallation
from app.clover.client import CloverApiError, CloverClient
from app.clover.config import CloverConfigurationError, CloverSettings
from app.clover.security import (
    InvalidWebhookSignature,
    InvalidOAuthState,
    TokenCipher,
    create_oauth_state,
    verify_oauth_state,
    verify_webhook_signature,
)
from app.orders.models import Order, OrderItem, OrderItemModifier


def settings(**overrides: str) -> CloverSettings:
    values = {
        "app_id": "app-id",
        "app_secret": "app-secret",
        "token_encryption_key": Fernet.generate_key().decode(),
        "state_secret": "s" * 48,
        "webhook_secret": "w" * 48,
        "public_app_url": "https://api.example.com",
        "frontend_url": "https://shop.example.com",
        "merchant_id": "merchant-id",
        "environment": "sandbox",
    }
    values.update(overrides)
    return CloverSettings(**values)


def test_clover_settings_expose_registered_callback_and_environment_hosts() -> None:
    config = settings()
    config.validate()

    assert config.callback_url == (
        "https://api.example.com/api/v1/clover/oauth/callback"
    )
    assert config.launch_url == "https://api.example.com/api/v1/clover/oauth/start"
    assert config.authorize_base_url == "https://sandbox.dev.clover.com"
    assert config.api_base_url == "https://apisandbox.dev.clover.com"
    assert config.platform_api_base_url == "https://apisandbox.dev.clover.com"
    assert config.hosted_checkout_base_url == "https://apisandbox.dev.clover.com"
    assert config.ecommerce_service_base_url == "https://scl-sandbox.dev.clover.com"
    assert config.tokenization_base_url == "https://token-sandbox.dev.clover.com"

    production = settings(environment="production")
    production.validate()
    assert production.authorize_base_url == "https://www.clover.com"
    assert production.platform_api_base_url == "https://api.clover.com"
    assert production.hosted_checkout_base_url == "https://api.clover.com"
    assert production.ecommerce_service_base_url == "https://scl.clover.com"
    assert production.tokenization_base_url == "https://token.clover.com"


def test_production_requires_oauth_while_sandbox_private_token_is_intentional() -> None:
    sandbox = settings(ecommerce_private_token="sandbox-private-token")
    sandbox.validate()
    assert sandbox.credential_source == "sandbox_private_token"

    with pytest.raises(CloverConfigurationError, match="requires OAuth"):
        settings(
            environment="production",
            ecommerce_private_token="must-not-be-used",
        ).validate()
    with pytest.raises(CloverConfigurationError, match="sandbox or production"):
        settings(environment="staging").validate()


def test_clover_diagnostic_identifiers_are_safely_masked() -> None:
    assert _masked_identifier("ABCD12345678WXYZ") == "ABCD...WXYZ"
    assert _masked_identifier("app-id") == "******"
    assert _masked_identifier(None) is None


def test_clover_checkout_expiration_accepts_iso_8601_and_milliseconds() -> None:
    expected = datetime(2026, 8, 5, 23, 5, 34, 367000, tzinfo=timezone.utc)

    assert _parse_clover_checkout_expiration("2026-08-05T23:05:34.367Z") == expected
    assert _parse_clover_checkout_expiration(1_785_971_134_367) == expected
    assert _parse_clover_checkout_expiration("1785971134367") == expected


def test_hosted_checkout_webhook_accepts_current_and_legacy_session_fields() -> None:
    assert _hosted_checkout_session_id(
        {"checkoutSessionId": "current-session", "data": "legacy-session"}
    ) == "current-session"
    assert _hosted_checkout_session_id(
        {"checkout_session_id": "snake-session"}
    ) == "snake-session"
    assert _hosted_checkout_session_id({"data": "legacy-session"}) == "legacy-session"
    assert _hosted_checkout_session_id({"Data": "legacy-session"}) == "legacy-session"


def test_clover_settings_reject_insecure_public_urls() -> None:
    with pytest.raises(CloverConfigurationError, match="HTTPS"):
        settings(frontend_url="http://shop.example.com").validate()
    with pytest.raises(CloverConfigurationError, match="without credentials"):
        settings(frontend_url="https://shop.example.com/path").validate()
    with pytest.raises(CloverConfigurationError, match="without credentials"):
        settings(frontend_url="https://shop.example.com/").validate()
    with pytest.raises(CloverConfigurationError, match="Fernet"):
        settings(token_encryption_key="not-a-key").validate()


def test_oauth_state_is_signed_and_expires() -> None:
    state = create_oauth_state("secret", now=100)
    verify_oauth_state(state, "secret", now=200)

    with pytest.raises(InvalidOAuthState):
        verify_oauth_state(state, "different-secret", now=200)
    with pytest.raises(InvalidOAuthState, match="expired"):
        verify_oauth_state(state, "secret", now=701)


def test_token_cipher_round_trip() -> None:
    cipher = TokenCipher(Fernet.generate_key().decode())
    encrypted = cipher.encrypt("sensitive-token")

    assert encrypted != "sensitive-token"
    assert cipher.decrypt(encrypted) == "sensitive-token"


def test_connection_health_distinguishes_expiry_and_reconnect_states() -> None:
    now = datetime(2026, 8, 18, tzinfo=timezone.utc)
    installation = CloverInstallation(
        merchant_id="merchant-id",
        environment="sandbox",
        app_id="app-id",
        access_token_encrypted="encrypted-access",
        refresh_token_encrypted="encrypted-refresh",
        access_token_expires_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        refresh_token_expires_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
        connection_state="connected",
    )
    assert _installation_health(None, now=now) == "disconnected"
    assert _installation_health(installation, now=now) == "healthy"
    installation.access_token_expires_at = datetime(2026, 8, 18, 12, tzinfo=timezone.utc)
    assert _installation_health(installation, now=now) == "expiring"
    installation.access_token_expires_at = datetime(2026, 8, 18, 0, 1, tzinfo=timezone.utc)
    assert _installation_health(installation, now=now) == "refresh_required"
    installation.connection_state = "reconnect_required"
    assert _installation_health(installation, now=now) == "reconnect_required"


def test_payment_evidence_requires_identity_approval_amount_currency_and_session() -> None:
    order = _configured_coffee_order(variant="12oz", modifiers=[], price_cents=500)
    order.clover_checkout_session_id = "checkout-session"
    payment = {
        "id": "payment-id",
        "result": "SUCCESS",
        "amount": order.total_cents,
        "currency": "CAD",
        "checkoutSessionId": "checkout-session",
    }
    assert _verify_payment_evidence(
        payment,
        payment_id="payment-id",
        order=order,
        require_session_identity=True,
    ) == ("SUCCESS", order.total_cents, "CAD")

    for field, value, message in (
        ("id", "other-payment", "identity"),
        ("result", "DECLINED", "not approved"),
        ("amount", order.total_cents + 1, "amount"),
        ("currency", "USD", "currency"),
        ("checkoutSessionId", "other-session", "session identity"),
    ):
        invalid = {**payment, field: value}
        with pytest.raises(ValueError, match=message):
            _verify_payment_evidence(
                invalid,
                payment_id="payment-id",
                order=order,
                require_session_identity=True,
            )


def test_hosted_checkout_webhook_signature() -> None:
    import hashlib
    import hmac

    body = b'{"status":"APPROVED"}'
    signature = hmac.new(
        b"webhook-secret", b"100." + body, hashlib.sha256
    ).hexdigest()
    verify_webhook_signature(
        body,
        f"t=100,v1={signature}",
        "webhook-secret",
        now=200,
    )
    with pytest.raises(InvalidWebhookSignature, match="expired"):
        verify_webhook_signature(
            body,
            f"t=100,v1={signature}",
            "webhook-secret",
            now=401,
        )


def test_oauth_authorization_and_token_exchange_contract() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "access_token": "access",
                "access_token_expiration": 2_000_000_000,
                "refresh_token": "refresh",
                "refresh_token_expiration": 2_100_000_000,
            },
        )

    client = CloverClient(
        settings(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    authorization_url = urlparse(client.authorization_url("signed-state"))
    query = parse_qs(authorization_url.query)

    assert authorization_url.netloc == "sandbox.dev.clover.com"
    assert query["client_id"] == ["app-id"]
    assert query["response_type"] == ["code"]
    assert query["state"] == ["signed-state"]
    assert query["redirect_uri"] == [
        "https://api.example.com/api/v1/clover/oauth/callback"
    ]

    tokens = client.exchange_code("authorization-code")
    assert tokens.access_token == "access"
    assert tokens.refresh_token == "refresh"
    assert tokens.expires_at == datetime.fromtimestamp(
        2_000_000_000, tz=timezone.utc
    )
    assert tokens.refresh_expires_at == datetime.fromtimestamp(
        2_100_000_000, tz=timezone.utc
    )
    assert requests[0].url.path == "/oauth/v2/token"
    assert requests[0].headers["content-type"] == "application/json"


def test_hosted_checkout_uses_server_side_bearer_token() -> None:
    captured: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return httpx.Response(
            200,
            json={
                "href": "https://checkout.clover.test/session",
                "checkoutSessionId": "session-id",
            },
        )

    client = CloverClient(
        settings(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    response = client.create_checkout(
        access_token="private-token",
        merchant_id="merchant-id",
        payload={"customer": {}, "shoppingCart": {"lineItems": []}},
    )

    assert response["checkoutSessionId"] == "session-id"
    assert captured is not None
    assert captured.headers["authorization"] == "Bearer private-token"
    assert captured.headers["x-clover-merchant-id"] == "merchant-id"
    assert captured.url.host == "apisandbox.dev.clover.com"


def test_payment_reconciliation_lookup_uses_platform_api() -> None:
    captured: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return httpx.Response(
            200,
            json={"id": "payment-id", "result": "SUCCESS", "amount": 565},
        )

    client = CloverClient(
        settings(environment="production"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    payment = client.get_payment(
        access_token="oauth-token",
        merchant_id="merchant-id",
        payment_id="payment-id",
    )

    assert payment["amount"] == 565
    assert captured is not None
    assert captured.url.host == "api.clover.com"
    assert captured.url.path == "/v3/merchants/merchant-id/payments/payment-id"


def test_merchant_tax_rates_uses_oauth_bearer_token_and_returns_diagnostics() -> None:
    captured: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return httpx.Response(
            200,
            headers={"X-Request-Id": "tax-request-123"},
            json={
                "elements": [
                    {"id": "tax-id", "name": "HST", "rate": 1_300_000}
                ]
            },
        )

    client = CloverClient(
        settings(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    data, upstream_status, upstream_headers = client.get_merchant_tax_rates(
        access_token="oauth-access-token",
        merchant_id="merchant-id",
    )

    assert data["elements"][0]["rate"] == 1_300_000
    assert upstream_status == 200
    assert upstream_headers["x-request-id"] == "tax-request-123"
    assert captured is not None
    assert captured.method == "GET"
    assert captured.url.path == "/v3/merchants/merchant-id/tax_rates"
    assert captured.headers["authorization"] == "Bearer oauth-access-token"


def test_tax_rates_diagnostic_returns_clover_error_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        clover_api,
        "_active_credential",
        lambda *_: ("merchant-id", "oauth-access-token"),
    )

    def rejected(*_: object, **__: object) -> tuple[dict, int, dict[str, str]]:
        raise CloverApiError(
            "Clover tax rates request failed (403).",
            code="clover_rejected_request",
            upstream_status=403,
            upstream_response_body={"message": "Forbidden"},
            upstream_response_headers={"x-correlation-id": "correlation-123"},
        )

    monkeypatch.setattr(CloverClient, "get_merchant_tax_rates", rejected)

    with pytest.raises(HTTPException) as captured:
        clover_api.debug_clover_tax_rates(
            response=Response(),
            session=type(
                "EmptySession",
                (),
                {"scalar": lambda *_: None},
            )(),
            settings=settings(ecommerce_private_token="private-token"),
            _=object(),
        )

    assert captured.value.status_code == 502
    assert captured.value.detail == {
        "code": "clover_rejected_request",
        "credential_diagnostic": {
            "credential_source": "CLOVER_ECOMMERCE_PRIVATE_TOKEN",
            "configured_app_id_masked": "******",
            "persisted_installation_app_id_masked": None,
            "merchant_id_masked": "merc...t-id",
            "token_refreshed": False,
            "stored_expiration": None,
            "current_utc_time": captured.value.detail["credential_diagnostic"][
                "current_utc_time"
            ],
        },
        "upstream_status": 403,
        "response_body": {"message": "Forbidden"},
        "request_id": "correlation-123",
    }


def test_clover_network_failures_and_insecure_checkout_urls_are_rejected() -> None:
    def network_failure(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("internal detail")

    unavailable = CloverClient(
        settings(),
        http_client=httpx.Client(transport=httpx.MockTransport(network_failure)),
    )
    with pytest.raises(CloverApiError, match="Unable to reach Clover") as captured:
        unavailable.exchange_code("code")
    assert captured.value.code == "clover_unreachable"
    assert captured.value.upstream_status is None

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    timed_out = CloverClient(
        settings(),
        http_client=httpx.Client(transport=httpx.MockTransport(timeout)),
    )
    with pytest.raises(CloverApiError) as timeout_error:
        timed_out.create_checkout(
            access_token="private-token",
            merchant_id="merchant-id",
            payload={},
        )
    assert timeout_error.value.code == "clover_timeout"
    assert timeout_error.value.timeout_information == {
        "exception_type": "ReadTimeout",
        "method": "POST",
        "phase": "read",
        "production_timeout_seconds": {
            "connect": 5,
            "pool": 15,
            "read": 15,
            "write": 15,
        },
        "url_host": "apisandbox.dev.clover.com",
        "url_path": "/invoicingcheckoutservice/v1/checkouts",
    }


def test_clover_rejection_preserves_safe_upstream_diagnostics() -> None:
    rejected = CloverClient(
        settings(),
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    401,
                    headers={
                        "Authorization": "Bearer response-secret",
                        "X-Request-Id": "clover-request-123",
                    },
                    json={
                        "code": "AUTH-401",
                        "message": "Hosted Checkout rejected private@example.test for Jessie Guest.",
                        "customer": {
                            "email": "private@example.test",
                            "firstName": "Jessie",
                            "lastName": "Guest",
                            "phoneNumber": "+1 613-555-0199",
                        },
                        "access_token": "response-secret",
                    },
                )
            )
        ),
    )

    with pytest.raises(CloverApiError) as captured:
        rejected.create_checkout(
            access_token="invalid-token",
            merchant_id="merchant-id",
            payload={},
        )

    assert captured.value.code == "clover_rejected_request"
    assert captured.value.upstream_status == 401
    assert captured.value.upstream_error_code == "AUTH-401"
    assert captured.value.upstream_error_message == (
        "Hosted Checkout rejected [REDACTED] for [REDACTED] [REDACTED]."
    )
    assert captured.value.upstream_response_headers == {
        "content-type": "application/json",
        "x-request-id": "clover-request-123"
    }
    assert captured.value.upstream_response_body == {
        "code": "AUTH-401",
        "message": "Hosted Checkout rejected [REDACTED] for [REDACTED] [REDACTED].",
        "customer": "[REDACTED]",
        "access_token": "[REDACTED]",
    }

    insecure = CloverClient(
        settings(),
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    json={
                        "href": "http://checkout.example.test/session",
                        "checkoutSessionId": "session-id",
                    },
                )
            )
        ),
    )
    with pytest.raises(CloverApiError, match="invalid checkout") as invalid_response:
        insecure.create_checkout(
            access_token="token",
            merchant_id="merchant-id",
            payload={},
        )
    assert invalid_response.value.code == "clover_invalid_response"
    assert invalid_response.value.upstream_status == 200
    assert invalid_response.value.upstream_response_body == {
        "href": "http://checkout.example.test/session",
        "checkoutSessionId": "session-id",
    }


def test_checkout_payload_matches_authoritative_total_with_tax() -> None:
    now = datetime.now(timezone.utc)
    order = Order(
        idempotency_key="checkout-payload-key",
        request_fingerprint="a" * 64,
        public_access_token="public-token",
        guest_name="Jessie Guest",
        guest_email="jessie@example.com",
        guest_phone="+15551234567",
        requested_pickup_at=now,
        business_timezone="America/New_York",
        currency="CAD",
        subtotal_cents=500,
        tax_cents=65,
        tax_name="HST",
        tax_rate_millionths=1_300_000,
        total_cents=565,
        expires_at=now,
    )
    order.items.append(
        OrderItem(
            product_slug="coffee",
            product_name="Coffee",
            base_unit_price_cents=250,
            unit_price_cents=250,
            quantity=2,
            line_subtotal_cents=500,
            sort_order=0,
        )
    )

    payload = _checkout_payload(order, settings())
    assert payload["shoppingCart"]["lineItems"][0]["price"] == 250
    assert payload["shoppingCart"]["lineItems"][0]["unitQty"] == 2
    assert payload["shoppingCart"]["lineItems"][0]["taxRates"] == [
        {"name": "HST", "rate": 1_300_000}
    ]
    assert payload["customer"]["lastName"] == "Guest"
    assert "currency" not in payload
    assert "currency" not in payload["shoppingCart"]

    order.total_cents = 564
    with pytest.raises(ValueError, match="does not match"):
        _checkout_payload(order, settings())

    order.total_cents = 565
    order.currency = "USD"
    with pytest.raises(ValueError, match="requires a CAD order"):
        _checkout_payload(order, settings(environment="production"))
    # Historical and intentional sandbox fixtures remain representable.
    assert _checkout_payload(order, settings())["shoppingCart"]["lineItems"]


def _modifier(group: str, option: str, quantity: int, sort_order: int) -> OrderItemModifier:
    return OrderItemModifier(
        modifier_group_key=group.lower().replace(" ", "-"),
        modifier_group_name=group,
        modifier_option_key=option.lower().replace(" ", "-"),
        modifier_option_name=option,
        price_adjustment_cents=0,
        quantity=quantity,
        sort_order=sort_order,
    )


def _configured_coffee_order(
    *, variant: str, modifiers: list[OrderItemModifier], price_cents: int = 205
) -> Order:
    now = datetime.now(timezone.utc)
    tax_cents = round(price_cents * 0.13)
    order = Order(
        idempotency_key=f"configured-{variant}",
        request_fingerprint="b" * 64,
        public_access_token=f"configured-{variant}-token",
        guest_name="Actual Checkout Name",
        guest_email="checkout@example.com",
        guest_phone="+15198816869",
        requested_pickup_at=now,
        business_timezone="America/Toronto",
        currency="CAD",
        subtotal_cents=price_cents,
        tax_cents=tax_cents,
        tax_name="HST",
        tax_rate_millionths=1_300_000,
        total_cents=price_cents + tax_cents,
        expires_at=now,
    )
    order.items.append(OrderItem(
        product_slug="drip-coffee",
        product_name="Drip Coffee",
        variant_key=variant.lower(),
        variant_name=variant,
        base_unit_price_cents=price_cents,
        unit_price_cents=price_cents,
        quantity=1,
        line_subtotal_cents=price_cents,
        sort_order=0,
        modifiers=modifiers,
    ))
    return order


def test_checkout_payload_exposes_complete_grouped_drip_coffee_configuration() -> None:
    order = _configured_coffee_order(
        variant="12oz",
        modifiers=[
            _modifier("Milk", "Whole milk", 1, 0),
            _modifier("Sugar", "Sugar", 2, 1),
        ],
    )

    payload = _checkout_payload(order, settings())
    line_item = payload["shoppingCart"]["lineItems"][0]

    assert line_item["name"] == (
        "12oz Drip Coffee — Milk: Whole milk · Sugar: Sugar x2"
    )
    assert line_item["note"] == "Milk: Whole milk · Sugar: Sugar x2"
    assert line_item["price"] == 205
    assert payload["customer"] == {
        "firstName": "Actual",
        "lastName": "Checkout Name",
        "email": "checkout@example.com",
        "phoneNumber": "+15198816869",
    }
    assert "currency" not in payload


def test_checkout_payload_groups_multiple_flavour_shots_once() -> None:
    order = _configured_coffee_order(
        variant="20oz",
        price_cents=275,
        modifiers=[
            _modifier("Milk", "Oat", 1, 0),
            _modifier("Flavour shots", "Vanilla", 2, 1),
            _modifier("Flavour shots", "Caramel", 1, 2),
        ],
    )

    line_item = _checkout_payload(order, settings())["shoppingCart"]["lineItems"][0]

    assert line_item["note"] == (
        "Milk: Oat · Flavour shots: Vanilla x2, Caramel"
    )
    assert line_item["name"] == (
        "20oz Drip Coffee — Milk: Oat · Flavour shots: Vanilla x2, Caramel"
    )
    assert line_item["price"] == 275


def test_checkout_payload_does_not_manufacture_a_last_name() -> None:
    order = _configured_coffee_order(variant="12oz", modifiers=[])
    order.guest_name = "Prince"

    payload = _checkout_payload(order, settings())

    assert payload["customer"]["firstName"] == "Prince"
    assert "lastName" not in payload["customer"]
