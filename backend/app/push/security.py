import hashlib
from cryptography.fernet import Fernet, InvalidToken

class SubscriptionProtector:
    def __init__(self, key: str):
        self._fernet = Fernet(key.encode())
    def encrypt(self, value: str) -> bytes:
        return self._fernet.encrypt(value.encode())
    def decrypt(self, value: bytes) -> str:
        try: return self._fernet.decrypt(value).decode()
        except InvalidToken as exc: raise ValueError("Stored push capability cannot be decrypted") from exc

def endpoint_fingerprint(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode()).hexdigest()
