from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import hashlib
from io import BytesIO
import os
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_BYTES = 10_000_000
MAX_IMAGE_WIDTH = 12_000
MAX_IMAGE_HEIGHT = 12_000
MAX_IMAGE_PIXELS = 40_000_000
_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
_PIL_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


class MediaValidationError(ValueError):
    pass


class MediaStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedImage:
    data: bytes
    media_type: str
    width: int
    height: int
    checksum: str


def _signature_matches(data: bytes, media_type: str) -> bool:
    return (
        media_type == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n")
        or media_type == "image/jpeg" and data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9")
        or media_type == "image/webp" and len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    )


def prepare_image(data: bytes, declared_media_type: str) -> PreparedImage:
    """Validate decoded content and return a metadata-free, web-optimized image."""
    media_type = declared_media_type.split(";", 1)[0].strip().lower()
    if media_type not in _EXTENSIONS:
        raise MediaValidationError("Use a PNG, JPEG, or WebP image.")
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise MediaValidationError("Images must be between 1 byte and 10 MB.")
    if not _signature_matches(data, media_type):
        raise MediaValidationError("Image content does not match its declared file type.")
    try:
        with Image.open(BytesIO(data)) as source:
            if _PIL_FORMATS.get(source.format or "") != media_type:
                raise MediaValidationError("Image content does not match its declared file type.")
            width, height = source.size
            if width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT or width * height > MAX_IMAGE_PIXELS:
                raise MediaValidationError(
                    f"Images may be at most {MAX_IMAGE_WIDTH} × {MAX_IMAGE_HEIGHT} pixels and {MAX_IMAGE_PIXELS:,} total pixels."
                )
            source.load()
            normalized = ImageOps.exif_transpose(source)
            output = BytesIO()
            if media_type == "image/jpeg":
                if normalized.mode not in {"RGB", "L"}:
                    background = Image.new("RGB", normalized.size, "white")
                    if "A" in normalized.getbands():
                        background.paste(normalized, mask=normalized.getchannel("A"))
                    else:
                        background.paste(normalized)
                    normalized = background
                normalized.save(output, "JPEG", quality=85, optimize=True, progressive=True)
            elif media_type == "image/png":
                normalized.save(output, "PNG", optimize=True)
            else:
                normalized.save(output, "WEBP", quality=85, method=4)
            normalized_width, normalized_height = normalized.size
    except MediaValidationError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as error:
        raise MediaValidationError("This image could not be read. Use a valid PNG, JPEG, or WebP image.") from error
    optimized = output.getvalue()
    if len(optimized) > MAX_IMAGE_BYTES:
        raise MediaValidationError("The optimized image exceeds the 10 MB limit.")
    return PreparedImage(optimized, media_type, normalized_width, normalized_height, hashlib.sha256(optimized).hexdigest())


def image_dimensions(data: bytes) -> tuple[int, int]:
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            return image.size
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as error:
        raise MediaValidationError("This image could not be read. Use a valid PNG, JPEG, or WebP image.") from error


def validate_image(data: bytes, media_type: str) -> tuple[int, int]:
    prepared = prepare_image(data, media_type)
    return prepared.width, prepared.height


class MediaStorage(ABC):
    """Private blob storage port; tenant authorization remains in the application layer."""

    @abstractmethod
    def put(self, organization_id: UUID, media_id: UUID, data: bytes, media_type: str) -> tuple[str, str]: ...

    @abstractmethod
    def read(self, storage_key: str) -> bytes: ...

    @abstractmethod
    def delete(self, storage_key: str) -> None: ...


class LocalMediaStorage(MediaStorage):
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def _safe_path(self, storage_key: str) -> Path:
        candidate = (self.root / storage_key).resolve()
        if self.root not in candidate.parents:
            raise MediaValidationError("Invalid media storage key.")
        return candidate

    def put(self, organization_id: UUID, media_id: UUID, data: bytes, media_type: str) -> tuple[str, str]:
        if media_type not in _EXTENSIONS or not _signature_matches(data, media_type):
            raise MediaValidationError("Use a valid PNG, JPEG, or WebP image.")
        relative = Path(str(organization_id)) / f"{media_id}.{_EXTENSIONS[media_type]}"
        destination = self._safe_path(relative.as_posix())
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = destination.with_suffix(f"{destination.suffix}.uploading")
        temporary.write_bytes(data)
        temporary.replace(destination)
        return relative.as_posix(), hashlib.sha256(data).hexdigest()

    def local_path(self, storage_key: str) -> Path:
        return self._safe_path(storage_key)

    def read(self, storage_key: str) -> bytes:
        return self._safe_path(storage_key).read_bytes()

    def delete(self, storage_key: str) -> None:
        path = self._safe_path(storage_key)
        path.unlink(missing_ok=True)
        try:
            path.parent.rmdir()
        except OSError:
            pass


class SupabaseMediaStorage(MediaStorage):
    """Server-side adapter for one private, platform-managed Supabase bucket."""

    def __init__(self, url: str, service_role_key: str, bucket: str, *, timeout_seconds: float = 20.0) -> None:
        if not url.startswith("https://") or not service_role_key or not bucket:
            raise MediaStorageError("Supabase media storage configuration is incomplete or unsafe.")
        if "/" in bucket or bucket in {".", ".."}:
            raise MediaStorageError("Supabase media bucket name is invalid.")
        self.url = url.rstrip("/")
        self.service_role_key = service_role_key
        self.bucket = bucket
        self.timeout_seconds = timeout_seconds

    def _object_url(self, storage_key: str) -> str:
        return f"{self.url}/storage/v1/object/{quote(self.bucket, safe='')}/{quote(storage_key, safe='/')}"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.service_role_key}", "apikey": self.service_role_key}

    @staticmethod
    def _check(response: httpx.Response, action: str) -> None:
        if not response.is_success:
            raise MediaStorageError(f"Permanent media storage could not {action} the object (status {response.status_code}).")

    def put(self, organization_id: UUID, media_id: UUID, data: bytes, media_type: str) -> tuple[str, str]:
        if media_type not in _EXTENSIONS or not _signature_matches(data, media_type):
            raise MediaValidationError("Use a valid PNG, JPEG, or WebP image.")
        storage_key = f"tenants/{organization_id}/{media_id}.{_EXTENSIONS[media_type]}"
        try:
            response = httpx.post(self._object_url(storage_key), headers={**self._headers(), "Content-Type": media_type, "x-upsert": "false"}, content=data, timeout=self.timeout_seconds)
        except httpx.HTTPError as error:
            raise MediaStorageError("Permanent media storage is unavailable.") from error
        self._check(response, "store")
        return storage_key, hashlib.sha256(data).hexdigest()

    def read(self, storage_key: str) -> bytes:
        try:
            response = httpx.get(self._object_url(storage_key), headers=self._headers(), timeout=self.timeout_seconds)
        except httpx.HTTPError as error:
            raise MediaStorageError("Permanent media storage is unavailable.") from error
        self._check(response, "read")
        return response.content

    def delete(self, storage_key: str) -> None:
        try:
            bucket_url = f"{self.url}/storage/v1/object/{quote(self.bucket, safe='')}"
            response = httpx.request("DELETE", bucket_url, headers={**self._headers(), "Content-Type": "application/json"}, json={"prefixes": [storage_key]}, timeout=self.timeout_seconds)
        except httpx.HTTPError as error:
            raise MediaStorageError("Permanent media storage is unavailable.") from error
        self._check(response, "delete")


def media_root() -> Path:
    return Path(os.getenv("JDS_LOCAL_MEDIA_ROOT", "/tmp/jds-local-media")).resolve()


def configured_media_storage(environment: str | None = None) -> MediaStorage:
    runtime = (environment if environment is not None else os.getenv("JDS_ENVIRONMENT", "")).strip().lower()
    mode = os.getenv("JDS_MEDIA_STORAGE", "local" if runtime in {"", "development", "test"} else "").strip().lower()
    if mode == "local":
        if runtime == "production":
            raise MediaStorageError("Production refuses temporary local media storage. Configure JDS_MEDIA_STORAGE=supabase.")
        return LocalMediaStorage(media_root())
    if mode == "supabase":
        return SupabaseMediaStorage(os.getenv("JDS_SUPABASE_STORAGE_URL", ""), os.getenv("JDS_SUPABASE_STORAGE_SERVICE_ROLE_KEY", ""), os.getenv("JDS_SUPABASE_STORAGE_BUCKET", ""))
    if runtime == "production":
        raise MediaStorageError("Production requires explicit permanent media storage configuration.")
    raise MediaStorageError("JDS_MEDIA_STORAGE must be 'local' or 'supabase'.")


def default_media_storage() -> MediaStorage:
    return configured_media_storage()


def persist_local_image(organization_id: UUID, media_id: UUID, data: bytes, media_type: str) -> tuple[str, str]:
    return LocalMediaStorage(media_root()).put(organization_id, media_id, data, media_type)


def local_media_path(storage_key: str) -> Path:
    return LocalMediaStorage(media_root()).local_path(storage_key)
