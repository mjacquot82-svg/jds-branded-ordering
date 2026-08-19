import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.mark.anyio
@pytest.mark.postgresql
async def test_readiness_succeeds_with_postgresql(postgresql_url: str) -> None:
    application = create_app(database_url=postgresql_url)
    transport = ASGITransport(app=application)

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")
    finally:
        application.state.db_engine.dispose()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "ok",
    }


@pytest.mark.anyio
async def test_readiness_fails_without_database_configuration() -> None:
    transport = ASGITransport(app=create_app(database_url=""))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "database": "failed",
    }
