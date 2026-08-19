from dataclasses import replace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.owner_auth import current_principal
from app.availability.models import ProductAvailability
from app.catalog.models import Category, Product
from app.jds_auth.foundation import ROLE_PERMISSIONS
from tests.test_owner_orders import owner_orders_api, principal


def test_staff_announcement_capability_is_narrow() -> None:
    assert "communications.announce" in ROLE_PERMISSIONS["staff"]
    assert "communications.announce" in ROLE_PERMISSIONS["owner"]
    assert "communications.general_announce" in ROLE_PERMISSIONS["owner"]
    assert "communications.general_announce" not in ROLE_PERMISSIONS["staff"]
    assert "integrations.manage" not in ROLE_PERMISSIONS["staff"]


@pytest.mark.postgresql
def test_communication_center_reports_honest_announcement_health(owner_orders_api) -> None:
    client, _ = owner_orders_api
    client.app.dependency_overrides[current_principal] = lambda: principal(
        "communications.announce"
    )

    response = client.get("/api/v1/owner/communications")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "actionable_warnings": 0,
        "lunch_special_attempting_today": False,
        "lunch_special_queued_today": False,
        "push_release_enabled": False,
    }
    assert payload["lunch_special"] is None
    assert payload["activity"] == []
    assert payload["health"] == [{
        "key": "push",
        "name": "Push notifications",
        "status": "not_connected",
        "detail": (
            "Customer push delivery is not connected yet. "
            "Announcement drafts cannot be sent."
        ),
        "actionable": False,
    }]
    assert "orders" not in payload
    assert "templates" not in payload


@pytest.mark.postgresql
def test_communication_center_reads_authoritative_lunch_special_and_warns_when_unavailable(
    owner_orders_api,
) -> None:
    client, engine = owner_orders_api
    client.app.dependency_overrides[current_principal] = lambda: principal(
        "communications.announce"
    )
    with Session(engine) as session:
        product = session.scalar(select(Product).order_by(Product.id))
        assert product is not None
        product.name = "Buffalo Chickpea Bowl"
        product.description = "Roasted vegetables and chickpeas."
        product.base_price_cents = 1295
        product.is_lunch_special = True
        product.is_published = True
        category = session.get(Category, product.category_id)
        assert category is not None
        category.is_published = True
        availability = session.scalar(
            select(ProductAvailability).where(ProductAvailability.product_id == product.id)
        )
        assert availability is not None
        availability.default_available = False
        session.commit()
        product_id = product.id
        product_image = product.image_reference or ""

    payload = client.get("/api/v1/owner/communications").json()

    assert payload["lunch_special"] == {
        "id": str(product_id),
        "name": "Buffalo Chickpea Bowl",
        "description": "Roasted vegetables and chickpeas.",
        "price_cents": 1295,
        "image": product_image,
        "customer_visible": True,
        "orderable": False,
        "warnings": ["This Lunch Special is unavailable for online ordering."],
    }


@pytest.mark.postgresql
def test_communication_center_allows_staff_with_existing_order_read_capability(
    owner_orders_api,
) -> None:
    client, _ = owner_orders_api
    staff = replace(principal("communications.announce"), role="staff")
    client.app.dependency_overrides[current_principal] = lambda: staff

    assert client.get("/api/v1/owner/communications").status_code == 200


@pytest.mark.postgresql
def test_communication_center_requires_announcement_permission(owner_orders_api) -> None:
    client, _ = owner_orders_api
    client.app.dependency_overrides[current_principal] = lambda: principal()
    assert client.get("/api/v1/owner/communications").status_code == 403
