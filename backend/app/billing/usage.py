"""Per-shop monthly usage counters. Fail-safe: counting never breaks a request."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

METRICS = ("emails_sent", "texts_sent")


def period_of(moment: datetime | None = None) -> str:
    return (moment or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m")


def record_usage(session: Session, organization_id: UUID | None, metric: str, amount: int = 1) -> None:
    """Upsert in its own short transaction so the caller's session/transaction is untouched."""
    if organization_id is None:
        return
    try:
        with session.get_bind().begin() as connection:
            connection.execute(text(
                "INSERT INTO shop_usage_counters (organization_id, period, metric, count) "
                "VALUES (:org, :period, :metric, :amount) "
                "ON CONFLICT (organization_id, period, metric) "
                "DO UPDATE SET count = shop_usage_counters.count + :amount, updated_at = now()"
            ), {"org": organization_id, "period": period_of(), "metric": metric, "amount": amount})
    except Exception as error:  # noqa: BLE001
        logger.warning("usage counter failed org=%s metric=%s error=%s", organization_id, metric, type(error).__name__)
