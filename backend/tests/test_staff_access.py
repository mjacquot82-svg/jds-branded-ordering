from sqlalchemy import select
from sqlalchemy.orm import Session
import pytest
from uuid import UUID

from app.jds_auth.models import JdsUser, OwnerSession, SecurityAuditEvent, StaffPinCredential
from app.jds_auth.security import pin_matches
from tests.test_jds_auth import (  # noqa: F401
    auth_client,
    auth_engine,
    auth_settings,
    fake_provider,
)


async def owner_login(client):
    response = await client.post("/api/v1/owner/auth/login", headers={"Origin": "http://test"}, json={"email": "owner@example.com", "password": "correct horse battery staple"})
    assert response.status_code == 200
    return response.json()


async def create_staff(client, csrf, name="Jessie", pin="482193"):
    return await client.post("/api/v1/owner/staff", headers={"Origin": "http://test", "X-CSRF-Token": csrf}, json={"display_name": name, "pin": pin})


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_owner_creates_individual_staff_and_pin_is_only_a_verifier(auth_client, auth_engine, auth_settings):
    owner = await owner_login(auth_client)
    created = await create_staff(auth_client, owner["csrf_token"])
    assert created.status_code == 201
    assert created.json()["display_name"] == "Jessie"
    assert "pin" not in created.json()
    with Session(auth_engine) as session:
        credential = session.scalar(select(StaffPinCredential))
        user = session.get(JdsUser, credential.user_id)
        assert credential.verifier != "482193"
        assert "482193" not in credential.verifier
        assert pin_matches("482193", credential.verifier, auth_settings.session_pepper)
        assert user.primary_email.endswith("@staff.invalid")


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_staff_pin_login_uses_shared_session_capabilities_and_generic_failure(auth_client, auth_engine, auth_settings):
    owner = await owner_login(auth_client)
    created = await create_staff(auth_client, owner["csrf_token"])
    staff_id = created.json()["id"]
    await auth_client.post("/api/v1/owner/auth/logout", headers={"Origin": "http://test", "X-CSRF-Token": owner["csrf_token"]})
    wrong = await auth_client.post("/api/v1/staff/access/login", headers={"Origin": "http://test"}, json={"staff_id": staff_id, "pin": "000000"})
    missing = await auth_client.post("/api/v1/staff/access/login", headers={"Origin": "http://test"}, json={"staff_id": "00000000-0000-0000-0000-000000000000", "pin": "000000"})
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json()["detail"] == missing.json()["detail"]
    login = await auth_client.post("/api/v1/staff/access/login", headers={"Origin": "http://test"}, json={"staff_id": staff_id, "pin": "482193"})
    assert login.status_code == 200
    assert login.json()["role"] == "staff"
    assert {"orders.read", "orders.fulfill", "catalog.read", "availability.manage", "communications.announce", "lunch_special.manage"} <= set(login.json()["permissions"])
    assert {"members.manage", "integrations.manage", "catalog.write"}.isdisjoint(login.json()["permissions"])
    with Session(auth_engine) as session:
        event = session.scalar(select(SecurityAuditEvent).where(SecurityAuditEvent.action == "auth.staff_pin_login"))
        assert event.actor_user_id == UUID(staff_id)


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_staff_cannot_manage_staff_and_disable_revokes_existing_session(auth_client, auth_engine):
    owner = await owner_login(auth_client)
    created = await create_staff(auth_client, owner["csrf_token"])
    staff_id = created.json()["id"]
    owner_cookie = auth_client.cookies.get("__Host-jds_owner_session")
    auth_client.cookies.clear()
    staff = await auth_client.post("/api/v1/staff/access/login", headers={"Origin": "http://test"}, json={"staff_id": staff_id, "pin": "482193"})
    assert (await auth_client.get("/api/v1/owner/staff")).status_code == 403
    staff_cookie = auth_client.cookies.get("__Host-jds_owner_session")
    auth_client.cookies.clear()
    auth_client.cookies.set("__Host-jds_owner_session", owner_cookie)
    owner_session = await auth_client.get("/api/v1/owner/auth/session")
    disabled = await auth_client.put(f"/api/v1/owner/staff/{staff_id}/status", headers={"Origin": "http://test", "X-CSRF-Token": owner_session.json()["csrf_token"]}, json={"active": False})
    assert disabled.status_code == 200
    auth_client.cookies.clear()
    auth_client.cookies.set("__Host-jds_owner_session", staff_cookie)
    assert (await auth_client.get("/api/v1/owner/auth/session")).status_code == 401
    stale_mutation = await auth_client.put(
        "/api/v1/owner/catalog/lunch-special",
        headers={"Origin": "http://test", "X-CSRF-Token": staff.json()["csrf_token"]},
        json={"product_id": None},
    )
    assert stale_mutation.status_code == 401
    assert (await auth_client.post("/api/v1/staff/access/login", headers={"Origin": "http://test"}, json={"staff_id": staff_id, "pin": "482193"})).status_code == 401
    with Session(auth_engine) as session:
        assert session.scalar(select(OwnerSession).where(OwnerSession.user_id == UUID(staff_id))).revoked_at is not None


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_staff_pin_login_is_throttled_per_account(auth_client):
    owner = await owner_login(auth_client)
    created = await create_staff(auth_client, owner["csrf_token"], pin="654321")
    auth_client.cookies.clear()
    for _ in range(5):
        response = await auth_client.post("/api/v1/staff/access/login", headers={"Origin": "http://test"}, json={"staff_id": created.json()["id"], "pin": "000000"})
        assert response.status_code == 401
    limited = await auth_client.post("/api/v1/staff/access/login", headers={"Origin": "http://test"}, json={"staff_id": created.json()["id"], "pin": "654321"})
    assert limited.status_code == 429
    assert "Retry-After" in limited.headers
