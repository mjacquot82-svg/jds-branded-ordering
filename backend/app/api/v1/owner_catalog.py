from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.catalog import get_catalog_session
from app.api.v1.owner_auth import csrf_principal, current_principal, require_permission
from app.api.v1.tenant_context import authenticated_owner_tenant
from app.catalog.repository import CatalogRepository
from app.catalog.schemas import LunchSpecialSelectionWrite, OwnerCatalogResponse, OwnerModifierGroupResponse, OwnerModifierGroupWrite, OwnerModifierOptionResponse, OwnerModifierOptionWrite, OwnerProductAvailabilityWrite, OwnerProductResponse, OwnerProductWrite
from app.catalog.service import CatalogService
from app.jds_auth.service import AuthPrincipal
from sqlalchemy.orm import Session
from app.tenancy.context import TenantContext


router = APIRouter(prefix="/owner/catalog", tags=["owner-catalog"])


def require_catalog_reader(
    principal: AuthPrincipal = Depends(current_principal),
) -> AuthPrincipal:
    if "catalog.read" not in principal.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "permission_denied", "message": "Permission is required."},
        )
    return principal


def require_full_catalog_manager(
    principal: AuthPrincipal = Depends(csrf_principal),
) -> AuthPrincipal:
    required = {"catalog.write", "catalog.publish", "availability.manage", "modifiers.manage"}
    if not required <= principal.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "permission_denied", "message": "Catalog editing permissions are required."},
        )
    return principal


def require_catalog_editor(
    principal: AuthPrincipal = Depends(require_full_catalog_manager),
) -> AuthPrincipal:
    require_full_catalog_manager(principal)
    return principal


def require_modifier_capability(
    principal: AuthPrincipal = Depends(csrf_principal),
) -> AuthPrincipal:
    if "modifiers.manage" not in principal.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "permission_denied", "message": "Modifier management permission is required."},
        )
    return principal


def require_modifier_manager(
    principal: AuthPrincipal = Depends(require_modifier_capability),
) -> AuthPrincipal:
    require_modifier_capability(principal)
    return principal


def catalog_service(
    session: Session = Depends(get_catalog_session),
    tenant: TenantContext = Depends(authenticated_owner_tenant),
) -> CatalogService:
    return CatalogService(CatalogRepository(session, tenant))


def mutation_error(error: Exception) -> None:
    if isinstance(error, LookupError):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(error, ValueError):
        raise HTTPException(status_code=409, detail=str(error)) from error
    raise HTTPException(status_code=503, detail="Catalog database is unavailable.") from error


@router.get("", response_model=OwnerCatalogResponse)
def read_owner_catalog(
    _: AuthPrincipal = Depends(require_catalog_reader),
    service: CatalogService = Depends(catalog_service),
) -> OwnerCatalogResponse:
    try:
        return service.build_owner_catalog()
    except SQLAlchemyError as error:
        mutation_error(error)


@router.post("/modifier-groups", response_model=OwnerModifierGroupResponse, status_code=201)
def create_modifier_group(
    payload: OwnerModifierGroupWrite,
    _: AuthPrincipal = Depends(require_modifier_manager),
    service: CatalogService = Depends(catalog_service),
) -> OwnerModifierGroupResponse:
    try:
        return service.create_modifier_group(payload)
    except (SQLAlchemyError, ValueError) as error:
        mutation_error(error)


@router.put("/modifier-groups/{group_id}", response_model=OwnerModifierGroupResponse)
def update_modifier_group(
    group_id: int,
    payload: OwnerModifierGroupWrite,
    _: AuthPrincipal = Depends(require_modifier_manager),
    service: CatalogService = Depends(catalog_service),
) -> OwnerModifierGroupResponse:
    try:
        return service.update_modifier_group(group_id, payload)
    except (SQLAlchemyError, ValueError, LookupError) as error:
        mutation_error(error)


@router.post("/modifier-groups/{group_id}/options", response_model=OwnerModifierOptionResponse, status_code=201)
def create_modifier_option(
    group_id: int,
    payload: OwnerModifierOptionWrite,
    _: AuthPrincipal = Depends(require_modifier_manager),
    service: CatalogService = Depends(catalog_service),
) -> OwnerModifierOptionResponse:
    try:
        return service.create_modifier_option(group_id, payload)
    except (SQLAlchemyError, ValueError, LookupError) as error:
        mutation_error(error)


@router.put("/modifier-groups/{group_id}/options/{option_id}", response_model=OwnerModifierOptionResponse)
def update_modifier_option(
    group_id: int,
    option_id: int,
    payload: OwnerModifierOptionWrite,
    _: AuthPrincipal = Depends(require_modifier_manager),
    service: CatalogService = Depends(catalog_service),
) -> OwnerModifierOptionResponse:
    try:
        return service.update_modifier_option(group_id, option_id, payload)
    except (SQLAlchemyError, ValueError, LookupError) as error:
        mutation_error(error)


@router.post("/products", response_model=OwnerProductResponse, status_code=201)
def create_product(
    payload: OwnerProductWrite,
    _: AuthPrincipal = Depends(require_catalog_editor),
    service: CatalogService = Depends(catalog_service),
) -> OwnerProductResponse:
    try:
        return service.create_product(payload)
    except (SQLAlchemyError, ValueError) as error:
        mutation_error(error)


@router.put("/products/{product_id}", response_model=OwnerProductResponse)
def update_product(
    product_id: int,
    payload: OwnerProductWrite,
    _: AuthPrincipal = Depends(require_catalog_editor),
    service: CatalogService = Depends(catalog_service),
) -> OwnerProductResponse:
    try:
        return service.update_product(product_id, payload)
    except (SQLAlchemyError, ValueError, LookupError) as error:
        mutation_error(error)


@router.delete("/products/{product_id}", status_code=204)
def archive_product(
    product_id: int,
    _: AuthPrincipal = Depends(require_permission("catalog.publish")),
    service: CatalogService = Depends(catalog_service),
) -> Response:
    try:
        service.archive_product(product_id)
        return Response(status_code=204)
    except (SQLAlchemyError, LookupError) as error:
        mutation_error(error)


@router.patch("/products/{product_id}/availability", response_model=OwnerProductResponse)
def update_product_availability(
    product_id: int,
    payload: OwnerProductAvailabilityWrite,
    _: AuthPrincipal = Depends(require_permission("availability.manage")),
    service: CatalogService = Depends(catalog_service),
) -> OwnerProductResponse:
    try:
        return service.set_product_availability(product_id, payload.available)
    except (SQLAlchemyError, LookupError) as error:
        mutation_error(error)


@router.put("/lunch-special", response_model=OwnerProductResponse | None)
def update_lunch_special(
    payload: LunchSpecialSelectionWrite,
    _: AuthPrincipal = Depends(require_permission("lunch_special.manage")),
    service: CatalogService = Depends(catalog_service),
) -> OwnerProductResponse | None:
    try:
        return service.set_lunch_special(payload.product_id)
    except (SQLAlchemyError, LookupError, ValueError) as error:
        mutation_error(error)
