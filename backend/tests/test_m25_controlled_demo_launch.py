"""M2.5 controlled demo launch — safety re-proof + pilot hardening."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from alembic import command
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.jds_auth.config import AuthSettings
from app.jds_auth.foundation import ensure_foundation
from app.jds_auth.models import Organization
from app.jds_auth.provider import InvalidCredentialsError, ProviderAuthentication, ProviderIdentity
from app.platform.commercial import enforce_live_commerce, enforce_not_self_upgrade
from app.platform.demo_limits import (
    DEMO_SIGNUP_IP_MAX,
    captcha_public_config,
    demo_invite_code_required,
    pilot_config_payload,
)
from app.platform.demo_service import (
    DemoFunnelService,
    DemoServiceError,
    enforce_demo_media_limits,
    invite_code_matches,
)
from app.platform.demo_starter import STARTER_CAFE_NAME
from app.platform.models import MediaAsset
from app.api.v1 import demo as demo_api
from tests.test_migrations import make_alembic_config
from tests.test_self_service_demo_funnel import DemoIdentityProvider, _signup


@pytest.fixture
def demo_engine(postgresql_url: str):
    command.upgrade(make_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    yield engine
    engine.dispose()


@pytest.fixture
def demo_settings() -> AuthSettings:
    return AuthSettings(
        supabase_url="https://identity.example.test",
        supabase_publishable_key="publishable",
        supabase_secret_key="secret",
        session_pepper="p" * 48,
        frontend_url="http://test",
        secure_cookies=False,
    )


@pytest.fixture
def demo_ctx(demo_engine, demo_settings):
    provider = DemoIdentityProvider()
    with Session(demo_engine) as session, session.begin():
        ensure_foundation(
            session,
            application_key="jds-commerce",
            application_name="JDS Commerce",
            organization_slug="the-guest-house",
            organization_name="The Guest House",
        )
    return demo_engine, demo_settings, provider


def test_m25_signup_rate_limit_is_pilot_tight():
    assert DEMO_SIGNUP_IP_MAX <= 5


def test_m25_invite_gate_optional_by_default(monkeypatch):
    monkeypatch.delenv("JDS_DEMO_INVITE_CODE", raising=False)
    assert demo_invite_code_required() is False
    assert invite_code_matches(None) is True
    assert captcha_public_config()["enabled"] is False


def test_m25_invite_gate_enforced_when_configured(demo_ctx, monkeypatch):
    engine, settings, provider = demo_ctx
    monkeypatch.setenv("JDS_DEMO_INVITE_CODE", "pilot-secret")
    with Session(engine) as session:
        service = DemoFunnelService(session, settings, provider)
        with pytest.raises(DemoServiceError) as raised:
            service.signup(
                email=f"noinvite-{uuid4().hex[:8]}@example.com",
                password="correct horse battery staple",
                business_name="No Invite Café",
                contact_name="A",
                desired_slug=None,
                now=datetime.now(timezone.utc),
                user_agent="pytest",
                client_id="invite-ip",
                invite_code="wrong",
            )
        assert raised.value.code == "invite_required"
        status, issued = service.signup(
            email=f"invite-{uuid4().hex[:8]}@example.com",
            password="correct horse battery staple",
            business_name="Invite Café",
            contact_name="A",
            desired_slug=None,
            now=datetime.now(timezone.utc),
            user_agent="pytest",
            client_id="invite-ip-2",
            invite_code="pilot-secret",
        )
        assert status == "ready"
        assert issued is not None


def test_m25_returning_enter_reuses_same_workspace(demo_ctx):
    engine, settings, provider = demo_ctx
    email = f"reuse-{uuid4().hex[:8]}@example.com"
    with Session(engine) as session:
        first = _signup(session, settings, provider, email, business="Reuse Café")
        service = DemoFunnelService(session, settings, provider)
        status, second = service.enter(
            email=email,
            password="correct horse battery staple",
            now=datetime.now(timezone.utc),
            user_agent="pytest",
            client_id="reuse-ip",
        )
        assert status == "ready"
        assert second.principal.organization_id == first.principal.organization_id
        orgs = session.scalars(
            select(Organization).where(Organization.commercial_mode == "prospect")
        ).all()
        # Guest House is live; only one prospect for this email path.
        assert sum(1 for org in orgs if org.name == "Reuse Café") == 1


def test_m25_commerce_and_payments_fail_closed(demo_ctx):
    engine, settings, provider = demo_ctx
    with Session(engine) as session:
        issued = _signup(session, settings, provider, f"lock-{uuid4().hex[:8]}@example.com")
        org_id = issued.principal.organization_id
        for action in ("create_order", "checkout", "clover_oauth", "clover_checkout", "invite_staff"):
            with pytest.raises(HTTPException) as raised:
                enforce_live_commerce(session, org_id, action=action)
            assert raised.value.status_code == 403
            assert raised.value.detail["code"] == "demo_commerce_locked"
        with pytest.raises(HTTPException) as raised:
            enforce_not_self_upgrade(session, org_id)
        assert raised.value.detail["code"] == "demo_activation_required"


def test_m25_media_quota_enforced_helper(demo_ctx):
    engine, settings, provider = demo_ctx
    with Session(engine) as session:
        issued = _signup(session, settings, provider, f"media-{uuid4().hex[:8]}@example.com")
        org_id = issued.principal.organization_id
        session.add(
            MediaAsset(
                organization_id=org_id,
                storage_key=f"{org_id}/full.png",
                media_type="image/png",
                purpose="design",
                byte_size=25 * 1024 * 1024,
                width=100,
                height=100,
                checksum="c" * 64,
            )
        )
        session.commit()
        with pytest.raises(HTTPException) as raised:
            enforce_demo_media_limits(session, org_id, incoming_bytes=1)
        assert raised.value.detail["code"] == "demo_media_storage_limit"


def test_m25_pilot_config_payload(monkeypatch):
    monkeypatch.delenv("JDS_DEMO_INVITE_CODE", raising=False)
    monkeypatch.delenv("JDS_DEMO_CAPTCHA_PROVIDER", raising=False)
    payload = pilot_config_payload()
    assert payload["inviteRequired"] is False
    assert payload["noCreditCardToBuild"] is True
    assert payload["jdsSalesTakePercent"] == 0
    assert payload["captcha"]["enabled"] is False


def test_m25_verification_required_payload_shape(demo_ctx):
    engine, settings, provider = demo_ctx

    class Unverified(DemoIdentityProvider):
        def register_user(self, email: str, password: str, redirect_url: str) -> ProviderIdentity:
            identity = super().register_user(email, password, redirect_url)
            self.users[email.strip().lower()] = (
                password,
                ProviderIdentity(identity.issuer, identity.subject, identity.email, False, identity.display_name),
            )
            return self.users[email.strip().lower()][1]

    provider = Unverified()
    with Session(engine) as session:
        service = DemoFunnelService(session, settings, provider)
        status, issued = service.signup(
            email=f"verify-{uuid4().hex[:8]}@example.com",
            password="correct horse battery staple",
            business_name="Verify Café",
            contact_name="V",
            desired_slug=None,
            now=datetime.now(timezone.utc),
            user_agent="pytest",
            client_id="verify-ip-m25",
        )
        assert status == "verification_required"
        assert issued is None


def test_m25_starter_remains_harbor_not_customer(demo_ctx):
    assert STARTER_CAFE_NAME == "Harbor & Hearth Café"
    assert "guest" not in STARTER_CAFE_NAME.lower()
    assert "ladel" not in STARTER_CAFE_NAME.lower()


def test_m25_pricing_endpoint_zero_take(demo_ctx):
    engine, settings, provider = demo_ctx
    with Session(engine) as session:
        payload = demo_api.demo_pricing(session=session)
        assert payload["jdsSalesTakePercent"] == 0
        assert "0%" in payload["disclosure"] or payload["jdsSalesTakePercent"] == 0
