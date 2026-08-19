from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class TenantResolutionSource(str, Enum):
    LADELS_COMPATIBILITY = "ladels_compatibility"
    AUTHENTICATED_MEMBERSHIP = "authenticated_membership"
    VERIFIED_HOSTNAME = "verified_hostname"
    PLATFORM_ADMIN = "platform_admin"


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Immutable tenant scope created only by trusted server-side resolvers."""

    organization_id: UUID
    organization_slug: str
    source: TenantResolutionSource
    principal_user_id: UUID | None = None
    membership_id: UUID | None = None
    permissions: frozenset[str] = frozenset()
