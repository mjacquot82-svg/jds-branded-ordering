from app.jds_auth.foundation import ROLE_PERMISSIONS


def test_kitchen_permission_is_separate_from_operations_permissions() -> None:
    assert "orders.read" in ROLE_PERMISSIONS["staff"]
    assert "orders.fulfill" in ROLE_PERMISSIONS["staff"]
    assert "kitchen.orders" not in ROLE_PERMISSIONS["staff"]
    assert "kitchen.orders" not in ROLE_PERMISSIONS["owner"]
    assert "kitchen.orders" not in ROLE_PERMISSIONS["manager"]
