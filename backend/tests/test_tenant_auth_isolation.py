from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jds_auth.models import JdsApplication, JdsUser, Membership, Organization, OwnerInvitation, Role, StaffPinCredential
from app.jds_auth.security import hash_pin
from tests.test_jds_auth import auth_client, auth_engine, auth_settings, fake_provider  # noqa: F401


async def _login(client):
    response = await client.post(
        "/api/v1/owner/auth/login", headers={"Origin": "http://test"},
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
    )
    assert response.status_code == 200
    return response.json()


def _add_membership(engine, *, user_email: str, slug: str, role_key: str = "owner", status: str = "active"):
    with Session(engine) as session, session.begin():
        user = session.scalar(select(JdsUser).where(JdsUser.primary_email == user_email))
        application = session.scalar(select(JdsApplication).where(JdsApplication.key == "jds-commerce"))
        role = session.scalar(select(Role).where(Role.application_id == application.id, Role.key == role_key))
        organization = Organization(slug=slug, name=slug.title())
        session.add(organization)
        session.flush()
        membership = Membership(
            organization_id=organization.id, application_id=application.id,
            user_id=user.id, role_id=role.id, status=status,
            joined_at=datetime.now(timezone.utc),
        )
        session.add(membership)
        session.flush()
        return membership.id, organization.id


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_multi_membership_selection_is_explicit_authorized_and_session_bound(auth_client, auth_engine):
    login = await _login(auth_client)
    membership_b, organization_b = _add_membership(auth_engine, user_email="owner@example.com", slug="tenant-b")

    organizations = await auth_client.get("/api/v1/owner/auth/organizations")
    assert organizations.status_code == 200
    assert {row["organization_id"] for row in organizations.json()} == {
        login["organization_id"], str(organization_b)
    }

    old_cookie = auth_client.cookies.get("__Host-jds_owner_session")
    selected = await auth_client.post(
        f"/api/v1/owner/auth/organizations/{membership_b}/select",
        headers={"Origin": "http://test", "X-CSRF-Token": login["csrf_token"]},
    )
    assert selected.status_code == 200
    assert selected.json()["organization_id"] == str(organization_b)
    invitation = await auth_client.post(
        "/api/v1/owner/auth/invitations",
        headers={"Origin": "http://test", "X-CSRF-Token": selected.json()["csrf_token"]},
        json={"email": "manager-b@example.com", "role": "manager"},
    )
    assert invitation.status_code == 201
    with Session(auth_engine) as session:
        assert session.scalar(select(OwnerInvitation.organization_id).where(OwnerInvitation.email == "manager-b@example.com")) == organization_b

    auth_client.cookies.clear()
    auth_client.cookies.set("__Host-jds_owner_session", old_cookie)
    assert (await auth_client.get("/api/v1/owner/auth/session")).status_code == 401


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_inactive_or_arbitrary_tenant_selection_fails_closed(auth_client, auth_engine):
    login = await _login(auth_client)
    inactive, _ = _add_membership(
        auth_engine, user_email="owner@example.com", slug="tenant-inactive", status="suspended"
    )
    denied = await auth_client.post(
        f"/api/v1/owner/auth/organizations/{inactive}/select",
        headers={"Origin": "http://test", "X-CSRF-Token": login["csrf_token"]},
    )
    assert denied.status_code == 403
    assert (await auth_client.get("/api/v1/owner/auth/session", headers={"X-Organization-Id": login["organization_id"]})).status_code == 403
    assert (await auth_client.get("/api/v1/owner/auth/session?tenant_id=" + login["organization_id"])).status_code == 403


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_staff_pin_is_membership_bound_and_cannot_be_replayed_across_tenants(auth_client, auth_engine, auth_settings):
    owner = await _login(auth_client)
    created = await auth_client.post(
        "/api/v1/owner/staff",
        headers={"Origin": "http://test", "X-CSRF-Token": owner["csrf_token"]},
        json={"display_name": "Shared Worker", "pin": "482193"},
    )
    staff_id = created.json()["id"]
    membership_b, _ = _add_membership(auth_engine, user_email=f"{staff_id}@staff.invalid", slug="tenant-b", role_key="staff")
    with Session(auth_engine) as session, session.begin():
        session.add(StaffPinCredential(
            membership_id=membership_b, user_id=UUID(staff_id),
            verifier=hash_pin("654321", auth_settings.session_pepper),
            changed_at=datetime.now(timezone.utc),
        ))
    auth_client.cookies.clear()
    replay = await auth_client.post(
        "/api/v1/staff/access/login", headers={"Origin": "http://test"},
        json={"staff_id": staff_id, "pin": "654321"},
    )
    assert replay.status_code == 401
    valid = await auth_client.post(
        "/api/v1/staff/access/login", headers={"Origin": "http://test"},
        json={"staff_id": staff_id, "pin": "482193"},
    )
    assert valid.status_code == 200
    assert valid.json()["organization_id"] == owner["organization_id"]
