import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.catalog.models import Product
from app.catalog.repository import CatalogRepository
from app.catalog.seed import seed_catalog
from app.catalog.service import CatalogService
from tests.test_catalog_api import catalog_api_engine


def public_product_slugs(service: CatalogService) -> set[str]:
    catalog = service.build_catalog()
    return {
        product.slug
        for category in catalog.categories
        for product in category.products
    }


@pytest.mark.postgresql
def test_daily_availability_toggle_immediately_controls_customer_menu(
    catalog_api_engine: Engine,
) -> None:
    with Session(catalog_api_engine) as session:
        seed_catalog(session)
        product = session.scalar(select(Product).order_by(Product.id))
        assert product is not None

        service = CatalogService(
            CatalogRepository(session),
            tax_name="HST",
            tax_rate_millionths=1_300_000,
        )

        unavailable = service.set_product_availability(product.id, False)
        assert unavailable.available is False
        assert product.slug not in public_product_slugs(service)

        available = service.set_product_availability(product.id, True)
        assert available.available is True
        assert product.slug in public_product_slugs(service)
