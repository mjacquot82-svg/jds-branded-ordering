from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jds_auth.models import JdsApplication, JdsUser, Membership, Organization, OwnerInvitation, Role, StaffPinCredential
from app.catalog.models import Category, Product
from app.orders.models import Order
from app.platform.design import DEFAULT_CONFIG, DesignService
from app.platform.models import BusinessProfile
from app.jds_auth.security import hash_pin
from app.jds_auth.provider import ProviderIdentity
from app.platform.models import CustomerRelationship, OnboardingState, StorefrontHostname
from app.tenancy.resolver import resolve_owner_tenant_context
from tests.test_jds_auth import auth_client, auth_engine, auth_settings, fake_provider  # noqa: F401
from tests.test_tenant_order_isolation import order_for
from tests.test_v1_platform_isolation import make_storefront_operationally_ready


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
async def test_multi_business_switch_changes_catalog_profile_orders_and_design_without_leakage(
    auth_client, auth_engine
):
    login_a = await _login(auth_client)
    membership_b, organization_b = _add_membership(
        auth_engine, user_email="owner@example.com", slug="switch-tenant-b"
    )
    organization_a = UUID(login_a["organization_id"])
    with Session(auth_engine) as session:
        actor = session.scalar(
            select(JdsUser).where(JdsUser.primary_email == "owner@example.com")
        )
        for organization_id, prefix in (
            (organization_a, "Alpha"),
            (organization_b, "Beta"),
        ):
            category = Category(
                organization_id=organization_id,
                slug="coffee",
                name=f"{prefix} Coffee",
                is_published=True,
            )
            session.add(category)
            session.flush()
            session.add_all(
                [
                    Product(
                        organization_id=organization_id,
                        category_id=category.id,
                        slug="latte",
                        name=f"{prefix} Latte",
                        base_price_cents=500,
                        is_published=True,
                    ),
                    BusinessProfile(
                        organization_id=organization_id,
                        display_name=f"{prefix} Café",
                        pickup_instructions=f"{prefix} counter",
                    ),
                    CustomerRelationship(
                        organization_id=organization_id,
                        user_id=actor.id,
                        display_name=f"{prefix} Customer",
                        phone=f"+15195550{'101' if prefix == 'Alpha' else '202'}",
                    ),
                    order_for(organization_id, key=f"{prefix.lower()}-order"),
                ]
            )
            session.flush()
            tenant = resolve_owner_tenant_context(
                session, principal_organization_id=organization_id
            )
            workspace = DesignService(session, tenant).workspace()
            session.commit()
            config = deepcopy(DEFAULT_CONFIG)
            config["displayName"] = f"{prefix} Café"
            DesignService(session, tenant).save(config, workspace.revision, actor.id)

    async def selected_data():
        catalog = await auth_client.get("/api/v1/owner/catalog")
        profile = await auth_client.get("/api/v1/owner/business-profile")
        orders = await auth_client.get("/api/v1/owner/orders/active")
        design = await auth_client.get("/api/v1/owner/design")
        customers = await auth_client.get("/api/v1/owner/customers")
        assert {response.status_code for response in (catalog, profile, orders, design, customers)} == {200}
        return (
            {item["name"] for item in catalog.json()["products"]},
            profile.json()["display_name"],
            {item["customer_name"] for item in orders.json()},
            design.json()["config"]["displayName"],
            {item["displayName"] for item in customers.json()["customers"]},
        )

    alpha = await selected_data()
    assert alpha == ({"Alpha Latte"}, "Alpha Café", {"Guest"}, "Alpha Café", {"Alpha Customer"})
    selected_b = await auth_client.post(
        f"/api/v1/owner/auth/organizations/{membership_b}/select",
        headers={"Origin": "http://test", "X-CSRF-Token": login_a["csrf_token"]},
    )
    assert selected_b.status_code == 200
    beta = await selected_data()
    assert beta == ({"Beta Latte"}, "Beta Café", {"Guest"}, "Beta Café", {"Beta Customer"})
    organizations = (await auth_client.get("/api/v1/owner/auth/organizations")).json()
    membership_a = next(
        item["membership_id"]
        for item in organizations
        if item["organization_id"] == str(organization_a)
    )
    selected_a = await auth_client.post(
        f"/api/v1/owner/auth/organizations/{membership_a}/select",
        headers={
            "Origin": "http://test",
            "X-CSRF-Token": selected_b.json()["csrf_token"],
        },
    )
    assert selected_a.status_code == 200
    assert await selected_data() == alpha


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


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_verified_customer_can_establish_independent_second_storefront_relationship(auth_client, auth_engine, fake_provider):
    fake_provider.identity = ProviderIdentity(
        issuer=fake_provider.identity.issuer, subject="shared-storefront-customer",
        email="shared-storefront@example.com", email_verified=True,
    )
    registered = await auth_client.post(
        "/api/v1/customer/auth/register", headers={"Origin":"http://test"},
        json={"display_name":"Ladel Customer","email":"shared-storefront@example.com","password":"correct horse battery staple","phone":"5198816869"},
    )
    assert registered.status_code == 201
    second_host = "customer-second.jdsstudio.ca"
    with Session(auth_engine) as session, session.begin():
        second = Organization(slug="customer-second", name="Customer Second", lifecycle_status="active")
        session.add(second); session.flush()
        session.add_all([
            OnboardingState(organization_id=second.id,state="complete",current_step="complete",public_ready=True),
            StorefrontHostname(organization_id=second.id,hostname=second_host,status="verified",is_canonical=True),
        ])
        second_id = second.id
    with Session(auth_engine) as session:
        actor = session.scalar(
            select(JdsUser).where(
                JdsUser.primary_email == "shared-storefront@example.com"
            )
        )
        make_storefront_operationally_ready(session, second_id, actor.id)
    login = await auth_client.post(
        "/api/v1/customer/auth/login",
        headers={"Host":second_host,"Origin":"http://test"},
        json={"email":"shared-storefront@example.com","password":"correct horse battery staple"},
    )
    assert login.status_code == 200
    assert login.json()["organization_id"] == str(second_id)
    with Session(auth_engine) as session:
        user = session.scalar(select(JdsUser).where(JdsUser.primary_email == "shared-storefront@example.com"))
        relationships = session.scalars(select(CustomerRelationship).where(CustomerRelationship.user_id == user.id)).all()
        assert len(relationships) == 2
        assert {item.organization_id for item in relationships} == {UUID(login.json()["organization_id"]), next(item.organization_id for item in relationships if item.organization_id != second_id)}
