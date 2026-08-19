import pytest
from pydantic import ValidationError

from app.customers.schemas import GuestCustomerInput
from app.orders.schemas import (
    ConfiguredOrderLineInput,
    CreatePendingOrderInput,
)


def test_guest_customer_normalizes_contact_information() -> None:
    customer = GuestCustomerInput(
        name="  Jessie   Guest  ",
        email="  JESSIE@EXAMPLE.COM ",
        phone="+1 (555) 123-4567",
    )

    assert customer.name == "Jessie Guest"
    assert customer.email == "jessie@example.com"
    assert customer.phone == "+15551234567"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", " "),
        ("name", "mjacquot82"),
        ("email", "not-an-email"),
        ("email", "guest@example"),
        ("phone", "123"),
        ("phone", "555-CALL-NOW"),
    ],
)
def test_guest_customer_rejects_invalid_contact_information(
    field: str,
    value: str,
) -> None:
    values = {
        "name": "Jessie Guest",
        "email": "jessie@example.com",
        "phone": "+15551234567",
    }
    values[field] = value

    with pytest.raises(ValidationError):
        GuestCustomerInput(**values)


def test_order_input_forbids_client_prices_and_requires_aware_pickup() -> None:
    with pytest.raises(ValidationError, match="price_cents"):
        ConfiguredOrderLineInput(
            product_id=1,
            variant_id=None,
            modifier_option_ids=[],
            quantity=1,
            price_cents=1,
        )

    with pytest.raises(ValidationError):
        CreatePendingOrderInput(
            idempotency_key="request-123",
            customer=GuestCustomerInput(
                name="Jessie Guest",
                email="jessie@example.com",
                phone="+15551234567",
            ),
            requested_pickup_at="2026-07-28T08:30:00",
            notes=None,
            lines=[
                ConfiguredOrderLineInput(
                    product_id=1,
                    variant_id=None,
                    modifier_option_ids=[],
                    quantity=1,
                )
            ],
        )


def test_order_notes_are_optional_trimmed_and_bounded() -> None:
    base_values = {
        "idempotency_key": "request-123",
        "customer": GuestCustomerInput(
            name="Jessie Guest",
            email="jessie@example.com",
            phone="+15551234567",
        ),
        "requested_pickup_at": "2026-07-28T08:30:00-04:00",
        "lines": [
            ConfiguredOrderLineInput(
                product_id=1,
                variant_id=None,
                modifier_option_ids=[],
                quantity=1,
            )
        ],
    }

    assert CreatePendingOrderInput(**base_values, notes="  ").notes is None
    assert (
        CreatePendingOrderInput(**base_values, notes="  Extra hot  ").notes
        == "Extra hot"
    )
    with pytest.raises(ValidationError):
        CreatePendingOrderInput(**base_values, notes="x" * 2001)
