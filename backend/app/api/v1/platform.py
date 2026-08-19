from datetime import datetime, timezone
from html import escape
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.catalog import get_catalog_session, ladels_compatibility_tenant
from app.api.v1.owner_auth import csrf_principal, current_principal
from app.api.v1.tenant_context import authenticated_owner_tenant
from app.jds_auth.models import JdsApplication, JdsUser, Membership, Organization, Role
from app.clover.models import CloverInstallation
from app.jds_auth.service import AuthPrincipal
from app.platform.assets import launch_qr_svg, tenant_icon_png
from app.platform.config import default_plan_key, hosted_storefront_hostname, storefront_url
from app.platform.design import DEFAULT_CONFIG, DesignService, DesignValidationError
from app.platform.entitlements import entitlement_features
from app.platform.models import BillingPlan, BusinessProfile, DesignMediaReference, DesignVersion, DesignWorkspace, MediaAsset, OnboardingState, OperationalAuditEvent, OrganizationSubscription, PlatformGrant, StorefrontHostname
from app.platform.media import MediaStorage, MediaValidationError, default_media_storage
from app.platform.readiness import evaluate_publish_readiness, evaluate_storefront_readiness, onboarding_completed_steps, synchronize_public_readiness
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
class StorefrontSlugInput(Strict):
    slug: str = Field(min_length=3,max_length=63,pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

def design_payload(workspace: DesignWorkspace) -> dict:
    return {"revision": workspace.revision, "config": workspace.draft_config, "published_version_id": str(workspace.published_version_id) if workspace.published_version_id else None}

def media_storage(request: Request) -> MediaStorage:
    return getattr(request.app.state, "media_storage", None) or default_media_storage()

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
def manifest(response: Response, tenant: TenantContext = Depends(ladels_compatibility_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    workspace = session.get(DesignWorkspace, tenant.organization_id); version = session.get(DesignVersion, workspace.published_version_id) if workspace and workspace.published_version_id else None
    config = version.config if version else DEFAULT_CONFIG; pwa = config.get("pwa", {})
    version_key=version.version_number if version else 0; cache_key=f"tenant={tenant.organization_id}&v={version_key}"
    response.headers["Cache-Control"]="public, max-age=60" if version else "no-store";response.headers["Vary"]="Host"
    return {"id": f"/{tenant.organization_slug}", "name": config.get("displayName", "Order ahead"), "short_name": pwa.get("shortName", "Order"), "start_url": "/", "scope": "/", "display": "standalone", "theme_color": pwa.get("themeColor", "#6f7d5f"), "background_color": pwa.get("backgroundColor", "#f7f0e6"), "icons":[{"src":f"/api/v1/storefront/icon/192.png?{cache_key}","sizes":"192x192","type":"image/png","purpose":"any"},{"src":f"/api/v1/storefront/icon/512.png?{cache_key}","sizes":"512x512","type":"image/png","purpose":"any"},{"src":f"/api/v1/storefront/icon/192.png?maskable=1&{cache_key}","sizes":"192x192","type":"image/png","purpose":"maskable"},{"src":f"/api/v1/storefront/icon/512.png?maskable=1&{cache_key}","sizes":"512x512","type":"image/png","purpose":"maskable"}]}

@router.get("/storefront/icon/{size}.png")
def storefront_icon(size: int, maskable: bool = False, tenant: TenantContext = Depends(ladels_compatibility_tenant), session: Session = Depends(get_catalog_session)) -> Response:
    workspace=session.get(DesignWorkspace,tenant.organization_id);version=session.get(DesignVersion,workspace.published_version_id) if workspace and workspace.published_version_id else None
    colors=(version.config if version else DEFAULT_CONFIG).get("colors",{})
    try: content=tenant_icon_png(size,colors.get("primary","#6f7d5f"),colors.get("accent","#b98564"),maskable=maskable)
    except ValueError as error: raise HTTPException(404,detail="Icon not found.") from error
    return Response(content=content,media_type="image/png",headers={"Cache-Control":"public, max-age=31536000, immutable","Vary":"Host"})

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
    readiness = evaluate_publish_readiness(session, tenant.organization_id)
    if not readiness.public_ready:
        raise HTTPException(409, detail={"code":"storefront_not_ready","message":"Complete required commerce setup before publishing.","checks":readiness.checks})
    try:
        item = DesignService(session, tenant).publish(principal.user_id)
        synchronize_public_readiness(session,tenant.organization_id);session.commit()
        return {"id":str(item.id),"version":item.version_number}
    except DesignValidationError as error: raise HTTPException(422, detail={"code":"design_invalid","message":str(error)}) from error

@router.post("/owner/design/revert")
def revert_design(payload: RevertInput, principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    try:
        item = DesignService(session, tenant).revert(payload.version_id, principal.user_id); return {"id":str(item.id),"version":item.version_number}
    except DesignValidationError as error: raise HTTPException(404, detail={"code":"version_not_found","message":str(error)}) from error

@router.get("/owner/design/preview")
def design_preview(response: Response, tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    response.headers["Cache-Control"]="private, no-store"
    workspace=DesignService(session,tenant).workspace();profile=session.get(BusinessProfile,tenant.organization_id)
    assets=session.scalars(select(MediaAsset).where(MediaAsset.organization_id==tenant.organization_id,MediaAsset.status=="active")).all()
    return {"tenant":{"id":str(tenant.organization_id),"slug":tenant.organization_slug},"business":business_payload(profile) if profile else None,"design":workspace.draft_config,"draftRevision":workspace.revision,"checkoutEnabled":False,"media":[{"id":str(asset.id),"url":f"/api/v1/owner/media/{asset.id}/content","altText":asset.alt_text} for asset in assets]}

@router.get("/owner/businesses")
def businesses(principal: AuthPrincipal = Depends(current_principal), session: Session = Depends(get_catalog_session)) -> list[dict]:
    rows = session.execute(select(Membership, Organization, Role).join(Organization, Organization.id == Membership.organization_id).join(Role, Role.id == Membership.role_id).where(Membership.user_id == principal.user_id, Membership.status == "active", Organization.is_active.is_(True)).order_by(Organization.name)).all()
    return [{"membershipId":str(m.id),"organizationId":str(o.id),"slug":o.slug,"name":o.name,"role":r.key,"selected":o.id == principal.organization_id} for m,o,r in rows]

@router.get("/owner/onboarding")
def onboarding(tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    item = session.get(OnboardingState, tenant.organization_id) or OnboardingState(organization_id=tenant.organization_id)
    if item not in session: session.add(item); session.commit()
    return {"state":item.state,"currentStep":item.current_step,"completedSteps":item.completed_steps,"publicReady":item.public_ready,"revision":item.revision}

@router.get("/owner/readiness")
def readiness(tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    result = evaluate_storefront_readiness(session, tenant.organization_id)
    return {"publicReady": result.public_ready, "checks": result.checks}

@router.post("/owner/readiness/recheck")
def recheck_readiness(principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    result=synchronize_public_readiness(session,tenant.organization_id)
    session.add(OperationalAuditEvent(organization_id=tenant.organization_id,scope="tenant",actor_user_id=principal.user_id,action="storefront.readiness_checked",target_type="organization",target_id=str(tenant.organization_id),outcome="ready" if result.public_ready else "incomplete",metadata_json={"checks":result.checks}));session.commit()
    return {"publicReady":result.public_ready,"checks":result.checks}

@router.get("/owner/storefront")
def owner_storefront(tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    rows=session.scalars(select(StorefrontHostname).where(StorefrontHostname.organization_id==tenant.organization_id).order_by(StorefrontHostname.created_at.desc())).all()
    return {"slug":tenant.organization_slug,"hostnames":[{"id":str(row.id),"hostname":row.hostname,"status":row.status,"canonical":row.is_canonical} for row in rows]}

@router.get("/owner/storefront/launch-kit")
def launch_kit(tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    hostname=session.scalar(select(StorefrontHostname.hostname).where(StorefrontHostname.organization_id==tenant.organization_id,StorefrontHostname.status=="verified",StorefrontHostname.is_canonical.is_(True)))
    if not hostname: raise HTTPException(409,detail="Verify a canonical storefront before generating launch assets.")
    url=storefront_url(hostname)
    return {"url":url,"qrUrl":"/api/v1/owner/storefront/launch-kit/qr.svg","printUrl":"/api/v1/owner/storefront/launch-kit/print"}

@router.get("/owner/storefront/launch-kit/qr.svg")
def launch_qr(tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> Response:
    hostname=session.scalar(select(StorefrontHostname.hostname).where(StorefrontHostname.organization_id==tenant.organization_id,StorefrontHostname.status=="verified",StorefrontHostname.is_canonical.is_(True)))
    if not hostname: raise HTTPException(409,detail="Verify a canonical storefront first.")
    return Response(content=launch_qr_svg(storefront_url(hostname)),media_type="image/svg+xml",headers={"Cache-Control":"private, no-store"})

@router.get("/owner/storefront/launch-kit/print", response_class=HTMLResponse)
def launch_print(tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> HTMLResponse:
    hostname=session.scalar(select(StorefrontHostname.hostname).where(StorefrontHostname.organization_id==tenant.organization_id,StorefrontHostname.status=="verified",StorefrontHostname.is_canonical.is_(True)))
    profile=session.get(BusinessProfile,tenant.organization_id)
    if not hostname or profile is None: raise HTTPException(409,detail="Complete storefront launch setup first.")
    name=escape(profile.display_name);url=escape(storefront_url(hostname))
    body=f"""<!doctype html><html><head><title>{name} launch sign</title><style>body{{font-family:system-ui;text-align:center;padding:8vh;color:#222}}h1{{font-size:3rem}}img{{width:min(60vw,420px)}}p{{font-size:1.4rem}}@media print{{button{{display:none}}}}</style></head><body><h1>Order ahead from {name}</h1><img src='/api/v1/owner/storefront/launch-kit/qr.svg' alt='QR code for {name}'><p>{url}</p><button onclick='print()'>Print sign</button></body></html>"""
    return HTMLResponse(body,headers={"Cache-Control":"private, no-store"})

@router.put("/owner/storefront")
def choose_storefront(payload: StorefrontSlugInput, principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    hostname=hosted_storefront_hostname(payload.slug)
    if not hostname: raise HTTPException(503,detail="Hosted storefront domains are not configured in this environment.")
    conflict=session.scalar(select(Organization.id).where(Organization.slug==payload.slug,Organization.id!=tenant.organization_id))
    if conflict or session.scalar(select(StorefrontHostname.id).where(StorefrontHostname.hostname==hostname,StorefrontHostname.organization_id!=tenant.organization_id)):
        raise HTTPException(409,detail="That storefront name is unavailable.")
    organization=session.get(Organization,tenant.organization_id);organization.slug=payload.slug
    item=session.scalar(select(StorefrontHostname).where(StorefrontHostname.organization_id==tenant.organization_id,StorefrontHostname.hostname==hostname))
    if item is None:
        item=StorefrontHostname(organization_id=tenant.organization_id,hostname=hostname,status="pending",is_canonical=False);session.add(item)
    session.add(OperationalAuditEvent(organization_id=tenant.organization_id,scope="tenant",actor_user_id=principal.user_id,action="storefront.hostname_requested",target_type="storefront_hostname",target_id=str(item.id),outcome="success",metadata_json={"hostname":hostname}));session.commit()
    return {"id":str(item.id),"slug":payload.slug,"hostname":hostname,"status":item.status}

@router.post("/owner/storefront/{hostname_id}/retry")
def retry_storefront(hostname_id: UUID, principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    item=session.scalar(select(StorefrontHostname).where(StorefrontHostname.id==hostname_id,StorefrontHostname.organization_id==tenant.organization_id))
    if item is None: raise HTTPException(404,detail="Hostname not found.")
    item.status="pending";item.is_canonical=False;item.verified_at=None
    synchronize_public_readiness(session,tenant.organization_id)
    session.add(OperationalAuditEvent(organization_id=tenant.organization_id,scope="tenant",actor_user_id=principal.user_id,action="storefront.hostname_retried",target_type="storefront_hostname",target_id=str(item.id),outcome="success"));session.commit()
    return {"id":str(item.id),"hostname":item.hostname,"status":item.status,"canonical":False}

@router.delete("/owner/storefront/{hostname_id}", status_code=204)
def disable_storefront(hostname_id: UUID, principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> Response:
    item=session.scalar(select(StorefrontHostname).where(StorefrontHostname.id==hostname_id,StorefrontHostname.organization_id==tenant.organization_id))
    if item is None: raise HTTPException(404,detail="Hostname not found.")
    item.status="disabled";item.is_canonical=False;item.verified_at=None
    synchronize_public_readiness(session,tenant.organization_id)
    session.add(OperationalAuditEvent(organization_id=tenant.organization_id,scope="tenant",actor_user_id=principal.user_id,action="storefront.hostname_disabled",target_type="storefront_hostname",target_id=str(item.id),outcome="success"));session.commit()
    return Response(status_code=204)

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
    readiness=evaluate_storefront_readiness(session,tenant.organization_id);derived_steps=onboarding_completed_steps(readiness)
    if item.revision != payload.revision:
        requested_state="complete" if len(derived_steps)==7 else "in_progress"
        if item.completed_steps==derived_steps and item.current_step==payload.current_step and item.state==requested_state:
            return {"state":item.state,"currentStep":item.current_step,"completedSteps":item.completed_steps,"publicReady":item.public_ready,"revision":item.revision}
        raise HTTPException(409, detail="Onboarding changed in another session.")
    allowed={"business","storefront","hours","fulfillment","design","catalog","clover"}
    if not set(payload.completed_steps)<=allowed or payload.current_step not in allowed|{"complete"}: raise HTTPException(422,detail="Invalid onboarding checkpoint.")
    item.completed_steps=derived_steps; item.current_step=payload.current_step; item.revision+=1
    # Checklist state is progress UX only; public availability is authoritative data.
    item.state="complete" if allowed<=set(derived_steps) else "in_progress"
    organization=session.get(Organization,tenant.organization_id)
    if organization and item.state=="complete" and organization.lifecycle_status=="onboarding": organization.lifecycle_status="active"
    synchronize_public_readiness(session, tenant.organization_id)
    session.commit(); return {"state":item.state,"currentStep":item.current_step,"completedSteps":item.completed_steps,"publicReady":item.public_ready,"revision":item.revision}

@router.get("/owner/entitlements")
def entitlements(tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    state,plan,features=entitlement_features(session,tenant.organization_id)
    return {"state":state,"plan":plan,"features":features}

@router.get("/owner/media")
def list_media(tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> list[dict]:
    rows=session.scalars(select(MediaAsset).where(MediaAsset.organization_id==tenant.organization_id,MediaAsset.status=="active").order_by(MediaAsset.created_at.desc())).all()
    return [{"id":str(item.id),"storageKey":item.storage_key,"mediaType":item.media_type,"altText":item.alt_text,"byteSize":item.byte_size,"url":f"/api/v1/storefront/media/{item.id}","ownerUrl":f"/api/v1/owner/media/{item.id}/content"} for item in rows]

@router.post("/owner/media/upload", status_code=201)
async def upload_media(request: Request, principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session), content_type: str = Header(alias="Content-Type"), alt_text: str = Header(default="",alias="X-Media-Alt")) -> dict:
    if len(alt_text) > 300: raise HTTPException(422,detail="Alternative text is too long.")
    data=await request.body(); media_id=uuid4(); item=MediaAsset(id=media_id,organization_id=tenant.organization_id,created_by_user_id=principal.user_id,storage_key="pending",media_type=content_type.split(";",1)[0].lower(),alt_text=alt_text.strip(),byte_size=len(data),checksum="0"*64)
    try:
        storage=media_storage(request);storage_key,checksum=storage.put(tenant.organization_id,media_id,data,item.media_type)
    except MediaValidationError as error: raise HTTPException(422,detail=str(error)) from error
    try:
        item.storage_key=storage_key;item.checksum=checksum;session.add(item);session.add(OperationalAuditEvent(organization_id=tenant.organization_id,scope="tenant",actor_user_id=principal.user_id,action="media.uploaded",target_type="media_asset",target_id=str(item.id),outcome="success",metadata_json={"mediaType":item.media_type,"byteSize":item.byte_size}));session.commit()
    except Exception:
        session.rollback();storage.delete(storage_key);raise
    return {"id":str(item.id),"mediaType":item.media_type,"altText":item.alt_text,"byteSize":item.byte_size,"url":f"/api/v1/storefront/media/{item.id}","ownerUrl":f"/api/v1/owner/media/{item.id}/content"}

@router.get("/storefront/media/{media_id}")
def storefront_media(media_id: UUID, request: Request, tenant: TenantContext = Depends(ladels_compatibility_tenant), session: Session = Depends(get_catalog_session)) -> FileResponse:
    item=session.scalar(select(MediaAsset).where(MediaAsset.id==media_id,MediaAsset.organization_id==tenant.organization_id,MediaAsset.status=="active"))
    if item is None: raise HTTPException(404,detail="Media not found.")
    try: path=media_storage(request).local_path(item.storage_key)
    except MediaValidationError as error: raise HTTPException(404,detail="Media not found.") from error
    if not path.is_file(): raise HTTPException(404,detail="Media not found.")
    return FileResponse(path,media_type=item.media_type,headers={"Cache-Control":"public, max-age=31536000, immutable","Vary":"Host"})

@router.get("/owner/media/{media_id}/content")
def owner_media(media_id: UUID, request: Request, tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> FileResponse:
    item=session.scalar(select(MediaAsset).where(MediaAsset.id==media_id,MediaAsset.organization_id==tenant.organization_id,MediaAsset.status=="active"))
    if item is None: raise HTTPException(404,detail="Media not found.")
    try: path=media_storage(request).local_path(item.storage_key)
    except MediaValidationError as error: raise HTTPException(404,detail="Media not found.") from error
    if not path.is_file(): raise HTTPException(404,detail="Media not found.")
    return FileResponse(path,media_type=item.media_type,headers={"Cache-Control":"private, no-store"})

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
    referenced=session.scalar(select(DesignMediaReference.id).where(DesignMediaReference.organization_id==tenant.organization_id,DesignMediaReference.media_asset_id==media_id).limit(1))
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

@router.get("/platform/admin/organizations/{organization_id}")
def platform_organization_detail(organization_id: UUID, principal: AuthPrincipal = Depends(current_principal), session: Session = Depends(get_catalog_session)) -> dict:
    grant=session.scalar(select(PlatformGrant.id).where(PlatformGrant.user_id==principal.user_id,PlatformGrant.capability=="platform.organizations.read",PlatformGrant.is_active.is_(True)))
    if grant is None: raise HTTPException(403,detail={"code":"platform_access_required","message":"Platform access is not authorized."})
    organization=session.get(Organization,organization_id)
    if organization is None: raise HTTPException(404,detail="Organization not found.")
    readiness=evaluate_storefront_readiness(session,organization_id)
    hostnames=session.scalars(select(StorefrontHostname).where(StorefrontHostname.organization_id==organization_id).order_by(StorefrontHostname.created_at.desc())).all()
    audits=session.scalars(select(OperationalAuditEvent).where(OperationalAuditEvent.organization_id==organization_id).order_by(OperationalAuditEvent.occurred_at.desc()).limit(50)).all()
    result={"id":str(organization.id),"name":organization.name,"slug":organization.slug,"status":organization.lifecycle_status,"readiness":{"publicReady":readiness.public_ready,"checks":readiness.checks},"hostnames":[{"id":str(item.id),"hostname":item.hostname,"status":item.status,"canonical":item.is_canonical} for item in hostnames],"audit":[{"action":item.action,"outcome":item.outcome,"targetType":item.target_type,"targetId":item.target_id,"occurredAt":item.occurred_at} for item in audits]}
    session.add(OperationalAuditEvent(scope="platform",actor_user_id=principal.user_id,action="platform.organization_viewed",target_type="organization",target_id=str(organization_id),outcome="success"));session.commit()
    return result

@router.get("/owner/platform-capabilities")
def platform_capabilities(principal: AuthPrincipal = Depends(current_principal), session: Session = Depends(get_catalog_session)) -> dict:
    capabilities = session.scalars(select(PlatformGrant.capability).where(
        PlatformGrant.user_id == principal.user_id,
        PlatformGrant.is_active.is_(True),
    ).order_by(PlatformGrant.capability)).all()
    return {"capabilities": capabilities}

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
    hostname = hosted_storefront_hostname(payload.slug)
    records = [
        Membership(organization_id=item.id,application_id=application.id,user_id=owner.id,role_id=role.id,status="active",joined_at=datetime.now(timezone.utc)),
        BusinessProfile(organization_id=item.id,display_name=payload.display_name.strip()),
        OnboardingState(organization_id=item.id,state="in_progress",current_step="business",public_ready=False),
        OperationalAuditEvent(organization_id=item.id,scope="platform",actor_user_id=principal.user_id,action="platform.organization_provisioned",target_type="organization",target_id=str(item.id),outcome="success"),
    ]
    if hostname:
        records.append(StorefrontHostname(organization_id=item.id,hostname=hostname,is_canonical=True,status="pending"))
    plan_key = default_plan_key()
    if plan_key and session.get(BillingPlan, plan_key):
        records.append(OrganizationSubscription(organization_id=item.id,plan_key=plan_key,state="trialing",provider="unconfigured"))
    session.add_all(records);session.commit()
    return {"id":str(item.id),"slug":item.slug,"hostname":hostname,"status":item.lifecycle_status,"publicReady":False}

@router.post("/platform/admin/hostnames/{hostname_id}/verify")
def verify_hostname(hostname_id: UUID, principal: AuthPrincipal = Depends(csrf_principal), session: Session = Depends(get_catalog_session)) -> dict:
    grant=session.scalar(select(PlatformGrant.id).where(PlatformGrant.user_id==principal.user_id,PlatformGrant.capability=="platform.organizations.write",PlatformGrant.is_active.is_(True)))
    if grant is None: raise HTTPException(403,detail={"code":"platform_access_required","message":"Platform hostname verification is not authorized."})
    item=session.get(StorefrontHostname,hostname_id)
    if item is None or item.status=="disabled": raise HTTPException(404,detail="Hostname not found.")
    session.execute(StorefrontHostname.__table__.update().where(StorefrontHostname.organization_id==item.organization_id,StorefrontHostname.id!=item.id).values(is_canonical=False))
    item.status="verified";item.is_canonical=True;item.verified_at=datetime.now(timezone.utc)
    result=synchronize_public_readiness(session,item.organization_id)
    session.add(OperationalAuditEvent(organization_id=item.organization_id,scope="platform",actor_user_id=principal.user_id,action="storefront.hostname_verified",target_type="storefront_hostname",target_id=str(item.id),outcome="success",metadata_json={"hostname":item.hostname}));session.commit()
    return {"id":str(item.id),"hostname":item.hostname,"status":item.status,"canonical":True,"publicReady":result.public_ready}
