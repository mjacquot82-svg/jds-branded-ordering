import os
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jds_auth.models import Membership, Organization
from app.tenancy.context import TenantContext, TenantResolutionSource

LADELS_ORGANIZATION_ID = UUID("cd802008-80c6-5719-81ef-9b2310b16512")
LADELS_ORGANIZATION_SLUG = "the-guest-house"
LADELS_ORGANIZATION_NAME = "The Guest House"

_UNTRUSTED_TENANT_HEADERS = frozenset(
    {"x-tenant-id", "x-organization-id", "x-tenant-slug", "x-organization-slug"}
)
_UNTRUSTED_TENANT_QUERY_KEYS = frozenset(
    {"tenant_id", "organization_id", "tenant_slug", "organization_slug"}
)
_LOCAL_COMPATIBILITY_HOSTS = frozenset(
    {"test", "testserver", "localhost", "127.0.0.1", "::1"}
)


class TenantResolutionError(RuntimeError):
    pass


def _ladels_organization(session: Session) -> Organization:
    organization = session.scalar(
        select(Organization).where(Organization.slug == LADELS_ORGANIZATION_SLUG)
    )
    if organization is None or not organization.is_active:
        raise TenantResolutionError("The Ladel's compatibility tenant is unavailable.")
    return organization


def _configured_legacy_hosts(frontend_url: str | None = None) -> frozenset[str]:
    configured = {
        value.strip().lower()
        for value in os.getenv("JDS_LEGACY_LADELS_HOSTS", "").split(",")
        if value.strip()
    }
    if frontend_url:
        hostname = urlparse(frontend_url).hostname
        if hostname:
            configured.add(hostname.lower())
    return frozenset(configured) | _LOCAL_COMPATIBILITY_HOSTS


def resolve_ladels_compatibility_context(
    session: Session,
    *,
    host: str | None = None,
    frontend_url: str | None = None,
    headers: object | None = None,
    query_params: object | None = None,
) -> TenantContext:
    """Resolve only the known legacy Ladel's surface; all tenant hints fail closed."""

    if headers is not None and any(key in headers for key in _UNTRUSTED_TENANT_HEADERS):
        raise TenantResolutionError("Client-supplied tenant context is not allowed.")
    if query_params is not None and any(
        key in query_params for key in _UNTRUSTED_TENANT_QUERY_KEYS
    ):
        raise TenantResolutionError("Client-supplied tenant context is not allowed.")
    normalized_host = (host or "").split(":", 1)[0].strip("[]").lower()
    if normalized_host not in _configured_legacy_hosts(frontend_url):
        raise TenantResolutionError("This host is not a known Ladel's compatibility surface.")

    organization = _ladels_organization(session)
    return TenantContext(
        organization_id=organization.id,
        organization_slug=organization.slug,
        source=TenantResolutionSource.LADELS_COMPATIBILITY,
    )


def resolve_internal_ladels_compatibility_context(session: Session) -> TenantContext:
    """Trusted compatibility scope for legacy internal call paths during Milestone 1."""

    organization = _ladels_organization(session)
    return TenantContext(
        organization_id=organization.id,
        organization_slug=organization.slug,
        source=TenantResolutionSource.LADELS_COMPATIBILITY,
    )


def resolve_owner_tenant_context(
    session: Session,
    *,
    principal_organization_id: UUID,
    principal_user_id: UUID | None = None,
    principal_membership_id: UUID | None = None,
    principal_application_id: UUID | None = None,
    permissions: frozenset[str] = frozenset(),
) -> TenantContext:
    """Resolve catalog scope from an authenticated membership, never request data."""

    organization = session.scalar(select(Organization).where(Organization.id == principal_organization_id))
    if organization is None or not organization.is_active:
        raise TenantResolutionError("The authenticated organization is not available here.")
    if principal_membership_id is not None:
        membership = session.scalar(
            select(Membership).where(
                Membership.id == principal_membership_id,
                Membership.organization_id == principal_organization_id,
                Membership.user_id == principal_user_id,
                Membership.application_id == principal_application_id,
                Membership.status == "active",
            )
        )
        if membership is None:
            raise TenantResolutionError("The authenticated membership is not active for this organization.")
    return TenantContext(
        organization_id=organization.id,
        organization_slug=organization.slug,
        source=TenantResolutionSource.AUTHENTICATED_MEMBERSHIP,
        principal_user_id=principal_user_id,
        membership_id=principal_membership_id,
        permissions=permissions,
    )
