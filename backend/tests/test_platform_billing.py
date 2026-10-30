from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from alembic import command
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.billing import service, square_billing
from app.billing.cockpit import shop_feed, token_ok
from app.billing.models import BillingPayment, ShopBillingAccount
from app.billing.usage import period_of, record_usage
from app.communications import order_alerts
from app.jds_auth.models import Organization
from app.platform.entitlements import entitlement_features
from tests.test_migrations import make_alembic_config

SQUARE_ENV = {
    "JDS_BILLING_SQUARE_ACCESS_TOKEN": "test-token", "JDS_BILLING_SQUARE_APPLICATION_ID": "sandbox-app",
    "JDS_BILLING_SQUARE_LOCATION_ID": "LOC1", "JDS_BILLING_PLAN_VARIATION_STARTER": "VAR_S",
    "JDS_BILLING_PLAN_VARIATION_PLUS": "VAR_P", "JDS_BILLING_PLAN_VARIATION_PRO": "VAR_PRO",
}


class FakeSquare:
    calls: list = []

    def __init__(self, settings):
        self.settings = settings

    def create_customer(self, **kw):
        FakeSquare.calls.append(("customer", kw)); return "CUST1"

    def create_card(self, **kw):
        FakeSquare.calls.append(("card", kw))
        return {"id": "CARD1", "card_brand": "VISA", "last_4": "1111", "exp_month": 12, "exp_year": 2030}

    def create_subscription(self, **kw):
        FakeSquare.calls.append(("subscription", kw)); return {"id": f"SUB-{uuid4().hex}", "start_date": "2026-11-01"}

    def update_subscription(self, subscription_id, **kw):
        FakeSquare.calls.append(("update", kw)); return {}

    def swap_plan(self, subscription_id, **kw):
        FakeSquare.calls.append(("swap", kw)); return {}


@pytest.fixture
def billing_db(postgresql_url, monkeypatch):
    command.upgrade(make_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    with Session(engine) as session:
        shop = Organization(slug=f"bill-{uuid4()}", name="Billing Café", lifecycle_status="active")
        beta = Organization(slug=f"beta-{uuid4()}", name="Beta Café", lifecycle_status="active", billing_exempt=True)
        session.add_all([shop, beta]); session.commit()
        ids = (shop.id, beta.id)
    sent = []
    monkeypatch.setattr(order_alerts, "email_sender", sent.append)
    monkeypatch.setattr(service, "owner_email", lambda session, org: "owner@example.com")
    monkeypatch.setenv("JDS_ORDER_ALERT_RESEND_API_KEY", "x"); monkeypatch.setenv("JDS_ORDER_ALERT_FROM_EMAIL", "contact@example.com")
    monkeypatch.setattr(square_billing, "client_factory", FakeSquare)
    FakeSquare.calls = []
    yield engine, ids, sent
    engine.dispose()


def _on(monkeypatch):
    monkeypatch.setenv("JDS_BILLING_ENABLED", "true")
    for key, value in SQUARE_ENV.items():
        monkeypatch.setenv(key, value)


@pytest.mark.postgresql
def test_billing_off_keeps_everything_free_and_unlocked(billing_db, monkeypatch):
    engine, (shop, _), sent = billing_db
    monkeypatch.delenv("JDS_BILLING_ENABLED", raising=False)
    with Session(engine) as session:
        assert entitlement_features(session, shop)[2]["loyalty"] is True  # legacy pre-billing behaviour unchanged
        features = service.shop_features(session, shop)
        assert features["loyalty"] and features["customerList"] and features["reports"]
        service.enforce_package_feature(session, shop, "staffPins")
        assert service.ordering_paused(session, shop) is False
        view = service.billing_view(session, shop)
        assert view["freeDuringBeta"] is True and view["cardForm"] is None
        with pytest.raises(HTTPException) as off:
            service.save_card_and_subscribe(session, shop, source_id="cnon:x", package_key="plus", actor=None)
        assert off.value.status_code == 409
        assert service.run_billing_sweep(session)["skipped"] is True
    assert FakeSquare.calls == [] and sent == []


@pytest.mark.postgresql
def test_existing_shops_are_marked_exempt_by_migration(postgresql_url):
    command.upgrade(make_alembic_config(postgresql_url), "head")
    command.downgrade(make_alembic_config(postgresql_url), "20261030_37")
    engine = create_engine(postgresql_url)
    from sqlalchemy import text
    slug = f"old-{uuid4()}"
    with engine.begin() as c:
        c.execute(text("INSERT INTO organizations (id, slug, name, is_active) VALUES (gen_random_uuid(), :s, 'Old', true)"), {"s": slug})
    command.upgrade(make_alembic_config(postgresql_url), "head")
    with engine.connect() as c:
        assert c.scalar(text("SELECT billing_exempt FROM organizations WHERE slug=:s"), {"s": slug}) is True
    engine.dispose()


@pytest.mark.postgresql
def test_gating_by_package_only_when_on_and_not_exempt(billing_db, monkeypatch):
    engine, (shop, beta), _ = billing_db
    _on(monkeypatch)
    with Session(engine) as session:
        session.get(Organization, shop).selected_package = "starter"; session.commit()
        with pytest.raises(HTTPException) as denied:
            service.enforce_package_feature(session, shop, "customerList")
        assert denied.value.detail["requiredPackage"] == "plus"
        service.enforce_package_feature(session, beta, "reports")  # exempt beta shop: unlocked
        session.get(Organization, shop).selected_package = "plus"; session.commit()
        service.enforce_package_feature(session, shop, "loyalty")
        with pytest.raises(HTTPException):
            service.enforce_package_feature(session, shop, "reports")
        assert entitlement_features(session, beta)[0] == "exempt"


@pytest.mark.postgresql
def test_subscribe_change_fail_grace_pause_and_resume(billing_db, monkeypatch):
    engine, (shop, beta), sent = billing_db
    _on(monkeypatch)
    now = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
    with Session(engine) as session:
        with pytest.raises(HTTPException):
            service.save_card_and_subscribe(session, beta, source_id="cnon:x", package_key="pro", actor=None)
        acct = service.get_account(session, shop, create=True); acct.extra_locations = 1; session.commit()
        acct = service.save_card_and_subscribe(session, shop, source_id="cnon:card-ok", package_key="plus", actor=None)
        sub = next(kw for name, kw in FakeSquare.calls if name == "subscription")
        assert sub["amount_cents"] == 22500 + 7500 and sub["plan_variation_id"] == "VAR_P"
        assert acct.status == "active" and acct.card_last4 == "1111"
        view = service.billing_view(session, shop)
        assert view["card"]["last4"] == "1111" and view["cardForm"]["locationId"] == "LOC1"
        assert "test-token" not in str(view)

        service.change_package(session, shop, package_key="pro", extra_locations=1, actor=None)
        acct = session.get(ShopBillingAccount, shop)
        assert acct.pending_package_key == "pro" and acct.package_key == "plus"  # next bill
        assert ("swap", {"plan_variation_id": "VAR_PRO"}) in FakeSquare.calls
        sub_id = acct.square_subscription_id

        failed = {"event_id": "ev-fail-1", "type": "invoice.scheduled_charge_failed",
                  "data": {"object": {"invoice": {"id": "inv1", "subscription_id": sub_id}}}}
        assert service.handle_square_event(session, failed, now=now) == "failed"
        assert service.handle_square_event(session, failed, now=now) == "duplicate"
        acct = session.get(ShopBillingAccount, shop)
        assert acct.status == "past_due" and acct.grace_ends_at == now + timedelta(days=7)
        assert len(sent) == 1 and "couldn't charge" in sent[0].text
        assert service.ordering_paused(session, shop, now=now) is False

        assert service.run_billing_sweep(session, now=now + timedelta(days=3))["reminders"] == 1
        assert service.run_billing_sweep(session, now=now + timedelta(days=8))["paused"] == 1
        assert service.ordering_paused(session, shop) is True
        with pytest.raises(HTTPException) as paused:
            service.enforce_ordering_not_paused(session, shop)
        assert paused.value.detail["code"] == "shop_ordering_paused"

        paid = {"event_id": "ev-paid-1", "type": "invoice.payment_made", "data": {"object": {"invoice": {
            "id": "inv1", "subscription_id": sub_id, "payment_requests": [{"total_completed_amount_money": {"amount": 37500}}]}}}}
        assert service.handle_square_event(session, paid, now=now + timedelta(days=9)) == "paid"
        acct = session.get(ShopBillingAccount, shop)
        assert acct.status == "active" and acct.package_key == "pro" and acct.pending_package_key is None
        assert service.ordering_paused(session, shop) is False
        assert session.get(Organization, shop).selected_package == "pro"
        assert "back on" in sent[-1].subject
        assert session.query(BillingPayment).filter_by(organization_id=shop).count() == 2
    assert not any("order" in m.subject.lower() and "new" in m.subject.lower() for m in sent)


@pytest.mark.postgresql
def test_cockpit_feed_is_token_protected_and_counts_usage(billing_db, monkeypatch):
    engine, (shop, beta), _ = billing_db
    monkeypatch.delenv("JDS_COCKPIT_FEED_TOKEN", raising=False)
    assert token_ok("Bearer anything") is False
    monkeypatch.setenv("JDS_COCKPIT_FEED_TOKEN", "feed-secret")
    assert token_ok("Bearer wrong") is False and token_ok("Bearer feed-secret") is True
    with Session(engine) as session:
        session.get(Organization, shop).selected_package = "plus"; session.commit()
        record_usage(session, shop, "emails_sent"); record_usage(session, shop, "emails_sent", 2)
        feed = shop_feed(session, period_of())
        row = next(s for s in feed["shops"] if s["organizationId"] == str(shop))
        assert row["emailsSent"] == 3 and row["textsSent"] == 0 and row["listPriceCents"] == 22500
        assert row["expectedRevenueCents"] == 0  # billing off
        assert {"ordersPlaced", "orderSalesCents", "storageBytes", "activeStaff", "products", "customers"} <= set(row)
        assert "email" not in str(row).replace("emailsSent", "")


from tests.test_orders_api import orders_api  # noqa: E402,F401
from app.square.security import square_signature  # noqa: E402


@pytest.mark.postgresql
def test_http_webhook_signature_and_cockpit_feed_auth(orders_api, monkeypatch):
    client, _, _ = orders_api
    monkeypatch.delenv("JDS_BILLING_WEBHOOK_SIGNATURE_KEY", raising=False)
    assert client.post("/api/v1/billing/square/webhook", content=b"{}").status_code == 503
    url = "https://api.example.test/api/v1/billing/square/webhook"
    monkeypatch.setenv("JDS_BILLING_WEBHOOK_SIGNATURE_KEY", "billing-key"); monkeypatch.setenv("JDS_BILLING_WEBHOOK_URL", url)
    body = b'{"event_id":"e-unknown","type":"invoice.payment_made","data":{"object":{"invoice":{"subscription_id":"nope"}}}}'
    assert client.post("/api/v1/billing/square/webhook", content=body,
                       headers={"x-square-hmacsha256-signature": "bad"}).status_code == 401
    ok = client.post("/api/v1/billing/square/webhook", content=body,
                     headers={"x-square-hmacsha256-signature": square_signature(body, url, "billing-key")})
    assert ok.status_code == 200 and ok.json()["result"] == "unknown_subscription"

    monkeypatch.delenv("JDS_COCKPIT_FEED_TOKEN", raising=False)
    assert client.get("/api/v1/platform/cockpit/feed").status_code == 404
    monkeypatch.setenv("JDS_COCKPIT_FEED_TOKEN", "feed-secret")
    assert client.get("/api/v1/platform/cockpit/feed").status_code == 401
    feed = client.get("/api/v1/platform/cockpit/feed?period=2026-10", headers={"Authorization": "Bearer feed-secret"})
    assert feed.status_code == 200 and feed.json()["period"] == "2026-10"
    assert client.get("/api/v1/platform/cockpit/feed?period=bad", headers={"Authorization": "Bearer feed-secret"}).status_code == 422
