from collections.abc import AsyncIterator, Iterator
from datetime import datetime

import pytest
from alembic import command
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.catalog.models import (
    Category,
    ModifierGroup,
    ModifierOption,
    Product,
    ProductModifierGroup,
    ProductVariant,
)
from app.catalog.schemas import CatalogResponse
from app.catalog.repository import CatalogRepository
from app.catalog.seed import seed_catalog
from app.catalog.service import CatalogService
from app.main import create_app
from app.api.v1.catalog import ladels_compatibility_tenant
from app.tenancy.context import TenantContext, TenantResolutionSource
from app.tenancy.resolver import LADELS_ORGANIZATION_ID, LADELS_ORGANIZATION_SLUG
from app.tenancy.resolver import resolve_internal_ladels_compatibility_context
from tests.test_migrations import make_alembic_config


@pytest.fixture
def catalog_api_engine(postgresql_url: str) -> Iterator[Engine]:
    command.upgrade(make_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE product_modifier_groups, modifier_options, "
                "product_variants, products, modifier_groups, categories "
                "RESTART IDENTITY CASCADE"
            )
        )

    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE product_modifier_groups, modifier_options, "
                    "product_variants, products, modifier_groups, categories "
                    "RESTART IDENTITY CASCADE"
                )
            )
        engine.dispose()


@pytest.fixture
async def catalog_client(
    postgresql_url: str,
    catalog_api_engine: Engine,
) -> AsyncIterator[AsyncClient]:
    application = create_app(database_url=postgresql_url)
    application.dependency_overrides[ladels_compatibility_tenant] = lambda: TenantContext(
        organization_id=LADELS_ORGANIZATION_ID,
        organization_slug=LADELS_ORGANIZATION_SLUG,
        source=TenantResolutionSource.LADELS_COMPATIBILITY,
    )
    transport = ASGITransport(app=application)

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        application.state.db_engine.dispose()


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_catalog_returns_complete_seeded_guest_house_contract(
    catalog_client: AsyncClient,
    catalog_api_engine: Engine,
) -> None:
    with Session(catalog_api_engine) as session:
        seed_catalog(session)

    response = await catalog_client.get("/api/v1/catalog")

    assert response.status_code == 200
    payload = response.json()
    parsed = CatalogResponse.model_validate(payload)
    assert parsed.version == "1"
    assert parsed.generated_at.tzinfo is not None
    assert datetime.fromisoformat(payload["generated_at"]).tzinfo is not None
    assert payload["pricing"] == {
        "tax_name": "HST",
        "tax_rate_millionths": 1_300_000,
    }

    assert [category["slug"] for category in payload["categories"]] == [
        "coffee",
        "espresso",
        "tea",
        "iced-drinks",
        "smoothies",
        "breakfast",
        "pastries",
        "snacks",
        "extras",
    ]
    assert sum(
        len(category["products"]) for category in payload["categories"]
    ) == 11

    products = {
        product["slug"]: product
        for category in payload["categories"]
        for product in category["products"]
    }
    assert products["latte"] == {
        "id": products["latte"]["id"],
        "slug": "latte",
        "name": "Latte",
        "description": "Velvety milk and a double shot.",
        "image": "coffee",
        "featured": True,
        "lunch_special": False,
        "base_price_cents": 525,
        "sort_order": 2,
        "variants": [
            {
                "id": variant["id"],
                "key": key,
                "name": name,
                "price_cents": price,
                "sort_order": sort_order,
            }
            for variant, (key, name, price, sort_order) in zip(
                products["latte"]["variants"],
                (
                    ("small", "Small", 525, 0),
                    ("medium", "Medium", 600, 1),
                    ("large", "Large", 650, 2),
                ),
                strict=True,
            )
        ],
        "modifier_groups": [
            {
                "id": products["latte"]["modifier_groups"][0]["id"],
                "key": "milk",
                "name": "Milk",
                "description": "",
                "selection_type": "single",
                "required": False,
                "min_selections": 0,
                "max_selections": 1,
                "allow_quantity": False,
                "sort_order": 0,
                "options": [
                    {
                        "id": option["id"],
                        "key": key,
                        "name": name,
                        "price_adjustment_cents": price,
                        "sort_order": sort_order,
                    }
                    for option, (key, name, price, sort_order) in zip(
                        products["latte"]["modifier_groups"][0]["options"],
                        (
                            ("whole", "Whole milk", 0, 0),
                            ("oat", "Oat", 85, 1),
                            ("almond", "Almond", 85, 2),
                            ("soy", "Soy", 85, 3),
                            ("coconut", "Coconut", 85, 4),
                        ),
                        strict=True,
                    )
                ],
            },
            {
                "id": products["latte"]["modifier_groups"][1]["id"],
                "key": "flavour-shots",
                "name": "Flavour shots",
                "description": "",
                "selection_type": "multiple",
                "required": False,
                "min_selections": 0,
                "max_selections": 0,
                "allow_quantity": False,
                "sort_order": 1,
                "options": [
                    {
                        "id": option["id"],
                        "key": key,
                        "name": name,
                        "price_adjustment_cents": 75,
                        "sort_order": sort_order,
                    }
                    for option, (key, name, sort_order) in zip(
                        products["latte"]["modifier_groups"][1]["options"],
                        (
                            ("vanilla", "Vanilla", 0),
                            ("caramel", "Caramel", 1),
                            ("hazelnut", "Hazelnut", 2),
                        ),
                        strict=True,
                    )
                ],
            },
        ],
    }

    category_contract = set(payload["categories"][0])
    product_contract = set(products["latte"])
    variant_contract = set(products["latte"]["variants"][0])
    group_contract = set(products["latte"]["modifier_groups"][0])
    option_contract = set(products["latte"]["modifier_groups"][0]["options"][0])
    assert category_contract == {
        "id",
        "slug",
        "name",
        "note",
        "sort_order",
        "products",
    }
    assert product_contract == {
        "id",
        "slug",
        "name",
        "description",
        "image",
        "featured",
        "lunch_special",
        "base_price_cents",
        "sort_order",
        "variants",
        "modifier_groups",
    }
    assert variant_contract == {"id", "key", "name", "price_cents", "sort_order"}
    assert group_contract == {
        "id",
        "key",
        "name",
        "description",
        "selection_type",
        "required",
        "min_selections",
        "max_selections",
        "allow_quantity",
        "sort_order",
        "options",
    }
    assert option_contract == {
        "id",
        "key",
        "name",
        "price_adjustment_cents",
        "sort_order",
    }


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_catalog_rejects_client_tenant_hints_and_unknown_hosts(
    catalog_client: AsyncClient,
    catalog_api_engine: Engine,
    postgresql_url: str,
) -> None:
    with Session(catalog_api_engine) as session:
        seed_catalog(session)

    catalog_client._transport.app.dependency_overrides.pop(ladels_compatibility_tenant)
    conflicting = await catalog_client.get(
        "/api/v1/catalog", headers={"X-Tenant-ID": "client-selected"}
    )
    assert conflicting.status_code == 404
    assert conflicting.json()["detail"]["code"] == "tenant_not_found"

    application = create_app(database_url=postgresql_url)
    transport = ASGITransport(app=application)
    try:
        async with AsyncClient(
            transport=transport, base_url="http://unknown.example"
        ) as client:
            unknown = await client.get("/api/v1/catalog")
        assert unknown.status_code == 404
        assert unknown.json()["detail"]["code"] == "tenant_not_found"
    finally:
        application.state.db_engine.dispose()


@pytest.mark.postgresql
def test_owner_catalog_hydrates_products_with_bounded_queries(
    catalog_api_engine: Engine,
) -> None:
    with Session(catalog_api_engine) as session:
        seed_catalog(session)
        tenant = resolve_internal_ladels_compatibility_context(session)
        statements: list[str] = []

        def record_query(*args) -> None:
            statements.append(args[2])

        event.listen(catalog_api_engine, "before_cursor_execute", record_query)
        try:
            catalog = CatalogService(
                CatalogRepository(session, tenant)
            ).build_owner_catalog()
        finally:
            event.remove(catalog_api_engine, "before_cursor_execute", record_query)

    selects = [statement for statement in statements if statement.lstrip().upper().startswith("SELECT")]
    assert catalog.products
    assert len(selects) == 6


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_catalog_returns_only_published_and_active_records(
    catalog_client: AsyncClient,
    catalog_api_engine: Engine,
) -> None:
    with Session(catalog_api_engine) as session:
        seed_catalog(session)

        session.scalar(
            select(Category).where(Category.slug == "extras")
        ).is_published = False
        session.scalar(
            select(Product).where(Product.slug == "trail-mix")
        ).is_published = False
        session.scalar(
            select(ProductVariant)
            .join(Product)
            .where(Product.slug == "latte", ProductVariant.key == "large")
        ).is_active = False
        session.scalar(
            select(ModifierOption)
            .join(ModifierGroup)
            .where(
                ModifierGroup.key == "milk",
                ModifierOption.key == "coconut",
            )
        ).is_active = False
        session.scalar(
            select(ModifierGroup).where(ModifierGroup.key == "toast")
        ).is_active = False
        session.scalar(
            select(ProductModifierGroup)
            .join(Product)
            .join(ModifierGroup)
            .where(
                Product.slug == "cold-brew",
                ModifierGroup.key == "flavour-shots",
            )
        ).is_active = False
        session.commit()

    payload = (await catalog_client.get("/api/v1/catalog")).json()
    assert "extras" not in {
        category["slug"] for category in payload["categories"]
    }
    products = {
        product["slug"]: product
        for category in payload["categories"]
        for product in category["products"]
    }
    assert "vanilla-shot" not in products
    assert "trail-mix" not in products
    assert [variant["key"] for variant in products["latte"]["variants"]] == [
        "small",
        "medium",
    ]
    assert [
        option["key"]
        for option in products["latte"]["modifier_groups"][0]["options"]
    ] == ["whole", "oat", "almond", "soy"]
    assert products["croissant"]["modifier_groups"] == []
    assert [
        group["key"] for group in products["cold-brew"]["modifier_groups"]
    ] == ["milk"]


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_catalog_ordering_is_deterministic(
    catalog_client: AsyncClient,
    catalog_api_engine: Engine,
) -> None:
    with Session(catalog_api_engine) as session:
        seed_catalog(session)
        session.execute(
            text("UPDATE categories SET sort_order = 0")
        )
        session.execute(
            text("UPDATE products SET sort_order = 0")
        )
        session.execute(
            text("UPDATE product_variants SET sort_order = 0")
        )
        session.execute(
            text("UPDATE modifier_options SET sort_order = 0")
        )
        session.commit()

    first = (await catalog_client.get("/api/v1/catalog")).json()
    second = (await catalog_client.get("/api/v1/catalog")).json()
    first.pop("generated_at")
    second.pop("generated_at")

    assert first == second
    assert [category["name"] for category in first["categories"]] == sorted(
        category["name"] for category in first["categories"]
    )
    for category in first["categories"]:
        assert [product["name"] for product in category["products"]] == sorted(
            product["name"] for product in category["products"]
        )


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_catalog_returns_empty_contract(
    catalog_client: AsyncClient,
) -> None:
    response = await catalog_client.get("/api/v1/catalog")

    assert response.status_code == 200
    assert response.json()["version"] == "1"
    assert response.json()["categories"] == []


@pytest.mark.anyio
async def test_catalog_returns_503_without_database_configuration() -> None:
    application = create_app(database_url="")
    transport = ASGITransport(app=application)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/catalog")

    assert response.status_code == 503
    assert response.json() == {"detail": "Catalog database is unavailable."}


def test_openapi_documents_catalog_contract() -> None:
    schema = create_app(database_url="").openapi()
    operation = schema["paths"]["/api/v1/catalog"]["get"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/CatalogResponse"
    }
    assert set(schema["components"]["schemas"]["CatalogResponse"]["properties"]) == {
        "version",
        "generated_at",
        "pricing",
        "categories",
    }
