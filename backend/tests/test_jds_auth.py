import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import date, datetime, time, timedelta, timezone
import logging
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import pytest
import httpx
from alembic import command
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.jds_auth.config import AuthSettings
from app.jds_auth.foundation import ensure_foundation
from app.jds_auth.provision_foundation import main as provision_foundation
from app.jds_auth.models import (
    ExternalIdentity,
    JdsApplication,
    JdsUser,
    Membership,
    Organization,
    OwnerInvitation,
    OwnerSession,
    Permission,
    Role,
    RolePermission,
    StaffPinCredential,
)
from app.jds_auth.provider import IdentityProviderError, InvalidCredentialsError, ProviderAuthentication, ProviderIdentity, SupabaseIdentityProvider
from app.jds_auth.schemas import CustomerPasswordCompletionRequest, CustomerRegistrationRequest, PasswordCompletionRequest
from app.jds_auth.security import hash_secret
from app.main import create_app
from app.catalog.models import Product
from app.catalog.seed import seed_catalog
from app.availability.models import BusinessClosure, BusinessHour, BusinessSettings, ProductAvailability
from app.orders.models import Order, OrderItem, OrderItemModifier
from app.customers.models import CustomerProfile
from app.clover.client import CloverClient
from tests.test_migrations import make_alembic_config
from tests.test_order_service import local_datetime, seed_order_dependencies


class FakeIdentityProvider:
    def __init__(self) -> None:
        self.identity = ProviderIdentity(
            issuer="https://identity.example.test/auth/v1",
            subject="provider-user-1",
            email="owner@example.com",
            email_verified=True,
        )
        self.invited: list[tuple[str, str]] = []
        self.reset_requests: list[tuple[str, str]] = []
        self.password_updates: list[str] = []
        self.enforce_password_updates = False
        self.password_update_error: Exception | None = None
        self.access_token_error: Exception | None = None
        self.verification_error: Exception | None = None
        self.registrations: list[tuple[str, str]] = []
        self.verification_resends: list[tuple[str, str]] = []

    def register_user(self, email: str, password: str, redirect_url: str) -> ProviderIdentity:
        assert password == "correct horse battery staple"
        self.registrations.append((email, redirect_url))
        return self.identity

    def authenticate_password(self, email: str, password: str) -> ProviderAuthentication:
        expected_password = self.password_updates[-1] if self.enforce_password_updates and self.password_updates else "correct horse battery staple"
        if password != expected_password:
            raise InvalidCredentialsError("Authentication failed.")
        return ProviderAuthentication(self.identity, "provider-access-token")

    def request_password_reset(self, email: str, redirect_url: str) -> None:
        self.reset_requests.append((email, redirect_url))

    def verify_email_token(self, token_hash: str, token_type: str) -> ProviderAuthentication:
        assert token_hash == "t" * 32
        assert token_type in {"invite", "recovery", "email"}
        if self.verification_error is not None:
            raise self.verification_error
        return ProviderAuthentication(self.identity, "provider-access-token")

    def authenticate_access_token(self, access_token: str) -> ProviderAuthentication:
        assert access_token == "recovery-access-token"
        if self.access_token_error is not None:
            raise self.access_token_error
        return ProviderAuthentication(self.identity, access_token)

    def resend_verification(self, email: str, redirect_url: str) -> None:
        self.verification_resends.append((email, redirect_url))

    def update_password(self, access_token: str, password: str) -> None:
        assert access_token in {"provider-access-token", "recovery-access-token"}
        if self.password_update_error is not None:
            raise self.password_update_error
        self.password_updates.append(password)

    def invite_user(self, email: str, redirect_url: str) -> str:
        self.invited.append((email, redirect_url))
        return self.identity.subject


@pytest.fixture
def auth_engine(postgresql_url: str) -> Iterator[Engine]:
    command.upgrade(make_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    auth_tables = (
        "security_audit_events, auth_rate_limit_buckets, owner_sessions, owner_invitations, staff_pin_credentials, "
        "organization_memberships, auth_role_permissions, external_identities, "
        "auth_roles, auth_permissions, jds_users, organizations, jds_applications"
    )
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {auth_tables} RESTART IDENTITY CASCADE"))
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {auth_tables} RESTART IDENTITY CASCADE"))
        engine.dispose()


@pytest.fixture
def auth_settings() -> AuthSettings:
    return AuthSettings(
        supabase_url="https://identity.example.test",
        supabase_publishable_key="publishable",
        supabase_secret_key="secret",
        session_pepper="p" * 48,
        frontend_url="http://test",
        secure_cookies=False,
    )


@pytest.fixture
def fake_provider() -> FakeIdentityProvider:
    return FakeIdentityProvider()


def seed_owner(engine: Engine, provider: FakeIdentityProvider) -> None:
    with Session(engine) as session, session.begin():
        application, organization = ensure_foundation(
            session,
            application_key="jds-commerce",
            application_name="JDS Commerce",
            organization_slug="the-guest-house",
            organization_name="The Guest House",
        )
        owner_role = session.scalar(
            select(Role).where(
                Role.application_id == application.id,
                Role.key == "owner",
            )
        )
        assert owner_role is not None
        user = JdsUser(
            primary_email=provider.identity.email,
            display_name="Owner User",
            email_verified_at=datetime.now(timezone.utc),
        )
        session.add(user)
        session.flush()
        session.add_all(
            [
                ExternalIdentity(
                    user_id=user.id,
                    issuer=provider.identity.issuer,
                    subject=provider.identity.subject,
                    provider="supabase",
                    provider_email=provider.identity.email,
                ),
                Membership(
                    organization_id=organization.id,
                    application_id=application.id,
                    user_id=user.id,
                    role_id=owner_role.id,
                    status="active",
                    joined_at=datetime.now(timezone.utc),
                ),
            ]
        )


@pytest.fixture
async def auth_client(
    postgresql_url: str,
    auth_engine: Engine,
    auth_settings: AuthSettings,
    fake_provider: FakeIdentityProvider,
) -> AsyncIterator[AsyncClient]:
    seed_owner(auth_engine, fake_provider)
    application = create_app(
        database_url=postgresql_url,
        auth_settings=auth_settings,
        auth_provider=fake_provider,
    )
    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://test",
    ) as client:
        yield client
    application.state.db_engine.dispose()


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_login_uses_opaque_httponly_session_and_csrf(
    auth_client: AsyncClient,
    auth_engine: Engine,
    auth_settings: AuthSettings,
) -> None:
    response = await auth_client.post(
        "/api/v1/owner/auth/login",
        headers={"Origin": "http://test"},
        json={
            "email": "owner@example.com",
            "password": "correct horse battery staple",
        },
    )
    assert response.status_code == 200
    assert response.json()["role"] == "owner"
    assert "members.invite" in response.json()["permissions"]
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Domain=" not in cookie

    raw_token = auth_client.cookies[auth_settings.session_cookie_name]
    with Session(auth_engine) as session:
        stored = session.scalar(select(OwnerSession))
        assert stored is not None
        assert stored.token_hash != raw_token
        assert stored.token_hash == hash_secret(raw_token, auth_settings.session_pepper)

    denied = await auth_client.post(
        "/api/v1/owner/auth/logout",
        headers={"Origin": "http://test", "X-CSRF-Token": "wrong"},
    )
    assert denied.status_code == 403
    csrf = response.json()["csrf_token"]
    logout = await auth_client.post(
        "/api/v1/owner/auth/logout",
        headers={"Origin": "http://test", "X-CSRF-Token": csrf},
    )
    assert logout.status_code == 200
    assert (await auth_client.get("/api/v1/owner/auth/session")).status_code == 401


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_login_repairs_legacy_email_derived_display_name(
    auth_client: AsyncClient,
    auth_engine: Engine,
    fake_provider: FakeIdentityProvider,
) -> None:
    with Session(auth_engine) as session, session.begin():
        user = session.scalar(select(JdsUser).where(JdsUser.primary_email == "owner@example.com"))
        assert user is not None
        user.display_name = "owner"
    fake_provider.identity = ProviderIdentity(
        issuer=fake_provider.identity.issuer,
        subject=fake_provider.identity.subject,
        email=fake_provider.identity.email,
        email_verified=True,
        display_name="Marc Jacquot",
    )

    response = await auth_client.post(
        "/api/v1/owner/auth/login",
        headers={"Origin": "http://test"},
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "Marc Jacquot"
    with Session(auth_engine) as session:
        user = session.scalar(select(JdsUser).where(JdsUser.primary_email == "owner@example.com"))
        assert user is not None
        assert user.display_name == "Marc Jacquot"


@pytest.mark.postgresql
def test_foundation_provisioning_is_idempotent_and_separates_customer_permissions(
    auth_engine: Engine,
    postgresql_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", postgresql_url)
    provision_foundation()
    with Session(auth_engine) as session, session.begin():
        customer = session.scalar(select(Role).where(Role.key == "customer"))
        integration = session.scalar(
            select(Permission).where(Permission.key == "integrations.manage")
        )
        assert customer is not None and integration is not None
        session.add(RolePermission(role_id=customer.id, permission_id=integration.id))
    provision_foundation()

    with Session(auth_engine) as session:
        roles = {
            role.key: role
            for role in session.scalars(select(Role)).all()
        }
        def permission_keys(role: Role) -> set[str]:
            return set(session.scalars(
                select(Permission.key)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id == role.id)
            ))

        customer_permissions = permission_keys(roles["customer"])
        owner_permissions = permission_keys(roles["owner"])
    assert customer_permissions == {"customer.orders", "customer.profile"}
    assert "integrations.manage" not in customer_permissions
    assert "integrations.manage" in owner_permissions


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_clover_management_routes_require_owner_integration_permission(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clover_environment = {
        "CLOVER_APP_ID": "app-id",
        "CLOVER_APP_SECRET": "app-secret",
        "CLOVER_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "CLOVER_STATE_SECRET": "s" * 48,
        "CLOVER_WEBHOOK_SECRET": "w" * 48,
        "CLOVER_MERCHANT_ID": "merchant-id",
        "CLOVER_ECOMMERCE_PRIVATE_TOKEN": "private-token",
        "PUBLIC_APP_URL": "https://api.example.test",
        "FRONTEND_URL": "https://shop.example.test",
    }
    for name, value in clover_environment.items():
        monkeypatch.setenv(name, value)

    assert (await auth_client.get("/api/v1/clover/oauth/start")).status_code == 401
    assert (
        await auth_client.get(
            "/api/v1/clover/oauth/callback",
            params={"code": "code", "state": "state", "merchant_id": "merchant-id"},
        )
    ).status_code == 401
    assert (await auth_client.get("/api/v1/clover/connection")).status_code == 401

    login = await owner_login(auth_client)
    assert "integrations.manage" in login["permissions"]
    connection = await auth_client.get("/api/v1/clover/connection")
    assert connection.status_code == 200
    assert connection.json()["connected"] is True
    assert connection.json()["environment"] == "sandbox"
    assert connection.json()["merchant_id"] == "merc...t-id"

    monkeypatch.delenv("CLOVER_ECOMMERCE_PRIVATE_TOKEN")
    disconnected = await auth_client.get("/api/v1/clover/connection")
    assert disconnected.status_code == 200
    assert disconnected.json() == {
        "configured": True,
        "connected": False,
        "environment": "sandbox",
        "merchant_id": "merc...t-id",
        "health": "disconnected",
        "credential_source": "oauth",
        "access_token_expires_at": None,
        "refresh_token_expires_at": None,
        "configuration": {
            "environment": "sandbox",
            "app_id_masked": "******",
            "merchant_id_masked": "merc...t-id",
            "credential_source": "oauth",
            "oauth_configured": True,
            "webhook_configured": True,
            "page_configuration": "default",
            "page_config_uuid_masked": None,
            "platform_api_host": "https://apisandbox.dev.clover.com",
            "hosted_checkout_host": "https://apisandbox.dev.clover.com",
            "ecommerce_service_host": "https://scl-sandbox.dev.clover.com",
            "tokenization_host": "https://token-sandbox.dev.clover.com",
        },
    }


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_password_reset_is_generic_and_provider_managed(
    auth_client: AsyncClient,
    fake_provider: FakeIdentityProvider,
) -> None:
    response = await auth_client.post(
        "/api/v1/owner/auth/password-reset",
        headers={"Origin": "http://test"},
        json={"email": "unknown@example.com"},
    )
    assert response.status_code == 200
    assert response.json()["message"].startswith("If the account exists")
    assert fake_provider.reset_requests == [
        ("unknown@example.com", "http://test/admin/reset-password")
    ]


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_owner_can_invite_future_role_with_csrf(
    auth_client: AsyncClient,
    auth_engine: Engine,
    fake_provider: FakeIdentityProvider,
) -> None:
    login = await auth_client.post(
        "/api/v1/owner/auth/login",
        headers={"Origin": "http://test"},
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
    )
    response = await auth_client.post(
        "/api/v1/owner/auth/invitations",
        headers={"Origin": "http://test", "X-CSRF-Token": login.json()["csrf_token"]},
        json={"email": "manager@example.com", "role": "manager"},
    )
    assert response.status_code == 201
    assert len(fake_provider.invited) == 1
    invited_email, redirect_url = fake_provider.invited[0]
    assert invited_email == "manager@example.com"
    parsed = urlparse(redirect_url)
    assert parsed.path == "/admin/invitation"
    parameters = parse_qs(parsed.query)
    assert set(parameters) == {"invitation_id", "invitation_secret"}
    with Session(auth_engine) as session:
        invitation = session.scalar(select(OwnerInvitation))
        assert invitation is not None
        assert invitation.secret_hash != parameters["invitation_secret"][0]
        assert invitation.secret_hash == hash_secret(
            parameters["invitation_secret"][0],
            "p" * 48,
        )


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_customer_catalog_stays_public_without_owner_session(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.get("/api/v1/catalog")
    assert response.status_code == 200


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_owner_scheduling_uses_authoritative_preview_and_protected_mutations(
    auth_client: AsyncClient,
    auth_engine: Engine,
) -> None:
    assert (await auth_client.get("/api/v1/owner/scheduling")).status_code == 401
    with Session(auth_engine) as session, session.begin():
        session.query(BusinessClosure).delete()
        session.query(BusinessHour).delete()
        organization_id = session.scalar(
            select(Organization.id).where(Organization.slug == "the-guest-house")
        )
        settings = session.scalar(
            select(BusinessSettings).where(
                BusinessSettings.organization_id == organization_id
            )
        )
        if settings is None:
            settings = BusinessSettings(
                organization_id=organization_id,
                timezone="America/Toronto",
            )
            session.add(settings)
        settings.ordering_enabled = True
        settings.ordering_mode = "schedule"
        settings.minimum_lead_time_minutes = 20
        settings.pickup_interval_minutes = 5
        settings.maximum_advance_days = 14
        for weekday in range(7):
            session.add(BusinessHour(settings=settings, weekday=weekday, is_closed=False, opens_at=time(0), closes_at=time(23, 59)))

    login = await owner_login(auth_client)
    csrf_headers = {"Origin": "http://test", "X-CSRF-Token": str(login["csrf_token"])}
    initial = await auth_client.get("/api/v1/owner/scheduling")
    assert initial.status_code == 200
    assert len(initial.json()["hours"]) == 7
    assert initial.json()["preview"]["ordering_available"] is True

    paused = await auth_client.put(
        "/api/v1/owner/scheduling/ordering",
        headers=csrf_headers,
        json={"ordering_mode": "force_closed"},
    )
    assert paused.status_code == 200
    assert paused.json()["preview"]["ordering_status"] == "paused"
    assert paused.json()["preview"]["status_reason"] == "Paused by owner."

    preferences = await auth_client.put(
        "/api/v1/owner/scheduling/preferences",
        headers=csrf_headers,
        json={
            "minimum_lead_time_minutes": 30,
            "pickup_interval_minutes": 10,
            "maximum_advance_days": 7,
        },
    )
    assert preferences.status_code == 200
    assert preferences.json()["minimum_lead_time_minutes"] == 30

    closure = await auth_client.post(
        "/api/v1/owner/scheduling/closures",
        headers=csrf_headers,
        json={
            "business_date": date.today().isoformat(),
            "reopens_on": (date.today() + timedelta(days=2)).isoformat(),
            "reason": "Staff holiday",
        },
    )
    assert closure.status_code == 201
    assert closure.json()["closures"][0]["reason"] == "Staff holiday"


def test_auth_settings_require_production_secrets() -> None:
    with pytest.raises(Exception, match="Missing JDS authentication"):
        AuthSettings("", "", "", "", "").validate()


def test_customer_passwords_require_10_characters_without_weakening_owner_completion() -> None:
    CustomerRegistrationRequest(
        display_name="Customer",
        email="customer@example.com",
        password="ten-chars!",
        phone="+15198816869",
    )
    CustomerPasswordCompletionRequest(
        access_token="recovery-access-token",
        password="ten-chars!",
    )

    with pytest.raises(ValueError):
        CustomerRegistrationRequest(
            display_name="Customer",
            email="customer@example.com",
            password="nine-char",
            phone="+15198816869",
        )
    with pytest.raises(ValueError):
        CustomerPasswordCompletionRequest(
            access_token="recovery-access-token",
            password="nine-char",
        )
    with pytest.raises(ValueError):
        PasswordCompletionRequest(token_hash="t" * 32, password="ten-chars!")


def test_supabase_adapter_keeps_admin_secret_server_side(
    auth_settings: AuthSettings,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/invite"):
            return httpx.Response(200, json={"id": "invited-subject"})
        return httpx.Response(
            200,
            json={
                "access_token": "provider-token",
                "user": {
                    "id": "subject",
                    "email": "owner@example.com",
                    "email_confirmed_at": "2026-08-02T00:00:00Z",
                    "user_metadata": {"full_name": "Marc Jacquot"},
                },
            },
        )

    provider = SupabaseIdentityProvider(
        auth_settings,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    authentication = provider.authenticate_password(
        "owner@example.com",
        "password",
    )
    provider.verify_email_token("t" * 32, "email")
    provider.resend_verification("customer@example.com", "http://test/account/verify-email")
    provider.invite_user("staff@example.com", "http://test/admin/invitation")

    assert authentication.identity.email_verified is True
    assert authentication.identity.display_name == "Marc Jacquot"
    assert requests[0].headers["apikey"] == "publishable"
    assert "authorization" not in requests[0].headers
    assert requests[1].url.path.endswith("/verify")
    assert requests[1].read() == b'{"token_hash":"tttttttttttttttttttttttttttttttt","type":"email"}'
    assert requests[2].url.path.endswith("/resend")
    assert requests[2].url.params["redirect_to"] == "http://test/account/verify-email"
    assert requests[2].read() == b'{"type":"signup","email":"customer@example.com"}'
    assert requests[3].headers["apikey"] == "secret"
    assert requests[3].headers["authorization"] == "Bearer secret"
    assert requests[3].url.params["redirect_to"] == "http://test/admin/invitation"


def test_supabase_adapter_logs_sanitized_rate_limit_diagnostics(
    auth_settings: AuthSettings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={
                "Retry-After": "42",
                "X-Sb-Error-Code": "over_email_send_rate_limit",
                "X-Request-Id": "request-123",
                "Set-Cookie": "must-not-be-logged=secret",
                "Authorization": "Bearer must-not-be-logged",
            },
            json={
                "code": "over_email_send_rate_limit",
                "message": "Email rate limit exceeded for customer@example.com\ntry later",
            },
            request=request,
        )

    provider = SupabaseIdentityProvider(
        auth_settings,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with caplog.at_level("ERROR"), pytest.raises(IdentityProviderError) as raised:
        provider.register_user(
            "customer@example.com",
            "a sufficiently long password",
            "http://test/account/verify-email",
        )

    diagnostic = caplog.messages[-1]
    assert "operation=/auth/v1/signup status=429" in diagnostic
    assert "code=over_email_send_rate_limit" in diagnostic
    assert "message='Email rate limit exceeded for [redacted-email] try later'" in diagnostic
    assert "retry_after='42'" in diagnostic
    assert "'x-sb-error-code': 'over_email_send_rate_limit'" in diagnostic
    assert "'x-request-id': 'request-123'" in diagnostic
    assert "must-not-be-logged" not in diagnostic
    assert raised.value.provider_status == 429
    assert raised.value.provider_code == "over_email_send_rate_limit"
    assert raised.value.provider_message == "Email rate limit exceeded for [redacted-email] try later"


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_public_registration_endpoint_does_not_exist(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.post(
        "/api/v1/owner/auth/register",
        headers={"Origin": "http://test"},
        json={"email": "person@example.com", "password": "a" * 20},
    )
    assert response.status_code == 404


async def owner_login(client: AsyncClient) -> dict[str, object]:
    response = await client.post(
        "/api/v1/owner/auth/login",
        headers={"Origin": "http://test"},
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
    )
    assert response.status_code == 200
    return response.json()


async def create_invitation_through_api(
    client: AsyncClient,
    provider: FakeIdentityProvider,
    csrf_token: str,
    *,
    email: str = "manager@example.com",
    role: str = "manager",
) -> dict[str, str]:
    before = len(provider.invited)
    response = await client.post(
        "/api/v1/owner/auth/invitations",
        headers={"Origin": "http://test", "X-CSRF-Token": csrf_token},
        json={"email": email, "role": role},
    )
    assert response.status_code == 201
    return {key: values[0] for key, values in parse_qs(urlparse(provider.invited[before][1]).query).items()}


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_invitation_acceptance_is_bound_to_exact_jds_secret_subject_and_email(
    auth_client: AsyncClient,
    auth_engine: Engine,
    fake_provider: FakeIdentityProvider,
) -> None:
    login = await owner_login(auth_client)
    fake_provider.identity = ProviderIdentity(
        issuer=fake_provider.identity.issuer,
        subject="provider-manager-1",
        email="manager@example.com",
        email_verified=True,
    )
    parameters = await create_invitation_through_api(
        auth_client,
        fake_provider,
        str(login["csrf_token"]),
    )
    response = await auth_client.post(
        "/api/v1/owner/auth/invitations/accept",
        headers={"Origin": "http://test"},
        json={
            **parameters,
            "token_hash": "t" * 32,
            "password": "a sufficiently long password",
            "display_name": "Manager User",
        },
    )
    assert response.status_code == 200
    with Session(auth_engine) as session:
        invitation = session.get(OwnerInvitation, UUID(parameters["invitation_id"]))
        assert invitation is not None
        assert invitation.status == "accepted"
        assert invitation.provider_subject == "provider-manager-1"
        manager = session.scalar(select(JdsUser).where(JdsUser.primary_email == "manager@example.com"))
        assert manager is not None

    replay = await auth_client.post(
        "/api/v1/owner/auth/invitations/accept",
        headers={"Origin": "http://test"},
        json={
            **parameters,
            "token_hash": "t" * 32,
            "password": "a sufficiently long password",
            "display_name": "Replay",
        },
    )
    assert replay.status_code == 400


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_invitation_substitution_is_rejected_without_consuming_target(
    auth_client: AsyncClient,
    auth_engine: Engine,
    fake_provider: FakeIdentityProvider,
) -> None:
    login = await owner_login(auth_client)
    fake_provider.identity = ProviderIdentity(
        issuer=fake_provider.identity.issuer,
        subject="provider-staff-1",
        email="staff@example.com",
        email_verified=True,
    )
    first = await create_invitation_through_api(auth_client, fake_provider, str(login["csrf_token"]), email="staff@example.com", role="staff")
    second = await create_invitation_through_api(auth_client, fake_provider, str(login["csrf_token"]), email="staff@example.com", role="owner")
    response = await auth_client.post(
        "/api/v1/owner/auth/invitations/accept",
        headers={"Origin": "http://test"},
        json={
            "invitation_id": second["invitation_id"],
            "invitation_secret": first["invitation_secret"],
            "token_hash": "t" * 32,
            "password": "a sufficiently long password",
            "display_name": "Staff User",
        },
    )
    assert response.status_code == 400
    with Session(auth_engine) as session:
        target = session.get(OwnerInvitation, UUID(second["invitation_id"]))
        assert target is not None
        assert target.status == "sent"


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_invitation_acceptance_is_concurrency_safe(
    auth_client: AsyncClient,
    auth_engine: Engine,
    fake_provider: FakeIdentityProvider,
) -> None:
    login = await owner_login(auth_client)
    fake_provider.identity = ProviderIdentity(
        issuer=fake_provider.identity.issuer,
        subject="provider-concurrent-1",
        email="concurrent@example.com",
        email_verified=True,
    )
    parameters = await create_invitation_through_api(
        auth_client,
        fake_provider,
        str(login["csrf_token"]),
        email="concurrent@example.com",
    )
    payload = {
        **parameters,
        "token_hash": "t" * 32,
        "password": "a sufficiently long password",
        "display_name": "Concurrent User",
    }
    first, second = await asyncio.gather(
        auth_client.post("/api/v1/owner/auth/invitations/accept", headers={"Origin": "http://test"}, json=payload),
        auth_client.post("/api/v1/owner/auth/invitations/accept", headers={"Origin": "http://test"}, json=payload),
    )
    assert sorted([first.status_code, second.status_code]) == [200, 400]
    with Session(auth_engine) as session:
        users = session.scalars(select(JdsUser).where(JdsUser.primary_email == "concurrent@example.com")).all()
        assert len(users) == 1


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_password_reset_security_version_invalidates_sessions_and_recovers_from_provider_failure(
    auth_client: AsyncClient,
    auth_engine: Engine,
    fake_provider: FakeIdentityProvider,
) -> None:
    await owner_login(auth_client)
    fake_provider.password_update_error = IdentityProviderError("ambiguous provider failure")
    failed = await auth_client.post(
        "/api/v1/owner/auth/password-reset/complete",
        headers={"Origin": "http://test"},
        json={"token_hash": "t" * 32, "password": "a sufficiently long password"},
    )
    assert failed.status_code == 400
    assert (await auth_client.get("/api/v1/owner/auth/session")).status_code == 401
    with Session(auth_engine) as session:
        user = session.scalar(select(JdsUser).where(JdsUser.primary_email == "owner@example.com"))
        assert user is not None
        assert user.security_version == 2
        assert user.credential_state == "recovery_pending"

    fake_provider.password_update_error = None
    completed = await auth_client.post(
        "/api/v1/owner/auth/password-reset/complete",
        headers={"Origin": "http://test"},
        json={"token_hash": "t" * 32, "password": "a sufficiently long password"},
    )
    assert completed.status_code == 200
    with Session(auth_engine) as session:
        user = session.scalar(select(JdsUser).where(JdsUser.primary_email == "owner@example.com"))
        assert user is not None
        assert user.security_version == 3
        assert user.credential_state == "active"


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_logout_all_revokes_every_session(
    auth_client: AsyncClient,
) -> None:
    await owner_login(auth_client)
    second = await owner_login(auth_client)
    response = await auth_client.post(
        "/api/v1/owner/auth/logout-all",
        headers={"Origin": "http://test", "X-CSRF-Token": second["csrf_token"]},
    )
    assert response.status_code == 200
    assert (await auth_client.get("/api/v1/owner/auth/session")).status_code == 401


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_login_rate_limit_returns_generic_429_with_retry_after(
    auth_client: AsyncClient,
) -> None:
    responses = []
    for _ in range(11):
        responses.append(await auth_client.post(
            "/api/v1/owner/auth/login",
            headers={"Origin": "http://test"},
            json={"email": "owner@example.com", "password": "correct horse battery staple"},
        ))
    limited = responses[-1]
    assert limited.status_code == 429
    assert limited.json()["detail"] == {
        "code": "rate_limited",
        "message": "Too many requests. Try again later.",
    }
    assert int(limited.headers["Retry-After"]) > 0


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_password_reset_request_limit_is_generic_for_any_email(
    auth_client: AsyncClient,
) -> None:
    for email in ("unknown@example.com", "owner@example.com"):
        responses = [
            await auth_client.post(
                "/api/v1/owner/auth/password-reset",
                headers={"Origin": "http://test"},
                json={"email": email},
            )
            for _ in range(4)
        ]
        assert [response.status_code for response in responses] == [200, 200, 200, 429]
        assert responses[-1].json()["detail"]["code"] == "rate_limited"


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_password_reset_completion_and_invitation_acceptance_are_limited(
    auth_client: AsyncClient,
    fake_provider: FakeIdentityProvider,
) -> None:
    completions = [
        await auth_client.post(
            "/api/v1/owner/auth/password-reset/complete",
            headers={"Origin": "http://test"},
            json={"token_hash": "t" * 32, "password": "a sufficiently long password"},
        )
        for _ in range(6)
    ]
    assert [response.status_code for response in completions] == [200, 200, 200, 200, 200, 429]

    login = await owner_login(auth_client)
    fake_provider.identity = ProviderIdentity(
        issuer=fake_provider.identity.issuer,
        subject="provider-limited-1",
        email="limited@example.com",
        email_verified=True,
    )
    parameters = await create_invitation_through_api(
        auth_client,
        fake_provider,
        str(login["csrf_token"]),
        email="limited@example.com",
    )
    attempts = [
        await auth_client.post(
            "/api/v1/owner/auth/invitations/accept",
            headers={"Origin": "http://test"},
            json={
                **parameters,
                "invitation_secret": "x" * 64,
                "token_hash": "t" * 32,
                "password": "a sufficiently long password",
                "display_name": "Limited User",
            },
        )
        for _ in range(6)
    ]
    assert [response.status_code for response in attempts] == [400, 400, 400, 400, 400, 429]


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_invitation_creation_is_limited_per_actor(
    auth_client: AsyncClient,
    fake_provider: FakeIdentityProvider,
) -> None:
    login = await owner_login(auth_client)
    responses = [
        await auth_client.post(
            "/api/v1/owner/auth/invitations",
            headers={"Origin": "http://test", "X-CSRF-Token": str(login["csrf_token"])},
            json={"email": f"person-{index}@example.com", "role": "staff"},
        )
        for index in range(21)
    ]
    assert [response.status_code for response in responses[:20]] == [201] * 20
    assert responses[-1].status_code == 429
    assert len(fake_provider.invited) == 20


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_owner_catalog_mutations_persist_to_public_catalog(
    auth_client: AsyncClient,
    auth_engine: Engine,
) -> None:
    with auth_engine.begin() as connection:
        connection.execute(text(
            "TRUNCATE product_modifier_groups, modifier_options, product_variants, "
            "product_availability, products, modifier_groups, categories RESTART IDENTITY CASCADE"
        ))
    with Session(auth_engine) as session:
        seed_catalog(session)

    unauthenticated = await auth_client.get("/api/v1/owner/catalog")
    assert unauthenticated.status_code == 401
    login = await owner_login(auth_client)
    csrf = str(login["csrf_token"])
    owner_catalog = (await auth_client.get("/api/v1/owner/catalog")).json()
    latte = next(item for item in owner_catalog["products"] if item["slug"] == "latte")
    pastries = next(item for item in owner_catalog["categories"] if item["slug"] == "pastries")

    write_payload = {
        "slug": latte["slug"],
        "name": "Production Latte",
        "description": latte["description"],
        "base_price_cents": 575,
        "category_id": int(pastries["id"]),
        "image": latte["image"],
        "available": False,
        "featured": True,
        "lunch_special": True,
        "published": True,
        "sort_order": latte["sort_order"],
        "variants": [
            {
                "key": item["key"], "name": item["name"],
                "price_cents": item["price_cents"], "active": item["active"],
                "sort_order": item["sort_order"],
            }
            for item in latte["variants"]
        ],
        "modifier_group_ids": [int(item) for item in latte["modifier_group_ids"]],
    }
    denied = await auth_client.put(
        f"/api/v1/owner/catalog/products/{latte['id']}", json=write_payload
    )
    assert denied.status_code == 403
    updated = await auth_client.put(
        f"/api/v1/owner/catalog/products/{latte['id']}",
        headers={"Origin": "http://test", "X-CSRF-Token": csrf},
        json=write_payload,
    )
    assert updated.status_code == 200
    assert updated.json()["category_id"] == pastries["id"]

    with Session(auth_engine) as session:
        persisted = session.scalar(select(Product).where(Product.slug == "latte"))
        assert persisted is not None
        assert persisted.name == "Production Latte"
        assert persisted.base_price_cents == 575
        assert session.get(ProductAvailability, persisted.id).default_available is False
    hidden_catalog = (await auth_client.get("/api/v1/catalog")).json()
    assert all(
        product["slug"] != "latte"
        for category in hidden_catalog["categories"]
        for product in category["products"]
    )

    write_payload["available"] = True
    restored = await auth_client.put(
        f"/api/v1/owner/catalog/products/{latte['id']}",
        headers={"Origin": "http://test", "X-CSRF-Token": csrf},
        json=write_payload,
    )
    assert restored.status_code == 200
    public_catalog = (await auth_client.get("/api/v1/catalog")).json()
    public_latte = next(
        product for category in public_catalog["categories"]
        for product in category["products"] if product["slug"] == "latte"
    )
    assert public_latte["name"] == "Production Latte"
    assert public_latte["featured"] is True
    assert public_latte["lunch_special"] is True

    archived = await auth_client.delete(
        f"/api/v1/owner/catalog/products/{latte['id']}",
        headers={"Origin": "http://test", "X-CSRF-Token": csrf},
    )
    assert archived.status_code == 204
    with Session(auth_engine) as session:
        persisted = session.scalar(select(Product).where(Product.slug == "latte"))
        assert persisted is not None
        assert persisted.archived_at is not None


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_duplicate_customer_registration_logs_safe_business_rule(
    auth_client: AsyncClient,
    fake_provider: FakeIdentityProvider,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_provider.identity = ProviderIdentity(
        issuer=fake_provider.identity.issuer,
        subject="duplicate-customer-provider-user",
        email="duplicate@example.com",
        email_verified=False,
    )
    payload = {
        "display_name": "Duplicate Customer",
        "email": "duplicate@example.com",
        "password": "correct horse battery staple",
        "phone": "5198816869",
    }
    first = await auth_client.post(
        "/api/v1/customer/auth/register",
        headers={"Origin": "http://test"},
        json=payload,
    )

    with caplog.at_level("ERROR"):
        duplicate = await auth_client.post(
            "/api/v1/customer/auth/register",
            headers={"Origin": "http://test"},
            json=payload,
        )

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "detail": {
            "code": "registration_failed",
            "message": "Customer account could not be created.",
        }
    }
    diagnostic = next(
        message for message in caplog.messages
        if message.startswith("customer_registration_failed")
    )
    assert "stage=external_identity_lookup" in diagnostic
    assert "exception_type=CustomerRegistrationError" in diagnostic
    assert "reason=duplicate_external_identity" in diagnostic
    assert "duplicate@example.com" not in diagnostic
    assert payload["password"] not in diagnostic


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_customer_verification_logs_safe_provider_failure(
    auth_client: AsyncClient,
    fake_provider: FakeIdentityProvider,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_provider.verification_error = IdentityProviderError(
        "Identity provider request failed.",
        provider_status=403,
        provider_code="otp_expired",
        provider_message="Token has expired or is invalid",
    )

    with caplog.at_level("ERROR"):
        response = await auth_client.post(
            "/api/v1/customer/auth/verify-email",
            headers={"Origin": "http://test"},
            json={"token_hash": "t" * 32},
        )

    assert response.status_code == 400
    assert response.json() == {
        "detail": {
            "code": "verification_invalid",
            "message": "Email verification link is invalid or expired.",
        }
    }
    diagnostic = next(
        message for message in caplog.messages
        if message.startswith("customer_verification_failed")
    )
    assert "stage=supabase_verification" in diagnostic
    assert "exception_type=IdentityProviderError" in diagnostic
    assert "provider_status=403" in diagnostic
    assert "provider_code=otp_expired" in diagnostic
    assert "provider_message='Token has expired or is invalid'" in diagnostic
    assert "business_rule=None" in diagnostic
    assert "t" * 32 not in diagnostic


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_customer_verification_logs_safe_business_rule_failure(
    auth_client: AsyncClient,
    fake_provider: FakeIdentityProvider,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_provider.identity = ProviderIdentity(
        issuer=fake_provider.identity.issuer,
        subject="missing-customer-provider-user",
        email="missing-customer@example.com",
        email_verified=True,
    )
    with caplog.at_level("ERROR"):
        response = await auth_client.post(
            "/api/v1/customer/auth/verify-email",
            headers={"Origin": "http://test"},
            json={"token_hash": "t" * 32},
        )

    assert response.status_code == 400
    diagnostic = next(
        message for message in caplog.messages
        if message.startswith("customer_verification_failed")
    )
    assert "stage=external_identity_lookup" in diagnostic
    assert "exception_type=CustomerVerificationError" in diagnostic
    assert "provider_status=None" in diagnostic
    assert "provider_code=None" in diagnostic
    assert "provider_message=None" in diagnostic
    assert "business_rule=missing_external_identity" in diagnostic
    assert "t" * 32 not in diagnostic


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_customer_password_reset_logs_safe_provider_failure(
    auth_client: AsyncClient,
    fake_provider: FakeIdentityProvider,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(logging.getLogger("app.api.v1.customer_auth"), "disabled", False)
    fake_provider.access_token_error = IdentityProviderError(
        "Identity provider request failed.",
        provider_status=401,
        provider_code="bad_jwt",
        provider_message="JWT expired",
        provider_operation="/auth/v1/user",
        provider_method="GET",
    )
    access_token = "recovery-access-token"
    password = "a sufficiently long password"

    with caplog.at_level("ERROR"):
        response = await auth_client.post(
            "/api/v1/customer/auth/password-reset/complete",
            headers={"Origin": "http://test"},
            json={"access_token": access_token, "password": password},
        )

    assert response.status_code == 400
    assert response.json() == {
        "detail": {
            "code": "password_reset_invalid",
            "message": "Password reset link is invalid or expired.",
        }
    }
    diagnostic = next(
        message for message in caplog.messages
        if message.startswith("customer_password_reset_failed")
    )
    assert "stage=recovery_session_validation" in diagnostic
    assert "exception_type=IdentityProviderError" in diagnostic
    assert "provider_operation=/auth/v1/user" in diagnostic
    assert "provider_method=GET" in diagnostic
    assert "provider_status=401" in diagnostic
    assert "provider_code=bad_jwt" in diagnostic
    assert "provider_message='JWT expired'" in diagnostic
    assert access_token not in diagnostic
    assert password not in diagnostic


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_customer_password_reset_reconciles_verified_orphaned_supabase_identity(
    auth_client: AsyncClient,
    auth_engine: Engine,
    fake_provider: FakeIdentityProvider,
) -> None:
    fake_provider.enforce_password_updates = True
    fake_provider.identity = ProviderIdentity(
        issuer=fake_provider.identity.issuer,
        subject="orphaned-customer-provider-user",
        email="orphaned@example.com",
        email_verified=True,
        display_name="Marc Jacquot",
    )
    new_password = "a new sufficiently long password"

    completed = await auth_client.post(
        "/api/v1/customer/auth/password-reset/complete",
        headers={"Origin": "http://test"},
        json={"access_token": "recovery-access-token", "password": new_password},
    )

    assert completed.status_code == 200
    assert completed.json() == {"message": "Password updated. Sign in again."}
    assert fake_provider.password_updates == [new_password]
    with Session(auth_engine) as session:
        identity = session.scalar(select(ExternalIdentity).where(
            ExternalIdentity.issuer == fake_provider.identity.issuer,
            ExternalIdentity.subject == fake_provider.identity.subject,
        ))
        assert identity is not None
        assert identity.user.primary_email == "orphaned@example.com"
        assert identity.user.display_name == "Marc Jacquot"
        assert identity.user.status == "active"
        assert identity.user.credential_state == "active"
        membership = session.scalar(select(Membership).where(Membership.user_id == identity.user_id))
        assert membership is not None
        assert membership.status == "active"
        role = session.get(Role, membership.role_id)
        assert role is not None
        assert role.key == "customer"

    old_password = await auth_client.post(
        "/api/v1/customer/auth/login",
        headers={"Origin": "http://test"},
        json={"email": "orphaned@example.com", "password": "correct horse battery staple"},
    )
    assert old_password.status_code == 401
    new_password_login = await auth_client.post(
        "/api/v1/customer/auth/login",
        headers={"Origin": "http://test"},
        json={"email": "orphaned@example.com", "password": new_password},
    )
    assert new_password_login.status_code == 200
    assert new_password_login.json()["role"] == "customer"


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_active_owner_cannot_sign_in_through_customer_login(
    auth_client: AsyncClient,
    auth_engine: Engine,
    fake_provider: FakeIdentityProvider,
) -> None:
    with Session(auth_engine) as session:
        application = session.scalar(select(JdsApplication).where(JdsApplication.key == "jds-commerce"))
        organization = session.scalar(select(Organization).where(Organization.slug == "the-guest-house"))
        user = session.scalar(select(JdsUser).where(JdsUser.primary_email == fake_provider.identity.email))
        assert application is not None
        assert organization is not None
        assert user is not None
        user_id = user.id
        application_id = application.id
        organization_id = organization.id
        identity_ids_before = list(session.scalars(select(ExternalIdentity.id).where(ExternalIdentity.user_id == user_id)))
        membership_ids_before = list(session.scalars(select(Membership.id).where(Membership.user_id == user_id)))
        assert len(identity_ids_before) == 1
        assert len(membership_ids_before) == 1

    customer_login = await auth_client.post(
        "/api/v1/customer/auth/login",
        headers={"Origin": "http://test"},
        json={"email": fake_provider.identity.email, "password": "correct horse battery staple"},
    )

    assert customer_login.status_code == 401
    assert customer_login.json()["detail"]["code"] == "authentication_failed"

    customer_session = await auth_client.get("/api/v1/customer/auth/session")
    assert customer_session.status_code == 401
    customer_orders = await auth_client.get("/api/v1/customer/orders")
    assert customer_orders.status_code == 401

    ordering_payload = {
        "idempotency_key": "owner-cannot-order",
        "customer": {"name": "Owner User", "email": "owner@example.com", "phone": "+15198816869"},
        "requested_pickup_at": local_datetime(8, 30).isoformat(),
        "lines": [{"product_id": 1, "quantity": 1}],
    }
    owner_order = await auth_client.post("/api/v1/orders", json=ordering_payload)
    assert owner_order.status_code == 401
    assert owner_order.json()["detail"]["code"] == "unauthenticated"

    owner_login_response = await auth_client.post(
        "/api/v1/owner/auth/login",
        headers={"Origin": "http://test"},
        json={"email": fake_provider.identity.email, "password": "correct horse battery staple"},
    )
    assert owner_login_response.status_code == 200
    assert owner_login_response.json()["role"] == "owner"

    customer_identity = ProviderIdentity(
        issuer=fake_provider.identity.issuer,
        subject="provider-customer-with-owner-session",
        email="customer-with-owner-session@example.com",
        email_verified=True,
    )
    with Session(auth_engine) as session, session.begin():
        customer_role = session.scalar(select(Role).where(Role.application_id == application_id, Role.key == "customer"))
        assert customer_role is not None
        customer_user = JdsUser(
            primary_email=customer_identity.email,
            display_name="Customer With Owner Session",
            email_verified_at=datetime.now(timezone.utc),
        )
        session.add(customer_user)
        session.flush()
        session.add_all([
            ExternalIdentity(
                user_id=customer_user.id,
                issuer=customer_identity.issuer,
                subject=customer_identity.subject,
                provider="supabase",
                provider_email=customer_identity.email,
            ),
            Membership(
                organization_id=organization_id,
                application_id=application_id,
                user_id=customer_user.id,
                role_id=customer_role.id,
                status="active",
                joined_at=datetime.now(timezone.utc),
            ),
        ])
    fake_provider.identity = customer_identity
    customer_login = await auth_client.post(
        "/api/v1/customer/auth/login",
        headers={"Origin": "http://test"},
        json={"email": customer_identity.email, "password": "correct horse battery staple"},
    )
    assert customer_login.status_code == 200
    assert customer_login.json()["role"] == "customer"
    assert (await auth_client.get("/api/v1/customer/auth/session")).json()["role"] == "customer"
    assert (await auth_client.get("/api/v1/owner/auth/session")).json()["role"] == "owner"

    with Session(auth_engine) as session:
        identities_after = list(session.scalars(select(ExternalIdentity).where(ExternalIdentity.user_id == user_id)))
        memberships_after = list(session.scalars(select(Membership).where(Membership.user_id == user_id)))
        assert [identity.id for identity in identities_after] == identity_ids_before
        assert [membership.id for membership in memberships_after] == membership_ids_before
        membership = memberships_after[0]
        role = session.get(Role, membership.role_id)
        assert role is not None
        assert role.key == "owner"
        assert membership.status == "active"
        assert membership.application_id == application_id
        assert membership.organization_id == organization_id


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_anonymous_order_and_clover_checkout_are_rejected_before_side_effects(
    auth_client: AsyncClient,
    auth_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with auth_engine.begin() as connection:
        connection.execute(text(
            "TRUNCATE order_item_modifiers, order_items, orders, "
            "product_availability_overrides, product_availability, "
            "business_closures, business_hours, business_settings, "
            "product_modifier_groups, modifier_options, product_variants, "
            "products, modifier_groups, categories RESTART IDENTITY CASCADE"
        ))
    with Session(auth_engine) as session:
        ids = seed_order_dependencies(session)
    clover_calls = 0

    def forbidden_clover_call(*_: object, **__: object) -> dict:
        nonlocal clover_calls
        clover_calls += 1
        return {}

    monkeypatch.setattr(CloverClient, "create_checkout", forbidden_clover_call)
    payload = {
        "idempotency_key": "anonymous-order-blocked",
        "customer": {"name": "Anonymous Person", "email": "person@example.com", "phone": "+15198816869"},
        "requested_pickup_at": local_datetime(8, 30).isoformat(),
        "lines": [{"product_id": ids["product"], "variant_id": ids["large"], "quantity": 1}],
    }

    order_response = await auth_client.post("/api/v1/orders", json=payload)
    checkout_response = await auth_client.post(
        "/api/v1/clover/orders/not-an-order/checkout"
    )

    assert order_response.status_code == 401
    assert checkout_response.status_code == 401
    assert clover_calls == 0
    with Session(auth_engine) as session:
        assert session.scalar(select(text("count(*)")).select_from(Order)) == 0


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_customer_registration_verification_profile_and_role_isolation(
    auth_client: AsyncClient,
    auth_engine: Engine,
    fake_provider: FakeIdentityProvider,
) -> None:
    fake_provider.identity = ProviderIdentity(
        issuer=fake_provider.identity.issuer,
        subject="customer-provider-user",
        email="customer@example.com",
        email_verified=False,
    )
    registration = await auth_client.post(
        "/api/v1/customer/auth/register",
        headers={"Origin": "http://test"},
        json={
            "display_name": "Customer User",
            "email": "customer@example.com",
            "password": "correct horse battery staple",
            "phone": "(519) 881-6869",
        },
    )
    assert registration.status_code == 201
    assert fake_provider.registrations == [
        ("customer@example.com", "http://test/account/verify-email")
    ]
    with Session(auth_engine) as session:
        registered_profile = session.scalar(select(CustomerProfile))
        assert registered_profile is not None
        assert registered_profile.phone == "+15198816869"
    resent = await auth_client.post(
        "/api/v1/customer/auth/verification/resend",
        headers={"Origin": "http://test"},
        json={"email": "customer@example.com"},
    )
    assert resent.status_code == 200
    assert fake_provider.verification_resends == [
        ("customer@example.com", "http://test/account/verify-email")
    ]
    unverified = await auth_client.post(
        "/api/v1/customer/auth/login",
        headers={"Origin": "http://test"},
        json={"email": "customer@example.com", "password": "correct horse battery staple"},
    )
    assert unverified.status_code == 403

    fake_provider.identity = ProviderIdentity(
        issuer=fake_provider.identity.issuer,
        subject="customer-provider-user",
        email="customer@example.com",
        email_verified=True,
    )
    verified = await auth_client.post(
        "/api/v1/customer/auth/verify-email",
        headers={"Origin": "http://test"},
        json={"token_hash": "t" * 32},
    )
    assert verified.status_code == 200
    login = await auth_client.post(
        "/api/v1/customer/auth/login",
        headers={"Origin": "http://test"},
        json={"email": "customer@example.com", "password": "correct horse battery staple"},
    )
    assert login.status_code == 200
    assert "Max-Age=43200" in login.headers["set-cookie"]
    payload = login.json()
    assert payload["role"] == "customer"
    assert payload["permissions"] == ["customer.orders", "customer.profile"]
    assert "catalog.write" not in payload["permissions"]
    with Session(auth_engine) as session:
        standard_session = session.scalar(
            select(OwnerSession).where(
                OwnerSession.user_id == UUID(payload["user_id"]),
                OwnerSession.is_persistent.is_(False),
            )
        )
        assert standard_session is not None
        assert standard_session.absolute_expires_at - standard_session.authenticated_at == timedelta(hours=12)

    persistent_login = await auth_client.post(
        "/api/v1/customer/auth/login",
        headers={"Origin": "http://test"},
        json={
            "email": "customer@example.com",
            "keep_signed_in": True,
            "password": "correct horse battery staple",
        },
    )
    assert persistent_login.status_code == 200
    assert "Max-Age=2592000" in persistent_login.headers["set-cookie"]
    persistent_payload = persistent_login.json()
    with Session(auth_engine) as session:
        persistent_session = session.scalar(
            select(OwnerSession).where(
                OwnerSession.user_id == UUID(payload["user_id"]),
                OwnerSession.is_persistent.is_(True),
            )
        )
        assert persistent_session is not None
        assert persistent_session.absolute_expires_at - persistent_session.authenticated_at == timedelta(days=30)
        assert persistent_session.idle_expires_at == persistent_session.absolute_expires_at

    owner_denied = await auth_client.post(
        "/api/v1/owner/auth/login",
        headers={"Origin": "http://test"},
        json={"email": "customer@example.com", "password": "correct horse battery staple"},
    )
    assert owner_denied.status_code == 401

    legacy_order_id: int
    with Session(auth_engine) as session, session.begin():
        customer = session.scalar(select(JdsUser).where(JdsUser.primary_email == "customer@example.com"))
        assert customer is not None
        registered_profile = session.get(CustomerProfile, customer.id)
        assert registered_profile is not None
        session.delete(registered_profile)
        legacy_now = datetime.now(timezone.utc)
        legacy_order = Order(
            customer_user_id=customer.id,
            idempotency_key="legacy-customer-profile-reconciliation",
            request_fingerprint="a" * 64,
            public_access_token="legacy-customer-profile-token",
            status="paid",
            guest_name=customer.display_name,
            guest_email=customer.primary_email,
            guest_phone="+15198816869",
            requested_pickup_at=legacy_now + timedelta(minutes=20),
            business_timezone="America/Toronto",
            currency="USD",
            subtotal_cents=500,
            tax_cents=0,
            total_cents=500,
            version=1,
            expires_at=legacy_now + timedelta(hours=1),
            created_at=legacy_now,
            updated_at=legacy_now,
        )
        session.add(legacy_order)
        session.flush()
        legacy_order_id = legacy_order.id

    initial_profile = await auth_client.get("/api/v1/customer/profile")
    assert initial_profile.status_code == 200
    assert initial_profile.headers["cache-control"] == "no-store"
    assert initial_profile.json()["email"] == "customer@example.com"
    assert initial_profile.json()["phone"] == "+15198816869"
    with Session(auth_engine) as session, session.begin():
        customer = session.scalar(select(JdsUser).where(JdsUser.primary_email == "customer@example.com"))
        assert customer is not None
        reconciled_profile = session.get(CustomerProfile, customer.id)
        assert reconciled_profile is not None
        assert reconciled_profile.phone == "+15198816869"
        session.delete(session.get(Order, legacy_order_id))
    updated = await auth_client.put(
        "/api/v1/customer/profile",
        headers={"Origin": "http://test", "X-CSRF-Token": persistent_payload["csrf_token"]},
        json={
            "name": "Returning Customer",
            "phone": "(519) 881-6869",
            "preferred_pickup_minutes": 20,
            "preferred_pickup_notes": "Side counter",
        },
    )
    assert updated.headers["cache-control"] == "no-store"
    assert updated.status_code == 200
    assert updated.json() == {
        "name": "Returning Customer",
        "email": "customer@example.com",
        "phone": "+15198816869",
        "preferred_pickup_minutes": 20,
        "preferred_pickup_notes": "Side counter",
    }

    now = datetime.now(timezone.utc)
    with Session(auth_engine) as session, session.begin():
        customer = session.scalar(select(JdsUser).where(JdsUser.primary_email == "customer@example.com"))
        assert customer is not None
        order = Order(
            customer_user_id=customer.id,
            idempotency_key="customer-history-order",
            request_fingerprint="b" * 64,
            public_access_token="customer-public-token",
            status="paid",
            fulfillment_status="completed",
            guest_name="Returning Customer",
            guest_email="customer@example.com",
            guest_phone="+15555550123",
            requested_pickup_at=now + timedelta(minutes=20),
            business_timezone="America/Toronto",
            currency="USD",
            subtotal_cents=500,
            tax_cents=0,
            total_cents=500,
            version=1,
            expires_at=now + timedelta(hours=1),
            created_at=now,
            updated_at=now,
            completed_at=now,
        )
        order.items.append(OrderItem(
            source_product_id=None,
            source_variant_id=None,
            product_slug="drip-coffee",
            product_name="Drip Coffee",
            variant_key="12oz",
            variant_name="12oz",
            base_unit_price_cents=500,
            unit_price_cents=500,
            quantity=1,
            line_subtotal_cents=500,
            sort_order=0,
            modifiers=[
                OrderItemModifier(
                    source_modifier_group_id=None,
                    source_modifier_option_id=None,
                    modifier_group_key="milk",
                    modifier_group_name="Milk",
                    modifier_option_key="whole-milk",
                    modifier_option_name="Whole milk",
                    price_adjustment_cents=0,
                    quantity=1,
                    sort_order=0,
                ),
                OrderItemModifier(
                    source_modifier_group_id=None,
                    source_modifier_option_id=None,
                    modifier_group_key="sugar",
                    modifier_group_name="Sugar",
                    modifier_option_key="sugar",
                    modifier_option_name="Sugar",
                    price_adjustment_cents=0,
                    quantity=2,
                    sort_order=1,
                ),
            ],
        ))
        session.add(order)
        session.flush()
        order_id = order.id
    history = await auth_client.get("/api/v1/customer/orders")
    assert history.status_code == 200
    assert history.json()[0]["id"] == order_id
    assert history.json()[0]["fulfillment_status"] == "completed"
    assert history.json()[0]["first_item"] == {
        "product_name": "Drip Coffee",
        "variant_name": "12oz",
        "quantity": 1,
        "modifiers": [
            {"group_name": "Milk", "option_name": "Whole milk", "quantity": 1},
            {"group_name": "Sugar", "option_name": "Sugar", "quantity": 2},
        ],
    }
    detail = await auth_client.get(f"/api/v1/customer/orders/{order_id}")
    assert detail.status_code == 200
    assert detail.json()["public_token"] == "customer-public-token"
    assert detail.json()["fulfillment_status"] == "completed"
    assert detail.json()["tax_name"] == "HST"

    logout = await auth_client.post(
        "/api/v1/customer/auth/logout",
        headers={"Origin": "http://test", "X-CSRF-Token": persistent_payload["csrf_token"]},
    )
    assert logout.status_code == 200
    assert (await auth_client.get("/api/v1/customer/auth/session")).status_code == 401
