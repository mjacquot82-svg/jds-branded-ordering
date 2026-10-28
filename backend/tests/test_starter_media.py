from dataclasses import replace

from app.platform import starter_media
from app.api.v1.platform import list_starter_media


def test_v1_starter_manifest_is_coherent_and_versioned() -> None:
    assets = starter_media.STARTER_MEDIA_ASSETS
    assert len(assets) == 70
    assert len({asset.reference for asset in assets}) == len(assets)
    assert len({asset.key for asset in assets}) == len(assets)
    assert {asset.collection for asset in assets} == {"cafe-restaurant"}
    assert {asset.category for asset in assets} == {
        "coffee", "tea-specialty-drinks", "cold-drinks", "breakfast", "bakery",
        "sandwiches-wraps", "lunch-savoury", "soup-salad", "desserts", "packaged-retail",
    }
    assert all(asset.width == asset.height == 1200 for asset in assets)
    assert all(asset.tags and asset.alt_text.startswith("Generic ") for asset in assets)
    assert starter_media.starter_asset("starter:cafe-restaurant/latte@1").name == "Latte"
    assert starter_media.starter_asset("starter:cafe-restaurant/not-real@1") is None


def test_binary_availability_and_retirement_are_separate_from_resolution(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JDS_STARTER_MEDIA_ROOT", str(tmp_path))
    latte = starter_media.starter_asset("starter:cafe-restaurant/latte@1")
    assert not starter_media.starter_asset_available(latte)
    path = starter_media.starter_asset_path(latte)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"future-reviewed-binary")
    assert starter_media.starter_asset_available(latte)
    retired = replace(latte, active=False)
    assert not starter_media.starter_asset_available(retired)
    assert starter_media.starter_public_url(retired.reference).endswith("/latte?version=1")


def test_merchants_receive_same_platform_manifest_without_broken_thumbnail_urls(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JDS_STARTER_MEDIA_ROOT", str(tmp_path))
    left = list_starter_media("cafe-restaurant", object())
    right = list_starter_media("cafe-restaurant", object())
    assert left == right
    assert len(left["assets"]) == 70
    assert all(asset["thumbnailUrl"] is None and not asset["available"] for asset in left["assets"])


def test_representative_aliases_are_present_on_stable_archetypes() -> None:
    by_key = {asset.key: set(asset.tags) for asset in starter_media.STARTER_MEDIA_ASSETS}
    assert {"caramel", "maple", "hazelnut"} <= by_key["latte"]
    assert {"blt", "club", "turkey", "ham"} <= by_key["deli-sandwich"]
    assert {"bacon", "egg", "english", "muffin"} <= by_key["breakfast-sandwich"]
    assert {"chicken", "caesar"} <= by_key["wrap"]
    assert {"oat", "milk"} <= by_key["cappuccino"]
    assert {"coffee", "beans", "retail"} <= by_key["coffee-beans-bag"]
