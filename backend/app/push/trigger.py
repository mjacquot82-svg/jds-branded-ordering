import logging

from app.push.config import PushSettings

logger = logging.getLogger(__name__)


def drain_push_outbox(session_factory, settings: PushSettings) -> int:
    """Best-effort trigger; PostgreSQL remains authoritative if this process dies."""
    if session_factory is None or not settings.active:
        return 0
    try:
        from app.push.dispatcher import PushDispatcher

        return PushDispatcher(session_factory, settings).run_batch()
    except Exception:
        # Never expose subscription capabilities or provider details in logs.
        logger.exception("Bounded Web Push outbox drain failed.")
        return 0
