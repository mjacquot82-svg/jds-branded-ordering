from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.owner_catalog import require_catalog_organization, require_modifier_manager
from app.catalog.schemas import OwnerModifierGroupWrite, OwnerModifierOptionWrite
from app.catalog.service import CatalogService
from app.jds_auth.service import AuthPrincipal


def principal(*permissions: str, organization_id=None, role="owner") -> AuthPrincipal:
    return AuthPrincipal(
        user_id=uuid4(), membership_id=uuid4(),
        organization_id=organization_id or uuid4(), application_id=uuid4(),
        session_id=uuid4(), email="owner@example.test", display_name="Owner",
        role=role, permissions=frozenset(permissions), assurance_level="password",
    )


def test_modifier_permission_allows_owner_capability_and_denies_staff() -> None:
    organization_id = uuid4()
    service = SimpleNamespace(_session=SimpleNamespace(scalar=lambda _: organization_id))
    settings = SimpleNamespace(organization_slug="the-guest-house")
    owner = principal("modifiers.manage", organization_id=organization_id)
    assert require_modifier_manager(owner, service, settings) is owner
    with pytest.raises(HTTPException) as denied:
        require_modifier_manager(principal("catalog.read", organization_id=organization_id, role="staff"), service, settings)
    assert denied.value.status_code == 403


def test_catalog_organization_is_server_derived() -> None:
    organization_id = uuid4()
    service = SimpleNamespace(_session=SimpleNamespace(scalar=lambda _: organization_id))
    settings = SimpleNamespace(organization_slug="the-guest-house")
    require_catalog_organization(principal("modifiers.manage", organization_id=organization_id), service, settings)
    with pytest.raises(HTTPException) as denied:
        require_catalog_organization(principal("modifiers.manage"), service, settings)
    assert denied.value.status_code == 403
    assert denied.value.detail["code"] == "organization_denied"


@pytest.mark.parametrize("payload,message", [
    (dict(required=True, min_selections=0), "minimum"),
    (dict(required=False, min_selections=1), "minimum of zero"),
    (dict(selection_type="single", max_selections=2, allow_quantity=False), "maximum of one"),
    (dict(selection_type="multiple", required=True, min_selections=2, max_selections=1), "Maximum selections"),
])
def test_group_selection_validation(payload: dict, message: str) -> None:
    values = dict(
        name="Test group", selection_type="single", required=False,
        min_selections=0, max_selections=1,
    )
    values.update(payload)
    with pytest.raises(ValueError, match=message):
        CatalogService._validate_group_write(OwnerModifierGroupWrite(**values))


@pytest.mark.parametrize(("selection_type", "allow_quantity", "max_selections"), [
    ("single", False, 1),
    ("single", True, 0),
    ("single", True, 3),
    ("multiple", False, 0),
    ("multiple", True, 0),
    ("multiple", True, 3),
])
def test_distinct_selection_mode_and_same_option_quantity_are_independent(
    selection_type: str, allow_quantity: bool, max_selections: int,
) -> None:
    payload = OwnerModifierGroupWrite(
        name="Generic group", selection_type=selection_type, required=False,
        min_selections=0, max_selections=max_selections,
        allow_quantity=allow_quantity,
    )
    CatalogService._validate_group_write(payload)


def test_price_adjustments_are_nonnegative_integer_minor_units() -> None:
    assert OwnerModifierOptionWrite(name="Included", price_adjustment_cents=0).price_adjustment_cents == 0
    assert OwnerModifierOptionWrite(name="Extra", price_adjustment_cents=75).price_adjustment_cents == 75
    with pytest.raises(ValueError):
        OwnerModifierOptionWrite(name="Invalid", price_adjustment_cents=-1)
    with pytest.raises(ValueError):
        OwnerModifierOptionWrite(name="Invalid", price_adjustment_cents=0.75)
