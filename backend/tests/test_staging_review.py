from collections.abc import Iterator
from pathlib import Path
import shutil
from uuid import uuid4

import pytest
from alembic import command
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.availability.models import BusinessClosure
from app.jds_auth.models import Membership, Organization
from app.jds_auth.provider import InvalidCredentialsError, StagingReviewIdentityProvider
from app.main import create_app
from app.platform.models import DesignVersion
from app.platform.media import LocalMediaStorage
from app.staging import STAGING_OWNER_EMAIL, assert_staging_seed_safe, validate_staging_media_root
from app.staging_review_seed import seed_staging_review
from tests.test_migrations import make_alembic_config


STAGING_ORIGIN = "https://jds-synthetic-review.netlify.app"


def configure_staging(monkeypatch, database_url: str, media_root: Path) -> None:
    values = {
        "DATABASE_URL": database_url,
        "FRONTEND_URL": STAGING_ORIGIN,
        "PUBLIC_APP_URL": "https://jds-synthetic-review-api.onrender.com",
        "JDS_ENVIRONMENT": "staging",
        "JDS_ENABLE_STAGING_REVIEW": "true",
        "JDS_STAGING_INSTANCE_ID": "jds-synthetic-staging-review-instance",
        "JDS_STAGING_ALLOWED_HOSTS": "jds-synthetic-review.netlify.app",
        "JDS_STAGING_AUTH_PASSWORD": "synthetic-staging-password-123",
        "JDS_STAGING_SEED_CONFIRMATION": "seed-synthetic-staging-review",
        "JDS_AUTH_PROVIDER": "staging-review",
        "JDS_AUTH_SESSION_PEPPER": "synthetic-staging-pepper-0123456789abcdef",
        "JDS_AUTH_SECURE_COOKIES": "true",
        "JDS_APPLICATION_KEY": "jds-commerce-staging-review",
        "JDS_ORGANIZATION_SLUG": "the-guest-house",
        "JDS_LOCAL_MEDIA_ROOT": str(media_root),
        "JDS_PAYMENT_MODE": "fixture-disabled",
        "JDS_OUTBOUND_INTEGRATIONS_ENABLED": "false",
        "PUSH_ENROLLMENT_ENABLED": "false",
        "PUSH_RELEASE_ENABLED": "false",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    for name in (
        "SUPABASE_AUTH_URL", "SUPABASE_AUTH_PUBLISHABLE_KEY", "SUPABASE_AUTH_SECRET_KEY",
        "CLOVER_APP_ID", "CLOVER_APP_SECRET", "CLOVER_ECOMMERCE_PRIVATE_TOKEN",
        "CLOVER_MERCHANT_ID", "CLOVER_TOKEN_ENCRYPTION_KEY", "CLOVER_STATE_SECRET",
        "CLOVER_WEBHOOK_SECRET", "WEB_PUSH_VAPID_PRIVATE_KEY", "WEB_PUSH_VAPID_PUBLIC_KEY",
        "WEB_PUSH_SUBSCRIPTION_ENCRYPTION_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def test_staging_identity_is_fixed_and_has_no_account_side_effects() -> None:
    provider = StagingReviewIdentityProvider(password="synthetic-staging-password-123")
    identity = provider.authenticate_password(STAGING_OWNER_EMAIL, "synthetic-staging-password-123").identity
    assert identity.subject == "jds-staging-review-owner"
    with pytest.raises(InvalidCredentialsError):
        provider.authenticate_password("someone@example.test", "synthetic-staging-password-123")
    with pytest.raises(Exception, match="Registration is unavailable"):
        provider.register_user(STAGING_OWNER_EMAIL, "anything", "https://example.test")
    with pytest.raises(Exception, match="Password recovery is unavailable"):
        provider.request_password_reset(STAGING_OWNER_EMAIL, "https://example.test")
    with pytest.raises(Exception, match="Invitations are unavailable"):
        provider.invite_user("other@example.test", "https://example.test")


def test_production_refuses_staging_and_staging_refuses_production_credentials(monkeypatch, tmp_path) -> None:
    database_url = "postgresql+psycopg://user:pass@db.example.test/jds_staging_review"
    configure_staging(monkeypatch, database_url, tmp_path / "media")
    monkeypatch.setenv("JDS_ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="Production refuses staging"):
        create_app()
    monkeypatch.setenv("JDS_ENVIRONMENT", "staging")
    monkeypatch.setenv("SUPABASE_AUTH_SECRET_KEY", "must-not-be-in-staging")
    with pytest.raises(RuntimeError, match="refuses production"):
        create_app()


def test_staging_seed_and_media_guards_fail_closed(monkeypatch, tmp_path) -> None:
    configure_staging(monkeypatch, "postgresql+psycopg://user:pass@db.example.test/jds_staging_review", tmp_path / "media")
    monkeypatch.setenv("JDS_ENVIRONMENT", "development")
    with pytest.raises(RuntimeError, match="explicit staging"):
        assert_staging_seed_safe("postgresql+psycopg://user:pass@db.example.test/jds_staging_review")
    monkeypatch.setenv("JDS_ENVIRONMENT", "staging")
    with pytest.raises(RuntimeError, match="positively identified"):
        assert_staging_seed_safe("postgresql+psycopg://user:pass@db.example.test/production")
    monkeypatch.setenv("JDS_LOCAL_MEDIA_ROOT", "/tmp/jds-staging-media")
    with pytest.raises(RuntimeError, match="persistent path"):
        validate_staging_media_root()
    safe_root = Path("/var/tmp") / f"jds-staging-media-{uuid4().hex}"
    monkeypatch.setenv("JDS_LOCAL_MEDIA_ROOT", str(safe_root))
    try:
        validated = validate_staging_media_root()
        assert validated == safe_root.resolve()
        storage = LocalMediaStorage(validated)
        organization_id = uuid4()
        media_id = uuid4()
        storage_key, _ = storage.put(organization_id, media_id, b"\x89PNG\r\n\x1a\nsynthetic", "image/png")
        assert LocalMediaStorage(validated).local_path(storage_key).read_bytes().endswith(b"synthetic")
    finally:
        shutil.rmtree(safe_root, ignore_errors=True)


@pytest.fixture
def staging_database(postgresql_url: str, monkeypatch, tmp_path) -> Iterator[str]:
    source = make_url(postgresql_url)
    database = f"jds_{uuid4().hex}_staging_review"
    admin = create_engine(source.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database}"'))
    database_url = source.set(database=database).render_as_string(hide_password=False)
    media_root = Path("/var/tmp") / f"jds-staging-media-{uuid4().hex}"
    configure_staging(monkeypatch, database_url, media_root)
    command.upgrade(make_alembic_config(database_url), "head")
    try:
        yield database_url
    finally:
        with admin.connect() as connection:
            connection.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=:name"), {"name": database})
            connection.execute(text(f'DROP DATABASE "{database}"'))
        admin.dispose()
        shutil.rmtree(media_root, ignore_errors=True)


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_staging_seed_auth_tenants_fixture_payments_and_noindex(staging_database: str, monkeypatch) -> None:
    seed_staging_review(staging_database)
    engine = create_engine(staging_database)
    with Session(engine) as session:
        first = (
            session.scalar(select(func.count()).select_from(Organization)),
            session.scalar(select(func.count()).select_from(Membership)),
            session.scalar(select(func.count()).select_from(DesignVersion)),
            session.scalar(select(func.count()).select_from(BusinessClosure)),
        )
    seed_staging_review(staging_database)
    with Session(engine) as session:
        assert first == (
            session.scalar(select(func.count()).select_from(Organization)),
            session.scalar(select(func.count()).select_from(Membership)),
            session.scalar(select(func.count()).select_from(DesignVersion)),
            session.scalar(select(func.count()).select_from(BusinessClosure)),
        )

    calls = []
    monkeypatch.setattr("app.clover.client.CloverClient.create_checkout", lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr("httpx.Client.request", lambda *args, **kwargs: calls.append((args, kwargs)))
    application = create_app(database_url=staging_database)
    async with AsyncClient(transport=ASGITransport(app=application), base_url=STAGING_ORIGIN) as client:
        guest = await client.get("/api/v1/storefront/bootstrap?review_tenant=the-guest-house")
        second = await client.get("/api/v1/storefront/bootstrap?review_tenant=second-street-cafe")
        assert guest.status_code == second.status_code == 200
        assert guest.json()["tenant"]["id"] != second.json()["tenant"]["id"]
        assert guest.json()["review"] == {"staging": True, "label": "STAGING — NO REAL TRANSACTIONS", "paymentMode": "fixture-disabled"}
        assert "TEST" in guest.json()["business"]["displayName"]
        assert guest.headers["x-robots-tag"] == "noindex, nofollow"
        assert (await client.get("/robots.txt")).text == "User-agent: *\nDisallow: /\n"
        unauthenticated = await client.get("/api/v1/owner/business-profile?review_tenant=second-street-cafe")
        assert unauthenticated.status_code == 401
        login = await client.post(
            "/api/v1/owner/auth/login",
            headers={"Origin": STAGING_ORIGIN},
            json={"email": STAGING_OWNER_EMAIL, "password": "synthetic-staging-password-123"},
        )
        assert login.status_code == 200
        organizations = await client.get("/api/v1/owner/auth/organizations")
        assert {item["organization_slug"] for item in organizations.json()} == {"the-guest-house", "second-street-cafe"}
        selected_before = login.json()["organization_id"]
        owner_hint = await client.get("/api/v1/owner/business-profile?review_tenant=second-street-cafe")
        assert owner_hint.status_code == 200
        refreshed_session = await client.get("/api/v1/owner/auth/session")
        assert refreshed_session.json()["organization_id"] == selected_before
        target = next(item for item in organizations.json() if item["organization_slug"] == "second-street-cafe")
        missing_csrf = await client.post(f'/api/v1/owner/auth/organizations/{target["membership_id"]}/select', headers={"Origin": STAGING_ORIGIN})
        assert missing_csrf.status_code == 403
        switched = await client.post(
            f'/api/v1/owner/auth/organizations/{target["membership_id"]}/select',
            headers={"Origin": STAGING_ORIGIN, "X-CSRF-Token": refreshed_session.json()["csrf_token"]},
        )
        assert switched.status_code == 200
        launch = await client.get("/api/v1/owner/storefront/launch-kit")
        assert launch.status_code == 200
        assert launch.json()["url"] == f"{STAGING_ORIGIN}?review_tenant=second-street-cafe"
        forbidden = await client.post(
            f"/api/v1/owner/auth/organizations/{uuid4()}/select",
            headers={"Origin": STAGING_ORIGIN, "X-CSRF-Token": switched.json()["csrf_token"]},
        )
        assert forbidden.status_code == 403
        oauth = await client.get("/api/v1/clover/oauth/start")
        assert oauth.status_code == 503
        assert oauth.json()["detail"]["code"] == "staging_payments_disabled"
        webhook = await client.post("/api/v1/clover/webhooks/hosted-checkout", headers={"Clover-Signature": "anything"}, content=b"{}")
        assert webhook.status_code == 503
        assert calls == []
    application.state.db_engine.dispose()
    engine.dispose()


@pytest.mark.anyio
async def test_noindex_and_staging_banner_metadata_are_staging_only(monkeypatch) -> None:
    monkeypatch.setenv("JDS_ENVIRONMENT", "production")
    monkeypatch.setenv("JDS_ENABLE_STAGING_REVIEW", "false")
    monkeypatch.setenv("JDS_AUTH_PROVIDER", "supabase")
    application = create_app()
    async with AsyncClient(transport=ASGITransport(app=application), base_url="https://production.example.test") as client:
        live = await client.get("/health/live")
        robots = await client.get("/robots.txt")
        assert live.status_code == 200
        assert "x-robots-tag" not in live.headers
        assert robots.text == "User-agent: *\nAllow: /\n"
