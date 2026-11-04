"""Sign-in from a shop's own <slug>.<base domain> origin (beta finding #2).

PR #37 stopped requiring a stored hostname row for `<slug>.<base domain>`, so a shop printing the
short address could not sign anyone in. `require_trusted_origin` now accepts an `https` Origin that
names a live, public-ready shop under `JDS_STOREFRONT_BASE_DOMAIN` -- without requiring the Origin's
hostname to equal the API's own request host, because Canner's edge rewrites that host.

These tests pin both halves: the one accepted shape, and that everything else still fails closed.
"""
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.jds_auth.models import AuthRateLimitBucket, JdsUser, Organization
from app.platform.design import DesignService
from app.platform.models import BusinessProfile, StorefrontHostname
from app.tenancy.context import TenantContext, TenantResolutionSource
from tests.test_jds_auth import auth_client, auth_engine, auth_settings, fake_provider  # noqa: F401
from tests.test_v1_platform_isolation import make_storefront_operationally_ready

BASE_DOMAIN = "order.jdsstudio.ca"
PASSWORD = "correct horse battery staple"
# The hostname Canner's edge leaves on the request: the API's own, never the shop's.
CANNER_API_HOST = "jds-beta-api.canner.app"


def _add_shop(engine, *, live: bool, public_ready: bool = True) -> str:
    """A shop whose canonical verified hostname is NOT its standard short address.

    That is the shape PR #37 made usable: live and public-ready (so the storefront bootstrap
    resolves it from the slug alone), with no stored row for `<slug>.<base>`.
    """
    slug = f"zzshop-{uuid4().hex[:10]}"
    with Session(engine) as session:
        owner = session.scalar(select(JdsUser).where(JdsUser.primary_email == "owner@example.com"))
        organization = Organization(slug=slug, name="Zz Shop", lifecycle_status="active")
        if not live:
            organization.commercial_mode = "prospect"
        session.add(organization)
        session.flush()
        session.add(StorefrontHostname(
            organization_id=organization.id,
            hostname=f"{slug}.legacy.example.test",
            status="verified",
            is_canonical=True,
        ))
        session.flush()
        if public_ready:
            # Also writes the business profile, hours, catalog, payment and published design.
            make_storefront_operationally_ready(session, organization.id, owner.id)
        else:
            # A published design only: hours, catalog and payment stay missing, so not ready.
            session.add(BusinessProfile(
                organization_id=organization.id, display_name="Zz Shop",
                timezone="America/Toronto", currency="CAD",
                pickup_instructions="Pick up at the counter.",
            ))
            session.flush()
            DesignService(session, TenantContext(
                organization_id=organization.id, organization_slug=slug,
                source=TenantResolutionSource.AUTHENTICATED_MEMBERSHIP,
            )).publish(owner.id)
            session.commit()
    return slug


async def _login(client, *, origin=None, request_host="test"):
    headers = {"Host": request_host}
    if origin is not None:
        headers["Origin"] = origin
    return await client.post(
        "/api/v1/owner/auth/login",
        headers=headers,
        json={"email": "owner@example.com", "password": PASSWORD},
    )


def _assert_origin_invalid(response):
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "origin_invalid"


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_live_shop_origin_is_accepted_even_though_the_request_host_is_the_api(
    auth_client, auth_engine, monkeypatch,
):
    """The Canner case: Origin names the shop, the request host is the API's own hostname."""
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", BASE_DOMAIN)
    slug = _add_shop(auth_engine, live=True)
    response = await _login(
        auth_client,
        origin=f"https://{slug}.{BASE_DOMAIN}",
        request_host=CANNER_API_HOST,
    )
    assert response.status_code == 200, response.text
    assert response.json()["authenticated"] is True


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_live_shop_origin_is_accepted_against_the_app_host_too(
    auth_client, auth_engine, monkeypatch,
):
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", BASE_DOMAIN)
    slug = _add_shop(auth_engine, live=True)
    response = await _login(auth_client, origin=f"https://{slug}.{BASE_DOMAIN}", request_host="jds-beta-web.canner.app")
    assert response.status_code == 200, response.text


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_unknown_subdomain_origin_is_rejected(auth_client, auth_engine, monkeypatch):
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", BASE_DOMAIN)
    _add_shop(auth_engine, live=True)
    _assert_origin_invalid(await _login(
        auth_client,
        origin=f"https://no-such-shop-{uuid4().hex[:8]}.{BASE_DOMAIN}",
        request_host=CANNER_API_HOST,
    ))


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_shop_origin_that_is_not_live_is_rejected(auth_client, auth_engine, monkeypatch):
    """A demo/prospect shop must not be a trusted origin."""
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", BASE_DOMAIN)
    slug = _add_shop(auth_engine, live=False)
    _assert_origin_invalid(await _login(
        auth_client, origin=f"https://{slug}.{BASE_DOMAIN}", request_host=CANNER_API_HOST,
    ))


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_shop_origin_that_is_live_but_not_public_ready_is_rejected(
    auth_client, auth_engine, monkeypatch,
):
    """A shop still in setup must not be a trusted origin."""
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", BASE_DOMAIN)
    slug = _add_shop(auth_engine, live=True, public_ready=False)
    _assert_origin_invalid(await _login(
        auth_client, origin=f"https://{slug}.{BASE_DOMAIN}", request_host=CANNER_API_HOST,
    ))


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_shop_origin_for_a_shop_that_was_switched_to_demo_is_rejected(
    auth_client, auth_engine, monkeypatch,
):
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", BASE_DOMAIN)
    slug = _add_shop(auth_engine, live=True)
    with Session(auth_engine) as session:
        organization = session.scalar(select(Organization).where(Organization.slug == slug))
        organization.commercial_mode = "prospect"
        session.commit()
    _assert_origin_invalid(await _login(
        auth_client, origin=f"https://{slug}.{BASE_DOMAIN}", request_host=CANNER_API_HOST,
    ))


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_cross_site_origin_against_a_live_shop_is_rejected(auth_client, auth_engine, monkeypatch):
    """A hostile page's own Origin keeps failing, even while a real shop is live."""
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", BASE_DOMAIN)
    _add_shop(auth_engine, live=True)
    for origin in (
        "https://evil.example",
        f"https://evil.example.{BASE_DOMAIN}",
        f"https://{BASE_DOMAIN}",
        f"https://www.{BASE_DOMAIN}",
        "https://evil.example/?next=ok",
    ):
        _assert_origin_invalid(await _login(auth_client, origin=origin, request_host=CANNER_API_HOST))


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_null_and_missing_origin_are_rejected(auth_client, auth_engine, monkeypatch):
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", BASE_DOMAIN)
    _add_shop(auth_engine, live=True)
    _assert_origin_invalid(await _login(auth_client, origin="null", request_host=CANNER_API_HOST))
    _assert_origin_invalid(await _login(auth_client, origin="", request_host=CANNER_API_HOST))
    _assert_origin_invalid(await _login(auth_client, origin=None, request_host=CANNER_API_HOST))


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_two_level_host_origin_is_rejected(auth_client, auth_engine, monkeypatch):
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", BASE_DOMAIN)
    slug = _add_shop(auth_engine, live=True)
    _assert_origin_invalid(await _login(
        auth_client, origin=f"https://extra.{slug}.{BASE_DOMAIN}", request_host=CANNER_API_HOST,
    ))


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_http_shop_origin_is_rejected(auth_client, auth_engine, monkeypatch):
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", BASE_DOMAIN)
    slug = _add_shop(auth_engine, live=True)
    _assert_origin_invalid(await _login(
        auth_client, origin=f"http://{slug}.{BASE_DOMAIN}", request_host=CANNER_API_HOST,
    ))


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_shop_origin_does_not_leak_into_unrelated_hosts(auth_client, auth_engine, monkeypatch):
    """Another platform's domain that merely ends in the same words is not one of our shops."""
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", BASE_DOMAIN)
    slug = _add_shop(auth_engine, live=True)
    for origin in (
        f"https://{slug}.{BASE_DOMAIN}.evil.example",
        f"https://not{BASE_DOMAIN}",
        f"https://{slug}.order.jdsstudio.ca.evil.example",
    ):
        _assert_origin_invalid(await _login(auth_client, origin=origin, request_host=CANNER_API_HOST))


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_rate_limiter_still_owns_its_transaction_after_the_origin_check(
    auth_client, auth_engine, monkeypatch,
):
    """The origin check must not leave a transaction open for the login rate limiter.

    A read in the origin check autobegins a transaction; before this was released, the limiter's
    own `session.begin()` raised "A transaction is already begun on this Session" and every
    sign-in from a shop origin failed with a 500.
    """
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", BASE_DOMAIN)
    slug = _add_shop(auth_engine, live=True)
    origin = f"https://{slug}.{BASE_DOMAIN}"
    for attempt in range(2):
        response = await _login(auth_client, origin=origin, request_host=CANNER_API_HOST)
        assert response.status_code == 200, (attempt, response.text)
    # Both attempts were actually counted: the limiter ran and committed its own transaction.
    with Session(auth_engine) as session:
        buckets = session.scalar(
            select(func.count()).select_from(AuthRateLimitBucket)
            .where(AuthRateLimitBucket.request_count >= 1)
        )
    assert buckets >= 1


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_csrf_is_still_required_from_a_live_shop_origin(auth_client, auth_engine, monkeypatch):
    """Accepting the Origin must not weaken CSRF: a state-changing call still needs its token."""
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", BASE_DOMAIN)
    slug = _add_shop(auth_engine, live=True)
    origin = f"https://{slug}.{BASE_DOMAIN}"
    login = await _login(auth_client, origin=origin, request_host=CANNER_API_HOST)
    assert login.status_code == 200, login.text
    denied = await auth_client.post(
        "/api/v1/owner/auth/invitations",
        headers={"Host": CANNER_API_HOST, "Origin": origin},
        json={"email": "csrf-probe@example.test", "role": "manager"},
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["detail"]["code"] == "csrf_invalid"


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_shop_origin_with_a_non_default_port_or_userinfo_is_rejected(
    auth_client, auth_engine, monkeypatch,
):
    """An Origin is scheme://host[:port]; anything odd about the authority is not a shop."""
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", BASE_DOMAIN)
    slug = _add_shop(auth_engine, live=True)
    host = f"{slug}.{BASE_DOMAIN}"
    for origin in (
        f"https://{host}:8443",
        f"https://user:pw@{host}",
        f"https://{host}/path",
    ):
        _assert_origin_invalid(await _login(auth_client, origin=origin, request_host=CANNER_API_HOST))
    # The default https port is the same origin and still passes.
    accepted = await _login(auth_client, origin=f"https://{host}:443", request_host=CANNER_API_HOST)
    assert accepted.status_code == 200, accepted.text
