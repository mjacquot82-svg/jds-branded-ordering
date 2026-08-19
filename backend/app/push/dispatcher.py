import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, update

from app.push.config import PushSettings
from app.push.models import CustomerNotificationPreference, PushAnnouncement, PushDeliveryAttempt, WebPushSubscription
from app.push.provider import PushProvider, PyWebPushProvider
from app.push.security import SubscriptionProtector

CAFE_TIMEZONE = ZoneInfo("America/Toronto")
CLAIM_TIMEOUT = timedelta(minutes=5)


class PushDispatcher:
    """Claim and deliver a bounded durable-outbox batch.

    Claiming and result recording use short transactions. The remote Web Push
    request always occurs after the claim transaction has committed and its
    session has closed.
    """

    def __init__(self, session_factory, settings: PushSettings, provider: PushProvider | None = None):
        self.sessions = session_factory
        self.settings = settings
        self.provider = provider or PyWebPushProvider(settings)
        self.crypt = SubscriptionProtector(settings.encryption_key)

    def run_batch(self) -> int:
        now = datetime.now(timezone.utc)
        with self.sessions() as db:
            db.execute(
                update(PushDeliveryAttempt)
                .where(
                    PushDeliveryAttempt.status == "claimed",
                    PushDeliveryAttempt.claimed_at < now - CLAIM_TIMEOUT,
                )
                .values(
                    status="retry",
                    claimed_at=None,
                    next_attempt_at=now,
                    error_code="claim_recovered",
                )
            )
            db.execute(
                delete(PushAnnouncement).where(
                    PushAnnouncement.completed_at
                    < now - timedelta(days=self.settings.retention_days)
                )
            )
            jobs = db.scalars(
                select(PushDeliveryAttempt)
                .where(
                    PushDeliveryAttempt.status.in_(("queued", "retry")),
                    PushDeliveryAttempt.next_attempt_at <= now,
                )
                .order_by(PushDeliveryAttempt.next_attempt_at, PushDeliveryAttempt.id)
                .with_for_update(skip_locked=True)
                .limit(self.settings.batch_size)
            ).all()
            ids = []
            for job in jobs:
                job.status = "claimed"
                job.claimed_at = now
                ids.append(job.id)
            db.commit()

        for job_id in ids:
            self._deliver(job_id)
        return len(ids)

    def _deliver(self, job_id) -> None:
        with self.sessions() as db:
            job = db.get(PushDeliveryAttempt, job_id)
            if job is None:
                return
            announcement = db.get(PushAnnouncement, job.announcement_id)
            subscription = db.get(WebPushSubscription, job.subscription_id)
            if announcement is None or subscription is None:
                return
            if job.organization_id != announcement.organization_id or subscription.organization_id != announcement.organization_id:
                self._finish_without_send(db, job, "suppressed", "tenant_mismatch")
                return
            if subscription.revoked_at or subscription.expired_at:
                self._finish_without_send(db, job, "suppressed", "subscription_inactive")
                return
            preference_enabled = db.scalar(
                select(CustomerNotificationPreference.enabled).where(
                    CustomerNotificationPreference.organization_id == announcement.organization_id,
                    CustomerNotificationPreference.customer_user_id == subscription.customer_user_id,
                    CustomerNotificationPreference.notification_kind == "lunch_special",
                )
            )
            if preference_enabled is not True:
                self._finish_without_send(db, job, "suppressed", "account_opted_out")
                return
            if self._announcement_is_stale(announcement):
                self._finish_without_send(db, job, "expired", "announcement_expired")
                return
            try:
                subscription_info = {
                    "endpoint": self.crypt.decrypt(subscription.endpoint_ciphertext),
                    "keys": {
                        "p256dh": self.crypt.decrypt(subscription.p256dh_ciphertext),
                        "auth": self.crypt.decrypt(subscription.auth_ciphertext),
                    },
                }
            except ValueError:
                self._finish_without_send(db, job, "failed", "subscription_decryption_failed")
                return
            payload = {
                "version": 1,
                "announcementId": str(announcement.id),
                "title": announcement.title,
                "body": announcement.frozen_message,
                "destination": announcement.target_route,
                "kind": announcement.kind,
            }
            ttl = self._ttl(announcement)

        result = self.provider.send(
            subscription_info,
            payload,
            ttl,
            "normal",
            str(announcement.id).replace("-", "")[:32],
        )
        now = datetime.now(timezone.utc)
        with self.sessions() as db:
            job = db.get(PushDeliveryAttempt, job_id)
            if job is None or job.status != "claimed":
                return
            subscription = db.get(WebPushSubscription, job.subscription_id)
            announcement = db.get(PushAnnouncement, job.announcement_id)
            if subscription is None or announcement is None:
                return
            job.attempt_count += 1
            job.last_attempt_at = now
            job.provider_http_status = result.http_status
            job.error_code = result.error_code
            job.claimed_at = None
            if announcement.started_at is None:
                announcement.started_at = now
            if result.accepted:
                job.status = "accepted"
                job.completed_at = now
                subscription.last_success_at = now
                subscription.failure_count = 0
            elif result.expired:
                job.status = "expired"
                job.completed_at = now
                subscription.expired_at = now
                subscription.failed_at = now
                subscription.failure_count += 1
            elif result.permanent or job.attempt_count >= self.settings.max_attempts:
                job.status = "failed"
                job.completed_at = now
                subscription.failed_at = now
                subscription.failure_count += 1
            else:
                job.status = "retry"
                job.next_attempt_at = now + timedelta(
                    seconds=min(3600, 30 * (2**job.attempt_count))
                    + random.randint(0, 20)
                )
            db.flush()
            self._aggregate(db, job.announcement_id)
            db.commit()

    def _finish_without_send(self, db, job, status: str, error_code: str) -> None:
        now = datetime.now(timezone.utc)
        job.status = status
        job.completed_at = now
        job.claimed_at = None
        job.error_code = error_code
        db.flush()
        self._aggregate(db, job.announcement_id)
        db.commit()

    @staticmethod
    def _lunch_special_is_stale(announcement: PushAnnouncement) -> bool:
        if announcement.kind != "lunch_special":
            return False
        local_now = datetime.now(timezone.utc).astimezone(CAFE_TIMEZONE)
        return announcement.cafe_day != local_now.date() or local_now.hour >= 23

    @classmethod
    def _announcement_is_stale(cls, announcement: PushAnnouncement) -> bool:
        if cls._lunch_special_is_stale(announcement):
            return True
        if announcement.kind != "general":
            return False
        # General rows without an expiry predate/invalidate the bounded-lifetime
        # contract and must fail closed instead of being resurrected later.
        return announcement.expires_at is None or announcement.expires_at <= datetime.now(timezone.utc)

    def _ttl(self, announcement: PushAnnouncement) -> int:
        if announcement.kind != "lunch_special":
            remaining = int((announcement.expires_at - datetime.now(timezone.utc)).total_seconds()) if announcement.expires_at else self.settings.general_ttl_seconds
            return max(60, min(self.settings.default_ttl_seconds, remaining))
        local_now = datetime.now(timezone.utc).astimezone(CAFE_TIMEZONE)
        cutoff = local_now.replace(hour=23, minute=0, second=0, microsecond=0)
        return max(
            60,
            min(self.settings.default_ttl_seconds, int((cutoff - local_now).total_seconds())),
        )

    @staticmethod
    def _aggregate(db, announcement_id) -> None:
        announcement = db.get(PushAnnouncement, announcement_id)
        if announcement is None:
            return
        counts = dict(
            db.execute(
                select(PushDeliveryAttempt.status, func.count())
                .where(PushDeliveryAttempt.announcement_id == announcement_id)
                .group_by(PushDeliveryAttempt.status)
            ).all()
        )
        announcement.attempted_count = db.scalar(
            select(func.coalesce(func.sum(PushDeliveryAttempt.attempt_count), 0)).where(
                PushDeliveryAttempt.announcement_id == announcement_id
            )
        )
        announcement.accepted_count = counts.get("accepted", 0)
        announcement.failed_count = counts.get("failed", 0)
        announcement.expired_count = counts.get("expired", 0)
        announcement.suppressed_count = counts.get("suppressed", 0)
        pending = sum(counts.get(key, 0) for key in ("queued", "retry", "claimed"))
        announcement.status = "completed" if not pending else "attempting"
        announcement.completed_at = datetime.now(timezone.utc) if not pending else None
