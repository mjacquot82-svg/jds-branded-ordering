from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import String, func, select
from sqlalchemy.orm import Session

from app.api.v1.catalog import get_catalog_session, ladels_compatibility_tenant
from app.api.v1.owner_auth import csrf_principal, current_principal
from app.api.v1.tenant_context import authenticated_owner_tenant
from app.jds_auth.models import JdsApplication, JdsUser, Membership, Organization, Role
from app.clover.models import CloverInstallation
from app.jds_auth.service import AuthPrincipal
from app.platform.design import DEFAULT_CONFIG, DesignService, DesignValidationError
from app.platform.models import BillingPlan, BusinessProfile, DesignVersion, DesignWorkspace, MediaAsset, OnboardingState, OperationalAuditEvent, OrganizationSubscription, PlatformGrant, StorefrontHostname
from app.tenancy.context import TenantContext

router = APIRouter(tags=["platform"])
class Strict(BaseModel): model_config = ConfigDict(extra="forbid")
class DraftInput(Strict): revision: int = Field(ge=1); config: dict
class RevertInput(Strict): version_id: UUID
class OnboardingInput(Strict): revision: int = Field(ge=1); current_step: str = Field(max_length=50); completed_steps: list[str] = Field(max_length=20)
class MediaInput(Strict):
    storage_key: str = Field(min_length=1, max_length=500, pattern=r"^[a-zA-Z0-9/_-]+\.[a-zA-Z0-9]+$")
    media_type: str = Field(pattern=r"^image/(png|jpeg|webp)$")
    alt_text: str = Field(default="", max_length=300)
    byte_size: int = Field(gt=0, le=10_000_000)
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
class BusinessInput(Strict):
    display_name: str = Field(min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, max_length=240)
    contact_email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=30)
    timezone: str = Field(min_length=1, max_length=100)
    currency: str = Field(default="CAD", pattern=r"^[A-Z]{3}$")
    pickup_instructions: str = Field(default="", max_length=1000)
    fulfillment_wording: str = Field(default="Pickup", min_length=1, max_length=120)
class ProvisionOrganizationInput(Strict):
    slug: str = Field(min_length=3,max_length=63,pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    display_name: str = Field(min_length=1,max_length=200)
    owner_email: str = Field(min_length=3,max_length=320)

def design_payload(workspace: DesignWorkspace) -> dict:
    return {"revision": workspace.revision, "config": workspace.draft_config, "published_version_id": str(workspace.published_version_id) if workspace.published_version_id else None}

@router.get("/storefront/bootstrap")
def storefront_bootstrap(response: Response, tenant: TenantContext = Depends(ladels_compatibility_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    workspace = session.get(DesignWorkspace, tenant.organization_id)
    version = session.get(DesignVersion, workspace.published_version_id) if workspace and workspace.published_version_id else None
    profile = session.get(BusinessProfile, tenant.organization_id)
    host = session.scalar(select(StorefrontHostname).where(StorefrontHostname.organization_id == tenant.organization_id, StorefrontHostname.is_canonical.is_(True), StorefrontHostname.status == "verified"))
    response.headers["Cache-Control"] = f"public, max-age=60" if version else "no-store"
    response.headers["Vary"] = "Host"
    return {"tenant": {"id": str(tenant.organization_id), "slug": tenant.organization_slug, "canonicalHost": host.hostname if host else None}, "business": {"displayName": profile.display_name if profile else tenant.organization_slug, "timezone": profile.timezone if profile else "America/Toronto", "currency": profile.currency if profile else "CAD", "pickupInstructions": profile.pickup_instructions if profile else ""}, "design": version.config if version else DEFAULT_CONFIG, "designVersion": version.version_number if version else 0}

@router.get("/storefront/manifest.webmanifest")
def manifest(tenant: TenantContext = Depends(ladels_compatibility_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    workspace = session.get(DesignWorkspace, tenant.organization_id); version = session.get(DesignVersion, workspace.published_version_id) if workspace and workspace.published_version_id else None
    config = version.config if version else DEFAULT_CONFIG; pwa = config.get("pwa", {})
    return {"id": f"/{tenant.organization_slug}", "name": config.get("displayName", "Order ahead"), "short_name": pwa.get("shortName", "Order"), "start_url": "/", "scope": "/", "display": "standalone", "theme_color": pwa.get("themeColor", "#6f7d5f"), "background_color": pwa.get("backgroundColor", "#f7f0e6")}

@router.get("/owner/design")
def get_design(response: Response, tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    response.headers["Cache-Control"] = "no-store"; return design_payload(DesignService(session, tenant).workspace())

@router.get("/owner/design/versions")
def design_versions(response: Response, tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> list[dict]:
    response.headers["Cache-Control"] = "no-store"
    workspace = DesignService(session, tenant).workspace()
    rows = session.scalars(select(DesignVersion).where(DesignVersion.organization_id == tenant.organization_id).order_by(DesignVersion.version_number.desc())).all()
    return [{"id":str(item.id),"version":item.version_number,"publishedAt":item.created_at,"isCurrent":item.id == workspace.published_version_id,"sourceVersionId":str(item.source_version_id) if item.source_version_id else None} for item in rows]

@router.put("/owner/design")
def save_design(payload: DraftInput, principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    try: return design_payload(DesignService(session, tenant).save(payload.config, payload.revision, principal.user_id))
    except DesignValidationError as error: raise HTTPException(409, detail={"code":"design_invalid","message":str(error)}) from error

@router.post("/owner/design/publish")
def publish_design(principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    try:
        item = DesignService(session, tenant).publish(principal.user_id); return {"id":str(item.id),"version":item.version_number}
    except DesignValidationError as error: raise HTTPException(422, detail={"code":"design_invalid","message":str(error)}) from error

@router.post("/owner/design/revert")
def revert_design(payload: RevertInput, principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    try:
        item = DesignService(session, tenant).revert(payload.version_id, principal.user_id); return {"id":str(item.id),"version":item.version_number}
    except DesignValidationError as error: raise HTTPException(404, detail={"code":"version_not_found","message":str(error)}) from error

@router.get("/owner/businesses")
def businesses(principal: AuthPrincipal = Depends(current_principal), session: Session = Depends(get_catalog_session)) -> list[dict]:
    rows = session.execute(select(Membership, Organization, Role).join(Organization, Organization.id == Membership.organization_id).join(Role, Role.id == Membership.role_id).where(Membership.user_id == principal.user_id, Membership.status == "active", Organization.is_active.is_(True)).order_by(Organization.name)).all()
    return [{"membershipId":str(m.id),"organizationId":str(o.id),"slug":o.slug,"name":o.name,"role":r.key,"selected":o.id == principal.organization_id} for m,o,r in rows]

@router.get("/owner/onboarding")
def onboarding(tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    item = session.get(OnboardingState, tenant.organization_id) or OnboardingState(organization_id=tenant.organization_id)
    if item not in session: session.add(item); session.commit()
    return {"state":item.state,"currentStep":item.current_step,"completedSteps":item.completed_steps,"publicReady":item.public_ready,"revision":item.revision}

def business_payload(item: BusinessProfile) -> dict:
    return {"display_name":item.display_name,"legal_name":item.legal_name,"contact_email":item.contact_email,"phone":item.phone,"timezone":item.timezone,"currency":item.currency,"pickup_instructions":item.pickup_instructions,"fulfillment_wording":item.fulfillment_wording}

@router.get("/owner/business-profile")
def owner_business_profile(tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    item = session.get(BusinessProfile, tenant.organization_id)
    if item is None:
        organization=session.get(Organization,tenant.organization_id)
        item=BusinessProfile(organization_id=tenant.organization_id,display_name=organization.name if organization else tenant.organization_slug)
        session.add(item);session.commit()
    return business_payload(item)

@router.put("/owner/business-profile")
def save_business_profile(payload: BusinessInput, principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try: ZoneInfo(payload.timezone)
    except ZoneInfoNotFoundError as error: raise HTTPException(422, detail="Choose a valid timezone.") from error
    item = session.get(BusinessProfile, tenant.organization_id)
    if item is None: item = BusinessProfile(organization_id=tenant.organization_id, display_name=payload.display_name); session.add(item)
    for key, value in payload.model_dump().items(): setattr(item, key, value.strip() if isinstance(value, str) else value)
    session.add(OperationalAuditEvent(organization_id=tenant.organization_id,scope="tenant",actor_user_id=principal.user_id,action="business_profile.updated",target_type="organization",target_id=str(tenant.organization_id),outcome="success"));session.commit()
    return business_payload(item)

@router.put("/owner/onboarding")
def save_onboarding(payload: OnboardingInput, _: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    item = session.scalar(select(OnboardingState).where(OnboardingState.organization_id == tenant.organization_id).with_for_update())
    if item is None: item=OnboardingState(organization_id=tenant.organization_id); session.add(item)
    if item.revision != payload.revision:
        requested_state="complete" if {"business","storefront","hours","fulfillment","design","catalog","clover"}<=set(payload.completed_steps) else "in_progress"
        if item.completed_steps==payload.completed_steps and item.current_step==payload.current_step and item.state==requested_state:
            return {"state":item.state,"currentStep":item.current_step,"completedSteps":item.completed_steps,"publicReady":item.public_ready,"revision":item.revision}
        raise HTTPException(409, detail="Onboarding changed in another session.")
    allowed={"business","storefront","hours","fulfillment","design","catalog","clover"}
    if not set(payload.completed_steps)<=allowed or payload.current_step not in allowed|{"complete"}: raise HTTPException(422,detail="Invalid onboarding checkpoint.")
    item.completed_steps=payload.completed_steps; item.current_step=payload.current_step; item.revision+=1
    # Readiness remains server-derived: completion alone cannot expose commerce.
    item.state="complete" if allowed<=set(payload.completed_steps) else "in_progress"; item.public_ready=False
    session.commit(); return {"state":item.state,"currentStep":item.current_step,"completedSteps":item.completed_steps,"publicReady":item.public_ready,"revision":item.revision}

@router.get("/owner/entitlements")
def entitlements(tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    row=session.execute(select(OrganizationSubscription,BillingPlan).join(BillingPlan,BillingPlan.key==OrganizationSubscription.plan_key).where(OrganizationSubscription.organization_id==tenant.organization_id)).first()
    if not row: return {"state":"none","plan":None,"features":{}}
    subscription,plan=row; enabled=subscription.state in {"trialing","active","grace"}
    return {"state":subscription.state,"plan":plan.key,"features":plan.entitlements if enabled else {}}

@router.get("/owner/media")
def list_media(tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> list[dict]:
    rows=session.scalars(select(MediaAsset).where(MediaAsset.organization_id==tenant.organization_id,MediaAsset.status=="active").order_by(MediaAsset.created_at.desc())).all()
    return [{"id":str(item.id),"storageKey":item.storage_key,"mediaType":item.media_type,"altText":item.alt_text,"byteSize":item.byte_size} for item in rows]

@router.post("/owner/media", status_code=201)
def create_media(payload: MediaInput, principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    # V1 local adapter records a validated logical asset. Blob writes remain an adapter concern.
    item=MediaAsset(organization_id=tenant.organization_id,created_by_user_id=principal.user_id,**payload.model_dump())
    session.add(item);session.flush();session.add(OperationalAuditEvent(organization_id=tenant.organization_id,scope="tenant",actor_user_id=principal.user_id,action="media.created",target_type="media_asset",target_id=str(item.id),outcome="success"));session.commit()
    return {"id":str(item.id)}

@router.delete("/owner/media/{media_id}", status_code=204)
def archive_media(media_id: UUID, principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> Response:
    item=session.scalar(select(MediaAsset).where(MediaAsset.id==media_id,MediaAsset.organization_id==tenant.organization_id))
    if item is None: raise HTTPException(404,detail="Media not found.")
    referenced=session.scalar(select(DesignVersion.id).where(DesignVersion.organization_id==tenant.organization_id,DesignVersion.config.cast(String).contains(str(media_id))).limit(1))
    if referenced is not None: raise HTTPException(409,detail="This image is used by a published design.")
    item.status="archived";session.add(OperationalAuditEvent(organization_id=tenant.organization_id,scope="tenant",actor_user_id=principal.user_id,action="media.archived",target_type="media_asset",target_id=str(item.id),outcome="success"));session.commit();return Response(status_code=204)

@router.get("/platform/admin/organizations")
def platform_organizations(principal: AuthPrincipal = Depends(current_principal), session: Session = Depends(get_catalog_session)) -> list[dict]:
    grant=session.scalar(select(PlatformGrant.id).where(PlatformGrant.user_id==principal.user_id,PlatformGrant.capability=="platform.organizations.read",PlatformGrant.is_active.is_(True)))
    if grant is None: raise HTTPException(403,detail={"code":"platform_access_required","message":"Platform access is not authorized."})
    rows=session.execute(select(Organization,OnboardingState,DesignWorkspace,OrganizationSubscription).outerjoin(OnboardingState,OnboardingState.organization_id==Organization.id).outerjoin(DesignWorkspace,DesignWorkspace.organization_id==Organization.id).outerjoin(OrganizationSubscription,OrganizationSubscription.organization_id==Organization.id).order_by(Organization.name)).all()
    session.add(OperationalAuditEvent(scope="platform",actor_user_id=principal.user_id,action="platform.organizations_viewed",outcome="success",metadata_json={"count":len(rows)}));session.commit()
    result=[]
    for org,onboarding,design,subscription in rows:
        hostname=session.scalar(select(StorefrontHostname.hostname).where(StorefrontHostname.organization_id==org.id,StorefrontHostname.is_canonical.is_(True),StorefrontHostname.status=="verified"))
        owners=session.scalar(select(func.count()).select_from(Membership).join(Role,Role.id==Membership.role_id).where(Membership.organization_id==org.id,Membership.status=="active",Role.key=="owner"))
        clover=session.scalars(select(CloverInstallation.connection_state).where(CloverInstallation.organization_id==org.id)).all()
        result.append({"id":str(org.id),"name":org.name,"slug":org.slug,"status":org.lifecycle_status,"onboarding":onboarding.state if onboarding else "not_started","publicReady":bool(onboarding and onboarding.public_ready),"canonicalHost":hostname,"ownerMemberships":owners or 0,"cloverHealth":sorted(set(clover)) or ["not_connected"],"publishedVersionId":str(design.published_version_id) if design and design.published_version_id else None,"subscription":subscription.state if subscription else "none"})
    return result

@router.post("/platform/admin/organizations", status_code=201)
def provision_organization(payload: ProvisionOrganizationInput, principal: AuthPrincipal = Depends(csrf_principal), session: Session = Depends(get_catalog_session)) -> dict:
    grant=session.scalar(select(PlatformGrant.id).where(PlatformGrant.user_id==principal.user_id,PlatformGrant.capability=="platform.organizations.write",PlatformGrant.is_active.is_(True)))
    if grant is None: raise HTTPException(403,detail={"code":"platform_access_required","message":"Platform provisioning is not authorized."})
    existing=session.scalar(select(Organization).where(Organization.slug==payload.slug))
    if existing is not None: raise HTTPException(409,detail={"code":"slug_unavailable","message":"That storefront name is unavailable."})
    owner=session.scalar(select(JdsUser).where(JdsUser.primary_email==payload.owner_email.strip().lower(),JdsUser.status=="active"))
    application=session.scalar(select(JdsApplication).where(JdsApplication.key=="jds-commerce",JdsApplication.is_active.is_(True)))
    role=session.scalar(select(Role).where(Role.application_id==application.id,Role.key=="owner")) if application else None
    if owner is None or application is None or role is None: raise HTTPException(422,detail={"code":"owner_unavailable","message":"Provision an active owner identity before creating the business."})
    item=Organization(slug=payload.slug,name=payload.display_name.strip(),lifecycle_status="onboarding",is_active=True);session.add(item);session.flush()
    session.add_all([
        Membership(organization_id=item.id,application_id=application.id,user_id=owner.id,role_id=role.id,status="active",joined_at=datetime.now(timezone.utc)),
        BusinessProfile(organization_id=item.id,display_name=payload.display_name.strip()),
        StorefrontHostname(organization_id=item.id,hostname=f"{payload.slug}.jdsstudio.ca",is_canonical=True,status="pending"),
        OnboardingState(organization_id=item.id,state="in_progress",current_step="business",public_ready=False),
        OrganizationSubscription(organization_id=item.id,plan_key="core",state="trialing",provider="local"),
        OperationalAuditEvent(organization_id=item.id,scope="platform",actor_user_id=principal.user_id,action="platform.organization_provisioned",target_type="organization",target_id=str(item.id),outcome="success"),
    ]);session.commit()
    return {"id":str(item.id),"slug":item.slug,"hostname":f"{item.slug}.jdsstudio.ca","status":item.lifecycle_status,"publicReady":False}
