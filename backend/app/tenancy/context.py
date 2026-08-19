from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class TenantResolutionSource(str, Enum):
    LADELS_COMPATIBILITY = "ladels_compatibility"
    AUTHENTICATED_MEMBERSHIP = "authenticated_membership"


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Immutable tenant scope created only by trusted server-side resolvers."""

    organization_id: UUID
    organization_slug: str
    source: TenantResolutionSource
