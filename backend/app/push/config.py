import os
import base64
from cryptography.fernet import Fernet
from dataclasses import dataclass


@dataclass(frozen=True)
class PushSettings:
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_subject: str = ""
    encryption_key: str = ""
    enrollment_enabled: bool = False
    release_enabled: bool = False
    batch_size: int = 50
    request_timeout_seconds: float = 10.0
    default_ttl_seconds: int = 14_400
    general_ttl_seconds: int = 14_400
    max_attempts: int = 4
    retention_days: int = 90

    @classmethod
    def from_env(cls) -> "PushSettings":
        return cls(
            vapid_private_key=os.getenv("WEB_PUSH_VAPID_PRIVATE_KEY", ""),
            vapid_public_key=os.getenv("WEB_PUSH_VAPID_PUBLIC_KEY", ""),
            vapid_subject=os.getenv("WEB_PUSH_VAPID_SUBJECT", ""),
            encryption_key=os.getenv("WEB_PUSH_SUBSCRIPTION_ENCRYPTION_KEY", ""),
            enrollment_enabled=os.getenv("PUSH_ENROLLMENT_ENABLED", "false").lower() == "true",
            release_enabled=os.getenv("PUSH_RELEASE_ENABLED", "false").lower() == "true",
            batch_size=max(1, min(500, int(os.getenv("PUSH_BATCH_SIZE", "50")))),
            request_timeout_seconds=max(1, min(30, float(os.getenv("PUSH_REQUEST_TIMEOUT_SECONDS", "10")))),
            default_ttl_seconds=max(60, min(86_400, int(os.getenv("PUSH_DEFAULT_TTL_SECONDS", "14400")))),
            general_ttl_seconds=max(300, min(86_400, int(os.getenv("PUSH_GENERAL_TTL_SECONDS", "14400")))),
            max_attempts=max(1, min(10, int(os.getenv("PUSH_MAX_ATTEMPTS", "4")))),
            retention_days=max(7, int(os.getenv("PUSH_RETENTION_DAYS", "90"))),
        )

    @property
    def configured(self) -> bool:
        if not (self.vapid_private_key and self.vapid_public_key and self.vapid_subject and self.encryption_key): return False
        if not (self.vapid_subject.startswith("mailto:") or self.vapid_subject.startswith("https://")): return False
        try:
            Fernet(self.encryption_key.encode())
            value=self.vapid_public_key; raw=base64.urlsafe_b64decode(value+"="*((4-len(value)%4)%4))
            return len(raw)==65 and raw[0]==4
        except Exception:
            return False

    @property
    def active(self) -> bool:
        return self.release_enabled and self.configured

    @property
    def can_enroll(self) -> bool:
        return self.configured and (self.enrollment_enabled or self.release_enabled)
