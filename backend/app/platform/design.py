from __future__ import annotations

import re
from copy import deepcopy
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.platform.models import DesignPublication, DesignVersion, DesignWorkspace, MediaAsset, OperationalAuditEvent
from app.tenancy.context import TenantContext

TEMPLATES = frozenset({"modern", "minimal", "cozy"})
FONTS = frozenset({"modern", "classic", "friendly"})
BUTTONS = frozenset({"rounded", "square", "pill"})
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
DEFAULT_CONFIG = {
    "template": "cozy", "displayName": "Your business", "tagline": "Order ahead",
    "colors": {"primary": "#6f7d5f", "accent": "#b98564", "background": "#f7f0e6", "surface": "#ffffff", "text": "#2f3328"},
    "typography": "classic", "buttonStyle": "rounded", "logoMediaId": None,
    "hero": {"mode": "color", "mediaId": None}, "categoryPresentation": "cards",
    "productCardPresentation": "comfortable", "navigation": "tabs",
    "sections": ["hero", "announcement", "categories", "quickOrder"],
    "pwa": {"shortName": "Order", "themeColor": "#6f7d5f", "backgroundColor": "#f7f0e6"},
}


class DesignValidationError(ValueError):
    pass


def validate_design(session: Session, tenant: TenantContext, candidate: dict) -> dict:
    config = deepcopy(candidate)
    if set(config) - set(DEFAULT_CONFIG):
        raise DesignValidationError("Unsupported design field.")
    if config.get("template") not in TEMPLATES or config.get("typography") not in FONTS or config.get("buttonStyle") not in BUTTONS:
        raise DesignValidationError("Unsupported design choice.")
    if not (1 <= len(str(config.get("displayName", "")).strip()) <= 80) or len(str(config.get("tagline", ""))) > 140:
        raise DesignValidationError("Business name or tagline is invalid.")
    colors = config.get("colors")
    if not isinstance(colors, dict) or set(colors) != set(DEFAULT_CONFIG["colors"]) or not all(isinstance(v, str) and HEX.fullmatch(v) for v in colors.values()):
        raise DesignValidationError("Design colors are invalid.")
    sections = config.get("sections")
    allowed_sections = set(DEFAULT_CONFIG["sections"])
    if not isinstance(sections, list) or len(sections) != len(set(sections)) or not set(sections) <= allowed_sections:
        raise DesignValidationError("Homepage sections are invalid.")
    media_ids = [config.get("logoMediaId"), (config.get("hero") or {}).get("mediaId")]
    for raw_id in filter(None, media_ids):
        try: media_id = UUID(str(raw_id))
        except ValueError as exc: raise DesignValidationError("Media reference is invalid.") from exc
        if session.scalar(select(MediaAsset.id).where(MediaAsset.id == media_id, MediaAsset.organization_id == tenant.organization_id, MediaAsset.status == "active")) is None:
            raise DesignValidationError("Media reference is unavailable.")
    return config


class DesignService:
    def __init__(self, session: Session, tenant: TenantContext):
        self.session, self.tenant = session, tenant

    def workspace(self, *, lock: bool = False) -> DesignWorkspace:
        query = select(DesignWorkspace).where(DesignWorkspace.organization_id == self.tenant.organization_id)
        if lock: query = query.with_for_update()
        item = self.session.scalar(query)
        if item is None:
            item = DesignWorkspace(organization_id=self.tenant.organization_id, draft_config=deepcopy(DEFAULT_CONFIG))
            self.session.add(item); self.session.flush()
        return item

    def save(self, config: dict, expected_revision: int, actor: UUID) -> DesignWorkspace:
        item = self.workspace(lock=True)
        if item.revision != expected_revision: raise DesignValidationError("Draft changed in another session.")
        item.draft_config = validate_design(self.session, self.tenant, config)
        item.revision += 1; item.updated_by_user_id = actor
        self._audit("design.draft_saved", actor, "workspace", str(item.revision)); self.session.commit()
        return item

    def publish(self, actor: UUID) -> DesignVersion:
        item = self.workspace(lock=True)
        config = validate_design(self.session, self.tenant, item.draft_config)
        number = (self.session.scalar(select(func.coalesce(func.max(DesignVersion.version_number), 0)).where(DesignVersion.organization_id == self.tenant.organization_id)) or 0) + 1
        version = DesignVersion(organization_id=self.tenant.organization_id, version_number=number, source_revision=item.revision, config=deepcopy(config), published_by_user_id=actor)
        self.session.add(version); self.session.flush(); item.published_version_id = version.id
        self.session.add(DesignPublication(organization_id=self.tenant.organization_id, version_id=version.id, action="publish", actor_user_id=actor))
        self._audit("design.published", actor, "design_version", str(version.id)); self.session.commit()
        return version

    def revert(self, version_id: UUID, actor: UUID) -> DesignVersion:
        source = self.session.scalar(select(DesignVersion).where(DesignVersion.id == version_id, DesignVersion.organization_id == self.tenant.organization_id))
        if source is None: raise DesignValidationError("Design version not found.")
        item = self.workspace(lock=True); item.draft_config = deepcopy(source.config); item.revision += 1
        number = (self.session.scalar(select(func.max(DesignVersion.version_number)).where(DesignVersion.organization_id == self.tenant.organization_id)) or 0) + 1
        version = DesignVersion(organization_id=self.tenant.organization_id, version_number=number, source_revision=item.revision, config=deepcopy(source.config), published_by_user_id=actor, source_version_id=source.id)
        self.session.add(version); self.session.flush(); item.published_version_id = version.id
        self.session.add(DesignPublication(organization_id=self.tenant.organization_id, version_id=version.id, action="revert", actor_user_id=actor))
        self._audit("design.reverted", actor, "design_version", str(source.id)); self.session.commit()
        return version

    def _audit(self, action: str, actor: UUID, target_type: str, target_id: str) -> None:
        self.session.add(OperationalAuditEvent(organization_id=self.tenant.organization_id, scope="tenant", actor_user_id=actor, action=action, target_type=target_type, target_id=target_id, outcome="success"))
