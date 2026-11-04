"""Sign-in from a shop's own <slug>.<base domain> address (beta finding #2).

PR #37 stopped requiring a stored hostname row for `<slug>.<base domain>`, but
`require_trusted_origin` still only trusted FRONTEND_URL or a verified row, so a shop that
printed the short address could not sign anyone in. These tests pin the one case added
(`_is_hosted_shop_origin`) and that everything else still fails closed.
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jds_auth.models import JdsUser
from app.jds_auth.provider import ProviderAuthentication, ProviderIdentity
from app.platform.design import DEFAULT_CONFIG, DesignService
from app.platform.models import BusinessProfile, StorefrontHostname
from app.tenancy.context import TenantContext, TenantResolutionSource
from app.jds_auth.models import Organization
from tests.test_jds_auth import auth_client, auth_engine, auth_settings, fake_provider  # noqa: F401
from tests.test_v1_platform_isolation import make_storefront_operationally_ready

BASE_DOMAIN = "order.jdsstudio.ca"
PASSWORD = "correct horse battery staple"


def _add_shop(engine, *, live: bool, public_ready: bool = True) -> str:
    """A shop whose canonical verified hostname is NOT its standard short address.

    That is the exact shape the old check could not see: live and public-ready (so the
    storefront bootstrap resolves it from the slug), but with no stored row for
    `<slug>.<base>`, which PR #37 made unnecessary.
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


async def _login(client, *, shop_host: str, origin: str):
    return await client.post(
        "/api/v1/owner/auth/login",
        headers={"Host": shop_host, "Origin": origin},
        json={"email": "owner@example.com", "password": PASSWORD},
    )


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_live_shop_sign_in_is_accepted_from_its_own_short_address(
    auth_client, auth_engine, monkeypatch,
):
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", BASE_DOMAIN)
    slug = _add_shop(auth_engine, live=True)
    host = f"{slug}.{BASE_DOMAIN}"
    response = await _login(auth_client, shop_host=host, origin=f"https://{host}")
    assert response.status_code == 200, response.text
    assert response.json()["authenticated"] is True


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_unknown_subdomain_is_still_rejected(auth_client, auth_engine, monkeypatch):
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", BASE_DOMAIN)
    _add_shop(auth_engine, live=True)
    host = f"no-such-shop-{uuid4().hex[:8]}.{BASE_DOMAIN}"
    response = await _login(auth_client, shop_host=host, origin=f"https://{host}")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "origin_invalid"


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_shop_that_is_not_live_or_not_ready_is_rejected(
    auth_client, auth_engine, monkeypatch,
):
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", BASE_DOMAIN)
    prospect = _add_shop(auth_engine, live=False)
    unready = _add_shop(auth_engine, live=True, public_ready=False)
    for slug in (prospect, unready):
        host = f"{slug}.{BASE_DOMAIN}"
        response = await _login(auth_client, shop_host=host, origin=f"https://{host}")
        assert response.status_code == 403, (slug, response.text)
        assert response.json()["detail"]["code"] == "origin_invalid"


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_two_level_host_is_still_rejected(auth_client, auth_engine, monkeypatch):
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", BASE_DOMAIN)
    slug = _add_shop(auth_engine, live=True)
    host = f"extra.{slug}.{BASE_DOMAIN}"
    response = await _login(auth_client, shop_host=host, origin=f"https://{host}")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "origin_invalid"


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_http_origin_is_still_rejected(auth_client, auth_engine, monkeypatch):
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", BASE_DOMAIN)
    slug = _add_shop(auth_engine, live=True)
    host = f"{slug}.{BASE_DOMAIN}"
    response = await _login(auth_client, shop_host=host, origin=f"http://{host}")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "origin_invalid"


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_origin_that_is_not_the_request_host_is_rejected(auth_client, auth_engine, monkeypatch):
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", BASE_DOMAIN)
    victim = _add_shop(auth_engine, live=True)
    sibling = _add_shop(auth_engine, live=True)
    # A sibling shop's live address is a first-party JDS origin, but not THIS request's host:
    # it must not be able to post to another shop's sign-in.
    response = await _login(
        auth_client,
        shop_host=f"{victim}.{BASE_DOMAIN}",
        origin=f"https://{sibling}.{BASE_DOMAIN}",
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "origin_invalid"
    # And a shop origin against the app host must not pass either.
    response = await _login(
        auth_client,
        shop_host="jds-beta-web.canner.app",
        origin=f"https://{victim}.{BASE_DOMAIN}",
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "origin_invalid"
