"""M3: owner/prospect requests must not starve or leak the DB connection pool.

Root cause guarded here: ``authenticated_owner_tenant`` was an ``async def`` dependency that opened a blocking
SQLAlchemy session *on the event loop*. Every owner request checks out three connections one after another
(auth session in the threadpool, tenant resolution, then the endpoint's catalog session, which is held until the
dependency teardown). Teardown is scheduled by the event loop, so when the pool was momentarily empty the tenant
checkout blocked the loop, no in-flight request could finish, and nothing could return its connection until
``QueuePool ... connection timed out``. These tests use a deliberately small pool so the starvation is
deterministic, and they pin fail-closed tenant behaviour.
"""
from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.orm import Session

from app.api.v1 import tenant_context as tenant_context_module
from app.catalog.models import Category, Product
from app.db.session import create_session_factory
from app.jds_auth.models import Membership
from app.main import create_app
from app.platform.media import LocalMediaStorage
from app.platform.models import MediaAsset
from tests.test_self_service_demo_funnel import (  # noqa: F401  (fixtures)
    DemoIdentityProvider,
    _signup,
    demo_ctx,
    demo_engine,
    demo_settings,
)

# Small on purpose: pool 2 + overflow 1 = 3 connections, far below the bursts below (>= 24 requests).
SMALL_POOL = dict(pool_size=2, max_overflow=1, pool_timeout=5)
BURST = 24
READ_PATHS = (
    "/api/v1/owner/catalog",
    "/api/v1/owner/design",
    "/api/v1/owner/design/versions",
    "/api/v1/owner/demo/status",
    "/api/v1/owner/media",
    "/api/v1/owner/onboarding",
    "/api/v1/owner/readiness",
    "/api/v1/owner/platform-capabilities",
)
LATTE = "starter:cafe-restaurant/latte@1"
MUFFIN = "starter:cafe-restaurant/muffin@1"


@dataclass
class PoolWatch:
    engine: object
    checkouts_on_event_loop: int = 0
    held: int = 0
    peak: int = 0

    def install(self, loop_thread: threading.Thread) -> None:
        lock = threading.Lock()

        @event.listens_for(self.engine, "checkout")
        def _checkout(*_args) -> None:
            with lock:
                self.held += 1
                self.peak = max(self.peak, self.held)
                if threading.current_thread() is loop_thread:
                    self.checkouts_on_event_loop += 1

        @event.listens_for(self.engine, "checkin")
        def _checkin(*_args) -> None:
            with lock:
                self.held -= 1

    def reset_peak(self) -> None:
        self.peak = self.held

    @property
    def checked_out(self) -> int:
        return self.engine.pool.checkedout()


def small_pool_app(url: str, settings, provider, **pool):
    application = create_app(url, auth_settings=settings, auth_provider=provider)
    application.state.db_engine.dispose()
    engine = create_engine(url, pool_pre_ping=True, **(pool or SMALL_POOL))
    application.state.db_engine = engine
    application.state.db_session_factory = create_session_factory(engine)
    return application, engine


@pytest.fixture
async def pool_app(demo_ctx, postgresql_url, tmp_path) -> AsyncIterator[tuple]:
    engine, settings, provider = demo_ctx
    application, small = small_pool_app(postgresql_url, settings, provider)
    application.state.media_storage = LocalMediaStorage(tmp_path)
    watch = PoolWatch(small)
    watch.install(threading.current_thread())
    try:
        yield application, settings, provider, engine, watch
    finally:
        small.dispose()


def prospect(engine, settings, provider, label: str):
    with Session(engine) as session:
        return _signup(session, settings, provider, f"pool-{label}-{uuid4().hex[:8]}@example.com", business=f"Pool {label} Café")


def client_for(application, settings, issued, *, raise_app_exceptions: bool = True) -> AsyncClient:
    client = AsyncClient(transport=ASGITransport(app=application, raise_app_exceptions=raise_app_exceptions), base_url="http://test")
    client.cookies.set(settings.session_cookie_name, issued.token)
    return client


def write_headers(issued) -> dict[str, str]:
    return {"Origin": "http://test", "X-CSRF-Token": issued.csrf_token}


async def gather_statuses(calls) -> tuple[list[int], list[BaseException]]:
    results = await asyncio.gather(*calls, return_exceptions=True)
    errors = [item for item in results if isinstance(item, BaseException)]
    return [item.status_code for item in results if not isinstance(item, BaseException)], errors


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_tenant_resolution_never_checks_out_a_connection_on_the_event_loop(pool_app) -> None:
    application, settings, provider, engine, watch = pool_app
    issued = prospect(engine, settings, provider, "loop")
    async with client_for(application, settings, issued) as client:
        for path in READ_PATHS:
            assert (await client.get(path)).status_code == 200, path
    assert watch.checkouts_on_event_loop == 0
    assert watch.checked_out == 0


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_sequential_and_concurrent_owner_requests_do_not_exhaust_or_leak_the_pool(pool_app) -> None:
    application, settings, provider, engine, watch = pool_app
    issued = prospect(engine, settings, provider, "burst")
    baseline = watch.checked_out
    async with client_for(application, settings, issued) as client:
        for index in range(40):  # many sequential session + tenant checks
            assert (await client.get(READ_PATHS[index % len(READ_PATHS)])).status_code == 200
        assert watch.checked_out == baseline

        for _round in range(3):  # realistic page-load bursts, each far above pool + overflow (3)
            statuses, errors = await gather_statuses(client.get(READ_PATHS[i % len(READ_PATHS)]) for i in range(BURST))
            assert not [e for e in errors if isinstance(e, PoolTimeoutError)], errors
            assert not errors, errors
            assert statuses == [200] * BURST
            assert watch.checked_out == baseline
    assert watch.checkouts_on_event_loop == 0


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_concurrent_prospect_saves_complete_without_pool_exhaustion(pool_app) -> None:
    application, settings, provider, engine, watch = pool_app
    owners = [prospect(engine, settings, provider, f"save{index}") for index in range(4)]
    clients = [client_for(application, settings, issued) for issued in owners]
    try:
        plans = []
        for issued, client in zip(owners, clients):
            design = (await client.get("/api/v1/owner/design")).json()
            catalog = (await client.get("/api/v1/owner/catalog")).json()
            category = catalog["categories"][0]
            product = catalog["products"][0]
            plans.append((issued, client, design, category, product))

        calls = []
        for issued, client, design, category, product in plans:
            headers = write_headers(issued)
            config = {**design["config"], "tagline": f"Saved under load {issued.principal.organization_id.hex[:6]}"}
            calls.append(client.put("/api/v1/owner/design", headers=headers, json={"config": config, "revision": design["revision"]}))
            calls.append(client.post("/api/v1/owner/catalog/products", headers=headers, json={"slug": f"load-{uuid4().hex[:6]}", "name": "Load Latte", "base_price_cents": 525, "category_id": int(category["id"]), "image": LATTE}))
            calls.append(client.put(f"/api/v1/owner/catalog/products/{int(product['id'])}", headers=headers, json={"slug": product["slug"], "name": product["name"], "base_price_cents": product.get("base_price_cents", 400), "category_id": int(category["id"]), "image": MUFFIN}))
            calls.append(client.put(f"/api/v1/owner/catalog/categories/{int(category['id'])}", headers=headers, json={"name": f"{category['name']} Fresh", "published": True}))
        statuses, errors = await gather_statuses(calls)
        assert not errors, errors
        assert sorted(statuses) == sorted([200, 201, 200, 200] * len(plans)), statuses
        assert watch.checked_out == 0

        with Session(engine) as session:
            for issued, _client, _design, category, product in plans:
                org = issued.principal.organization_id
                assert session.scalar(select(Product.image_reference).where(Product.id == int(product["id"]), Product.organization_id == org)) == MUFFIN
                assert session.scalar(select(Product.id).where(Product.organization_id == org, Product.name == "Load Latte")) is not None
                assert session.scalar(select(Category.name).where(Category.id == int(category["id"]))).endswith(" Fresh")
        for issued, client, *_ in plans:
            assert (await client.get("/api/v1/owner/design")).json()["config"]["tagline"].startswith("Saved under load")
    finally:
        for client in clients:
            await client.aclose()
    assert watch.checkouts_on_event_loop == 0


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_fail_closed_missing_invalid_session_and_client_tenant_context(pool_app) -> None:
    application, settings, provider, engine, watch = pool_app
    issued = prospect(engine, settings, provider, "closed")
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as anonymous:
        assert (await anonymous.get("/api/v1/owner/catalog")).status_code == 401
        anonymous.cookies.set(settings.session_cookie_name, "not-a-real-session")
        assert (await anonymous.get("/api/v1/owner/catalog")).status_code == 401
    async with client_for(application, settings, issued) as client:
        other = prospect(engine, settings, provider, "other")
        response = await client.get("/api/v1/owner/catalog", headers={"X-Tenant-Id": str(other.principal.organization_id)})
        assert response.status_code == 403
        response = await client.get(f"/api/v1/owner/catalog?organization_id={other.principal.organization_id}")
        assert response.status_code == 403
        # cross-tenant write: another prospect's product id is not found in this tenant and is left untouched
        with Session(engine) as session:
            foreign = session.scalar(select(Product).where(Product.organization_id == other.principal.organization_id))
            foreign_id, foreign_name = foreign.id, foreign.name
        response = await client.put(f"/api/v1/owner/catalog/products/{foreign_id}", headers=write_headers(issued), json={"slug": "stolen", "name": "Stolen", "base_price_cents": 1, "category_id": foreign.category_id, "image": ""})
        assert response.status_code == 404  # same as before the fix
        with Session(engine) as session:
            assert session.get(Product, foreign_id).name == foreign_name
    assert watch.checked_out == 0


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_fail_closed_inactive_membership_and_tenant_resolution_errors(pool_app, monkeypatch) -> None:
    application, settings, provider, engine, watch = pool_app
    issued = prospect(engine, settings, provider, "resolve")
    org = issued.principal.organization_id

    async with client_for(application, settings, issued, raise_app_exceptions=False) as client:
        # tenant resolution refuses -> 404 tenant_not_found, endpoint never runs
        def refuse(*_args, **_kwargs):
            raise tenant_context_module.TenantResolutionError("membership is not active")
        monkeypatch.setattr(tenant_context_module, "resolve_owner_tenant_context", refuse)
        response = await client.post("/api/v1/owner/catalog/categories", headers=write_headers(issued), json={"name": "Should Not Exist"})
        assert response.status_code == 404 and response.json()["detail"]["code"] == "tenant_not_found"

        # a database error while resolving the tenant denies (500) instead of proceeding
        def db_down(*_args, **_kwargs):
            raise OperationalError("SELECT organizations", {}, Exception("connection lost"))
        monkeypatch.setattr(tenant_context_module, "resolve_owner_tenant_context", db_down)
        response = await client.post("/api/v1/owner/catalog/categories", headers=write_headers(issued), json={"name": "Should Not Exist"})
        assert response.status_code == 500
        monkeypatch.undo()

        with Session(engine) as session:
            assert session.scalar(select(Category.id).where(Category.organization_id == org, Category.name == "Should Not Exist")) is None

        # a membership that is no longer active is refused by the real resolver path
        with Session(engine) as session, session.begin():
            session.execute(update(Membership).where(Membership.id == issued.principal.membership_id).values(status="suspended"))
        response = await client.get("/api/v1/owner/catalog")
        assert response.status_code == 401 and response.json()["detail"]["code"] == "session_expired"  # same as before the fix
    assert watch.checked_out == 0


def png_bytes(color: tuple[int, int, int]) -> bytes:
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (900, 900), color).save(buffer, format="PNG")
    return buffer.getvalue()


def upload(client: AsyncClient, issued, color=(200, 120, 40)):
    headers = {**write_headers(issued), "Content-Type": "image/png", "X-Media-Purpose": "product", "X-Media-Alt": "Owner photo"}
    return client.post("/api/v1/owner/media/upload", headers=headers, content=png_bytes(color))


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_each_prospect_write_and_upload_holds_one_connection_and_none_on_the_event_loop(pool_app) -> None:
    application, settings, provider, engine, watch = pool_app
    issued = prospect(engine, settings, provider, "single")
    async with client_for(application, settings, issued) as client:
        catalog = (await client.get("/api/v1/owner/catalog")).json()
        category = catalog["categories"][0]
        watch.reset_peak()
        created = await client.post("/api/v1/owner/catalog/products", headers=write_headers(issued), json={"slug": f"one-{uuid4().hex[:6]}", "name": "One Latte", "base_price_cents": 500, "category_id": int(category["id"]), "image": LATTE})
        assert created.status_code == 201
        assert watch.peak == 1  # the commercial-mode check reuses the request transaction instead of a side session
        watch.reset_peak()
        uploaded = await upload(client, issued)
        assert uploaded.status_code == 201, uploaded.text
        assert watch.peak == 1
    assert watch.checkouts_on_event_loop == 0
    assert watch.checked_out == 0
    with Session(engine) as session:
        assert session.scalar(select(MediaAsset.organization_id).where(MediaAsset.id == uploaded.json()["id"])) == issued.principal.organization_id


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_concurrent_uploads_during_page_load_bursts_do_not_starve_the_pool(pool_app) -> None:
    application, settings, provider, engine, watch = pool_app
    owners = [prospect(engine, settings, provider, f"up{index}") for index in range(4)]
    clients = [client_for(application, settings, issued) for issued in owners]
    try:
        calls = []
        for index, (issued, client) in enumerate(zip(owners, clients)):
            calls.append(upload(client, issued, (40 * index, 90, 160)))
            calls.extend(client.get(READ_PATHS[i % len(READ_PATHS)]) for i in range(6))
        statuses, errors = await gather_statuses(calls)
        assert not errors, errors
        assert sorted(statuses) == sorted(([201] + [200] * 6) * len(owners))
    finally:
        for client in clients:
            await client.aclose()
    assert watch.checkouts_on_event_loop == 0
    assert watch.checked_out == 0


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_production_pool_settings_survive_multi_page_load_bursts(demo_ctx, postgresql_url) -> None:
    """Real ``create_database_engine`` pool (5 + 5 overflow, 30 s timeout): 60 concurrent owner requests, about
    two or three wizard page loads at the same instant. Before the fix, 25 already produced 15 QueuePool timeouts."""
    engine, settings, provider = demo_ctx
    application = create_app(postgresql_url, auth_settings=settings, auth_provider=provider)
    pool = application.state.db_engine.pool
    assert (pool.size(), pool._max_overflow) == (5, 5)
    issued = prospect(engine, settings, provider, "prod")
    try:
        async with client_for(application, settings, issued) as client:
            for _round in range(2):
                statuses, errors = await gather_statuses(client.get(READ_PATHS[i % len(READ_PATHS)]) for i in range(60))
                assert not errors, errors
                assert statuses == [200] * 60
                assert pool.checkedout() == 0
    finally:
        application.state.db_engine.dispose()
