from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.availability.models import ProductAvailability
from app.availability.repository import AvailabilityRepository
from app.tenancy.resolver import resolve_internal_ladels_compatibility_context
from app.availability.service import AvailabilityConfigurationError, SellabilityService
from app.catalog.models import Category, Product
from app.push.config import PushSettings
from app.push.models import CustomerNotificationPreference, PushAnnouncement, PushDeliveryAttempt, WebPushSubscription

CAFE_TZ = ZoneInfo("America/Toronto")

def lunch_special_message(name: str, price_cents: int) -> str:
    price = f"${price_cents / 100:,.2f}"
    return f"Today’s Lunch Special is {name} for {price}. Order online while it’s available!"


class CommunicationCenterService:
    """Build the operator-facing customer-announcement snapshot.

    Transactional order-email/SMS delivery was never installed. Authentication
    email remains owned by Supabase Auth and intentionally does not participate in
    this operational health response.
    """

    def __init__(self, session: Session, settings: PushSettings | None = None) -> None:
        self._session = session
        self._settings = settings or PushSettings()

    def snapshot(self, *, organization_id: UUID) -> dict[str, object]:
        cafe_day = datetime.now(CAFE_TZ).date()
        today_lunch = self._session.scalar(
            select(PushAnnouncement)
            .where(
                PushAnnouncement.organization_id == organization_id,
                PushAnnouncement.kind == "lunch_special",
                PushAnnouncement.cafe_day == cafe_day,
                PushAnnouncement.is_override.is_(False),
            )
            .limit(1)
        )
        lunch_special = self._session.scalar(
            select(Product)
            .where(
                Product.is_lunch_special.is_(True),
                Product.archived_at.is_(None),
            )
            .order_by(Product.id)
            .limit(1)
        )
        return {
            "generated_at": datetime.now(timezone.utc),
            "summary": {
                "actionable_warnings": 0,
                "lunch_special_attempting_today": today_lunch is not None and today_lunch.status in ("queued", "attempting"),
                "lunch_special_queued_today": today_lunch is not None,
                "push_release_enabled": self._settings.active,
            },
            "lunch_special": (
                self._lunch_special(lunch_special, at=datetime.now(timezone.utc))
                if lunch_special is not None
                else None
            ),
            "activity": [self._activity(item) for item in self._session.scalars(select(PushAnnouncement).order_by(PushAnnouncement.created_at.desc()).limit(50))],
            "health": [
                {
                    "key": "push",
                    "name": "Push notifications",
                    "status": "ready" if self._settings.active else "not_connected",
                    "detail": (
                        "Web Push is release-enabled and uses the durable delivery queue."
                        if self._settings.active else "Customer push delivery is not connected yet. Announcement drafts cannot be sent."
                    ),
                    "actionable": False,
                }
            ],
        }

    def _activity(self, item: PushAnnouncement) -> dict[str, object]:
        queued = self._session.scalar(
            select(func.count())
            .select_from(PushDeliveryAttempt)
            .where(
                PushDeliveryAttempt.announcement_id == item.id,
                PushDeliveryAttempt.status.in_(("queued", "retry", "claimed")),
            )
        ) or 0
        return {"id":str(item.id),"kind":item.kind,"title":item.title,"message":item.frozen_message,"status":item.status,
                "occurred_at":item.created_at,"sent_by":item.actor_name_snapshot,"queued":queued,
                "attempted":item.attempted_count,"accepted":item.accepted_count,"failed":item.failed_count,"expired":item.expired_count,"suppressed":item.suppressed_count,"clicked":item.clicked_count}

    def create_lunch_special(self, *, organization_id: UUID, actor_user_id: UUID, actor_name: str, idempotency_key: str, override: bool) -> PushAnnouncement:
        if not self._settings.active: raise ValueError("push_not_released")
        prior=self._session.scalar(select(PushAnnouncement).where(PushAnnouncement.organization_id==organization_id,PushAnnouncement.idempotency_key==idempotency_key))
        if prior:
            if prior.kind != "lunch_special" or prior.is_override != override:
                raise ValueError("idempotency_conflict")
            return prior
        product = self._session.scalar(select(Product).where(Product.is_lunch_special.is_(True), Product.archived_at.is_(None)).limit(1))
        if product is None: raise ValueError("lunch_special_missing")
        details=self._lunch_special(product, at=datetime.now(timezone.utc))
        if not details["orderable"]: raise ValueError("lunch_special_not_orderable")
        cafe_day=datetime.now(CAFE_TZ).date()
        existing=self._session.scalar(select(PushAnnouncement).where(PushAnnouncement.organization_id==organization_id,PushAnnouncement.kind=="lunch_special",PushAnnouncement.cafe_day==cafe_day,PushAnnouncement.is_override.is_(False)))
        if existing and not override: raise ValueError("duplicate_lunch_special")
        announcement=PushAnnouncement(organization_id=organization_id,kind="lunch_special",title="Today’s Lunch Special",frozen_message=lunch_special_message(product.name,product.base_price_cents),target_route=f"/menu?product={quote(product.slug, safe='')}",source_product_id=product.id,product_name_snapshot=product.name,price_cents_snapshot=product.base_price_cents,actor_user_id=actor_user_id,actor_name_snapshot=actor_name,status="queued",idempotency_key=idempotency_key,cafe_day=cafe_day,is_override=override)
        return self._queue(announcement, require_lunch_preference=True)

    def create_general(self, *, organization_id: UUID, actor_user_id: UUID, actor_name: str, idempotency_key: str, title: str, body: str, route: str) -> PushAnnouncement:
        if not self._settings.active: raise ValueError("push_not_released")
        prior=self._session.scalar(select(PushAnnouncement).where(PushAnnouncement.organization_id==organization_id,PushAnnouncement.idempotency_key==idempotency_key))
        if prior:
            if prior.kind != "general" or (prior.title, prior.frozen_message, prior.target_route) != (title, body, route):
                raise ValueError("idempotency_conflict")
            return prior
        now = datetime.now(timezone.utc)
        announcement=PushAnnouncement(organization_id=organization_id,kind="general",title=title,frozen_message=body,target_route=route,actor_user_id=actor_user_id,actor_name_snapshot=actor_name,status="queued",idempotency_key=idempotency_key,expires_at=now + timedelta(seconds=self._settings.general_ttl_seconds))
        # The first release has one explicit customer opt-in: café notifications.
        # The persisted kind remains lunch_special to avoid an unnecessary migration.
        # General announcements target only that opted-in cohort,
        # never every stored browser capability indiscriminately.
        return self._queue(announcement, require_lunch_preference=True)

    def _queue(self, announcement: PushAnnouncement, *, require_lunch_preference: bool) -> PushAnnouncement:
        try:
            self._session.add(announcement); self._session.flush()
            query=select(WebPushSubscription).where(WebPushSubscription.revoked_at.is_(None),WebPushSubscription.expired_at.is_(None))
            if require_lunch_preference:
                query=query.join(CustomerNotificationPreference,CustomerNotificationPreference.customer_user_id==WebPushSubscription.customer_user_id).where(CustomerNotificationPreference.notification_kind=="lunch_special",CustomerNotificationPreference.enabled.is_(True))
            eligible=self._session.scalars(query).all()
            self._session.add_all([PushDeliveryAttempt(announcement_id=announcement.id,subscription_id=item.id) for item in eligible])
            if not eligible: announcement.status="completed"; announcement.completed_at=datetime.now(timezone.utc)
            self._session.commit(); return announcement
        except IntegrityError:
            self._session.rollback()
            prior=self._session.scalar(select(PushAnnouncement).where(PushAnnouncement.organization_id==announcement.organization_id,PushAnnouncement.idempotency_key==announcement.idempotency_key))
            if prior is not None:
                same = prior.kind == announcement.kind and (
                    prior.kind == "lunch_special"
                    or (prior.title, prior.frozen_message, prior.target_route)
                    == (announcement.title, announcement.frozen_message, announcement.target_route)
                )
                if not same:
                    raise ValueError("idempotency_conflict")
                return prior
            if announcement.kind == "lunch_special" and not announcement.is_override:
                raise ValueError("duplicate_lunch_special")
            raise

    def _lunch_special(self, product: Product, *, at: datetime | None = None) -> dict[str, object]:
        category_published, available = self._session.execute(
            select(
                Category.is_published,
                func.coalesce(ProductAvailability.default_available, True),
            )
            .select_from(Product)
            .join(Category, Category.id == product.category_id)
            .outerjoin(
                ProductAvailability,
                ProductAvailability.product_id == product.id,
            )
            .where(Product.id == product.id)
        ).one()
        customer_visible = bool(product.is_published and category_published)
        orderable = bool(customer_visible and available)
        if at is not None:
            try:
                orderable = SellabilityService(
                    AvailabilityRepository(
                        self._session,
                        resolve_internal_ladels_compatibility_context(self._session),
                    )
                ).evaluate(product.id, at=at).is_sellable
            except AvailabilityConfigurationError:
                orderable = False
        warnings: list[str] = []
        if not customer_visible:
            warnings.append("This Lunch Special is hidden from the customer menu.")
        if not available:
            warnings.append("This Lunch Special is unavailable for online ordering.")
        return {
            "id": str(product.id),
            "name": product.name,
            "description": product.description or "",
            "price_cents": product.base_price_cents,
            "image": product.image_reference or "",
            "customer_visible": customer_visible,
            "orderable": orderable,
            "warnings": warnings,
        }
