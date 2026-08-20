from collections.abc import Iterator
from uuid import uuid4

import pytest
from alembic import command
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.jds_auth.config import AuthSettings
from app.jds_auth.models import Membership, Organization
from app.jds_auth.provider import DevelopmentIdentityProvider, InvalidCredentialsError, SupabaseIdentityProvider
from app.local_review_seed import assert_safe_local_review, seed_local_review
from app.main import create_app
from app.platform.models import DesignVersion
from tests.test_migrations import make_alembic_config


def test_development_auth_is_fixed_and_rejects_arbitrary_identity() -> None:
    provider = DevelopmentIdentityProvider(
        email="owner@local.jds.test", password="local-review-password",
    )
    identity = provider.authenticate_password(
        "owner@local.jds.test", "local-review-password",
    ).identity
    assert identity.subject == "jds-local-review-owner"
    with pytest.raises(InvalidCredentialsError):
        provider.authenticate_password("attacker@local.jds.test", "local-review-password")


def test_development_auth_refuses_production_activation(monkeypatch) -> None:
    monkeypatch.setenv("JDS_AUTH_PROVIDER", "development")
    monkeypatch.setenv("JDS_ENVIRONMENT", "production")
    monkeypatch.setenv("JDS_ENABLE_LOCAL_REVIEW", "true")
    monkeypatch.setenv("JDS_LOCAL_AUTH_PASSWORD", "local-review-password")
    monkeypatch.setenv("JDS_LOCAL_REVIEW_ORIGIN", "https://synthetic-codespace-5173.app.github.dev")
    monkeypatch.setenv("JDS_LOCAL_REVIEW_PROXY_ORIGIN", "http://localhost:5173")
    with pytest.raises(RuntimeError, match="explicit local development"):
        create_app()


def test_production_provider_selection_remains_supabase(monkeypatch) -> None:
    monkeypatch.setenv("JDS_AUTH_PROVIDER", "supabase")
    settings = AuthSettings(
        supabase_url="https://identity.example.test", supabase_publishable_key="public",
        supabase_secret_key="secret", session_pepper="p" * 48,
        frontend_url="https://store.example.test",
    )
    application = create_app(auth_settings=settings)
    assert isinstance(application.state.auth_provider, SupabaseIdentityProvider)


def test_local_seed_rejects_unsafe_environment_and_database(monkeypatch) -> None:
    monkeypatch.setenv("JDS_ENVIRONMENT", "production")
    monkeypatch.setenv("JDS_ENABLE_LOCAL_REVIEW", "true")
    with pytest.raises(RuntimeError, match="development review mode"):
        assert_safe_local_review("postgresql+psycopg://user:pass@localhost/app_local_review")
    monkeypatch.setenv("JDS_ENVIRONMENT", "development")
    with pytest.raises(RuntimeError, match="localhost database"):
        assert_safe_local_review("postgresql+psycopg://user:pass@db.production.invalid/app_local_review")
    with pytest.raises(RuntimeError, match="ending in _local_review"):
        assert_safe_local_review("postgresql+psycopg://user:pass@localhost/production")


@pytest.fixture
def local_review_database(postgresql_url: str, monkeypatch) -> Iterator[str]:
    source = make_url(postgresql_url)
    database_name = f"jds_{uuid4().hex}_local_review"
    admin_url = source.set(database="postgres")
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    database_url = source.set(database=database_name).render_as_string(hide_password=False)
    monkeypatch.setenv("JDS_ENVIRONMENT", "development")
    monkeypatch.setenv("JDS_ENABLE_LOCAL_REVIEW", "true")
    monkeypatch.setenv("JDS_AUTH_PROVIDER", "development")
    monkeypatch.setenv("JDS_LOCAL_AUTH_EMAIL", "owner@local.jds.test")
    monkeypatch.setenv("JDS_LOCAL_AUTH_PASSWORD", "local-review-password")
    monkeypatch.setenv("JDS_LOCAL_REVIEW_ORIGIN", "https://synthetic-codespace-5173.app.github.dev")
    monkeypatch.setenv("JDS_LOCAL_REVIEW_PROXY_ORIGIN", "http://localhost:5173")
    monkeypatch.setenv("JDS_AUTH_SESSION_PEPPER", "local-review-pepper-0123456789abcdef")
    monkeypatch.setenv("FRONTEND_URL", "http://test")
    command.upgrade(make_alembic_config(database_url), "head")
    try:
        yield database_url
    finally:
        with admin.connect() as connection:
            connection.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=:name"), {"name": database_name})
            connection.execute(text(f'DROP DATABASE "{database_name}"'))
        admin.dispose()


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_local_seed_is_idempotent_and_owner_switching_is_membership_scoped(local_review_database: str, monkeypatch) -> None:
    seed_local_review(local_review_database)
    engine = create_engine(local_review_database)
    with Session(engine) as session:
        first = (
            session.scalar(select(func.count()).select_from(Organization)),
            session.scalar(select(func.count()).select_from(Membership)),
            session.scalar(select(func.count()).select_from(DesignVersion)),
        )
    seed_local_review(local_review_database)
    with Session(engine) as session:
        second = (
            session.scalar(select(func.count()).select_from(Organization)),
            session.scalar(select(func.count()).select_from(Membership)),
            session.scalar(select(func.count()).select_from(DesignVersion)),
        )
    assert second == first

    review_origin = "https://synthetic-codespace-5173.app.github.dev"
    monkeypatch.setenv("JDS_ENVIRONMENT", "production")
    production_app = create_app(
        database_url=local_review_database,
        auth_settings=AuthSettings(
            supabase_url="https://identity.example.test", supabase_publishable_key="public",
            supabase_secret_key="secret", session_pepper="p" * 48,
            frontend_url="http://test", secure_cookies=False,
        ),
        auth_provider=DevelopmentIdentityProvider(
            email="owner@local.jds.test", password="local-review-password",
        ),
    )
    async with AsyncClient(transport=ASGITransport(app=production_app), base_url="http://test") as production:
        denied = await production.post("/api/v1/owner/auth/login", headers={"Origin": review_origin}, json={"email": "owner@local.jds.test", "password": "local-review-password"})
        assert denied.status_code == 403
        assert denied.json()["detail"]["code"] == "origin_invalid"
    production_app.state.db_engine.dispose()
    monkeypatch.setenv("JDS_ENVIRONMENT", "development")

    application = create_app(database_url=local_review_database)
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        rejected = await client.post("/api/v1/owner/auth/login", headers={"Origin": "http://test"}, json={"email": "other@local.jds.test", "password": "local-review-password"})
        assert rejected.status_code == 401
        unrelated = await client.post("/api/v1/owner/auth/login", headers={"Origin": "https://attacker.example"}, json={"email": "owner@local.jds.test", "password": "local-review-password"})
        assert unrelated.status_code == 403
        forged_forwarding = await client.post("/api/v1/owner/auth/login", headers={"Origin": "http://localhost:5173", "X-Forwarded-Host": "attacker.example", "X-Forwarded-Proto": "https"}, json={"email": "owner@local.jds.test", "password": "local-review-password"})
        assert forged_forwarding.status_code == 403
        proxy_headers = {"Origin": "http://localhost:5173", "X-Forwarded-Host": "synthetic-codespace-5173.app.github.dev", "X-Forwarded-Proto": "https"}
        diagnostics = await client.get(
            "/api/v1/local-review/request-diagnostics",
            headers={
                **proxy_headers,
                "Forwarded": 'for=127.0.0.1;host="synthetic-codespace-5173.app.github.dev";proto=https',
                "Referer": f"{review_origin}/owner/login",
                "Sec-Fetch-Site": "same-origin",
            },
        )
        assert diagnostics.status_code == 200
        assert diagnostics.json()["headers"] == {
            "origin": "http://localhost:5173",
            "host": "test",
            "x-forwarded-host": "synthetic-codespace-5173.app.github.dev",
            "x-forwarded-proto": "https",
            "forwarded": 'for=127.0.0.1;host="synthetic-codespace-5173.app.github.dev";proto=https',
            "referer": f"{review_origin}/owner/login",
            "sec-fetch-site": "same-origin",
        }
        login = await client.post("/api/v1/owner/auth/login", headers=proxy_headers, json={"email": "owner@local.jds.test", "password": "local-review-password"})
        assert login.status_code == 200
        organizations = await client.get("/api/v1/owner/auth/organizations")
        assert {item["organization_slug"] for item in organizations.json()} == {"the-guest-house", "second-street-cafe"}
        target = next(item for item in organizations.json() if item["organization_slug"] == "second-street-cafe")
        missing_csrf = await client.post(f'/api/v1/owner/auth/organizations/{target["membership_id"]}/select', headers=proxy_headers)
        assert missing_csrf.status_code == 403
        assert missing_csrf.json()["detail"]["code"] == "csrf_invalid"
        switched = await client.post(f'/api/v1/owner/auth/organizations/{target["membership_id"]}/select', headers={**proxy_headers, "X-CSRF-Token": login.json()["csrf_token"]})
        assert switched.status_code == 200
        assert switched.json()["organization_id"] == target["organization_id"]
        forbidden = await client.post(f'/api/v1/owner/auth/organizations/{uuid4()}/select', headers={**proxy_headers, "X-CSRF-Token": switched.json()["csrf_token"]})
        assert forbidden.status_code == 403

    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as public:
        ladels = await public.get("/api/v1/catalog?review_tenant=the-guest-house")
        second_cafe = await public.get("/api/v1/catalog?review_tenant=second-street-cafe")
        unknown = await public.get("/api/v1/catalog?review_tenant=not-seeded")
        assert ladels.status_code == second_cafe.status_code == 200
        assert ladels.json() != second_cafe.json()
        assert unknown.status_code == 404
    application.state.db_engine.dispose(); engine.dispose()
