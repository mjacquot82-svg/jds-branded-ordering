"""M3: the shipped JDS illustrated starter pack is complete, valid, and safely served."""
from __future__ import annotations

from io import BytesIO

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from app.api.v1.platform import list_starter_media, storefront_starter_media
from app.main import create_app
from app.platform import starter_media
from app.platform.demo_starter import STARTER_PRODUCTS, starter_product_image_reference

SHIPPED_KEYS = {
    "brewed-coffee", "espresso", "latte", "cappuccino", "iced-latte", "iced-coffee",
    "hot-tea", "hot-chocolate", "iced-tea", "lemonade-fruit-cooler", "smoothie",
    "plain-croissant", "filled-croissant-danish", "muffin", "cookie", "donut",
    "brownie-dessert-square", "scone", "loaf-slice", "breakfast-sandwich", "toast",
    "yogurt-granola", "deli-sandwich", "wrap", "creamy-soup", "green-salad",
}


@pytest.fixture(autouse=True)
def default_root(monkeypatch):
    monkeypatch.delenv("JDS_STARTER_MEDIA_ROOT", raising=False)


def test_shipped_pack_covers_curated_archetypes_with_valid_square_webp() -> None:
    available = {a.key for a in starter_media.STARTER_MEDIA_ASSETS if starter_media.starter_asset_available(a)}
    assert available == SHIPPED_KEYS
    for asset in starter_media.STARTER_MEDIA_ASSETS:
        if asset.key not in available:
            continue
        data = starter_media.starter_asset_path(asset).read_bytes()
        assert len(data) < 200_000
        with Image.open(BytesIO(data)) as image:
            assert image.format == "WEBP"
            assert image.size == (asset.width, asset.height) == (1200, 1200)


def test_every_shipped_category_group_has_art_and_list_marks_placeholders() -> None:
    payload = list_starter_media("cafe-restaurant", object())
    assert len(payload["assets"]) == 70
    shipped = [a for a in payload["assets"] if a["available"]]
    assert len(shipped) == len(SHIPPED_KEYS)
    assert {a["category"] for a in shipped} >= {"coffee", "tea-specialty-drinks", "cold-drinks", "breakfast", "bakery", "sandwiches-wraps", "soup-salad"}
    assert all(a["artStyle"] == starter_media.STARTER_MEDIA_ART_STYLE and a["thumbnailUrl"].startswith("/api/v1/storefront/starter-media/cafe-restaurant/") for a in shipped)
    assert all(a["artStyle"] is None and a["thumbnailUrl"] is None for a in payload["assets"] if not a["available"])


def test_harbor_and_hearth_starter_products_reference_available_art() -> None:
    for product in STARTER_PRODUCTS:
        reference = starter_product_image_reference(product[1])
        assert reference, product
        asset = starter_media.starter_asset(reference)
        assert asset is not None and starter_media.starter_asset_available(asset)


def test_public_starter_endpoint_serves_immutable_webp_and_rejects_bad_refs() -> None:
    response = storefront_starter_media("cafe-restaurant", "latte", 1)
    assert response.media_type == "image/webp"
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    for collection, key, version in (
        ("cafe-restaurant", "americano", 1),  # manifest entry without shipped art
        ("cafe-restaurant", "not-real", 1),
        ("cafe-restaurant", "latte", 2),
        ("other-collection", "latte", 1),
        ("cafe-restaurant", "../latte", 1),
        ("..", "cafe-restaurant/latte", 1),
    ):
        with pytest.raises(HTTPException) as error:
            storefront_starter_media(collection, key, version)
        assert error.value.status_code == 404


def test_starter_http_route_serves_public_image_without_path_escape() -> None:
    with TestClient(create_app()) as client:
        image = client.get("/api/v1/storefront/starter-media/cafe-restaurant/muffin?version=1")
        assert image.status_code == 200 and image.headers["content-type"] == "image/webp"
        assert image.content[:4] == b"RIFF" and image.content[8:12] == b"WEBP"
        assert client.get("/api/v1/storefront/starter-media/cafe-restaurant/%2E%2E%2Fsecret?version=1").status_code == 404
        assert client.get("/api/v1/storefront/starter-media/cafe-restaurant/latte?version=abc").status_code == 422
