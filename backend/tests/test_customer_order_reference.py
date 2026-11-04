"""A customer reads the same order number the shop's queue shows (beta finding: two identifiers).

The readable number (`ZTC-000010`-style, derived from the shop's own prefix) is added to the
customer's order response as a display field. The public access token keeps its exact role:
the unguessable key in URLs, unchanged, never printed, and still the only way to look an
order up -- there is deliberately no lookup-by-readable-number route.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.api.v1.customer_auth import optional_ordering_customer
from app.orders.models import Order
from app.orders.reference import order_reference
from tests.test_orders_api import order_payload, orders_api  # noqa: F401


def _new_order(client, ids, key: str) -> dict:
    created = client.post("/api/v1/orders", json=order_payload(ids, idempotency_key=key))
    assert created.status_code == 201, created.text
    return created.json()


@pytest.mark.postgresql
def test_customer_order_response_carries_the_readable_number_and_the_token_unchanged(orders_api) -> None:  # noqa: F811
    client, engine, ids = orders_api
    body = _new_order(client, ids, "reference-create-0011")
    with Session(engine) as session:
        order = session.scalar(select(Order).where(Order.public_access_token == body["public_token"]))
        assert order is not None
        expected = order_reference(order)
    assert body["reference"] == expected
    # The readable number looks like a queue number, not like the token.
    assert body["reference"].count("-") == 1
    prefix, digits = body["reference"].split("-")
    assert 2 <= len(prefix) <= 3 and prefix.isupper()
    assert digits == f"{order.id:06d}"
    # The public token is untouched and still exactly what the create call returned.
    assert isinstance(body["public_token"], str) and len(body["public_token"]) >= 20
    assert body["public_token"] != body["reference"]


@pytest.mark.postgresql
def test_the_readable_number_matches_what_the_owner_queue_shows(orders_api) -> None:  # noqa: F811
    client, engine, ids = orders_api
    body = _new_order(client, ids, "reference-create-0012")
    with Session(engine) as session:
        order = session.scalar(select(Order).where(Order.public_access_token == body["public_token"]))
        from app.api.v1.owner_orders import OwnerOrderResponse

        # One identifier: the customer's response and the shop's queue format the same row alike.
        assert body["reference"] == OwnerOrderResponse.from_model(order).reference


@pytest.mark.postgresql
def test_a_guest_still_sees_only_their_own_order_and_only_by_token(orders_api) -> None:  # noqa: F811
    client, engine, ids = orders_api
    signed_in = client.app.dependency_overrides[optional_ordering_customer]
    member = _new_order(client, ids, "reference-member-0001")

    client.app.dependency_overrides[optional_ordering_customer] = lambda: None
    guest = _new_order(client, ids, "reference-guest-0001")

    # The guest's own order opens by token, and it shows a readable number.
    own = client.get(f"/api/v1/orders/{guest['public_token']}")
    assert own.status_code == 200
    assert own.json()["reference"] == guest["reference"]
    # Another customer's order is not reachable, whatever it is called.
    assert client.get(f"/api/v1/orders/{member['public_token']}").status_code == 404
    client.app.dependency_overrides[optional_ordering_customer] = signed_in

    # There is no route that looks an order up by its readable number.
    with TestClient(client.app) as schema_client:
        paths = schema_client.get("/openapi.json").json()["paths"]
    order_paths = [path for path in paths if "order" in path]
    assert all("{public_token}" in path or "reference" not in path for path in order_paths)
    assert f"/api/v1/orders/{guest['reference']}" not in paths


@pytest.mark.postgresql
def test_the_readable_number_is_not_a_search_key(orders_api) -> None:  # noqa: F811
    """Even the exact readable number must not resolve an order."""
    client, engine, ids = orders_api
    body = _new_order(client, ids, "reference-not-a-key-01")
    assert client.get(f"/api/v1/orders/{body['reference']}").status_code == 404
