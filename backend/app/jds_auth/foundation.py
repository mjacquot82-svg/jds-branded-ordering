from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.jds_auth.models import JdsApplication, Organization, Permission, Role, RolePermission

PERMISSIONS = {
    "catalog.read": "Read owner catalog data.",
    "catalog.write": "Create and edit catalog data.",
    "catalog.publish": "Publish or archive catalog data.",
    "modifiers.manage": "Manage modifier definitions and assignments.",
    "availability.manage": "Manage product availability.",
    "orders.read": "Read organization orders.",
    "orders.fulfill": "Progress order fulfillment.",
    "communications.announce": "Prepare customer Lunch Special announcements.",
    "communications.general_announce": "Send owner-approved general customer announcements.",
    "lunch_special.manage": "Select or clear the current Lunch Special product.",
    "loyalty.manage": "Manage customer loyalty program configuration.",
    "loyalty.adjust": "Apply audited customer loyalty adjustments.",
    "members.invite": "Invite organization members.",
    "members.manage": "Manage organization memberships.",
    "integrations.manage": "Connect and inspect organization integrations.",
    "customer.profile": "Manage the authenticated customer's profile.",
    "customer.orders": "Read the authenticated customer's orders.",
}

ROLE_PERMISSIONS = {
    "owner": frozenset(PERMISSIONS) - {"customer.profile", "customer.orders"},
    "manager": frozenset(PERMISSIONS) - {"members.manage", "customer.profile", "customer.orders", "communications.general_announce", "loyalty.manage", "loyalty.adjust"},
    "staff": frozenset({
        "catalog.read", "availability.manage", "orders.read", "orders.fulfill",
        "communications.announce", "lunch_special.manage",
    }),
    "customer": frozenset({"customer.profile", "customer.orders"}),
}


def ensure_foundation(
    session: Session,
    *,
    application_key: str,
    application_name: str,
    organization_slug: str,
    organization_name: str,
) -> tuple[JdsApplication, Organization]:
    application = session.scalar(select(JdsApplication).where(JdsApplication.key == application_key))
    if application is None:
        application = JdsApplication(key=application_key, name=application_name)
        session.add(application)
    organization = session.scalar(select(Organization).where(Organization.slug == organization_slug))
    if organization is None:
        organization = Organization(slug=organization_slug, name=organization_name)
        session.add(organization)
    session.flush()

    permissions: dict[str, Permission] = {}
    for key, description in PERMISSIONS.items():
        permission = session.scalar(select(Permission).where(Permission.application_id == application.id, Permission.key == key))
        if permission is None:
            permission = Permission(application_id=application.id, key=key, description=description)
            session.add(permission)
        permissions[key] = permission
    session.flush()

    for role_key, permission_keys in ROLE_PERMISSIONS.items():
        role = session.scalar(select(Role).where(Role.application_id == application.id, Role.key == role_key))
        if role is None:
            role = Role(application_id=application.id, key=role_key, name=role_key.title())
            session.add(role)
            session.flush()
        existing = set(session.scalars(select(RolePermission.permission_id).where(RolePermission.role_id == role.id)))
        desired = {permissions[key].id for key in permission_keys}
        stale = existing - desired
        if stale:
            session.execute(
                delete(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id.in_(stale),
                )
            )
        for key in permission_keys:
            if permissions[key].id not in existing:
                session.add(RolePermission(role_id=role.id, permission_id=permissions[key].id))
    session.flush()
    return application, organization
