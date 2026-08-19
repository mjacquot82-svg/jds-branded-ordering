from typing import Protocol
from uuid import UUID

from app.jds_auth.models import SecurityAuditEvent


class SecurityAuditWriter(Protocol):
    def record(
        self,
        action: str,
        outcome: str,
        *,
        organization_id: UUID | None = None,
        actor_user_id: UUID | None = None,
        session_id: UUID | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        details: str | None = None,
    ) -> None: ...


class DatabaseSecurityAuditWriter:
    def __init__(self, session: object) -> None:
        self._session = session

    def record(self, action: str, outcome: str, **values: object) -> None:
        self._session.add(SecurityAuditEvent(action=action, outcome=outcome, **values))
