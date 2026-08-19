import os

import pytest
from sqlalchemy import create_engine, text

from app.tenancy.resolver import (
    LADELS_ORGANIZATION_ID,
    LADELS_ORGANIZATION_NAME,
    LADELS_ORGANIZATION_SLUG,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def postgresql_url() -> str:
    database_url = os.getenv("TEST_DATABASE_URL")

    if not database_url:
        pytest.fail("TEST_DATABASE_URL is required for PostgreSQL integration tests.")

    return database_url


@pytest.fixture(autouse=True)
def preserve_ladels_compatibility_organization() -> None:
    """Keep destructive database fixtures independent at migration head."""

    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        return
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            if connection.scalar(text("SELECT to_regclass('organizations')")) is None:
                return
            connection.execute(
                text(
                    "INSERT INTO organizations (id, slug, name, is_active) "
                    "VALUES (CAST(:id AS uuid), :slug, :name, true) "
                    "ON CONFLICT (slug) DO NOTHING"
                ),
                {
                    "id": str(LADELS_ORGANIZATION_ID),
                    "slug": LADELS_ORGANIZATION_SLUG,
                    "name": LADELS_ORGANIZATION_NAME,
                },
            )
    finally:
        engine.dispose()
