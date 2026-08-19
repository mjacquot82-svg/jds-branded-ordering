from __future__ import annotations

from abc import ABC, abstractmethod
import hashlib
import os
from pathlib import Path
from uuid import UUID


class MediaValidationError(ValueError):
    pass


_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def validate_image(data: bytes, media_type: str) -> None:
    if not data or len(data) > 10_000_000:
        raise MediaValidationError("Images must be between 1 byte and 10 MB.")
    valid = (
        media_type == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n")
        or media_type == "image/jpeg" and data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9")
        or media_type == "image/webp" and len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    )
    if not valid:
        raise MediaValidationError("Image content does not match its declared file type.")


class MediaStorage(ABC):
    """Storage port; tenant authorization remains in the application layer."""

    @abstractmethod
    def put(self, organization_id: UUID, media_id: UUID, data: bytes, media_type: str) -> tuple[str, str]:
        raise NotImplementedError

    @abstractmethod
    def local_path(self, storage_key: str) -> Path:
        raise NotImplementedError

    @abstractmethod
    def delete(self, storage_key: str) -> None:
        raise NotImplementedError


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
        validate_image(data, media_type)
        extension = _EXTENSIONS.get(media_type)
        if extension is None:
            raise MediaValidationError("Use a PNG, JPEG, or WebP image.")
        relative = Path(str(organization_id)) / f"{media_id}.{extension}"
        destination = self._safe_path(relative.as_posix())
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = destination.with_suffix(f"{destination.suffix}.uploading")
        temporary.write_bytes(data)
        temporary.replace(destination)
        return relative.as_posix(), hashlib.sha256(data).hexdigest()

    def local_path(self, storage_key: str) -> Path:
        return self._safe_path(storage_key)

    def delete(self, storage_key: str) -> None:
        path = self._safe_path(storage_key)
        path.unlink(missing_ok=True)
        try:
            path.parent.rmdir()
        except OSError:
            pass


def media_root() -> Path:
    return Path(os.getenv("JDS_LOCAL_MEDIA_ROOT", "/tmp/jds-local-media")).resolve()


def default_media_storage() -> MediaStorage:
    return LocalMediaStorage(media_root())


def persist_local_image(organization_id: UUID, media_id: UUID, data: bytes, media_type: str) -> tuple[str, str]:
    return default_media_storage().put(organization_id, media_id, data, media_type)


def local_media_path(storage_key: str) -> Path:
    return default_media_storage().local_path(storage_key)
