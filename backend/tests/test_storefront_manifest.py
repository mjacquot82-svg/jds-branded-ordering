"""The per-shop install manifest (beta finding: /manifest.webmanifest 404'd on every storefront).

The manifest resolves exactly like the storefront bootstrap -- `?shop=` or the shop's own host --
so a browser's install prompt always describes the shop the visitor is on, and an unresolved
storefront is a 404 rather than another shop's name.
"""
from __future__ import annotations

import json
from uuid import uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.jds_auth.models import JdsUser, Organization
from app.main import create_app
from app.platform.design import DesignService
from app.platform.models import StorefrontHostname
from app.tenancy.context import TenantContext, TenantResolutionSource
from tests.test_migrations import make_alembic_config
from tests.test_v1_platform_isolation import make_storefront_operationally_ready


BASE_DOMAIN = "order.jdsstudio.ca"
ENDPOINT = "/api/v1/storefront/manifest.webmanifest"


def _add_shop(engine, *, display_name: str, tagline: str, short_name: str | None, primary: str, background: str, live: bool = True) -> str:
    slug = f"zzmanifest-{uuid4().hex[:8]}"
    with Session(engine) as session:
        owner = session.scalar(select(JdsUser).where(JdsUser.primary_email == "owner@example.com"))
        if owner is None:
            owner = JdsUser(primary_email="owner@example.com", display_name="Owner")
            session.add(owner)
            session.flush()
        organization = Organization(slug=slug, name=display_name, lifecycle_status="active")
        if not live:
            organization.commercial_mode = "prospect"
        session.add(organization)
        session.flush()
        session.add(StorefrontHostname(
            organization_id=organization.id, hostname=f"{slug}.legacy.example.test",
            status="verified", is_canonical=True,
        ))
        session.flush()
        make_storefront_operationally_ready(session, organization.id, owner.id)
        context = TenantContext(organization_id=organization.id, organization_slug=slug, source=TenantResolutionSource.AUTHENTICATED_MEMBERSHIP)
        service = DesignService(session, context)
        workspace = service.workspace()
        config = dict(workspace.draft_config)
        config["displayName"] = display_name
        config["tagline"] = tagline
        config["colors"] = {**config["colors"], "primary": primary, "background": background}
        pwa = dict(config.get("pwa") or {})
        if short_name is not None:
            pwa["shortName"] = short_name
        pwa["themeColor"] = primary
        pwa["backgroundColor"] = background
        config["pwa"] = pwa
        session.commit()
        service.save(config, workspace.revision, owner.id)
        service.publish(owner.id)
        session.commit()
    return slug


@pytest.fixture
def manifest_db(postgresql_url, monkeypatch, tmp_path):
    command.upgrade(make_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    monkeypatch.setenv("JDS_MEDIA_STORAGE", "local")
    monkeypatch.setenv("JDS_LOCAL_MEDIA_ROOT", str(tmp_path))
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", BASE_DOMAIN)
    monkeypatch.setenv("JDS_PILOT_SHOP_LINKS", "true")
    monkeypatch.setenv("JDS_ENVIRONMENT", "beta")
    # Each test builds its own shops; clearing organizations (and dependents) keeps the shared
    # test database at a known state without leaving half-deleted tenants behind.
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE organizations CASCADE"))
    yield engine
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE organizations CASCADE"))
    engine.dispose()


def _client(database_url):
    return TestClient(create_app(database_url))


@pytest.mark.postgresql
def test_manifest_describes_the_shop_named_by_the_shop_parameter(manifest_db, postgresql_url):
    slug = _add_shop(manifest_db, display_name="Manifest Café", tagline="Coffee and kindness",
                     short_name=None, primary="#1e66d0", background="#f6f1ea")
    with _client(postgresql_url) as client:
        response = client.get(f"{ENDPOINT}?shop={slug}")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/manifest+json")
    assert response.headers["cache-control"] in {"no-store", "public, max-age=60"}
    body = response.json()
    assert body["name"] == "Manifest Café"
    assert body["theme_color"] == "#1e66d0"
    assert body["background_color"] == "#f6f1ea"
    assert body["start_url"] == "/" and body["scope"] == "/" and body["display"] == "standalone"
    # No explicit short name in the design, so a fit-safe label comes from the shop name.
    assert body["short_name"] == "Manifest"
    assert body["id"] == f"/{slug}"
    assert [icon["sizes"] for icon in body["icons"]] == ["192x192", "512x512", "192x192", "512x512"]
    assert {icon["purpose"] for icon in body["icons"]} == {"any", "maskable"}
    for icon in body["icons"]:
        assert icon["src"].startswith("/api/v1/storefront/icon/")
        # The generated install icon names the shop, so it resolves on the shop's own address.
        assert f"shop={slug}" in icon["src"]


@pytest.mark.postgresql
def test_manifest_describes_the_shop_named_by_its_own_host(manifest_db, postgresql_url):
    slug = _add_shop(manifest_db, display_name="Host Café", tagline="Baked here",
                     short_name=None, primary="#4a5d4e", background="#ffffff")
    with _client(postgresql_url) as client:
        response = client.get(ENDPOINT, headers={"Host": f"{slug}.{BASE_DOMAIN}"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Host Café"
    assert body["id"] == f"/{slug}"


@pytest.mark.postgresql
def test_manifest_never_leaks_another_tenant(manifest_db, postgresql_url):
    first = _add_shop(manifest_db, display_name="Alpha Roast", tagline="A", short_name=None,
                      primary="#111111", background="#ffffff")
    second = _add_shop(manifest_db, display_name="Beta Bake", tagline="B", short_name=None,
                       primary="#222222", background="#fafafa")
    with _client(postgresql_url) as client:
        alpha = client.get(f"{ENDPOINT}?shop={first}").json()
        beta = client.get(f"{ENDPOINT}?shop={second}").json()
    assert alpha["name"] == "Alpha Roast" and alpha["theme_color"] == "#111111"
    assert beta["name"] == "Beta Bake" and beta["theme_color"] == "#222222"
    assert "Alpha" not in json.dumps(beta) and "Beta" not in json.dumps(alpha)
    assert alpha["id"] != beta["id"]


@pytest.mark.postgresql
def test_unknown_shop_or_host_is_not_found(manifest_db, postgresql_url):
    _add_shop(manifest_db, display_name="Real Café", tagline="Real", short_name=None,
              primary="#123456", background="#ffffff")
    missing = f"no-such-shop-{uuid4().hex[:8]}"
    with _client(postgresql_url) as client:
        for response in (
            client.get(f"{ENDPOINT}?shop={missing}"),
            client.get(ENDPOINT, headers={"Host": f"{missing}.{BASE_DOMAIN}"}),
            client.get(ENDPOINT, headers={"Host": "jds-beta-web.canner.app"}),
        ):
            assert response.status_code == 404, response.text
            assert response.json()["detail"]["code"] == "tenant_not_found"


@pytest.mark.postgresql
def test_a_shop_that_is_not_live_has_no_manifest(manifest_db, postgresql_url):
    slug = _add_shop(manifest_db, display_name="Draft Café", tagline="Soon", short_name=None,
                     primary="#654321", background="#ffffff", live=False)
    with _client(postgresql_url) as client:
        response = client.get(ENDPOINT, headers={"Host": f"{slug}.{BASE_DOMAIN}"})
    assert response.status_code == 404, response.text


def test_short_name_is_a_fit_safe_label_from_the_shop_name():
    from app.api.v1.platform import _manifest_short_name

    # A configured short name wins.
    assert _manifest_short_name("ZZ Test Cafe (Grok QA)", "ZZ") == "ZZ"
    # The design default is not a shop name, so the shop's first words are used instead.
    assert _manifest_short_name("ZZ Test Cafe (Grok QA)", "Order") == "ZZ Test Cafe"
    assert _manifest_short_name("Blue Door Coffee House", None) == "Blue Door"
    assert _manifest_short_name("One", "Your business") == "One"
    assert _manifest_short_name("", None) == "Order"
    for name in ("ZZ Test Cafe (Grok QA)", "A Very Long Coffee Shop Name That Never Ends"):
        assert 1 <= len(_manifest_short_name(name, "Order")) <= 30
