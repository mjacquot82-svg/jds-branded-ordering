from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.catalog.repository import CatalogRepository
from app.catalog.schemas import CatalogResponse
from app.catalog.service import CatalogService
from app.availability.repository import AvailabilityRepository
from app.orders.pricing import DEFAULT_TAX_NAME, DEFAULT_TAX_RATE_MILLIONTHS

router = APIRouter()


def get_catalog_session(request: Request) -> Generator[Session, None, None]:
    session_factory = request.app.state.db_session_factory
    if session_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Catalog database is unavailable.",
        )

    with session_factory() as session:
        yield session


@router.get("/catalog", response_model=CatalogResponse)
def get_catalog(
    session: Session = Depends(get_catalog_session),
) -> CatalogResponse:
    try:
        pricing = AvailabilityRepository(session).get_business_settings()
        return CatalogService(
            CatalogRepository(session),
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
