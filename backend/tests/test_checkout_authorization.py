from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.customer_auth import current_ordering_customer
from app.jds_auth.service import AuthPrincipal


def principal(role: str) -> AuthPrincipal:
    return AuthPrincipal(
        user_id=uuid4(), membership_id=uuid4(), organization_id=uuid4(),
        application_id=uuid4(), session_id=uuid4(), email=f"{role}@example.com",
        display_name=role.title(), role=role, permissions=frozenset(),
        assurance_level="aal1",
    )


def test_dedicated_customer_role_can_use_ordering_boundary() -> None:
    customer = principal("customer")
    assert current_ordering_customer(customer) is customer


@pytest.mark.parametrize("role", ["owner", "staff", "kitchen", "manager"])
def test_operational_roles_cannot_use_customer_ordering_boundary(role: str) -> None:
    with pytest.raises(HTTPException) as caught:
        current_ordering_customer(principal(role))
    assert caught.value.status_code == 403
    assert caught.value.detail["code"] == "customer_required"
