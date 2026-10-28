"""M3.1: reading the session must not rotate the CSRF token (multi-tab saves).

Bug guarded here: ``GET /api/v1/owner/auth/session`` called ``AuthenticationService.rotate_csrf``, which
minted a fresh random CSRF token and overwrote ``owner_sessions.csrf_token_hash`` on every session read.
The frontend reads the session on load, so opening or reloading a second tab silently invalidated the token
held by every other open tab of the same login, and their next save failed with ``403 csrf_invalid``.

The CSRF token is now bound to the session (HMAC of the opaque session token under the server pepper). It is
stable for the life of the session, and a new session (login, organization switch) gets a new one. The
negative tests below pin that validation is unchanged: a missing, forged, other-session or post-logout token
is still refused, and a valid token never crosses tenants.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.models import Product
from app.jds_auth.models import OwnerSession
from app.jds_auth.security import create_secret, derive_csrf_token, hash_secret
from app.jds_auth.service import AuthenticationService
from app.main import create_app
from app.platform.models import DesignWorkspace
from app.jds_auth.provider import ProviderIdentity
from tests.test_jds_auth import auth_client, auth_engine, auth_settings, fake_provider  # noqa: F401  (fixtures)
from tests.test_self_service_demo_funnel import (  # noqa: F401  (fixtures)
    DemoIdentityProvider,
    _signup,
    demo_ctx,
    demo_engine,
    demo_settings,
)

PASSWORD = "correct horse battery staple"  # the password _signup registers
ORIGIN = {"Origin": "http://test"}
SESSION = "/api/v1/owner/auth/session"
DESIGN = "/api/v1/owner/design"


@pytest.fixture
async def csrf_app(demo_ctx):
    engine, settings, provider = demo_ctx
    application = create_app(str(engine.url.render_as_string(hide_password=False)), auth_settings=settings, auth_provider=provider)
    try:
        yield application, settings, provider, engine
    finally:
        application.state.db_engine.dispose()


def new_prospect(engine, settings, provider, label: str) -> str:
    email = f"csrf-{label}-{uuid4().hex[:8]}@example.com"
    with Session(engine) as session:
        _signup(session, settings, provider, email, business=f"CSRF {label} Café")
    return email


def tab(application, settings=None, token: str | None = None) -> AsyncClient:
    """One browser tab. Tabs of one login share the session cookie, as a browser shares its cookie jar."""
    client = AsyncClient(transport=ASGITransport(app=application), base_url="http://test")
    if token is not None:
        client.cookies.set(settings.session_cookie_name, token)
    return client


async def login(application, settings, email: str) -> tuple[str, str]:
    """Real HTTP login. Returns (session cookie value, CSRF token from the login response)."""
    # A distinct client address per login keeps the per-IP login rate limit (persisted in the DB) out of the way.
    address = (f"10.31.{uuid4().int % 250}.{uuid4().int % 250 + 1}", 50000)
    async with AsyncClient(transport=ASGITransport(app=application, client=address), base_url="http://test") as client:
        response = await client.post("/api/v1/owner/auth/login", headers=ORIGIN, json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    token = response.cookies.get(settings.session_cookie_name)
    assert token
    return token, response.json()["csrf_token"]


def writes(csrf: str | None) -> dict[str, str]:
    return {**ORIGIN, **({"X-CSRF-Token": csrf} if csrf is not None else {})}


async def save_tagline(client: AsyncClient, csrf: str | None, tagline: str):
    design = (await client.get(DESIGN)).json()
    return await client.put(DESIGN, headers=writes(csrf), json={"revision": design["revision"], "config": {**design["config"], "tagline": tagline}})


def stored_tagline(engine, organization_id: str) -> str | None:
    with Session(engine) as session:
        workspace = session.get(DesignWorkspace, organization_id)
        return (workspace.draft_config or {}).get("tagline") if workspace else None


def assert_csrf_refused(response) -> None:
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "csrf_invalid"


# --- the regression -----------------------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_session_read_in_another_tab_does_not_break_saves_in_the_first_tab(csrf_app) -> None:
    application, settings, provider, engine = csrf_app
    email = new_prospect(engine, settings, provider, "tabs")
    token, login_csrf = await login(application, settings, email)
    async with tab(application, settings, token) as tab_a, tab(application, settings, token) as tab_b:
        # Tab A loads: it reads the session and keeps that CSRF token in memory.
        session_a = await tab_a.get(SESSION)
        assert session_a.status_code == 200
        csrf_a = session_a.json()["csrf_token"]
        organization_id = session_a.json()["organization_id"]

        # Tab B opens (and is refocused/reloaded twice). This is the read that used to rotate the token.
        for _ in range(3):
            session_b = await tab_b.get(SESSION)
            assert session_b.status_code == 200
        csrf_b = session_b.json()["csrf_token"]

        # Tab A saves with the token it already had: must succeed and persist.
        saved_a = await save_tagline(tab_a, csrf_a, "Saved from tab A")
        assert saved_a.status_code == 200, saved_a.text
        assert stored_tagline(engine, organization_id) == "Saved from tab A"
        assert (await tab_b.get(DESIGN)).json()["config"]["tagline"] == "Saved from tab A"

        # Tab A also updates a product with the same token (a second, unrelated owner save).
        catalog = (await tab_a.get("/api/v1/owner/catalog")).json()
        product, category = catalog["products"][0], catalog["categories"][0]
        renamed = await tab_a.put(
            f"/api/v1/owner/catalog/products/{int(product['id'])}",
            headers=writes(csrf_a),
            json={"slug": product["slug"], "name": "Tab A Renamed", "base_price_cents": product.get("base_price_cents", 400), "category_id": int(category["id"])},
        )
        assert renamed.status_code == 200, renamed.text
        with Session(engine) as session:
            assert session.scalar(select(Product.name).where(Product.id == int(product["id"]))) == "Tab A Renamed"

        # Tab B saves with the token it read: also succeeds.
        saved_b = await save_tagline(tab_b, csrf_b, "Saved from tab B")
        assert saved_b.status_code == 200, saved_b.text
        assert stored_tagline(engine, organization_id) == "Saved from tab B"

        # And tab A can still save after tab B's save and yet another session read.
        assert (await tab_b.get(SESSION)).status_code == 200
        assert (await save_tagline(tab_a, csrf_a, "Tab A again")).status_code == 200
        assert stored_tagline(engine, organization_id) == "Tab A again"

    # One login, one token: every tab sees the same value, including the tab that logged in.
    assert csrf_a == csrf_b == login_csrf


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_session_read_does_not_write_a_new_csrf_hash(csrf_app) -> None:
    application, settings, provider, engine = csrf_app
    token, _csrf = await login(application, settings, new_prospect(engine, settings, provider, "nowrite"))
    token_hash = hash_secret(token, settings.session_pepper)

    def stored_csrf_hash() -> str:
        with Session(engine) as session:
            return session.scalar(select(OwnerSession.csrf_token_hash).where(OwnerSession.token_hash == token_hash))

    before = stored_csrf_hash()
    async with tab(application, settings, token) as client:
        for _ in range(3):
            assert (await client.get(SESSION)).status_code == 200
    assert stored_csrf_hash() == before


# --- CSRF still protects --------------------------------------------------------------------------------------
# These use the token from the session's most recent read, so they hold on the old (rotating) code too:
# they pin behaviour that must not change, and they pass before and after the fix.


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_missing_and_forged_csrf_tokens_are_still_refused(csrf_app) -> None:
    application, settings, provider, engine = csrf_app
    token, csrf = await login(application, settings, new_prospect(engine, settings, provider, "forged"))
    async with tab(application, settings, token) as client:
        organization_id = (await client.get(SESSION)).json()["organization_id"]
        before = stored_tagline(engine, organization_id)
        assert_csrf_refused(await save_tagline(client, None, "no header"))
        assert_csrf_refused(await save_tagline(client, "", "empty header"))
        for forged in ("garbage", create_secret(), csrf[:-1] + ("A" if csrf[-1] != "A" else "B"), csrf.upper(), hash_secret(token, settings.session_pepper), token):
            assert_csrf_refused(await save_tagline(client, forged, "forged"))
        # A token derived under a different pepper (e.g. another environment) is not valid here.
        assert_csrf_refused(await save_tagline(client, derive_csrf_token(token, "x" * 48), "wrong pepper"))
        assert stored_tagline(engine, organization_id) == before
        # A valid token with a foreign Origin is still refused (origin check is independent of the token).
        design = (await client.get(DESIGN)).json()
        foreign = await client.put(DESIGN, headers={"Origin": "https://evil.example", "X-CSRF-Token": csrf}, json={"revision": design["revision"], "config": design["config"]})
        assert foreign.status_code == 403


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_token_from_another_users_session_is_refused(csrf_app) -> None:
    application, settings, provider, engine = csrf_app
    token_1, _ = await login(application, settings, new_prospect(engine, settings, provider, "user1"))
    token_2, _ = await login(application, settings, new_prospect(engine, settings, provider, "user2"))
    async with tab(application, settings, token_1) as client_1, tab(application, settings, token_2) as client_2:
        session_1, session_2 = (await client_1.get(SESSION)).json(), (await client_2.get(SESSION)).json()
        org_1, csrf_1 = session_1["organization_id"], session_1["csrf_token"]
        org_2, csrf_2 = session_2["organization_id"], session_2["csrf_token"]
        assert csrf_1 != csrf_2
        before_1, before_2 = stored_tagline(engine, org_1), stored_tagline(engine, org_2)
        assert_csrf_refused(await save_tagline(client_1, csrf_2, "user 2 token on user 1 session"))
        assert_csrf_refused(await save_tagline(client_2, csrf_1, "user 1 token on user 2 session"))
        assert (stored_tagline(engine, org_1), stored_tagline(engine, org_2)) == (before_1, before_2)
        # Each still works with its own token.
        assert (await save_tagline(client_1, csrf_1, "user 1 own")).status_code == 200
        assert (await save_tagline(client_2, csrf_2, "user 2 own")).status_code == 200


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_token_is_dead_after_logout_in_every_tab(csrf_app) -> None:
    application, settings, provider, engine = csrf_app
    token, _ = await login(application, settings, new_prospect(engine, settings, provider, "logout"))
    async with tab(application, settings, token) as tab_a, tab(application, settings, token) as tab_b:
        current = (await tab_a.get(SESSION)).json()
        organization_id, csrf = current["organization_id"], current["csrf_token"]
        assert (await save_tagline(tab_a, csrf, "before logout")).status_code == 200
        before = stored_tagline(engine, organization_id)
        assert (await tab_b.post("/api/v1/owner/auth/logout", headers=writes(csrf))).status_code == 200
        # Tab A still has the cookie value and the token in memory (a browser would have dropped the cookie,
        # an attacker replaying both would not). The session is revoked, so auth fails before CSRF.
        after = await tab_a.put(DESIGN, headers=writes(csrf), json={"revision": 1, "config": {"tagline": "after logout"}})
        assert after.status_code == 401
        assert after.json()["detail"]["code"] == "session_expired"
        assert (await tab_a.get(SESSION)).status_code == 401
        assert stored_tagline(engine, organization_id) == before


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_fresh_login_issues_a_new_session_and_csrf_token(csrf_app) -> None:
    application, settings, provider, engine = csrf_app
    email = new_prospect(engine, settings, provider, "relogin")
    old_token, old_csrf = await login(application, settings, email)
    new_token, new_csrf = await login(application, settings, email)
    # Session-fixation defence: a login always issues a new opaque session and a new CSRF token.
    assert new_token != old_token
    assert new_csrf != old_csrf
    async with tab(application, settings, new_token) as client:
        new_csrf = (await client.get(SESSION)).json()["csrf_token"]
        assert new_csrf != old_csrf
        assert_csrf_refused(await save_tagline(client, old_csrf, "old session token on new session"))
        assert (await save_tagline(client, new_csrf, "new session token")).status_code == 200
    # Logging out the old session does not affect the new one, and the old one is dead.
    async with tab(application, settings, old_token) as old_client:
        assert (await old_client.post("/api/v1/owner/auth/logout", headers=writes(old_csrf))).status_code == 200
    async with tab(application, settings, old_token) as replay:  # replay the old cookie and token together
        assert (await replay.put(DESIGN, headers=writes(old_csrf), json={"revision": 1, "config": {"tagline": "old after logout"}})).status_code == 401
    async with tab(application, settings, new_token) as client:
        assert (await save_tagline(client, new_csrf, "new still works")).status_code == 200


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_valid_token_for_one_tenant_cannot_modify_another_tenants_data(csrf_app) -> None:
    application, settings, provider, engine = csrf_app
    token_1, _ = await login(application, settings, new_prospect(engine, settings, provider, "tenant1"))
    token_2, _ = await login(application, settings, new_prospect(engine, settings, provider, "tenant2"))
    async with tab(application, settings, token_1) as client_1, tab(application, settings, token_2) as client_2:
        session_1 = (await client_1.get(SESSION)).json()
        org_1, csrf_1 = session_1["organization_id"], session_1["csrf_token"]
        org_2 = (await client_2.get(SESSION)).json()["organization_id"]
        assert org_1 != org_2
        catalog_2 = (await client_2.get("/api/v1/owner/catalog")).json()
        product_2, category_2 = catalog_2["products"][0], catalog_2["categories"][0]
        tagline_2 = stored_tagline(engine, org_2)

        # Prospect 1's valid session + token aimed at prospect 2's product id: not found in prospect 1's tenant.
        attempt = await client_1.put(
            f"/api/v1/owner/catalog/products/{int(product_2['id'])}",
            headers=writes(csrf_1),
            json={"slug": product_2["slug"], "name": "Hijacked", "base_price_cents": 1, "category_id": int(category_2["id"])},
        )
        assert attempt.status_code == 404, attempt.text
        # Client-supplied tenant context is still rejected on a CSRF-valid write.
        design_1 = (await client_1.get(DESIGN)).json()
        spoofed = await client_1.put(DESIGN, headers={**writes(csrf_1), "X-Organization-Id": org_2}, json={"revision": design_1["revision"], "config": {**design_1["config"], "tagline": "Hijacked"}})
        assert spoofed.status_code == 403, spoofed.text
        assert spoofed.json()["detail"]["code"] == "tenant_context_invalid"
        # A normal save with prospect 1's token only changes prospect 1's design.
        assert (await save_tagline(client_1, csrf_1, "Tenant 1 only")).status_code == 200

    with Session(engine) as session:
        assert session.scalar(select(Product.name).where(Product.id == int(product_2["id"]))) == product_2["name"]
    assert stored_tagline(engine, org_2) == tagline_2
    assert stored_tagline(engine, org_1) == "Tenant 1 only"


# --- sessions issued before this change ---------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_pre_existing_session_is_rebound_once_then_stable(csrf_app) -> None:
    application, settings, provider, engine = csrf_app
    token, derived = await login(application, settings, new_prospect(engine, settings, provider, "legacy"))
    legacy_csrf = create_secret()  # what the old code stored: a random token unrelated to the session token
    with Session(engine) as session, session.begin():
        row = session.scalar(select(OwnerSession).where(OwnerSession.token_hash == hash_secret(token, settings.session_pepper)))
        row.csrf_token_hash = hash_secret(legacy_csrf, settings.session_pepper)
    async with tab(application, settings, token) as tab_a, tab(application, settings, token) as tab_b:
        # Until the first session read after deploy, the legacy token keeps working (no forced sign-out).
        assert (await save_tagline(tab_a, legacy_csrf, "legacy token")).status_code == 200
        # The first read re-binds the session to its derived token, once.
        first = (await tab_a.get(SESSION)).json()["csrf_token"]
        assert first == derived
        assert_csrf_refused(await save_tagline(tab_a, legacy_csrf, "legacy after rebind"))
        # From then on reads in any tab are stable.
        assert (await tab_b.get(SESSION)).json()["csrf_token"] == first
        assert (await save_tagline(tab_a, first, "stable after rebind")).status_code == 200


# --- the derivation itself ----------------------------------------------------------------------------------


def test_derived_csrf_token_is_stable_per_session_and_distinct_otherwise() -> None:
    pepper = "p" * 48
    token_a, token_b = create_secret(), create_secret()
    assert derive_csrf_token(token_a, pepper) == derive_csrf_token(token_a, pepper)
    assert derive_csrf_token(token_a, pepper) != derive_csrf_token(token_b, pepper)
    assert derive_csrf_token(token_a, pepper) != derive_csrf_token(token_a, "q" * 48)
    derived = derive_csrf_token(token_a, pepper)
    # Never equal to the session token or to the stored session-token hash, and URL/header safe.
    assert derived not in (token_a, hash_secret(token_a, pepper))
    assert len(derived) >= 43 and set(derived) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


@pytest.mark.postgresql
def test_service_session_csrf_is_idempotent(demo_ctx) -> None:
    engine, settings, provider = demo_ctx
    email = new_prospect(engine, settings, provider, "service")
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        issued = AuthenticationService(session, provider, settings).login(email, PASSWORD, now=now, user_agent="pytest", allowed_roles=frozenset({"owner", "manager", "staff"}))
    with Session(engine) as session:
        service = AuthenticationService(session, provider, settings)
        principal, first = service.session_csrf(issued.token, now=now)
        _principal, second = service.session_csrf(issued.token, now=now)
        assert first == second == issued.csrf_token
        service.verify_csrf(principal, first)


# --- customer sessions share the same service method ---------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_customer_session_read_in_another_tab_does_not_break_profile_save(auth_client, fake_provider, auth_settings) -> None:
    identity = dict(issuer=fake_provider.identity.issuer, subject="csrf-tab-customer", email="tabs@example.com")
    fake_provider.identity = ProviderIdentity(**identity, email_verified=False)
    registered = await auth_client.post("/api/v1/customer/auth/register", headers=ORIGIN, json={"display_name": "Tab Customer", "email": "tabs@example.com", "password": PASSWORD, "phone": "(519) 881-6869"})
    assert registered.status_code == 201
    fake_provider.identity = ProviderIdentity(**identity, email_verified=True)
    assert (await auth_client.post("/api/v1/customer/auth/verify-email", headers=ORIGIN, json={"token_hash": "t" * 32})).status_code == 200
    login_response = await auth_client.post("/api/v1/customer/auth/login", headers=ORIGIN, json={"email": "tabs@example.com", "password": PASSWORD})
    assert login_response.status_code == 200
    login_csrf = login_response.json()["csrf_token"]
    token = auth_client.cookies.get(auth_settings.customer_session_cookie_name)
    assert token

    application = auth_client._transport.app
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as tab_b:
        tab_b.cookies.set(auth_settings.customer_session_cookie_name, token)
        for _ in range(2):
            read = await tab_b.get("/api/v1/customer/auth/session")
            assert read.status_code == 200, read.text
        csrf_b = read.json()["csrf_token"]
    profile = {"name": "Saved From Tab A", "phone": "(519) 881-6869", "preferred_pickup_minutes": 15, "preferred_pickup_notes": ""}
    saved = await auth_client.put("/api/v1/customer/profile", headers=writes(login_csrf), json=profile)
    assert saved.status_code == 200, saved.text
    assert saved.json()["name"] == "Saved From Tab A"
    assert csrf_b == login_csrf
    assert_csrf_refused(await auth_client.put("/api/v1/customer/profile", headers=writes("garbage"), json=profile))
    assert_csrf_refused(await auth_client.put("/api/v1/customer/profile", headers=writes(None), json=profile))
