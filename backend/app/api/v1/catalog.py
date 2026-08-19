from collections.abc import Generator
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.catalog.repository import CatalogRepository
from app.catalog.schemas import CatalogResponse
from app.catalog.service import CatalogService
from app.availability.repository import AvailabilityRepository
from app.orders.pricing import DEFAULT_TAX_NAME, DEFAULT_TAX_RATE_MILLIONTHS
from app.tenancy.context import TenantContext
from app.tenancy.resolver import TenantResolutionError, resolve_storefront_context

router = APIRouter()
logger = logging.getLogger(__name__)


def get_catalog_session(request: Request) -> Generator[Session, None, None]:
    session_factory = request.app.state.db_session_factory
    if session_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Catalog database is unavailable.",
        )

    with session_factory() as session:
        yield session


def ladels_compatibility_tenant(
    request: Request,
    session: Session = Depends(get_catalog_session),
) -> TenantContext:
    settings = request.app.state.auth_settings
    frontend_url = settings.frontend_url if settings is not None else os.getenv("FRONTEND_URL")
    try:
        return resolve_storefront_context(
            session,
            host=request.url.hostname,
            frontend_url=frontend_url,
            headers=request.headers,
            query_params=request.query_params,
        )
    except TenantResolutionError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "tenant_not_found", "message": "Storefront is unavailable."},
        ) from error


@router.get("/catalog", response_model=CatalogResponse)
async def get_catalog(
    session: Session = Depends(get_catalog_session),
    tenant: TenantContext = Depends(ladels_compatibility_tenant),
) -> CatalogResponse:
    try:
        logger.info(
            "Building public catalog.",
            extra={"organization_id": str(tenant.organization_id)},
        )
        pricing = AvailabilityRepository(session, tenant).get_business_settings()
        return CatalogService(
            CatalogRepository(session, tenant),
            tax_name=pricing.tax_name if pricing else DEFAULT_TAX_NAME,
            tax_rate_millionths=(
                pricing.tax_rate_millionths
                if pricing else DEFAULT_TAX_RATE_MILLIONTHS
            ),
        ).build_catalog()
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Catalog database is unavailable.",
        ) from error
