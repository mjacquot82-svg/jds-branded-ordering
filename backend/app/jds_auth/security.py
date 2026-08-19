import hashlib
import hmac
import secrets
import base64

PIN_SCRYPT_N = 2**14
PIN_SCRYPT_R = 8
PIN_SCRYPT_P = 1


def create_secret() -> str:
    return secrets.token_urlsafe(48)


def hash_secret(secret: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), secret.encode(), hashlib.sha256).hexdigest()


def secret_matches(secret: str, expected_hash: str, pepper: str) -> bool:
    return hmac.compare_digest(hash_secret(secret, pepper), expected_hash)


def hash_pin(pin: str, pepper: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        pin.encode(), salt=salt, n=PIN_SCRYPT_N, r=PIN_SCRYPT_R,
        p=PIN_SCRYPT_P, dklen=32, maxmem=64 * 1024 * 1024,
    )
    mac = hmac.new(pepper.encode(), derived, hashlib.sha256).digest()
    return "scrypt$16384$8$1$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(mac).decode()


def pin_matches(pin: str, verifier: str, pepper: str) -> bool:
    try:
        algorithm, n, r, p, encoded_salt, encoded_mac = verifier.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(encoded_salt.encode())
        expected = base64.urlsafe_b64decode(encoded_mac.encode())
        derived = hashlib.scrypt(
            pin.encode(), salt=salt, n=int(n), r=int(r), p=int(p),
            dklen=32, maxmem=64 * 1024 * 1024,
        )
        actual = hmac.new(pepper.encode(), derived, hashlib.sha256).digest()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False
