"""Square webhook signature check and token encryption."""

from __future__ import annotations

import base64
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken


class InvalidSquareSignature(ValueError):
    pass


def square_signature(raw_body: bytes, notification_url: str, signature_key: str) -> str:
    digest = hmac.new(
        signature_key.encode(), notification_url.encode() + raw_body, hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode()


def verify_square_signature(
    raw_body: bytes, signature_header: str | None, notification_url: str, signature_key: str
) -> None:
    """Square signs base64(HMAC-SHA256(key, notification_url + raw_body))."""
    if not signature_header or not signature_key:
        raise InvalidSquareSignature("Square signature is missing.")
    expected = square_signature(raw_body, notification_url, signature_key)
    if not hmac.compare_digest(signature_header.strip().encode(), expected.encode()):
        raise InvalidSquareSignature("Square signature is invalid.")


class SquareTokenCipher:
    def __init__(self, key: str):
        self._fernet = Fernet(key.encode())

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as error:
            raise ValueError("Stored Square token cannot be decrypted.") from error
