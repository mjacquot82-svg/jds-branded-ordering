from io import BytesIO
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from PIL import Image

from app.platform.media import (
    LocalMediaStorage,
    MediaStorageError,
    MediaValidationError,
    SupabaseMediaStorage,
    configured_media_storage,
    prepare_image,
)


def png(width: int = 32, height: int = 24, *, metadata: bool = False) -> bytes:
    output = BytesIO()
    info = None
    if metadata:
        from PIL.PngImagePlugin import PngInfo
        info = PngInfo(); info.add_text("Comment", "private camera metadata")
    Image.new("RGB", (width, height), "#b98564").save(output, "PNG", pnginfo=info)
    return output.getvalue()


def test_local_storage_remains_available_for_test_and_development(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JDS_MEDIA_STORAGE", "local")
    monkeypatch.setenv("JDS_LOCAL_MEDIA_ROOT", str(tmp_path))
    storage = configured_media_storage("test")
    assert isinstance(storage, LocalMediaStorage)
    key, checksum = storage.put(uuid4(), uuid4(), png(), "image/png")
    assert storage.read(key) == png()
    assert len(checksum) == 64
    storage.delete(key)
    with pytest.raises(FileNotFoundError):
        storage.read(key)


def test_production_refuses_local_or_implicit_storage(monkeypatch) -> None:
    monkeypatch.setenv("JDS_MEDIA_STORAGE", "local")
    with pytest.raises(MediaStorageError, match="refuses temporary"):
        configured_media_storage("production")
    monkeypatch.delenv("JDS_MEDIA_STORAGE")
    with pytest.raises(MediaStorageError, match="requires explicit"):
        configured_media_storage("production")


def test_supabase_configuration_is_explicit_and_private(monkeypatch) -> None:
    monkeypatch.setenv("JDS_MEDIA_STORAGE", "supabase")
    monkeypatch.setenv("JDS_SUPABASE_STORAGE_URL", "https://project.supabase.co")
    monkeypatch.setenv("JDS_SUPABASE_STORAGE_SERVICE_ROLE_KEY", "test-secret")
    monkeypatch.setenv("JDS_SUPABASE_STORAGE_BUCKET", "tenant-media")
    storage = configured_media_storage("production")
    assert isinstance(storage, SupabaseMediaStorage)
    assert storage.bucket == "tenant-media"
    monkeypatch.delenv("JDS_SUPABASE_STORAGE_SERVICE_ROLE_KEY")
    with pytest.raises(MediaStorageError, match="incomplete"):
        configured_media_storage("production")


def test_supabase_objects_are_tenant_scoped_and_use_authorized_server_requests(monkeypatch) -> None:
    calls: list[tuple[str, str, dict[str, str]]] = []
    def response(method: str, url: str, **kwargs):
        calls.append((method, url, kwargs["headers"]))
        return httpx.Response(200, content=png(), request=httpx.Request(method, url))
    monkeypatch.setattr(httpx, "post", lambda url, **kwargs: response("POST", url, **kwargs))
    monkeypatch.setattr(httpx, "get", lambda url, **kwargs: response("GET", url, **kwargs))
    monkeypatch.setattr(httpx, "request", lambda method, url, **kwargs: response(method, url, **kwargs))
    organization_id, media_id = uuid4(), uuid4()
    storage = SupabaseMediaStorage("https://project.supabase.co", "secret", "tenant-media")
    key, _ = storage.put(organization_id, media_id, png(), "image/png")
    assert key == f"tenants/{organization_id}/{media_id}.png"
    assert storage.read(key) == png()
    storage.delete(key)
    assert [method for method, _, _ in calls] == ["POST", "GET", "DELETE"]
    assert all(headers["Authorization"] == "Bearer secret" for _, _, headers in calls)


def test_image_processing_rejects_spoofing_and_dimensions_and_strips_metadata() -> None:
    with pytest.raises(MediaValidationError, match="does not match"):
        prepare_image(png(), "image/jpeg")
    with pytest.raises(MediaValidationError, match="total pixels"):
        prepare_image(png(7000, 6000), "image/png")
    prepared = prepare_image(png(metadata=True), "image/png")
    assert prepared.width == 32 and prepared.height == 24
    assert b"private camera metadata" not in prepared.data
