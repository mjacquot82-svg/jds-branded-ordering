from fastapi import Depends, HTTPException, Request, status

from app.api.v1.owner_auth import current_principal
from app.jds_auth.service import AuthPrincipal
from app.tenancy.context import TenantContext
from app.tenancy.resolver import (
    TenantResolutionError,
    resolve_owner_tenant_context,
)


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
        with session_factory() as session:
            return resolve_owner_tenant_context(
                session,
                principal_organization_id=principal.organization_id,
            )
    except TenantResolutionError as error:
        _resolution_error(error)
