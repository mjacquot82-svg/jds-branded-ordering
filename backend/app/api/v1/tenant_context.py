from fastapi import Depends, HTTPException, Request, status

from app.api.v1.owner_auth import current_principal
from app.jds_auth.service import AuthPrincipal
from app.tenancy.context import TenantContext
from app.tenancy.resolver import (
    TenantResolutionError,
    resolve_owner_tenant_context,
)

_TENANT_HEADERS = ("x-tenant-id", "x-organization-id", "x-tenant-slug", "x-organization-slug")
_TENANT_QUERY = ("tenant_id", "organization_id", "tenant_slug", "organization_slug")


def _resolution_error(error: TenantResolutionError) -> None:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "tenant_not_found", "message": "Storefront is unavailable."},
    ) from error


async def authenticated_owner_tenant(
    request: Request,
    principal: AuthPrincipal = Depends(current_principal),
) -> TenantContext:
    session_factory = request.app.state.db_session_factory
    if session_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Catalog database is unavailable.",
        )
    try:
        if any(key in request.headers for key in _TENANT_HEADERS) or any(
            key in request.query_params for key in _TENANT_QUERY
        ):
            raise TenantResolutionError("Client-supplied tenant context is not allowed.")
        with session_factory() as session:
            return resolve_owner_tenant_context(
                session,
                principal_organization_id=principal.organization_id,
                principal_user_id=principal.user_id,
                principal_membership_id=principal.membership_id,
                principal_application_id=principal.application_id,
                permissions=principal.permissions,
            )
    except TenantResolutionError as error:
        _resolution_error(error)
