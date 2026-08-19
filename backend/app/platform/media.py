from __future__ import annotations

import hashlib
import os
from pathlib import Path
from uuid import UUID


class MediaValidationError(ValueError):
    pass


_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def media_root() -> Path:
    root = Path(os.getenv("JDS_LOCAL_MEDIA_ROOT", "/tmp/jds-local-media")).resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root


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


def persist_local_image(organization_id: UUID, media_id: UUID, data: bytes, media_type: str) -> tuple[str, str]:
    validate_image(data, media_type)
    extension = _EXTENSIONS.get(media_type)
    if extension is None:
        raise MediaValidationError("Use a PNG, JPEG, or WebP image.")
    relative = Path(str(organization_id)) / f"{media_id}.{extension}"
    destination = media_root() / relative
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination.write_bytes(data)
    return relative.as_posix(), hashlib.sha256(data).hexdigest()


def local_media_path(storage_key: str) -> Path:
    root = media_root()
    candidate = (root / storage_key).resolve()
    if root not in candidate.parents:
        raise MediaValidationError("Invalid media storage key.")
    return candidate
