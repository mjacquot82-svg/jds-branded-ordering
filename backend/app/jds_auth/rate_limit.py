from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.jds_auth.models import AuthRateLimitBucket
from app.jds_auth.security import hash_secret


class RateLimitExceeded(RuntimeError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Authentication request limit exceeded.")
        self.retry_after = max(1, retry_after)


@dataclass(frozen=True)
class RateLimit:
    namespace: str
    maximum: int
    window_seconds: int


class DatabaseAuthRateLimiter:
    """Atomic fixed-window limits shared by every API instance."""

    def __init__(self, session: Session, pepper: str) -> None:
        self._session = session
        self._pepper = pepper

    def check(self, policy: RateLimit, identifier: str, *, now: datetime) -> None:
        normalized = identifier.strip().lower() or "unknown"
        key_hash = hash_secret(f"{policy.namespace}:{normalized}", self._pepper)
        lock_key = int.from_bytes(bytes.fromhex(key_hash[:16]), "big", signed=True)
        with self._session.begin():
            self._session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": lock_key},
            )
            bucket = self._session.get(AuthRateLimitBucket, key_hash)
            if bucket is None or bucket.expires_at <= now:
                bucket = AuthRateLimitBucket(
                    key_hash=key_hash,
                    lock_key=lock_key,
                    window_started_at=now,
                    expires_at=now + timedelta(seconds=policy.window_seconds),
                    request_count=1,
                )
                self._session.merge(bucket)
                return
            if bucket.request_count >= policy.maximum:
                raise RateLimitExceeded(int((bucket.expires_at - now).total_seconds()) + 1)
            bucket.request_count += 1


LOGIN_IP = RateLimit("login-ip", 30, 15 * 60)
LOGIN_ACCOUNT = RateLimit("login-account", 10, 15 * 60)
RESET_REQUEST_IP = RateLimit("reset-request-ip", 10, 60 * 60)
RESET_REQUEST_ACCOUNT = RateLimit("reset-request-account", 3, 60 * 60)
RESET_COMPLETE_IP = RateLimit("reset-complete-ip", 10, 60 * 60)
RESET_COMPLETE_TOKEN = RateLimit("reset-complete-token", 5, 60 * 60)
VERIFICATION_RESEND_IP = RateLimit("verification-resend-ip", 10, 60 * 60)
VERIFICATION_RESEND_ACCOUNT = RateLimit("verification-resend-account", 3, 60 * 60)
INVITE_ACCEPT_IP = RateLimit("invite-accept-ip", 20, 60 * 60)
INVITE_ACCEPT_INVITATION = RateLimit("invite-accept-invitation", 5, 60 * 60)
INVITE_CREATE_ACTOR = RateLimit("invite-create-actor", 20, 60 * 60)
INVITE_CREATE_ORGANIZATION = RateLimit("invite-create-organization", 50, 24 * 60 * 60)
STAFF_LOGIN_IP = RateLimit("staff-login-ip", 20, 15 * 60)
STAFF_LOGIN_ACCOUNT = RateLimit("staff-login-account", 5, 15 * 60)
PUSH_SUBSCRIBE_ACCOUNT = RateLimit("push-subscribe-account", 20, 60 * 60)
PUSH_ANNOUNCE_ACTOR = RateLimit("push-announce-actor", 12, 60 * 60)
