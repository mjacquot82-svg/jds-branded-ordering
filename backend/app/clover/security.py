import base64
import hashlib
import hmac
import json
import secrets
import time

from cryptography.fernet import Fernet, InvalidToken


class InvalidOAuthState(ValueError):
    pass


class InvalidWebhookSignature(ValueError):
    pass


def create_oauth_state(
    secret: str, *, organization_id: str | None = None,
    membership_id: str | None = None, environment: str | None = None,
    app_id: str | None = None, now: int | None = None,
) -> str:
    payload = {
        "iat": int(time.time() if now is None else now),
        "nonce": secrets.token_urlsafe(24),
    }
    if organization_id is not None:
        payload.update({
            "organization_id": organization_id,
            "membership_id": membership_id,
            "environment": environment,
            "app_id": app_id,
        })
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    signature = hmac.new(
        secret.encode(), encoded.encode(), hashlib.sha256
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{encoded}.{encoded_signature}"


def verify_oauth_state(
    state: str,
    secret: str,
    *,
    max_age_seconds: int = 600,
    now: int | None = None,
) -> dict[str, object]:
    try:
        encoded, supplied_signature = state.split(".", 1)
        expected = hmac.new(
            secret.encode(), encoded.encode(), hashlib.sha256
        ).digest()
        signature = base64.urlsafe_b64decode(
            supplied_signature + "=" * (-len(supplied_signature) % 4)
        )
        if not hmac.compare_digest(signature, expected):
            raise InvalidOAuthState("OAuth state signature is invalid.")
        payload = json.loads(
            base64.urlsafe_b64decode(
                encoded + "=" * (-len(encoded) % 4)
            ).decode()
        )
        issued_at = int(payload["iat"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise InvalidOAuthState("OAuth state is invalid.") from error

    current_time = int(time.time() if now is None else now)
    if issued_at > current_time + 30 or current_time - issued_at > max_age_seconds:
        raise InvalidOAuthState("OAuth state has expired.")
    return payload


def oauth_nonce_hash(nonce: object) -> str:
    if not isinstance(nonce, str) or not nonce:
        raise InvalidOAuthState("OAuth state nonce is invalid.")
    return hashlib.sha256(nonce.encode()).hexdigest()


class TokenCipher:
    def __init__(self, key: str):
        self._fernet = Fernet(key.encode())

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as error:
            raise ValueError("Stored Clover token cannot be decrypted.") from error


def verify_webhook_signature(
    raw_body: bytes,
    signature_header: str,
    secret: str,
    *,
    tolerance_seconds: int = 300,
    now: int | None = None,
) -> None:
    parts = dict(
        part.split("=", 1)
        for part in signature_header.split(",")
        if "=" in part
    )
    try:
        timestamp = int(parts["t"])
        supplied = parts["v1"]
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidWebhookSignature("Clover signature is malformed.") from error
    current_time = int(time.time() if now is None else now)
    if abs(current_time - timestamp) > tolerance_seconds:
        raise InvalidWebhookSignature("Clover signature has expired.")
    signed_payload = str(timestamp).encode() + b"." + raw_body
    expected = hmac.new(
        secret.encode(), signed_payload, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(supplied, expected):
        raise InvalidWebhookSignature("Clover signature is invalid.")
