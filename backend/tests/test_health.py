import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.mark.anyio
async def test_liveness_endpoint() -> None:
    transport = ASGITransport(app=create_app())

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.headers["X-Request-Id"]
    assert response.json() == {
        "status": "ok",
        "service": "guesthouse-backend",
        "version": "0.1.0",
    }


@pytest.mark.anyio
async def test_request_id_is_propagated_or_safely_replaced() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        propagated = await client.get(
            "/health/live", headers={"X-Request-Id": "local-test:123"}
        )
        replaced = await client.get(
            "/health/live", headers={"X-Request-Id": "unsafe value"}
        )

    assert propagated.headers["X-Request-Id"] == "local-test:123"
    assert replaced.headers["X-Request-Id"] != "unsafe value"
    uuid.UUID(replaced.headers["X-Request-Id"])
